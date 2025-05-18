import threading
import time
import functools
from loguru import logger

def run_in_thread(send_processing_message=True, delay=0.2):
    """
    将函数在单独线程中运行的装饰器
    
    :param send_processing_message: 是否发送处理中的消息
    :param delay: 发送处理消息后等待的秒数，确保消息先被处理
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 获取参数
            to = kwargs.get('to', None)
            if to is None and len(args) > 0:
                to = args[0]

            command_name = func.__name__.replace('_command_handler', '')

            # 发送处理中消息
            # if send_processing_message and to:
            #     from wechatter.sender import sender
            #     sender.send_msg(to, f"正在处理 {command_name} 命令...")

            # 线程函数
            def thread_func():
                try:
                    # 等待一段时间，确保处理中消息先发送
                    if send_processing_message:
                        time.sleep(delay)

                    # 执行原函数
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"线程中执行 {func.__name__} 时发生错误: {str(e)}")
                    # 发送错误消息
                    if to:
                        from wechatter.sender import sender
                        sender.send_msg(to, f"执行 {command_name} 命令时发生错误: {str(e)}")

            # 启动线程
            thread = threading.Thread(target=thread_func)
            thread.daemon = True
            thread.start()

            # 不返回任何内容，因为实际处理在线程中进行
            return None

        return wrapper

    return decorator
