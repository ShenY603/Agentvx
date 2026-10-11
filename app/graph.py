"""LangGraph 图：retrieve → generate，带引用来源，checkpoint 持久化。"""

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from psycopg_pool import ConnectionPool

from app.config import settings
from app.llm import build_llm
from app.state import GraphState
from app.vector_store import search

_SYSTEM_PROMPT = (
    "你是一个知识问答助手。请只依据下面给出的资料回答用户问题，"
    "并在引用处用 [编号] 标注。如果资料中没有相关信息，"
    "请直接回答：这个问题资料中没有相关内容。"
)


def _format_context(docs: list[Document]) -> str:
    return "\n\n".join(f"[{i}] {doc.page_content}" for i, doc in enumerate(docs, start=1))


def _extract_sources(docs: list[Document]) -> list[str]:
    sources: list[str] = []
    for doc in docs:
        source = doc.metadata.get("source", "未知来源")
        page = doc.metadata.get("page")
        sources.append(f"{source}" + (f" 第{page}页" if page else ""))
    return sources


def _retrieve(state: GraphState) -> dict:
    question = str(state["messages"][-1].content)
    docs = search(question, k=settings.top_k)
    return {"context": docs, "sources": _extract_sources(docs)}


def _generate(state: GraphState) -> dict:
    question = str(state["messages"][-1].content)
    context_text = _format_context(state.get("context", []))
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(
            content=f"资料：\n{context_text}\n\n用户问题：{question}\n\n请基于资料回答并标注引用。"
        ),
    ]
    response = build_llm().invoke(messages)
    return {"answer": response.content, "messages": [response]}


def build_graph():
    """构造并编译图（含 PostgresSaver checkpoint）。"""
    graph = StateGraph(GraphState)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("generate", _generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)

    pool = ConnectionPool(
        settings.database_url,
        open=True,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return graph.compile(checkpointer=checkpointer)
