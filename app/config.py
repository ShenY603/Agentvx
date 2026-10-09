"""应用配置：从环境变量 / 项目根目录 .env 读取。"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录（app/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """集中管理配置，字段名对应同名环境变量（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 数据库
    database_url: str = "postgresql://postgres@127.0.0.1:5432/mydb"

    # 企微
    bot_id: str = ""
    bot_secret: str = ""

    # DeepSeek
    deepseek_api_key: str = ""

    # embedding 与检索
    embedding_model: str = "BAAI/bge-m3"
    collection_name: str = "knowledge"
    chunk_size: int = 600
    chunk_overlap: int = 120
    top_k: int = 4


settings = Settings()
