from wechatter.init_logger import init_logger

from .config import load_config
from .validate import validate_config
from .qq_validate import validate_qq_bot_config

# 初始化 logger
init_logger()
# 加载配置
config = load_config()

# 根据配置类型选择验证方式
bot_type = config.get("bot_type", "wechat")
if bot_type == "qq":
    validate_qq_bot_config(config)
else:
    validate_config(config)

__all__ = ["config"]