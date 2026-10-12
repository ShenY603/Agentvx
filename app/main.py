"""入口：装配 graph + 启动企微长连接。"""

from app.bot import build_client, register_handlers
from app.graph import build_graph


def main() -> None:
    graph = build_graph()
    client = build_client()
    register_handlers(client, graph)
    client.run()  # 阻塞：内部创建事件循环、connect、run_forever


if __name__ == "__main__":
    main()
