import json
import time
import random
from functools import singledispatch
from typing import List, Union

import requests
import tenacity
from loguru import logger

from wechatter.app.routers.qq_bot import desensitize_message
from wechatter.app.routers.upload import upload_image
from wechatter.commands._commands.qrcode import get_qrcode_saved_path
from wechatter.config import config
from wechatter.models import Person
from wechatter.models.wechat import QuotedResponse, SendTo, Group
from wechatter.sender.quotable import make_quotable
from wechatter.utils import join_urls, post_request


# 对retry装饰器重新包装，增加日志输出
def _retry(
    stop=tenacity.stop_after_attempt(3),
    retry_error_log_level="ERROR",
):
    """
    重试装饰器
    """

    def retry_wrapper(func):
        @tenacity.retry(stop=stop)
        def wrapped_func(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.log(
                    retry_error_log_level,
                    f"重试 {func.__name__} 失败，错误信息：{str(e)}",
                )
                raise

        return wrapped_func

    return retry_wrapper


def _logging(func):
    """
    日志装饰器
    """

    def logging_wrapper(*args, **kwargs):
        response = func(*args, **kwargs)
        try:
            r_json = response.json()
        except requests.exceptions.JSONDecodeError:
            logger.debug("请求返回值 JSON 解析失败")
            return
        # https://github.com/danni-cool/wechatbot-webhook?tab=readme-ov-file#%E8%BF%94%E5%9B%9E%E5%80%BC-response-%E7%BB%93%E6%9E%84
        if r_json["message"].startswith("Message"):
            pass
        elif r_json["message"].startswith("Some"):
            logger.error(f"发送消息失败，参数校验不通过：{kwargs['json']}")
        elif r_json["message"].startswith("All"):
            logger.error(f"发送消息失败，所有消息均发送失败: {kwargs['json']}")
            return
        elif r_json["message"].startswith("Part"):
            logger.warning(f"发送消息失败，部分消息发送成功: {kwargs['json']}")
            return

        if "task" not in r_json:
            return

        try:
            data = json.loads(response.request.body.decode("utf-8"))
        except UnicodeDecodeError:
            # 本地文件发送无法解码
            # logger.info("发送图片成功")
            return
        except json.JSONDecodeError as e:
            logger.error(f"发送消息失败，错误信息：{str(e)}")
            return

        if isinstance(data, list):
            for item in data:
                logger.info(
                    f"发送消息成功，发送给：{item['to']}，发送的内容：{item['data']}"
                )
        elif isinstance(data, dict):
            logger.info(
                f"发送消息成功，发送给：{data['to']}，发送的内容：{data['data']}"
            )

    return logging_wrapper


@_logging
@_retry()
def _post_request(
    url, data=None, json=None, files=None, headers={}, timeout=5
) -> requests.Response:
    return post_request(
        url, data=data, json=json, files=files, headers=headers, timeout=timeout
    )


URL = (
    join_urls(config["wx_webhook_base_api"], "webhook/msg/v2")
    + f"?token={config['wx_webhook_token']}"
)
V1_URL = (
    join_urls(config["wx_webhook_base_api"], "webhook/msg")
    + f"?token={config['wx_webhook_token']}"
)

MSG_TYPE = ["text", "fileUrl", "localfile"]


def _validate(func):
    """
    验证接收者和消息内容是否为空
    """

    def validate_wrapper(to, message, *args, **kwargs):
        if not to:
            logger.error(f"发送消息失败，接收者为空：{func.__name__}")
            return
        if not message:
            logger.error(f"发送消息失败，消息内容为空：{func.__name__}")
            return
        # 检查kwargs中type的值是否合法
        if "type" in kwargs:
            if kwargs["type"] not in MSG_TYPE:
                logger.error(
                    f"发送消息失败，消息类型 type 的值不合法，type 只能为以下值之一: {MSG_TYPE}"
                )
                return

        return func(to, message, *args, **kwargs)

    return validate_wrapper


@singledispatch
def send_msg(
    to: Union[str, SendTo],
    message: str,
    is_group: bool = False,
    type: str = "text",
    quoted_response: QuotedResponse = None,
):
    """
    发送消息

    当传入的第一个参数是字符串时，is_group 默认为 False。
    当传入的第一个参数是 SendTo 对象时，is_group 默认为 True。

    当 quoted_response 不为 None 时，该消息为可引用消息。表示该消息被
    引用回复后，会触发进一步的消息互动。

    :param to: 接收对象的名字或SendTo对象
    :param message: 消息内容
    :param is_group: 是否为群组（默认值根据 to 的类型而定）
    :param type: 消息类型，可选 text、fileUrl（默认值为 text）
    :param quoted_response: 被引用后的回复消息（默认值为 None）
    """
    pass


@send_msg.register(str)
@_validate
def _send_msg1(
    name: str,
    message: str,
    is_group: bool = False,
    type: str = "text",
    quoted_response: QuotedResponse = None,
    platform = "qq",
    person: Person = None,
    group: Group = None,
):
    """
    发送消息
    :param name: 接收者
    :param message: 消息内容
    :param is_group: 是否为群组（默认为个人，False）
    :param type: 消息类型（text、fileUrl）
    :param quoted_response: 被引用后的回复消息（默认值为 None）
    """    
    # 一般只要是引用的消息，message都是url，但是qq机器人需要配置https才可以发送url，
    # 因此如果是引用消息，就可以把它变成二维码，这样就很好的解决问题

    # 如果内容是URL，转二维码
    if message.startswith("http://") or message.startswith("https://"):
        logger.warning(f"发送消息为URL，尝试转二维码。消息message：{message}")
        message = get_qrcode_saved_path(message)
        # 成功把url变成qrcode 注意这里的message已经变成了qrcode的路径
        # 注意type要用"localfile"
        type="localfile"
        
    is_image = False
    if type == "localfile":
        is_image = True
        # 已经是绝对路径
        abs_image_path = message
        url_image_path = upload_image(abs_image_path)
        message = url_image_path
    else:
        message = desensitize_message(message)
        
    if quoted_response:
        message = make_quotable(message=message, quoted_response=quoted_response)

        
    
    # 如果是QQ平台
    if platform == "qq":
        from wechatter.app.routers.qq_bot import qq_bot_instance
        print("QQ消息发送中...")
        if qq_bot_instance:
            # 如果要发送给个人就有person
            if person:
                logger.debug(f"这是person:{person}")
                msg_id = person.msg_id
                # 如果person有guild_id，说明是在qq频道私信
                if person.guild_id is not None:
                    guild_id = person.guild_id
                        # 添加到发送队列
                    qq_bot_instance._direct_message_queue.append((message, guild_id, msg_id, is_image))
                    logger.info(f"QQ消息已加入qq频道私信队列(_direct_message_queue)，信息是：{message}，guild_id：{guild_id}，msg_id：{msg_id}，是否为图片：{is_image}。")
                    
                # 如果person有user_openid，说明是在qq私信
                elif person.user_openid is not None:
                    user_openid = person.user_openid
                    # 添加到发送队列
                    qq_bot_instance._c2c_message_queue.append((message, user_openid, msg_id, is_image))
                    logger.info(f"QQ消息已加入qq私信队列(_c2c_message_queue)，信息是：{message}，user_openid：{user_openid}，msg_id：{msg_id}，是否为图片：{is_image}。")
                
            if group:
                logger.debug(f"这是group:{group}")
                group_openid = group.id
                msg_id = group.msg_id
                # 添加到发送队列
                qq_bot_instance._group_at_message_queue.append((message, group_openid, msg_id, group, is_image))
                logger.info(f"QQ消息已加入qq群消息队列(_group_at_message_queue)，信息是：{message}，group_openid：{group_openid}，msg_id：{msg_id}，group：{group}，是否为图片：{is_image}。")
                
    return

@send_msg.register(SendTo)
def _send_msg2(
    to: SendTo,
    message: str,
    is_group: bool = True,
    type: str = "text",
    quoted_response: QuotedResponse = None,
):
    """
    发送消息
    :param to: SendTo 对象
    :param message: 消息内容
    :param is_group: 是否为群组（默认为群组，True）
    :param type: 消息类型（text、fileUrl）
    :param quoted_response: 被引用后的回复消息（默认值为 None）
    """
    if not is_group:
        return _send_msg1(
            to.p_name,
            message,
            is_group=False,
            type=type,
            quoted_response=quoted_response,
        )

    if to.g_id and to.g_name:
        return _send_msg1(
            to.g_name,
            message,
            is_group=True,
            type=type,
            quoted_response=quoted_response,
            group=to.group
        )   
    elif to.person:
        return _send_msg1(
            to.p_name,
            message,
            is_group=False,
            type=type,
            quoted_response=quoted_response,
            person=to.person
        )
    else:
        logger.error("发送消息失败，接收者为空")


@singledispatch
def send_msg_list(
    to: Union[str, SendTo],
    message_list: List[str],
    is_group: bool = False,
    type: str = "text",
):
    """
    发送多条消息，消息类型相同
    :param to: 接收者
    :param message_list: 消息内容列表
    :param is_group: 是否为群组
    :param type: 消息类型（text、fileUrl）
    """
    pass


@send_msg_list.register(str)
@_validate
def _send_msg_list1(
    name: str,
    message_list: List[str],
    is_group: bool = False,
    type: str = "text",
):
    """
    发送多条消息，消息类型相同
    :param name: 接收者
    :param message_list: 消息内容列表
    :param is_group: 是否为群组
    :param type: 消息类型（text、fileUrl）
    """
    data = {"to": name, "isRoom": is_group, "data": []}
    for message in message_list:
        data["data"].append({"type": type, "content": message})
    _post_request(URL, json=data)


@send_msg_list.register(SendTo)
def _send_msg_list2(
    to: SendTo, message_list: List[str], is_group: bool = True, type: str = "text"
):
    """
    发送多条消息，消息类型相同
    :param to: SendTo 对象
    :param message_list: 消息内容列表
    :param is_group: 是否为群组
    :param type: 消息类型（text、fileUrl）
    """
    if not is_group:
        return _send_msg_list1(to.p_name, message_list, is_group=False, type=type)

    if to.group:
        return _send_msg_list1(to.g_name, message_list, is_group=True, type=type)
    elif to.person:
        return _send_msg_list1(to.p_name, message_list, is_group=False, type=type)
    else:
        logger.error("发送消息失败，接收者为空")


@_validate
def mass_send_msg(
    name_list: List[str],
    message: str,
    is_group: bool = False,
    type: str = "text",
    quoted_response: QuotedResponse = None,
    is_qq_c2c_list: bool = False,
):
    """
    群发消息，给多个人发送一条消息
    :param name_list: 接收者列表
    :param message: 消息内容
    :param is_group: 是否为群组
    :param type: 消息类型（text、fileUrl、localfile）
    :param quoted_response: 被引用后的回复消息（默认值为 None）
    """
    global qq_bot_instance  # 声明引用全局变量

    # 一般只要是引用的消息，message都是url，但是qq机器人需要配置https才可以发送url，
    # 因此如果是引用消息，就可以把它变成二维码，这样就很好的解决问题

    # 如果内容是URL，转二维码
    if message.startswith("http://") or message.startswith("https://"):
        logger.warning(f"发送消息为URL，尝试转二维码。消息message：{message}")
        message = get_qrcode_saved_path(message)
        # 成功把url变成qrcode 注意这里的message已经变成了qrcode的路径
        # 注意type要用"localfile"
        type="localfile"

    is_image = False
    if type == "localfile":
        is_image = True
        # 已经是绝对路径
        abs_image_path = message
        url_image_path = upload_image(abs_image_path)
        message = url_image_path
    else:
        message = desensitize_message(message)

    if quoted_response:
        message = make_quotable(message=message, quoted_response=quoted_response)
        
    # 由于是主动发送，所以没有msg_id
    msg_id = None
    is_image = False
    if type == "localfile":
        is_image = True
        # 已经是绝对路径
        abs_image_path = message
        url_image_path = upload_image(abs_image_path)
        message = url_image_path



    for name in name_list:
        # 只有qq频道才可以主动发送信息
        # 通过name获取guild_id(就是person的id)
        from wechatter.database.tables.person import Person as DbPerson
        from wechatter.database import make_db_session
        from wechatter.app.routers.qq_bot import qq_bot_instance
        if not is_group:
            if is_qq_c2c_list:
                user_openid = name
                qq_bot_instance._c2c_message_queue.append((message, user_openid, msg_id, is_image))
                logger.info(f"QQ消息已加入qq私信队列(_c2c_message_queue)，信息是：{message}，user_openid：{user_openid}，msg_id：{msg_id}，是否为图片：{is_image}。")
            else:
                with make_db_session() as session:
                    person = session.query(DbPerson).filter(DbPerson.name == name).first()
                    if person and person.id is not None:
                        guild_id = str(person.id)                  
                        # 添加到发送队列
                        qq_bot_instance._direct_message_queue.append((message, guild_id, msg_id, is_image))
                        logger.info(f"QQ消息已加入qq频道私信队列(_direct_message_queue)，信息是：{message}，guild_id：{guild_id}，msg_id：{msg_id}，是否为图片：{is_image}。")
        else:
            # 是群，因此name就是群group_openid
            group_openid = name
            group = Group(
                id=group_openid,
                name=group_openid,
                member_list=[],
            )
            # 添加到发送队列
            qq_bot_instance._group_at_message_queue.append((message, group_openid, msg_id, group, is_image))
            logger.info(f"QQ消息已加入qq群消息队列(_group_at_message_queue)，信息是：{message}，group_openid：{group_openid}，msg_id：{msg_id}，group：{group}，是否为图片：{is_image}。")
            
                
        
        # data = [
        #     {
        #         "to": name,
        #         "isRoom": is_group,
        #         "data": {"type": type, "content": message},
        #     }
        # ]
        # _post_request(URL, json=data)
        # time.sleep(random.uniform(5, 6))  # 避免触发风控，使用 5-6 秒之间的随机数


@singledispatch
def send_localfile_msg(to: Union[str, SendTo], file_path: str, is_group: bool = False):
    """
    发送本地文件
    :param to: 接收者
    :param file_path: 文件路径
    :param is_group: 是否为群组
    """
    pass


@send_localfile_msg.register(str)
@_validate
def _send_localfile_msg1(name: str, file_path: str, is_group: bool = False):
    """
    发送本地文件
    :param name: 接收者
    :param file_path: 文件路径
    :param is_group: 是否为群组
    """
    data = {"to": name, "isRoom": int(is_group)}
    files = {"content": open(file_path, "rb")}
    _post_request(V1_URL, data=data, files=files)


@send_localfile_msg.register(SendTo)
def _send_localfile_msg2(to: SendTo, file_path: str, is_group: bool = True):
    """
    发送本地文件
    :param to: SendTo 对象
    :param file_path: 文件路径
    :param is_group: 是否为群组
    """
    if not is_group:
        return _send_localfile_msg1(to.p_name, file_path, is_group=False)

    if to.group:
        return _send_localfile_msg1(to.g_name, file_path, is_group=True)
    elif to.person:
        return _send_localfile_msg1(to.p_name, file_path, is_group=False)
    else:
        logger.error("发送消息失败，接收者为空")


def mass_send_msg_to_admins(
    message: str, type: str = "text", quoted_response: QuotedResponse = None
):
    """
    群发消息给所有管理员
    :param message: 消息内容
    :param type: 消息类型（text、fileUrl）
    :param quoted_response: 被引用后的回复消息（默认值为 None）
    """
    if quoted_response:
        message = make_quotable(message=message, quoted_response=quoted_response)

    admin_list = config.get("admin_list")
    admin_qq_c2c_list = config.get("admin_qq_c2c_list")
    if admin_list:
        logger.info(f"发送消息给管理员：{admin_list}")
        mass_send_msg(admin_list, message, type=type)
    
    if admin_qq_c2c_list:
        logger.info(f"发送qq私信消息给管理员：{admin_qq_c2c_list}")
        mass_send_msg(admin_qq_c2c_list, message, type=type, is_qq_c2c_list=True)

    admin_group_list = config.get("admin_group_list")
    if admin_group_list:
        logger.info(f"发送消息给管理员群组：{admin_group_list}")
        mass_send_msg(admin_group_list, message, is_group=True, type=type)


def mass_send_msg_to_github_webhook_receivers(
    message: str, type: str = "text", quoted_response: QuotedResponse = None
):
    """
    群发消息给所有 GitHub Webhook 接收者
    :param message: 消息内容
    :param type: 消息类型（text、fileUrl）
    :param quoted_response: 被引用后的回复消息（默认值为 None）
    """
    if quoted_response:
        message = make_quotable(message=message, quoted_response=quoted_response)

    person_list = config.get("github_webhook_receive_person_list")
    person_qq_c2c_list = config.get("github_webhook_receive_person_qq_c2c_list")
    group_list = config.get("github_webhook_receive_group_list")
    if person_list:
        logger.info(f"发送消息给 GitHub Webhook 接收者：{person_list}")
        mass_send_msg(
            person_list,
            message,
            is_group=False,
            type=type,
        )
    if person_qq_c2c_list:
        logger.info(f"发送消息给 GitHub Webhook 接收者：{person_qq_c2c_list}")
        mass_send_msg(
            person_qq_c2c_list,
            message,
            is_group=False,
            type=type,
            is_qq_c2c_list=True,
        )
    if group_list:
        logger.info(f"发送消息给 GitHub Webhook 接收者：{group_list}")
        mass_send_msg(
            group_list,
            message,
            is_group=True,
            type=type,
        )


def send_to_discord(webhook_url: str, message: str, person, group=None):
    """
    发送消息到 Discord
    :param webhook_url: Discord 频道 Webhook URL
    :param message: 消息内容
    :param person: 用户
    :param group: 群组
    """
    data = {"username": "", "content": message}
    if group:
        data["username"] = f"WeChatter [{group.name}]-[{person.name}]"
    else:
        data["username"] = f"WeChatter [{person.name}]"

    _post_request(webhook_url, json=data)
