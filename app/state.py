"""Graph 状态定义。"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class GraphState(TypedDict):
    """LangGraph 图的状态。"""

    # 对话消息，add_messages 自动追加形成历史（含工具调用/结果）
    messages: Annotated[list[BaseMessage], add_messages]
    # 引用来源（文档名/页码，由检索工具回填）
    sources: list[str]
