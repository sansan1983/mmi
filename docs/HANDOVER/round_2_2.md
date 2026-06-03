# 交接文档 — Round 2.2
> 日期：2026-06-03
> 状态：✅ 已完成
> 主题：向量记忆(FAISS)落地 + context 集成 + CLI 接入

---

## 1. 本轮完成

- ✅ 装 `faiss-cpu` + `sentence-transformers`(`pyproject.toml` 加 `memory` extras)
- ✅ `mmi/core/memory.py` 全量实现(430+ 行)
  - `Embedder` Protocol + `HashEmbedder`(测试/降级) + `SentenceTransformerEmbedder`(生产)
  - `MemoryRecord` 数据类 + `MemoryConfig` 配置
  - SQLite `memories` 表(元数据)+ FAISS index(向量)+ `faiss_ids.json`(位置→id 映射)
  - `store_memory` / `search_semantic` / `rerank` / `build_structured_summary` / `recall_memories`
  - `memory_count` / `clear_memories` / `reset_for_test`
- ✅ `mmi/core/context.py` 集成
  - `LoaderConfig.memory: MemoryConfig` 字段
  - `_load_intermediate` 末尾按需调 `recall_memories` (静默降级)
  - `compose_messages` 把 recall 段拼到 system prompt
  - 修了空 session 早退 bug(让 memory 在 0-turn session 也能跑)
- ✅ `mmi/cli.py` 新增 `mmi memory {search|count|clear}` 子命令
- ✅ `tests/test_memory.py` 24 个测试(Hash 假嵌入器,无需下载模型)
- ✅ 全量 **375/375 全绿**(改前 351)

---

## 2. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/memory.py` | 新建 | 完整向量记忆模块 |
| `mmi/core/paths.py` | 修改 | 加 `get_memory_db_path` / `get_faiss_index_path` / `get_faiss_ids_path` |
| `mmi/core/context.py` | 修改 | `LoaderConfig.memory` 字段 + `_load_intermediate` 集成 + `compose_messages` 注入 |
| `mmi/cli.py` | 修改 | `memory` 子命令 + `cmd_memory` 实现 |
| `pyproject.toml` | 修改 | 加 `[memory]` extras(`faiss-cpu` + `numpy`) |
| `tests/test_memory.py` | 新建 | 24 个单元 + 集成测试 |
| `ROUND_LOG.md` | 更新 | 本轮日志 |
| `docs/HANDOVER/round_2_2.md` | 新建 | 本交接文档 |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| 改前 baseline | 351 / 351 | Round 2.1 收尾 |
| 改后(本轮) | **375 / 375** | +24 memory tests |
| 改后含 CLI | 375 + 3 skip | CLI 集成测试需 `~/.mmi-fusion` 预置,环境依赖,跳过 |

跑法：
```bash
# 装依赖(含 memory)
python3 -m venv /tmp/mmi-venv
/tmp/mmi-venv/bin/pip install -e ".[test,memory,tui]" rapidfuzz

# 跑测试
/tmp/mmi-venv/bin/python -m pytest tests/ -q --ignore=tests/test_cli.py
```

---

## 4. 关键决策记录

### 决策 1：嵌入器可注入 + 失败降级

- **方案 A**(采用)：默认 `SentenceTransformerEmbedder`(`all-MiniLM-L6-v2`,本地),任何加载失败 → 降级到 `HashEmbedder`(sha256 切片,64 维,完全可复现,无外部依赖)
- **方案 B**：固定走 OpenAI `text-embedding-3-small`(架构文档原方案)
- **理由**：
  - 嵌入是高频操作,本地比 API 调用快 + 零成本 + 不需要 API key
  - 测试用 `HashEmbedder` 避免下载模型(CI 友好)
  - 失败降级保证即使离线也不阻塞主流程
  - 后续要换 OpenAI 只需 `set_embedder(...)` 注入

### 决策 2：SQLite 元数据 + FAISS 向量 + JSON id 映射(三个文件)

- **方案 A**(采用)：三个文件:`memory.db` / `faiss.index` / `faiss_ids.json`
- **方案 B**：单一 SQLite 存所有(向量 BLOB)
- **理由**：
  - FAISS 索引用 `write_index` / `read_index` 原生序列化,JSON 映射只存 list[str],都极快
  - SQLite 索引 `session_id` / `created_at` 方便后续按 session 反查
  - FAISS `IndexFlatL2` 起步,小规模够用;规模上去后切 HNSW 也只换 index 格式

### 决策 3：rerank 容错策略

- **方案 A**(采用)：LLM 异常/返回未知 id → 退回 FAISS 原顺序补齐;无 LLM → 直接按 FAISS 顺序截 top_n
- **方案 B**：rerank 失败抛异常,主流程感知
- **理由**：
  - rerank 是"锦上添花",不是关键路径
  - LLM 输出格式不稳定(测试里 mock 各种异常情况),容错保证可降级
  - 主流程(chat)不应该被 rerank 异常阻塞

### 决策 4：build_structured_summary 规则版(暂不调 LLM)

- **方案 A**(采用)：从 markdown 头/尾提 title + conclusion,其余留空
- **方案 B**：直接调 LLM 提取 {主题, 决策, 结论, 待办}
- **理由**：
  - Round 2.2 范围是"向量记忆落地",不重复 Round 3 的 LLM 提取
  - 规则版稳定可测,先满足"能存能检索"
  - Round 2.3 接 chat 末尾自动入库时再升级为 LLM 版(那时能复用 chat 的 LLM 实例)

### 决策 5：context 空 session 早退 bug 修复

- **原代码**：`if not all_turns: return ctx` 在 `_load_intermediate` 顶部 → 0-turn session 完全跳过 memory recall
- **新代码**：把 turns 处理包到 `if all_turns:` 里,memory recall 移到外面独立判断
- **影响**：新会话第一轮提问就能注入跨会话记忆(原行为会丢失这个机会)

---

## 5. 遗留问题

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | `build_structured_summary` 规则版只提 title + conclusion | 没真做 LLM 提取,记忆检索质量受限 | Round 2.3 升级 LLM 版 |
| 2 | FTS5 路径未实现(架构文档提了,本轮只做 FAISS) | 关键词检索精度有限 | Round 2.3 加 |
| 3 | 70 个 ruff error(全是既有 unused import / F841) | 质量门禁未达 0 error | 单独开一轮清 |
| 4 | `store_memory` 未接到 chat 末尾 | 需手动调才有记忆 | Round 2.3 接 summarizer 后台线程 |
| 5 | `cli.py` 子命令分发有几处重复 if(`info` / `rename` 出现两次) | 不影响功能,代码冗余 | 下轮整理 |

---

## 6. 下轮计划

**Round 2.3 — memory 接通 chat + 升级 LLM 摘要 + FTS5**

任务：
1. `summarizer.update_summary` 完成后自动调 `memory.store_memory`(后台线程,失败静默)
2. `build_structured_summary` 升级为 LLM 提取版(`mmi/core/llm` 已能调)
3. 加 FTS5 虚拟表到 `memory.db`,`search_semantic` 双路召回(FAISS top-20 + FTS5 top-10 → 合并去重 → top-K)
4. 整理 `cli.py` 重复 if
5. 测试补充(自动入库 + FTS5 双路)
6. 跑全量 + 写交接

预估：1d

前置依赖：本轮全部完成 ✅

---

## 7. 关键代码片段（速查）

### memory.py — store_memory 核心流程

```python
def store_memory(session_id, body, *, summary="", turns_at=0, embedder=None):
    emb = embedder or get_embedder()
    struct = build_structured_summary(body)
    memory_id = new_session_id()        # ULID
    text_to_embed = " ".join([struct["title"], struct["conclusion"],
                              (summary or body)[:300]]).strip() or session_id
    vector = emb.embed(text_to_embed)    # 失败 → []
    record = MemoryRecord(memory_id, session_id, ...)
    # 1) SQLite 写元数据（始终）
    with _db_lock:
        conn.execute("INSERT OR REPLACE INTO memories (...) VALUES (?, ...)", ...)
        conn.commit()
    # 2) FAISS 写向量（仅在 embedding 成功时）
    if vector:
        with _faiss_lock:
            idx = _load_faiss_index(emb.dim)
            ids = _load_faiss_ids()
            idx.add(np.array([vector], dtype="float32"))
            ids.append(memory_id)
            _save_faiss_index(idx); _save_faiss_ids(ids)
    return record
```

### context.py — 集成段(修早退)

```python
all_turns = storage.parse_turns(session.body) if session else []
if all_turns:
    # 3) 最近 N 轮
    recent_pairs = _take_last_pairs(all_turns, config.recent_turns)
    ctx.recent_turns = recent_pairs
    # 4) 关键词命中
    older = all_turns[: max(0, len(all_turns) - len(recent_pairs))]
    if older and user_input and config.hit_paragraphs > 0:
        ctx.hit_turns = search.search_top_k(older, user_input, k=...)

# 5) 跨会话记忆（不依赖本 session 有 turns）
if config.memory.enabled and user_input:
    try:
        ctx.recalled_memories = recall_memories(user_input, config=config.memory)
    except Exception:
        ctx.recalled_memories = []   # 静默降级,不阻塞主流程
```

### CLI 用法

```bash
$ mmi memory count
当前记忆条数: 0

$ mmi memory search postgres 分表
找到 2 条与「postgres 分表」相关的记忆:
  [1] 01KT6...
      标题:   postgres 分表
      结论:   讨论 hash 策略。
      来源:   session s1 (turns=5)
      时间:   2026-06-03T14:19:48.473Z
  [2] ...

$ mmi memory clear --yes   # 清空
```

---

> 接手者先跑 §3 测试,看到 375 passed 即可接 Round 2.3。
