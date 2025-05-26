# 获取命令帮助消息
from typing import Union
from wechatter.commands import commands
from wechatter.commands.handlers import command
from wechatter.commands.mcp import mcp_server
from wechatter.config import config
from wechatter.models.wechat import SendTo
from wechatter.sender import sender
from wechatter.utils import text_to_image


@command(command="help", keys=["帮助", "help"], desc="获取帮助信息。")
async def help_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    # # 获取帮助信息(文本)
    # from command.help import get_help_msg
    # response = get_help_msg()

    # 获取帮助信息(图片)

    help_msg = get_help_msg()
    response = text_to_image(help_msg)
    if response:
        sender.send_msg(to, response, type="localfile")

@command(command="help_txt", keys=["帮助(文本)", "help_txt", "help-txt", "文本帮助"], desc="获取帮助信息(文本)。")
async def help_txt_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    help_msg = get_help_msg()
    sender.send_msg(to, help_msg, type="text")


def get_help_msg() -> str:
    help_msg = "=====帮助信息=====\n"
    for value in commands.values():
        if value == "None":
            continue
        cmd_msg = ""
        for key in value["keys"]:
            if config.get("command_prefix"):
                cmd_msg += config["command_prefix"] + key + "\n"
            else:
                cmd_msg += key + "\n"
        help_msg += cmd_msg + "-->「" + value["desc"] + "」\n\n"
    return help_msg

@mcp_server.tool(
    name="get_help_txt_msg",
    description="获取帮助文本信息。",
)
async def get_help_txt_msg():
    """
    获取帮助文本信息
    :return: 返回帮助文本信息（注意是文本）
    """
    help_msg = get_help_msg()
    return help_msg
