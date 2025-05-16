import os
import requests
import uuid
import shutil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from loguru import logger

from wechatter.utils import get_abs_path, join_path, check_and_create_folder
from wechatter.config import config

router = APIRouter()

def upload_image(image_path: str):
    """
    上传本地图片到服务器
    :param image_path: 图片的绝对路径
    :return: 图片访问URL
    """
    # 检查文件是否存在
    if not os.path.exists(image_path):
        logger.error(f"图片文件不存在: '{image_path}'")
        raise ValueError(f"图片文件不存在: '{image_path}'")
    
    # 检查文件是否为图片（简单检查文件扩展名）
    _, file_extension = os.path.splitext(image_path)
    if file_extension.lower() not in ['.jpg', '.png']:
        logger.error(f"文件不是图片: '{image_path}'")
        raise ValueError(f"文件不是图片: '{image_path}'")
    
    # 生成唯一文件名
    file_name = f"{str(uuid.uuid4())}{file_extension}"
    dest_path = join_path("data/upload_image", file_name)
    abs_dest_path = get_abs_path(dest_path)
    
    # 复制文件
    try:
        shutil.copy2(image_path, abs_dest_path)
        logger.info(f"图片已上传并保存至 '{abs_dest_path}'")
        
        # 获取端口号
        port = config["wechatter_port"]
        ip = requests.get('https://checkip.amazonaws.com').text.strip()
        
        # 返回可访问URL
        url = f"http://ip:{port}/api/image/{file_name}"
        return url
    
    except Exception as e:
        logger.error(f"处理图片时出错：{str(e)}")
        raise ValueError(f"处理图片失败：{str(e)}")

@router.get("/api/image/{image_name}")
async def get_image(image_name: str):
    """
    获取图片API
    :param image_name: 图片文件名
    :return: 图片文件
    """
    # 构建图片路径
    image_path = join_path("data/upload_image", image_name)
    abs_image_path = get_abs_path(image_path)
    
    # 检查文件是否存在
    if not os.path.exists(abs_image_path):
        raise HTTPException(status_code=404, detail="图片不存在")
    
    # 返回图片文件
    return FileResponse(abs_image_path)
