# HANDOVER 索引 — Round ↔ PLAN.md 任务对应

> 这份索引的目的:让你/接手者能扫一眼"每个 Round 实际覆盖了 PLAN.md 哪些任务"。
> 避免 Round 编号(我自己编的)和 PLAN.md 任务编号(2.1-2.10)对不上,以后回头查阅时混乱。

---

## 完整对应表

| Round 文件 | 日期 | 覆盖 PLAN.md 任务 | 主题 |
|---|---|---|---|
| `round_2.md` | 2026-06-03 | **2.1** | SessionMeta 时间字段 + cold→zombie 升级 + manager 写竞态修复 |
| `round_2_2.md` | 2026-06-03 | **2.2, 2.3, 2.4, 2.6, 2.7, 2.8, 2.9, 2.10**(8 项) | FAISS + memory 模块 + CLI + context 集成 |
| `round_2_3.md` | 2026-06-04 | **2.5**(补 2.2 漏的) | LLM 版 build_structured_summary + FTS5 双路 + summarizer 自动入库 |
| `round_2_4.md` | 2026-06-04 | **无**(bonus 收尾) | memory 入库拆独立线程 + content_hash 去重 + 清 ruff |
| `round_2_5.md` | 2026-06-04 | **无**(用户临时加的小项目) | 交互式 LLM 配置 wizard:5 国内商 + 1 自定义 + Anthropic 优先 |
| `round_3.md` | 2026-06-04 | **临时变更计划 改进 Round 1** | P0-1 短会话入库 + P0-3 tiktoken + P2-8 任务队列(三期顺延) |
| `round_4.md` | 2026-06-04 | **临时变更计划 改进 Round 2** | P0-2 jieba + BM25 + P1-4 截断优先级 + P1-5 动态窗口 |
| `round_5.md` | 2026-06-04 | **临时变更计划 改进 Round 3** | P1-7 增量摘要 + P2-10 FAISS 池化 + P2-9 简化版热度 |
| `round_6_phase3.md` | 2026-06-05 | **三期 3.1–3.12 全部 12 项** | BaseAgent + Router + Orchestrator + Validator + CodeReviewAgent + DocAgent + 生命周期 + registry 单例 + CLI agent/skill + mode locale |

---

## 怎么用这份索引

1. 想查"2.5 做了没" → 看 `round_2_3.md` 顶部
2. 想查"某个 Round 干了啥" → 看下面这张表
3. 想查"哪些任务还差" → 对照 PLAN.md 二期任务清单(2.1-2.10)全在表里

## PLAN.md 二期 10 项对应表

| PLAN.md 任务 | 落地 Round | 关键文件 |
|---|---|---|
| 2.1 修 SessionMeta 遗留 + cold_since_parsed | `round_2.md` | `mmi/core/session.py` `mmi/core/gc.py` |
| 2.2 装 FAISS + sentence-transformers | `round_2_2.md` | `pyproject.toml` `[memory]` |
| 2.3 memory.store_memory() | `round_2_2.md` | `mmi/core/memory.py:store_memory` |
| 2.4 memory.search_semantic() | `round_2_2.md` | `mmi/core/memory.py:search_semantic` |
| 2.5 memory.build_structured_summary() LLM 版 | `round_2_3.md` | `mmi/core/memory.py:build_structured_summary` |
| 2.6 memory.rerank() | `round_2_2.md` | `mmi/core/memory.py:rerank` |
| 2.7 集成 context.py | `round_2_2.md` | `mmi/core/context.py` LoaderConfig.memory |
| 2.8 新增记忆表 + FAISS index | `round_2_2.md` | `~/.mmi/memory.db` `faiss.index` `faiss_ids.json` |
| 2.9 CLI: mmi memory search | `round_2_2.md` | `mmi/cli.py:cmd_memory` |
| 2.10 memory 模块测试 | `round_2_2.md` + `round_2_3.md` | `tests/test_memory.py`(共 44 个) |

> 更新规则:每轮完工写 HANDOVER 时,务必在文件顶部加 `覆盖 PLAN.md: ...` 行;
> 同步更新这份 INDEX.md。
