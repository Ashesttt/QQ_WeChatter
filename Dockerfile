# 第一阶段：构建阶段
FROM python:3.12-slim-bullseye AS builder

WORKDIR /app

COPY requirements.txt .

# 为 pip 配置镜像源
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ --trusted-host pypi.tuna.tsinghua.edu.cn

# 安装 Playwright 浏览器。这会将浏览器下载到 /root/.cache/ms-playwright/
RUN playwright install chromium

# 第二阶段：最终运行阶段
FROM python:3.12-slim-bullseye

LABEL authors="Ashesttt"

# --- 关键修改开始 ---

# 1. 安装 Playwright 运行所需的系统依赖
# 这些是 Playwright 浏览器（如 Chromium）在 Linux 环境下运行所必需的库
# 根据 Playwright 官方文档和常见问题，这些是推荐的依赖
RUN apt-get update && apt-get install -y \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    libgconf-2-4 \
    libdrm-dev \
    libatspi2.0-0 \
    libcups2 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxtst6 \
    libappindicator1 \
    libevent-2.1-7 \
    libsecret-1-0 \
    libvulkan1 \
    libu2f-udev \
    fonts-noto-color-emoji \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /wechatter

# 2. 从构建阶段复制 Playwright 下载的浏览器到最终镜像
# Playwright 默认将浏览器下载到 ~/.cache/ms-playwright/
# 在 Docker 构建过程中，通常是 /root/.cache/ms-playwright/
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# 3. 设置环境变量，明确告诉 Playwright 浏览器缓存路径
ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

# --- 关键修改结束 ---

# 从构建阶段复制安装的 Python 依赖
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
# 复制你的应用代码
COPY . /wechatter

# 使 loguru 支持颜色输出
ENV LOGURU_COLORIZE=True
# 设置日志级别
ENV WECHATTER_LOG_LEVEL=INFO

EXPOSE 4000

CMD ["python3", "-m", "wechatter"]
