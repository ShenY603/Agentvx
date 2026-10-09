# 知识问答系统说明

本项目是一个基于企业微信的知识问答 agent。用户在企业微信里 @机器人 提问，系统会从文档库中检索相关内容并生成回答。

## 技术栈

- 生成模型：DeepSeek（deepseek-chat）
- 向量模型：本地 bge-m3
- 编排框架：LangGraph
- 数据库：PostgreSQL + pgvector

## 部署方式

系统部署在腾讯云 Ubuntu 服务器上，使用 Docker Compose 管理 postgres 和 app 两个容器。文档向量存储在 pgvector 的 collection 里，检索时按相似度返回最相关的片段。

## 引用来源

回答会附带引用来源，标注命中的文档名与页码，方便用户追溯原文。
