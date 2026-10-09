"""本地 embedding：封装 bge-m3，文档向量化与查询向量化共用。"""

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from app.config import settings

# bge 系列推荐给查询侧加前缀、文档侧不加，可小幅提升中文检索效果
_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


@lru_cache(maxsize=1)
def get_embedding() -> HuggingFaceEmbeddings:
    """进程内单例，模型只加载一次。"""
    return HuggingFaceEmbeddings(
        model_name=settings.embedding_model,
        encode_kwargs={"normalize_embeddings": True},
    )


def embed_query(text: str) -> list[float]:
    """对查询文本生成向量（自动带查询前缀）。"""
    return get_embedding().embed_query(_QUERY_INSTRUCTION + text)
