# 交接文档 — Round 2.4
> 日期：2026-06-04
> 状态：✅ 已完成
> 主题：memory 写入收尾(独立线程 + 内容 hash 去重 + 清 ruff)
> 覆盖 PLAN.md：**无**(bonus 收尾,不在 PLAN.md 任务清单里)
>
> 改动:summarizer 入库拆独立线程 + content_hash 去重 + 清 35 个 ruff error
> 性质:对 Round 2.2/2.3 已交付的代码做收尾打磨,不属于新功能交付

---

## 1. 本轮完成

- ✅ **入库拆独立线程**：`summarizer._run` 只跑 `update_summary`，完成后调用 `_schedule_memory_store(session_id)` 起独立 daemon 线程跑 `store_memory`。摘要与入库解耦，update_summary 的 LLM 慢调用结束后立刻释放线程
- ✅ **content_hash 去重**：`memories` 表加 `content_hash TEXT` 列 + 索引；`store_memory` 入口先 `_get_by_hash(body_hash)`，命中即返回旧 record 不再写盘
- ✅ **ruff 0 error**：35 个 error 全清（24 个 `--fix` 自动修 + 11 个手动修）
- ✅ **+8 个新测试**（6 个去重 + 2 个独立线程）
- ✅ **全量 395/395 全绿**（改前 387）

---

## 2. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/summarizer.py` | 修改 | `_run` 只跑 update_summary，成功后调 `_schedule_memory_store`；加 `_schedule_memory_store` 函数；移除未用 `current_turns` |
| `mmi/core/memory.py` | 修改 | schema 加 `content_hash` + 索引；`store_memory` 加 hash 去重；`_get_by_hash` 辅助；`_content_hash` 函数；FAISS `I` 改名 `idx_indices` 消 E741 |
| `mmi/__init__.py` | 修改 | `SessionState as SessionState` 显式 re-export |
| `mmi/cli.py` | 修改 | 移除未用 `p_tui` / `p_doctor` / `p_stat` / `title` |
| `mmi/tools/doctor.py` | 修改 | 4 个 import 加 `noqa: E402` |
| `tests/test_memory.py` | 修改 | +8 个 Round 2.4 测试 |
| `ROUND_LOG.md` | 更新 | 本轮日志 |
| `docs/HANDOVER/round_2_4.md` | 新建 | 本交接文档 |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| 改前 baseline | 387 / 387 | Round 2.3 收尾 |
| 改后(本轮) | **395 / 395** | +8 memory tests |
| 改后含 CLI | 402 / 405 | 3 个 CLI 集成需 `~/.mmi-fusion` 预置,跳过 |
| ruff | **0 error** | 改前 35 |

跑法：
```bash
/tmp/mmi-venv/bin/python -m pytest tests/ -q --ignore=tests/test_cli.py
/tmp/mmi-venv/bin/ruff check mmi/
```

---

## 4. 关键决策记录

### 决策 1：入库独立线程(不是消息队列)

- **方案 A**(采用)：`_schedule_memory_store` 起独立 daemon 线程
- **方案 B**：用 `queue.Queue` + 单消费者线程
- **理由**：
  - 当前 store_memory 频率不高(每次 summary 完一次),单 daemon 线程足够
  - 线程方案比队列简单,代码量小,无额外组件
  - 后续高频场景再升级队列

### 决策 2：content_hash 16 字符短 hash

- **方案 A**(采用)：sha256(body)[:16] = 16 hex chars
- **方案 B**：完整 sha256 = 64 chars
- **理由**：
  - 16 字符冲突概率 ~1/2^64,业务场景(几千条记忆)基本不可能撞
  - 索引体积小 4 倍,SQLite 索引效率高
  - 生产可换更长 hash,但本阶段没必要

### 决策 3：去重命中时返旧 record(不更新 created_at)

- **方案 A**(采用)：同 hash 命中 → 直接返旧 record,不动盘
- **方案 B**：更新 created_at = now,顶掉旧时间
- **理由**：
  - 内容相同就是同一条记忆,时间戳不该变化
  - 方案 B 会让同一条记忆反复"刷新"时间,失去时间维度语义
  - 真要更新,应手动 clear + 重新入库(意图明确)

---

## 5. 遗留问题

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | Round 3.0 多 Agent 调度 还没开始 | 拖慢整体进度 | 下一轮启动 |
| 2 | LLM summary prompt 可调优 | 提取质量 | 实测数据后调 |
| 3 | FTS5 query sanitizer 简化版(NEAR/列查询不支持) | 复杂 query 受限 | Round 3.x 升级 |
| 4 | 入库无频率限制(高频 chat 仍可能堆积) | 极端场景下线程数 | Round 3.x 加节流 |

---

## 6. 下轮计划(建议)

**Round 3.0 — 多 Agent 调度骨架(PLAN.md 三期)**

任务：
1. `Orchestrator.chat()` 完整流程（context → classify → route → execute → validate → persist）
2. `Router` 意图分类（规则预筛 + LLM 二次确认）
3. `Registry` Agent 注册/匹配/列表
4. 3 个内置 Agent 骨架填充：`CodeReviewAgent` / `DocAgent` / `DataAgent`
5. `modes.py` STANDARD/BRAINSTORM/AUDIT 三模式 prompt 切换
6. `validate.py` 规则引擎（敏感词/格式/空输出）
7. `skill.py` Skill CRUD
8. `tools.py` @tool 装饰器 + 自动发现
9. `trace.py` 调用追踪
10. CLI: `mmi agent list/invoke`, `mmi skill list/create`
11. 测试:Agent 调度集成测试

预估：2-3d

前置依赖：本轮全部完成 ✅

---

## 7. 关键代码片段（速查）

### summarizer.py — 拆线程

```python
def _run() -> None:
    try:
        ok = update_summary(session_id, llm, language=language)
        if ok:
            _schedule_memory_store(session_id)   # 起独立线程
    except Exception:
        pass

def _schedule_memory_store(session_id: str) -> threading.Thread:
    """独立线程做入库,与 update_summary 解耦。"""
    def _run() -> None:
        try:
            body, turns_at = _read_body_for_memory(session_id)
            if not body: return
            memory_module.store_memory(session_id, body, turns_at=turns_at)
        except Exception: pass
    t = threading.Thread(target=_run, daemon=True, name=f"memstore-{session_id[:8]}")
    t.start()
    return t
```

### memory.py — 去重

```python
def store_memory(session_id, body, *, summary="", turns_at=0, embedder=None):
    if not body or not body.strip():
        return None
    body_hash = _content_hash(body)
    existing = _get_by_hash(body_hash)   # 命中 → 返旧 record
    if existing is not None:
        return existing
    # ... 原写入逻辑,带 content_hash ...
```

### memory.py — schema

```sql
CREATE TABLE memories (
    ...
    content_hash TEXT
);
CREATE INDEX idx_memories_hash ON memories(content_hash);
```

---

> 接手者先跑 §3 测试,看到 395 passed + ruff 0 即可接 Round 3.0。
