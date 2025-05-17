import json
from typing import Union

from loguru import logger

from wechatter.commands.handlers import command
from wechatter.models.wechat import QuotedResponse, SendTo
from wechatter.sender import sender
from wechatter.database import make_db_session, QuotedResponse as DbQuotedResponse

COMMAND_NAME = "quoted"

@command(
    command=COMMAND_NAME,
    keys=["引用", "quoted"],
    desc="引用任意可引用消息。",
)
def quoted_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    """
    直接通过 quotable_id 和参数引用任意可引用消息
    """
    # 解析参数
    parts = message.strip().split()
    if len(parts) < 2:
        sender.send_msg(to, "用法：/引用 quotable_id 参数\n如：/引用 00F 1")
        return
    quotable_id, param = parts[0], " ".join(parts[1:])

    # 查找引用内容
    with make_db_session() as session:
        db_qr = session.query(DbQuotedResponse).filter_by(quotable_id=quotable_id).order_by(DbQuotedResponse.id.desc()).first()
        if not db_qr:
            sender.send_msg(to, f"未找到可引用消息ID：{quotable_id}")
            return
        quoted_response = db_qr.to_model()

    # 触发对应的 quoted_handler
    from wechatter.commands.handlers import quoted_handlers
    handler = quoted_handlers.get(quoted_response.command)
    if not handler:
        sender.send_msg(to, f"未找到该引用消息的处理函数：{quoted_response.command}")
        return

    # 直接调用 quoted_handler
    handler(
        to if isinstance(to, SendTo) else SendTo(person=None, group=None),  # 兼容性
        param,
        quoted_response.response
    )

# 这个命令本身不需要 quoted_handler和mainfunc
