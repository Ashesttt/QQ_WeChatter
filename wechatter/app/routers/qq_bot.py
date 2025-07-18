import json
import os
import re

import botpy
from botpy.message import DirectMessage, GroupMessage, C2CMessage
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
from wechatter.sender import notifier
from wechatter.utils.time import get_current_timestamp, get_current_datetime2

# 传入命令字典，构造消息处理器
message_handler = MessageHandler(
    commands=commands, quoted_handlers=quoted_handlers, games=games
)

class QQBot(botpy.Client):
    """QQ机器人处理类"""
    
        
    async def on_ready(self):
        """机器人就绪事件"""
        logger.success(f"机器人 {self.robot.name} 已就绪")
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
        # 初始化阻塞队列
        self._blocking_group_queue = []
        self._blocking_c2c_queue = []
        # 启动消息处理任务
        import asyncio
        self._process_message_task = asyncio.create_task(self._process_message_queue())
        # 启动阻塞队列定期检查任务
        self._check_blocking_queue_task = asyncio.create_task(self._check_blocking_queues())
        notifier.notify_logged_in()

    async def _process_message_queue(self):
        """处理所有消息队列的异步任务"""
        import asyncio
        from collections import OrderedDict
        from time import time

        class MessageSeqManager:
            def __init__(self, expiry_time=300):
                self.msg_seq_map = OrderedDict()  # 使用OrderedDict来维护插入顺序
                self.msg_time_map = {}  # 记录每个msg_id的最后使用时间
                self.expiry_time = expiry_time
                self.last_cleanup_time = time()
                self.cleanup_interval = 60  # 每60秒检查一次过期消息

            def get_seq(self, msg_id):
                current_time = time()
                # 检查是否需要清理过期消息
                if current_time - self.last_cleanup_time > self.cleanup_interval:
                    self._cleanup_expired()
                    self.last_cleanup_time = current_time

                # 如果msg_id不存在，初始化为1
                if msg_id not in self.msg_seq_map:
                    self.msg_seq_map[msg_id] = 1
                    self.msg_time_map[msg_id] = current_time
                    return 1

                # 更新最后使用时间
                self.msg_time_map[msg_id] = current_time
                # 获取并递增seq
                seq = self.msg_seq_map[msg_id] + 1
                self.msg_seq_map[msg_id] = seq
                return seq

            def _cleanup_expired(self):
                current_time = time()
                # 创建需要删除的msg_id列表
                expired_ids = [
                    msg_id for msg_id, last_time in self.msg_time_map.items()
                    if current_time - last_time > self.expiry_time
                ]
                # 删除过期的msg_id
                for msg_id in expired_ids:
                    del self.msg_seq_map[msg_id]
                    del self.msg_time_map[msg_id]

            def get_current_state(self):
                return {
                    'msg_seq_map': dict(self.msg_seq_map),
                    'msg_time_map': self.msg_time_map
                }

        # 创建消息序列管理器实例
        seq_manager = MessageSeqManager(expiry_time=300)  # 5分钟过期
        last_group_msg_id = ""
        last_group_msg_time = 0
        
        last_c2c_msg_id = ""
        last_c2c_msg_time = 0

        async def process_direct_message(msg_data):
            post_dms = ""
            # 参数兼容处理
            if len(msg_data) == 4:
                content, guild_id, msg_id, is_image = msg_data
                retry_count = 0
            else:
                content, guild_id, msg_id, is_image, retry_count = msg_data
            try:
                params = {
                    "content": content,
                    "guild_id": guild_id,
                }
                if msg_id is not None:
                    params["msg_id"] = msg_id
                # 当要发送的信息是图片的时候，content就是图片路径
                if is_image is True:
                    params["image"] = content
                    params["content"] = ""
                post_dms = await self.api.post_dms(**params)
                # # 避免磁盘空间浪费，但没必要
                # if is_image is True and os.path.exists(content):
                #     os.remove(content)
                logger.debug(f"这是post_dms：\n{post_dms}")
                logger.success(f"QQ频道私信发送成功，内容：{content}，guild_id: {guild_id}，msg_id：{msg_id}，是否为图片：{is_image}。")
            except Exception as e:
                logger.error(f"QQ频道私信发送失败: {str(e)}")
                # 加入消息队列说发送失败
                failed_content = f"\n❗️ 错误：消息发送失败：{desensitize_message(str(e))}"
                retry_count += 1
                MAX_RETRY = 3
                if retry_count <= MAX_RETRY:
                    # 重新加入队列，带上重试次数
                    self._direct_message_queue.append((failed_content, guild_id, msg_id, is_image, retry_count))
                    logger.warning(f"QQ频道私信发送失败，已重试{retry_count}次，将再次尝试。")
                else:
                    logger.error(f"QQ频道私信发送失败，重试已达上限({MAX_RETRY})，不再重试。内容：{failed_content}")
                
            try:    
                # 主动发送返回的post_dms:to_A:{'code': 304023, 'message': '消息提交安全审核成功', 'data': {'message_audit': {'audit_id': 'a542254e-7390-4ec0-81a9-9b03e5df41e5'}}, 'err_code': 40034120, 'trace_id': '490b134028f32983479ee42ccc7d1424'}
                # 由于qq的api无法接收机器人自己的消息，所以需要手动添加
                _msg_id = post_dms.get("id")
                message_obj = Message(
                    type=MessageType.text,
                    person=self.qqrobot_person,
                    content=content,
                    msg_id=_msg_id,
                )
                message_obj.id = add_message(message_obj)
                logger.debug(f"qq机器人的消息已保存，id：{message_obj.id}")
            except  Exception as e:
                logger.error(f"保存qq机器人消息失败: {str(e)}")

            
        async def process_group_at_message(msg_data):
            nonlocal last_group_msg_id, last_group_msg_time
            post_group_message = ""
            # 参数兼容处理
            if len(msg_data) == 5:
                content, group_openid, msg_id, group, is_image = msg_data
                retry_count = 0
            else:
                content, group_openid, msg_id, group, is_image, retry_count = msg_data
                
            # 获取当前时间戳
            _current_time = get_current_timestamp()
            
            # 如果收到新消息(msg_id不为None)，而且msg_id与上次的msg_id不同，则发送消息
            if msg_id is not None and msg_id != last_group_msg_id:
                last_group_msg_id = msg_id
                last_group_msg_time = _current_time
                # 获取新的seq
                msg_seq = seq_manager.get_seq(msg_id)
            # 如果msg_id为空，代表这个消息任务是主动发送的
            elif last_group_msg_id and (_current_time - last_group_msg_time < 300):
                # 获取当前msg_id的seq
                msg_seq = seq_manager.get_seq(last_group_msg_id)
                if msg_seq > 5:
                    current_time = get_current_datetime2()
                    modified_content = f"{content}\n\n⚠️ 注意：此消息非实时发送，实际发生的时间为：\n⌚️ {current_time}"
                    qq_bot_instance._blocking_group_queue.append((modified_content, group_openid, msg_id, group, is_image))
                    logger.warning(f"msg_seq已达到上限(5)，添加到阻塞消息队列(_blocking_group_queue)，信息是：{modified_content}，group_openid：{group_openid}，msg_id：{msg_id}，group：{group}，是否为图片：{is_image}。")
                    return f"信息已加入阻塞队列，请耐心等待发送完成，需要群里有新消息才能激活发送。"
                
                msg_id = last_group_msg_id
            else:
                current_time = get_current_datetime2()
                modified_content = f"{content}\n\n⚠️ 注意：此消息非实时发送，实际发生的时间为：\n⌚️ {current_time}"
                qq_bot_instance._blocking_group_queue.append((modified_content, group_openid, msg_id, group, is_image))
                logger.warning(f"QQ消息已加入阻塞消息队列(_blocking_group_queue)，信息是：{modified_content}，group_openid：{group_openid}，msg_id：{msg_id}，group：{group}，是否为图片：{is_image}。")
                logger.critical(f"这是msg_seq_map状态:{seq_manager.get_current_state()}")
                return f"信息已加入阻塞队列，请耐心等待发送完成，需要群里@机器人，或者私聊机器人，即可发送。"

            try:
                params = {
                    "group_openid": group_openid,
                    "msg_id": str(last_group_msg_id),
                    "msg_seq": msg_seq
                }
                if is_image is True:
                    uploadMedia = await self.api.post_group_file(
                        group_openid=group_openid,
                        file_type=1, # 文件类型要对应上，具体支持的类型见方法说明
                        url=content # 文件Url
                    )
                    logger.debug(f"这是图片上传结果uploadMedia：{uploadMedia}")
                    params["media"] = uploadMedia
                    params["msg_type"] = 7
                else:
                    params["content"] = content
                    
                    
                post_group_message = await self.api.post_group_message(**params)
                logger.debug(f"这是post_group_message：\n{post_group_message}")
                logger.success(f"QQ群聊@消息发送成功")
            except Exception as e:
                logger.error(f"QQ群聊@消息发送失败: {str(e)}")
                failed_content = f"\n❗️ 错误：消息发送失败：{desensitize_message(str(e))}"
                retry_count += 1
                MAX_RETRY = 3
                if retry_count <= MAX_RETRY:
                    self._group_at_message_queue.append((failed_content, group_openid, msg_id, group, is_image, retry_count))
                    logger.warning(f"QQ群聊@消息发送失败，已重试{retry_count}次，将再次尝试。")
                else:
                    logger.error(f"QQ群聊@消息发送失败，重试已达上限({MAX_RETRY})，不再重试。内容：{failed_content}")

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
                logger.debug(f"qq机器人的消息已保存，id：{message_obj.id}")
            except  Exception as e:
                logger.error(f"保存qq机器人消息失败: {str(e)}")

        async def process_c2c_message(msg_data):
            nonlocal last_c2c_msg_id, last_c2c_msg_time
            post_c2c_message = ""
            # 实现私聊消息发送逻辑
            # 参数兼容处理
            if len(msg_data) == 4:
                content, user_openid, msg_id, is_image = msg_data
                retry_count = 0
            else:
                content, user_openid, msg_id, is_image, retry_count = msg_data        
            # 获取当前时间戳
            _current_time = get_current_timestamp()
            # 如果收到新消息(msg_id不为None)，而且msg_id与上次的msg_id不同，则发送消息，更新最后消息ID和时间
            if msg_id is not None and msg_id != last_c2c_msg_id:
                last_c2c_msg_id = msg_id
                last_c2c_msg_time = _current_time
                # 为新msg_id初始化msg_seq
                msg_seq = seq_manager.get_seq(msg_id)
            # 如果msg_id为空，代表这个消息任务是主动发送的，检查上一条消息ID是否在有效期内
            elif last_c2c_msg_id and (_current_time - last_c2c_msg_time < 300):
                if seq_manager.get_seq(last_c2c_msg_id) >= 5:
                    current_time = get_current_datetime2()
                    modified_content = f"{content}\n\n⚠️ 注意：此消息非实时发送，实际发生的时间为：\n⌚️ {current_time}"
                    qq_bot_instance._blocking_c2c_queue.append((modified_content, user_openid, msg_id, is_image))
                    logger.warning(f"msg_seq已达到上限(5)，添加到阻塞消息队列(_blocking_c2c_queue)，信息是：{modified_content}，user_openid：{user_openid}，msg_id：{msg_id}，是否为图片：{is_image}。")
                    return f"信息已加入阻塞队列，请耐心等待发送完成，需要有新消息才能激活发送。"
                msg_id = last_c2c_msg_id
                # 获取并递增当前msg_id对应的msg_seq
                msg_seq = seq_manager.get_seq(msg_id)
            # 如果上一条消息ID没有或已过期，将消息添加到阻塞队列
            else:
                current_time = get_current_datetime2()
                modified_content = f"{content}\n\n⚠️ 注意：此消息非实时发送，实际发生的时间为：\n⌚️ {current_time}"
                qq_bot_instance._blocking_c2c_queue.append((modified_content, user_openid, msg_id, is_image))
                logger.warning(f"QQ消息已加入阻塞消息队列(_blocking_c2c_queue)，信息是：{modified_content}，user_openid：{user_openid}，msg_id：{msg_id}，是否为图片：{is_image}。")
                return f"信息已加入阻塞队列，请耐心等待发送完成，需要私聊机器人，即可发送。"
        
            try:
                params = {
                    "openid": user_openid,
                    "msg_id": str(last_c2c_msg_id),
                    "msg_seq": msg_seq
                }
                if is_image is True:
                    uploadMedia = await self.api.post_c2c_file(
                        openid=user_openid,
                        file_type=1, # 文件类型要对应上，具体支持的类型见方法说明
                        url=content # 文件Url
                    )
                    logger.debug(f"这是图片上传结果uploadMedia：{uploadMedia}")
                    params["media"] = uploadMedia
                    params["msg_type"] = 7
                else:
                    params["content"] = content
        
                post_c2c_message = await self.api.post_c2c_message(**params)
                logger.debug(f"这是post_c2c_message：\n{post_c2c_message}")
                logger.success(f"QQ私聊消息发送成功，内容：{content}，user_openid：{user_openid}，msg_id：{msg_id}，是否为图片：{is_image}。")
            except Exception as e:
                logger.error(f"QQ私聊消息发送失败: {str(e)}")
                failed_content = f"\n❗️ 错误：消息发送失败：{desensitize_message(str(e))}"
                retry_count += 1
                MAX_RETRY = 3
                if retry_count <= MAX_RETRY:
                    self._c2c_message_queue.append((failed_content, user_openid, msg_id, is_image, retry_count))
                    logger.warning(f"QQ私聊消息发送失败，已重试{retry_count}次，将再次尝试。")
                else:
                    logger.error(f"QQ私聊消息发送失败，重试已达上限({MAX_RETRY})，不再重试。内容：{failed_content}")
        
            try:
                # 由于qq的api无法接收机器人自己的消息，所以需要手动添加
                _msg_id = post_c2c_message.get("id")
                message_obj = Message(
                    type=MessageType.text,
                    person=self.qqrobot_person,
                    content=content,
                    msg_id=_msg_id,
                )
                message_obj.id = add_message(message_obj)
                logger.debug(f"qq机器人的消息已保存，id：{message_obj.id}")
            except Exception as e:
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
                    logger.warning(f"正在处理队列任务：{queue_name}:\n{queue}")
                    msg_data = queue.pop(0)
                    await handler(msg_data)
                    processed_any = True
                    logger.success(f"处理完成队列任务：{queue_name}:\n{queue}")
    
            # 如果所有队列都为空，等待一段时间再检查
            if not processed_any:
                await asyncio.sleep(1)
            else:
                # 短暂暂停避免消息发送过快
                await asyncio.sleep(0.1)

    async def _check_blocking_queues(self):
        """定期检查阻塞队列，尝试处理其中的消息"""
        import asyncio
    
        # 每隔多少秒检查一次阻塞队列
        CHECK_INTERVAL = 180  # 3分钟检查一次
    
        while True:
            # 等待指定时间
            await asyncio.sleep(CHECK_INTERVAL)
    
            # 检查群聊阻塞队列
            if hasattr(self, '_blocking_group_queue') and self._blocking_group_queue:
                blocked_count = len(self._blocking_group_queue)
                logger.warning(f"定期检查：群聊阻塞队列中有 {blocked_count} 条消息待处理")
                logger.debug(f"qq群聊阻塞队列（_blocking_group_queue）：{self._blocking_group_queue}")
    
    
            # 检查私聊阻塞队列
            if hasattr(self, '_blocking_c2c_queue') and self._blocking_c2c_queue:
                blocked_count = len(self._blocking_c2c_queue)
                logger.warning(f"定期检查：私聊阻塞队列中有 {blocked_count} 条消息待处理")
                logger.debug(f"qq私聊阻塞队列（_blocking_c2c_queue）：{self._blocking_c2c_queue}")
                
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
                    logger.info(f"收到图片：{attachment.filename}，attachment：{attachment}")
                if attachment.content_type and attachment.content_type == "file":
                    logger.info(f"收到文件：{attachment.filename}，attachment：{attachment}")
                if attachment.content_type and attachment.content_type == "voice":
                    logger.info(f"收到语音：{attachment.filename}，attachment：{attachment}")
                _type = MessageType.file

                    
        # 构建source
        # message.author.id没有用，message.guild_id才有用，用作qq频道私信fa发送信息的的guild_id
        author_dict = json.loads(json.dumps({"id": message.guild_id, "username": message.author.username, "avatar": message.author.avatar}))

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
            content=message.content or ".",
            source=source,
            is_mentioned=is_mentioned,
            is_from_self=is_from_self,
            attachments=message.attachments,
        )
        # 向用户表中添加该用户
        add_person(message_obj.person)
        # 向消息表中添加该消息
        message_obj.id = add_message(message_obj)
        # DEBUG
        logger.debug(str(message_obj))
        # 用户发来的消息均送给消息解析器处理
        await message_handler.handle_message(message_obj)

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
        logger.info(f"收到私信:{message.content}")
        # 适配wechatter的消息对象
        _type = MessageType.text
        if message.attachments:
            for attachment in message.attachments:
                # 检查是否为图片
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    logger.info(f"收到图片：{attachment.filename}，attachment：{attachment}")
                if attachment.content_type and attachment.content_type == "file":
                    logger.info(f"收到文件：{attachment.filename}，attachment：{attachment}")
                if attachment.content_type and attachment.content_type == "voice":
                    logger.info(f"收到语音：{attachment.filename}，attachment：{attachment}")
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
            content=message.content or ".",
            source=source,
            is_mentioned=is_mentioned,
            is_from_self=is_from_self,
            attachments=message.attachments,
        )
        # 向群组表中添加该群组
        add_group(message_obj.group)
        # 向用户表中添加该用户
        add_person(message_obj.person)
        # 向消息表中添加该消息
        message_obj.id = add_message(message_obj)
        # DEBUG
        logger.debug(str(message_obj))
        # 用户发来的消息均送给消息解析器处理
        await message_handler.handle_message(message_obj)

        # 处理阻塞队列中的消息
        if hasattr(self, '_blocking_group_queue') and self._blocking_group_queue:
            logger.warning(f"收到新消息，尝试处理qq群阻塞消息队列(_blocking_group_queue)中的消息，当前队列长度：{len(self._blocking_group_queue)}")
            logger.debug(f"qq群阻塞消息队列(_blocking_group_queue):{self._blocking_group_queue}")
            # 最多处理5条消息（因为一个msg_id最多只能回复5次）
            messages_to_process = min(5, len(self._blocking_group_queue))
            logger.warning(f"本次将处理 {messages_to_process} 条qq群阻塞消息队列")
    
            # 将部分阻塞队列消息添加到正常队列
            for i in range(messages_to_process):
                blocked_msg = self._blocking_group_queue.pop(0)  # 从队列头部取出消息
                self._group_at_message_queue.append(blocked_msg)
            logger.warning(f"处理后qq群阻塞消息队列剩余 {len(self._blocking_group_queue)} 条消息")

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
                    logger.info(f"收到图片：{attachment.filename}，attachment：{attachment}")
                if attachment.content_type and attachment.content_type == "file":
                    logger.info(f"收到文件：{attachment.filename}，attachment：{attachment}")
                if attachment.content_type and attachment.content_type == "voice":
                    logger.info(f"收到语音：{attachment.filename}，attachment：{attachment}")
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
            content=message.content or ".",
            source=source,
            is_mentioned=is_mentioned,
            is_from_self=is_from_self,
            attachments=message.attachments,
        )
        # 向用户表中添加该用户
        add_person(message_obj.person)
        # 向消息表中添加该消息
        message_obj.id = add_message(message_obj)
        # DEBUG
        logger.debug(str(message_obj))
        # 用户发来的消息均送给消息解析器处理
        await message_handler.handle_message(message_obj)

        # 处理阻塞队列中的消息
        if hasattr(self, '_blocking_c2c_queue') and self._blocking_c2c_queue:
            logger.warning(f"收到新消息，尝试处理qq私聊阻塞消息队列(_blocking_c2c_queue)中的消息，当前队列长度：{len(self._blocking_c2c_queue)}")
            logger.debug(f"qq私聊阻塞消息队列(_blocking_c2c_queue):{self._blocking_c2c_queue}")
            # 最多处理5条消息（因为一个msg_id最多只能回复5次）
            messages_to_process = min(5, len(self._blocking_c2c_queue))
            logger.warning(f"本次将处理 {messages_to_process} 条qq私聊阻塞消息")

            # 将部分阻塞队列消息添加到正常队列
            for i in range(messages_to_process):
                blocked_msg = self._blocking_c2c_queue.pop(0)  # 从队列头部取出消息
                self._c2c_message_queue.append(blocked_msg)
            logger.warning(f"处理后qq私聊阻塞消息队列剩余 {len(self._blocking_c2c_queue)} 条消息")

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
    client = QQBot(
        intents=intents,
        bot_log=None  # 禁用bot日志
    )
    qq_bot_instance = client    
    return client

def desensitize_message(content):
    """
    对消息进行脱敏处理
    """
    """     
    # 匹配所有URL
    url_pattern = r'https?://[^\s]+'
    content = re.sub(url_pattern, '[链接已隐藏]', content)
    # 匹配所有域名（如 example.com、abc.xyz、mail.example.co.uk）
    # 只要有"点"且后面是2-10位字母（常见顶级域名长度）
    domain_pattern = r'\b[a-zA-Z0-9.-]+\.[a-zA-Z]{2,10}\b'
    content = re.sub(domain_pattern, '[域名已隐藏]', content)
    return content
    """
    return re.sub(r'\.', '_', content)
