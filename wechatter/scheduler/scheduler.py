from typing import List
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from wechatter.models.scheduler import CronTask
from wechatter.models.wechat import SendTo
from wechatter.sender import sender
from wechatter.utils import get_abs_path, load_json, save_json

# 提醒数据存储路径
REMIND_DATA_PATH = get_abs_path("data/reminds")

class Scheduler:
    def __init__(self, cron_task_list: List[CronTask] = None):
        self.scheduler = BackgroundScheduler()
        self.cron_task_list = cron_task_list

    def startup(self):
        """
        启动定时任务
        """
        if not self.cron_task_list:
            logger.info("定时任务为空，不启动定时任务")
            return
        for cron_task in self.cron_task_list:
            if cron_task.enabled:
                for func, args in cron_task.funcs:
                    self.scheduler.add_job(func, cron_task.cron_trigger, args=args)
                logger.info(f"定时任务已添加: {cron_task.desc}")
        
        # 添加提醒检查任务
        self.scheduler.add_job(
            self._check_reminds,
            'interval',
            minutes=1,
            id='remind_checker'
        )
        
        self.scheduler.start()
        logger.info("定时任务已启动")

    def shutdown(self):
        """
        停止定时任务
        """
        self.scheduler.shutdown()
        logger.info("定时任务已停止")

    def _check_reminds(self):
        """
        检查并执行到期的提醒
        """
        current_time = datetime.now()
        
        # 遍历所有提醒文件
        for filename in os.listdir(REMIND_DATA_PATH):
            if filename.endswith('_reminds.json'):
                file_path = os.path.join(REMIND_DATA_PATH, filename)
                reminds = load_json(file_path)
                
                # 过滤出已过期的提醒
                expired_reminds = [
                    r for r in reminds 
                    if datetime.strptime(r['trigger_time'], '%Y-%m-%d %H:%M:%S') <= current_time
                ]
                
                if not expired_reminds:
                    continue
                
                # 发送提醒
                person_id = filename.split('_')[0]
                for remind in expired_reminds:
                    try:
                        from wechatter.models.wechat import Person
                        person = Person(id=person_id)
                        to = SendTo(person=person)
                        sender.mass_send_msg(
                            to=to,
                            message=f"⏰ 提醒: {remind['content']}",
                            is_group=False
                        )
                        logger.info(f"已发送提醒: {remind['content']} 给 {person_id}")
                    except Exception as e:
                        logger.error(f"发送提醒失败: {str(e)}")
                
                # 更新提醒文件，移除已发送的提醒
                updated_reminds = [
                    r for r in reminds 
                    if datetime.strptime(r['trigger_time'], '%Y-%m-%d %H:%M:%S') > current_time
                ]
                
                # 保存更新后的提醒
                save_json(file_path, updated_reminds)
