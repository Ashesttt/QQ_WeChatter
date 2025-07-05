from fastapi import APIRouter, Request
from loguru import logger

from wechatter.sender import sender

router = APIRouter()

@router.post("/webhook/coolmonitor")
async def recv_coolmonitor_webhook(request: Request):
    """
    接收 coolmonitor Webhook
    """
    data = await request.json()

    
    try:
        message = _generate_coolmonitor_message(data)
        sender.mass_send_msg_to_admins(message)
    except Exception as e:
        logger.error(f"处理coolmonitor Webhook失败: {str(e)}")
        return {"detail": "Webhook processing failed"}
    
    return {"detail": "Webhook received"}

def _generate_coolmonitor_message(data: dict) -> str:
    """
    生成coolmonitor通知消息
    """
    event = data.get("event", "unknown")
    monitor = data.get("monitor", {})
    
    status_emoji = {
        "正常": "✅",
        "异常": "❌",
        "等待": "🔄"
    }.get(monitor.get("status"), "❓")
    
    message = (
        "== coolmonitor 监控状态变更 ==\n"
        f"💬 事件：{event}\n"
        f"📅 时间: {data.get('timestamp')}\n"
        f"📊 监控项: {monitor.get('name')} ({monitor.get('type')})\n"
        f"{status_emoji} 状态: {monitor.get('status')}\n"
        f"📝 详情: {monitor.get('message')}\n"
    )
    
    if monitor.get("status") == "异常" and "failure_info" in data:
        failure = data["failure_info"]
        message += (
            f"⚠️ 失败次数: {failure.get('count')}\n"
            f"⏱️ 持续时间: {failure.get('duration_minutes')}分钟\n"
            f"⏳ 首次失败: {failure.get('first_failure_time')}\n"
            f"⌛ 最后失败: {failure.get('last_failure_time')}\n"
        )
    
    return message
