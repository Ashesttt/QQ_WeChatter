from wechatter.utils import check_and_create_folder
import os
from loguru import logger

def download_file(file_name: str, file_url: str, download_dir: str) -> str:
    """
    下载文件到指定目录
    
    :param file_name: 文件名
    :param file_url: 文件URL
    :param download_dir: 下载目录
    :return: 下载后的文件完整路径
    :raises ValueError: 当所有下载方法都失败时抛出
    """
    import requests
    import subprocess
    from loguru import logger

    # 构建完整的文件路径
    file_path = download_dir + file_name

    # 如果file_url没有请求头，则添加https://
    if not file_url.startswith("https://"):
        file_url = "https://" + file_url
    
    download_successful = False
    downloaded_file_path = ""

    try:
        logger.info(f"尝试使用 requests 下载文件：{file_name} from {file_url}")
        # 首先尝试使用 requests 下载文件
        response = requests.get(file_url, stream=True)
        response.raise_for_status()

        # 保存文件
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        download_successful = True
        downloaded_file_path = file_path
        logger.info(f"requests 下载成功：{file_name}, 原始大小：{get_file_size_formatted(file_path)}")

    except requests.exceptions.RequestException as e:
        logger.warning(f"使用 requests 下载失败，尝试使用 curl：{str(e)}")
        #删除可能已部分下载的文件
        if os.path.exists(file_path):
            os.remove(file_path)

        try:
            logger.info(f"尝试使用 下载文件：{file_name} from {file_url}")
            # 使用 curl 命令下载文件
            curl_command = ['curl', '-L', '-o', file_path, file_url]
            logger.debug(f"执行 curl 命令: {' '.join(curl_command)}")
            result = subprocess.run(curl_command, capture_output=True, text=True, check=True) # check=True: 如果返回非零状态码则抛出CalledProcessError

            download_successful = True
            downloaded_file_path = file_path
            logger.info(f"curl 下载成功：{file_name}, 原始大小为：{get_file_size_formatted(file_path)}")
            if result.stderr:
                logger.error(f"curl 错误：{result.stderr}")
            if result.stdout:
                logger.info(f"curl 输出：{result.stdout}")
        
        except subprocess.CalledProcessError as curl_e:
            error_msg = f"curl 下载失败 （返回码 {curl_e.returncode}），错误信息：{str(curl_e.stderr)}"
            logger.error(error_msg)
            # 删除可能已部分下载的文件
            if os.path.exists(file_path):
                os.remove(file_path)
            raise ValueError(error_msg)
        except FileNotFoundError:
            error_msg = "curl 命令未找到。请检查是否已安装。"
            logger.error(error_msg)
            raise ValueError(error_msg)
        except Exception as curl_error:
            error_msg = f"curl 下载时发生未知错误：{curl_error}"
            logger.error(error_msg)
            # 删除可能已部分下载的文件
            if os.path.exists(file_path):
                os.remove(file_path)
            raise ValueError(error_msg)
    except Exception as general_error:
        error_msg = f"下载文件时发生未知错误：{str(general_error)}"
        logger.error(error_msg)
        # 删除可能已部分下载的文件
        if os.path.exists(file_path):
            os.remove(file_path)
        raise ValueError(error_msg)
    
    if download_successful:
        # 尝试判断是否为图片并进行压缩使用
        # 使用 mimetypes 辅助判断，但最终以Pillow 能否打开为准
        import mimetypes
        mime_type, _ = mimetypes.guess_type(downloaded_file_path)
        if mime_type and mime_type.startswith("image/"):
            logger.info(f"文件 {file_name} 可能是图片 ({mime_type})，尝试进行压缩...")
            
            # 压缩后的文件路径，可以考虑使用不同的文件名，例如添加 _compressed 后缀
            # 这里为了简化，直接覆盖原文件，或者保存到临时文件再替换
            # 为了避免覆盖失败导致原文件丢失，我们先保存到临时文件，成功后再替换
            temp_compressed_path = os.path.join(download_dir, f"{os.path.splitext(file_name)[0]}_compressed{os.path.splitext(file_name)[1]}")
            
            final_path_after_compression = compress_image(
                image_path=downloaded_file_path, 
                output_path=temp_compressed_path,
                max_dimension=1920, # 你可以根据需求调整这些参数
                quality=80 # 默认质量，可以根据需求调整
            )
            
            if final_path_after_compression == temp_compressed_path:
                # 如果压缩成功，删除原始文件，并重命名压缩后的文件为原始文件名
                # 这样外部调用者拿到的路径就是压缩后的文件路径，且文件名不变
                os.remove(downloaded_file_path)
                os.rename(temp_compressed_path, downloaded_file_path)
                logger.info(f"图片压缩并替换成功。最终路径：{downloaded_file_path}")
                return downloaded_file_path
            else:
                # 压缩失败或不是图片，返回原始下载路径
                if os.path.exists(temp_compressed_path): # 如果有临时文件，删除它
                    os.remove(temp_compressed_path)
                logger.warning(f"图片 {file_name} 压缩失败或未进行压缩，返回原始下载路径：{downloaded_file_path}")
                return downloaded_file_path
        else:
            logger.info(f"文件 {file_name} 不是图片 ({mime_type if mime_type else '未知类型'})，跳过压缩。")
            return downloaded_file_path
    else:
        # 理论上这里不会被执行，因为下载失败会抛出异常
        raise ValueError("文件下载失败，未能获取文件路径。")



def get_file_size_formatted(file_path: str) -> str:
    """ 
    获取文件的大小并格式化为易读KB、MB为单位的格式
    """
    file_size_bytes = os.path.getsize(file_path)
    if file_size_bytes >= (1024 * 1024):
        file_size_value = file_size_bytes / (1024 * 1024)
        file_size_unit = "MB"
    else:
        file_size_value = file_size_bytes / 1024
        file_size_unit = "KB"
    return f"{file_size_value:.3f} {file_size_unit}"


def compress_image(
    image_path: str,
    output_path: str,
    max_dimension: int = 1920, # 最大边长，如果图片任一边长超过此值，则按比例缩小
    quality: int = 85,         # JPEG/WebP 压缩质量 (0-100)
    optimize: bool = True      # PNG 优化
) -> str:
    """
    压缩图片文件。
    
    :param image_path: 原始图片文件的完整路径。
    :param output_path: 压缩后图片保存的完整路径。
    :param max_dimension: 图片最大边长，如果图片尺寸超过此值，将按比例缩小。
    :param quality: JPEG/WebP 压缩质量 (0-100)，数字越小压缩率越高，质量越低。
    :param optimize: 是否对 PNG 图像进行优化。
    :return: 压缩后图片的完整路径，如果不是图片或压缩失败则返回原始路径。
    """
    from PIL import Image, UnidentifiedImageError
    try:
        # 尝试打开图片
        with Image.open(image_path) as img:
            original_width, original_height = img.size
            original_format = image_path.split(".")[-1] # 获取原始图片格式

            logger.info(f"尝试压缩图片：{os.path.basename(image_path)}，原始尺寸：{original_width}x{original_height}，格式：{original_format}")

            # 1. 尺寸调整
            if max(original_width, original_height) > max_dimension:
                ratio = max_dimension / max(original_width, original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                img = img.resize((new_width, new_height), Image.LANCZOS) # 使用高质量的缩放算法
                logger.info(f"图片尺寸调整为：{new_width}x{new_height}")

            # 2. 格式转换与质量压缩
            # 确定输出格式。通常，如果不是 JPEG，可以转换为 JPEG 以获得更好的压缩比（如果不需要透明度）
            # 或者保持原格式进行压缩。这里我们优先保持原格式，但对JPEG进行质量压缩。
            output_format = original_format if original_format else "JPEG" # 默认为JPEG
            
            # 如果是透明的PNG，转换为JPEG会丢失透明度，所以保持PNG
            if original_format == "png" and img.mode in ('RGBA', 'LA'):
                logger.info("PNG图片包含透明度，将保持PNG格式进行优化。")
                img.save(output_path, format="PNG", optimize=optimize)
            elif original_format in ["JPEG", "JPG", "jpeg", "jpg"]:
                logger.info(f"JPEG图片，使用质量 {quality} 进行压缩。")
                img.save(output_path, format="JPEG", quality=quality, optimize=optimize)
            elif original_format == "webp":
                logger.info(f"WebP图片，使用质量 {quality} 进行压缩。")
                img.save(output_path, format="WEBP", quality=quality)
            else:
                # 对于其他格式（如BMP, GIF等），尝试转换为JPEG或PNG
                logger.warning(f"图片格式 {original_format} 不常见，尝试转换为JPEG进行压缩。")
                # 转换为RGB模式以保存为JPEG，防止模式不兼容
                if img.mode in ('RGBA', 'LA'): # 如果有透明度，转换为RGB会丢失透明度
                    logger.warning("非JPEG图片有透明度，转换为JPEG会丢失透明度。")
                    img = img.convert('RGB')
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                img.save(output_path, format="JPEG", quality=quality, optimize=optimize)
                output_format = "JPEG"

            logger.info(f"图片压缩成功，保存至：{output_path}，新大小：{get_file_size_formatted(output_path)}")
            return output_path

    except UnidentifiedImageError:
        logger.info(f"文件 {os.path.basename(image_path)} 不是一个可识别的图片文件，跳过压缩。")
        return image_path
    except Exception as e:
        logger.error(f"压缩图片 {os.path.basename(image_path)} 时发生错误: {e}")
        return image_path # 压缩失败，返回原始路径
