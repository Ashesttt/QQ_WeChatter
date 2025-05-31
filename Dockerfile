FROM python:3.12-slim-bullseye AS build
LABEL authors="Ashesttt"

WORKDIR /wechatter

ADD . /wechatter

RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ --trusted-host pypi.tuna.tsinghua.edu.cn

# 使 loguru 支持颜色输出
ENV LOGURU_COLORIZE=True
# 设置日志级别
ENV WECHATTER_LOG_LEVEL=INFO

EXPOSE 4000

CMD ["python3", "-m", "wechatter"]
