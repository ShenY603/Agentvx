"""企微接入：wecom-aibot-python-sdk 长连接，收消息、排重、调 graph、回复。"""

import asyncio
import time

from aibot import WSClient, WSClientOptions
from langchain_core.messages import HumanMessage

from app.config import settings
from app.db import insert_message, insert_request_log, message_exists

_FALLBACK = "抱歉，暂时没查到相关资料～"


def build_client() -> WSClient:
    """构造企微智能机器人客户端。"""
    return WSClient(
        WSClientOptions(
            bot_id=settings.bot_id,
            secret=settings.bot_secret,
        )
    )


def _format_reply(answer: str, sources: list[str]) -> str:
    """把回答与引用来源拼成企微文本。"""
    if not sources:
        return answer
    lines = "\n".join(f"{i}. {src}" for i, src in enumerate(sources, start=1))
    return f"{answer}\n\n来源：\n{lines}"


def register_handlers(client: WSClient, graph) -> None:
    """注册消息/事件回调（graph 由调用方注入，保持解耦）。"""

    @client.on("authenticated")
    def on_authenticated():
        print("企微长连接鉴权成功")

    @client.on("message.text")
    async def on_text(frame):
        body = frame.get("body", {})
        text = ((body.get("text") or {}).get("content") or "").strip()
        if not text:
            return

        msgid = body.get("msgid")
        chattype = body.get("chattype") or "single"
        chatid = body.get("chatid")
        userid = (body.get("from") or {}).get("userid")

        # 幂等排重：同一条消息只处理一次（群聊 @机器人 由企微侧过滤，无需再判断）
        if msgid and message_exists(msgid):
            return

        thread_id = chatid or userid or "default"
        insert_message(msgid, userid, chatid, chattype, "user", text)

        start = time.monotonic()
        try:
            # 用线程池跑同步 graph.invoke，避免阻塞事件循环
            result = await asyncio.to_thread(
                graph.invoke,
                {"messages": [HumanMessage(content=text)]},
                {"configurable": {"thread_id": thread_id}},
            )
            answer = result.get("answer") or ""
            sources = result.get("sources") or []
            reply_text = _format_reply(answer, sources)
            status = "ok"
            detail = ""
        except Exception as exc:  # 任何异常都兜底，避免机器人无响应
            reply_text = _FALLBACK
            status = "error"
            detail = str(exc)

        latency_ms = int((time.monotonic() - start) * 1000)
        insert_message(None, userid, chatid, chattype, "assistant", reply_text)
        insert_request_log(chatid, status, latency_ms, detail)

        await client.reply(frame, {"msgtype": "text", "text": {"content": reply_text}})
