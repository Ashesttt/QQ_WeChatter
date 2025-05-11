from .config import config

if __name__ == "__main__":
    # 根据配置决定启动哪个机器人
    bot_type = config.get("bot_type", "wechat")

    if bot_type == "qq":
        from . import qqchatter
        qqchatter.main()
    else:
        from . import wechatter
        wechatter.main()
