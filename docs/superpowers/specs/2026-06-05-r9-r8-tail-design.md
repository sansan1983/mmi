# MMI R9 — R8 末遗留收口设计规格

> 日期:2026-06-05
> 范围:R8 末遗留问题中 4 条(不含 TUI 真流式 + 美化)
> 依据:`ROUND_LOG.md` 遗留问题 1/2/3/4 + `docs/handover-history/round_8_phase4_fb.md`
> 状态:草稿,等用户审

---

## 0. 背景与目标

### 0.1 起点

R8(2026-06-05)四期 4.7-4.10 全部收口,master **539 passed / ruff 0**。
R8.5(2026-06-05)三个独立小补丁也收口,master **565 passed / ruff 0**:

- R8.5.1b provider 参数透传(14 测试)
- R8.5.2 Anthropic 真 SSE 流式(12 测试)
- R8.5.3 Kimi 从预置移除

ROUND_LOG §遗留问题 列 5 条:

| # | 项 | 当前文件 | 量级 |
|---|---|---|---|
| 1 | TUI 真流式 + 美化 | `mmi/tui/app.py` | 中(单独 round 更好) |
| 2 | Manager.batch_chat 并发 | `mmi/core/manager.py` | 1-2h |
| 3 | test_cli.py ctrim 硬编码 → 归档 | `tests/test_cli.py` | 0.5h |
| 4 | ValidationIssue.span UI 化 | `mmi/agent/validate.py` + `mmi/agent/result.py` + `mmi/tui/...` | 1-2h |
| 5 | validation.issue 大量 issue 时 EventBus 刷屏 → 节流 | `mmi/agent/steps.py:ValidateStep.run` | 1-2h |

### 0.2 本轮目标

清遗留 2/3/4/5(不含 TUI 真流式),共 4 条 ~5-7h。理由:

- 4 条都是"已有接口 / 已有字段,补强",低风险
- 每条独立可测,符合 R8.5 三个补丁的轻量节奏
- TUI 真流式需要 textual stream API 调研 + CSS 美化,工程量偏中,单独 round 更好隔离
- 五期 20 项 / 六期 16 项仍是主队列,本轮只清 R8 末尾巴

### 0.3 范围外(明确不做)

- TUI 真流式 + 美化(留 R9.x 或 R10)
- 五期 20 项(留 R10+)
- 六期 16 项(留 R10+)
- R8.5.1b 报告 §5 B1-B4 + C1(Kimi / 千问 / ProviderInfo 白名单)— 用户已表示"工作量 + 实际用量 → 直接移除 Kimi";B4/C1 等下次单独 round

---

## 1. 任务清单

| 任务 | 落点 | 净增测试 | 估时 |
|---|---|---|---|
| **9.1** test_cli.py ctrim 硬编码 → 归档 | `tests/test_cli.py` 删,内容迁 docs | 0 | 0.5h |
| **9.2** EventBus 节流(validation.issue 大量 issue 不刷屏) | `mmi/agent/steps.py` + `tests/test_event_bus_throttle.py` | 6-8 | 1.5h |
| **9.3** ValidationIssue.span 字段补齐(切到具体字符位置)+ to_dict 透传 | `mmi/agent/validate.py` + `mmi/agent/result.py` + `tests/test_validate.py` | 4-6 | 1-2h |
| **9.4** Manager.batch_chat 并发(后台线程池) | `mmi/core/manager.py` + `tests/test_batch_chat.py` | 6-8 | 2-3h |

合计:**~5-7h,净增测试 16-22**

---

## 2. 设计细节

### 9.1 test_cli.py ctrim 硬编码 → 归档

#### 现状

`tests/test_cli.py:9-23` 硬编码:

```python
VENV = "/home/ubuntu/ctrim/.venv/bin/python"
ROOT = "/home/ubuntu/ctrim-fusion"
```

跑 ctrim 旧 CLI 来验证,完全跟 mmi 无关(R8.5.1 顺手 ruff-fix 时已经标记)。

#### 设计

- 删 `tests/test_cli.py` 整个文件
- 内容迁到 `docs/history/ctrim-tests-deprecated.md`(头部 `[DEPRECATED]` 标签,记录原因)
- `conftest.py` 改:`collect_ignore_glob` 加 `test_cli.py`(保险,避免有人恢复)
- `pytest` 命令从 `--ignore=tests/test_cli.py` 简化回 `pytest tests/ -x`(全 0 失败)

#### 验证

- `pytest tests/ -x` 全通过(无 test_cli)
- `ruff check .` 0 error
- 文档落地

---

### 9.2 EventBus 节流(validation.issue 大量 issue 不刷屏)

#### 现状

`mmi/agent/steps.py:ValidateStep.run` 在 issues 多时一条条 publish `validation.issue`:

```python
for issue in ctx.validation.issues:
    self.event_bus.publish(Event(name="validation.issue", ...))
```

如果一次 chat 触发 10+ issues(罕见但可能),bus 上瞬间 10+ 事件,订阅方可能刷屏。

#### 设计

- 在 `mmi/agent/steps.py:ValidateStep` 加字段 `issue_batch_threshold: int = 5`
  - 超过阈值 → 改 publish `validation.issue_batch`(payload 含 issues 列表 + 计数)
  - 不超过 → 保持原行为(每条 issue 单独 publish,便于实时 UI 高亮)
- 默认 5(对照 deep analysis 经验值:常规 chat 1-3 issues,大段违规才 >5)
- 加一个 `force_individual: bool = False` 开关(给调试 / 排错场景用)
- payload 设计:
  - `validation.issue_batch`: `{session_id, count, issues: [{name, severity, message, span?}, ...]}`
  - `validation.issue`(原有,阈值下用):不变

#### 验证

- `test_issue_below_threshold_publishes_individually` — 3 issues 走单发
- `test_issue_above_threshold_publishes_batch` — 6 issues 走批量
- `test_issue_exactly_at_threshold_publishes_individually` — 边界 5
- `test_issue_batch_payload_includes_count_and_issues` — payload 字段全
- `test_issue_batch_threshold_configurable` — 改 2 测通过
- `test_force_individual_always_publishes_singly` — 强制开关
- `test_complete_event_unchanged` — `validation.complete` 行为不变
- `test_no_event_bus_still_works` — bus 为 None 时不抛

---

### 9.3 ValidationIssue.span 字段补齐 + 切到具体字符位置

#### 现状

R8 4.10 引入 `ValidationIssue` 4 字段(frozen=True):

```python
@dataclass(frozen=True)
class ValidationIssue:
    name: str
    severity: Literal["error", "warning"]
    message: str
    span: tuple[int, int] | None = None
```

`span` 字段已有(在 result.py to_dict 序列化),但**当前 `_check_rules` 全部填 None**(TODO 状态),没有真正切到具体违规位置。

#### 设计

- `mmi/agent/validate.py`:
  - 改 `_check_rules` 让规则匹配时填 span `(start, end)`(字符偏移,从 0)
  - 优先级:`pattern`(regex finditer) > `required_substrings`(str.find) > 长度规则(整段 `0, len(output)`)
  - `max_length` / `min_length` 违规:span = `(0, len(output))`(整段标黄)
- `mmi/agent/result.py`:无需改(to_dict 已透传 asdict,span 跟着走)
- TUI 暂不接(留 R9.x),只保证字段填了 + 序列化对

#### 验证

- `test_pattern_match_fills_span_with_match_position` — regex 命中位置精确
- `test_pattern_multiple_matches_fills_first_span` — 多匹配取首
- `test_required_substring_match_fills_span` — required 命中
- `test_max_length_violation_fills_full_span` — 整段
- `test_min_length_violation_fills_full_span` — 整段
- `test_to_dict_includes_span` — 序列化透传
- `test_no_match_leaves_span_none` — 命中不上时 None

---

### 9.4 Manager.batch_chat 并发(后台线程池)

#### 现状

R7 4.6 引入 `Manager.batch_chat` / `batch_touch` / `batch_get_meta`,但**全部串行执行**:

```python
def batch_chat(self, session_ids: list[str], user_message: str, ...) -> list[ChatResult]:
    return [self.chat(sid, user_message, ...) for sid in session_ids]
```

TUI 多会话并行选中 / 批量评分等场景下,串行效率低。

#### 设计

- `mmi/core/manager.py`:
  - `SessionManager` 构造加可选字段 `max_batch_workers: int = 4`
  - `batch_chat` 改用 `concurrent.futures.ThreadPoolExecutor`:
    ```python
    def batch_chat(self, session_ids, user_message, **kwargs):
        if len(session_ids) <= 1 or self._max_batch_workers == 1:
            return [self.chat(sid, user_message, **kwargs) for sid in session_ids]
        with ThreadPoolExecutor(max_workers=self._max_batch_workers) as ex:
            futures = {ex.submit(self.chat, sid, user_message, **kwargs): sid for sid in session_ids}
            results = [None] * len(session_ids)
            for i, (sid, fut) in enumerate(zip(session_ids, futures)):
                try:
                    results[i] = fut.result()
                except Exception as e:
                    results[i] = _error_result(e)
            return results
    ```
  - `batch_touch` / `batch_get_meta`:同模式(IO 密集,线程池收益)
  - 加全局 `BATCH_WORKERS` 限速保护(默认 4,跟 deep analysis 经验值)
- SessionStorage 读写:`storage.py` 用 `threading.RLock`(R5 没做,这次顺手;但要测现有 storage 测试不破)
- 异常隔离:单 session 失败不影响其它(原 chat 抛 → 包成 ChatResult(reply="[error]", error=...))

#### 验证

- `test_batch_chat_serial_when_single_session` — 1 session 走串行快路径
- `test_batch_chat_concurrent_when_multiple` — 3 session 用 3 worker
- `test_batch_chat_respects_max_workers` — 限速
- `test_batch_chat_isolates_exceptions` — 单失败不影响其它
- `test_batch_touch_concurrent` — 同上
- `test_batch_get_meta_concurrent` — 同上
- `test_storage_concurrent_read_write_safe` — storage RLock 验证
- `test_existing_storage_tests_unchanged` — 回归(跑 storage 全测试)

---

## 3. 风险与回退

| 风险 | 缓解 |
|---|---|
| storage 加 RLock 破旧测试 | 先跑 `pytest tests/test_storage.py` 基线;RLock 嵌套安全(可重入) |
| ThreadPoolExecutor 引入新依赖 | `concurrent.futures` 是 stdlib,无依赖 |
| 节流阈值 5 不准 | 留 `issue_batch_threshold` 配置 + `force_individual` 开关,可调 |
| 归档 test_cli 漏内容 | docs/history/ 留完整 copy + 头部 DEPRECATED 标签 |

---

## 4. 不做 / 推后

- TUI 真流式 + 美化 → 留 R9.x 或 R10
- 五期 20 项 / 六期 16 项 → 留 R10+
- R8.5.1b 报告 §5 B/C 队列 → 留 R8.5.x 单独 round
- ValidationIssue.span 的 TUI 接线 → 留 R9.x(本轮只填字段,不上 UI)

---

## 5. 质量门禁

- `pytest tests/ -x` 全通过(预计 ~580 passed)
- `ruff check .` 0 error
- 旧 R0-R8.5 全部测试零回归
- 文档:写 `docs/handover-history/round_9_*.md`(可分 4 个微 round 文件)+ 更新 INDEX + ROUND_LOG
- 4 个 git commit(每个任务一个),master merge

---

> 接手者:读本文档 → 顺序执行 9.1 → 9.2 → 9.3 → 9.4 → 写 round_9 交接
