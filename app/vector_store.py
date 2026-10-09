"""PGVector 封装：文档块写入与相似检索，隔离存储细节。"""

from langchain_core.documents import Document
from langchain_postgres import PGVector

from app.config import settings
from app.embed import embed_query, get_embedding


def _sqlalchemy_url() -> str:
    """PGVector 走 SQLAlchemy，需显式指定 psycopg(v3) 驱动；DATABASE_URL 保持 libpq 格式。"""
    url = settings.database_url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def build_store() -> PGVector:
    """构造 PGVector 实例（collection 不存在时首次写入会自动建表）。"""
    return PGVector(
        embeddings=get_embedding(),
        collection_name=settings.collection_name,
        connection=_sqlalchemy_url(),
        use_jsonb=True,
    )


def add_documents(documents: list[Document]) -> None:
    """写入文档块（内部会批量向量化）。"""
    if not documents:
        return
    build_store().add_documents(documents)


def search(query: str, k: int | None = None) -> list[Document]:
    """按查询检索最相关的 top-k 文档块，返回带 metadata（来源/页码）的 Document。"""
    vector = embed_query(query)
    return build_store().similarity_search_by_vector(vector, k=k or settings.top_k)


def delete_collection() -> None:
    """清空当前 collection（--reset 用）。"""
    build_store().delete_collection()
