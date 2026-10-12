FROM python:3.12-slim

WORKDIR /app

# 先装依赖（单独 COPY requirements，利用 Docker 层缓存；国内走清华 pip 镜像加速）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 构建时预下载 embedding 模型（国内走镜像，一次性）
ENV HF_ENDPOINT=https://hf-mirror.com
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"

# 拷贝应用代码
COPY app ./app
COPY sql ./sql

# 运行时离线加载模型（已打进镜像）；不缓冲 stdout，日志实时可见
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
