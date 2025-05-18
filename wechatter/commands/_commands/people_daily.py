from typing import Union
import re
import requests
from bs4 import BeautifulSoup
from loguru import logger

from wechatter.commands.handlers import command
from wechatter.models.wechat import SendTo
from wechatter.sender import sender
from wechatter.utils.time import get_current_ymd


@command(
    command="people-daily",
    keys=["人民日报", "people", "people-daily"],
    desc="获取人民日报。",
)
def people_daily_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    """
    发送人民日报pdf
    """
    _send_people_daily(to, message, type="fileUrl")


@command(
    command="people-daily-url",
    keys=["人民日报链接", "people-url", "people-daily-url"],
    desc="获取人民日报url。",
)
def people_daily_url_command_handler(to: Union[str, SendTo], message: str = "") -> None:
    """
    发送人民日报url
    """
    _send_people_daily(to, message, type="text")


def _send_people_daily(to: Union[str, SendTo], message: str, type: str) -> None:
    if message == "":
        try:
            url = get_today_people_daliy_url()
        except Exception as e:
            error_message = f"获取今天的人民日报失败，错误信息：{str(e)}"
            logger.error(error_message)
            sender.send_msg(to, error_message)
        else:
            sender.send_msg(to, url, type=type)
    # 获取指定日期
    else:
        try:
            url = get_people_daily_url(message)
        except Exception as e:
            error_message = f"输入的日期版本号不符合要求，请重新输入，错误信息：{str(e)}\n若要获取2025年5月18日01版的人民日报的URL，请输入：\n/people-url 2025051801"
            logger.error(error_message)
            sender.send_msg(to, error_message)
        else:
            sender.send_msg(to, url, type=type)


def get_people_daily_url(date_version: str) -> str:
    """获取特定日期特定版本的人民日报PDF链接"""
    if not date_version.isdigit() or len(date_version) != 10:
        logger.error("输入的日期版本号不符合要求，请重新输入。")
        raise ValueError("输入的日期版本号不符合要求，请重新输入。")

    # 解析日期和版本
    yearmonthday = date_version[:8]  # 20250518
    year = date_version[:4]  # 2025
    month = date_version[4:6]  # 05
    day = date_version[6:8]  # 18
    version = date_version[8:]  # 01

    # 构造布局页面URL
    year_month = f"{year}{month}"  # 202505
    layout_url = f"https://paper.people.com.cn/rmrb/pc/layout/{year_month}/{day}/node_{version}.html"

    try:
        # 请求布局页面
        response = requests.get(layout_url, timeout=10)
        response.raise_for_status()

        # 解析HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # 查找PDF下载链接
        download_link = soup.select_one(f'a[download="rmrb{yearmonthday}{version}.pdf"]')
        if not download_link:
            raise ValueError(f"未找到{yearmonthday}{version}版人民日报的下载链接")

        pdf_url = "https://paper.people.com.cn" + download_link['href'].replace("../../../", "/rmrb/pc/")
        return pdf_url
    except requests.RequestException as e:
        logger.error(f"请求人民日报页面失败: {e}")
        raise ValueError(f"获取人民日报失败: {e}")
    except Exception as e:
        logger.error(f"解析人民日报页面失败: {e}")
        raise ValueError(f"获取人民日报失败: {e}")


def get_today_people_daliy_url() -> str:
    """获取今日01版人民日报PDF的url"""
    yearmonthday = get_current_ymd()
    version = "01"
    today_version = f"{yearmonthday}{version}"
    return get_people_daily_url(today_version)
