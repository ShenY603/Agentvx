"""graph 集成测试：需要 PG + DeepSeek key + 已摄入的文档。"""

from langchain_core.messages import HumanMessage

from app.graph import build_graph


def test_agent_returns_answer_with_sources() -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-thread"}}
    result = graph.invoke(
        {"messages": [HumanMessage(content="根据文档，这个项目部署在哪里？")]},
        config=config,
    )
    messages = result.get("messages", [])
    assert messages
    answer = str(messages[-1].content)
    assert answer.strip()
    assert result.get("sources")
