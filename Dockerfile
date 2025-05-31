FROM python:3.12-bullseye AS builder
WORKDIR /app
COPY requirements.txt .
# 为 pip 配置镜像源
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ --trusted-host pypi.tuna.tsinghua.edu.cn
RUN pip install playwright && playwright install chromium

FROM python:3.12-bullseye
LABEL authors="Ashesttt"

# 安装 Chromium 依赖
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libgobject-2.0-0 \
    libnss3 \
    libnssutil3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgio2.0-0 \
    libexpat1 \
    libatspi0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libxcb1 \
    libxkbcommon0 \
    libasound2

WORKDIR /wechatter
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright
COPY . /wechatter

ENV LOGURU_COLORIZE=True
ENV WECHATTER_LOG_LEVEL=INFO

EXPOSE 4000

CMD ["python3", "-m", "wechatter"]
