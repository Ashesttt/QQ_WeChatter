import re
from typing import Dict
import inspect
from datetime import datetime

from loguru import logger

from wechatter.bot import BotInfo
from wechatter.config import config
from wechatter.database import QuotedResponse, make_db_session, MessageStats, CommandStats
from wechatter.message.message_forwarder import MessageForwarder
from wechatter.models.wechat import Message, SendTo

message_forwarder = MessageForwarder()
if config["message_forwarding_enabled"]:
    message_forwarder.set_wechat_forwarding_rule(config["message_forwarding_rule_list"])

if config["official_account_reminder_enabled"]:
    message_forwarder.set_official_account_reminder_rule(
        config["official_account_reminder_rule_list"]
    )

if config["discord_message_forwarding_enabled"]:
    message_forwarder.set_discord_forwarding_rule(
        config["discord_message_forwarding_rule_list"]
    )


# message_forwarder.official_account_reminder_type = config[
#     "official_account_reminder_type"
# ]


class MessageHandler:
    """
    消息处理器，用于处理用户发来的消息
    """

    def __init__(self, commands: Dict, quoted_handlers: Dict, games: Dict):
        """
        :param commands: 命令处理函数字典
        :param quoted_handlers: 可引用的命令消息处理函数字典
        """
        self.commands = commands
        self.quoted_handlers = quoted_handlers
        self.games = games

    async def handle_message(self, message_obj: Message):
        """
        处理消息
        :param message_obj: 消息对象
        """
        # 判断是否为黑名单
        if (
            config.get("ban_person_list")
            and message_obj.person.name in config["ban_person_list"]
        ):
            logger.info(f"黑名单用户：{message_obj.person.name}")
            return
        if (
            message_obj.is_group
            and config.get("ban_group_list")
            and message_obj.group.name in config["ban_group_list"]
        ):
            logger.info(f"黑名单群：{message_obj.group.name}")
            return

        # 公众号文章提醒
        if (
            config["official_account_reminder_enabled"]
            and message_obj.is_official_account
            and message_obj.type.value == "urlLink"
        ):
            # 尝试提醒
            message_forwarder.remind_official_account_article(message_obj)
            return

        # 判断是否为拍一拍
        if message_obj.is_tickled and not message_obj.is_from_self:
            # 回复 Hello, WeChatter
            to = SendTo(person=message_obj.person, group=message_obj.group)
            from wechatter.app.routers.qq_bot import reply_tickled
            reply_tickled(to)
            return

        # if message_obj.type.value == "unknown":
        #     logger.info("未知消息类型")
        #     return

        # 消息转发
        if config["message_forwarding_enabled"] and not message_obj.is_official_account:
            # 尝试进行消息转发
            message_forwarder.forwarding_to_wechat(message_obj)
            # 尝试进行转发消息的回复
            if message_obj.forwarded_source_name:
                message_forwarder.reply_wechat_forwarded_message(message_obj)
                return

        # Discord消息转发
        if (
            config["discord_message_forwarding_enabled"]
            and not message_obj.is_official_account
        ):
            message_forwarder.forwarding_to_discord(message_obj)

        # 判断是否是自己的消息，是则需要将 to 设置为对方
        if message_obj.is_from_self and not message_obj.is_group:
            to = SendTo(person=message_obj.receiver, group=message_obj.group)
        else:
            to = SendTo(person=message_obj.person, group=message_obj.group)

        # 解析命令
        content = message_obj.content
        cmd_dict = self.__parse_command(
            content, message_obj.is_mentioned, message_obj.is_group
        )

        # 是可引用的命令消息
        if message_obj.quotable_id:
            quoted_response = _get_quoted_response(message_obj.quotable_id)
            quoted_handler = self.quoted_handlers.get(quoted_response.command, None)
            _execute_quoted_handler(
                quoted_handler, to, message_obj, quoted_response=quoted_response
            )
            return

        # 是命令消息
        if not cmd_dict["command"] == "None":
            logger.info(cmd_dict["desc"])
            # TODO: 可以为不同的群设置是否need_mentioned
            if (
                config["need_mentioned"]
                and message_obj.is_group
                and not message_obj.is_mentioned
            ):
                logger.debug("该消息为群消息，但未@机器人，不处理")
                return
            # 开始处理命令
            await _execute_command(cmd_dict, to, message_obj)
        else:
            # 判断是否配置了默认GPT命令，若有则触发GPT命令
            if (
                # message_obj.type != "file" and 
                message_obj.sender_name in config.get("gpt_mode_person_list", [])
            ):
                cmd_dict["command"] = config.get("gpt_mode_model", "gemini")
                cmd_dict["handler"] = self.commands.get(cmd_dict["command"], {}).get(
                    "handler", None
                )
                cmd_dict["desc"] = self.commands.get(cmd_dict["command"], {}).get(
                    "desc", ""
                )
                cmd_dict["args"] = content
                cmd_dict["param_count"] = self.commands.get(
                    cmd_dict["command"], {}
                ).get("param_count", 0)
                logger.info(f"默认触发GPT命令：{cmd_dict['command']}")
                await _execute_command(cmd_dict, to, message_obj)
            logger.debug("该消息不是命令类型")

        # 更新消息统计
        with make_db_session() as session:
            msg_stats = session.query(MessageStats).first()
            if not msg_stats:
                msg_stats = MessageStats(
                    total_messages=0,
                    command_messages=0,
                    group_messages=0,
                    private_messages=0,
                    last_updated=datetime.now()
                )
                session.add(msg_stats)
            
            msg_stats.total_messages += 1
            if message_obj.is_group:
                msg_stats.group_messages += 1
            else:
                msg_stats.private_messages += 1
            
            if not cmd_dict["command"] == "None":
                msg_stats.command_messages += 1
                # 更新命令统计
                cmd_stat = session.query(CommandStats).filter_by(command_name=cmd_dict["command"]).first()
                if not cmd_stat:
                    cmd_stat = CommandStats(
                        command_name=cmd_dict["command"],
                        use_count=0,
                        last_used=datetime.now()
                    )
                    session.add(cmd_stat)
                cmd_stat.use_count += 1
                cmd_stat.last_used = datetime.now()
            
            msg_stats.last_updated = datetime.now()
            session.commit()

    def __parse_command(self, content: str, is_mentioned: bool, is_group: bool) -> Dict:
        """
        解析命令
        :param content: 消息内容
        :param is_mentioned: 是否@机器人
        :param is_group: 是否群消息
        """
        cmd_dict = {
            "command": "None",
            "desc": "",
            "args": "",
            "handler": None,
            "param_count": 0,
        }
        # 不带命令前缀和@前缀的消息内容
        if is_mentioned and is_group:
            # 去掉"@机器人名"的前缀
            content = content.replace(f"@{BotInfo.name} ", "")
        for command, info in self.commands.items():
            # 第一个空格或回车前的内容即为指令
            cont_list = re.split(r"\s|\n", content, 1)
            if config.get("command_prefix") is not None:
                if not cont_list[0].startswith(config["command_prefix"]):
                    continue
                # 去掉命令前缀
                no_prefix = cont_list[0][len(config["command_prefix"]) :]
            else:
                no_prefix = cont_list[0]
            if no_prefix.lower() in info["keys"]:
                cmd_dict["command"] = command
                cmd_dict["desc"] = info["desc"]
                cmd_dict["handler"] = info["handler"]
                cmd_dict["param_count"] = info["param_count"]
                if len(cont_list) == 2:
                    cmd_dict["args"] = cont_list[1]  # 消息内容
                return cmd_dict
        return cmd_dict


async def _execute_command(cmd_dict: Dict, to: SendTo, message_obj: Message):
    """
    执行命令
    :param cmd_dict: 命令字典
    :param to: 发送对象
    :param message_obj: 消息对象
    """
    cmd_handler = cmd_dict["handler"]
    if cmd_handler is not None:
        if cmd_dict["param_count"] == 2:
            if inspect.iscoroutinefunction(cmd_handler):
                await cmd_handler(
                    to=to,
                    message=cmd_dict["args"],
                )
            else:
                cmd_handler(
                    to=to,
                    message=cmd_dict["args"],
                )
        elif cmd_dict["param_count"] == 3:
            if inspect.iscoroutinefunction(cmd_handler):
                await cmd_handler(
                    to=to,
                    message=cmd_dict["args"],
                    message_obj=message_obj,
                )
            else:
                cmd_handler(
                    to=to,
                    message=cmd_dict["args"],
                    message_obj=message_obj,
                )
    else:
        logger.error("该命令未实现")


def _execute_quoted_handler(
    quoted_handler, to: SendTo, message_obj: Message, quoted_response: QuotedResponse
):
    """
    执行可引用的命令消息处理函数
    :param quoted_handler: 可引用的命令消息处理函数
    :param to: 发送对象
    :param message_obj: 消息内容
    :param quoted_response: 可引用的命令消息
    """

    if quoted_handler:
        quoted_handler(
            to=to,
            # message=message_obj.pure_content,
            message=message_obj.content,
            q_response=quoted_response.response,
        )
    else:
        logger.warning(f"未找到可引用的命令消息处理函数: {quoted_response.command}")


def _get_quoted_response(quotable_id: str) -> QuotedResponse:
    """
    获取可引用的命令消息
    :param quotable_id: 可引用的命令消息id
    :return: 可引用的命令消息
    """

    with make_db_session() as session:
        _quoted_response = (
            session.query(QuotedResponse)
            .filter_by(quotable_id=quotable_id)
            .order_by(QuotedResponse.id.desc())
            .first()
        )
        quoted_response = _quoted_response.to_model()
    return quoted_response
