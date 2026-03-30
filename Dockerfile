FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY src/ ./src/
COPY knowledge/ ./knowledge/
COPY prometheus.yml ./prometheus.yml

# 工作目录切换到 src
WORKDIR /app/src

# 暴露端口
EXPOSE 8081

# 启动命令
CMD ["python", "discord_bot_final.py"]

