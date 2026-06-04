# MMI 分期计划（PLAN）

> 版本：v1.0 | 2026-06-04
> 当前阶段：二期完成，进入三期(同时跑改进计划)

---

## 总览

| 阶段 | 目标 | 核心交付 | 状态 |
|---|---|---|---|
| 一期 | MVP — 有记忆的单Agent | 会话+上下文+摘要+热度+GC+CLI+TUI | ✅ 完成 |
| 二期 | 向量记忆 | FAISS检索 + 结构化摘要 + 动态重排 | ✅ 完成 |
| 三期 | 多Agent调度 | 意图路由 + 子Agent池 + 技能库 + 校验 | ⬜ 待开始 |
| 四期 | 进化 + 生态 | 技能统计 + 候选提议 + 评估框架 + 第三方 | ⬜ 规划中 |

---

## 临时变更计划 — memory/context 改进(2026-06-04 启动)

> 来源:`IMPROVEMENT-PLAN.md`(10 项 P0/P1/P2)
> 顺序:按可行性 + 依赖关系调整后,**三期(原计划三)顺延**,先做 3 轮改进
> 预估:21-32h(详见 IMPROVEMENT-PLAN §四 + 我的可行性分析)

| 轮 | 项目 | 时间 | 备注 |
|---|---|---|---|
| 改进 Round 1 | **P0-1** 短会话入库 + **P0-3** tiktoken 精确估算 + **P2-8** 任务队列 | 3-4h | 基础修复,高频入库 + 精确预算 + 后台安全 |
| 改进 Round 2 | **P0-2** jieba + BM25 + **P1-4** 截断优先级 + **P1-5** 动态窗口 | 8-10h | 搜索质量 + 上下文弹性 |
| 改进 Round 3 | **P1-7** 增量摘要 + **P2-10** FAISS 池化 + **P2-9**(简化版)增强热度 | 10-12h | 性能与智能 |
| 改进 Round 4(可选) | **P1-6** 上下文增量缓存 | 5-6h | 长对话性能(投出比存疑,后议) |

**顺延影响**:三期(多 Agent 调度)与四期(进化)推到改进计划完成后。

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

## 二期：向量记忆 ✅

### 目标
将会话记忆从纯 TF 关键词检索升级为 FAISS 向量语义检索 + LLM 动态重排。

### 已完成（2026-06-04 收尾）

| # | 任务 | 状态 | 落点 |
|---|---|---|---|
| 2.1 | 修复 SessionMeta 遗留测试 + cold_since_parsed | ✅ | `mmi/core/session.py`、`mmi/core/gc.py` |
| 2.2 | 安装 FAISS + sentence-transformers 依赖 | ✅ | `pyproject.toml` `[memory]` extras |
| 2.3 | 实现 memory.store_memory() | ✅ | `mmi/core/memory.py:store_memory` |
| 2.4 | 实现 memory.search_semantic() | ✅ | `mmi/core/memory.py:search_semantic`(FAISS + FTS5 双路) |
| 2.5 | 实现 memory.build_structured_summary() | ✅ | `mmi/core/memory.py` 规则版 + LLM 版双模 |
| 2.6 | 实现 memory.rerank() | ✅ | `mmi/core/memory.py:rerank` |
| 2.7 | 集成 context.py | ✅ | `mmi/core/context.py` LoaderConfig.memory + system 段 |
| 2.8 | 新增记忆表 + FAISS index | ✅ | `~/.mmi/memory.db` + `~/.mmi/faiss.index` + `faiss_ids.json` |
| 2.9 | CLI: mmi memory search/count/clear | ✅ | `mmi/cli.py` cmd_memory |
| 2.10 | 测试 | ✅ | `tests/test_memory.py` 44 个 + 1 个 summarizer 集成 |

### 验收对照

- ✅ `mmi memory search "关键词"` 返回相关历史记忆
- ✅ 新会话能自动注入相关历史记忆到上下文
- ✅ 记忆检索延迟 < 500ms(FAISS IndexFlatL2 + 64 维)
- ✅ 记忆模块测试通过(44 个单元 + 1 集成)
- ✅ summarizer 后台线程成功后自动入库(content_hash 去重)
- ✅ ruff 0 error(全 35 个清完)

### 关键决策（已落地,不再重提）

- 嵌入器可注入:默认 sentence-transformers,失败降级 HashEmbedder(测试用)
- 存储:SQLite 存元数据 + FAISS 存向量 + JSON 存 id 映射(三件套)
- 检索:FAISS top-k + FTS5 top-k → 按 memory_id 去重,FAISS 优先
- rerank 容错:LLM 异常/未知 id → 退回原顺序补齐
- summarizer 完成后自动入库,失败静默(独立 daemon 线程)
- 同 body 重复入库 → content_hash 去重,不重算 embedding

### 下一阶段
[三期：多Agent调度](#三期多agent调度) — 3.1 orchestrator / 3.2 router / 3.3 registry 等

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
