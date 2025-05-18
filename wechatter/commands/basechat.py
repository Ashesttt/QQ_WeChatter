# base_chat.py
from datetime import datetime
from typing import List, Union

from loguru import logger

from wechatter.database import (
    GptChatInfo as DbGptChatInfo,
    GptChatMessage as DbGptChatMessage,
    make_db_session,
)
from wechatter.models.gpt import GptChatInfo
from wechatter.models.wechat import Person, SendTo
from wechatter.sender import sender
from wechatter.utils import post_request_json
from wechatter.utils.time import get_current_date, get_current_week, get_current_time

DEFAULT_TOPIC = "（对话进行中*）"
DEFAULT_CONVERSATION = [
    {
        "role": "system",
        "content": f"""
        你是一个叫 WeChatter 的虚拟助手。今天是{get_current_date()}，星期{get_current_week()}，现在是{get_current_time()}。
        请严格遵守以下要求：
        1. 所有回复必须使用纯文本
        2. 禁止使用任何 Markdown 格式（包括**粗体*、_斜体_、代码块等）
        3. 禁止使用列表符号（如- *等）
        4. 用自然段落的文字回答
        """
    }
]


class BaseChat:
    def __init__(self, model: str, api_url: str, token: str):
        self.model = model
        self.api_url = api_url
        self.token = token

    def gptx(self, command_name: str, model: str, to: SendTo, message: str = "", message_obj=None) -> None:
        person = to.person
        # 获取文件夹下最新的对话记录
        chat_info = BaseChat.get_chatting_chat_info(person, model)
        if message == "":  # /gpt4
            # 判断对话是否有效
            sender.send_msg(to, "正在创建新对话...")
            if chat_info is None or BaseChat._is_chat_valid(chat_info):
                BaseChat.create_chat(self, person, model)
                logger.info("创建新对话成功")
                sender.send_msg(to, "创建新对话成功")
                return
            logger.info("对话未开始，继续上一次对话")
            sender.send_msg(to, "对话未开始，继续上一次对话")
        else:  # /gpt4 <message>
            # 如果没有对话记录，则创建新对话
            sender.send_msg(to, f"正在调用 {command_name} 进行对话，LLM模型为 {model}...")
            if chat_info is None:
                chat_info = BaseChat.create_chat(self, person, model)
                logger.info("无历史对话记录，创建新对话成功")
                sender.send_msg(to, "无历史对话记录，创建新对话成功")
            try:
                response = BaseChat.chat(
                    self, chat_info, message=message, message_obj=message_obj
                )
                logger.info(response)
                sender.send_msg(to, response)
            except Exception as e:
                error_message = f"调用 {model} 服务失败，错误信息：{str(e)}"
                logger.error(error_message)
                sender.send_msg(to, error_message)

    def gptx_chats(self, model: str, to: SendTo, message: str = "", message_obj=None) -> None:
        response = BaseChat.get_chat_list_str(self, to.person, model)
        sender.send_msg(to, response)

    def gptx_record(self, model: str, to: SendTo, message: str = ""):
        person = to.person
        if message == "":
            # 获取当前对话的对话记录
            chat_info = BaseChat.get_chatting_chat_info(person, model)
        else:
            # 获取指定对话的对话记录
            chat_info = BaseChat.get_chat_info(self, person, model, int(message))
        if chat_info is None:
            logger.warning("对话不存在")
            sender.send_msg(to, "对话不存在")
            return
        response = BaseChat.get_brief_conversation_str(chat_info)
        logger.info(response)
        sender.send_msg(to, response)

    def gptx_continue(self, model: str, to: SendTo, message: str = "") -> None:
        person = to.person
        # 判断message是否为数字
        if not message.isdigit():
            logger.info("请输入对话记录编号")
            sender.send_msg(to, "请输入对话记录编号")
            return
        sender.send_msg(to, f"正在切换到对话记录 {message}...")
        chat_info = BaseChat.continue_chat(
            self, person=person, model=model, chat_index=int(message)
        )
        if chat_info is None:
            warning_message = "选择历史对话失败，对话不存在"
            logger.warning(warning_message)
            sender.send_msg(to, warning_message)
            return
        response = BaseChat.get_brief_conversation_str(chat_info)
        response += "====================\n"
        response += "对话已选中，输入命令继续对话"
        logger.info(response)
        sender.send_msg(to, response)

    def create_chat(self, person: Person, model: str) -> GptChatInfo:
        """
        创建一个新的对话
        :param person: 用户
        :param model: 模型
        :return: 新的对话信息
        """
        self._save_chatting_chat_topic(person, model)
        self._set_all_chats_not_chatting(person, model)
        gpt_chat_info = GptChatInfo(
            person=person,
            model=model,
            topic=DEFAULT_TOPIC,
            is_chatting=True,
        )
        with make_db_session() as session:
            _gpt_chat_info = DbGptChatInfo.from_model(gpt_chat_info)
            session.add(_gpt_chat_info)
            session.commit()
            session.refresh(_gpt_chat_info)
            gpt_chat_info = _gpt_chat_info.to_model()
            return gpt_chat_info

    def continue_chat(self, person: Person, model: str, chat_index: int) -> Union[GptChatInfo, None]:
        """
        继续对话，选择历史对话
        :param person: 用户
        :param model: 模型
        :param chat_index: 对话记录索引（从1开始）
        :return: 对话信息
        """
        chat_info = self.get_chat_info(person, model, chat_index)
        if chat_info is None:
            return None
        chatting_chat_info = self.get_chatting_chat_info(person, model)
        if chatting_chat_info:
            if not self._is_chat_valid(chatting_chat_info):
                self._delete_chat(chatting_chat_info)
            else:
                self._save_chatting_chat_topic(person, model)
        self._set_chatting_chat(person, model, chat_info)
        return chat_info

    def _set_chatting_chat(self, person: Person, model: str, chat_info: GptChatInfo) -> None:
        """
        设置正在进行中的对话记录
        """
        self._set_all_chats_not_chatting(person, model)
        with make_db_session() as session:
            chat_info = session.query(DbGptChatInfo).filter_by(id=chat_info.id).first()
            if chat_info is None:
                logger.error("对话记录不存在")
                raise ValueError("对话记录不存在")
            chat_info.is_chatting = True
            session.commit()

    @staticmethod
    def _delete_chat(chat_info: GptChatInfo) -> None:
        """
        删除对话记录
        """
        with make_db_session() as session:
            session.query(DbGptChatMessage).filter_by(gpt_chat_id=chat_info.id).delete()
            session.query(DbGptChatInfo).filter_by(id=chat_info.id).delete()
            session.commit()

    @staticmethod
    def get_brief_conversation_str(chat_info: GptChatInfo) -> str:
        """
        获取对话记录的字符串
        :param chat_info: 对话记录
        :return: 对话记录字符串
        """
        with make_db_session() as session:
            chat_info = session.query(DbGptChatInfo).filter_by(id=chat_info.id).first()
            if chat_info is None:
                logger.error("对话记录不存在")
                raise ValueError("对话记录不存在")
            conversation_str = f"✨==={chat_info.topic}===✨\n"
            if not chat_info.gpt_chat_messages:
                conversation_str += "    无对话记录"
                return conversation_str
            for msg in chat_info.gpt_chat_messages:
                content: str = msg.message.content
                content = content.replace("\n", "")
                content = content[content.find(" ") + 1:][:30]
                response = msg.gpt_response[:30]
                response = response.replace("\n", "")
                if len(msg.message.content) > 30:
                    content += "..."
                if len(msg.gpt_response) > 30:
                    response += "..."
                conversation_str += f"💬：{content}\n"
                conversation_str += f"🤖：{response}\n"
            return conversation_str

    @staticmethod
    def _set_all_chats_not_chatting(person: Person, model: str) -> None:
        """
        将所有对话记录的 is_chatting 字段设置为 False
        """
        with make_db_session() as session:
            session.query(DbGptChatInfo).filter_by(
                person_id=person.id, model=model
            ).update({"is_chatting": False})
            session.commit()

    @staticmethod
    def _list_chat_info(person: Person, model: str) -> List:
        """
        列出用户的所有对话记录
        """
        with make_db_session() as session:
            chat_info_list = (
                session.query(DbGptChatInfo)
                .filter_by(person_id=person.id, model=model)
                .order_by(
                    DbGptChatInfo.is_chatting.desc(),
                    DbGptChatInfo.talk_time.desc(),
                )
                .limit(20)
                .all()
            )
            _chat_info_list = []
            for chat_info in chat_info_list:
                _chat_info_list.append(chat_info.to_model())
            return _chat_info_list

    def get_chat_list_str(self, person: Person, model: str) -> str:
        """
        获取用户的所有对话记录
        :param person: 用户
        :param model: 模型
        :return: 对话记录
        """
        chat_info_list = self._list_chat_info(person, model)
        chat_info_list_str = f"✨==={model}对话记录===✨\n"
        if not chat_info_list:
            chat_info_list_str += "     📭 无对话记录"
            return chat_info_list_str
        with make_db_session() as session:
            for i, chat_info in enumerate(chat_info_list):
                chat = session.query(DbGptChatInfo).filter_by(id=chat_info.id).first()
                if chat.is_chatting:
                    chat_info_list_str += f"{i + 1}. 💬{chat.topic}\n"
                else:
                    chat_info_list_str += f"{i + 1}. {chat.topic}\n"
            return chat_info_list_str

    def get_chat_info(self, person: Person, model: str, chat_index: int) -> Union[GptChatInfo, None]:
        """
        获取用户的对话信息
        :param person: 用户
        :param model: 模型
        :param chat_index: 对话记录索引（从1开始）
        :return: 对话信息
        """
        chat_info_id_list = self._list_chat_info(person, model)
        if not chat_info_id_list:
            return None
        if chat_index <= 0 or chat_index > len(chat_info_id_list):
            return None
        return chat_info_id_list[chat_index - 1]

    @staticmethod
    def get_chatting_chat_info(person: Person, model: str) -> Union[GptChatInfo, None]:
        """
        获取正在进行中的对话信息
        :param person: 用户
        :param model: 模型
        :return: 对话信息
        """
        with make_db_session() as session:
            chat_info = (
                session.query(DbGptChatInfo)
                .filter_by(person_id=person.id, model=model, is_chatting=True)
                .first()
            )
            if not chat_info:
                return None
            return chat_info.to_model()

    def chat(self, chat_info: GptChatInfo, message: str, message_obj) -> str:
        """
        持续对话
        :param chat_info: 对话信息
        :param message: 用户消息
        :param message_obj: 消息对象
        :return: GPT 回复
        """
        return self._chat(chat_info=chat_info, message=message, message_obj=message_obj, is_save=True)

    def _chat(self, chat_info: GptChatInfo, message: str, message_obj, is_save: bool) -> str:
        """
        持续对话
        :param chat_info: 对话信息
        :param message: 用户消息
        :param message_obj: 消息对象
        :param is_save: 是否保存此轮对话记录
        :return: GPT 回复
        """
        newconv = [{"role": "user", "content": message}]
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
        }
        # TODO:增加是否开启深度搜索
        #  https://www.xfyun.cn/doc/spark/HTTP%E8%B0%83%E7%94%A8%E6%96%87%E6%A1%A3.html#_3-%E8%AF%B7%E6%B1%82%E8%AF%B4%E6%98%8E
        json = {
            "model": chat_info.model,
            "messages": DEFAULT_CONVERSATION + chat_info.get_conversation() + newconv,
        }

        r_json = post_request_json(url=self.api_url, headers=headers, json=json, timeout=60)

        # if "error" in r_json or "code" in r_json:
        if "error" in r_json in r_json:
            raise ValueError(f"服务返回值错误: {r_json}")

        msg = r_json["choices"][0]["message"]
        msg_content = msg.get("content", "调用服务失败")
        if is_save:
            newconv.append({"role": "assistant", "content": msg_content})
            chat_info.extend_conversation(newconv)
            with make_db_session() as session:
                _chat_info = session.query(DbGptChatInfo).filter_by(id=chat_info.id).first()
                _chat_info.talk_time = datetime.now()
                for chat_message in chat_info.gpt_chat_messages[-len(newconv) // 2:]:
                    _chat_message = DbGptChatMessage.from_model(chat_message)
                    _chat_message.message_id = message_obj.id
                    _chat_info.gpt_chat_messages.append(_chat_message)
                session.commit()
        return msg_content

    def _save_chatting_chat_topic(self, person: Person, model: str) -> None:
        """
        生成正在进行的对话的主题
        """
        chat_info = self.get_chatting_chat_info(person, model)
        if chat_info is None or self._has_topic(chat_info):
            return
        # 生成对话主题
        if not self._is_chat_valid(chat_info):
            logger.error("对话记录长度小于1")
            return

        topic = self._generate_chat_topic(chat_info)
        if not topic:
            logger.error("生成对话主题失败")
            raise ValueError("生成对话主题失败")
        # 更新对话主题
        with make_db_session() as session:
            chat_info = session.query(DbGptChatInfo).filter_by(id=chat_info.id).first()
            chat_info.topic = topic
            session.commit()

    def _generate_chat_topic(self, chat_info: GptChatInfo) -> str:
        """
        生成对话主题，用于保存对话记录
        """
        assert self._is_chat_valid(chat_info)
        # 通过一次对话生成对话主题，但这次对话不保存到对话记录中
        prompt = "请用10个字以内总结一下这次对话的主题，不带任何标点符号"
        topic = self._chat(
            chat_info=chat_info, message=prompt, message_obj=None, is_save=False
        )
        # 限制主题长度
        if len(topic) > 21:
            topic = topic[:21] + "..."
        logger.info(f"生成对话主题：{topic}")
        return topic

    @staticmethod
    def _has_topic(chat_info: GptChatInfo) -> bool:
        """
        判断对话是否有主题
        """
        return chat_info.topic != DEFAULT_TOPIC

    @staticmethod
    def _is_chat_valid(chat_info: GptChatInfo) -> bool:
        """
        判断对话是否有效
        """
        if chat_info.gpt_chat_messages:
            return True
        return False
