# MMI 记忆与上下文机制 — 修复改进计划

> 版本：v1.0 | 2026-06-04
> 范围：memory / context / search / heat / summarizer / gc 模块
> 定位：在现有架构基础上的可落地改进，不重构整体设计

---

## 总览

| 优先级 | 数量 | 影响面 |
|--------|------|--------|
| 🔴 P0（必须修） | 3 | 跨会话记忆有效性、中文搜索质量、Token 预算准确度 |
| 🟡 P1（应该修） | 4 | 截断一致性、窗口灵活性、性能、摘要成本 |
| 🟠 P2（值得修） | 3 | 竞态安全、热度语义、FAISS 性能 |

---

## 一、P0 优先级 — 必须修复

### P0-1: 打通短会话的跨会话记忆入库

**问题**：`store_memory()` 只在摘要触发时才被调用，短会话（<20 轮、<5000 字、<24h）永远无法进入向量记忆库。

**修复方案**：

```
修改点：summarizer.py 中 schedule_summary_update() 的调用链路

方案 A（推荐）：
  在 manager.chat() 的每轮循环末尾，无论是否触发摘要更新，
  都调用 _schedule_memory_store(session_id) 入库当前轮。
  
  入库逻辑改为：
    - 对每轮 turn 单独做 embedding + 结构化摘要
    - 存入 memory.db 和 FAISS
    - 不再依赖摘要触发条件

方案 B（保守）：
  在 schedule_summary_update() 的后台线程中，
  先执行 store_memory()，再执行 update_summary()。
  这样即使摘要更新失败，记忆入库也已完成。
```

**修改文件**：`mmi/core/summarizer.py`、`mmi/core/manager.py`

**预估工作量**：1 小时

**测试**：
- 新建一个 3 轮的会话 → 退出
- 新建另一个会话，问"上次说的方案X是什么" → 应能召回

---

### P0-2: 升级中文检索 — jieba + BM25

**问题**：`search.py` 用 2-gram 分词，`"案讨"` 等无意义片段污染搜索结果。

**修复方案**：

```
替换：search.py 的 tokenize() 和 _score_turns()

1. 分词升级：
   中文 → jieba.cut()（支持自定义词典）
   英文 → 空格分词
   停用词 → 保留现有的中英文停用词表

2. 评分升级：
   从 TF 分 → BM25 分
   引入 IDFM 因子：低频关键词权重更高
   公式：score = BM25(query_terms, turn_text)

3. 可选升级（Phase 2）：
   添加 rapidfuzz 模糊匹配，支持拼写容错
```

**依赖**：`pip install jieba`（可选 `rapidfuzz`）

**修改文件**：`mmi/core/search.py`

**预估工作量**：3 小时（含测试）

**测试**：
- 搜索"项目方案" → 不应召回"案讨"相关的无关段落
- 中英混杂搜索"review PR" → 两个词都应有贡献

---

### P0-3: 引入精确 Token 估算

**问题**：`context.py` 用 1 token ≈ 2 字符，中文实际 1 字 ≈ 1.5~2.5 token，估算严重不准。

**修复方案**：

```
替换：context.py 的 estimate_tokens()

1. 首选方案（推荐）：
   使用 tiktoken 精确计算：
     pip install tiktoken
     encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4o 用
     num_tokens = len(encoding.encode(text))

2. 降级方案（不安装 tiktoken 时）：
   区分中英文：
     中文 1 字 ≈ 2 token
     英文 1 词 ≈ 1.3 token
   用正则分别统计后相加
```

**修改文件**：`mmi/core/context.py`

**预估工作量**：1 小时

**测试**：
- 4000 字符中文文本 → tiktoken 估算应接近真实值
- 截断后总 token 应 ≤ budget

---

## 二、P1 优先级 — 应该修复

### P1-4: 修复截断优先级 — 区分 hits 和 recent

**问题**：`context.py` 的 `_truncate()` 无法区分 hits 和 recent，截断顺序与设计意图不符。

**修复方案**：

```
修改点：context.py 的 compose_messages()

1. 返回结构化消息列表，而非扁平列表：
   messages = {
       "system": [...],
       "hits": [...],
       "recent": [...],
       "user": [...]
   }

2. _truncate() 改为按优先级截断：
   for section in ["recent", "hits"]:  # 先删 recent，再删 hits
       truncate_section(messages[section])

3. 最后再 flatten 成 LLM 需要的列表格式
```

**修改文件**：`mmi/core/context.py`

**预估工作量**：3 小时（涉及函数签名变更，需同步更新 manager.py）

**测试**：
- 构造一个 hits > recent 的场景 → 截断后应保留更多 hits

---

### P1-5: 动态最近轮窗口

**问题**：固定 10 轮，长对话不够用，短对话浪费 token。

**修复方案**：

```
修改点：context.py 的 build_context_detailed()

1. 根据 token 余量动态调整：
   remaining = budget - system_tokens - hits_tokens - user_tokens
   recent_turns = min(
       max(5, remaining // avg_turn_tokens),
       DEFAULT_RECENT_TURNS * 2
   )

2. 可选：根据对话节奏自适应
   如果最近 N 轮都在讨论同一话题 → 扩大窗口
   如果话题频繁切换 → 缩小窗口（聚焦最近）
```

**修改文件**：`mmi/core/context.py`

**预估工作量**：2 小时

**测试**：
- 摘要短 + hits 少 → recent 应能扩大到 15~20 轮
- 摘要长 + hits 多 → recent 应缩到 5~8 轮

---

### P1-6: 上下文增量缓存

**问题**：每次对话都从头构建，长对话性能随长度线性下降。

**修复方案**：

```
修改点：context.py + manager.py

1. 缓存最近 N 轮的上下文片段：
   cache_key = f"context:{session_id}:{last_turn_count}"
   如果 last_turn_count 没变 → 直接返回缓存

2. 缓存失效条件：
   - 新轮次加入（last_turn_count 变化）
   - 摘要更新（summary_version 变化）
   - 跨会话记忆更新（memory_db 时间戳变化）

3. 内存限制：
   LRU 缓存，最多保留 10 个会话的上下文
```

**修改文件**：`mmi/core/context.py`、`mmi/core/manager.py`

**预估工作量**：4 小时

**测试**：
- 连续 5 轮对话 → 第 2~5 轮构建上下文应命中缓存
- 新轮加入后 → 缓存应失效

---

### P1-7: 增量摘要更新

**问题**：每次更新摘要都重新读全文发给 LLM，对话越长成本越高。

**修复方案**：

```
修改点：summarizer.py 的 update_summary()

1. 改为增量更新：
   输入 = 旧摘要 + 新增 turns（自上次摘要以来的）
   输出 = 新摘要
   
2. 旧摘要的字段保留：
   - summary（更新）
   - summary_version（+1）
   - summary_history（追加旧摘要）

3. 每 100 轮做一次全量重建（兜底，防止增量漂移）
```

**修改文件**：`mmi/core/summarizer.py`

**预估工作量**：4 小时

**测试**：
- 100 轮对话 → 每次更新只发新增的 20 轮给 LLM
- 对比全量 vs 增量的 token 消耗（应节省 70%+）

---

## 三、P2 优先级 — 值得修复

### P2-8: 后台任务队列化

**问题**：摘要更新和记忆入库各自起独立后台线程，可能打架。

**修复方案**：

```
修改点：summarizer.py + manager.py

1. 引入单一线程池：
   from concurrent.futures import ThreadPoolExecutor
   executor = ThreadPoolExecutor(max_workers=1)
   
2. 所有后台任务（摘要更新、记忆入库）提交到同一队列：
   executor.submit(_run_summary_update, ...)
   executor.submit(_run_memory_store, ...)

3. 任务按 FIFO 执行，避免竞态
```

**修改文件**：`mmi/core/summarizer.py`

**预估工作量**：2 小时

**测试**：
- 连续触发 5 次摘要更新 → 应依次执行，不丢不叠

---

### P2-9: 增强热度公式

**问题**：热度只考虑访问次数和时间，不考虑内容重要性。

**修复方案**：

```
修改点：heat.py 的 compute_heat()

1. 增加内容权重因子：
   content_weight = min(1.0, total_turns / 50)  # 50 轮以上权重=1
   
2. 增加摘要关键词权重：
   如果摘要包含 "项目"、"方案"、"决策" → +2
   如果摘要包含 "你好"、"再见" → -1

3. 新公式：
   heat = (access_count * 1.0 + recency_bonus - age_penalty) * content_weight
```

**修改文件**：`mmi/core/heat.py`

**预估工作量**：2 小时

**测试**：
- 5 轮闲聊 vs 5 轮项目讨论 → 后者热度应更高

---

### P2-10: FAISS 写入性能优化

**问题**：每条记忆入库都要读/写整个 FAISS 索引文件。

**修复方案**：

```
修改点：memory.py 的 store_memory()

1. 内存池化：
   维护一个内存中的 FAISS 索引（IndexFlatIP）
   定期（每 50 条或每 5 分钟）批量持久化到磁盘

2. 写入时：
   - 内存索引 add() → O(1)
   - 磁盘持久化 → 后台异步

3. 读取时：
   - 内存索引优先
   - 内存中没有的从磁盘加载
```

**修改文件**：`mmi/core/memory.py`

**预估工作量**：4 小时

**测试**：
- 连续入库 100 条记忆 → 总耗时应显著下降
- 程序重启后 → FAISS 索引应完整恢复

---

## 四、执行路线

### Round 1: 基础修复（1-2 天）
```
├── P0-1 短会话记忆入库 → 打通跨会话记忆
├── P0-3 精确 Token 估算 → 上下文预算准了
└── P2-8 任务队列 → 后台线程安全
    ↓
Round 2: 搜索与截断升级（2-3 天）
├── P0-2 jieba + BM25 → 搜索质量提升
├── P1-4 截断优先级修复 → 设计 vs 实现一致
└── P1-5 动态窗口 → 弹性上下文
    ↓
Round 3: 性能与智能增强（2-3 天）
├── P1-6 上下文缓存 → 长对话性能
├── P1-7 增量摘要 → 省钱
├── P2-9 增强热度 → 排序更合理
└── P2-10 FAISS 池化 → 写入性能
```

### 各轮冒烟测试

```
Round1:
  - 新创建 5 轮会话 → mmi memory search 能搜到
  - 4000 字符中文 → tiktoken 估算接近真实值
  - 连续触发摘要 → 不丢数据

Round2:
  - 搜索"项目方案" → 结果质量提升
  - 构造 hits>recent → 截断后 hits 保留更多
  - 长对话 → recent 窗口自动扩大

Round3:
  - 100 轮对话 → 第 2~5 轮上下文构建命中缓存
  - 100 轮 → 每次更新只发新增 turn 给 LLM
  - 100 条记忆入库 → 耗时显著下降
```

---

## 五、风险与注意事项

| 风险 | 应对 |
|------|------|
| tiktoken 安装失败 | 降级为中英文区分估算，不影响功能 |
| jieba 分词效果不佳 | 保留 2-gram 作为 fallback |
| 缓存导致上下文不一致 | 严格的缓存失效条件 + 单元测试 |
| 增量摘要漂移 | 每 100 轮强制全量重建 |
| 任务队列阻塞主流程 | 用 ThreadPoolExecutor 异步提交 |

---

## 六、验收标准

每轮修复完成后，必须满足：

1. ✅ `pytest tests/` 全部通过
2. ✅ `ruff check .` 0 error
3. ✅ 新增/修改的模块有单元测试覆盖
4. ✅ 冒烟测试通过（见上）
5. ✅ ROUND_LOG.md 已更新本轮修改

---

> 参考：`ARCHITECTURE.md`、`RULES.md`、`PLAN.md`
