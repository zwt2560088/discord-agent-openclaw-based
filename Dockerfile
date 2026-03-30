# 基础镜像：Python 3.11 slim（轻量 + 兼容所有依赖）
FROM python:3.11-slim

# 1. 安装系统依赖：Tesseract OCR（识图核心）+ Pillow 依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 2. 设置工作目录
WORKDIR /app

# 3. 复制依赖清单并安装 Python 包
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 复制项目全部代码
COPY . .

# 5. 给启动脚本授权
RUN chmod +x bin/start_final_bot.sh

# 6. 非 root 用户运行（安全规范）
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# 7. 启动机器人
CMD ["bash", "bin/start_final_bot.sh"]

