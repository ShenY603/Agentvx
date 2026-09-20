# 生活助手（企业微信智能机器人）实施方案

> v2：全 Python + LangGraph（原 v1 的 C++ 业务服务已移除，核心编排统一到 Python 生态）

## Context（背景）

用户想做一个「生活助手」：接入企业微信，用户 @机器人 提问生活问题，系统给出合理正确的回答。技术栈定为 **纯 Python**，数据库用**云服务器 Docker 容器里的 PostgreSQL**（已就绪）。

已确认的关键决策：

- **回答引擎**：DeepSeek API（OpenAI 兼容接口），经 `langchain-deepseek` 接入
- **编排框架**：LangGraph（有状态 agent 工作流，checkpoint 持久化、流式）
- **企微接入**：企业微信「智能机器人」→ API 接入 → **WebSocket 长连接模式**（官方推荐，无需备案域名/HTTPS）
- **PG 用途**：对话历史 + 日志 + LangGraph 状态（v1 不做 RAG/向量检索，但预留扩展位）
- **服务器**：腾讯云 Ubuntu（主机名 `VM-0-8-ubuntu`），已装 Docker 29.8 + PostgreSQL 17 容器（`postgres`，映射 `127.0.0.1:5432`）

## 可行性结论

**完全可行。** 相较原 C++ + Python 方案，本方案更简单、出错面更小：

- 企微 WebSocket 长连接仍由官方 SDK（`wecom-aibot-python-sdk`）负责，无需手写私有协议。
- DeepSeek 是 OpenAI 兼容接口，LangChain 原生支持，无需自己拼 HTTP/JSON。
- 对话历史、状态持久化、流式输出都有现成组件，无需手写 `libpqxx` 这类胶水。

唯一不变的技术难点依旧是企微 WebSocket 长连接协议——但该协议由官方 SDK 屏蔽，业务侧只需关心「收到消息 → 交给 LangGraph → 回复」。

## 架构总览

```
企微用户 @机器人 提问
        │  (WebSocket 长连接，wss://openws.work.weixin.qq.com)
        ▼
┌─ Python 服务（单进程 asyncio，一个容器）─────────────────────┐
│                                                              │
│  bot.py —— wecom-aibot-python-sdk 维持长连接                    │
│    · 收消息：仅处理 text，群聊先判断是否 @机器人                    │
│    · msgid 幂等排重（查 messages 表）                            │
│    · 把问题交给 LangGraph，取回答案（可流式）                      │
│                                                              │
│  graph.py —— LangGraph 编排                                    │
│    · State：messages(历史+当前) + 元数据                         │
│    · generate 节点 → DeepSeek 生成（langchain-deepseek）          │
│    · checkpointer = PostgresSaver（thread_id = chatid/userid）    │
│                                                              │
│  db.py —— psycopg 读写 messages / request_log                   │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
                        PostgreSQL 容器
        （messages 对话日志 + request_log 统计 + LangGraph checkpoint 状态）
```

单进程单容器即可跑通全链路；`bot.py`（接入）与 `graph.py`（业务）通过普通函数/异步调用衔接，若日后要拆成两个服务也很自然。

## 为什么「全 Python + LangGraph」

| 决策 | 理由 |
|------|------|
| 放弃 C++ | LangChain/LangGraph 是 Python 生态，编排逻辑天然落在 Python；C++ 只会退化成 HTTP 转发壳，无保留价值 |
| 用 LangGraph 而非裸调 DeepSeek | 用**状态机**组织流程：多轮记忆（checkpoint 自动带上文）、流式输出、后续可无痛加 RAG / 工具调用 / 意图路由分支 |
| checkpointer 用 PG 持久化 | 状态落库、进程重启不丢上下文、天然支持「按会话 id 隔离」 |

## 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| 企微接入 | `wecom-aibot-python-sdk` | 官方 Python SDK，asyncio 长连接 |
| LLM 编排 | `langgraph` | 有状态 agent 工作流，支持流式与 checkpoint |
| LLM 模型 | `langchain-deepseek`（`ChatDeepSeek`） | DeepSeek 官方 LangChain 集成，`model="deepseek-chat"`；也可用 `langchain-openai` 的 `ChatOpenAI(base_url=…)` |
| 状态持久化 | `langgraph-checkpoint-postgres`（`PostgresSaver`） | LangGraph 状态/多轮记忆存 PG，`thread_id=会话` |
| 业务日志/排重 | `psycopg[binary]` | 直接读写 `messages` / `request_log` 表（与 PostgresSaver 同用 psycopg，少一个依赖） |
| 配置 | `pydantic-settings` + `python-dotenv` | 读环境变量 / `.env` |
| 包管理 | `uv` 或 `pip` + `requirements.txt` | 依赖锁定 |
| 代码风格 | `ruff` | 统一格式化（`ruff format`）+ 静态检查（`ruff check`），PEP 8 |
| 部署 | Docker Compose | 两容器：`postgres` + `app`，内部网络 |

## 编码约定（本项目统一遵循）

- 所有 Python 代码写在项目目录下（`app/`、`tests/`、`sql/`）。
- 分文件编写：入口 / 配置 / 接入 / 编排 / 状态 / 模型 / DB 各一文件。
- 模块解耦：`bot.py`（接入）与 `graph.py`（编排）通过函数/异步调用衔接，不互相侵入内部实现。
- 文件名全小写。
- 格式统一：**ruff**（`ruff format` + `ruff check`），PEP 8。
- 分阶段推进，每阶段附验证步骤；完成一阶段后在「实施阶段」勾选对应 `- [x]`。

## 目录结构

```
life-assistant/
├── docker-compose.yml
├── README.md
├── sql/
│   └── init.sql                # 建表：messages + request_log
├── app/
│   ├── requirements.txt        # 或 pyproject.toml
│   ├── .env.example
│   ├── main.py                 # 入口：起企微长连接，装配 graph
│   ├── config.py               # 读环境变量（BOT_ID/BOT_SECRET/DEEPSEEK_API_KEY/DATABASE_URL）
│   ├── bot.py                  # wecom-aibot-python-sdk 封装：收消息、@过滤、排重、回复/流式
│   ├── graph.py                # LangGraph 图定义（State、generate 节点、checkpointer）
│   ├── state.py                # GraphState 类型定义（TypedDict）
│   ├── llm.py                  # 构造 ChatDeepSeek
│   └── db.py                   # psycopg 连接池 + 排重 + 日志读写
└── tests/
    └── test_graph.py           # 脱离企微，直接 ainvoke 单测 graph
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
    chatid     TEXT,
    status     TEXT,                     -- 'ok' / 'error' / 'timeout'
    latency_ms INT,
    detail     TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

> LangGraph 的 checkpoint 表（`checkpoints` / `checkpoint_blobs` / `checkpoint_writes`）由 `PostgresSaver` 首次启动时自动建，不必手写。`messages` 表独立保留，用于**幂等排重**与**可读审计日志**（checkpoint 表是框架内部格式，不便直接查询）。

### 2. LangGraph 应用（核心，`graph.py` / `state.py`）

- **State（`GraphState`）**：基于 LangGraph 内置的 `MessagesState`（含 `messages: list[BaseMessage]`），追加业务元数据 `userid / chatid / chattype / msgid`。
- **节点**：
  - `generate`：取 `messages`（checkpoint 已带上文 + 本次用户问题），组装 system 提示词，调 `ChatDeepSeek`，把结果作为 `AIMessage` 追加。
- **边**：`START → generate → END`。v1 单节点足够简单；用 LangGraph 的价值在于后续可无痛插入 `retrieve`（RAG）、`tools`（工具调用）、`route`（意图路由）等节点与条件分支。
- **checkpointer**：`PostgresSaver`，`thread_id = chatid or userid`（群聊按群、单聊按人隔离多轮上下文）。

### 3. DeepSeek 调用（`llm.py`）

- `ChatDeepSeek(model="deepseek-chat", api_key=..., temperature=...)`，需 `DEEPSEEK_API_KEY`。
- system 提示词示例：「你是一个生活助手，用简洁准确的中文回答日常生活问题。」
- 超时建议 60s；后续需要更强推理可换 `deepseek-reasoner`。

### 4. 企微接入（`bot.py`）

- 依赖：`wecom-aibot-python-sdk`。
- 配置：`BOT_ID`、`BOT_SECRET`（企微后台创建智能机器人后获得）。
- 流程：
  1. 用 SDK 建立到 `wss://openws.work.weixin.qq.com` 的长连接并鉴权（Bot ID + Secret）。
  2. 收到消息事件：仅处理 `msgtype == "text"`，取 `text.content`；群聊中先判断是否 @了机器人。
  3. **排重**：查 `messages` 表是否有该 `msgid`；有则复用已有回答（幂等，防重试/重投重复处理）。
  4. 写 `role='user'` 记录 → 调 `graph.ainvoke`（或 `astream`）→ 写 `role='assistant'` 记录 + `request_log`。
  5. 用 SDK 回复企微。v1 用普通文本回复；流式切换成本低：`graph.astream(stream_mode="messages")` 逐 token 下发到企微流式接口。
- 异常处理：DeepSeek 超时/失败时回复固定兜底文案（如「抱歉，暂时没想好怎么回答～」），并写 `request_log.status='error'`。

## 企微接入步骤（前置条件，需用户操作）

1. 注册/登录企业微信，进入管理后台（**智能机器人功能通常要求认证企业**，需先确认账号是否已认证）。
2. 「应用管理 / 智能机器人」→ 创建机器人 → 选择 **API 接入（调用自有模型）** → **长连接模式**。
3. 复制 **Bot ID** 与 **Secret**（填入 Python 服务环境变量）。
4. 参考官方文档：
   - 智能机器人总览：https://developer.work.weixin.qq.com/document/path/101039
   - 接收消息：https://developer.work.weixin.qq.com/document/path/100719
   - 流式消息回复：https://developer.work.weixin.qq.com/document/path/101031
   - Python SDK：https://pypi.org/project/wecom-aibot-python-sdk/
5. DeepSeek 开放平台注册并创建 API Key（https://platform.deepseek.com ）。

## 部署（docker-compose.yml）

两服务同处一个内部网络，PG 不暴露公网：

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

  app:
    build: ./app
    environment:
      BOT_ID: ${BOT_ID}
      BOT_SECRET: ${BOT_SECRET}
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
      DATABASE_URL: postgresql://postgres:${PG_PASSWORD}@postgres:5432/mydb
    depends_on: [postgres]
    restart: unless-stopped

volumes:
  pgdata:
```

> 说明：现有独立 PG 容器里的 `mydb` 基本是空库，可改为由 compose 统一管理（更干净）。若想复用现有容器，则去掉 compose 里的 postgres 服务，把 `DATABASE_URL` 的 host 指向宿主机地址即可。

## 实施阶段（按阶段推进，完成后勾选 `[x]`）

> 约定：每阶段 = 实现 + 可执行的验证。完成一阶段后，把该项 `- [ ]` 改为 `- [x]`；所有代码提交前跑 `ruff format` + `ruff check` 保证风格统一。

- [ ] **Phase 0 前置（用户操作）**
  - 做：确认企微账号可创建智能机器人（认证）；拿到 Bot ID/Secret；拿到 DeepSeek API Key。
  - 验证：三个凭证齐全，`app/.env.example` 对应字段可填。

- [ ] **Phase 1 数据库**
  - 做：写 `sql/init.sql`（`messages` + `request_log`），在 PG 建表。
  - 验证：执行后 `\dt` 能看到两张表；`\d messages` 字段符合设计。

- [ ] **Phase 2 LangGraph 应用**
  - 做：`state.py` / `llm.py` / `db.py` / `graph.py` + `tests/test_graph.py`。
  - 验证：`python -m pytest tests/test_graph.py` 通过；`graph.ainvoke` 返回 answer，`messages` 表新增 user+assistant 两条，checkpoint 表有对应 thread 状态；同一 thread 连问两次能引用上文。

- [ ] **Phase 3 企微接入**
  - 做：`config.py` / `bot.py`，接 `wecom-aibot-python-sdk` 长连接，转发到 graph。
  - 验证：启动后日志显示长连接鉴权成功；本地模拟一条消息事件，确认转发到 graph 并拿到回答。

- [ ] **Phase 4 容器化**
  - 做：Dockerfile（`python:3.12-slim`）+ `docker-compose.yml`（postgres + app）。
  - 验证：`docker compose up -d` 后 `docker compose ps` 两服务 running；`docker compose logs app` 无报错；进程存活且 PG 连通。

- [ ] **Phase 5 端到端联调**
  - 做：企微里 @机器人 提问，全链路打通。
  - 验证：收到正确回答；`messages` 表有完整对话记录；重复消息（同 msgid）不重复入库。
