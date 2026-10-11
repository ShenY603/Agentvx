"""Graph 状态定义。"""

from typing import Annotated, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    """LangGraph 图的状态。"""

    # 对话消息，add_messages 自动追加形成多轮历史
    messages: Annotated[list[BaseMessage], add_messages]
    # 检索到的文档块
    context: list[Document]
    # 引用来源（文档名/页码）
    sources: list[str]
    # 最终回答
    answer: str
