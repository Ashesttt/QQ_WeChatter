import time
from datetime import datetime, timedelta

from wechatter.commands.handlers import command
from wechatter.commands.mcp import mcp_server
from wechatter.database import make_db_session
from wechatter.database.tables.Statistical_table import MessageStats, CommandStats
from wechatter.models.wechat import SendTo
from wechatter.sender import sender
from wechatter.bot import BotInfo
from wechatter.utils.system_monitor import get_system_info, get_network_info, get_project_memory_usage, get_project_disk_usage


@command(
    command="bot",
    keys=["bot", "机器人", "状态"],
    desc="查看机器人运行状态",
)
async def bot_command_handler(to: SendTo, message: str = "", message_obj=None):
    """
    显示机器人运行状态
    """
    if not hasattr(BotInfo, 'start_time'):
        sender.send_msg(to, "机器人启动时间未记录")
        return

    # 获取状态消息
    status_msg = get_status_msg()

    sender.send_msg(to, status_msg)

def get_status_msg():
    """
    获取机器人状态消息
    """
    # 基础信息
    uptime_seconds = int(time.time() - BotInfo.start_time)
    uptime = timedelta(seconds=uptime_seconds)
    days = uptime.days
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    seconds = uptime.seconds % 60

    # 获取消息统计
    with make_db_session() as session:
        msg_stats = session.query(MessageStats).first()
        if not msg_stats:
            msg_stats = MessageStats(
                total_messages=0,
                command_messages=0,
                group_messages=0,
                private_messages=0,
                last_updated=datetime.now()
            )
            session.add(msg_stats)
            session.commit()

        # 获取命令使用统计
        cmd_stats = session.query(CommandStats).order_by(CommandStats.use_count.desc()).limit(5).all()

    # 获取系统信息
    sys_info = get_system_info()
    net_info = get_network_info()
    project_memory = get_project_memory_usage()
    project_disk = get_project_disk_usage()

    # 构建状态消息
    status_msg = f"🤖 机器人状态\n"
    status_msg += f"🔗 机器人ID：{BotInfo.id}\n"
    status_msg += f"🔗 机器人名称：{BotInfo.name}\n"
    status_msg += f"📅 启动时间：{datetime.fromtimestamp(BotInfo.start_time).strftime('%Y-%m-%d %H:%M:%S')}\n"
    status_msg += f"⏱️ 运行时间：{days}天 {hours}小时 {minutes}分钟 {seconds}秒\n\n"

    # 消息统计
    status_msg += f"📊 消息统计\n"
    status_msg += f"📨 总消息数：{msg_stats.total_messages}\n"
    status_msg += f"📝 命令消息：{msg_stats.command_messages}\n"
    status_msg += f"👥 群消息数：{msg_stats.group_messages}\n"
    status_msg += f"👤 私聊消息：{msg_stats.private_messages}\n\n"

    # 命令使用统计
    status_msg += f"📈 热门命令（Top 5）\n"
    for cmd in cmd_stats:
        status_msg += f"• {cmd.command_name}: {cmd.use_count}次\n"
    status_msg += "\n"

    # 系统资源
    status_msg += f"💻 系统资源\n"
    status_msg += f"CPU: {sys_info['cpu']['percent']}% ({sys_info['cpu']['count']}核)\n"
    status_msg += f"内存: {sys_info['memory']['percent']}% ({sys_info['memory']['used'] / 1024 / 1024 / 1024:.1f}GB/{sys_info['memory']['total'] / 1024 / 1024 / 1024:.1f}GB)\n"
    status_msg += f"磁盘: {sys_info['disk']['percent']}% ({sys_info['disk']['used'] / 1024 / 1024 / 1024:.1f}GB/{sys_info['disk']['total'] / 1024 / 1024 / 1024:.1f}GB)\n\n"

    # 项目资源使用情况
    status_msg += f"📦 项目资源使用\n"
    status_msg += f"内存占用: {project_memory['rss'] / 1024 / 1024:.1f}MB ({project_memory['percent']:.1f}%)\n"
    status_msg += f"项目大小: {project_disk['total'] / 1024 / 1024:.1f}MB\n"
    status_msg += f"数据目录: {project_disk['data_dir'] / 1024 / 1024:.1f}MB\n\n"

    # 网络状态
    status_msg += f"🌐 网络状态\n"
    status_msg += f"发送: {net_info['bytes_sent'] / 1024 / 1024:.1f}MB\n"
    status_msg += f"接收: {net_info['bytes_recv'] / 1024 / 1024:.1f}MB"

    return status_msg


@mcp_server.tool("bot_info")
def bot_info_tool():
    """
    获取机器人信息
    """     
    return get_status_msg()
