# MMI 四期核心 (R7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 MMI Agent 调度层从三期"5 步串行硬编码"升级到四期"EventBus + 可插拔 Pipeline + LLM 重试/流式 + 批量接口",为六期多 agent 协作打地基。

**Architecture:** 新增 `mmi/agent/event_bus.py` (同步派发) + `mmi/agent/pipeline.py` (6 个可插拔 Step + 容器) + `mmi/agent/result.py` (ChatResult) + `mmi/agent/steps.py` (6 个内建 Step)。`mmi/core/llm.py` 加 `chat_with_retry` / `stream_chat` / `LLMRetryExhausted` / `StreamError`。`Orchestrator` 退化为 Pipeline 容器装配,公开 API 保持兼容(新增 `chat_legacy()`)。

**Tech Stack:** Python 3.11+ / pytest / ruff / dataclass(不用 Pydantic,跟现状一致)/ httpx(已有)。不引入 tenacity(自写退避),不引入 async(同步迭代器起步)。

**Reference Spec:** `docs/superpowers/specs/2026-06-05-mmi-phase4-design.md` § 1-6
**Reference Baseline:** 三期交接 `docs/handover-history/round_6_phase3.md` — 三期 466/466 测试 + ruff 0 error 是基线

---

## 任务地图

| 任务 | 内容 | 文件 | 净增测试 |
|---|---|---|---|
| 1 | LLM 重试(4.3)+ ChatResult(4.5) | `mmi/core/llm.py` + `mmi/agent/result.py` + `tests/test_llm_retry.py` + `tests/test_chat_result.py` | ~10 |
| 2 | EventBus(4.1) | `mmi/agent/event_bus.py` + `tests/test_event_bus.py` | ~6 |
| 3 | Pipeline 容器 + 6 Step(4.2) | `mmi/agent/pipeline.py` + `mmi/agent/steps.py` + `tests/test_pipeline.py` | ~10 |
| 4 | Orchestrator 改走 Pipeline(4.2 收) | `mmi/agent/orchestrator.py` | (回归既有 ~27) |
| 5 | LLM stream_chat(4.4) | `mmi/core/llm.py` + `tests/test_llm_stream.py` | ~4 |
| 6 | Manager 批量(4.6) | `mmi/core/manager.py` + `tests/test_batch_chat.py` | ~3 |

预计 R7 收口:**全量 ≥ 484 passed**(466 基线 + 18 净增)+ ruff 0 error。

---

## Task 1: LLM 重试 + ChatResult

**Files:**
- Create: `mmi/agent/result.py`
- Create: `mmi/core/exceptions.py`
- Modify: `mmi/core/llm.py`(已有,加方法)
- Create: `tests/test_llm_retry.py`
- Create: `tests/test_chat_result.py`

- [ ] **Step 1.1: 写 ChatResult dataclass 测试**

创建 `tests/test_chat_result.py`:

```python
"""ChatResult 数据契约测试。"""
from mmi.agent.result import ChatResult
from mmi.agent.validate import ValidationResult, ValidationIssue
from mmi.agent.router import IntentType


def test_chat_result_required_fields():
    r = ChatResult(
        reply="hi",
        intent=IntentType.QA,
        agent_id="qa",
        validation=None,
        trace_ids=[],
    )
    assert r.reply == "hi"
    assert r.intent == IntentType.QA
    assert r.attempts == 1
    assert r.latency_ms == 0.0
    assert r.error is None


def test_chat_result_with_error():
    r = ChatResult(
        reply="",
        intent=IntentType.QA,
        agent_id="qa",
        validation=None,
        trace_ids=["t1"],
        attempts=3,
        latency_ms=1234.5,
        error="LLM timeout",
    )
    assert r.attempts == 3
    assert r.latency_ms == 1234.5
    assert r.error == "LLM timeout"
    assert r.trace_ids == ["t1"]


def test_chat_result_to_dict():
    r = ChatResult(
        reply="ok",
        intent=IntentType.QA,
        agent_id="qa",
        validation=ValidationResult(passed=True, issues=()),
        trace_ids=[],
    )
    d = r.to_dict()
    assert d["reply"] == "ok"
    assert d["intent"] == "qa"
    assert d["agent_id"] == "qa"
    assert d["validation"] == {"passed": True, "issues": []}
```

- [ ] **Step 1.2: 跑测试,确认失败**

Run: `pytest tests/test_chat_result.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mmi.agent.result'`

- [ ] **Step 1.3: 实现 ChatResult**

创建 `mmi/agent/result.py`:

```python
"""统一的 chat 结果数据契约。"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mmi.agent.router import IntentType
    from mmi.agent.validate import ValidationResult


@dataclass
class ChatResult:
    reply: str
    intent: "IntentType"
    agent_id: str
    validation: "ValidationResult | None"
    trace_ids: list[str] = field(default_factory=list)
    attempts: int = 1
    latency_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # IntentType 枚举转字符串;ValidationResult 走自己的 to_dict
        d["intent"] = self.intent.value
        if self.validation is not None and hasattr(self.validation, "to_dict"):
            d["validation"] = self.validation.to_dict()
        return d
```

注:这里依赖 `ValidationResult.to_dict`,4.10 R8 才会加。如果 R7 阶段 ValidationResult 还没有 `to_dict` 方法,本测试用 `assert d["validation"] == {"passed": True, "issues": []}` 时会失败 — 临时方案:R7 阶段 ChatResult.to_dict 直接保留 `validation` 字段(不调 to_dict),用 `asdict` 出原始结构。**采纳这个简化方案**,R8 4.10 落地后 ChatResult.to_dict 不需要再改。

修改 `mmi/agent/result.py` 的 `to_dict`:

```python
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["intent"] = self.intent.value
        return d
```

- [ ] **Step 1.4: 跑测试,确认通过**

Run: `pytest tests/test_chat_result.py -v`
Expected: 3 passed

- [ ] **Step 1.5: 实现异常类**

创建 `mmi/core/exceptions.py`:

```python
"""mmi 内部异常类。"""
from __future__ import annotations


class LLMRetryExhausted(Exception):
    """LLM 重试 max_attempts 次后仍失败。"""

    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"LLM retry exhausted after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


class StreamError(Exception):
    """流式 LLM 调用中途出错。"""
```

- [ ] **Step 1.6: 写 LLM 重试测试**

创建 `tests/test_llm_retry.py`:

```python
"""LLM.chat_with_retry 行为测试。"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

from mmi.core.exceptions import LLMRetryExhausted
from mmi.core.llm import LLM


class _FakeLLM(LLM):
    """跳过 __init__,只暴露 chat_with_retry 行为。"""

    def __init__(self, side_effects: list):
        # 故意绕过 LLM.__init__,只接 side_effects
        self._side_effects = list(side_effects)
        self.call_count = 0
        self.sleeps: list[float] = []

    def chat(self, messages):
        self.call_count += 1
        eff = self._side_effects.pop(0) if self._side_effects else "ok"
        if isinstance(eff, Exception):
            raise eff
        return eff


def test_retry_on_timeout_then_success():
    timeout = httpx.TimeoutException("timeout")
    llm = _FakeLLM([timeout, "ok"])
    with patch("mmi.core.llm.time.sleep") as mock_sleep:
        result = llm.chat_with_retry([{"role": "user", "content": "hi"}])
    assert result.reply == "ok"
    assert result.attempts == 2
    assert llm.call_count == 2
    assert mock_sleep.call_count == 1
    # 退避 0.5s
    assert mock_sleep.call_args.args == (0.5,)


def test_retry_on_5xx_then_success():
    # httpx.HTTPStatusError 5xx 可重试
    req = httpx.Request("POST", "https://api.example.com")
    resp = httpx.Response(503, request=req)
    err5xx = httpx.HTTPStatusError("503", request=req, response=resp)
    llm = _FakeLLM([err5xx, "ok"])
    with patch("mmi.core.llm.time.sleep"):
        result = llm.chat_with_retry([])
    assert result.attempts == 2
    assert result.reply == "ok"


def test_retry_on_429_too_many_requests():
    req = httpx.Request("POST", "https://api.example.com")
    resp = httpx.Response(429, request=req)
    err429 = httpx.HTTPStatusError("429", request=req, response=resp)
    llm = _FakeLLM([err429, "ok"])
    with patch("mmi.core.llm.time.sleep"):
        result = llm.chat_with_retry([])
    assert result.attempts == 2


def test_no_retry_on_4xx():
    req = httpx.Request("POST", "https://api.example.com")
    resp = httpx.Response(400, request=req)
    err400 = httpx.HTTPStatusError("400", request=req, response=resp)
    llm = _FakeLLM([err400])
    with pytest.raises(httpx.HTTPStatusError):
        llm.chat_with_retry([])
    assert llm.call_count == 1  # 没重试


def test_retry_exhausted_raises():
    timeout = httpx.TimeoutException("timeout")
    llm = _FakeLLM([timeout, timeout, timeout])
    with patch("mmi.core.llm.time.sleep"):
        with pytest.raises(LLMRetryExhausted) as ei:
            llm.chat_with_retry([])
    assert ei.value.attempts == 3
    assert llm.call_count == 3


def test_retry_backoff_timing():
    timeout = httpx.TimeoutException("timeout")
    llm = _FakeLLM([timeout, timeout, "ok"])
    sleeps: list[float] = []
    with patch("mmi.core.llm.time.sleep", side_effect=lambda s: sleeps.append(s)):
        result = llm.chat_with_retry([])
    assert sleeps == [0.5, 1.0]  # 第 3 次成功前退避 0.5+1.0
    assert result.attempts == 3
```

- [ ] **Step 1.7: 跑测试,确认失败**

Run: `pytest tests/test_llm_retry.py -v`
Expected: FAIL with `AttributeError: 'LLM' object has no attribute 'chat_with_retry'`

- [ ] **Step 1.8: 在 LLM 加 chat_with_retry**

先读一下当前 `mmi/core/llm.py`,找到 `LLM` 类的位置:

Run: `grep -n "class LLM\|def chat" mmi/core/llm.py`

按现状追加方法(假设 `class LLM` 有 `def chat(self, messages) -> str`)。具体位置用 Edit 工具替换,在 `class LLM` 内 `def chat` 之后追加:

```python
    def chat_with_retry(
        self,
        messages: list[dict],
        *,
        max_attempts: int = 3,
        base_delay: float = 0.5,
    ) -> "ChatResult":
        """指数退避重试。5xx / 429 / Timeout / ConnectError 可重试,4xx 直接抛。"""
        from mmi.agent.result import ChatResult
        from mmi.core.exceptions import LLMRetryExhausted

        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                text = self.chat(messages)
                return ChatResult(
                    reply=text,
                    intent=None,  # 由 Pipeline 在 RunStep 设置
                    agent_id="",
                    validation=None,
                    trace_ids=[],
                    attempts=attempt,
                )
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

注意:在文件顶部加 `import time`(如果还没) 和 `import httpx`(如果还没)。

- [ ] **Step 1.9: 跑测试,确认通过**

Run: `pytest tests/test_llm_retry.py tests/test_chat_result.py -v`
Expected: 6 + 3 = 9 passed

- [ ] **Step 1.10: 跑全量,确认无回归**

Run: `pytest tests/ -x --ignore=tests/test_cli.py -q`
Expected: 466(基线)+ 9 = 475 passed

Run: `ruff check mmi/ tests/`
Expected: 0 error

- [ ] **Step 1.11: Commit**

```bash
git add mmi/agent/result.py mmi/core/exceptions.py mmi/core/llm.py tests/test_llm_retry.py tests/test_chat_result.py
git commit -m "feat(4.3+4.5): LLM chat_with_retry + ChatResult"
```

---

## Task 2: EventBus

**Files:**
- Create: `mmi/agent/event_bus.py`
- Create: `tests/test_event_bus.py`

- [ ] **Step 2.1: 写 EventBus 测试**

创建 `tests/test_event_bus.py`:

```python
"""EventBus 行为测试。"""
from __future__ import annotations

from mmi.agent.event_bus import Event, EventBus


def test_subscribe_and_publish():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("test", lambda e: received.append(e))
    bus.publish(Event(name="test", timestamp=0.0, payload={"k": 1}))
    assert len(received) == 1
    assert received[0].name == "test"
    assert received[0].payload == {"k": 1}


def test_multiple_subscribers_all_called():
    bus = EventBus()
    a, b = [], []
    bus.subscribe("e", lambda e: a.append(e))
    bus.subscribe("e", lambda e: b.append(e))
    bus.publish(Event(name="e", timestamp=0.0))
    assert len(a) == 1
    assert len(b) == 1


def test_unsubscribe():
    bus = EventBus()
    received: list[Event] = []
    h = lambda e: received.append(e)
    bus.subscribe("e", h)
    bus.unsubscribe("e", h)
    bus.publish(Event(name="e", timestamp=0.0))
    assert received == []


def test_handler_exception_isolated():
    bus = EventBus()
    a, b = [], []
    bus.subscribe("e", lambda e: a.append(e))
    bus.subscribe("e", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("e", lambda e: b.append(e))
    # 第二个 handler 抛错,第一第三仍要跑通
    bus.publish(Event(name="e", timestamp=0.0))
    assert len(a) == 1
    assert len(b) == 1


def test_different_events_isolated():
    bus = EventBus()
    a, b = [], []
    bus.subscribe("a", lambda e: a.append(e))
    bus.subscribe("b", lambda e: b.append(e))
    bus.publish(Event(name="a", timestamp=0.0))
    assert len(a) == 1
    assert b == []


def test_reset_clears_subscribers():
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe("e", lambda e: received.append(e))
    bus.reset()
    bus.publish(Event(name="e", timestamp=0.0))
    assert received == []


def test_event_is_frozen():
    e = Event(name="x", timestamp=0.0)
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.name = "y"  # type: ignore[misc]
```

(顶部加 `import pytest`)

- [ ] **Step 2.2: 跑测试,确认失败**

Run: `pytest tests/test_event_bus.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mmi.agent.event_bus'`

- [ ] **Step 2.3: 实现 EventBus**

创建 `mmi/agent/event_bus.py`:

```python
"""轻量级 EventBus,同步派发,handler 异常隔离。"""
from __future__ import annotations

import dataclasses
import logging
from collections import defaultdict
from typing import Callable

log = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Event:
    name: str
    timestamp: float
    payload: dict[str, object] = dataclasses.field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable[[Event], None]) -> None:
        self._subs[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Callable[[Event], None]) -> None:
        if event_name in self._subs:
            try:
                self._subs[event_name].remove(handler)
            except ValueError:
                pass

    def publish(self, event: Event) -> None:
        for handler in list(self._subs.get(event.name, [])):
            try:
                handler(event)
            except Exception:
                log.exception("EventBus handler %r for %r failed", handler, event.name)

    def reset(self) -> None:
        self._subs.clear()


# 全局单例
bus = EventBus()
```

- [ ] **Step 2.4: 跑测试,确认通过**

Run: `pytest tests/test_event_bus.py -v`
Expected: 7 passed

- [ ] **Step 2.5: 跑全量 + ruff**

Run: `pytest tests/ -x --ignore=tests/test_cli.py -q`
Expected: 475(基线)+ 7 = 482 passed

Run: `ruff check mmi/ tests/`
Expected: 0 error

- [ ] **Step 2.6: Commit**

```bash
git add mmi/agent/event_bus.py tests/test_event_bus.py
git commit -m "feat(4.1): EventBus 同步派发 + 异常隔离"
```

---

## Task 3: Pipeline 容器 + 6 个内建 Step

**Files:**
- Create: `mmi/agent/pipeline.py`
- Create: `mmi/agent/steps.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 3.1: 写 Pipeline 容器测试(空 pipeline + fake step)**

创建 `tests/test_pipeline.py`:

```python
"""Pipeline 容器 + 6 个内建 Step 行为测试。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import pytest

from mmi.agent.pipeline import Pipeline, PipelineCtx, StepError
from mmi.agent.router import IntentType


# ── 容器测试 ─────────────────────────────────────────────


def test_empty_pipeline_returns_chat_result_with_error():
    ctx = PipelineCtx(session_id="s1", user_message="hi")
    p = Pipeline([])
    result = p.run(ctx)
    # 空 pipeline:无 reply,error 标 "no steps"
    assert result.reply == ""
    assert result.error is not None
    assert "no steps" in result.error.lower()


@dataclass
class _NoopStep:
    name: ClassVar[str] = "noop"
    on_error: ClassVar[str] = "degrade"
    call_count: int = 0

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        self.call_count += 1
        return ctx


def test_pipeline_runs_steps_in_order():
    s1, s2, s3 = _NoopStep(), _NoopStep(), _NoopStep()
    s1.name = "a"; s2.name = "b"; s3.name = "c"
    p = Pipeline([s1, s2, s3])
    p.run(PipelineCtx(session_id="s1", user_message="x"))
    assert s1.call_count == s2.call_count == s3.call_count == 1


@dataclass
class _FailStep:
    name: ClassVar[str] = "fail"
    on_error: ClassVar[str] = "fail"

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        raise RuntimeError("boom")


def test_fail_policy_stops_pipeline():
    s_ok, s_bad = _NoopStep(), _FailStep()
    s_ok.name = "ok"
    p = Pipeline([s_ok, s_bad])
    result = p.run(PipelineCtx(session_id="s1", user_message="x"))
    assert result.error is not None
    assert "fail" in result.error.lower()


@dataclass
class _DegradeStep:
    name: ClassVar[str] = "degrade"
    on_error: ClassVar[str] = "degrade"
    call_count: int = 0

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("first call fail")
        return ctx


def test_degrade_policy_continues():
    s = _DegradeStep()
    s_after = _NoopStep()
    s_after.name = "after"
    p = Pipeline([s, s_after])
    result = p.run(PipelineCtx(session_id="s1", user_message="x"))
    assert s.call_count == 2  # 失败重试 1 次
    assert s_after.call_count == 1  # 后续 step 仍跑
    assert any("first call fail" in str(e) for e in result.errors)


# ── 内建 Step 测试 ─────────────────────────────────────────


def test_classify_step_sets_intent():
    from mmi.agent.steps import ClassifyStep
    from mmi.agent.router import Router

    router = Router()
    step = ClassifyStep(router=router)
    ctx = step.run(PipelineCtx(session_id="s1", user_message="审查一下这段代码"))
    assert ctx.intent == IntentType.CODE_REVIEW


def test_route_step_picks_first_agent():
    from mmi.agent.steps import RouteStep
    from mmi.agent.router import Router

    step = RouteStep(router=Router())
    ctx = PipelineCtx(session_id="s1", user_message="x", intent=IntentType.QA)
    ctx = step.run(ctx)
    assert ctx.agent_id == "qa"


def test_run_step_degrade_on_agent_error():
    from mmi.agent.steps import RunStep
    from mmi.agent.base import BaseAgent
    from mmi.agent.router import IntentType

    class _BoomAgent(BaseAgent):
        @property
        def name(self) -> str:
            return "boom"

        def run(self, user_message, *, mode=None):
            raise RuntimeError("agent down")

    agent = _BoomAgent(llm=None, system_prompt="x")
    step = RunStep()
    ctx = step.run(PipelineCtx(
        session_id="s1", user_message="hi", intent=IntentType.QA, agent=agent
    ))
    # reply 是脱敏占位
    assert ctx.reply is not None
    assert ctx.reply != ""
    assert len(ctx.errors) == 1
```

(顶部加 `from mmi.agent.router import IntentType` 已经存在;补 `pytest` import)

- [ ] **Step 3.2: 跑测试,确认失败**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mmi.agent.pipeline'`

- [ ] **Step 3.3: 实现 Pipeline 容器**

创建 `mmi/agent/pipeline.py`:

```python
"""可插拔 Pipeline:把 Orchestrator 的 5 步拆成 Step + 容器。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from mmi.agent.event_bus import Event, bus as default_bus

if TYPE_CHECKING:
    from mmi.agent.event_bus import EventBus
    from mmi.agent.modes import ThinkingMode
    from mmi.agent.result import ChatResult
    from mmi.agent.router import IntentType
    from mmi.agent.trace import TraceRecord
    from mmi.agent.validate import ValidationResult
    from mmi.core.manager import SessionManager

log = logging.getLogger(__name__)


@dataclass
class StepError:
    step: str
    cause: Exception
    policy: str

    def __str__(self) -> str:
        return f"[{self.step}] {self.cause!r}"


@dataclass
class PipelineCtx:
    session_id: str
    user_message: str
    mode: "ThinkingMode | None" = None
    intent: "IntentType | None" = None
    agent_id: str | None = None
    agent: object = None  # BaseAgent | None
    reply: str | None = None
    validation: "ValidationResult | None" = None
    trace: list["TraceRecord"] = field(default_factory=list)
    errors: list[StepError] = field(default_factory=list)
    chat_result: "ChatResult | None" = None
    manager: "SessionManager | None" = None


@runtime_checkable
class PipelineStep(Protocol):
    name: str
    on_error: str  # "fail" | "degrade" | "skip"

    def run(self, ctx: PipelineCtx) -> PipelineCtx: ...


class Pipeline:
    def __init__(
        self,
        steps: list[PipelineStep],
        *,
        event_bus: "EventBus | None" = None,
    ) -> None:
        self.steps = steps
        self.bus = event_bus or default_bus

    def run(self, ctx: PipelineCtx) -> "ChatResult":
        # 局部 import 避免循环
        from mmi.agent.result import ChatResult

        started = time.perf_counter()
        self.bus.publish(Event(
            name="pipeline.start",
            timestamp=time.time(),
            payload={"session_id": ctx.session_id, "user_message": ctx.user_message},
        ))

        for step in self.steps:
            ctx = self._run_step(step, ctx)

        result = ChatResult(
            reply=ctx.reply or "",
            intent=ctx.intent,
            agent_id=ctx.agent_id or "",
            validation=ctx.validation,
            trace_ids=[t.id for t in ctx.trace],
            latency_ms=(time.perf_counter() - started) * 1000,
            error="; ".join(str(e) for e in ctx.errors) if ctx.errors else None,
        )
        ctx.chat_result = result

        self.bus.publish(Event(
            name="chat.end",
            timestamp=time.time(),
            payload={
                "session_id": ctx.session_id,
                "agent_id": ctx.agent_id,
                "latency_ms": result.latency_ms,
                "attempts": result.attempts,
            },
        ))
        return result

    def _run_step(self, step: PipelineStep, ctx: PipelineCtx) -> PipelineCtx:
        self.bus.publish(Event(
            name="step.start",
            timestamp=time.time(),
            payload={"step": step.name},
        ))
        t0 = time.perf_counter()
        try:
            ctx = step.run(ctx)
            self.bus.publish(Event(
                name="step.end",
                timestamp=time.time(),
                payload={"step": step.name, "duration_ms": (time.perf_counter() - t0) * 1000},
            ))
            return ctx
        except Exception as e:
            err = StepError(step=step.name, cause=e, policy=step.on_error)
            log.exception("Step %s failed", step.name)
            self.bus.publish(Event(
                name="step.error",
                timestamp=time.time(),
                payload={"step": step.name, "error": str(e), "policy": step.on_error},
            ))
            if step.on_error == "fail":
                # 后续 step 由外层 for 循环的 `if ctx.errors[-1].policy == "fail": continue` 跳过
                ctx.errors.append(err)
                return ctx
            elif step.on_error == "degrade":
                ctx.errors.append(err)
                return ctx
            else:  # skip
                return ctx
```

外层 for 循环的跳过判断:

```python
        for step in self.steps:
            # 上一步是 fail 策略且出错,后续 step 全部跳过
            if ctx.errors and ctx.errors[-1].policy == "fail":
                continue
            ctx = self._run_step(step, ctx)
```

- [ ] **Step 3.4: 跑容器测试,确认通过**

Run: `pytest tests/test_pipeline.py -v -k "not ClassifyStep and not RouteStep and not RunStep"`
Expected: 4 passed(空 pipeline / 顺序 / fail / degrade)

- [ ] **Step 3.5: 实现 6 个内建 Step**

创建 `mmi/agent/steps.py`:

```python
"""Pipeline 内建 Step 实现。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mmi.agent.pipeline import PipelineCtx, PipelineStep

if TYPE_CHECKING:
    from mmi.agent.base import BaseAgent
    from mmi.agent.router import IntentType, Router
    from mmi.agent.validate import Validator
    from mmi.core.manager import SessionManager

log = logging.getLogger(__name__)


@dataclass
class ClassifyStep(PipelineStep):
    name: str = "classify"
    on_error: str = "fail"
    router: "Router | None" = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.router is None:
            raise RuntimeError("ClassifyStep.router not set")
        ctx.intent = self.router.classify(ctx.user_message)
        return ctx


@dataclass
class RouteStep(PipelineStep):
    name: str = "route"
    on_error: str = "fail"
    router: "Router | None" = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.router is None or ctx.intent is None:
            raise RuntimeError("RouteStep.router/intent missing")
        ids = self.router.route(ctx.intent)
        ctx.agent_id = ids[0] if ids else "qa"
        return ctx


@dataclass
class InstantiateStep(PipelineStep):
    name: str = "instantiate"
    on_error: str = "fail"
    registry: object = None  # AgentRegistry

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.registry is None or ctx.agent_id is None:
            raise RuntimeError("InstantiateStep.registry/agent_id missing")
        agent = self.registry.get(ctx.agent_id)
        if agent is None:
            raise RuntimeError(f"agent {ctx.agent_id!r} not registered")
        ctx.agent = agent
        return ctx


@dataclass
class RunStep(PipelineStep):
    name: str = "run"
    on_error: str = "degrade"

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if ctx.agent is None:
            raise RuntimeError("RunStep: ctx.agent is None")
        try:
            ctx.reply = ctx.agent.run(ctx.user_message, mode=ctx.mode)
        except Exception as e:
            # 脱敏占位
            ctx.reply = f"[LLM 暂时不可用: {type(e).__name__}]"
            log.exception("RunStep agent.run failed")
            raise  # 由 Pipeline 容器记 ctx.errors
        return ctx


@dataclass
class ValidateStep(PipelineStep):
    name: str = "validate"
    on_error: str = "degrade"
    validator: "Validator | None" = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.validator is None:
            raise RuntimeError("ValidateStep.validator not set")
        reply = ctx.reply or ""
        ctx.validation = self.validator.check(reply, ctx.intent)
        return ctx


@dataclass
class PersistStep(PipelineStep):
    name: str = "persist"
    on_error: str = "degrade"
    manager: "SessionManager | None" = None

    def run(self, ctx: PipelineCtx) -> PipelineCtx:
        if self.manager is None:
            raise RuntimeError("PersistStep.manager not set")
        self.manager.persist_turn(
            session_id=ctx.session_id,
            user_input=ctx.user_message,
            reply=ctx.reply or "",
        )
        return ctx


def default_steps(
    *,
    router: "Router",
    registry: object,
    validator: "Validator",
    manager: "SessionManager",
) -> list[PipelineStep]:
    """返回 6 个内建 Step 的默认装配。"""
    return [
        ClassifyStep(router=router),
        RouteStep(router=router),
        InstantiateStep(registry=registry),
        RunStep(),
        ValidateStep(validator=validator),
        PersistStep(manager=manager),
    ]
```

- [ ] **Step 3.6: 跑全测试,确认通过**

Run: `pytest tests/test_pipeline.py -v`
Expected: 7 passed(4 容器 + 3 内建)

如果某些测试因 BaseAgent 实际签名不符失败,打开 `mmi/agent/base.py` 看 `BaseAgent.__init__` 签名,调整 `_BoomAgent` 测试构造(可能是 `BaseAgent.__init__` 强制要 `llm` 参数,改 `agent = _BoomAgent(llm=MagicMock(), system_prompt="x")`)。

- [ ] **Step 3.7: 跑全量 + ruff**

Run: `pytest tests/ -x --ignore=tests/test_cli.py -q`
Expected: 482(基线)+ 7 = 489 passed

Run: `ruff check mmi/ tests/`
Expected: 0 error

- [ ] **Step 3.8: Commit**

```bash
git add mmi/agent/pipeline.py mmi/agent/steps.py tests/test_pipeline.py
git commit -m "feat(4.2): Pipeline 容器 + 6 个内建 Step"
```

---

## Task 4: Orchestrator 改走 Pipeline(4.2 收口)

**Files:**
- Modify: `mmi/agent/orchestrator.py`(已有)
- Modify: `mmi/agent/__init__.py`(暴露新符号)

- [ ] **Step 4.1: 写 Orchestrator 行为测试(走 Pipeline)**

打开三期既有 `tests/test_agent_phase3.py`,确保现有 ~27 个测试仍通过(基线)。**不**在 Phase3 测试里加东西,新增测试进 `tests/test_pipeline.py`(Task 3 已含部分),这里补 Orchestrator 公开 API 形状的回归测试。

创建 `tests/test_orchestrator_phase4.py`:

```python
"""Orchestrator 走 Pipeline + chat_legacy 兼容。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mmi.agent.orchestrator import Orchestrator


@pytest.fixture
def orch():
    llm = MagicMock()
    llm.chat_with_retry.return_value = MagicMock(reply="hi", attempts=1)
    orch = Orchestrator(llm=llm)
    return orch


def test_chat_returns_chat_result(orch):
    result = orch.chat("s1", "hi")
    assert hasattr(result, "reply")
    assert result.reply == "hi"


def test_chat_legacy_returns_str(orch):
    s = orch.chat_legacy("s1", "hi")
    assert isinstance(s, str)
    assert s == "hi"
```

- [ ] **Step 4.2: 跑测试,确认失败**

Run: `pytest tests/test_orchestrator_phase4.py -v`
Expected: FAIL(可能是 `Orchestrator` 不接受 `llm` 单独参数,或者 `chat` 返 `str` 不是 ChatResult)

- [ ] **Step 4.3: 改造 Orchestrator**

读 `mmi/agent/orchestrator.py`,把 `chat()` 方法改造,内部走 Pipeline:

```python
from mmi.agent.pipeline import Pipeline, PipelineCtx
from mmi.agent.steps import default_steps
from mmi.agent.result import ChatResult
# 其它 import 保持

class Orchestrator:
    def __init__(
        self,
        *,
        llm=None,
        router=None,
        registry=None,
        validator=None,
        manager=None,
        pipeline: Pipeline | None = None,
    ):
        self.llm = llm
        self.router = router or Router()
        self.registry = registry or AgentRegistry.get_instance()
        self.validator = validator or Validator()
        self.manager = manager
        self.pipeline = pipeline or Pipeline(default_steps(
            router=self.router,
            registry=self.registry,
            validator=self.validator,
            manager=self.manager,
        ))

    def chat(self, session_id, user_message, *, mode=None) -> ChatResult:
        ctx = PipelineCtx(
            session_id=session_id,
            user_message=user_message,
            mode=mode,
            manager=self.manager,
        )
        return self.pipeline.run(ctx)

    def chat_legacy(self, session_id, user_message, *, mode=None) -> str:
        return self.chat(session_id, user_message, mode=mode).reply
```

具体怎么改三期既有 Orchestrator,根据实际情况调整(可能既有 `__init__` 签名不同,需要保留兼容)。**原则**:对外 API 行为不能破(既有 27 个测试要继续过),`chat()` 内部走 `self.pipeline.run(ctx)`。

- [ ] **Step 4.4: 跑全量测试**

Run: `pytest tests/ -x --ignore=tests/test_cli.py -q`
Expected: 489(基线)+ 2 = 491 passed

Run: `ruff check mmi/ tests/`
Expected: 0 error

- [ ] **Step 4.5: Commit**

```bash
git add mmi/agent/orchestrator.py mmi/agent/__init__.py tests/test_orchestrator_phase4.py
git commit -m "refactor(4.2): Orchestrator 内部走 Pipeline + chat_legacy 兼容"
```

---

## Task 5: LLM stream_chat

**Files:**
- Modify: `mmi/core/llm.py`(加 `stream_chat` + `StreamError` 已在 exceptions)
- Create: `tests/test_llm_stream.py`

- [ ] **Step 5.1: 写 stream_chat 测试**

创建 `tests/test_llm_stream.py`:

```python
"""LLM.stream_chat 行为测试。"""
from __future__ import annotations

import pytest

from mmi.core.exceptions import StreamError
from mmi.core.llm import LLM


class _FakeStreamLLM(LLM):
    def __init__(self, chunks: list):
        self._chunks = list(chunks)
        self.call_count = 0

    def chat(self, messages):
        # 不走 chat,强制走 stream
        raise RuntimeError("should not be called")

    def stream_chat(self, messages):
        self.call_count += 1
        for c in self._chunks:
            if isinstance(c, Exception):
                raise StreamError(str(c))
            yield c


def test_stream_iterates_chunks():
    llm = _FakeStreamLLM(["He", "llo", " world"])
    out = list(llm.stream_chat([]))
    assert "".join(out) == "Hello world"


def test_stream_raises_on_mid_chunk_error():
    llm = _FakeStreamLLM(["a", "b", RuntimeError("net"), "c"])
    with pytest.raises(StreamError):
        list(llm.stream_chat([]))


def test_stream_empty():
    llm = _FakeStreamLLM([])
    assert list(llm.stream_chat([])) == []
```

(顶部加 `import pytest`)

- [ ] **Step 5.2: 跑测试,确认失败**

Run: `pytest tests/test_llm_stream.py -v`
Expected: FAIL with `AttributeError: 'LLM' object has no attribute 'stream_chat'`

- [ ] **Step 5.3: 在 LLM 基类加 stream_chat 默认实现**

在 `mmi/core/llm.py` 的 `class LLM` 内加默认方法(子 Provider 可 override):

```python
    def stream_chat(self, messages: list[dict]):
        """默认实现:走 chat,拆成单 chunk。子类可 override 走真流式。"""
        from mmi.core.exceptions import StreamError
        try:
            text = self.chat(messages)
        except Exception as e:
            raise StreamError(str(e)) from e
        yield text
```

OpenAI 兼容 Provider 真支持流式时,override 这个方法走 `client.chat.completions.create(stream=True)`。

- [ ] **Step 5.4: 跑测试,确认通过**

Run: `pytest tests/test_llm_stream.py -v`
Expected: 3 passed

- [ ] **Step 5.5: 跑全量 + ruff**

Run: `pytest tests/ -x --ignore=tests/test_cli.py -q`
Expected: 491(基线)+ 3 = 494 passed

Run: `ruff check mmi/ tests/`
Expected: 0 error

- [ ] **Step 5.6: Commit**

```bash
git add mmi/core/llm.py tests/test_llm_stream.py
git commit -m "feat(4.4): LLM.stream_chat 同步迭代器 + StreamError"
```

---

## Task 6: Manager 批量接口

**Files:**
- Modify: `mmi/core/manager.py`(加 batch_* 方法)
- Create: `tests/test_batch_chat.py`

- [ ] **Step 6.1: 写批量测试**

创建 `tests/test_batch_chat.py`:

```python
"""Manager.batch_* 行为测试。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mmi.agent.result import ChatResult
from mmi.agent.router import IntentType


@pytest.fixture
def manager():
    from mmi.core.manager import SessionManager
    m = SessionManager.__new__(SessionManager)  # 跳过 __init__
    m.orchestrator = MagicMock()
    return m


def test_batch_chat_returns_results(manager):
    manager.orchestrator.chat.side_effect = [
        ChatResult(reply="a", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
        ChatResult(reply="b", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
    ]
    out = manager.batch_chat([("s1", "hi"), ("s2", "yo")])
    assert [r.reply for r in out] == ["a", "b"]
    assert manager.orchestrator.chat.call_count == 2


def test_batch_chat_isolates_exception(manager):
    manager.orchestrator.chat.side_effect = [
        ChatResult(reply="a", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
        RuntimeError("boom"),
        ChatResult(reply="c", intent=IntentType.QA, agent_id="qa", validation=None, trace_ids=[]),
    ]
    # batch_chat 当前不隔离异常(Task 6.3 实现 degrade 行为);先看真实实现
    # 本测试在 Step 6.3 完成后才能 PASS
    pytest.skip("等 batch_chat degrade 实现")


def test_batch_touch_isolates_failure(manager):
    manager.touch = MagicMock(side_effect=[None, RuntimeError("x"), None])
    # 单条失败不阻塞其它
    manager.batch_touch(["s1", "s2", "s3"])
    assert manager.touch.call_count == 3


def test_batch_get_meta_skips_missing(manager):
    manager.get_session_meta = MagicMock(side_effect=[
        {"id": "s1", "title": "t1"},
        KeyError("s2 missing"),
        {"id": "s3", "title": "t3"},
    ])
    out = manager.batch_get_meta(["s1", "s2", "s3"])
    assert "s1" in out
    assert "s2" not in out
    assert "s3" in out
```

注:`KeyError` 顶层 import 一下。`test_batch_chat_isolates_exception` 标 skip,在 Step 6.3 取消 skip。

- [ ] **Step 6.2: 跑测试,看哪些失败**

Run: `pytest tests/test_batch_chat.py -v`
Expected: 失败 `test_batch_chat_returns_results`(无 `batch_chat`)和 `test_batch_touch_isolates_failure`(无 `batch_touch`)。`test_batch_get_meta_skips_missing` 同。

- [ ] **Step 6.3: 在 Manager 加 batch_* 方法**

读 `mmi/core/manager.py` 找到 `def touch` / `def get_session_meta`,在附近加:

```python
def batch_chat(self, items: list[tuple[str, str]]) -> list["ChatResult"]:
    """顺序执行 chat(),单条抛错不阻塞其它(返 ChatResult 带 error)。"""
    out: list[ChatResult] = []
    from mmi.agent.router import IntentType
    for sid, msg in items:
        try:
            out.append(self.orchestrator.chat(sid, msg))
        except Exception as e:
            log.exception("batch_chat item failed: sid=%s", sid)
            out.append(ChatResult(
                reply="",
                intent=IntentType.UNKNOWN,
                agent_id="",
                validation=None,
                trace_ids=[],
                error=str(e),
            ))
    return out

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
```

取消 `test_batch_chat_isolates_exception` 的 skip。

- [ ] **Step 6.4: 跑测试,确认全部通过**

Run: `pytest tests/test_batch_chat.py -v`
Expected: 4 passed

- [ ] **Step 6.5: 跑全量 + ruff**

Run: `pytest tests/ -x --ignore=tests/test_cli.py -q`
Expected: 494(基线)+ 4 = 498 passed

Run: `ruff check mmi/ tests/`
Expected: 0 error

- [ ] **Step 6.6: Commit**

```bash
git add mmi/core/manager.py tests/test_batch_chat.py
git commit -m "feat(4.6): Manager batch_chat / batch_touch / batch_get_meta"
```

---

## R7 收口:文档 + 全量验证

- [ ] **Step 7.1: 写 R7 交接文档**

创建 `docs/handover-history/round_7_phase4_core.md`,按三期交接的格式写:本轮完成、文件清单、测试总结、关键设计决策、遗留问题、下轮预告。

- [ ] **Step 7.2: 更新索引**

修改 `docs/handover-history/INDEX.md`,加 `round_7` 行。

修改 `docs/INDEX.md`,四期 4.1/4.3/4.4/4.5/4.6 状态从 ⬜ 改为 ✅(4.2 标"Pipeline 容器 + 6 Step 落地,R8 收尾 4.7/4.8/4.9/4.10 期间可继续用 4.2")。

- [ ] **Step 7.3: 更新 ROUND_LOG**

把 `ROUND_LOG.md` 标题切到 "四期 架构加固(R7 核心)",填执行记录 + 测试结果。

- [ ] **Step 7.4: 最终验证**

Run: `pytest tests/ --ignore=tests/test_cli.py -q`
Expected: ≥ 484 passed(实际估 498,看 Task 6 收口时是否还有别的)

Run: `ruff check mmi/ tests/`
Expected: 0 error

- [ ] **Step 7.5: Commit**

```bash
git add docs/handover-history/round_7_phase4_core.md docs/handover-history/INDEX.md docs/INDEX.md ROUND_LOG.md
git commit -m "docs: R7 交接 + 四期 4.1/4.2/4.3/4.4/4.5/4.6 落地"
```

---

## Self-Review Checklist(写完后自检)

跑完上面 6 个 Task + 收口后,逐条确认:

- [ ] 4.3 LLM 重试 → Task 1 Step 1.6-1.8
- [ ] 4.5 ChatResult → Task 1 Step 1.1-1.5
- [ ] 4.1 EventBus → Task 2
- [ ] 4.2 Manager Pipeline → Task 3 + Task 4
- [ ] 4.4 LLM stream_chat → Task 5
- [ ] 4.6 Manager 批量 → Task 6
- [ ] spec § 10 "不在四期" 的项没有越界(每条 plan 任务都没去碰 heat / storage LRU / Skill 持久化 / Trace 持久化)
- [ ] `mmi/core/llm.py` 引用了 `mmi/agent/result.py` 和 `mmi/core/exceptions.py` — 都在 Task 1 同一个 commit 里
- [ ] 既有 27 个三期 net new 测试不退化
- [ ] 既有 466 baseline 不退化

---

## 风险点(实施时注意)

1. **`mmi/core/llm.py` 现状未读过** — Task 1 Step 1.8 第一次读它,确认 `class LLM` 签名,再 paste 代码
2. **`Orchestrator` 三期 `__init__` 签名可能不只 `llm` 一个参数** — Task 4 Step 4.3 第一次读既有,可能要把 `router/registry/validator/manager` 也保留为参数(向后兼容)
3. **`BaseAgent.__init__` 强制参数** — Task 3 Step 3.6 的 `_BoomAgent` 可能要传 `llm=MagicMock()` 才能构造
4. **既有 Orchestrator chat() 既有 5 步逻辑里可能直接 return string 给上层(CLI/TUI)用** — Task 4 改成 `ChatResult` 后,要让 `chat_legacy()` 真被 CLI/TUI 调到。看 `mmi/cli.py` 和 `mmi/tui/` 哪里调 `orch.chat()`(可能直接解包 `.reply`),决定是切到 `chat_legacy` 还是改用 `.reply`。
5. **既有 TraceRecord 调用 `latency_ms=0.0`** — Task 4 改造后,EventBus `step.end.duration_ms` 可让 Tracer 拿真时延。但 Tracer 改造不在本 plan,留到 R7 收口后单独 PR,或本期直接改(简短:在 Tracer 加 `subscribe("step.end", ...)` handler,从 payload 拿 duration_ms 写 TraceRecord)。

---

## 执行交接

本 plan 完成后(预计 6 个 commit + 1 收口 commit,共 7 个),R7 收口。

R8 plan(4.7 LRU + 4.8/4.9 Router + 4.10 ValidationResult)是独立 plan,等 R7 收口后另写。
