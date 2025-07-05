#
#  __     __   ______   ______   __  __   ______   ______  ______  ______   ______
# /\ \  _ \ \ /\  ___\ /\  ___\ /\ \_\ \ /\  __ \ /\__  _\/\__  _\/\  ___\ /\  == \
# \ \ \/ ".\ \\ \  __\ \ \ \____\ \  __ \\ \  __ \\/_/\ \/\/_/\ \/\ \  __\ \ \  __<
#  \ \__/".~\_\\ \_____\\ \_____\\ \_\ \_\\ \_\ \_\  \ \_\   \ \_\ \ \_____\\ \_\ \_\
#   \/_/   \/_/ \/_____/ \/_____/ \/_/\/_/ \/_/\/_/   \/_/    \/_/  \/_____/ \/_/ /_/
#

import threading
import asyncio
import time

import uvicorn

import wechatter.database as db
from wechatter.app.app import app
from wechatter.app.routers.qq_bot import create_qq_bot
from wechatter.art_text import print_wechatter_art_text
from wechatter.bot import BotInfo
from wechatter.config import config
from wechatter.games import load_games
from wechatter.utils import check_and_create_folder
from wechatter.commands.mcp.mcpchat import MCPChat


def start_web_server():
    """启动Web服务器"""
    # 启动uvicorn
    port = config["wechatter_port"]
    uvicorn.run(app, host="0.0.0.0", port=port)  # nosec


def start_qq_bot():
    """启动QQ机器人"""
    # 获取QQ机器人配置
    bot_config = config.get("qq_bot", {})
    appid = bot_config.get("appid")
    secret = bot_config.get("secret")

    # 创建并启动QQ机器人
    if appid and secret:
        client = create_qq_bot()
        client.run(appid=appid, secret=secret)
    else:
        from loguru import logger
        logger.error("QQ机器人配置不完整，无法启动机器人")


async def cleanup():
    """清理资源"""
    for instance in list(MCPChat._instances):  # 使用list复制集合，因为我们在迭代时会修改它
        await instance.close()


def main():
    """
    QQChatter 启动文件
    """
    # BotInfo.update_name(config["bot_name"])
    # 记录启动时间
    BotInfo.start_time = time.time()
    
    # 创建文件夹
    check_and_create_folder("data/qrcodes")
    check_and_create_folder("data/todos")
    check_and_create_folder("data/text_image")
    check_and_create_folder("data/upload_image")
    check_and_create_folder("data/screenshots")
    check_and_create_folder("data/download_file")
    check_and_create_folder("data/reminds")

    # 初始化数据库
    db.create_tables()

    # 加载游戏
    load_games()

    # 启动Web服务器作为单独线程
    web_thread = threading.Thread(target=start_web_server)
    web_thread.daemon = True
    web_thread.start()

    try:
        # 主线程运行QQ机器人
        start_qq_bot()
    finally:
        # 确保在程序退出时清理资源
        asyncio.run(cleanup())
