# MMI 分期计划（PLAN）

> 版本：v0.1.0 | 2026-06-03  
> 当前阶段：一期 MVP 完成，进入二期

---

## 总览

| 阶段 | 目标 | 核心交付 | 状态 |
|---|---|---|---|
| 一期 | MVP — 有记忆的单Agent | 会话+上下文+摘要+热度+GC+CLI+TUI | ✅ 完成 |
| 二期 | 向量记忆 | FAISS检索 + 结构化摘要 + 动态重排 | ⬜ 待开始 |
| 三期 | 多Agent调度 | 意图路由 + 子Agent池 + 技能库 + 校验 | ⬜ 规划中 |
| 四期 | 进化 + 生态 | 技能统计 + 候选提议 + 评估框架 + 第三方 | ⬜ 规划中 |

---

## 一期：MVP — 有记忆的单Agent ✅

### 目标
从 ctrim v0.5.0a5 迁移为 MMI v0.1.0，保持所有现有功能，新增 agent/ 骨架。

### 已完成

| 模块 | 内容 |
|---|---|
| core/ | session / storage / heat / context / summarizer / gc / search / titler / classifier / llm / config / i18n / paths / manager 全量迁移 |
| context.py | 三源合并上下文构建（摘要 + 命中段 + 最近轮） |
| summarizer.py | 三条件触发 + 版本链 + 后台线程 |
| heat.py | 四态状态机 + 热度公式 |
| gc.py | trash TTL + zombie/cold 清理 |
| CLI | 15+ mmi 子命令（new/list/chat/archive/delete/gc/stat/export/tui/rename/info/inspect/doctor） |
| TUI | textual 界面（list/chat/search屏 + 流式输出 + 斜杠命令） |
| i18n | 中英双语基线 |
| agent/ | orchestrator / router / registry / modes / validate / skill / tools / trace 骨架 |
| memory.py | 向量记忆接口骨架 |

### 测试
- 302/312 核心测试通过
- 10个失败：SessionMeta datetime 序列化类型一致性问题（同根因）
- CLI/TUI/Fuzzy 测试排除（环境依赖）

### 产出
- 仓库: `https://github.com/sansan1983/mmi`
- 包: `mmi v0.1.0`
- 架构文档: `ARCHITECTURE.md`

---

## 二期：向量记忆

### 目标
将会话记忆从纯 TF 关键词检索升级为 FAISS 向量语义检索 + LLM 动态重排。

### 任务清单

| # | 任务 | 说明 | 预估 |
|---|---|---|---|
| 2.1 | 修复 SessionMeta 遗留测试 | 10个失败 + cold_since_parsed 属性 | 0.5d |
| 2.2 | 安装 FAISS 依赖 | faiss-cpu + sentence-transformers | 0.5d |
| 2.3 | 实现 memory.store_memory() | 对话结束 → embedding → 存入 SQLite + FAISS | 2d |
| 2.4 | 实现 memory.search_semantic() | 用户输入 → embedding → FAISS top-20 | 1d |
| 2.5 | 实现 memory.build_structured_summary() | LLM 生成 {主题, 决策, 结论, 待办} | 1d |
| 2.6 | 实现 memory.rerank() | LLM 动态重排 top-20 → top-3 | 1d |
| 2.7 | 集成 context.py | build_context() 调用 memory.search_semantic() 注入上下文 | 1d |
| 2.8 | 新增记忆表 | memories 表（SQLite）或 Faiss index 文件 | 0.5d |
| 2.9 | CLI: mmi memory search | 检索历史记忆命令 | 0.5d |
| 2.10 | 测试 | memory 模块单元测试 + 集成测试 | 1.5d |

### 验收标准
- `mmi memory search "关键词"` 返回相关历史记忆
- 新会话能自动注入相关历史记忆到上下文
- 记忆检索延迟 < 500ms
- 记忆模块测试通过

---

## 三期：多Agent调度

### 目标
从单Agent升级为多Agent分工协作系统。

### 任务清单

| # | 任务 | 说明 |
|---|---|---|
| 3.1 | 实现 orchestrator.py | 完整 chat() 流程：上下文 → 分类 → 路由 → 执行 → 校验 → 持久化 |
| 3.2 | 实现 router.py | 意图分类（QA/CREATIVE/EXECUTE/TOOL） |
| 3.3 | 实现 registry.py | Agent 注册/匹配/列表 |
| 3.4 | 实现 CodeReviewAgent | 代码审查（system_prompt + tools 绑定） |
| 3.5 | 实现 DocAgent | 文档生成/翻译 |
| 3.6 | 实现 modes.py | STANDARD/BRAINSTORM/AUDIT 三模式 prompt 切换 |
| 3.7 | 实现 validate.py 规则引擎 | 敏感词/格式/空输出 |
| 3.8 | 实现 skill.py | Skill CRUD + 触发匹配 |
| 3.9 | 实现 tools.py | @tool 装饰器 + 自动发现 |
| 3.10 | 实现 trace.py | 调用追踪记录 |
| 3.11 | CLI: mmi agent list/invoke | Agent管理命令 |
| 3.12 | CLI: mmi skill list/create | 技能管理命令 |
| 3.13 | 测试 | Agent调度集成测试 |

### 验收标准
- 同一输入按意图路由到不同Agent
- 输出通过规则引擎校验
- 技能库可人工创建/匹配
- Agent调用链可追踪

---

## 四期：进化 + 生态

### 目标
数据驱动的迭代能力 + 第三方对接。

### 任务清单

| # | 任务 | 说明 |
|---|---|---|
| 4.1 | 技能统计看板 | 使用率/采纳率 |
| 4.2 | 候选技能提议 | LLM提议 + 人工确认 |
| 4.3 | LLM深度审核上线 | 高风险输出二次检查 |
| 4.4 | 评估框架 | 100个典型场景自动化评估 |
| 4.5 | 第三方Tool对接 | 外部API注册为Tool |
| 4.6 | Web GUI 骨架 | Vue3单页对话界面 |
| 4.7 | MCP协议集成 | 作为Tool来源之一 |
| 4.8 | 性能压测 + 调优 | 并发/延迟/内存 |

---

## 工作规范

每轮开发遵循 RULES.md 定义的流程：

```
读上轮交接 → 读架构文档 → 对齐检查 → 开始工作
  → 更新 ROUND_LOG.md → 跑测试 → 写交接文档 → commit
```

质量门禁：ruff 0 error + pytest 全绿 + 文档已更新。

---

> 完整架构见 `ARCHITECTURE.md`，工作规范见 `RULES.md`
