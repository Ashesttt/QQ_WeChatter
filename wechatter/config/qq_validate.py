from loguru import logger

QQ_BOT_ESSENTIAL_FIELDS = [
    # "bot_name",
    "wechatter_port",
    "qq_bot",
]

QQ_BOT_CONFIG_FIELDS = [
    "appid", 
    "secret"
]


def validate_qq_bot_config(config):
    """
    验证QQ机器人配置
    :param config: 配置文件
    """
    logger.info("正在验证QQ机器人配置...")

    # 顶层字段验证
    for field in QQ_BOT_ESSENTIAL_FIELDS:
        if field not in config:
            error_msg = f"配置参数错误：缺少必要字段 {field}"
            logger.critical(error_msg)
            raise ValueError(error_msg)
    
    # QQ机器人配置验证
    qq_bot_config = config.get("qq_bot", {})
    for field in QQ_BOT_CONFIG_FIELDS:
        if field not in qq_bot_config:
            error_msg = f"配置参数错误：qq_bot配置缺少必要字段 {field}"
            logger.critical(error_msg)
            raise ValueError(error_msg)
    
    logger.info("QQ机器人配置验证通过！")
