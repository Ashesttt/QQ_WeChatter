import psutil
import platform
import os
from datetime import datetime

def get_system_info():
    """获取系统资源使用情况"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    return {
        'cpu': {
            'percent': cpu_percent,
            'count': psutil.cpu_count()
        },
        'memory': {
            'total': memory.total,
            'used': memory.used,
            'percent': memory.percent
        },
        'disk': {
            'total': disk.total,
            'used': disk.used,
            'percent': disk.percent
        }
    }

def get_network_info():
    """获取网络连接状态"""
    net_io = psutil.net_io_counters()
    return {
        'bytes_sent': net_io.bytes_sent,
        'bytes_recv': net_io.bytes_recv,
        'packets_sent': net_io.packets_sent,
        'packets_recv': net_io.packets_recv
    }

def get_project_memory_usage():
    """获取项目内存使用情况"""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    
    return {
        'rss': memory_info.rss,  # 物理内存使用量
        'vms': memory_info.vms,  # 虚拟内存使用量
        'percent': process.memory_percent()  # 内存使用百分比
    }

def get_project_disk_usage():
    """获取项目磁盘使用情况"""
    project_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # 获取项目根目录
    total_size = 0
    
    # 遍历项目目录计算总大小
    for dirpath, dirnames, filenames in os.walk(project_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):  # 跳过符号链接
                total_size += os.path.getsize(fp)
    
    return {
        'total': total_size,  # 总大小（字节）
        'data_dir': get_data_dir_size()  # data目录大小
    }

def get_data_dir_size():
    """获取data目录大小"""
    data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
    if not os.path.exists(data_path):
        return 0
        
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(data_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    
    return total_size
