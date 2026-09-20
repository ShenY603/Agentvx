# 生活助手（企业微信智能机器人）实施方案

## Context（背景）

用户想做一个「生活助手」：接入企业微信，用户 @机器人 提问生活问题，系统给出合理正确的回答。技术栈明确要求 **C++ + Python**，数据库用**云服务器 Docker 容器里的 PostgreSQL**（已就绪）。

已确认的关键决策：

- **回答引擎**：DeepSeek API（OpenAI 兼容接口）
- **企微接入**：企业微信「智能机器人」→ API 接入 → **WebSocket 长连接模式**（官方推荐，无需备案域名/HTTPS）
- **PG 用途**：只存对话历史 + 日志（v1 不做 RAG/向量检索）
- **服务器**：腾讯云 Ubuntu（主机名 `VM-0-8-ubuntu`），已装 Docker 29.8 + PostgreSQL 17 容器（`postgres`，映射 `127.0.0.1:5432`）

## 可行性结论

**完全可行。** 唯一的技术难点是企微智能机器人的 WebSocket 长连接协议——官方只提供 Node.js 和 Python SDK（[aibot-node-sdk](https://github.com/WecomTeam/aibot-node-sdk)、[wecom-aibot-python-sdk](https://pypi.org/project/wecom-aibot-python-sdk/)），**没有 C++ SDK**。若在 C++ 里手写这套协议（鉴权握手、心跳、事件帧解析、回复帧）成本很高且易错。

因此采用下面的分工，让两种语言各用在最合适的地方。

## 架构总览

```
企微用户 @机器人 提问
        │  (WebSocket 长连接，wss://openws.work.weixin.qq.com)
        ▼
┌─ Python 接入服务 ─────────────────────────────┐
│  wecom-aibot-python-sdk 维持长连接、收发消息      │
│  收到问题 → HTTP POST 转发给 C++ 服务             │
└───────────────────┬──────────────────────────┘
                    │  POST http://127.0.0.1:8080/ask  {"question": "...", "userid": "...", "chatid": "..."}
                    ▼
┌─ C++ 业务服务 ────────────────────────────────┐
│  cpp-httplib HTTP 服务（端口 8080）             │
│  1) 解析问题                                     │
│  2) 调用 DeepSeek API 生成回答（cpp-httplib 客户端）│
│  3) 写 PostgreSQL（libpqxx）                     │
│  4) 返回 {"answer": "..."}                       │
└───────────────────┬──────────────────────────┘
                    │  返回回答
                    ▼
┌─ Python 接入服务 ─────────────────────────────┐
│  通过 SDK 回复企微（文本回复，可后续加流式）         │
└──────────────────────────────────────────────┘
        │
        ▼
   用户在企微看到回答
```

## C++ / Python 分工（及理由）

| 语言 | 职责 | 理由 |
|------|------|------|
| **Python** | 企微 WebSocket 长连接接入（收发消息、回复） | 有官方 SDK，免去手写私有协议；异步/流式生态成熟 |
| **C++** | 核心业务服务：调 DeepSeek、读写 PG、排重/日志 | C++ 擅长高性能后端；体现「用 C++ 做核心逻辑」 |

两服务通过**本机 HTTP**（`127.0.0.1:8080`）通信，简单、易调试。

## 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| C++ HTTP 服务/客户端 | [cpp-httplib](https://github.com/yhirose/cpp-httplib) | 单头文件，需 OpenSSL（调 DeepSeek 的 HTTPS） |
| C++ JSON | [nlohmann/json](https://github.com/nlohmann/json) | 单头文件 |
| C++ 访问 PG | [libpqxx](https://github.com/jtv/libpqxx) | 官方 libpq 的现代 C++ 封装 |
| Python 企微接入 | `wecom-aibot-python-sdk` | 官方 Python SDK，asyncio 长连接 |
| Python HTTP 客户端 | `httpx` / `aiohttp` | SDK 异步环境下转发请求 |
| 构建 | CMake | 跨 Windows(MSYS2) 与 Ubuntu 一致 |
| 部署 | Docker Compose | 三容器：postgres + cpp + python，内部网络 |

## 目录结构

```
life-assistant/
├── docker-compose.yml
├── README.md
├── sql/
│   └── init.sql                # 建表语句
├── cpp/                        # C++ 业务服务
│   ├── CMakeLists.txt
│   ├── third_party/
│   │   ├── httplib.h
│   │   └── json.hpp
│   └── src/
│       ├── main.cpp            # HTTP 服务入口，路由 /ask、/health
│       ├── config.h/.cpp       # 读环境变量（DEEPSEEK_API_KEY、DATABASE_URL、PORT）
│       ├── llm.h/.cpp          # 调 DeepSeek /chat/completions
│       ├── db.h/.cpp           # libpqxx 读写 PG
│       └── log.h               # 简单日志
└── python/                     # 企微接入服务
    ├── main.py                 # 长连接 + 消息处理 + 转发 C++ + 回复
    ├── requirements.txt
    └── .env.example
```

## 组件详细设计

### 1. PostgreSQL 表结构（`sql/init.sql`）

在已有 `mydb`（或新建库）中执行：

```sql
CREATE TABLE IF NOT EXISTS messages (
    id         BIGSERIAL PRIMARY KEY,
    msgid      TEXT UNIQUE,              -- 企微消息 id，用于排重
    userid     TEXT,                     -- 提问用户
    chatid     TEXT,                     -- 会话 id（群聊才有）
    chattype   TEXT,                     -- single / group
    role       TEXT NOT NULL,            -- 'user' / 'assistant'
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_userid ON messages(userid);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

CREATE TABLE IF NOT EXISTS request_log (
    id         BIGSERIAL PRIMARY KEY,
    path       TEXT,
    status     INT,
    latency_ms INT,
    detail     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 2. C++ 业务服务（核心）

- 依赖：`cpp-httplib`、`nlohmann/json`、`libpqxx`、OpenSSL。
- 环境变量（部署时注入）：
  - `DEEPSEEK_API_KEY`（必填）
  - `DATABASE_URL`，如 `postgresql://postgres:密码@postgres:5432/mydb`
  - `PORT`（默认 8080）
- 路由：
  - `GET /health` → 返回 `{"status":"ok"}`（容器健康检查）
  - `POST /ask` → 入参 `{"question","userid","chatid","chattype","msgid"}`；内部流程：
    1. 若 `msgid` 已存在于 `messages` 表则直接返回已有回答（幂等排重）
    2. 插入一条 `role='user'` 记录
    3. 调 DeepSeek 生成回答（见下）
    4. 插入 `role='assistant'` 记录 + 写 `request_log`
    5. 返回 `{"answer": "...", "errmsg": "ok"}`
- **DeepSeek 调用**（`llm.cpp`）：POST `https://api.deepseek.com/chat/completions`，Header `Authorization: Bearer <key>`，body：
  ```json
  {
    "model": "deepseek-chat",
    "messages": [
      {"role": "system", "content": "你是一个生活助手，用简洁准确的中文回答日常生活问题。"},
      {"role": "user", "content": "<question>"}
    ],
    "stream": false
  }
  ```
  取 `choices[0].message.content`。超时建议 60s。

### 3. Python 接入服务（企微长连接）

- 依赖：`wecom-aibot-python-sdk`、`httpx`。
- 配置：`BOT_ID`、`BOT_SECRET`（企微后台创建智能机器人后获得）、`CPP_SERVICE_URL=http://127.0.0.1:8080`。
- 流程：
  1. 用 SDK 建立到 `wss://openws.work.weixin.qq.com` 的长连接并鉴权（Bot ID + Secret）。
  2. 收到消息事件：仅处理 `msgtype == "text"`，取 `text.content`（群聊中建议先判断是否 @了机器人）。
  3. `httpx` POST 到 C++ `/ask`，带上 userid/chatid/msgid。
  4. 拿到 `answer`，用 SDK 的回复接口发回企微（v1 用普通文本回复；后续可换流式，官方文档 [流式消息回复](https://developer.work.weixin.qq.com/document/path/101031)）。
- 异常处理：C++ 超时/失败时回复用户一条固定兜底文案（如「抱歉，暂时没想好怎么回答～」）。

## 企微接入步骤（前置条件，需用户操作）

1. 注册/登录企业微信，进入管理后台（**智能机器人功能通常要求认证企业**，需先确认账号是否已认证）。
2. 「应用管理 / 智能机器人」→ 创建机器人 → 选择 **API 接入（调用自有模型）** → **长连接模式**。
3. 复制 **Bot ID** 与 **Secret**（填入 Python 服务环境变量）。
4. 参考官方文档：
   - 智能机器人总览：https://developer.work.weixin.qq.com/document/path/101039
   - 接收消息：https://developer.work.weixin.qq.com/document/path/100719
   - 流式消息回复：https://developer.work.weixin.qq.com/document/path/101031
   - Python SDK：https://pypi.org/project/wecom-aibot-python-sdk/
   - Node SDK（协议参考）：https://github.com/WecomTeam/aibot-node-sdk
5. DeepSeek 开放平台注册并创建 API Key（https://platform.deepseek.com ）。

## 部署（docker-compose.yml）

三服务同处一个内部网络，PG 不暴露公网：

```yaml
services:
  postgres:
    image: postgres:17
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${PG_PASSWORD}
      POSTGRES_DB: mydb
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./sql/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    restart: unless-stopped
    # 不映射端口到宿主机，仅内部网络可访问

  cpp:
    build: ./cpp
    environment:
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
      DATABASE_URL: postgresql://postgres:${PG_PASSWORD}@postgres:5432/mydb
      PORT: "8080"
    depends_on: [postgres]
    restart: unless-stopped

  python:
    build: ./python
    environment:
      BOT_ID: ${BOT_ID}
      BOT_SECRET: ${BOT_SECRET}
      CPP_SERVICE_URL: http://cpp:8080
    depends_on: [cpp]
    restart: unless-stopped

volumes:
  pgdata:
```

> 说明：现有独立 PG 容器里的 `mydb` 基本是空库，可改为由 compose 统一管理（更干净）。若想复用现有容器，则去掉 compose 里的 postgres 服务，把 `DATABASE_URL` 的 host 指向宿主机地址即可。

## 实施阶段（建议顺序）

1. **Phase 0 前置**：确认企业微信账号可创建智能机器人（认证）；拿到 Bot ID/Secret；拿到 DeepSeek API Key。
2. **Phase 1 数据库**：写 `sql/init.sql`，在 PG 中建表。
3. **Phase 2 C++ 服务**：先在本机/服务器用 `curl` 单测 `/ask`（不依赖企微），验证「调 DeepSeek + 写 PG」通。
4. **Phase 3 Python 接入**：接 `wecom-aibot-python-sdk`，本地连上长连接，转发到 C++。
5. **Phase 4 容器化**：写 Dockerfile（cpp 用 cmake + gcc 编译；python 用官方镜像），docker-compose 一键起。
6. **Phase 5 端到端联调**：企微里 @机器人 提问，观察回答 + PG 记录 + 日志。

## 验证

- **C++ 单测**（无需企微）：
  ```bash
  curl -X POST http://127.0.0.1:8080/ask \
    -H 'Content-Type: application/json' \
    -d '{"question":"今天天气怎么样？","userid":"test"}'
  ```
  预期：返回 `{"answer":"..."}`，且 `messages` 表新增 2 条记录（user + assistant）。
- **Python 单测**：启动后日志显示长连接鉴权成功；本地模拟发一条消息事件，确认能转发到 C++ 并拿到回答。
- **全链路**：企微群/单聊 @机器人 提问 → 收到正确回答；`messages` 表有完整对话记录；重复消息（同 msgid）不重复入库。
- **健康检查**：`GET /health` 返回 ok；`docker compose ps` 三服务均 running。
