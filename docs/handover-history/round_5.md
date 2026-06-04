# 交接文档 — 改进 Round 3
> 日期：2026-06-04
> 状态：✅ 已完成
> 主题：性能与智能增强 — 增量摘要 + FAISS 池化 + 简化版热度
> 覆盖 PLAN.md：**临时变更计划 改进 Round 3**

---

## 1. 本轮完成

- ✅ **P1-7 增量摘要**:`update_summary` 改增量模式(只发新增 turns),每 100 轮强制全量重建防漂移;新增 `_extract_new_turns` 辅助
- ✅ **P2-10 FAISS 池化**:`_INMEM_INDEX` 模块单例,lazy load + 节流 flush(50 条阈值);`_ensure_loaded` / `_maybe_flush` / `flush_faiss` 三件套
- ✅ **P2-9 简化版热度**:`compute_heat` 加 `content_bonus`(turn 数加成,封顶 +2);`apply_heat_and_state` + `manager.chat` 传 `total_turns`
- ✅ **测试**:439/439 全绿(改前 430);+9 个新测试
- ✅ **ruff**:0 error

---

## 2. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/summarizer.py` | 修改 | `FULL_REBUILD_EVERY=100` 常量;`update_summary` 增量/全量分支;`_extract_new_turns` 辅助;`_build_summary_input` 加 `incremental` 参数 |
| `mmi/core/memory.py` | 重构 | `_INMEM_INDEX` 池;`_ensure_loaded` lazy load;`_maybe_flush` 节流;`flush_faiss` 显式;store_memory 走池;`_search_faiss` 走池;clear_memories 重置池 |
| `mmi/core/heat.py` | 修改 | `compute_heat` 加 `total_turns` 参数 + content_bonus;`apply_heat_and_state` 加同参 |
| `mmi/core/manager.py` | 修改 | `_recompute_heat` 传 `total_turns=s.body.count("**User:**")` |
| `tests/test_memory.py` | 修改 | +9 个测试(FAISS 池 4 + 增量摘要 3 + 热度 2) |
| `docs/HANDOVER/round_5.md` | 新建 | 本交接文档 |
| `docs/HANDOVER/INDEX.md` | 修改 | +round_5 行 |
| `ROUND_LOG.md` | 修改 | 本轮日志 |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| 改前 baseline | 430 / 430 | 改进 Round 2 收尾 |
| 改后(本轮) | **439 / 439** | +9 net new |
| ruff | **0 error** | — |

---

## 4. 关键决策记录

### 决策 1：P1-7 增量触发条件 — `current_turns - last_t >= 100` 走全量

- 简单阈值,每 100 轮兜底
- 防漂移:每 100 轮新摘要"重新校准"全文
- 增量 prompt 明确告诉 LLM "这是新增对话",LLM 不会困惑

### 决策 2：P2-10 池化阈值 FLUSH_THRESHOLD=50

- 50 条一次性写盘,IO 量从 N 次降到 N/50 次
- 1000 轮 chat → 20 次写盘(改前 1000 次)
- 内存增长:64 维 * 4 bytes * 50 = 12.8KB,完全可接受
- 进程崩溃容忍:已 commit 到 SQLite 的 record 是权威,启动时从磁盘读完整索引

### 决策 3：P2-9 用加法而不是乘法

- 乘法:0 turn → heat 0 → 状态推导会乱(全 cold)
- 加法:基础 heat 不变,长对话额外 +0~2 bonus,state 仍按 base heat 推
- `content_bonus = min(2.0, total_turns / 25)` → 50 轮封顶 +2
- 简单可解释,无需调参

---

## 5. 关键代码片段

### summarizer.py — 增量

```python
FULL_REBUILD_EVERY = 100

def update_summary(...):
    last_t = last_summary_turns(meta)
    current_turns = body.count("**User:**")
    is_full = (last_t == 0) or (current_turns - last_t >= FULL_REBUILD_EVERY)
    if is_full:
        new_body = body
    else:
        new_body = _extract_new_turns(body, last_t)
    user_msg = _build_summary_input(meta.summary, new_body, language=language, incremental=not is_full)
    # ... 同 LLM + 写盘
```

### memory.py — 池

```python
_INMEM_INDEX = None
_INMEM_IDS: list[str] = []
_INMEM_DIRTY: int = 0
FLUSH_THRESHOLD = 50

def _ensure_loaded(dim):
    global _INMEM_INDEX, _INMEM_IDS, _INMEM_DIM, _INMEM_LOADED
    if _INMEM_LOADED and _INMEM_DIM == dim: return
    with _INMEM_LOCK:
        ...
        _INMEM_INDEX = _load_faiss_index(dim)
        _INMEM_IDS = _load_faiss_ids()
        _INMEM_LOADED = True

def _maybe_flush():
    if _INMEM_DIRTY < FLUSH_THRESHOLD: return
    with _INMEM_LOCK:
        _save_faiss_index(_INMEM_INDEX)
        _save_faiss_ids(_INMEM_IDS)
        _INMEM_DIRTY = 0
```

### heat.py — 简化版加成

```python
def compute_heat(*, total_turns=0, ...):
    raw = access_count * 1.0 + recency_bonus - age_penalty
    content_bonus = min(2.0, max(0.0, total_turns) / 25.0)
    return raw + content_bonus
```

---

## 6. 遗留问题

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | FAISS 池在多个测试间需 reset | 已有 `reset_for_test` | OK |
| 2 | 增量摘要的 LLM 质量 < 全量 | 长对话摘要可能漏早期细节 | 100 轮兜底 |
| 3 | 简化版热度只看 turn 数,不看内容质量 | 闲聊 50 轮也 +2 | 后续接 LLM 提取重要度 |
| 4 | 池化维度切换会重建索引,旧向量丢失 | 用户切模型丢历史 | 暂可接受;后续按维度多索引 |

---

## 7. 下轮预告

**改进 Round 4**(可选):P1-6 上下文增量缓存 — 长对话性能(5-6h,投出比存疑)

或:**三期 3.0 多 Agent 调度**(PLAN.md 三期) — 收尾整个 mmi 路线图

按时间投入,建议:**先三期 3.0**(多 Agent 调度是 mmi 核心能力,不可缺)

---

> 接手者先跑 §3 测试,看到 439 passed + ruff 0 即可接 Round 4 或三期。
