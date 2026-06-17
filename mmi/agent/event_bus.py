"""轻量级 EventBus,同步派发,handler 异常隔离。"""
from __future__ import annotations

import contextlib
import dataclasses
import logging
from collections import defaultdict
from collections.abc import Callable

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
            with contextlib.suppress(ValueError):
                self._subs[event_name].remove(handler)

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
