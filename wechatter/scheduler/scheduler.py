from typing import List
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger
from sqlalchemy import true

from wechatter.models import Person
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
                for remind in expired_reminds:
                    try:
                        from wechatter.models.wechat import Group
                        
                        person = None
                        if remind['to']['person']['id']:
                            person = Person(
                                 id=remind['to']['person']['id'],
                                 name=remind['to']['person']['name'],
                                 alias='',
                                 gender='male',
                                 is_star=False,
                                 is_friend=True,
                                 user_openid=remind['to']['person']['user_openid'],
                                 member_openid=remind['to']['person']['member_openid']
                             )
                        
                        group = None
                        if remind['to']['group']['id']:
                            group = Group(
                                id=remind['to']['group']['id'],
                                name=remind['to']['group']['name']
                            )
                        
                        to = SendTo(
                            p_id=remind['to']['p_id'],
                            p_name=remind['to']['p_name'],
                            g_id=remind['to']['g_id'],
                            g_name=remind['to']['g_name'],
                            person=person,
                            group=group
                        )
                        if to.g_id and to.g_name:
                            _is_group = True
                        else:
                            _is_group = False
                        # 修改send_msg调用方式
                        sender.send_msg(
                            to=to,
                            message=f"⏰ 提醒: {remind['content']}",
                            is_group=_is_group
                        )
                        logger.info(f"已发送提醒: {remind['content']} 给{to.p_id}")
                    except Exception as e:
                        logger.error(f"发送提醒失败: {str(e)}")
                
                # 更新提醒文件，移除已发送的提醒
                updated_reminds = [
                    r for r in reminds 
                    if datetime.strptime(r['trigger_time'], '%Y-%m-%d %H:%M:%S') > current_time
                ]
                
                # 保存更新后的提醒
                save_json(file_path, updated_reminds)
