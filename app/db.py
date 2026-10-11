"""业务表读写：messages / request_log 与 msgid 幂等排重。"""

import psycopg

from app.config import settings


def _connect() -> psycopg.Connection:
    return psycopg.connect(settings.database_url)


def insert_message(
    msgid: str | None,
    userid: str | None,
    chatid: str | None,
    chattype: str,
    role: str,
    content: str,
) -> None:
    """写入一条对话记录；msgid 已存在则跳过（幂等）。"""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (msgid, userid, chatid, chattype, role, content)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (msgid) DO NOTHING
            """,
            (msgid, userid, chatid, chattype, role, content),
        )


def message_exists(msgid: str) -> bool:
    """判断某条企微消息是否已处理过。"""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM messages WHERE msgid = %s LIMIT 1", (msgid,))
        return cur.fetchone() is not None


def get_answer_by_msgid(msgid: str) -> str | None:
    """排重命中时，取回该消息对应的历史回答。"""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT content FROM messages WHERE msgid = %s AND role = 'assistant' LIMIT 1",
            (msgid,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def insert_request_log(chatid: str | None, status: str, latency_ms: int, detail: str) -> None:
    """写入请求日志。"""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO request_log (chatid, status, latency_ms, detail) VALUES (%s, %s, %s, %s)",
            (chatid, status, latency_ms, detail),
        )
