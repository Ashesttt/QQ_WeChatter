#
#  __     __   ______   ______   __  __   ______   ______  ______  ______   ______
# /\ \  _ \ \ /\  ___\ /\  ___\ /\ \_\ \ /\  __ \ /\__  _\/\__  _\/\  ___\ /\  == \
# \ \ \/ ".\ \\ \  __\ \ \ \____\ \  __ \\ \  __ \\/_/\ \/\/_/\ \/\ \  __\ \ \  __<
#  \ \__/".~\_\\ \_____\\ \_____\\ \_\ \_\\ \_\ \_\  \ \_\   \ \_\ \ \_____\\ \_\ \_\
#   \/_/   \/_/ \/_____/ \/_____/ \/_/\/_/ \/_/\/_/   \/_/    \/_/  \/_____/ \/_/ /_/
#

import uvicorn

import wechatter.database as db
from wechatter.app.app import app
from wechatter.bot import BotInfo
from wechatter.config import config
from wechatter.games import load_games
from wechatter.utils import check_and_create_folder


def main():
    """
    WeChatter 启动文件
    """

    BotInfo.update_name(config["bot_name"])
    # 创建文件夹
    check_and_create_folder("data/qrcodes")
    check_and_create_folder("data/todos")
    check_and_create_folder("data/text_image")
    check_and_create_folder("data/upload_image")
    check_and_create_folder("data/screenshots")

    db.create_tables()
    load_games()

    # 启动uvicorn
    port = config["wechatter_port"]
    uvicorn.run(app, host="0.0.0.0", port=port)  # nosec


if __name__ == "__main__":
    main()
