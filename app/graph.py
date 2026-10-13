"""LangGraph 图：agent 循环（LLM 决策调用工具 → 执行 → 再决策），带 checkpoint。"""

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg_pool import ConnectionPool

from app.config import settings
from app.llm import build_llm
from app.state import GraphState
from app.tools import TOOLS, run_tool

_SYSTEM_PROMPT = (
    "你是一个知识问答助手，可以调用工具来回答问题。\n"
    "- 知识/文档类问题：必须先调用 search_knowledge_base 检索文档库，再基于结果作答并标注引用。\n"
    "- 实时信息/新闻/网页类问题：调用 web_search 搜索网页，基于搜索结果作答并标注来源。\n"
    "- 询问天气：调用 get_weather（用户未指定城市时可不传 city，用默认城市）。\n"
    "- 数学计算：必须调用 calculator 计算。\n"
    "- 询问当前时间：必须调用 get_current_time 获取实时时间。\n"
    "重要：每次回答都必须重新调用对应工具获取最新结果，"
    "禁止直接复述对话历史里出现过的旧答案或旧时间。\n"
    "如果检索结果没有相关内容，如实回答「资料中没有相关内容」。"
)


def _agent(state: GraphState) -> dict:
    """LLM 节点：决定回答问题或调用工具。"""
    llm = build_llm().bind_tools(TOOLS)
    messages = [SystemMessage(content=_SYSTEM_PROMPT), *state["messages"]]
    response = llm.invoke(messages)
    result: dict = {"messages": [response]}
    # 新一轮用户提问时清空来源，避免上一轮来源串到本轮
    if isinstance(state["messages"][-1], HumanMessage):
        result["sources"] = []
    return result


def _tools(state: GraphState) -> dict:
    """执行被调用的工具，并回填检索来源。"""
    last = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    sources = list(state.get("sources", []))
    for call in last.tool_calls:
        text, new_sources = run_tool(call["name"], call.get("args") or {})
        tool_messages.append(ToolMessage(content=text, tool_call_id=call["id"]))
        if new_sources:
            sources = list(dict.fromkeys(sources + new_sources))
    return {"messages": tool_messages, "sources": sources}


def _should_continue(state: GraphState) -> str:
    """agent 之后：还有工具调用则继续，否则结束。"""
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def build_graph():
    """构造并编译 agent 图（含 PostgresSaver checkpoint）。"""
    graph = StateGraph(GraphState)
    graph.add_node("agent", _agent)
    graph.add_node("tools", _tools)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    pool = ConnectionPool(
        settings.database_url,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return graph.compile(checkpointer=checkpointer)
