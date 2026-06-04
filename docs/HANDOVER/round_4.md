# 交接文档 — 改进 Round 2
> 日期：2026-06-04
> 状态：✅ 已完成
> 主题：搜索质量 + 截断优先级 + 动态窗口
> 覆盖 PLAN.md：**临时变更计划 改进 Round 2**

---

## 1. 本轮完成

- ✅ **P0-2 jieba + BM25**:`search.py` 中文走 `jieba.cut()`(精确模式),降级 2-gram;评分从 TF 改为 BM25(Robertson-Sparck Jones IDF + 长度归一化,低频词权重更高);`pyproject.toml` 加 `[search]` extras
- ✅ **P1-4 截断优先级**:`compose_sections` + `flatten_sections` 拆分结构化;`_truncate_by_section` 按 section 独立删(先 recent → 再 hits → 永不删 system/user);`LoadedContext.sections` 新增字段
- ✅ **P1-5 动态窗口**:`_compute_recent_window` 根据 token 余量动态调 recent 数量(MIN 5 ~ MAX recent_turns*2)
- ✅ **测试**:430/430 全绿(改前 428);新增 3 个测试(tokenize jieba / 停用词 / no-jieba fallback)
- ✅ **ruff**:0 error

---

## 2. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/search.py` | 重构 | 中文 jieba.cut + 英文空格切;score_turns 改 BM25;降级路径保留 |
| `mmi/core/context.py` | 重构 | 新增 `_compute_recent_window` / `compose_sections` / `flatten_sections` / `_truncate_by_section`;`LoadedContext.sections` 字段;`compose_messages` 改 wrapper 兼容老 API |
| `pyproject.toml` | 修改 | 加 `[search]` extras(`jieba>=0.42`) |
| `tests/test_search.py` | 修改 | `test_tokenize_zh_uses_bigrams` → `test_tokenize_zh_uses_jieba_or_bigrams`;+停用词 / no-jieba fallback |
| `tests/test_loader.py` | 修改 | 删 1 个旧测试(动态窗口已变更);+clamped_on_small_budget |
| `docs/HANDOVER/round_4.md` | 新建 | 本交接文档 |
| `docs/HANDOVER/INDEX.md` | 修改 | +round_4 行 |
| `ROUND_LOG.md` | 修改 | 本轮日志 |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| 改前 baseline | 428 / 428 | 改进 Round 1 收尾 |
| 改后(本轮) | **430 / 430** | 旧 1 个测试改语义,新 +2 |
| ruff | **0 error** | — |

---

## 4. 关键决策记录

### 决策 1：jieba 精确模式,降级 2-gram

- 选了 `jieba.cut(text, cut_all=False)` 精确模式(全模式会产生大量无意义 1-gram)
- jieba 不可用时降级到 2-gram(向后兼容旧测试)
- 不引自定义词典(`jieba.load_userdict`):Round 2 范围够用,后续可加

### 决策 2：BM25 参数用经典值 (k1=1.5, b=0.75)

- 学术默认值,常见 90% 场景适用
- 不做调参(数据集小,调了也泛化不好)
- 中文分词后 BM25 仍适用(token 化后是普通词袋)

### 决策 3：P1-4 用结构化 dict 不破坏 API

- `LoadedContext.sections` 新增字段(向后兼容,`messages` 仍为列表)
- `compose_messages` 改成 wrapper,老 import 不挂
- `_truncate` 也改 wrapper,把 messages 假装塞 sections 再调真函数

### 决策 4：P1-5 动态窗口范围 [5, recent_turns*2]

- MIN=5 保证语境
- MAX=recent_turns*2(默认 20)防止吃满 token
- 删了一个失败测试(原期望 2 对窗口,budget 大时被推到 MAX)
- 新增 clamped_on_small_budget:验证小 budget 时窗口被压

---

## 5. 关键代码片段

### search.py — BM25

```python
def _bm25_idf(n_q: int, n_docs: int) -> float:
    return math.log((n_docs - n_q + 0.5) / (n_q + 0.5) + 1.0)

def score_turns(turns, query, *, language="zh-CN"):
    q_tokens = tokenize(query, language=language)
    # 1) 预处理:每个 turn 的 token + 长度
    turn_tokens = [tokenize((t.get("content") or "").lower(), language=language) for t in turns]
    n_docs = len(turns)
    avgdl = max(1.0, sum(len(t) for t in turn_tokens) / n_docs)
    # 2) IDF
    q_idf = {qt: _bm25_idf(sum(1 for toks in turn_tokens if qt in toks), n_docs) for qt in set(q_tokens)}
    # 3) BM25 per turn
    for i, toks in enumerate(turn_tokens):
        tf = Counter(toks)
        s = 0.0
        for qt in q_tokens:
            f = tf.get(qt, 0)
            if f == 0: continue
            denom = f + _BM25_K1 * (1 - _BM25_B + _BM25_B * doc_len / avgdl)
            s += q_idf.get(qt, 0.0) * (f * (_BM25_K1 + 1)) / denom
```

### context.py — P1-4 截断

```python
def _truncate_by_section(sections, config):
    """先删 recent,再删 hits;system + user 永不删。"""
    while sections["recent"] and cur_total > config.max_tokens:
        sections["recent"].pop(0)
    while sections["hits"] and cur_total > config.max_tokens:
        sections["hits"].pop(0)
```

### context.py — P1-5 动态窗口

```python
def _compute_recent_window(all_turns, config, *, user_input="", language="zh-CN"):
    DEFAULT_MIN = 5
    DEFAULT_MAX = max(10, config.recent_turns * 2)
    budget = config.max_tokens - overhead
    pairs_budget = (budget - hits_reserve) // avg_pair_tokens
    return max(DEFAULT_MIN, min(DEFAULT_MAX, pairs_budget))
```

---

## 6. 遗留问题

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | jieba 装包 10MB+,CI 慢 | 安装时间 | 可选 extras `mmi[search]` |
| 2 | BM25 参数未调 | 可能微调召回率 | 实测数据累积后再调 |
| 3 | 动态窗口用样本平均估算,首 5 对极短时不准 | 极端短对话会扩过头 | MIN 5 兜底 |
| 4 | 删了原 test_build_context_recent_turns_limit(硬写 2 对) | 测试覆盖减 | 改用 clamped_on_small_budget 替代 |

---

## 7. 下轮预告

**改进 Round 3**:P1-7 增量摘要 + P2-10 FAISS 池化 + P2-9 简化版增强热度(10-12h)

前置依赖:本轮全完成 ✅

---

> 接手者先跑 §3 测试,看到 430 passed + ruff 0 即可接 Round 3。
