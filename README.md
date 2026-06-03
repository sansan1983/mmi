# README.md

# MMI — Multimodal Intelligence 多模态智能体系统

> 带记忆引擎与多Agent调度的智能体系统。
> 从 [C-Trim](https://github.com/sansan1983/ctrim) 演进而来。

## 架构

```
mmi/
├── core/          # 记忆引擎层（会话/上下文/摘要/检索/热度/GC）
├── agent/         # Agent调度层（路由/思维模式/校验/技能/Tool/追踪）
├── cli.py         # 统一CLI入口
├── tui/           # 终端UI（textual）
└── tools/         # 诊断工具
```

完整架构见 `MMI统一架构设计.md`。

## 快速开始

```bash
# 安装
pip install -e ".[tui,fuzzy]"

# 环境变量
export MMI_API_KEY=sk-...            # OpenAI 兼容 API Key
export MMI_BASE_URL=https://...      # 可选，自定义 endpoint
export MMI_MODEL=gpt-4o-mini         # 可选，config.toml 优先

# CLI
mmi new "我的第一个会话"
mmi list
mmi chat <session_id>
mmi tui                               # 启动 TUI
mmi doctor                            # 诊断
mmi stat                              # 统计

# 测试
python -m pytest tests/ -v
```

## 工作原理

```
用户输入 → 主Agent调度 → 意图分类 → 路由到子Agent/思维模式
                ↕
        mmi/core 记忆引擎
        ├── context: 三源合并上下文构建（摘要+语义记忆+最近轮）
        ├── memory: FAISS向量检索 + LLM动态重排
        ├── heat: 四态状态机（active/warm/cold/zombie）
        └── gc: 自动垃圾回收
```

## 核心原则

- UI ≠ 推理 —— 界面只负责显示
- 显示 ≠ 发送 —— LLM上下文是修剪过的视图
- 不压缩原文 —— 原文完整保存，只修剪LLM视图
- 核心可独立运行 —— core/不依赖UI

## 设计文档

| 文档 | 说明 |
|---|---|
| `MMI统一架构设计.md` | 完整架构设计 |
| `RULES.md` | 工作规范 |
| `PLAN.md` | 分期计划 |
