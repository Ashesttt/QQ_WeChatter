#
#  __     __   ______   ______   __  __   ______   ______  ______  ______   ______
# /\ \  _ \ \ /\  ___\ /\  ___\ /\ \_\ \ /\  __ \ /\__  _\/\__  _\/\  ___\ /\  == \
# \ \ \/ ".\ \\ \  __\ \ \ \____\ \  __ \\ \  __ \\/_/\ \/\/_/\ \/\ \  __\ \ \  __<
#  \ \__/".~\_\\ \_____\\ \_____\\ \_\ \_\\ \_\ \_\  \ \_\   \ \_\ \ \_____\\ \_\ \_\
#   \/_/   \/_/ \/_____/ \/_____/ \/_/\/_/ \/_/\/_/   \/_/    \/_/  \/_____/ \/_/ /_/
#

import threading

import uvicorn

import wechatter.database as db
from wechatter.app.app import app
from wechatter.art_text import print_wechatter_art_text
from wechatter.bot import BotInfo, create_qq_bot
from wechatter.config import config
from wechatter.games import load_games
from wechatter.utils import check_and_create_folder


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


def main():
    """
    QQChatter 启动文件
    """
    # BotInfo.update_name(config["bot_name"])
    # 创建文件夹
    check_and_create_folder("data/qrcodes")
    check_and_create_folder("data/todos")
    check_and_create_folder("data/text_image")

    # 初始化数据库
    db.create_tables()

    # 加载游戏
    if config.get("features", {}).get("enable_games", False):
        load_games()

    print_wechatter_art_text()

    # 启动Web服务器作为单独线程
    web_thread = threading.Thread(target=start_web_server)
    web_thread.daemon = True
    web_thread.start()

    # 主线程运行QQ机器人
    start_qq_bot()
