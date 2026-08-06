---
title: AI懂车价
emoji: 🚗
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
license: mit
---

# AI懂车价

二手车选品、行情与完整七要素估价 Agent。线上主页位于 `/agent`。

当前运行版本：`2026-07-15 internal gray release + v195.439 full-catalog pricing model`。

本版包含按文本动态编排的行情、选品、定价和汽车知识问答工具链，完整七要素
定价、可编辑价差利润计算器、任意预算/品类筛选，以及逐步流式任务过程。

定价模型运行资产、人工审核面板、市场缓存和内部日报通过私有运行资产仓加载，
不会保存在公开 Space 仓库中。API 密钥只通过 Hugging Face Secrets 注入。
