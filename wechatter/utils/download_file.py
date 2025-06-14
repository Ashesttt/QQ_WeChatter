from wechatter.utils import check_and_create_folder


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

    try:
        # 首先尝试使用 requests 下载文件
        response = requests.get(file_url, stream=True)
        response.raise_for_status()

        # 保存文件
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        logger.info(f"文件下载成功：{file_name}")
        return file_path

    except Exception as e:
        logger.warning(f"使用 requests 下载失败，尝试使用 curl：{str(e)}")
        try:
            # 使用 curl 命令下载文件
            curl_command = ['curl', '-L', '-o', file_path, file_url]
            logger.debug(f"执行 curl 命令: {' '.join(curl_command)}")
            result = subprocess.run(curl_command, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"使用 curl 下载成功：{file_name}")
                logger.debug(f"curl 连接详情:\n{result.stderr}")
                return file_path
            else:
                error_msg = f"curl 下载失败: {result.stderr}"
                logger.error(error_msg)
                raise ValueError(error_msg)

        except Exception as curl_error:
            error_msg = f"所有下载方法都失败：\n1. requests 错误: {str(e)}\n2. curl 错误: {str(curl_error)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
