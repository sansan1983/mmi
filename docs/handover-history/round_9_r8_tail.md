# 交接文档 — R9 R8 末遗留收口
> 日期:2026-06-06
> 状态:✅ R9 全部完成(9.1 test_cli 归档 / 9.2 EventBus 节流 / 9.3 span 测试补强 / 9.4 batch_* 并发)
> 主题:延续 R8.5 节奏,清 R8 末遗留 4 条 + 1 fix
> 覆盖:`round_8_phase4_fb.md` 遗留问题 1-4(不含 TUI 真流式,留 R9.x)

---

## 1. 本轮完成(R9 全部收口)

| 任务 | 落地 | 关键文件 | 净增测试 |
|---|---|---|---|
| 9.1 test_cli.py 归档 | ✅ | `tests/test_cli.py` 删除 + `docs/history/ctrim-tests-deprecated.md` 快照 + `tests/conftest.py` 加 `collect_ignore_glob` | -7(归档 7 个 ctrim 测试,3 个本就 fail 不计) |
| 9.2 EventBus 节流 | ✅ | `mmi/agent/steps.py:ValidateStep` 加 `issue_batch_threshold: int = 5` + `force_individual: bool = False`,改 publish 逻辑(超阈值改 `validation.issue_batch` 单条) | +7 |
| 9.3 span 边界补强 | ✅ | `tests/test_validate.py` 追加 3 个测试(min_length / 多 match / to_dict 透传)— R8 4.10 已填字段,本轮补覆盖 | +3 |
| 9.4 batch_* 并发 | ✅ | `mmi/core/manager.py:SessionManager` 加 `max_batch_workers: int = 4`,`batch_chat` / `batch_touch` / `batch_get_meta` 改用 ThreadPoolExecutor(单元素走串行快路径) | +7 |
| 9.4-fix _StubLLM.classify | ✅ | `tests/test_batch_chat.py` 修 `_StubLLM.classify` 签名(对齐 `LLMProvider` 抽象) | 0 |
| **合计** | **5/5** | | **+17 净增(R8.5.3 末 564 → R9 末 581)** |

- ✅ **测试**:master **581 passed**(R8.5.3 末 `--ignore=tests/test_cli.py` 是 564;本轮归档后直接报 564 → 9.2/9.3/9.4 净增 17 → 581)
- ✅ **ruff**:`0 error`(全程维持 0)

---

## 2. 改动文件清单(已合并 master)

### 核心代码
| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/agent/steps.py` | 修改 | `ValidateStep` 加 2 字段(`issue_batch_threshold: int = 5` / `force_individual: bool = False`),`run()` 内 if/else 改 publish 逻辑:`force_individual=True` 或 `len(issues) <= threshold` 时走老路径(逐条 `validation.issue`);否则改发单条 `validation.issue_batch`(payload 含 `session_id` / `count` / `issues` 列表) |
| `mmi/core/manager.py` | 修改 | `SessionManager.__init__` 加 `max_batch_workers: int = 4` 参 + 类属性默认值(让 `__new__` 测试 helper 仍能工作);`batch_chat` / `batch_touch` / `batch_get_meta` 改用 `ThreadPoolExecutor`,单元素走串行快路径(避免线程池开销);用 pre-allocated list + enumerate index 保结果顺序 |

### 测试
| 文件 | 操作 | 净增 |
|---|---|---|
| `tests/test_cli.py` | **删除** | -7(ctrim 硬编码,归档到 `docs/history/ctrim-tests-deprecated.md`) |
| `tests/test_event_bus_throttle.py` | **新建** | +7(下方/边界/上方/可配置/`force_individual`/`complete` 不变/no bus) |
| `tests/test_validate.py` | 修改 | +3(min_length span / 多 match 同一 regex / `to_dict` 透传 tuple) |
| `tests/test_batch_chat.py` | 修改 | +7(单元素快路径 / 多元素并发 / `max_workers=1` 退化 / 顺序保持 / `batch_touch` 并发 / `batch_get_meta` 并发 / 构造参透传) + `_StubLLM.classify` 签名修(fix commit) |
| `tests/conftest.py` | 修改 | 加 `collect_ignore_glob = ["test_cli.py"]` 保险(双保险) |

### 文档
| 文件 | 操作 | 说明 |
|---|---|---|
| `docs/history/ctrim-tests-deprecated.md` | **新建** | 归档原因 + DEPRECATED 头 + 简要说明(指向 git history 取原文) |
| `docs/handover-history/round_9_r8_tail.md` | **新建** | 本交接文档 |
| `docs/handover-history/INDEX.md` | 修改 | +round_9 行 |
| `ROUND_LOG.md` | 修改 | 切到 Round 9 |

---

## 3. 关键设计决策

### 决策 1:spec 缺陷 implementer 现场修复(TDD 失败循环自检)

R9 plan 文本里发现 5 处 spec 偏差,subagent 在 TDD 红→绿循环中自检 + 修对:

1. **`_count_events()` 闭包 bug**(Task 2)— plan 写 `count = 0; def fn(): nonlocal count; ...; return count`,但用法是 `f = _count_events(...)` 然后 `assert f == 3`,自相矛盾(函数对象不能直接 ==)。改为返回 list `[0]` 容器 + 断言 `count[0] == 3`。
2. **`asdict` 不转 tuple → list**(Task 3)— spec 注释假设 `asdict(issue)["span"]` 会变 list,实际 `asdict` 保留 tuple,只 `json.dumps` 才转 list。改断言用 tuple。
3. **regex 多 match span 位置手算错**(Task 3)— spec 写 `(20, 23)`,实际 `text="xyz first match then xyz second"` 中第 2 次 `xyz` 起始 21,所以 `(21, 24)`。
4. **`_StubLLM` 漏 `classify()` 抽象方法**(Task 4)— spec 漏写 `LLMProvider` 还有 `classify` 抽象(不只是 `chat` / `stream_chat`)。补最小实现 + fix commit 修签名/返回类型。
5. **`__new__` 跳过 `__init__` 旧测试 helper 也需要 `_max_batch_workers`**(Task 4)— `SessionManager.__new__(cls)` 跳 `__init__`,实例上没有 `_max_batch_workers`;通过加**类属性默认值**让 `__new__` 风格测试仍工作。

**全部由 subagent 在 TDD 失败循环中自检 + 修对**,符合 spec 实施纪律。教训:后续 plan 写代码片段要更"可执行级"(尤其手算坐标 / mock 协议方法)。

### 决策 2:节流阈值默认 5

按 deep analysis 经验值:常规 chat 1-3 issues,大段违规才 >5。超阈值改 publish 单条 `validation.issue_batch`(payload 含 `session_id` / `count` / `issues` 列表),下游订阅者一次拿到全部 issue 列表做聚合,避免单条刷屏。

`force_individual: bool = False` 强制单发开关,给调试 / 排错场景用,绕过阈值。

### 决策 3:storage 不另加 RLock

`mmi/core/storage.py` 已有 portalocker 文件锁(注释:写操作全部走 portalocker 排他锁,跨平台 fcntl/Windows LockFileEx)。

- 跨进程安全已有
- 跨线程同一 manager 单实例 portalocker 文件级排他自动串行化
- R9 9.4 batch_* 改线程池后,各 worker 调 chat 触发 storage 时 portalocker 自动串行化(同 session 文件非递归锁阻塞;不同 session 文件独立无跨锁)

**不**加 RLock 是因为加 RLock 反而会带来"跨进程互斥语义混乱"风险(portalocker 是文件锁,RLock 是线程锁,叠加易出顺序问题)。R9 spec 二修时已删 RLock 项。

### 决策 4:`validation.issue_batch` payload 设计

跟 `validation.issue` 单条 payload 对齐,只把"单条"扩成"列表":

```python
{
    "session_id": "...",
    "count": 6,
    "issues": [
        {"rule_id": "r1", "severity": "error", "message": "...", "span": [0, 3]},
        ...
    ]
}
```

订阅方根据 `count` 字段决定一次性处理还是拆分,跟单条事件保持 schema 一致(同样的 `rule_id/severity/message/span` 字段)。

### 决策 5:span 字段 R8 4.10 已填,本轮 9.3 只补测试

写 spec 时核到事实:`ValidationIssue.span` R8 4.10 已填好(`regex` → `(m.start(), m.end())`,`max_length` → `(0, min(...))`,`min_length` → `(0, len(text))`,`required_substrings` → `None`),4 个 span 测试已存在。

R8 末遗留第 4 条("`ValidationIssue.span` UI 还没接")实际只指 UI 接线(TUI 高亮),留 R9.x / R10。本轮只补 3 个边界测试(钉住现有行为),不动实现、不接 UI。R9 spec 二修(`fff8bc7`)已把 9.3 改为"补强测试覆盖"。

### 决策 6:`batch_*` 单元素快路径

单元素调用走串行快路径(`if len(items) == 1: return [self.chat(items[0])]`),避免 ThreadPoolExecutor 启停开销。多元素才进线程池。

顺序保证:不靠 `as_completed` 排序,而是 pre-allocated `results = [None] * len(items)` + `executor.submit(_run, i, x)` 内部 `results[i] = ...`,直接按 index 写入。

---

## 4. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| R8.5.3 末 baseline | 564 / 564 | `--ignore=tests/test_cli.py`;test_cli 含 7 pass + 3 fail(R8 末就 fail,被忽略) |
| R9-9.1 删 test_cli | 564 / 564 | 同 baseline(删除的 7 pass + 3 fail 都不算了) |
| R9-9.2 EventBus 节流 | +7 → 571 / 571 | `tests/test_event_bus_throttle.py` |
| R9-9.3 span 边界补强 | +3 → 574 / 574 | `tests/test_validate.py` 追加 |
| R9-9.4 batch_* 并发 | +7 → 581 / 581 | `tests/test_batch_chat.py` 追加 |
| R9-9.4-fix _StubLLM | 581 / 581 | 签名修,无新增 |
| **R9 收口** | **581 / 581** | **+17 净增(564 → 581)** |

ruff 全程 0 error。

---

## 5. 接手者

- `git checkout master` 即可
- `pytest tests/ -q` → **581 passed**
- `ruff check mmi/ tests/` → **All checks passed**
- R9 已清 R8 末遗留 4 条(不含 TUI 真流式,留 R9.x / R10)
- 下次续做:
  - **R9.x**(可选):TUI 真流式 + 美化(本轮明确推后)
  - **R10+**:五期 20 项 / 六期 16 项
  - **R8.5.x**(可选):R8.5.1b 报告 §5 B1-B4 + C1(千问 / ProviderInfo 白名单)

---

## 6. 遗留问题(R9.x / R10+ 起点)

| # | 问题 | 建议归属 |
|---|---|---|
| 1 | TUI `stream_chat` 仍 `asyncio.to_thread + list(...)` 收齐再渲染,不是 chunk-by-chunk 增量 | R9.x "TUI 美化" |
| 2 | TUI 主题色(目前 Tokyo Night 单色,缺渲染层次 / Markdown / 代码高亮) | R9.x |
| 3 | `ValidationIssue.span` UI 还没接(TUI 没高亮) | R9.x / R10 |
| 4 | `validation.issue_batch` 单条 payload 含大量 issue 嵌套 EventBus 仍有节流压力(本轮已比逐条好) | R10+ 视情况 |
| 5 | spec 写 plan 时需要更"可执行级"代码片段(本轮 5 处偏差) | 后续 plan 改 TDD-first 写法 |

---

> 来源:`docs/superpowers/plans/2026-06-06-r9-r8-tail.md`(R9 plan,Task 1-5)
> 来源:`docs/superpowers/specs/2026-06-05-r9-r8-tail-design.md`(R9 spec)
