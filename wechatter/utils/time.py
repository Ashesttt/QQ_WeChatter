# 获取时间工具类
import time
from datetime import datetime, timedelta


def get_current_hour() -> int:
    """
    获取当前小时
    :return: 返回当前小时
    """
    return time.localtime().tm_hour


def get_current_minute() -> int:
    """
    获取当前分钟
    :return: 返回当前分钟
    """
    return time.localtime().tm_min


def get_current_second() -> int:
    """
    获取当前秒
    :return: 返回当前秒
    """
    return time.localtime().tm_sec


def get_current_timestamp() -> int:
    """
    获取当前时间戳
    :return: 返回当前时间戳
    """
    return int(time.time())


def get_current_datetime_object() -> datetime:
    """
    获取当前时间对象
    :return: 返回当前时间对象
    """
    return datetime.now()


def get_current_datetime() -> str:
    """
    获取当前时间
    :return: 返回格式化后的时间字符串
    """
    return time.strftime("%y-%m-%d_%H-%M-%S", time.localtime())

def get_current_datetime2() -> str:
    """
    获取当前时间
    :return: 返回格式化后的时间字符串
    """
    return time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())


def get_current_date() -> str:
    """
    获取当前日期
    :return: 返回格式化后的日期字符串
    """
    return time.strftime("%y-%m-%d", time.localtime())


def get_current_week() -> str:
    """
    获取当前日期
    :return: 返回格式化后的日期字符串
    """
    return time.strftime("%w", time.localtime())


def get_current_time() -> str:
    """
    获取当前时间
    :return: 返回格式化后的时间字符串
    """
    return time.strftime("%H:%M:%S", time.localtime())


def get_current_year_month() -> str:
    """
    获取当前年月
    :return: 返回格式化后的年月字符串
    """
    return time.strftime("%Y-%m", time.localtime())


def get_current_day() -> str:
    """
    获取当前日
    :return: 返回格式化后的日字符串
    """
    return time.strftime("%d", time.localtime())


def get_current_ymd() -> str:
    """
    获取当前年月日
    :return: 格式化后的年月日字符串
    """
    return time.strftime("%Y%m%d", time.localtime())


def get_current_ymdh() -> str:
    """
    获取当前年月日时
    :return: 返回格式化后的年月日时字符串
    """
    return time.strftime("%Y%m%d%H", time.localtime())


def get_current_bdy() -> str:
    """
    获取当前月（英文）日年
    :return: 返回格式化后的月（英文）日年字符串,输出: November 16, 2024
    """
    return time.strftime("%B %d, %Y", time.localtime())


def get_yesterday_bdy() -> str:
    """
    获取昨天月（英文）日年
    :return: 返回格式化后的昨天月（英文）日年字符串,输出: November 16, 2024
    """
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime("%B %d, %Y")
