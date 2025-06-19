import os
from typing import Union
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from loguru import logger

from wechatter.commands.handlers import command
from wechatter.commands.mcp import mcp_server
from wechatter.models.wechat import SendTo
from wechatter.sender import sender
from wechatter.utils import get_abs_path, run_in_thread
from wechatter.utils.time import get_current_datetime2
"""
pip install playwright
playwright install chromium(必须手动下载）
"""

@command(
    command="screenshot",
    keys=["网页截图", "网站截图", "页面截图", "screenshot"],
    desc="对网页进行截图并发送。用法：/网页截图 [URL]",
)
@run_in_thread()
def screenshot_command_handler(to: Union[str, SendTo], message: str = "", message_obj=None) -> None:
    """
    网页截图命令处理函数
    """
    if not message:
        error_message = "请提供要截图的网页URL。"
        logger.error(error_message)
        sender.send_msg(to, error_message)
        return

    try:
        sender.send_msg(to, "正在截取网页，请稍候...")
        path = get_web_screenshot(message)
        sender.send_msg(to, path, type="localfile")
    except Exception as e:
        error_message = f"截图失败，错误信息：{str(e)}"
        logger.error(error_message)
        sender.send_msg(to, error_message)


@screenshot_command_handler.mainfunc
def get_web_screenshot(url: str, output_path: str = None, timeout: int = 30000) -> str:
    """
    获取网页截图并保存
    
    参数：
    url (str): 要截图的网页URL
    output_path (str, optional): 截图保存路径，默认按域名+时间戳生成
    timeout (int, optional): 页面加载超时时间（毫秒），默认30000
    
    返回：
    str: 保存的截图文件路径
    """
    try:
        with sync_playwright() as p:
            # 启动Chromium浏览器实例
            logger.info("正在启动浏览器实例...")
            browser = p.chromium.launch(
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"]
            )
            logger.debug("已启动浏览器实例")

            page = browser.new_page()
            logger.debug("已创建新页面")

            page.set_default_timeout(timeout)

            logger.debug(f"正在访问URL: {url}")
            page.goto(url)
            logger.debug("页面已加载")

            # 如果未提供输出路径，则自动生成文件名
            if not output_path:
                """urlparse用法
                   url = "https://www.example.com:8080/path/to/resource?key=value#section1"
                   parsed = urlparse(url)
                   print(parsed.scheme)  # 输出: https
                   print(parsed.netloc)  # 输出: www.example.com:8080
                   print(parsed.path)    # 输出: /path/to/resource
                   print(parsed.query)   # 输出：?key=value
                   print(parsed.fragment)# 输出：#section1
                """
                parsed_url = urlparse(url)
                domain = parsed_url.netloc.replace(".", "_") if parsed_url.netloc else "unknown"
                domain_port = domain.replace(":", "_")
                timestamp = get_current_datetime2()
                output_dir = get_abs_path("data/screenshots")
                output_path = os.path.join(
                    output_dir,
                    f"{domain_port}_{timestamp}.png"
                )

            # 截取完整页面截图并保存到指定路径
            page.screenshot(path=output_path, full_page=True, type="png")
            logger.info("截图已完成")

            logger.debug("正在关闭浏览器...")
            browser.close()
            logger.debug("浏览器已关闭")

            # 检查文件是否成功保存
            if not os.path.exists(output_path):
                logger.error(f"文件未成功保存到路径: {output_path}")
                raise FileNotFoundError(f"文件未成功保存到路径: {output_path}")
            else:
                logger.info(f"网页截图已保存到: {output_path}")

            return output_path

    except Exception as e:
        logger.error(f"截图失败: {str(e)}")
        raise RuntimeError(f"截图失败: {str(e)}")

mcp_server.tool(
    name="get_web_screenshot_tool",
    description="获取网页截图。",
)
async def get_web_screenshot_tool(url: str) -> str:
    """ 
    获取网页截图
    :param url: 网页URL,一定要判断是否为http或者https，如果是域名，则帮我加上http或者https
    :return: 截图文件路径
    """
    try:
        # if not url.startswith("http://") and not url.startswith("https://"):
        #     http_url = "http://" + url
        #     # 尝试能否访问
        #     response = requests.get(http_url)
        #     if response.status_code == 200:
        #         url = http_url
        #     else:
        #         url = "https://" + url
        return await run_in_thread(get_web_screenshot, url)
    except Exception as e:
        logger.error(f"截图失败: {str(e)}")
        raise RuntimeError(f"截图失败: {str(e)}")