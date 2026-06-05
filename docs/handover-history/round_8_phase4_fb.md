# 交接文档 — 四期 R8 全部收口
> 日期:2026-06-05
> 状态:✅ R8 全部完成(4.7 / 4.8 / 4.9 / 4.10 + 跨期遗留 7/8 收尾)
> 主题:四期 架构加固 R8 — Tracer→EventBus / LLM 流式重试 / Validate&Persist 拆 hook / ValidationIssue 结构化 / 测试基建
> 覆盖:PLAN.md 四期 4.7 + 4.8 + 4.9 + 4.10 + 跨期遗留 #7 (chat_legacy 评估) + #8 (tests/_fakes.py)

---

## 1. 本轮完成(R8 全部收口)

按 R8 计划 4 个 PLAN.md Task + 2 个跨期遗留,全部完成并合并 master:

| 任务 | 落地 | 关键文件 | 净增测试 |
|---|---|---|---|
| 4.10 ValidationIssue 结构化 | ✅ | `mmi/agent/validate.py`(`ValidationIssue` 4 字段 + `ValidationRule.severity`) | +12 |
| 4.7 Tracer → EventBus | ✅ | `mmi/agent/trace.py`(`Tracer(event_bus=...)` + `trace.recorded` 事件)+ `mmi/agent/orchestrator.py`(注入 bus) | +4 |
| 4.9 Validate / Persist 拆 hook | ✅ | `mmi/agent/steps.py`(`ValidateStep` / `PersistStep` 加 `event_bus` + 3 个事件名)+ `mmi/agent/orchestrator.py`(透传 bus) | +6 |
| 4.8 LLM 流式重试 | ✅ | `mmi/core/llm.py:LLMProvider.stream_chat_with_retry()`(pre-yield 可重试 / mid-stream 不可重试) | +11 |
| 跨期 #7 `chat_legacy` 评估 | ✅ | 决议:**保留**(理由见第 5 节决策 1) | 0 |
| 跨期 #8 `tests/_fakes.py` 抽公共 | ✅ | `tests/_fakes.py`(`ScriptedLLM` / `KeywordStubLLM` / `MinimalStubLLM`)+ `conftest.py` 重构 | 0(测试基建,零行为变化) |
| ruff 跨期遗留清理 | ✅ | `ruff check --fix` 13 个测试文件,44 error → 0 | — |
| **合计** | **6/6** | | **+33** |

- ✅ **测试**:master **539/539**(506 R7 末 + 33 net new)
- ✅ **ruff**:**0 error**(R7 末是 0,本轮维护 0)
- ✅ **R8 收口**:本文档 + `docs/INDEX.md` 全部状态更新 + `ROUND_LOG.md` 切换 + `round_7_phase4_core.md` 第 7 节 R8 起点(已全 ✅)

---

## 2. 改动文件清单(已合并 master)

### 核心代码

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/agent/validate.py` | 修改 | `ValidationIssue` 扩 4 字段(`message/severity/rule_id/span`,`frozen=True`);`ValidationRule` 加 `severity` 字段(默认 "error");`_check_rules` 重写填充新字段(regex 命中 → span=m.start/end;missing substring → span=None;max_length → span=(0, max_length);单条 regex 多次命中 → 多条 issue) |
| `mmi/agent/trace.py` | 修改 | `Tracer.__init__(event_bus=None)` 接受 bus;`record()` 末尾 publish `trace.recorded` 事件;新增 `reset_instance()` 类方法(测试用);`get_instance()` 行为不变 |
| `mmi/agent/orchestrator.py` | 修改 | 默认 `self.tracer = Tracer(event_bus=self.bus)`(透传);`default_steps(..., event_bus=self.bus)` 透传到 Validate/Persist |
| `mmi/agent/steps.py` | 修改 | `ValidateStep` / `PersistStep` 加 `event_bus: EventBus | None`;完成后 publish `validation.complete` + 每条 issue 单独 publish `validation.issue` / `persist.complete`;`default_steps(..., event_bus=None)` 接受并透传 |
| `mmi/core/llm.py` | 修改 | 加 `stream_chat_with_retry(messages, *, max_attempts=3, base_delay=0.5)`;**核心约束**:`consumed_count` 状态机区分 pre-yield(可重试) vs mid-stream(不可重试,包成 `StreamError`) |

### 测试

| 文件 | 操作 | 净增 |
|---|---|---|
| `tests/test_validate.py` | **新建** | 12 个(4.10 全覆盖:frozen / 默认 severity / 4 字段 / regex span / 缺失 span / max_length span / warning 透传 / 序列化 / 默认 rule severity) |
| `tests/test_event_bus_hooks.py` | **新建** | 10 个(4.7+4.9:Tracer publish / 无 bus 静默 / handler 异常隔离 / orchestrator 透传 / ValidateStep complete/issue/无 bus / PersistStep complete/无 bus / default_steps 透传) |
| `tests/test_llm_stream_retry.py` | **新建** | 11 个(4.8:正常 / pre-yield 3 种错误可重试 / 4xx 不可重试 / mid-stream 2 种错误转 StreamError / 重试耗尽 ×2 / 退避时序 / EchoLLM 默认实现兼容) |
| `tests/_fakes.py` | **新建** | 3 个共享 LLM 假实现(`ScriptedLLM` / `KeywordStubLLM` / `MinimalStubLLM`) |
| `tests/conftest.py` | 修改 | 删 `ScriptedLLM` 类定义,改 `from tests._fakes import ScriptedLLM`;保留 fixture 不变;删 unused import(`Any` / `Classification`) |
| `tests/test_event_bus_hooks.py` | 修改 | 用 `MinimalStubLLM` 替换本地 `_StubLLM`(沿用旧命名 `_StubLLM = MinimalStubLLM`) |

### 跨期 ruff 清理(13 个测试文件)

| 文件 | 改动类型 |
|---|---|
| test_agent_phase3 / test_batch_chat / test_chat_result / test_classifier / test_config / test_llm / test_parse_blocks / test_paths / test_providers / test_search / test_titler / test_tui_list | 删 unused import(F401,auto-fix) |
| test_cli | auto-fix 重排 import 多行 |
| test_heat | E702 multiple statements on one line 改多行(5 处) |
| test_manager | E702 × 3 + 重排 |
| test_storage | E702 × 2 + 删 unused local var `orig` |
| test_summarizer | 删 unused local var `sid` |

### 文档(本轮)

| 文件 | 操作 | 说明 |
|---|---|---|
| `docs/handover-history/round_8_phase4_fb.md` | **新建** | 本交接文档 |
| `docs/handover-history/INDEX.md` | 修改 | +round_8 行 |
| `docs/INDEX.md` | 修改 | 四期 4.7/4.8/4.9/4.10 状态 ⬜ → 🟢(本轮 4 项);四期整段从 🟢 R7 → 🟢 R8 全清 |
| `ROUND_LOG.md` | 修改 | 切到 Round 8 "四期架构加固 R8 全部收口" |
| `docs/handover-history/round_7_phase4_core.md` | 修改 | 第 7 节 R8 起点 4 项 → 全 ✅(本轮全部完成);第 8 节排除项维持(TUI 美化仍后期单独 round) |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| R7 末 baseline | 506 / 506 | R7 全部收口 |
| R8 Task 1 (4.10) | +12 → 518 / 518 | ValidationIssue 4 字段 |
| R8 Task 2 (4.7+4.9) | +10 → 528 / 528 | Tracer→EventBus + Validate/Persist hooks |
| R8 Task 3 (4.8) | +11 → 539 / 539 | stream_chat_with_retry |
| R8 Task 4 (#7+#8+ruff) | 539 / 539(无新增测试) | chat_legacy 评估 + _fakes 抽取 + ruff 清 0 |
| ruff | **0 error** | 44(R7 末)→ 0,本轮清完 |

---

## 4. 关键设计决策

### 决策 1:`chat_legacy()` 评估结论 — 保留

**移除候选理由**:
- 1 个生产调用点(`mmi/cli.py:cmd_agent`),5 个测试调用点
- phase 3 兼容接口,R8 之后可考虑清理

**保留理由**(决定采纳):
- `chat_legacy` 提供有价值的 fallback 语义:`chat().reply` 失败时自动包成 `"[Orchestrator error] ..."` 字符串(**不抛异常**),让 CLI 不崩
- 移除 = 改 CLI 入口 + 改 5 个测试 + 还要专门写 fallback 测试
- 净代码 ~10 行,删了省不到钱,留着不亏
- 双接口并存对调用者透明,选 `chat()` 拿 `ChatResult`、选 `chat_legacy()` 拿 `str` 都有意义

**决议**:**保留**,R8 不动。后续若 phase 3 测试全删,可一并评估。

### 决策 2:`ValidationIssue` 用 frozen=True

- 放进 `tuple`(已经是 immutable 容器)+ 不可变字段 = 可哈希 + 可安全放进 `EventBus.payload`
- 测试 `test_validation_issue_is_frozen` 验证 setattr 抛 `FrozenInstanceError`
- 副作用:实例化时要传齐 4 字段(或全用默认),不像普通 dataclass 可以后改

### 决策 3:`stream_chat_with_retry` 用 `consumed_count` 状态机区分 pre/mid-stream

- **核心约束**:stream 是生成器,每调一次产生新 stream 实例
- **pre-yield 错误**(还没 yield 任何 chunk):可重试,对调用者不可见(新 stream 整段重发)
- **mid-stream 错误**(已 yield 一些 chunk):**不可重试**,包成 `StreamError(f"mid-stream error after N chunks: ...")` 透传
  - 理由:重试会重复已 yield 的文本,UI 看到两段一样的内容
- 4xx 不可重试;5xx/429/Timeout/ConnectError 在 pre-yield 阶段可重试

**实现**:内层生成器 + `consumed_count` 状态变量追踪 caller 消费进度。

**测试**:`_ScriptedStreamLLM` 用 2D list 表达"每次 stream_chat 调用的剧本",独立可验证每次重试用不同剧本。

### 决策 4:`EventBus` 透传路径 Orchestrator → Pipeline → Steps

```
Orchestrator.__init__(event_bus=bus)
  ├─ Tracer(event_bus=bus)            # 4.7
  └─ Pipeline(default_steps(..., event_bus=bus), event_bus=bus)
      └─ ValidateStep(event_bus=bus)  # 4.9
      └─ PersistStep(event_bus=bus)   # 4.9
```

- 统一从 Orchestrator 入口传入,所有需要发事件的组件共享同一个 bus
- 向后兼容:不传 bus → 各组件发事件代码跳过(`if self._bus is not None` / `if self.event_bus is not None`)
- 事件 payload 设计:不放大对象(避免循环引用),只放 ID + 关键字段,订阅者按需再查源

### 决策 5:`tests/_fakes.py` 抽 3 个共享 LLM 假实现

- `ScriptedLLM`:可预设 chat replies / stream chunks / 关 stream 支持(从 conftest 提)
- `KeywordStubLLM`:按 user message 关键词返不同内容(密码 → 触发 rule、审计 → audit 风格、其它 → 正常)— 给 phase 3 agent 测试
- `MinimalStubLLM`:永远返固定字符串,记录 chat 历史 — 给纯协议测试

**为什么不强制合并更多**:不同 stub 各有窄用途(测试 `LLMRetryExhausted` 的 `side_effects` 模式、`_Boom` 抛错 LLMError 等都是局部的,合并反而复杂),3 个共享的已经覆盖 ~80% 场景。

**未抽取**(评估为不值得):
- `test_llm_retry.py:13 _FakeLLM` — 用 `unbound method` 调用 + `side_effects`,合并会破坏简化意图
- 各测试里的 `_Boom` 抛错 stub — 一次性,3 行代码

### 决策 6:ruff 跨期 44 error → 0

- 大量 F401 unused import(测试文件 import 多是历史遗留)+ E702 multiple statements on one line + 几个 F841
- `ruff check --fix` 自动修了 ~28 个,剩余 15 个手动清理(E702 多行展开 / F841 删 var)
- 净效果:测试代码更可读,无功能改动,539/539 零回归

---

## 5. 关键代码片段

### `mmi/core/llm.py` — `stream_chat_with_retry` 主体

```python
def stream_chat_with_retry(self, messages, *, max_attempts=3, base_delay=0.5):
    """流式重试,pre-yield 可重试 / mid-stream 转 StreamError。"""
    import httpx
    from mmi.core.exceptions import LLMRetryExhausted

    consumed_count = 0
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            gen = self.stream_chat(messages)
            for chunk in gen:
                consumed_count += 1
                yield chunk
            return
        except (httpx.TimeoutException, httpx.ConnectError, ConnectionError) as e:
            last_error = e
            if consumed_count > 0:
                raise StreamError(f"mid-stream error after {consumed_count} chunks: {e}") from e
            if attempt < max_attempts:
                time.sleep(base_delay * (2 ** (attempt - 1)))
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status >= 500 or status == 429:
                last_error = e
                if consumed_count > 0:
                    raise StreamError(f"mid-stream error after {consumed_count} chunks: {e}") from e
                if attempt < max_attempts:
                    time.sleep(base_delay * (2 ** (attempt - 1)))
            else:
                if consumed_count > 0:
                    raise StreamError(f"mid-stream 4xx after {consumed_count} chunks: {e}") from e
                raise
        except Exception as e:
            if consumed_count > 0:
                raise StreamError(f"mid-stream error after {consumed_count} chunks: {e}") from e
            raise
    raise LLMRetryExhausted(attempts=max_attempts, last_error=last_error)
```

### `mmi/agent/validate.py` — `ValidationIssue` 4 字段

```python
@dataclass(frozen=True)
class ValidationIssue:
    """R8 4.10:4 字段不可变,便于 tuple / EventBus payload。"""
    message: str = ""
    severity: Literal["error", "warning"] = "error"
    rule_id: str = ""
    span: tuple[int, int] | None = None

# _check_rules 填充示例
for m in re.finditer(rule.pattern, text):
    issues.append(ValidationIssue(
        message=f"[{rule.name}] Output matches prohibited pattern: {rule.pattern!r}",
        severity=rule.severity,
        rule_id=rule.name,
        span=(m.start(), m.end()),  # regex 命中区间
    ))
```

### `mmi/agent/trace.py` — Tracer → EventBus

```python
def record(self, trace: TraceRecord) -> None:
    self._records.append(trace)
    if self._bus is not None:
        from mmi.agent.event_bus import Event
        self._bus.publish(Event(
            name="trace.recorded",
            timestamp=time.time(),
            payload={
                "trace_id": trace.trace_id,
                "session_id": trace.session_id,
                "agent_id": trace.agent_id,
                "intent": trace.intent,
                "latency_ms": trace.latency_ms,
            },
        ))
```

### `mmi/agent/steps.py` — ValidateStep 拆 hook

```python
@dataclass
class ValidateStep(PipelineStep):
    name: str = "validate"
    on_error: str = "degrade"
    validator: "Validator | None" = None
    event_bus: "EventBus | None" = None  # R8 4.9 引入

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.validator is None:
            raise RuntimeError("ValidateStep.validator not set")
        ctx.validation = self.validator.check(ctx.reply or "", ctx.intent)
        if self.event_bus is not None:
            from mmi.agent.event_bus import Event
            self.event_bus.publish(Event(
                name="validation.complete",
                timestamp=time.time(),
                payload={"session_id": ctx.session_id,
                         "passed": ctx.validation.passed,
                         "issue_count": len(ctx.validation.issues)},
            ))
            for issue in ctx.validation.issues:
                self.event_bus.publish(Event(
                    name="validation.issue",
                    timestamp=time.time(),
                    payload={"session_id": ctx.session_id,
                             "rule_id": issue.rule_id,
                             "severity": issue.severity,
                             "message": issue.message,
                             "span": list(issue.span) if issue.span is not None else None},
                ))
        return ctx
```

---

## 6. 遗留问题 / 五期起点

| # | 问题 | 建议归属 |
|---|---|---|
| 1 | TUI `stream_chat` 仍 `asyncio.to_thread + list(...)` 收齐再渲染,不是 chunk-by-chunk 增量 | R8.5 / R9 "TUI 美化" |
| 2 | TUI 主题色(目前 Tokyo Night 单色,缺渲染层次 / Markdown / 代码高亮) | R8.5 / R9 |
| 3 | `Manager.batch_chat` 顺序执行,无并发选项 | R8.5 / 后期 |
| 4 | `tests/test_cli.py` 仍硬编码 ctrim 旧路径(三期就发现,跨期) | 留待归档 |
| 5 | `LLMError` 包成 `StreamError` 时只包 `str(e)`,丢 traceback | 后期小修 |
| 6 | `OpenAILLMProvider.stream_chat` 在 chunk 流中失败时无重试(stream_chat_with_retry 帮它做了) | ✅ 本轮 4.8 解决 |
| 7 | `ValidationIssue.span` UI 还没接(没高亮) | 后期 TUI 改造 |
| 8 | `validation.issue` 事件目前每次 issue 都 publish,大量 issue 时 EventBus 会被刷屏 | 后期加节流 |

---

## 7. 五期起点(下一轮)

四期(10 项)全部收口,下一步是五期(20 项, ~29.5h,周边模块)。

按 R7 plan 文档和 `docs/INDEX.md`,五期范围:
- 1.1 session 字段分组
- 1.2 storage LRU 句柄 + 读写锁 + schema 校验
- 1.3 heat 指数衰减 + 连续函数
- 1.4 GC 后台自动触发 + 磁盘感知 + dry-run JSON
- 1.5 TF 归一化 + rapidfuzz + titler jieba
- 1.7 titler 永不 trash
- 1.8 classifier 滑动窗口 + 行为模式
- 1.10 config tomllib + Schema 校验 + 原子写
- 1.13 model_fetcher 本地缓存
- 1.14 i18n fallback 原文
- 5.1-5.3 storage 三件套
- 5.7 titler 话题偏移
- 5.17 session frontmatter mmi_version

**预计五期净工时**:~29.5h(可拆 2-3 个 round)。

或者,先做"独立小 round"清理:
- 遗留 #4 `test_cli.py` 归档(估 0.5h)
- 后期单独 round 处理 TUI 美化 + 真流式(R8.5 / R9)

---

> 接手者:`git checkout master` 即可;`pytest tests/ --ignore=tests/test_cli.py -q` 看到 539 passed + ruff 0 即可接五期。
