"""R9 9.2 — EventBus 节流:issues 数量超阈值时改 publish batch 事件。"""
from __future__ import annotations

from dataclasses import dataclass

from mmi.agent.event_bus import Event, EventBus
from mmi.agent.pipeline import PipelineCtx
from mmi.agent.router import IntentType
from mmi.agent.steps import ValidateStep
from mmi.agent.validate import ValidationIssue, ValidationResult


@dataclass
class _FakeValidator:
    """返回固定 N 个 issue,用于驱动 ValidateStep。"""

    n_issues: int

    def check(self, text: str, intent: IntentType) -> ValidationResult:
        issues = tuple(
            ValidationIssue(
                message=f"issue {i}",
                severity="error",
                rule_id=f"rule_{i}",
                span=(i, i + 1),
            )
            for i in range(self.n_issues)
        )
        return ValidationResult(passed=False, issues=issues)


def _make_ctx() -> PipelineCtx:
    return PipelineCtx(
        session_id="sid-1",
        user_message="hi",
        reply="some reply",
    )


def _count_events(bus: EventBus, name: str) -> list[int]:
    """通过订阅一个 dummy handler 计数,而不是 inspect internals。
    返回一个长度为 1 的 list,publish 后用 [0] 读取。"""
    count = [0]
    bus.subscribe(name, lambda _e: count.__setitem__(0, count[0] + 1))
    return count


def _last_event(bus: EventBus, name: str) -> Event:
    """Subscribe + 触发后拿到最后一条事件。"""
    holder: list[Event] = []
    bus.subscribe(name, lambda e: holder.append(e))
    return holder[-1] if holder else None  # type: ignore[return-value]


def test_issue_below_threshold_publishes_individually():
    """3 issues 全部单独 publish 'validation.issue'。"""
    bus = EventBus()
    individual_count = _count_events(bus, "validation.issue")
    step = ValidateStep(
        validator=_FakeValidator(n_issues=3),  # type: ignore[arg-type]
        event_bus=bus,
        issue_batch_threshold=5,
    )
    step.run(_make_ctx())
    assert individual_count[0] == 3
    # batch 事件不应被 publish
    batch_holder: list[Event] = []
    bus.subscribe("validation.issue_batch", lambda e: batch_holder.append(e))
    # 注:_count_events 已订阅过 individual,这里重订阅 batch
    assert len(batch_holder) == 0


def test_issue_above_threshold_publishes_batch():
    """6 issues 超阈值(默认 5),改 publish 单条 'validation.issue_batch'。"""
    bus = EventBus()
    individual_holder: list[Event] = []
    bus.subscribe("validation.issue", lambda e: individual_holder.append(e))
    batch_holder: list[Event] = []
    bus.subscribe("validation.issue_batch", lambda e: batch_holder.append(e))

    step = ValidateStep(
        validator=_FakeValidator(n_issues=6),  # type: ignore[arg-type]
        event_bus=bus,
        issue_batch_threshold=5,
    )
    step.run(_make_ctx())

    assert len(individual_holder) == 0  # 不再单发
    assert len(batch_holder) == 1
    payload = batch_holder[0].payload
    assert payload["session_id"] == "sid-1"
    assert payload["count"] == 6
    assert len(payload["issues"]) == 6
    assert payload["issues"][0]["rule_id"] == "rule_0"


def test_issue_exactly_at_threshold_publishes_individually():
    """边界:issues 数 == 阈值,走单发(> 阈值才转 batch)。"""
    bus = EventBus()
    individual_count = _count_events(bus, "validation.issue")
    step = ValidateStep(
        validator=_FakeValidator(n_issues=5),  # type: ignore[arg-type]
        event_bus=bus,
        issue_batch_threshold=5,
    )
    step.run(_make_ctx())
    assert individual_count[0] == 5


def test_issue_batch_threshold_configurable():
    """阈值改成 2,3 issues 走 batch。"""
    bus = EventBus()
    batch_holder: list[Event] = []
    bus.subscribe("validation.issue_batch", lambda e: batch_holder.append(e))
    step = ValidateStep(
        validator=_FakeValidator(n_issues=3),  # type: ignore[arg-type]
        event_bus=bus,
        issue_batch_threshold=2,
    )
    step.run(_make_ctx())
    assert len(batch_holder) == 1
    assert batch_holder[0].payload["count"] == 3


def test_force_individual_always_publishes_singly():
    """force_individual=True 时无论数量都走单发。"""
    bus = EventBus()
    individual_count = _count_events(bus, "validation.issue")
    step = ValidateStep(
        validator=_FakeValidator(n_issues=10),  # type: ignore[arg-type]
        event_bus=bus,
        issue_batch_threshold=5,
        force_individual=True,
    )
    step.run(_make_ctx())
    assert individual_count[0] == 10


def test_complete_event_unchanged():
    """'validation.complete' 行为不变,无论 issue 数量。"""
    bus = EventBus()
    complete_holder: list[Event] = []
    bus.subscribe("validation.complete", lambda e: complete_holder.append(e))
    step = ValidateStep(
        validator=_FakeValidator(n_issues=6),  # type: ignore[arg-type]
        event_bus=bus,
        issue_batch_threshold=5,
    )
    step.run(_make_ctx())
    assert len(complete_holder) == 1
    assert complete_holder[0].payload["issue_count"] == 6
    assert complete_holder[0].payload["passed"] is False


def test_no_event_bus_still_works():
    """event_bus=None 时不抛。"""
    step = ValidateStep(
        validator=_FakeValidator(n_issues=3),  # type: ignore[arg-type]
        event_bus=None,
        issue_batch_threshold=5,
    )
    ctx = step.run(_make_ctx())
    assert ctx.validation is not None
    assert len(ctx.validation.issues) == 3
