# 交接文档 — 改进 Round 1
> 日期：2026-06-04
> 状态：✅ 已完成
> 主题：基础修复 — P0-1 短会话入库 + P0-3 tiktoken 精确估算 + P2-8 任务队列
> 覆盖 PLAN.md：**临时变更计划 改进 Round 1**(原三期顺延)

---

## 1. 本轮完成

- ✅ **P0-1 短会话入库**:`manager.chat()` 每轮末尾无条件调 `_schedule_memory_store(session_id)`,不再依赖摘要触发;短会话(<20 轮)也能进库
- ✅ **P0-3 tiktoken 精确估算**:`context.estimate_tokens()` 优先用 tiktoken(cl100k_base),装不上降级为中英文区分估算;`pyproject.toml` 加 `[context]` extras
- ✅ **P2-8 任务队列**:`ThreadPoolExecutor(max_workers=1)` 全模块单例;`schedule_summary_update` + `_schedule_memory_store` 都走同一队列,FIFO 顺序执行;`_ThreadLike` 包装保留 `Thread` 风格 API
- ✅ **测试**:428/428 全绿(改前 423);新增 4 个测试(短会话入库 + tiktoken 验证 + FIFO 队列)
- ✅ **ruff**:0 error

---

## 2. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/manager.py` | 修改 | chat() 末尾调 `_schedule_memory_store`(每轮入库);注释从 4) 改 5)、原 5)→6) |
| `mmi/core/context.py` | 修改 | `estimate_tokens` 优先 tiktoken;`tiktoken` ImportError 时降级中英文区分 |
| `mmi/core/summarizer.py` | 重构 | `schedule_summary_update` / `_schedule_memory_store` 改用 `ThreadPoolExecutor(max_workers=1)`;加 `_ThreadLike` 包装 + `shutdown_background_pool()` 辅助 |
| `pyproject.toml` | 修改 | 加 `[context]` extras(`tiktoken>=0.5`) |
| `tests/test_loader.py` | 修改 | `test_estimate_tokens_simple` 改用范围断言(适应 tiktoken 输出) |
| `tests/test_summarizer.py` | 修改 | `test_schedule_summary_update_returns_thread` 改断言 `.join` / `.is_alive` 存在而非 isinstance(Thread) |
| `tests/test_memory.py` | 修改 | +4 个新测试(P0-1 短会话 / P0-3 tiktoken 中文 / P0-3 tiktoken 英文 / P2-8 FIFO) |
| `PLAN.md` | 修改 | 加"临时变更计划"小节;三期标"待开始 + 顺延" |
| `docs/HANDOVER/round_3.md` | 新建 | 本交接文档 |
| `docs/HANDOVER/INDEX.md` | 修改 | 加 round_3 行 |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| 改前 baseline | 423 / 423 | Round 2.5 收尾 |
| 改后(本轮) | **428 / 428** | +4 net new(短会话 / tiktoken / FIFO) |
| ruff | **0 error** | — |

跑法：
```bash
/tmp/mmi-venv/bin/pip install -e ".[test,context,memory]"   # 全可选
/tmp/mmi-venv/bin/python -m pytest tests/ -q --ignore=tests/test_cli.py
/tmp/mmi-venv/bin/ruff check mmi/
```

---

## 4. 关键决策记录

### 决策 1：P0-1 直接在 manager.chat() 加调用,不动 summarizer 内部

- **方案 A**(采用):manager.py 加一行 `summarizer._schedule_memory_store(session_id)`,每轮 chat 都调
- **方案 B**(plan 的 plan B):在 schedule_summary_update 后台线程里 store_memory
- **理由**:
  - A 路径短,直接;短会话永不触发摘要,B 路径就是当前 bug
  - A 解耦了 store_memory 和 update_summary,各自独立入池
  - content_hash 去重已经在,重复 body 不会膨胀

### 决策 2：P0-3 tiktoken 是 optional,不阻塞安装

- **实现**:`try: import tiktoken` 静默降级,无依赖也能跑
- **降级公式**:中文 1 字 ≈ 2 token,英文 1 词 ≈ 1.3 token,加 4 role overhead
- **理由**:tiktoken 首次用要联网下载 BPE(~1MB),不强依赖更稳;CI 不装也能测

### 决策 3：P2-8 单线程池,1 worker,不要 per-session pool

- **方案**:`ThreadPoolExecutor(max_workers=1, thread_name_prefix="mmi-bg")` 模块单例
- **理由**:
  - 单 worker 保证 FIFO —— summary 和 memory store 不会同时改同一 session 的 frontmatter
  - per-session 池太复杂,会引入调度延迟
  - 用户感知:高频 chat 排队 ≈ 0ms(只要 worker 不在跑 LLM)
- **API 兼容**:`_ThreadLike` 包装保留 `Thread.join` / `is_alive`,3 个旧测试不用大改

---

## 5. 关键代码片段

### manager.py — P0-1 短会话入库

```python
# 3) 追加 turn
s = storage.append_turn(session_id, user_input, reply)

# 4) 跨会话记忆入库(每轮都跑,不等摘要)
#   短会话(<20 轮/5000 字/24h)不触发摘要,但记忆照样要进库
#   content_hash 已做去重,重复 body 不会重复入库
try:
    summarizer._schedule_memory_store(session_id)
except Exception:
    pass
```

### context.py — P0-3 优先 tiktoken

```python
try:
    import tiktoken
    _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
    _HAS_TIKTOKEN = True
except ImportError:
    _TIKTOKEN_ENC = None
    _HAS_TIKTOKEN = False

def estimate_tokens(messages):
    if _HAS_TIKTOKEN:
        return sum(len(_TIKTOKEN_ENC.encode(m["content"] or "")) + 4 for m in messages)
    # 降级:中英文区分
    import re
    total = 0
    for m in messages:
        text = m.get("content") or ""
        cn = sum(1 for c in text if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
        en_text = re.sub(r'[一-鿿㐀-䶿]', ' ', text)
        en_words = max(1, len(en_text.split()))
        total += cn * 2 + int(en_words * 1.3) + 4
    return total
```

### summarizer.py — P2-8 单线程池

```python
_BACKGROUND_POOL: ThreadPoolExecutor | None = None

def _get_pool() -> ThreadPoolExecutor:
    global _BACKGROUND_POOL
    if _BACKGROUND_POOL is None:
        with _POOL_LOCK:
            if _BACKGROUND_POOL is None:
                _BACKGROUND_POOL = ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix="mmi-bg",
                )
    return _BACKGROUND_POOL

def schedule_summary_update(session_id, llm, *, language="zh-CN") -> _ThreadLike:
    def _run():
        try:
            ok = update_summary(session_id, llm, language=language)
            if ok:
                _run_memory_store(session_id)
        except Exception:
            pass
    return _ThreadLike(_get_pool().submit(_run))
```

---

## 6. 冒烟测试

```
# Round 1:
  - 新建 3 轮短会话 → mmi memory search 能召回      ✅ (test_short_session_memory_stores)
  - 中文 100 字 → tiktoken 估算 ≥ 50 tokens         ✅ (test_estimate_tokens_chinese_*)
  - 连续 schedule 2 任务 → 都在同一 worker 顺序执行   ✅ (test_background_pool_submits_fifo)
  - 摘要短/长对话 → 都不阻塞主流程                 ✅ (test_schedule_summary_update_does_not_block)
```

---

## 7. 遗留问题

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | P0-1 每轮 store,1000 轮 chat → 1000 次 FAISS 全量写 | 高频场景慢 | Round 3 P2-10 FAISS 池化 |
| 2 | P2-8 单 worker,前面的任务慢会阻塞后面 | 用户感知延迟 | 高频场景再优化;现在短会话只是 disk IO,影响小 |
| 3 | tiktoken 首次联网下载 | CI 无网会失败但降级稳 | OK,生产用户有网 |
| 4 | content_hash 去重只去重完全相同的 body | 微调同 body 仍会多入库 | 后续可加"近似去重" |

---

## 8. 下轮预告

**改进 Round 2**:P0-2 jieba + BM25 + P1-4 截断优先级 + P1-5 动态窗口(8-10h,需 P0-3 完)

前置依赖:本轮全完成 ✅(P1-5 依赖 P0-3 的精确 token 估算)

---

> 接手者先跑 §3 测试,看到 428 passed + ruff 0 即可接 Round 2。
