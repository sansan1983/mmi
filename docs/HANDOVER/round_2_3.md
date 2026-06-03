# 交接文档 — Round 2.3
> 日期：2026-06-04
> 状态：✅ 已完成
> 主题：memory 接通 chat 自动入库 + LLM 摘要升级 + FTS5 双路召回
> 覆盖 PLAN.md：**2.5**(补 Round 2.2 漏掉的 build_structured_summary LLM 版)
> 顺手清:cli.py 重复 if + FTS5 schema + 12 个新测试

---

## 1. 本轮完成

- ✅ **summarizer 自动入库**：`schedule_summary_update` 后台线程成功生成摘要后，自动调 `memory.store_memory`（失败静默，不阻塞主流程）
- ✅ **build_structured_summary 升级**：新增 LLM 提取版（抽 `{title, decision, conclusion, todos}` 四字段），失败自动降级到规则版
- ✅ **FTS5 双路召回**：SQLite 加 `memories_fts` 虚拟表 + AI/AU/AD 触发器自动同步；`search_semantic` 改为 FAISS + FTS5 双路召回、按 memory_id 去重、FAISS 优先
- ✅ **cli.py 清理**：去掉重复的 `if info` / `if rename` 分支
- ✅ **+12 个新测试**：LLM summary 4 + FTS5 7 + auto-store 1
- ✅ **全量 387/387 全绿**（改前 375）

---

## 2. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/summarizer.py` | 修改 | `schedule_summary_update` 后台线程成功后自动 `store_memory`；加 `_read_body_for_memory` 辅助 |
| `mmi/core/memory.py` | 修改 | `build_structured_summary` 加 LLM 版 + 降级；FTS5 schema + 触发器；`_search_fts` / `_sanitize_fts_query`；`search_semantic` 双路召回 + 去重 |
| `mmi/cli.py` | 修改 | 去掉 `if info` / `if rename` 重复分支 |
| `tests/test_memory.py` | 修改 | +12 个测试（LLM summary、FTS5、auto-store）|
| `ROUND_LOG.md` | 更新 | 本轮日志 |
| `docs/HANDOVER/round_2_3.md` | 新建 | 本交接文档 |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| 改前 baseline | 375 / 375 | Round 2.2 收尾 |
| 改后(本轮) | **387 / 387** | +12 memory tests |
| 跑全量含 CLI | 387 + 3 skip | CLI 集成需 `~/.mmi-fusion` 预置,跳过 |

跑法：
```bash
python3 -m venv /tmp/mmi-venv
/tmp/mmi-venv/bin/pip install -e ".[test,memory,tui]" rapidfuzz
/tmp/mmi-venv/bin/python -m pytest tests/ -q --ignore=tests/test_cli.py
```

---

## 4. 关键决策记录

### 决策 1：FTS5 触发器自动同步(放弃手工 DELETE/INSERT)

- **方案 A**(采用)：用 `AFTER INSERT/UPDATE/DELETE` triggers 自动维护 `memories_fts`
- **方案 B**：手工在 `store_memory` 里 `DELETE + INSERT` 同步 FTS5
- **理由**：
  - 方案 B 跑测试时直接触发 `sqlite3.DatabaseError: database disk image is malformed` ——FTS5 external content 模式禁止在 content 表里没有对应 row 时 DELETE/INSERT
  - 方案 A 触发器是 SQLite 官方推荐方式,与 `content='memories'` 模式完全兼容
  - 触发器一加,store_memory 不用关心 FTS5,代码更清晰

### 决策 2：search_semantic 双路召回(FAISS 优先)

- **方案 A**(采用)：FAISS 召 top_k → FTS5 召 top_k → 按 memory_id 去重 → FAISS 命中的排前
- **方案 B**：FAISS + FTS5 评分合并(rank fusion)
- **理由**：
  - 方案 B 实现复杂(归一化评分),不一定更准
  - 方案 A 简单,FAISS 语义近邻更准,排前合理;FTS5 关键词补盲(专有名词 / 缩写)
  - 后续要升级到 B 也很容易(只改 search_semantic 内部)

### 决策 3：LLM summary 失败降级到规则版(用原 body,不用 LLM 输出)

- **方案 A**(采用)：JSON 解析失败 / LLM 异常 → 传原 body 走规则版
- **方案 B**：JSON 解析失败时用 LLM 的 raw 输出当 title
- **理由**：
  - 方案 B 会出现"title = '不是 JSON,就是乱说'"这种污染
  - 方案 A 用原 body 降级 → title 至少是 markdown 标题(干净的)
  - 实际业务里,L2 摘要的 LLM 失败率不为零,降级是必备

### 决策 4：summarizer 后台线程串行做摘要 + 入库

- **方案 A**(采用)：同一后台线程先 update_summary,成功后 store_memory
- **方案 B**：摘要 + 入库分两个独立后台线程
- **理由**：
  - 入库需要 body + turns_at,得从磁盘读;摘要也得读 body → 两个线程重复读 IO
  - 串行做的话,IO 一次,逻辑清晰
  - 入库失败不影响摘要(已经在内存写好了),反之亦然

---

## 5. 遗留问题

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | 70 个 ruff error(全是既有 unused import / F841) | 质量门禁未达 0 error | 单独开一轮清 |
| 2 | FTS5 query sanitizer 简化版,不支持 NEAR/列查询 | 复杂 query 表达受限 | Round 2.4 升级 |
| 3 | LLM 提取 prompt 可调优 | 提取质量取决于 prompt 细节 | 实测数据后调 |
| 4 | 自动入库与 summarizer 串行,高频 chat 场景下入库成瓶颈 | 大流量时摘要后入库会拖慢 | Round 2.4 拆成独立触发器 |
| 5 | 写入路径未防抖(每次 chat 都入库一条) | 重复内容可能堆积 | Round 2.4 加去重(基于 hash) |

---

## 6. 下轮计划(候选)

**A. Round 3.0 — 多 Agent 调度骨架**
- 实现 `Orchestrator.chat()` 完整流程
- 实现 `Router` 意图分类(规则 + LLM)
- 实现 `Registry` Agent 注册/匹配
- 内置 3 个 Agent:CodeReview / Doc / Data(填充骨架)
- 预估：2-3d

**B. Round 2.4 — memory 写入优化**
- 入库拆成独立后台线程(独立触发器)
- 加内容 hash 去重
- 批量入库(每 N 条一次写盘)
- 预估：0.5d

**优先建议**：先做 2.4(0.5d,把 memory 收尾),再做 3.0(2-3d,开新阶段)

前置依赖：本轮全部完成 ✅

---

## 7. 关键代码片段（速查）

### summarizer.py — 自动入库

```python
def _run() -> None:
    try:
        body, turns_at = _read_body_for_memory(session_id)
        ok = update_summary(session_id, llm, language=language)
        if ok and body:
            from . import memory as memory_module
            try:
                memory_module.store_memory(session_id, body, turns_at=turns_at)
            except Exception:
                pass  # 记忆入库失败不抛:摘要是关键路径,记忆是锦上添花
    except Exception:
        pass  # 后台线程:任何异常都吞掉
```

### memory.py — FTS5 schema + 触发器

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    title, decision, conclusion, todos, raw_excerpt,
    content='memories', content_rowid='rowid', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES (new.rowid, new.title, new.decision, new.conclusion, new.todos, new.raw_excerpt);
END;
-- AU / AD 类似
```

### memory.py — search_semantic 双路召回

```python
def search_semantic(query, *, top_k=20, embedder=None):
    faiss_hits = _search_faiss(query, top_k=top_k, embedder=embedder) or []
    fts_hits = _search_fts(query, top_k=top_k) or []
    seen = set()
    merged = []
    for c in faiss_hits + fts_hits:        # FAISS 优先
        if c.memory_id in seen: continue
        seen.add(c.memory_id)
        merged.append(c)
        if len(merged) >= top_k: break
    return merged
```

### memory.py — LLM summary 降级

```python
def _parse_structured_json(raw, *, body_for_fallback):
    # ... 抠 JSON ...
    if not valid_json:
        return _build_structured_summary_rules(body_for_fallback)  # 用原 body,不用 raw
    return {...字段...}
```

---

> 接手者先跑 §3 测试,看到 387 passed 即可接 Round 2.4 或 3.0。
