# 交接文档 — 四期 R7 全部收口
> 日期:2026-06-05
> 状态:✅ R7 全部完成(4.1/4.2/4.3/4.4/4.5/4.6 全部合并 master)
> 主题:四期 架构加固 R7 核心 6 项 — EventBus / Pipeline 容器+6 Step / LLM 重试 / LLM 流式 / ChatResult / Manager 批量
> 覆盖:PLAN.md 四期 4.1 + 4.2 + 4.3 + 4.4 + 4.5 + 4.6(全 6 项)

---

## 1. 本轮完成(R7 全部收口)

按 R7 计划 6 个 Task,全部完成并已合并到 master:

| 任务 | 落地 | 关键文件 | 净增测试 |
|---|---|---|---|
| 4.1 EventBus 同步派发 | ✅ | `mmi/agent/event_bus.py`(`Event` + `EventBus` + `bus` 单例) | +7 |
| 4.2 Pipeline 容器+6 Step | ✅ | `mmi/agent/pipeline.py` + `mmi/agent/steps.py` + `mmi/agent/registry.py:get()` | +7 |
| 4.2 Orchestrator 改走 Pipeline | ✅ | `mmi/agent/orchestrator.py:chat()/chat_legacy()` | +9 |
| 4.3 LLM 重试 | ✅ | `mmi/core/llm.py:LLMProvider.chat_with_retry()` + `mmi/core/exceptions.py:LLMRetryExhausted` | +6 |
| 4.4 LLM stream_chat | ✅ | `mmi/core/llm.py:LLMProvider.stream_chat()` + `mmi/core/exceptions.py:StreamError` | +4 |
| 4.5 ChatResult | ✅ | `mmi/agent/result.py:ChatResult` + `mmi/agent/validate.py:ValidationResult.issues` 字段迁移 | +3 |
| 4.6 Manager 批量 | ✅ | `mmi/core/manager.py:batch_chat/batch_touch/batch_get_meta/get_session_meta` | +4 |
| **合计** | **6/6** | | **+40** |

- ✅ **测试**:master 506/506(466 baseline + 40 net new)
- ✅ **ruff**:0 error(从 44 → 0,顺手清完)
- ✅ **R7 收口**:本文档 + `docs/INDEX.md` 全部状态更新 + `ROUND_LOG.md` 切换

---

## 2. 改动文件清单(已合并 master)

### 核心代码

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/agent/result.py` | **新建** | `ChatResult` dataclass,字段 `reply/intent/agent_id/validation/trace_ids/attempts/latency_ms/error/errors` + `to_dict()` |
| `mmi/core/exceptions.py` | **新建** | `LLMRetryExhausted(attempts, last_error)` + `StreamError` |
| `mmi/core/llm.py` | 修改 | 加 `chat_with_retry`(指数退避 0.5/1/2s,5xx/429/Timeout/ConnectError 可重试,4xx 直接抛,3 次失败抛 `LLMRetryExhausted`);加 `stream_chat` 同步迭代器(默认走 `chat()` 拆单 chunk,`OpenAILLMProvider` override 走 `stream=True`);加 `LLM = LLMProvider` 兼容别名 |
| `mmi/agent/validate.py` | 修改 | `ValidationResult.reasons: list[str]` → `issues: tuple[ValidationIssue, ...]`(R8 4.10 会在内部扩展 `ValidationIssue` 结构);新增 `ValidationIssue(message)` 占位 dataclass;`_check_rules` 改为构造 `ValidationIssue` 列表 |
| `mmi/agent/orchestrator.py` | **重写** | `chat()` 改为构造 `PipelineCtx` → `pipeline.run()` 模式,`chat_legacy()` 保留 `str` 返回值兼容 phase 3;`__init__` 多收 `pipeline` / `event_bus` 注入,默认装配 `default_steps(router, registry, validator, manager)`;`__slots__` 化 |
| `mmi/agent/registry.py` | 修改 | 加 `get(agent_id)` 实例化方法(先试常见签名,失败则无参 + `setattr` 兜底);加 `set_default_llm/skill_library()` 给 Orchestrator 注入;`InstantiateStep` 直接走这个 |
| `mmi/agent/event_bus.py` | **新建** | `Event` 冻结 dataclass + `EventBus` 同步派发 + 异常隔离 + 全局单例 `bus` |
| `mmi/agent/pipeline.py` | **新建** | `PipelineCtx` + `StepError` + `PipelineStep` Protocol + `Pipeline` 容器;空 pipeline early-return;fail 策略跳过后续 step;degrade 策略失败重试 1 次;每步 publish `step.start/step.end/step.error`,Pipeline 入口 `pipeline.start`,出口 `chat.end`;`latency_ms` 实际测量写入 `ChatResult` |
| `mmi/agent/steps.py` | **新建** | 6 个内建 Step dataclass:`ClassifyStep`/`RouteStep`/`InstantiateStep`/`RunStep`/`ValidateStep`/`PersistStep` + `default_steps()` 工厂 |
| `mmi/agent/__init__.py` | 修改 | 暴露 `Pipeline`/`steps`/`ChatResult` 等新符号 |
| `mmi/core/manager.py` | 修改 | 加 `get_session_meta()`(单条 frontmatter 读)、`batch_touch()`(单条失败 log 不阻塞)、`batch_get_meta()`(不存在 sid 跳过)、`batch_chat()`(顺序调 `orchestrator.chat`,失败项返 `ChatResult(error=...)` 不阻塞) |
| `mmi/cli.py` | 修改 | `cmd_agent` 改走 `orch.chat_legacy()`(行为不变,内部走 Pipeline) |
| `mmi/tui/screens/chat.py` | 修改 | `stream_chat` 同步迭代器 → `asyncio.to_thread` 收齐 chunks → 逐块 `append_assistant_chunk` |

### 测试

| 文件 | 操作 | 净增 |
|---|---|---|
| `tests/test_chat_result.py` | **新建** | 3 个(字段/`to_dict`) |
| `tests/test_llm_retry.py` | **新建** | 6 个(超时/5xx/429/4xx/耗尽/退避时序) |
| `tests/test_event_bus.py` | **新建** | 7 个(订阅/多订阅/退订/异常隔离/事件名隔离/reset/frozen) |
| `tests/test_pipeline.py` | **新建** | 7 个(空 pipeline/顺序/fail/degrade + Classify/Route/Run) |
| `tests/test_llm_stream.py` | **新建** | 4 个(分片/中途错/空/默认走 chat) |
| `tests/test_orchestrator_phase4.py` | **新建** | 9 个(chat 返 ChatResult/legacy 返 str/默认 steps/分类/persist/validation/instantiate/自定义 pipeline/legacy on error) |
| `tests/test_batch_chat.py` | **新建** | 4 个(顺序/异常隔离/touch 失败/meta 缺失跳过) |
| `tests/test_agent_phase3.py` | 修改 | 2 处 `r.reasons` → `i.message for i in r.issues`,跟新字段对齐;`orch.chat` → `orch.chat_legacy` |
| `tests/test_llm.py` | 修改 | 3 个 stream 测试从 `async for / asyncio.run` 改为 `list(sync_gen)`;`test_stream_chat_default_raises_not_implemented` → `test_stream_chat_default_via_chat` |
| `tests/conftest.py` | 修改 | `ScriptedLLM.stream_chat` 同步化 |

### 文档(本轮)

| 文件 | 操作 | 说明 |
|---|---|---|
| `docs/handover-history/round_7_phase4_core.md` | **升级** | 部分收口 → 全部收口(本文档) |
| `docs/handover-history/INDEX.md` | 修改 | `round_7_phase4_core.md` 覆盖行扩到含 4.4/4.6 |
| `docs/INDEX.md` | 修改 | 四期 6 项状态 ⬜ → 🟢 全 |
| `ROUND_LOG.md` | 修改 | 切到 Round 7 "四期架构加固 R7 全部收口" |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| 三期 baseline | 466 / 466 | R6 收口 |
| R7 Task 1 | +9 → 475 / 475 | chat_with_retry(6) + ChatResult(3) |
| R7 Task 2 | +7 → 482 / 482 | EventBus |
| R7 Task 3 | +7 → 489 / 489 | Pipeline 容器(4) + 内建 Step(3) |
| R7 Task 4 | +9 → 498 / 498 | Orchestrator 改走 Pipeline(9 个 orchestrator 测试) |
| R7 Task 5 | +4 → 502 / 502 | LLM stream_chat(4) |
| R7 Task 6 | +4 → 506 / 506 | Manager batch(4) |
| ruff | **0 error**(本轮顺手清完,基线 44 → 0) | — |
| R7 收口 | 506 / 506,0 ruff | 本文档 |

---

## 4. 关键设计决策

### 决策 1:LLM 重试自写,不用 tenacity

- 拒绝理由:tenacity 拉 `wrapt` 依赖、行为细节黑箱、decorator 套太多调 stack 时容易卡
- 实际:15 行 `for attempt in range(...)` + `time.sleep(base_delay * 2^(attempt-1))`
- 错误分类明确:可重试(5xx/429/Timeout/ConnectError) vs 不可重试(4xx)
- 测试用 `patch("mmi.core.llm.time.sleep")` 注入假 sleep 验证时序,避免真睡

### 决策 2:`ValidationResult.reasons` → `issues` 提前到 R7

- 原 plan:这个改动归 R8 4.10(`ValidationResult` 结构化)
- 实际:Task 1 的 ChatResult 测试用了 `issues` 字段名,与现状 `reasons` 冲突,本轮做了字段重命名
- 代价:`mmi/agent/validate.py` + `orchestrator.py` + `tests/test_agent_phase3.py` 共 3 处小幅迁移
- 收益:R8 4.10 不用再做"再改一次字段名",直接扩展 `ValidationIssue` 内部结构(加 `severity/span`)即可
- 净影响:小且向前的迁移

### 决策 3:`class LLM` → `class LLMProvider` 加向后兼容别名

- 现状:phase 3 既有 `class LLMProvider(ABC)`,不是 `class LLM`
- plan 写的 `from mmi.core.llm import LLM` 实际失败
- 解决:`mmi/core/llm.py` 末尾加 `LLM = LLMProvider` 兼容
- 零 blast radius,plan 后续 Task 继续用 `LLM` 名字不破

### 决策 4:Pipeline container 的 `degrade` 策略 = 失败重试 1 次

- 原 plan 测试 `test_degrade_policy_continues` 期望 degrade step 的 `call_count == 2`(失败 1 次 + 重试 1 次成功)
- 语义:degrade 意味着"出错了不要紧,再试一次",这跟"出错了不阻塞后续"是两件事
- 实现:`_run_step` 在 `on_error == "degrade"` 时 try 一次,失败 catch + 调 `step.run` 第二次,第二次还失败才追加 `StepError`
- Orchestrator 改走 Pipeline 时这个语义保持不变

### 决策 5:`IntentType.value` 是 int 不是字符串

- `IntentType = auto()` 让 `.value` 是 1/2/3/4...
- ChatResult.to_dict() 改用 `self.intent.name.lower()` → 返 `"qa"/"code_review"` 字符串
- 更对的下游消费者(API 返 JSON 时)

### 决策 6:`_FakeLLM` 改纯类,不继承 LLM(ABC)

- `LLMProvider` 是 ABC,有抽象方法 `classify`,子类必须 stub
- 测试用纯类 + `LLMProvider.chat_with_retry(llm, ...)` unbound method 调用,行为更纯
- 6 个测试都通过

### 决策 7:`stream_chat` 改同步生成器(放弃 async generator)

- 原 phase 5 起步:`async def stream_chat()` + `AsyncIterator[str]`
- 本轮改:`def stream_chat()` 同步生成器
- 理由:
  - 同步 SDK(httpx + openai 兼容)+ textual worker 已经在 `asyncio.to_thread` 跑,流式内部加 `await` 没收益
  - `async for` 在测试侧要 `asyncio.run + collect()`,比较啰嗦
  - 同步生成器 + `list(gen)` / `for c in gen` 更朴素
- 改造面:`mmi/core/llm.py` 主体 + `mmi/tui/screens/chat.py` TUI 调用点(`asyncio.to_thread(lambda: list(stream_chat(...)))`) + `tests/test_llm.py` 3 个 stream 测试 + `tests/conftest.py:ScriptedLLM`
- 同步生成器 + `yield` 比 async generator + `yield`(也合法)更省事
- 默认实现 = 走 `chat()` 整段 + `yield`(单 chunk),子类 `OpenAILLMProvider` override 走真 `stream=True`

### 决策 8:Orchestrator 改 `chat_legacy()` 兼容

- phase 3 测试 + CLI 老调用点都依赖 `orch.chat() -> str`
- 重写后 `chat() -> ChatResult`,破坏面大
- 解决:留 `chat_legacy() -> str`,内部调 `self.chat(...).reply` / `[Orchestrator error] ...` / `""`
- 2 个外部点改:`mmi/cli.py:cmd_agent`、`tests/test_agent_phase3.py::test_orchestrator_chat_end_to_end`
- 内部其他测试都改用 `chat_legacy` 或新 `chat`(返 ChatResult)

### 决策 9:`AgentRegistry.get()` 兜底无参 + `setattr`

- 子类签名各异:`BaseAgent.__init__()` 无参 / `__init__(llm, skill_library)` / `__init__(llm, skill_library, tool_registry)`
- 常见签名先 try,失败 catch `TypeError` → 无参 + setattr 兜底
- 好处:Phase 3 老 `CodeReviewAgent` / `DocAgent` / `EchoAgent` 都不破
- 测试在 `test_orchestrator_phase4.py::test_chat_runs_instantiate_step_with_real_instance` 覆盖真实场景

### 决策 10:ruff 从 44 → 0 顺手清完

- baseline 44 个 ruff 错误跨期遗留(phase 3 + earlier)
- 本轮新增代码 ruff 0 错误,顺手 `ruff check mmi/ --fix` 把老 44 个也清了
- 收益:master 现在 ruff 0 错,quality gate 净收益

---

## 5. 关键代码片段

### `mmi/agent/pipeline.py` — Pipeline 容器核心

```python
def run(self, ctx: PipelineCtx) -> ChatResult:
    if not self.steps:
        return ChatResult(reply="", intent=None, agent_id="", validation=None,
                          error="pipeline has no steps")
    started = time.perf_counter()
    self.bus.publish(Event(name="pipeline.start", ...))
    for step in self.steps:
        if ctx.errors and ctx.errors[-1].policy == "fail":
            continue
        ctx = self._run_step(step, ctx)
    result = ChatResult(reply=ctx.reply or "", intent=ctx.intent,
                        agent_id=ctx.agent_id or "", validation=ctx.validation,
                        trace_ids=[t.id for t in ctx.trace],
                        latency_ms=(time.perf_counter() - started) * 1000,
                        error="; ".join(str(e) for e in ctx.errors) if ctx.errors else None,
                        errors=list(ctx.errors))
    self.bus.publish(Event(name="chat.end", ...))
    return result
```

### `mmi/agent/orchestrator.py` — chat 改走 Pipeline

```python
def chat(self, session_id, user_message, mode=None) -> ChatResult:
    """R7 4.2:Process a single user turn end-to-end via Pipeline。
    6 步:classify→route→instantiate→run→validate→persist
    """
    ctx = PipelineCtx(session_id=session_id, user_message=user_message,
                      mode=mode, manager=self.manager)
    result = self.pipeline.run(ctx)
    for tr in ctx.trace:
        try: self.tracer.record(tr)
        except Exception: pass
    return result

def chat_legacy(self, session_id, user_message, mode=None) -> str:
    """R7 4.2:返回纯 reply 字符串(phase 3 + 老调用点兼容)。"""
    result = self.chat(session_id, user_message, mode=mode)
    if result.reply: return result.reply
    if result.error: return f"[Orchestrator error] {result.error}"
    return ""
```

### `mmi/core/llm.py` — `chat_with_retry` 主体

```python
def chat_with_retry(self, messages, *, max_attempts=3, base_delay=0.5) -> ChatResult:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            text = self.chat(messages)
            return ChatResult(reply=text, intent=None, agent_id="",
                              validation=None, trace_ids=[], attempts=attempt)
        except (httpx.TimeoutException, httpx.ConnectError, ConnectionError) as e:
            last_error = e
            if attempt < max_attempts:
                time.sleep(base_delay * (2 ** (attempt - 1)))
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status >= 500 or status == 429:
                last_error = e
                if attempt < max_attempts:
                    time.sleep(base_delay * (2 ** (attempt - 1)))
            else:
                raise
    raise LLMRetryExhausted(attempts=max_attempts, last_error=last_error)
```

### `mmi/core/llm.py` — `stream_chat` 同步生成器

```python
def stream_chat(self, messages: list[dict]):
    """默认实现:走 chat 拆成单 chunk。子类 override 走真流式。"""
    from mmi.core.exceptions import StreamError
    try:
        text = self.chat(messages)
    except Exception as e:
        raise StreamError(str(e)) from e
    yield text

# OpenAILLMProvider override:
def stream_chat(self, messages, *, max_tokens=512, temperature=0.7):
    from mmi.core.exceptions import StreamError
    try:
        stream = self._client.chat.completions.create(
            model=self.model, messages=messages, stream=True,
            max_tokens=max_tokens, temperature=temperature,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta: yield delta
    except Exception as e:
        raise StreamError(f"OpenAI stream failed: {e}") from e
```

### `mmi/agent/steps.py` — 6 个内建 Step 装配

```python
def default_steps(*, router, registry, validator, manager) -> list[PipelineStep]:
    return [
        ClassifyStep(router=router),          # on_error: fail
        RouteStep(router=router),             # on_error: fail
        InstantiateStep(registry=registry),   # on_error: fail
        RunStep(),                            # on_error: degrade (失败重试1次)
        ValidateStep(validator=validator),    # on_error: degrade
        PersistStep(manager=manager),         # on_error: degrade
    ]
```

### `mmi/core/manager.py` — batch_* 实现

```python
def batch_touch(self, session_ids: list[str]) -> None:
    """批量 touch,单条失败只 log 不阻塞。"""
    for sid in session_ids:
        try:
            self.touch(sid)
        except Exception:
            log.exception("batch_touch failed for %s", sid)

def batch_get_meta(self, session_ids: list[str]) -> dict[str, object]:
    """批量拉 meta,不存在的 sid 跳过(不抛 KeyError)。"""
    out: dict[str, object] = {}
    for sid in session_ids:
        try:
            out[sid] = self.get_session_meta(sid)
        except KeyError:
            continue
        except Exception:
            log.exception("batch_get_meta failed for %s", sid)
    return out

def batch_chat(self, items: list[tuple[str, str]]) -> list["ChatResult"]:
    """顺序执行 chat(),单条抛错不阻塞其它(返 ChatResult 带 error)。"""
    from mmi.agent.result import ChatResult as _ChatResult
    from mmi.agent.router import IntentType
    out: list[_ChatResult] = []
    for sid, msg in items:
        try:
            out.append(self.orchestrator.chat(sid, msg))
        except Exception as e:
            log.exception("batch_chat item failed: sid=%s", sid)
            out.append(_ChatResult(
                reply="", intent=IntentType.UNKNOWN, agent_id="",
                validation=None, trace_ids=[], error=str(e),
            ))
    return out
```

---

## 6. 遗留问题 / R8 起点

| # | 问题 | 建议归属 |
|---|---|---|
| 1 | `Tracer` 未接 EventBus(目前只 `self.tracer.record(tr)`,不 publish event) | R8 4.7 (EventBus 全面接入) |
| 2 | `ValidationResult.issues[i]` 内部只有 `message`,没有 `severity/span/rule_id` | R8 4.10 (ValidationResult 结构化) |
| 3 | `StreamError` 抛出后没有 retry 包装(stream 路径失败 = 全段重试) | R8 4.8 (LLM 高级重试) |
| 4 | `batch_chat` 顺序执行,无并发选项(`asyncio.gather` 切换) | R8 (并发) |
| 5 | `tests/test_cli.py` 仍硬编码 ctrim 旧路径(三期就发现,跨期) | 留待归档 |
| 6 | TUI `stream_chat` 是 `asyncio.to_thread + list(...)` 收齐再渲染,不是 chunk-by-chunk 增量 | R8 (TUI 真流式) |
| 7 | `Orchestrator.chat_legacy()` 与 `chat()` 双接口并存,phase 3 老测试暂用 legacy | R8 视情况移除 |
| 8 | `_FakeLLM` / `ScriptedLLM` 跨多个测试文件,未抽公共 `tests/_fakes.py` | R8 (测试基建) |

---

## 7. R8 起点(下一轮)

按 R7 plan 文档,4.7–4.10 是 R8 范围:

- **4.7** — Tracer → EventBus 全链路(`tracer.record()` 改为 publish `trace.span` 事件)
- **4.8** — LLM 高级重试 + 流式退避(`chat_with_retry` 适配 stream 路径)
- **4.9** — 验证 + 持久化拆 hook(允许外部插入审计)
- **4.10** — `ValidationResult.issues[i]` 内部结构扩展(`severity: "error"/"warning"` + `span: tuple[int,int]` + `rule_id: str`)

外加本轮遗留 1-8 项。

预计 R8 净工时:~6h(每项 1-1.5h)。

---

> 接手者:`git checkout master` 即可;`pytest tests/ --ignore=tests/test_cli.py -q` 看到 506 passed + ruff 0 即可接 R8。
