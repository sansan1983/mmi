"""EventBus 行为测试。"""
from __future__ import annotations

import dataclasses

import pytest

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

    def h(e: Event) -> None:
        received.append(e)

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
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.name = "y"  # type: ignore[misc]
