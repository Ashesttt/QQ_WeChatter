import enum
import json
import re
from functools import cached_property
from typing import Optional, Tuple

from botpy.message import DirectMessage, GroupMessage, C2CMessage
from loguru import logger
from pydantic import BaseModel, computed_field
from wechatter.models.wechat.group import Group
from wechatter.models.wechat.person import Person
from wechatter.models.wechat.quoted_response import QUOTABLE_FORMAT
from wechatter.models.wechat.url_link import UrlLink

PERSON_FORWARDING_MESSAGE_FORMAT = "⤴️ [%s] 说：\n" "-------------------------\n"
GROUP_FORWARDING_MESSAGE_FORMAT = "⤴️ [%s] 在 [%s] 说：\n" "-------------------------\n"


class MessageType(enum.Enum):
    """
    消息类型枚举类
    """

    text = "text"
    file = "file"
    urlLink = "urlLink"
    friendship = "friendship"
    system_event_login = "system_event_login"
    system_event_logout = "system_event_logout"
    system_event_error = "system_event_error"
    system_event_push_notify = "system_event_push_notify"
    unknown = "unknown"


class MessageSenderType(enum.Enum):
    """
    消息来源枚举
    """

    PERSON = 0
    GROUP = 1


class Message(BaseModel):
    """
    微信消息类（消息接收）
    """
    model_config = {
        "arbitrary_types_allowed": True
    }
    type: MessageType
    person: Person
    group: Optional[Group] = None
    receiver: Optional[Person] = None
    content: str
    is_mentioned: bool = False
    is_from_self: bool = False
    id: Optional[int] = None
    qq_directmessage: DirectMessage = None
    qq_groupmessage: GroupMessage = None
    qq_c2cmessage:  C2CMessage = None
    msg_id: Optional[str] = None
    attachments: Optional[list] = None

    @classmethod
    def from_api_direct_message(
            cls,
            type: MessageType,
            qq_directmessage: DirectMessage,
            content: str,
            source: str,
            is_mentioned: str,
            is_from_self: str = 0,
            attachments: Optional[list] = None
    ):
        """
        从API接口创建消息对象
        :param type: 消息类型
        :param qq_directmessage: qq的DirectMessage
        :param content: 消息内容
        :param source: 消息来源
        :param is_mentioned: 是否@机器人
        :param is_from_self: 是否是自己发送的消息
        :param attachments: 消息附件列表
        :return: 消息对象
        """
        try:
            source_json = json.loads(source)
        except json.JSONDecodeError as e:
            logger.error("消息来源解析失败")
            raise e

        # from为发送者信息，无论是个人消息还是群消息，都有from
        payload = source_json.get("from").get("payload", {})
        gender = int(payload.get("gender", -1))
        g = "unknown"
        if gender == 1:
            g = "male"
        elif gender == 0:
            g = "female"
        # 判断 id 长度：个人用户为65位，公众号为33位（包括@符号）
        name = payload.get("name", "")
        # 暂时通过名字判断是否为央视新闻公众号
        is_official_account = len(payload.get("id", "")) == 33
        if name == "央视新闻":
            is_official_account = True
            
        # 频道私信guild_id
        guild_id = ""
        if qq_directmessage.guild_id != "":
            guild_id = qq_directmessage.guild_id
        
        # 信息id
        msg_id = ""
        if qq_directmessage.id != "":
            msg_id = qq_directmessage.id
        
        
        _person = Person(
            id=payload.get("id", ""),
            name=name,
            alias=payload.get("alias", ""),
            gender=g,
            signature=payload.get("signature", ""),
            province=payload.get("province", ""),
            city=payload.get("city", ""),
            # phone_list=payload.get("phone", []),
            is_star=payload.get("star", False),
            is_friend=payload.get("friend", False),
            is_official_account=is_official_account,
            guild_id=guild_id,
            msg_id=msg_id
        )

        _group = None
        # room为群信息，只有群消息才有room
        if source_json["room"] != '':
            if "room" in source_json and isinstance(source_json["room"], dict):
                g_data = source_json["room"]
                payload = g_data.get("payload", {})
                _group = Group(
                    id=g_data.get("id", ""),
                    name=payload.get("topic", ""),
                    admin_id_list=payload.get("adminIdList", []),
                    member_list=payload.get("memberList", []),
                )
            else:
                logger.error("source_json[room]: " + str(source_json["room"]))
        # else:
        #     logger.warning("source_json[room]是空的，不是群信息")

        _receiver = None
        if source_json.get("to"):
            to_payload = source_json.get("to").get("payload", {})
            _receiver = Person(
                id=to_payload.get("id", ""),
                name=to_payload.get("name", ""),
                alias=to_payload.get("alias", ""),
                gender="unknown",
                is_star=to_payload.get("star", False),
                is_friend=to_payload.get("friend", False),
            )

        _content = content.lstrip()
        _is_mentioned = False
        if is_mentioned == "1":
            _is_mentioned = True
        _is_from_self = False
        if is_from_self == "1":
            _is_from_self = True
        return cls(
            type=type,
            person=_person,
            group=_group,
            receiver=_receiver,
            content=_content,
            is_mentioned=_is_mentioned,
            is_from_self=_is_from_self,
            qq_directmessage=qq_directmessage,
            msg_id=msg_id,
            attachments=attachments,
        )

    @classmethod
    def from_api_group_at_message(
            cls,
            type: MessageType,
            qq_groupmessage: GroupMessage,
            content: str,
            source: str,
            is_mentioned: str,
            is_from_self: str = 0,
            attachments: Optional[list] = None
    ):
        """
        从API接口创建消息对象
        :param type: 消息类型
        :param qq_groupmessage: qq的GroupMessage
        :param content: 消息内容
        :param source: 消息来源
        :param is_mentioned: 是否@机器人
        :param is_from_self: 是否是自己发送的消息
        :param attachments: 消息附件列表
        :return: 消息对象
        """
        try:
            source_json = json.loads(source)
        except json.JSONDecodeError as e:
            logger.error("消息来源解析失败")
            raise e

        # from为发送者信息，无论是个人消息还是群消息，都有from
        payload = source_json.get("from").get("payload", {})
        gender = int(payload.get("gender", -1))
        g = "unknown"
        if gender == 1:
            g = "male"
        elif gender == 0:
            g = "female"
        # 判断 id 长度：个人用户为65位，公众号为33位（包括@符号）
        name = payload.get("name", "")
        # 暂时通过名字判断是否为央视新闻公众号
        is_official_account = len(payload.get("id", "")) == 33
        if name == "央视新闻":
            is_official_account = True

        #获取发送人的member_openid
        member_openid = ""
        if qq_groupmessage.author.member_openid != "":
            member_openid = qq_groupmessage.author.member_openid
        
        # 要回复的消息id msg_id
        msg_id = ""
        if qq_groupmessage.id != "":
            msg_id = qq_groupmessage.id

        _person = Person(
            id=payload.get("id", ""),
            name=name,
            alias=payload.get("alias", ""),
            gender=g,
            signature=payload.get("signature", ""),
            province=payload.get("province", ""),
            city=payload.get("city", ""),
            # phone_list=payload.get("phone", []),
            is_star=payload.get("star", False),
            is_friend=payload.get("friend", False),
            is_official_account=is_official_account,
            msg_id=msg_id,
            member_openid=member_openid
        )

        _group = None
        # room为群信息，只有群消息才有room
        if source_json["room"] != '':
            if "room" in source_json and isinstance(source_json["room"], dict):
                g_data = source_json["room"]
                payload = g_data.get("payload", {})
                _group = Group(
                    id=g_data.get("id", ""),
                    name=g_data.get("topic", ""),
                    admin_id_list=payload.get("adminIdList", []),
                    member_list=payload.get("memberList", []),
                    msg_id=msg_id
                )
            else:
                logger.error("source_json[room]: " + str(source_json["room"]))

        _receiver = None
        if source_json.get("to"):
            to_payload = source_json.get("to").get("payload", {})
            _receiver = Person(
                id=to_payload.get("id", ""),
                name=to_payload.get("name", ""),
                alias=to_payload.get("alias", ""),
                gender="unknown",
                is_star=to_payload.get("star", False),
                is_friend=to_payload.get("friend", False),
            )

        _content = content.lstrip()
        _is_mentioned = False
        if is_mentioned == "1":
            _is_mentioned = True
        _is_from_self = False
        if is_from_self == "1":
            _is_from_self = True
        return cls(
            type=type,
            person=_person,
            group=_group,
            receiver=_receiver,
            content=_content,
            is_mentioned=_is_mentioned,
            is_from_self=_is_from_self,
            qq_groupmessage=qq_groupmessage,
            attachments=attachments,
        )
    @classmethod
    def from_api_c2c_message(
            cls,
            type: MessageType,
            qq_c2cmessage: C2CMessage,
            content: str,
            source: str,
            is_mentioned: str,
            is_from_self: str = 0,
            attachments: Optional[list] = None
    ):
        """
        从API接口创建消息对象
        :param type: 消息类型
        :param qq_c2cmessage: qq的C2CMessage
        :param content: 消息内容
        :param source: 消息来源
        :param is_mentioned: 是否@机器人
        :param is_from_self: 是否是自己发送的消息
        :param attachments: 消息附件列表
        :return: 消息对象
        """
        try:
            source_json = json.loads(source)
        except json.JSONDecodeError as e:
            logger.error("消息来源解析失败")
            raise e

        # from为发送者信息，无论是个人消息还是群消息，都有from
        payload = source_json.get("from").get("payload", {})
        gender = int(payload.get("gender", -1))
        g = "unknown"
        if gender == 1:
            g = "male"
        elif gender == 0:
            g = "female"
        # 判断 id 长度：个人用户为65位，公众号为33位（包括@符号）
        name = payload.get("name", "")
        # 暂时通过名字判断是否为央视新闻公众号
        is_official_account = len(payload.get("id", "")) == 33
        if name == "央视新闻":
            is_official_account = True

        #获取发送人的user_openid
        user_openid = ""
        if qq_c2cmessage.author.user_openid != "":
            user_openid = qq_c2cmessage.author.user_openid

        # 要回复的消息id msg_id
        msg_id = ""
        if qq_c2cmessage.id != "":
            msg_id = qq_c2cmessage.id

        _person = Person(
            id=payload.get("id", ""),
            name=name,
            alias=payload.get("alias", ""),
            gender=g,
            signature=payload.get("signature", ""),
            province=payload.get("province", ""),
            city=payload.get("city", ""),
            # phone_list=payload.get("phone", []),
            is_star=payload.get("star", False),
            is_friend=payload.get("friend", False),
            is_official_account=is_official_account,
            msg_id=msg_id,
            user_openid=user_openid
        )

        _group = None
        # room为群信息，只有群消息才有room
        if source_json["room"] != '':
            if "room" in source_json and isinstance(source_json["room"], dict):
                g_data = source_json["room"]
                payload = g_data.get("payload", {})
                _group = Group(
                    id=g_data.get("id", ""),
                    name=g_data.get("topic", ""),
                    admin_id_list=payload.get("adminIdList", []),
                    member_list=payload.get("memberList", []),
                    msg_id=msg_id
                )
            else:
                logger.error("source_json[room]: " + str(source_json["room"]))

        _receiver = None
        if source_json.get("to"):
            to_payload = source_json.get("to").get("payload", {})
            _receiver = Person(
                id=to_payload.get("id", ""),
                name=to_payload.get("name", ""),
                alias=to_payload.get("alias", ""),
                gender="unknown",
                is_star=to_payload.get("star", False),
                is_friend=to_payload.get("friend", False),
            )

        _content = content.lstrip()
        _is_mentioned = False
        if is_mentioned == "1":
            _is_mentioned = True
        _is_from_self = False
        if is_from_self == "1":
            _is_from_self = True
        return cls(
            type=type,
            person=_person,
            group=_group,
            receiver=_receiver,
            content=_content,
            is_mentioned=_is_mentioned,
            is_from_self=_is_from_self,
            qq_c2cmessage=qq_c2cmessage,
            attachments=attachments,
        )
    @classmethod
    def from_api_msg(
        cls,
        type: MessageType,
        content: str,
        source: str,
        is_mentioned: str,
        is_from_self: str = 0,
    ):
        """
        从API接口创建消息对象
        :param type: 消息类型
        :param content: 消息内容
        :param source: 消息来源
        :param is_mentioned: 是否@机器人
        :param is_from_self: 是否是自己发送的消息
        :return: 消息对象
        """
        try:
            source_json = json.loads(source)
        except json.JSONDecodeError as e:
            logger.error("消息来源解析失败")
            raise e

        # from为发送者信息，无论是个人消息还是群消息，都有from
        payload = source_json.get("from").get("payload", {})
        gender = int(payload.get("gender", -1))
        g = "unknown"
        if gender == 1:
            g = "male"
        elif gender == 0:
            g = "female"
        # 判断 id 长度：个人用户为65位，公众号为33位（包括@符号）
        name = payload.get("name", "")
        # 暂时通过名字判断是否为央视新闻公众号
        is_official_account = len(payload.get("id", "")) == 33
        if name == "央视新闻":
            is_official_account = True
        _person = Person(
            id=payload.get("id", ""),
            name=name,
            alias=payload.get("alias", ""),
            gender=g,
            signature=payload.get("signature", ""),
            province=payload.get("province", ""),
            city=payload.get("city", ""),
            # phone_list=payload.get("phone", []),
            is_star=payload.get("star", False),
            is_friend=payload.get("friend", False),
            is_official_account=is_official_account,
        )

        _group = None
        # room为群信息，只有群消息才有room
        if source_json["room"] != '':
            if "room" in source_json and isinstance(source_json["room"], dict):
                g_data = source_json["room"]
                payload = g_data.get("payload", {})
                _group = Group(
                    id=g_data.get("id", ""),
                    name=payload.get("topic", ""),
                    admin_id_list=payload.get("adminIdList", []),
                    member_list=payload.get("memberList", []),
                )
            else:
                logger.error("source_json[room]: " + str(source_json["room"]))
        # else:
        #     logger.warning("source_json[room]是空的，不是群信息")

        _receiver = None
        if source_json.get("to"):
            to_payload = source_json.get("to").get("payload", {})
            _receiver = Person(
                id=to_payload.get("id", ""),
                name=to_payload.get("name", ""),
                alias=to_payload.get("alias", ""),
                gender="unknown",
                is_star=to_payload.get("star", False),
                is_friend=to_payload.get("friend", False),
            )

        _content = content.replace("\u2005", " ", 1)
        _is_mentioned = False
        if is_mentioned == "1":
            _is_mentioned = True
        _is_from_self = False
        if is_from_self == "1":
            _is_from_self = True
        return cls(
            type=type,
            person=_person,
            group=_group,
            receiver=_receiver,
            content=_content,
            is_mentioned=_is_mentioned,
            is_from_self=_is_from_self,
        )

    @computed_field
    @property
    def is_group(self) -> bool:
        """
        是否是群消息
        :return: 是否是群消息
        """
        return self.group is not None and self.group.id != ''
    @computed_field
    @cached_property
    def is_quoted(self) -> bool:
        """
        是否引用机器人消息
        :return: 是否引用机器人消息
        """
        # 如果是qq频道私信 用户引用了机器人信息
        if self.qq_directmessage is not None:
            if self.qq_directmessage.message_reference.message_id is not None:
                return True
        elif self.qq_groupmessage is not None:
            # TODO：qq群里无法接收到引用消息qq_groupmessage.message_reference，无论引不引用，qq_groupmessage.message_reference.id都是None
            if self.qq_groupmessage.message_reference.message_id is not None:
                return True
        else:
            return False
        
        # # 引用消息的正则
        # quote_pattern = r"(?s)「(.*?)」\n- - - - - - - - - - - - - - -"
        # match_result = re.match(quote_pattern, self.content)
        # # 判断是否为引用机器人消息
        # if match_result and self.content.startswith(f"「{BotInfo.name}"):
        #     return True
        # return False

    # TODO: 判断所有的引用消息，不仅仅是机器人消息
    #  待解决：在群中如果有人设置了自己的群中名称，那么引用内容的名字会变化，导致无法匹配到用户

    @computed_field
    @property
    def sender_name(self) -> str:
        """
        返回消息发送对象名，如果是群则返回群名，如果不是则返回人名
        :return: 消息发送对象名
        """
        return self.group.name if self.is_group else self.person.name

    @computed_field
    @cached_property
    def quotable_id(self) -> Optional[str]:
        """
        获取引用消息的id
        :return: 引用消息的id
        """
        if self.is_quoted:
            if self.qq_directmessage is not None:
                if self.qq_directmessage.message_reference.message_id is not None:
                    #需要被引用的消息的id是message_id
                    message_id = self.qq_directmessage.message_reference.message_id
                    #通过这个message_id来获取message表里面的message.content
                    from wechatter.database.tables.message import Message as DbMessage
                    from wechatter.database import make_db_session
                    with make_db_session() as session:
                        quotable_message = session.query(DbMessage).filter(DbMessage.msg_id == message_id).first()
                        if quotable_message is not None:
                            quotable_id = from_content_get_quotable_id(quotable_message.content)
                            return quotable_id

        elif self.qq_groupmessage is not None:
            if self.qq_groupmessage.message_reference.message_id is not None:
                pass
    

    @computed_field
    @cached_property
    def pure_content(self) -> str:
        """
        获取不带引用的消息内容，即用户真实发送的消息
        :return: 不带引用的消息内容
        """
        if self.is_quoted:
            pattern = "「[\s\S]+」\n- - - - - - - - - - - - - - -\n([\s\S]*)"
            return re.search(pattern, self.content).group(1)
        else:
            return self.content

    @computed_field
    @cached_property
    def forwarded_source_name(self) -> Optional[Tuple[str, bool]]:
        """
        获取转发消息的来源的名字
        :return: 消息来源的名字和是否为群的元组(source_name, is_group)
        """
        if self.is_quoted:
            # 先尝试匹配群消息
            group_format = GROUP_FORWARDING_MESSAGE_FORMAT.replace("[", "\[").replace(
                "]", "\]"
            )
            pattern = re.compile(f'{group_format % ("(.*)", "(.+)")}')
            try:
                # 将名字和该名字是否为群都返回，便于在回复时判断
                return re.search(pattern, self.content).group(2), True
            except AttributeError:
                pass
            # 再尝试匹配个人消息
            person_format = PERSON_FORWARDING_MESSAGE_FORMAT.replace("[", "\[").replace(
                "]", "\]"
            )
            pattern = re.compile(f'{person_format % "(.+)"}')
            try:
                return re.search(pattern, self.content).group(1), False
            except AttributeError:
                return None
        else:
            return None

    @computed_field
    @cached_property
    def is_official_account(self) -> bool:
        """
        是否是公众号消息
        :return: 是否是公众号消息
        """
        return self.person.is_official_account

    @computed_field
    @cached_property
    def urllink(self) -> Optional[UrlLink]:
        """
        当消息类型为urlLink时，返回url link的解析结果
        :return: url link的解析结果
        """
        if self.type == MessageType.urlLink:
            url_link_json = json.loads(self.content)
            return UrlLink(
                title=url_link_json.get("title"),
                desc=url_link_json.get("description"),
                url=url_link_json.get("url"),
                cover_url=url_link_json.get("thumbnailUrl"),
            )
        return None

    @computed_field
    @cached_property
    def is_tickled(self) -> bool:
        """
        是否为拍一拍消息
        :return: 是否为拍一拍消息
        """
        # 消息类型为 unknown 且 content 为 "某人" 拍了拍我
        return self.type == MessageType.unknown and (
            "拍了拍我" in self.content or "我拍了拍自己" in self.content
        )

    @computed_field
    @cached_property
    def is_sticky(self) -> bool:
        """
        是否为表情包消息
        :return: 是否为表情包消息
        """
        # 表情包消息类型为 unknown，内容为 XML 格式，具体格式为 <msg><emoji.*></emoji></msg>
        return self.type == MessageType.unknown and self.content.startswith(
            "<msg><emoji"
        )

    @computed_field
    @cached_property
    def sticky_url(self) -> Optional[str]:
        """
        获取表情包的URL
        :return: 表情包的URL
        """
        if self.is_sticky:
            # 使用 spilt，比正则效率高
            url = self.content.split('cdnurl="')[1].split('" designerid')[0]
            # 将 URL 中的 &amp; 替换为 &
            # 带上别名参数，使得表情包为原图
            return f'{url.replace("&amp;amp;", "&")}?$alias=sticky.jpg'
        return None

    # def __str__(self) -> str:
    #     #     source = self.person
    #     #     if self.is_group:
    #     #         source = self.group
    #     #     return (
    #     #         f"消息内容：{self.content}\n"
    #     #         f"消息来源：{source}\n"
    #     #         f"是否@：{self.is_mentioned}\n"
    #     #         f"是否引用：{self.is_quoted}"
    #     #     )
    def __str__(self) -> str:
        source = self.person
        if self.is_group:
            source = self.group
        return (
            "这是message对象\n"
            f"type(类型):{self.type}\n"
            f"person:{self.person}\n"
            f"group:{self.group}\n"
            f"source(消息来源):{source}\n"
            f"receiver(接收者):{self.receiver}\n"
            # f"content(消息内容):{self.content}\n"
            f"是否@:{self.is_mentioned}\n"
            f"是否引用:{self.is_quoted}\n"
            # f"id:{self.id}\n"
            f"qq_directmessage:{self.qq_directmessage}\n"
            f"qq_groupmessage:{self.qq_groupmessage}\n"
            f"qq_c2cmessage:{self.qq_c2cmessage}"
        )
def from_content_get_quotable_id(content):
    # pattern = f'^「[^「]+{QUOTABLE_FORMAT % "(.{3})"}'
    pattern = f'{QUOTABLE_FORMAT % "(.{3})"}'
    try:
        return re.search(pattern, content).group(1)
    except AttributeError:
        return None
