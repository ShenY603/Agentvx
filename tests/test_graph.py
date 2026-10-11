"""graph 集成测试：需要 PG + DeepSeek key + 已摄入的文档。"""

from langchain_core.messages import HumanMessage

from app.graph import build_graph


def test_retrieve_and_generate_returns_cited_answer() -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-thread"}}
    result = graph.invoke(
        {"messages": [HumanMessage(content="数据库用什么？")]},
        config=config,
    )
    assert isinstance(result["answer"], str)
    assert result["answer"].strip()
    assert result["sources"]
