# 机器人信息类
import json


# TODO: 做成单例模式
class BotInfo:
    """机器人信息类"""

    id: str = ""
    name: str = ""
    start_time: float = 0.0

    @staticmethod
    def update_from_source(source: str) -> None:
        """从消息来源更新机器人信息"""
        source_dict = {}
        try:
            source_dict = json.loads(source)
        except Exception:
            print("更新机器人信息时，消息来源JSON解析失败")
            return
        to = source_dict.get("to", {})
        if to == "":
            return
        payload = to.get("payload", {})
        BotInfo.id = payload.get("id", "")
        BotInfo.name = payload.get("name", "")

    @staticmethod
    def update_id(id: str) -> None:
        """更新机器人ID"""
        BotInfo.id = id

    @staticmethod
    def update_name(name: str) -> None:
        """更新机器人名称"""
        BotInfo.name = name

    @staticmethod
    def update_start_time(start_time: float) -> None:
        """更新机器人启动时间"""
        BotInfo.start_time = start_time
