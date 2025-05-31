# 第一阶段：构建阶段
FROM python:3.12-alpine AS builder
WORKDIR /app
COPY requirements_docker.txt .
# 为 pip 配置镜像源
RUN pip install --no-cache-dir -r requirements_docker.txt -i https://pypi.tuna.tsinghua.edu.cn/simple/ --trusted-host pypi.tuna.tsinghua.edu.cn

# 第二阶段：最终运行阶段
FROM python:3.12-alpine
LABEL authors="Ashesttt"

WORKDIR /wechatter
# 从构建阶段复制安装的依赖
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
# 复制你的应用代码
COPY . /wechatter

# 使 loguru 支持颜色输出
ENV LOGURU_COLORIZE=True
# 设置日志级别
ENV WECHATTER_LOG_LEVEL=INFO

EXPOSE 4000

CMD ["python3", "-m", "wechatter"]
