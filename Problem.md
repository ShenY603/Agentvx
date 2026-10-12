# 踩坑记录（Problems）

本文件记录项目过程中遇到的所有问题、根因与解决方案，供排查时快速对照。方案正文见 [README.md](README.md)。

## 一、环境 / 部署

### 1. GitHub HTTPS 克隆报「Password authentication is not supported」
- **现象**：`git clone https://...` 提示 `Invalid username or token. Password authentication is not supported`。
- **根因**：GitHub 自 2021 年起禁用 HTTPS 密码认证。
- **解决**：用 Personal Access Token（PAT）代替密码；或改用 SSH（`ssh-keygen -t ed25519`，公钥加到 GitHub，用 `git@github.com:...` 地址）。注：`ssh-keygen -C "邮箱"` 里的邮箱只是备注，与认证无关。

### 2. 服务器 `python3 -m venv` 失败
- **现象**：`The virtual environment was not created successfully because ensurepip is not available`。
- **根因**：Ubuntu 缺 `python3-venv` 包。
- **解决**：`sudo apt install -y python3.10-venv`，删掉半成品 `.venv` 重建。

### 3. 国内服务器连不上 HuggingFace
- **现象**：下载模型报 `[Errno 101] Network is unreachable`（连 `huggingface.co`）。
- **根因**：国内服务器无法直连 HuggingFace。
- **解决**：走国内镜像 `export HF_ENDPOINT=https://hf-mirror.com`。

### 4. 模型加载时联网检查卡住（几十秒无响应）
- **现象**：`get_embedding()` 加载模型一直阻塞在 socket 上，curl 直连镜像也极慢（10 秒才回 200）。
- **根因**：`sentence-transformers` 加载模型时会联网检查，而镜像/直连当时都很慢。
- **解决**：模型已缓存时强制离线加载——在 `app/__init__.py` 里 `setdefault` `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`（可被显式覆盖）。新机器首次部署需先 `HF_HUB_OFFLINE=0 python -m app.ingest` 在线下载一次。

### 5. 2GB 内存服务器加载 bge-m3 直接 OOM
- **现象**：`RuntimeError: unable to mmap 2271145830 bytes ... Cannot allocate memory (12)`。
- **根因**：服务器仅 1.9GB 内存、无 swap，bge-m3（fp32 约 2.27GB）装不下。
- **解决**：换 `BAAI/bge-small-zh-v1.5`（~100MB，512 维），几十篇文档完全够用。

## 二、数据库 / PostgreSQL

### 6. 程序连 PG 报 `fe_sendauth: no password supplied`
- **现象**：程序连 `127.0.0.1:5432` 报 `fe_sendauth: no password supplied`，但 `docker exec psql` 却不用密码。
- **根因**：`docker exec psql` 走容器内 unix socket（trust）；程序走 TCP，官方镜像对 TCP 默认要求密码。更关键的是：Docker 端口转发后，postgres 看到的来源 IP 是网关 `172.17.x.x` 而非 `127.0.0.1`，所以 `pg_hba` 里 `127.0.0.1/32 trust` 匹配不到，落到 `host all all all scram-sha-256`。
- **解决**：把 `pg_hba.conf` 里的 `scram-sha-256`/`md5` 改成 `trust` 并 `pg_reload_conf()`。容器重启会失效，Phase 5 用 `POSTGRES_HOST_AUTH_METHOD=trust` 固化。

### 7. 建表时 collation version mismatch 警告
- **现象**：`WARNING: database "mydb" has a collation version mismatch (2.41 vs 2.36)`。
- **根因**：数据卷由旧镜像（glibc 2.41）创建，新 `pgvector/pgvector:pg17` 镜像 glibc 是 2.36。
- **解决**：空库无害，`ALTER DATABASE mydb REFRESH COLLATION VERSION;` 清掉警告即可。

### 8. `PostgresSaver.from_conn_string(...).setup()` 报 AttributeError
- **现象**：`'_GeneratorContextManager' object has no attribute 'setup'`。
- **根因**：`from_conn_string` 是 context manager，返回的不是 saver 本身。
- **解决**：用连接池直接构造 `PostgresSaver(ConnectionPool(url))`。

### 9. `checkpointer.setup()` 报 `CREATE INDEX CONCURRENTLY cannot run inside a transaction block`
- **现象**：`psycopg.errors.ActiveSqlTransaction`。
- **根因**：psycopg 默认 `autocommit=False`，而 `CREATE INDEX CONCURRENTLY` 必须在事务外执行。
- **解决**：`ConnectionPool(url, open=True, kwargs={"autocommit": True, "prepare_threshold": 0})`。

## 三、DeepSeek

### 10. `ChatDeepSeek` 调用一直超时（约 60s × 3 次重试）
- **现象**：`invoke()` 卡在 socket 上 227 秒，但 curl 直连 `api.deepseek.com` 秒回 200。
- **根因**：`langchain-deepseek` 的 `ChatDeepSeek` 默认 `openai_api_base=None`，回落到 `api.openai.com`（国内被墙、SYN 被丢 → 挂起超时）。
- **解决**：显式传 `openai_api_base="https://api.deepseek.com"`。

## 四、RAG 设计

### 11. `chunk_size=600` 超出 bge-small 的 512 token 上限
- **现象**：600 中文字符 ≈ 600 token，超过 bge-small 的 `max_seq_length=512`，每块尾部约 88 字被静默截断。
- **解决**：`chunk_size=500`、`chunk_overlap=100`。

## 五、企微接入

### 12. 把「微信客服」当成「智能机器人」
- **现象**：拿到 `work.weixin.qq.com/kfid/...` 链接。
- **根因**：`kfid` 是微信客服（外部用户联系客服用），与「智能机器人」是两个不同功能。
- **解决**：正确入口是管理后台「应用管理 → 智能机器人 → API 接入 → 长连接」。

### 13. 误以为智能机器人必须企业认证
- **现象**：找不到「智能机器人 / 长连接」入口，以为卡在认证。
- **根因**：长连接模式**不强制企业认证**，硬门槛是**管理员权限**（普通成员看不到 API 接入选项）。
- **解决**：用管理员账号，或个人免费注册企业微信（注册即管理员）。

## 六、测试

### 14. 分块单测失败（`assert 1 > 1`）
- **现象**：`test_split_keeps_source_and_produces_chunks` 失败。
- **根因**：测试文本 `"句子一。句子二。句子三。" * 50` = 600 字符，正好等于 `chunk_size`，未触发切分。
- **解决**：文本加长到 `* 100`。

## 七、SDK 已知噪声

### 15. Ctrl+C 退出时刷屏 `Task was destroyed but it is pending`
- **现象**：`python -m app.main` 启动、鉴权都正常，但 `Ctrl+C` 退出时刷一堆 `Task was destroyed but it is pending`、`Event loop is closed`、`coroutine ... was never awaited`。
- **根因**：SDK 的 `run()` 在 KeyboardInterrupt 里调用的是同步 `disconnect()`，而内部清理（心跳、收包、断开）是 async，未被 await 就被 `loop.close()` 销毁。
- **影响**：**纯退出噪声，不影响功能**（连接已正常关闭）。
- **解决**：v1 可忽略；如介意，可在 `main.py` 自行管理事件循环、优雅 await 异步断开。
