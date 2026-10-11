"""生成模型：DeepSeek（OpenAI 兼容接口）。"""

from langchain_deepseek import ChatDeepSeek

from app.config import settings


def build_llm() -> ChatDeepSeek:
    """构造 DeepSeek 聊天模型。"""
    return ChatDeepSeek(
        model="deepseek-chat",
        api_key=settings.deepseek_api_key,
        openai_api_base="https://api.deepseek.com",
        temperature=0.3,
        max_retries=2,
        timeout=60,
    )
