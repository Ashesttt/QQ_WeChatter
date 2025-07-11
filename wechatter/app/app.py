from fastapi import FastAPI
from loguru import logger

import wechatter.app.routers as routers
from wechatter.art_text import print_wechatter_art_text
from wechatter.config import config
from wechatter.config.parsers import parse_task_cron_list
from wechatter.scheduler import Scheduler

app = FastAPI()

app.include_router(routers.wechat_router)
app.include_router(routers.upload_router)  # 添加图片上传路由
app.include_router(routers.coolmonitor_router)


if config["github_webhook_enabled"]:
    app.include_router(routers.github_router)

# 定时任务
scheduler = Scheduler()
if config["all_task_cron_enabled"]:
    scheduler.cron_task_list = parse_task_cron_list(config["task_cron_list"])
    print(parse_task_cron_list(config["task_cron_list"]))


@app.on_event("startup")
def startup():
    scheduler.startup()
    print_wechatter_art_text()
    logger.info("WeChatter 启动成功！")


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()
