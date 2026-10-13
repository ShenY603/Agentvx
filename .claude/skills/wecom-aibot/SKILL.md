---
name: wecom-aibot
description: 开发企业微信智能机器人（WebSocket 长连接模式）——aibot SDK 用法、标准架构、关键踩坑。当需要接入企微智能机器人、收发消息、回复消息时使用。
---

# 企业微信智能机器人开发指南

## 核心概念

企业微信「智能机器人」支持两种接入方式：**URL 回调** 与 **WebSocket 长连接**。

- **长连接模式（推荐）**：免备案域名、免公网入站、免 IP 白名单，只需 Bot ID + Secret，主动出站连 `wss://openws.work.weixin.qq.com`。
- **URL 回调模式**：需要公网 IP + 备案域名 + HTTPS（未认证企业还无法生成 EncodingAESKey）。

关键前提：
- **长连接不强制企业认证**，硬门槛是**管理员权限**（普通成员在后台看不到「API 接入」选项）。
- 智能机器人**仅限企业微信内部成员**使用；外部微信用户需走「微信客服」通道（要备案域名 + 公网回调）。
- 同一 `bot_id` 只允许一条有效长连接；主动推送需用户先发过消息。

## SDK 快速上手（wecom-aibot-python-sdk，模块名 `aibot`）

```python
from aibot import WSClient, WSClientOptions, generate_req_id

client = WSClient(WSClientOptions(bot_id="...", secret="..."))

@client.on("message.text")   # 事件名：message.text / message.image / event.enter_chat / authenticated
async def on_text(frame):
    body = frame.get("body", {})
    text = (body.get("text") or {}).get("content", "")
    # 回复：必须用 reply_stream（msgtype=stream）；reply(msgtype=text) 会被拒 40008
    await client.reply_stream(frame, generate_req_id("stream"), "回复内容", True)

client.run()  # 同步阻塞：内部 new_event_loop -> connect -> run_forever
```

方法签名（`inspect` 可得）：
- `connect()` async —— 建连接 + 自动鉴权（bot_id+secret）
- `run()` sync —— 便捷启动（new_event_loop + connect + run_forever）
- `reply(frame, body, cmd=None)` async —— 通用回复（body 自己拼 `{"msgtype": ..., ...}`）
- `reply_stream(frame, stream_id, content, finish, msg_item=None, feedback=None)` async —— 流式文本回复
- `on(event, f=None)` —— 注册回调（装饰器）

## 消息帧结构（text 消息）

```python
frame = {
  "headers": {"req_id": "..."},   # 回复时透传
  "body": {
    "msgid": "...",                 # 幂等排重键
    "chattype": "single" | "group",
    "chatid": "...",                # 仅群聊返回
    "from": {"userid": "..."},
    "msgtype": "text",
    "text": {"content": "..."},
  }
}
```

## 标准架构（模块解耦）

- `bot.py` —— 企微接入：收消息 / msgid 排重 / 调 graph / 回复
- `graph.py` —— LangGraph agent 循环（LLM 决策调用工具）；`tools.py` 定义工具（知识库检索 / 网页搜索 / 天气 / 计算 / 时间）
- `db.py` —— 落库 + 排重（messages / request_log）
- `embed.py` / `vector_store.py` —— RAG 向量化与检索
- `main.py` —— 装配：`graph = build_graph(); client = build_client(); register_handlers(client, graph); client.run()`

关键解耦点：`graph` 由 `main` 注入 `bot`（`register_handlers(client, graph)`），接入层不 import 业务层。异步 handler 里跑同步 `graph.invoke` 用 `asyncio.to_thread(...)` 避免阻塞事件循环。

## 关键踩坑（详见项目 Problem.md）

1. **回复用 `reply_stream`**（`msgtype=stream`），`reply(msgtype=text)` 报 `40008 invalid message type`。
2. 群聊消息企微侧已过滤 @机器人，无需再判断；`chatid` 仅群聊有。
3. 按 `msgid` 幂等排重（`messages.msgid` 唯一约束 + `ON CONFLICT DO NOTHING`）。
4. Ctrl+C 退出时 SDK 会刷 `Task was destroyed` 噪声（同步 disconnect 未 await async 清理），不影响功能。
5. 配 DeepSeek 需显式 `openai_api_base="https://api.deepseek.com"`（默认连 api.openai.com 被墙）。
6. 国内：HF 用 `HF_ENDPOINT=https://hf-mirror.com`，模型已缓存时 `HF_HUB_OFFLINE=1` 离线加载。
