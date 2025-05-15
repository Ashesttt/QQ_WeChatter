import json

import botpy
from botpy.message import DirectMessage, GroupMessage, C2CMessage
from botpy.types.message import Reference, MarkdownPayload, MessageMarkdownParams
from loguru import logger

from wechatter.bot import BotInfo
from wechatter.commands import commands, quoted_handlers
from wechatter.config import config
from wechatter.database import (
    Group as DbGroup,
    Message as DbMessage,
    Person as DbPerson,
)
from wechatter.models.wechat.group import Group
from wechatter.database import make_db_session
from wechatter.games import games
from wechatter.message import MessageHandler
from wechatter.models.wechat import Message, MessageType
from wechatter.models.wechat.person import Person, Gender

# 传入命令字典，构造消息处理器
message_handler = MessageHandler(
    commands=commands, quoted_handlers=quoted_handlers, games=games
)

class QQBot(botpy.Client):
    """QQ机器人处理类"""
    
        
    async def on_ready(self):
        """机器人就绪事件"""
        logger.info(f"机器人 {self.robot.name} 已就绪")
        # user = await self.api.me()
        BotInfo.update_name(self.robot.name)
        BotInfo.update_id(self.robot.id)
        self.qqrobot_person = Person(
            id=str(self.robot.id),
            alias=self.robot.name,
            name=self.robot.name,
            gender=Gender.unknown,
            avatar=self.robot.avatar,
            is_star=False,
            is_friend=True,
        )
        add_person(self.qqrobot_person)
        
        # 初始化qq频道私聊消息队列
        self._direct_message_queue = []
        # 初始化qq群聊消息队列
        self._group_at_message_queue = []
        # 初始化qq私聊消息队列
        self._c2c_message_queue = []
    
        # 启动消息处理任务
        import asyncio
        self._process_message_task = asyncio.create_task(self._process_message_queue())

    async def _process_message_queue(self):
        """处理所有消息队列的异步任务"""
        import asyncio

        last_group_msg_id = ""
        last_group_msg_seq = 1
        
        last_c2c_msg_id = ""
        last_c2c_msg_seq  = 1
    
        # 定义各队列的消息发送处理函数
        async def process_direct_message(msg_data):
            post_dms = ""
            content, guild_id, msg_id = msg_data
            try:
                post_dms = await self.api.post_dms(
                    content=content,
                    guild_id=guild_id,
                    msg_id=msg_id if msg_id is not None else None,
                )
                logger.debug(f"这是post_dms：\n{post_dms}")
                logger.info(f"QQ频道私信发送成功，内容：{content}，guild_id: {guild_id}，msg_id：{msg_id}")
            except Exception as e:
                logger.error(f"QQ频道私信发送失败: {str(e)}")
                
            try:    
                # 由于qq的api无法接收机器人自己的消息，所以需要手动添加
                _content = post_dms.get("content")
                _msg_id = post_dms.get("id")
                message_obj = Message(
                    type=MessageType.text,
                    person=self.qqrobot_person,
                    content=_content,
                    msg_id=_msg_id,
                )
                message_obj.id = add_message(message_obj)
                logger.info(f"qq机器人的消息已保存，id：{message_obj.id}")
            except  Exception as e:
                logger.error(f"保存qq机器人消息失败: {str(e)}")

            
        async def process_group_at_message(msg_data):
            nonlocal last_group_msg_id, last_group_msg_seq
            post_group_message = ""
            # 实现群聊@消息发送逻辑
            content, group_openid, msg_id, group = msg_data
            """
                由于post_group_message和post_c2c_message方法如果想要多次回复一条信息，需要使用msg_seq（相同的 msg_id + msg_seq 重复发送会失败），
                因此，先记录下这次的msg_id为last_group_msg_id，然后下次消息队列又来消息时，如果msg_id与last_group_msg_id相同，
                则将msg_seq+1，然后发送。
            """
            if msg_id == last_group_msg_id:
                last_group_msg_seq += 1
            else:
                last_group_msg_id = msg_id
                last_group_msg_seq = 1

            try:
                post_group_message = await self.api.post_group_message(
                    content=content,
                    group_openid=group_openid,
                    msg_id=str(last_group_msg_id),
                    msg_seq=last_group_msg_seq,
                )
                print("这是post_group_message")
                print(post_group_message)
                logger.info(f"QQ群聊@消息发送成功")
            except Exception as e:
                logger.error(f"QQ群聊@消息发送失败: {str(e)}")

            try:
                # 由于qq的api无法接收机器人自己的消息，所以需要手动添加
                _content = content
                _msg_id = post_group_message.get("id")
                message_obj = Message(
                    type=MessageType.text,
                    person=self.qqrobot_person,
                    group=group,
                    content=_content,
                    msg_id=_msg_id,
                )
                message_obj.id = add_message(message_obj)
                logger.info(f"qq机器人的消息已保存，id：{message_obj.id}")
            except  Exception as e:
                logger.error(f"保存qq机器人消息失败: {str(e)}")
    
        async def process_c2c_message(msg_data):
            nonlocal last_c2c_msg_id, last_c2c_msg_seq
            post_c2c_message = ""
            # 实现私聊消息发送逻辑
            content, user_openid, msg_id = msg_data
            if msg_id == last_c2c_msg_id:
                last_c2c_msg_seq += 1
            else:
                last_c2c_msg_id = msg_id
                last_c2c_msg_seq = 1
            
            try:
                post_c2c_message = await self.api.post_c2c_message(
                    content=content,
                    openid=user_openid,
                    msg_id=last_c2c_msg_id,
                    msg_seq=str(last_c2c_msg_seq),
                )
                print("这是post_c2c_message:")
                print(post_c2c_message)
                logger.info(f"QQ私聊消息发送成功")
            except Exception as e:
                logger.error(f"QQ私聊消息发送失败: {str(e)}")
                
            try:
                # 由于qq的api无法接收机器人自己的消息，所以需要手动添加
                _content = content
                _msg_id = post_c2c_message.get("id")
                message_obj = Message(
                    type=MessageType.text,
                    person=self.qqrobot_person,
                    content=_content,
                    msg_id=_msg_id,
                )
                message_obj.id = add_message(message_obj)
                logger.info(f"qq机器人的消息已保存，id：{message_obj.id}")
            except  Exception as e:
                logger.error(f"保存qq机器人消息失败: {str(e)}")

    
        # 消息队列与处理函数的映射
        queue_handlers = {
            '_direct_message_queue': process_direct_message,
            '_group_at_message_queue': process_group_at_message,
            '_c2c_message_queue': process_c2c_message
        }
    
        while True:
            processed_any = False
    
            # 轮询处理所有队列
            for queue_name, handler in queue_handlers.items():
                queue = getattr(self, queue_name, [])
                if queue:
                    # 获取并处理一条消息
                    msg_data = queue.pop(0)
                    await handler(msg_data)
                    processed_any = True
    
            # 如果所有队列都为空，等待一段时间再检查
            if not processed_any:
                await asyncio.sleep(1)
            else:
                # 短暂暂停避免消息发送过快
                await asyncio.sleep(0.1)

    
    async def on_direct_message_create(self, message: DirectMessage):
        """
        当收到qq频道私信消息时
        {
            'author': "{'id': '6928966086347309992', 'username': 'Ashes Awake Ascend', 'avatar': 'http://thirdqq.qlogo.cn/g?b=oidb&k=iauaXFLfXDiceMr5hiazndTXw&kti=Z8PFIQwBHsE&s=0&t=1740883233'}", 
            'content': '防守对方的', 
            'direct_message': 'True', 
            'channel_id': '76434501746857877', 
            'id': '08d3f7ccb4a59990f0121095afd2e9e398e3870138890148cae985c106', 
            'guild_id': '1360158325245950931', 
            'member': "{'joined_at': '2025-05-10T14:17:57+08:00'}", 
            'message_reference': "{'message_id': None}", 
            'attachments': '[]', 
            'seq': '137', 
            'seq_in_channel': '137', 
            'src_guild_id': '5037443047639925653', 
            'timestamp': '2025-05-12T12:10:50+08:00', 
            'event_id': 'DIRECT_MESSAGE_CREATE:08d3f7ccb4a59990f0121095afd2e9e398e3870138890148cae985c106'
        }
        """
        logger.info(f"收到私信: {message.content}")
        # 适配wechatter的消息对象
        _type = MessageType.text
        if message.attachments:
            for attachment in message.attachments:
                # 检查是否为图片
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    print(f"收到图片：{attachment.url}")
                    # 图片处理逻辑
                    _type = MessageType.file
        # 构建source
        author_dict = json.loads(json.dumps({"id": message.author.id, "username": message.author.username, "avatar": message.author.avatar}))

        # 构建source字典
        source_dict = {
            "from": {
                "id": author_dict["id"],
                "payload": {
                    "alias": "",
                    "avatar": author_dict["avatar"],
                    "city": "",
                    "friend": True,
                    "gender": 1,  # 默认为男性
                    "id": author_dict["id"],
                    "name": author_dict["username"],
                    "phone": [],
                    "province": "",
                    "star": False,
                    "type": 1
                },
                "_events": {},
                "_eventsCount": 0,
            },
            # 这是私信消息，不是群消息，所以room为空字符串
            "room": "",
            # 接收者信息(机器人)
            # 可以不用设置to，因为qq机器人无法接受自己的消息，这个to为了_receiver，而_receiver是为了转发消息，但是qq机器人不支持
            "to": {
                "id": str(self.robot.id),
                "payload": {
                    "alias": "",
                    "avatar": str(self.robot.avatar),
                    "friend": False,
                    "gender": 1,
                    "id": str(self.robot.id),
                    "name": str(self.robot.name),
                    "phone": [],
                    "signature": "",
                    "star": False,
                    "type": 1
                },
                "_events": {},
                "_eventsCount": 0,
            }
        }
        
        # 转换为JSON字符串
        source = json.dumps(source_dict)
        is_mentioned = "0"
        is_from_self = "0"
        # 解析命令
        # 构造消息对象
        message_obj = Message.from_api_direct_message(
            type=_type,
            qq_directmessage=message,
            content=message.content,
            source=source,
            is_mentioned=is_mentioned,
            is_from_self=is_from_self,
        )
        # 向用户表中添加该用户
        add_person(message_obj.person)
        # 向消息表中添加该消息
        message_obj.id = add_message(message_obj)
        # DEBUG
        print(str(message_obj))
        # 用户发来的消息均送给消息解析器处理
        message_handler.handle_message(message_obj)

    async def on_group_at_message_create(self, message: GroupMessage):
        """
        在qq群里@机器人
        {
            'author': "{'member_openid': 'A317B61B65FF0E81CD3C30F45AEBA2CC'}", 
            'group_openid': '61B585791ED672988F6F9D0FF9A917FD', 
            'content': ' /help ', 
            'id': 'ROBOT1.0_hGDa5VcOCXIqddR28QJYdp0ANUa.huWd.TJO3-lkD39V36VnnRVKWs6KiF3gTYWJkfuRSvhI7EKul46BTnltVlKTBl0bDXXBybve5OK.Tdk!', 
            'message_reference': "{'message_id': None}", 
            'mentions': '[]', 
            'attachments': '[]', 
            'msg_seq': 'None', 
            'timestamp': '2025-05-13T20:22:37+08:00', 
            'event_id': 'GROUP_AT_MESSAGE_CREATE:hgda5vcocxiqddr28qjydk1wdgg79js8xq7yjlrq8ypuv957wseidnfe0ixfc6s'
        }
        """
        logger.info(f"收到私信: {message.content}")
        # 这个方法返回的content前面多了空格，所以需要去掉
        message.content = message.content.strip()
        # 适配wechatter的消息对象
        _type = MessageType.text
        if message.attachments:
            for attachment in message.attachments:
                # 检查是否为图片
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    print(f"收到图片：{attachment.url}")
                    # 图片处理逻辑
                    _type = MessageType.file
        # 构建source
        author_dict = json.loads(json.dumps({"member_openid": message.author.member_openid}))

        # 构建source字典
        source_dict = {
            "from": {
                "id": author_dict["member_openid"],
                "payload": {
                    "alias": "",
                    "avatar": "",
                    "city": "",
                    "friend": True,
                    "gender": 1,  # 默认为男性
                    "id": author_dict["member_openid"],
                    "name": "",
                    "phone": [],
                    "province": "",
                    "star": False,
                    "type": 1
                },
                "_events": {},
                "_eventsCount": 0,
            },
            "room": {
                "id":message.group_openid,
                "topic": message.group_openid, #qq不支持查看群名，因此暂时把群名设置成群id
                "payload": {
                    "id": "",
                    "adminIdList": [],
                    "avatar": "",
                    "memberList": [],
                },
                "_events": {},
                "_eventsCount": 0,
            },
            "to": ""
        }

        # 转换为JSON字符串
        source = json.dumps(source_dict)
        is_mentioned = "1"
        is_from_self = "0"
        # 解析命令
        # 构造消息对象
        message_obj = Message.from_api_group_at_message(
            type=_type,
            qq_groupmessage=message,
            content=message.content,
            source=source,
            is_mentioned=is_mentioned,
            is_from_self=is_from_self,
        )
        # 向群组表中添加该群组
        add_group(message_obj.group)
        # 向用户表中添加该用户
        add_person(message_obj.person)
        # 向消息表中添加该消息
        message_obj.id = add_message(message_obj)
        # DEBUG
        print(str(message_obj))
        # 用户发来的消息均送给消息解析器处理
        message_handler.handle_message(message_obj)

    async def on_c2c_message_create(self, message: C2CMessage):
        """
        当机器人收到qq私信消息时
        {
            'author': "{'user_openid': 'A317B61B65FF0E81CD3C30F45AEBA2CC'}", 
            'content': '/抖音热搜 ', 
            'id': 'ROBOT1.0_u7w.ZNyE23EZYaD5FqcvXHxNjAJSuA-YK2TUwASJmatjCdcY3CkW6PVEzZeRVV17BvKef2S.vd.M.Z--CICTeA!!', 
            'message_reference': "{'message_id': None}", 
            'mentions': '[]', 
            'attachments': '[]', 
            'msg_seq': 'None', 
            'timestamp': '2025-05-14T21:29:29+08:00', 
            'event_id': 'C2C_MESSAGE_CREATE:nryysp2niqgzgqmnku6cfs7lagy819f1etougbvq3b9aj4efkw9mumbbbskblks'
        }

        """
        logger.info(f"收到私信: {message.content}")
        # 适配wechatter的消息对象
        _type = MessageType.text
        if message.attachments:
            for attachment in message.attachments:
                # 检查是否为图片
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    print(f"收到图片：{attachment.url}")
                    # 图片处理逻辑
                    _type = MessageType.file
        # 构建source
        author_dict = json.loads(json.dumps({"id": message.author.user_openid}))

        # 构建source字典
        source_dict = {
            "from": {
                "id": author_dict["id"],
                "payload": {
                    "alias": "",
                    "avatar": "",
                    "city": "",
                    "friend": True,
                    "gender": 1,  # 默认为男性
                    "id": author_dict["id"],
                    "name": author_dict["id"],
                    "phone": [],
                    "province": "",
                    "star": False,
                    "type": 1
                },
                "_events": {},
                "_eventsCount": 0,
            },
            # 这是私信消息，不是群消息，所以room为空字符串
            "room": "",
            # 接收者信息(机器人)
            # 不用设置to，因为qq机器人无法接受自己的消息
            "to": {
                "id": str(self.robot.id),
                "payload": {
                    "alias": "",
                    "avatar": str(self.robot.avatar),
                    "friend": False,
                    "gender": 1,
                    "id": str(self.robot.id),
                    "name": str(self.robot.name),
                    "phone": [],
                    "signature": "",
                    "star": False,
                    "type": 1
                },
                "_events": {},
                "_eventsCount": 0,
            }
        }

        # 转换为JSON字符串
        source = json.dumps(source_dict)
        is_mentioned = "0"
        is_from_self = "0"
        # 解析命令
        # 构造消息对象
        message_obj = Message.from_api_c2c_message(
            type=_type,
            qq_c2cmessage=message,
            content=message.content,
            source=source,
            is_mentioned=is_mentioned,
            is_from_self=is_from_self,
        )
        # 向用户表中添加该用户
        add_person(message_obj.person)
        # 向消息表中添加该消息
        message_obj.id = add_message(message_obj)
        # DEBUG
        print(str(message_obj))
        # 用户发来的消息均送给消息解析器处理
        message_handler.handle_message(message_obj)
def add_group(group: Group) -> None:
    """
    判断群组表中是否有该群组，若没有，则添加该群组
    """
    if group is None:
        return
    with make_db_session() as session:
        _group = session.query(DbGroup).filter(DbGroup.id == group.id).first()
        if _group is None:
            _group = DbGroup.from_model(group)
            session.add(_group)
            # 逐个添加群组成员，若存在则更新
            for member in group.member_list:
                _person = (
                    session.query(DbPerson).filter(DbPerson.id == member.id).first()
                )
                if _person is None:
                    _person = DbPerson.from_member_model(member)
                    session.add(_person)
                    session.commit()
                    logger.debug(f"用户 {member.name} 已添加到数据库")
                else:
                    # 更新用户信息
                    _person.name = member.name
                    _person.alias = member.alias
                    session.commit()

            session.commit()
            logger.debug(f"群组 {group.name} 已添加到数据库")
        else:
            # 更新群组信息
            _group.update(group)
            session.commit()
def add_person(person: Person) -> None:
    """
    判断用户表中是否有该用户，若没有，则添加该用户
    """
    with make_db_session() as session:
        _person = session.query(DbPerson).filter(DbPerson.id == person.id).first()
        if _person is None:
            _person = DbPerson.from_model(person)
            session.add(_person)
            session.commit()
            logger.debug(f"用户 {person.name} 已添加到数据库")
        else:
            # 更新用户信息
            _person.update(person)
            session.commit()


def add_message(message: Message) -> int:
    """
    添加消息到消息表
    """
    with make_db_session() as session:
        _message = DbMessage.from_model(message)
        session.add(_message)
        session.commit()
        logger.debug(f"消息 {_message.id} 已添加到数据库")
        return _message.id


# 创建一个全局变量存储QQBot实例
qq_bot_instance = None
def create_qq_bot():
    """创建QQ机器人实例"""
    global qq_bot_instance    
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
    qq_bot_instance = client    
    return client
