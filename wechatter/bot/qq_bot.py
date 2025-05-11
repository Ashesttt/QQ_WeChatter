import botpy
from botpy import logging
from botpy.message import DirectMessage, Message
from loguru import logger

from wechatter.bot import BotInfo
from wechatter.config import config


class QQBot(botpy.Client):
    """QQ机器人处理类"""
    
        
    async def on_ready(self):
        """机器人就绪事件"""
        logger.info(f"机器人 {self.robot.name} 已就绪")
        # user = await self.api.me()
        BotInfo.update_name(self.robot.name)
        BotInfo.update_id(self.robot.id)
    
    async def on_direct_message_create(self, message: DirectMessage):
        """当收到私信消息时"""
        logger.info(f"收到私信: {message.content}")
        await self.api.post_dms(
            guild_id=message.guild_id,
            content=f"你好，我是{self.robot.name}，我收到了你的私信：{message.content}",
            msg_id=message.id
        )

def create_qq_bot():
    """创建QQ机器人实例"""
    bot_config = config.get("qq_bot", {})
    
    # 设置机器人意图
    intents_type = bot_config.get("intents", "all")
    if intents_type == "all":
        intents = botpy.Intents.all()
    elif intents_type == "guild_messages":
        intents = botpy.Intents(public_guild_messages=True)
    elif intents_type == "direct_messages":
        intents = botpy.Intents(direct_messages=True)
    else:
        intents = botpy.Intents.all()
    
    # 创建客户端
    client = QQBot(intents=intents)
    return client
