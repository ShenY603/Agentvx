"""知识问答 agent 应用包。"""

import os

# 国内服务器直连 huggingface.co 会卡住：下载走国内镜像、运行时默认离线加载（模型已缓存）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
