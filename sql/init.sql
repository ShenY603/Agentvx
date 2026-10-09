-- 知识问答 agent：数据库初始化
-- 由 docker-entrypoint-initdb.d 在 PG 首次启动时自动执行（pgvector 镜像）

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS messages (
    id         BIGSERIAL PRIMARY KEY,
    msgid      TEXT UNIQUE,              -- 企微消息 id，排重
    userid     TEXT,
    chatid     TEXT,
    chattype   TEXT,                     -- single / group
    role       TEXT NOT NULL,            -- 'user' / 'assistant'
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_userid ON messages(userid);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

CREATE TABLE IF NOT EXISTS request_log (
    id         BIGSERIAL PRIMARY KEY,
    chatid     TEXT,
    status     TEXT,                     -- 'ok' / 'error' / 'timeout'
    latency_ms INT,
    detail     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
