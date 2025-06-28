from sqlalchemy import Column, Integer, String, DateTime, Float
from wechatter.database.tables import Base


class MessageStats(Base):
    """消息统计表"""
    __tablename__ = 'message_stats'

    id = Column(Integer, primary_key=True)
    total_messages = Column(Integer, default=0)  # 总消息数
    command_messages = Column(Integer, default=0)  # 命令消息数
    group_messages = Column(Integer, default=0)  # 群消息数
    private_messages = Column(Integer, default=0)  # 私聊消息数
    last_updated = Column(DateTime)  # 最后更新时间

class CommandStats(Base):
    """命令使用统计表"""
    __tablename__ = 'command_stats'

    id = Column(Integer, primary_key=True)
    command_name = Column(String(50))  # 命令名称
    use_count = Column(Integer, default=0)  # 使用次数
    last_used = Column(DateTime)  # 最后使用时间
