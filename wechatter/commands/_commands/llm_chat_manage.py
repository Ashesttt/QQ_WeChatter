from loguru import logger

from wechatter.config import config
from ..basechat import BaseChat
from ..handlers import command
from ...models.wechat import SendTo
from wechatter.utils import run_in_thread


class Chat(BaseChat):
    def __init__(self, model, api_url, token):
        super().__init__(
            model=model,
            api_url=api_url,
            token="Bearer " + token
        )


# 读取配置文件
llms_config = config["llms"]

# 创建 Chat 实例并动态注册命令
chat_instances = {}

def register_commands(command_name, chat_instance):

    pure_command_name = get_pure_command_name(command_name)#为了兼容qq的快捷命令（command不能存在符号，如：/deepseekv3, sparkx1）
    @command(
        command=command_name,
        keys=[command_name, f"{command_name}_chat", pure_command_name],
        desc=f"与 {command_name} AI 聊天",
    )
    @run_in_thread() # 在单独线程中运行
    def chat_command_handler(to: SendTo, message: str = "", message_obj=None):
        chat_instance.gptx(command_name, chat_instance.model, to, message, message_obj)
        logger.warning(f"{command_name}命令已注册，模型为 {chat_instance.model}")

    @command(
        command=f"{command_name}-chats",
        keys=[f"{command_name}-chats", f"{command_name}对话记录", f"{pure_command_name}-chats", f"{pure_command_name}对话记录"],
        desc=f"列出{command_name}对话记录。",
    )
    async def chats_command_handler(to: SendTo, message: str = "", message_obj=None):
        chat_instance.gptx_chats(chat_instance.model, to, message, message_obj)

    @command(
        command=f"{command_name}-record",
        keys=[f"{command_name}-record", f"{command_name}记录", f"{pure_command_name}-record", f"{pure_command_name}记录"],
        desc=f"获取{command_name}对话记录。",
    )
    async def record_command_handler(to: SendTo, message: str = "", message_obj=None):
        chat_instance.gptx_record(chat_instance.model, to, message)

    @command(
        command=f"{command_name}-continue",
        keys=[f"{command_name}-continue", f"{command_name}继续", f"{pure_command_name}-continue", f"{pure_command_name}继续"],
        desc=f"继续{command_name}对话。",
    )
    async def continue_command_handler(to: SendTo, message: str = "", message_obj=None):
        chat_instance.gptx_continue(chat_instance.model, to, message)
        
def get_pure_command_name(command_name):
    # 去掉-或者_
    return command_name.replace("-", "").replace("_", "")

for command_name, model_config in llms_config.items():
    chat_instance = Chat(
        model=model_config["model"],
        api_url=model_config["api_url"],
        token=model_config["token"],
    )
    chat_instances[command_name] = chat_instance
    register_commands(command_name, chat_instance)
