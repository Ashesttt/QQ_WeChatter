import os
import re
from datetime import datetime
from typing import Union

from mcp.server.fastmcp.server import logger

from wechatter.commands.handlers import command
from wechatter.models.wechat import SendTo
from wechatter.sender import sender
from wechatter.utils import get_abs_path, load_json, save_json

# 提醒数据存储路径
REMIND_DATA_PATH = get_abs_path("data/reminds")

@command(
    command="remind",
    keys=["提醒", "remind"],
    desc="设置提醒功能。格式: /remind [内容] [时间]"
)
async def remind_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    """
    提醒功能处理函数
    格式: /remind [内容] [时间]
    时间格式: 
        - 绝对时间: YYYYMMDDHHMM (如202505182159)
        - 相对时间: 今天/明天HHMM (如今天2159, 明天2200)
    """
    if not message:
        _message = "请输入提醒内容和时间。格式: /remind [内容] [时间]。\n"
        _message += """    时间格式: 
        - 绝对时间: YYYYMMDDHHMM (如202505182159)
        - 相对时间: 今天/明天HHMM (如今天2159, 明天2200)"""
        sender.send_msg(to, _message)
        return

    # 解析内容和时间
    parts = message.split(maxsplit=1)
    if len(parts) < 2:
        sender.send_msg(to, "格式错误。正确格式: /remind [内容] [时间]")
        return

    content, time_str = parts
    
    try:
        # 解析时间
        trigger_time = parse_time(time_str)
        logger.critical(f"to:{to}")
        # 保存提醒
        remind_id = save_remind(to.p_id, content, trigger_time)
        
        # 返回成功消息
        sender.send_msg(to, f"✅ 提醒设置成功！\n内容: {content}\n时间: {trigger_time.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"{to.p_id} 设置了提醒: {content}")
        
    except ValueError as e:
        sender.send_msg(to, f"❌ 设置提醒失败: {str(e)}")
        logger.error(f"{to.p_id} 设置提醒失败: {str(e)}")


def parse_time(time_str: str) -> datetime:
    """
    解析时间字符串
    """
    # 绝对时间格式: YYYYMMDDHHMM
    if re.fullmatch(r"\d{12}", time_str):
        try:
            return datetime.strptime(time_str, "%Y%m%d%H%M")
        except ValueError:
            raise ValueError("时间格式错误，请使用YYYYMMDDHHMM格式")
    
    # 相对时间格式: 今天/明天HHMM
    match = re.fullmatch(r"(今天|明天)(\d{4})", time_str)
    if match:
        day_type, time_part = match.groups()
        now = datetime.now()
        
        try:
            hour = int(time_part[:2])
            minute = int(time_part[2:])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except ValueError:
            raise ValueError("时间格式错误，请使用HHMM格式(0000-2359)")
        
        if day_type == "今天":
            return datetime(now.year, now.month, now.day, hour, minute)
        else:  # 明天
            return datetime(now.year, now.month, now.day + 1, hour, minute)
    
    raise ValueError("时间格式错误，请使用YYYYMMDDHHMM或今天/明天HHMM格式")


def save_remind(person_id: str, content: str, trigger_time: datetime) -> str:
    """
    保存提醒到JSON文件
    """
    
    # 生成唯一ID
    remind_id = f"remind_{int(trigger_time.timestamp())}_{person_id}"
    
    # 构造提醒数据
    remind_data = {
        "id": remind_id,
        "person_id": person_id,
        "content": content,
        "trigger_time": trigger_time.strftime("%Y-%m-%d %H:%M:%S"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # 保存到文件
    file_path = os.path.join(REMIND_DATA_PATH, f"{person_id}_reminds.json")
    reminds = []
    
    if os.path.exists(file_path):
        reminds = load_json(file_path)
    
    reminds.append(remind_data)
    save_json(file_path, reminds)
    
    return remind_id
