# 知识问答 Agent（企业微信智能机器人）实施方案

> v3：纯 Python + LangGraph + RAG（pgvector + 本地 embedding）。从「生活问答」升级为「知识问答 agent」——用户 @机器人 提问，系统基于自建文档库检索并生成**带引用来源**的回答。

## Context（背景）

用户想做一个「知识问答 agent」：接入企业微信，用户 @机器人 提问，系统从用户自己的文档库中检索相关内容，给出**有理有据、可溯源**的回答。技术栈为**纯 Python**，数据库用**云服务器上的 PostgreSQL**（已就绪）。

已确认的关键决策：

- **生成模型**：DeepSeek API（OpenAI 兼容接口），经 `langchain-deepseek` 接入
- **Embedding**：**本地 `BAAI/bge-m3`**（DeepSeek 官方无 embedding 接口，故本地向量化；中文强、免费、离线）
- **向量存储**：同一台 PG 上的 **`pgvector`** 扩展（不用另引独立向量库）
- **编排框架**：LangGraph（`retrieve → generate`，预留 agentic 化空间）
- **企微接入**：企业微信「智能机器人」→ API 接入 → **WebSocket 长连接模式**（无需备案域名/HTTPS）
- **文档**：PDF / Word / Markdown / txt，约几十篇
- **回答要求**：**附引用来源**
- **服务器**：腾讯云 Ubuntu（`VM-0-8-ubuntu`），Docker + PostgreSQL 17（`postgres`，映射 `127.0.0.1:5432`，密码为空）

## 可行性结论

**完全可行。** RAG 正是「LangGraph + 云 PG + DeepSeek」这套技术栈最标准的落地场景。两个新增依赖已确认：

1. **Embedding**：DeepSeek 官方不提供 embedding 接口，改用本地 `bge-m3`（`sentence-transformers` / `langchain-huggingface`）。
2. **pgvector**：现有 `postgres:17` 官方镜像默认不含该扩展，需换成 `pgvector/pgvector:pg17` 镜像（现有 `mydb` 基本为空，迁移成本≈0）。

唯一不变的技术难点仍是企微 WebSocket 长连接协议——由官方 SDK 屏蔽。

## 架构总览

```
企微用户 @机器人 提问
        │  (WebSocket 长连接，wss://openws.work.weixin.qq.com)
        ▼
┌─ Python 服务（单进程 asyncio，一个容器）──────────────────────┐
│                                                              │
│  bot.py —— wecom-aibot-python-sdk 长连接：收消息 / 排重 / 回复     │
│                                                              │
│  graph.py —— LangGraph 编排                                    │
│     retrieve 节点：query embedding → pgvector 相似检索 top-k       │
│     generate 节点：[检索上下文 + 问题] → DeepSeek → 答案 + 引用来源  │
│                                                              │
│  embed.py —— 本地 bge-m3 向量化                                 │
│  db.py —— psycopg 读写 messages / request_log                  │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
                        PostgreSQL（pgvector）
          messages 对话日志 · request_log 统计
          chunks 文档向量 · LangGraph checkpoint 状态

离线（一次性/增量）：
  docs/ → ingest.py → 解析 → 分块 → bge-m3 → chunks 表
```

## 技术选型

| 组件 | 选型 | 说明 |
|------|------|------|
| 企微接入 | `wecom-aibot-python-sdk` | 官方 Python SDK，asyncio 长连接 |
| LLM 编排 | `langgraph` | 有状态工作流，`retrieve → generate` |
| 生成模型 | `langchain-deepseek`（`ChatDeepSeek`） | `model="deepseek-chat"` |
| Embedding | `sentence-transformers` + `BAAI/bge-m3` | 本地 1024 维，中文强 |
| 向量存储 | `langchain-postgres`（`PGVector`）+ `pgvector` 扩展 | 复用云 PG |
| 状态持久化 | `langgraph-checkpoint-postgres`（`PostgresSaver`） | 多轮上下文存 PG |
| 文档解析 | `pymupdf`（PDF）/ `python-docx`（Word）/ 内建（md、txt） | `langchain-community` 统一加载 |
| 业务日志/排重 | `psycopg[binary]` | 直接读写 `messages` / `request_log` |
| 配置 | `pydantic-settings` + `python-dotenv` | 读环境变量 |
| 代码风格 | `ruff` | `ruff format` + `ruff check`，PEP 8 |
| 部署 | Docker Compose | 两容器：`postgres`(pgvector) + `app` |

## 编码约定（本项目统一遵循）

- 所有 Python 代码写在项目目录下（`app/`、`tests/`、`sql/`、`docs/`）。
- 分文件编写：入口 / 配置 / 接入 / 编排 / 状态 / 模型 / embedding / DB / 向量库 / 摄入 各一文件。
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
│   └── init.sql                # 建表 + 启用 pgvector
├── docs/                       # 待摄入的文档（几十篇放这里）
├── app/
│   ├── requirements.txt        # 或 pyproject.toml
│   ├── .env.example
│   ├── main.py                 # 入口：起企微长连接，装配 graph
│   ├── config.py               # 读环境变量
│   ├── bot.py                  # 企微接入：收消息、@过滤、排重、回复
│   ├── graph.py                # LangGraph 图：retrieve + generate
│   ├── state.py                # GraphState 类型定义
│   ├── llm.py                  # ChatDeepSeek
│   ├── embed.py                # bge-m3 本地 embedding（query/文档共用）
│   ├── vector_store.py         # PGVector 封装：写入 / 相似检索
│   ├── db.py                   # psycopg：messages/request_log + msgid 排重
│   └── ingest.py               # 离线摄入脚本：解析 → 分块 → embed → 入库
└── tests/
    ├── test_graph.py           # 脱离企微，直接 ainvoke 单测
    └── test_ingest.py          # 摄入 + 检索单测
```

## 组件详细设计

### 1. PostgreSQL（`sql/init.sql`）

```sql
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
```

- `chunks` 向量表由 `PGVector` 首次写入时**自动建**（含 `embedding vector(1024)`、`document`、`cmetadata`），`cmetadata` 里存来源信息（文件名、页码/块号）供引用。
- `messages` 独立保留，用于**幂等排重**与**可读审计日志**；LangGraph checkpoint 表由 `PostgresSaver` 自动建。

### 2. 文档摄入（`ingest.py`，离线）

1. 遍历 `docs/`，按扩展名选 loader：PDF→`pymupdf`、`.docx`→`python-docx`、md/txt→直接读。
2. 分块：`RecursiveCharacterTextSplitter`，块约 500–800 字、重叠 100–150，保留 `source`（文件名）+ 页/块号到 metadata。
3. `embed.py` 用 bge-m3 逐块向量化（1024 维）。
4. 写入 `PGVector`（collection=`knowledge`），metadata 存来源。
5. 支持**增量摄入**：按文件 hash 跳过已摄入内容（v1 可先全量，hash 去重作为增强）。

### 3. Embedding（`embed.py`）

- `HuggingFaceEmbeddings(model_name="BAAI/bge-m3")`（底层 `sentence-transformers`）。
- 查询用 bge 推荐的查询前缀（`"为这个句子生成表示以用于检索相关文章："`），文档侧不加，可小幅提升中文检索效果。
- 首次运行需下载模型（约 2 GB），CPU 推理对"几十篇 + 低并发"完全够用。

### 4. LangGraph 应用（`graph.py` / `state.py`）

- **State**：`MessagesState`（`messages`）+ 元数据（`userid/chatid/chattype/msgid`）+ `context`（检索到的文档块）+ `sources`（引用）。
- **节点**：
  - `retrieve`：取最新用户问题 → query embedding → `PGVector` 相似检索 top-k → 写回 `context` + `sources`。
  - `generate`：用 `system` 提示词 + `context`（带来源标注）+ 历史 + 当前问题 → `ChatDeepSeek` 生成 → 输出答案 + 引用。
- **边**：`START → retrieve → generate → END`。
- **checkpointer**：`PostgresSaver`，`thread_id = chatid or userid`。
- **v2 升级点**：把 `retrieve` 变成工具、加 query 改写 / 多跳 / 条件分支，即可 agentic 化（不改整体骨架）。

### 5. 检索与引用来源

- system 提示词要求：**只依据给定资料回答**，句末用 `[1][2]` 标注出处；资料不足时明确说"这个问题资料里没有"。
- 回复格式（企微文本）：
  ```
  <回答正文>……[1][2]

  来源：
  1. 《xxx.pdf》第 3 页
  2. 《yyy.md》
  ```

### 6. DeepSeek 调用（`llm.py`）

- `ChatDeepSeek(model="deepseek-chat", api_key=..., temperature=...)`，需 `DEEPSEEK_API_KEY`。
- 超时建议 60s。

### 7. 企微接入（`bot.py`）

- 配置：`BOT_ID`、`BOT_SECRET`。
- 流程：SDK 建立长连接鉴权 → 收 `text` 消息（群聊先判断是否 @机器人）→ `msgid` 排重 → 写 `role='user'` → `graph.ainvoke`（或 `astream`）→ 写 `role='assistant'` + `request_log` → SDK 回复。
- 异常兜底：失败回复固定文案「抱歉，暂时没查到相关资料～」，写 `request_log.status='error'`。

## 企微接入步骤（前置条件，需用户操作）

1. 注册/登录企业微信，进入管理后台。
2. 「应用管理 / 智能机器人」→ 创建机器人 → **API 接入（调用自有模型）** → **长连接模式**（无需认证/备案域名，管理员账号即可）。
3. 复制 **Bot ID** 与 **Secret**（填入 `.env`）。
4. 参考官方文档：
   - 智能机器人总览：https://developer.work.weixin.qq.com/document/path/101039
   - 智能机器人长连接：https://developer.work.weixin.qq.com/document/path/101463
   - 接收消息：https://developer.work.weixin.qq.com/document/path/100719
   - Python SDK：https://pypi.org/project/wecom-aibot-python-sdk/
5. DeepSeek 开放平台注册并创建 API Key（https://platform.deepseek.com ）。

## 部署（docker-compose.yml）

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg17
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
    volumes:
      - ./docs:/app/docs:ro          # 摄入用文档
      - hf_cache:/root/.cache/huggingface   # embedding 模型缓存
    depends_on: [postgres]
    restart: unless-stopped

volumes:
  pgdata:
  hf_cache:
```

> 说明：Dockerfile 在构建时下载 bge-m3 模型（或首次运行下载，走 `hf_cache` 卷）。现有独立 PG 容器是官方 `postgres:17`、不含 pgvector，且 `mydb` 基本为空，建议直接换 `pgvector/pgvector:pg17` 由 compose 统一管理。若坚持复用现有容器，则需在其内 `apt` 安装 pgvector 扩展后执行 `CREATE EXTENSION vector;`。

## 实施阶段（按阶段推进，完成后勾选 `[x]`）

> 约定：每阶段 = 实现 + 可执行的验证。完成一阶段后把 `- [ ]` 改为 `- [x]`；所有代码提交前跑 `ruff format` + `ruff check`。

- [x] **Phase 0 前置（用户操作）**
  - 做：拿到企微 Bot ID/Secret；拿到 DeepSeek API Key。
  - 验证：三个凭证齐全，`app/.env` 字段已填。

- [x] **Phase 1 数据库 + pgvector**
  - 做：写 `sql/init.sql`（`messages` + `request_log` + `CREATE EXTENSION vector`）；PG 换 `pgvector/pgvector:pg17`。
  - 验证：`psql` 执行后 `\dx` 有 `vector` 扩展；`\dt` 能看到 `messages`、`request_log`。

- [ ] **Phase 2 文档摄入**
  - 做：`embed.py`、`vector_store.py`、`ingest.py` + `tests/test_ingest.py`；`docs/` 放入几篇测试文档。
  - 验证：跑 `python -m app.ingest` 后，向量表有对应条数；用一条已知问题检索，能命中预期文档块（含正确 `source`）。

- [ ] **Phase 3 RAG 图**
  - 做：`state.py`、`llm.py`、`db.py`、`graph.py` + `tests/test_graph.py`。
  - 验证：`python -m pytest tests/test_graph.py` 通过；答案来自文档且带 `来源`；`messages` 表新增 user+assistant 两条，checkpoint 表有对应 thread；同一 thread 连问两次能引用上文。

- [ ] **Phase 4 企微接入**
  - 做：`config.py`、`bot.py`，接 SDK 长连接，转发到 graph。
  - 验证：启动后日志显示长连接鉴权成功；本地模拟一条消息事件，确认转发到 graph 并拿到带引用的回答。

- [ ] **Phase 5 容器化**
  - 做：Dockerfile（`python:3.12-slim`，构建时拉 bge-m3）+ `docker-compose.yml`（pgvector + app）。
  - 验证：`docker compose up -d` 后两服务 running；`docker compose logs app` 无报错；容器内 `graph.ainvoke` 能检索并生成。

- [ ] **Phase 6 端到端联调**
  - 做：企微里 @机器人 提问，全链路打通。
  - 验证：收到**带引用来源**的正确回答；`messages` 有完整记录；重复 msgid 不重复入库；`request_log` 有耗时记录。
