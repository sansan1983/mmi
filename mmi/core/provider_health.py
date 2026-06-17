"""Provider health monitoring and automatic failover.

P3-3: Tracks per-provider failure counts, marks providers as degraded,
and automatically switches to a healthy fallback when needed.

Design:
  - ``ProviderHealthMonitor`` is a singleton that tracks per-provider health.
  - On ``report_failure(provider_name)``, increment failure count.
  - If consecutive failures >= threshold, mark provider as ``degraded``.
  - On ``report_success(provider_name)``, reset failure count and mark healthy.
  - ``get_healthy_provider()`` returns the best available provider.
  - Events: ``provider.degraded`` / ``provider.healthy`` via EventBus (optional).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from mmi.agent.event_bus import EventBus


class ProviderState(Enum):
    """Health state of a provider."""

    HEALTHY = auto()
    DEGRADED = auto()
    UNKNOWN = auto()


@dataclass
class _ProviderHealth:
    """Internal health tracking for a single provider."""

    name: str
    state: ProviderState = ProviderState.UNKNOWN
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0


@dataclass
class ProviderHealthConfig:
    """Configuration for health monitoring."""

    failure_threshold: int = 3
    """Consecutive failures before marking a provider as degraded."""

    recovery_threshold: int = 1
    """Consecutive successes needed to recover from degraded state."""

    ping_timeout_s: float = 5.0
    """Timeout for health-check ping requests."""


class ProviderHealthMonitor:
    """Singleton health monitor for LLM providers.

    Usage::

        from mmi.core.provider_health import ProviderHealthMonitor

        monitor = ProviderHealthMonitor.get_instance()

        # After a failed LLM call:
        monitor.report_failure("openai")

        # After a successful LLM call:
        monitor.report_success("openai")

        # Check state:
        state = monitor.get_state("openai")

        # Get a healthy provider from a list:
        provider = monitor.get_healthy_provider(["openai", "anthropic", "qwen"])
    """

    _instance: ClassVar[ProviderHealthMonitor | None] = None

    def __init__(
        self,
        *,
        config: ProviderHealthConfig | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._providers: dict[str, _ProviderHealth] = {}
        self._config = config or ProviderHealthConfig()
        self._lock = threading.RLock()
        self._bus = event_bus

    @classmethod
    def get_instance(cls: type[ProviderHealthMonitor]) -> ProviderHealthMonitor:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls: type[ProviderHealthMonitor]) -> None:
        """For testing only."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create(self, name: str) -> _ProviderHealth:
        if name not in self._providers:
            self._providers[name] = _ProviderHealth(name=name)
        return self._providers[name]

    def _emit_event(self, event_name: str, provider_name: str) -> None:
        if self._bus is None:
            return
        import time as _time

        from mmi.agent.event_bus import Event
        self._bus.publish(Event(
            name=event_name,
            timestamp=_time.time(),
            payload={"provider": provider_name},
        ))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def report_success(self, provider_name: str) -> None:
        """Report a successful call to *provider_name*.

        If the provider was degraded and has now met the recovery threshold,
        mark it as healthy again and emit ``provider.healthy``.
        """
        import time as _time

        with self._lock:
            ph = self._get_or_create(provider_name)
            ph.total_successes += 1
            ph.last_success_time = _time.monotonic()
            ph.consecutive_failures = 0

            if ph.state == ProviderState.DEGRADED:
                # Simple recovery: one success is enough by default
                ph.state = ProviderState.HEALTHY
                self._emit_event("provider.healthy", provider_name)
            elif ph.state == ProviderState.UNKNOWN:
                ph.state = ProviderState.HEALTHY

    def report_failure(self, provider_name: str) -> None:
        """Report a failed call to *provider_name*.

        If consecutive failures reach the threshold, mark the provider as
        degraded and emit ``provider.degraded``.
        """
        import time as _time

        with self._lock:
            ph = self._get_or_create(provider_name)
            ph.consecutive_failures += 1
            ph.total_failures += 1
            ph.last_failure_time = _time.monotonic()

            if (ph.state != ProviderState.DEGRADED
                    and ph.consecutive_failures >= self._config.failure_threshold):
                ph.state = ProviderState.DEGRADED
                self._emit_event("provider.degraded", provider_name)

    def get_state(self, provider_name: str) -> ProviderState:
        """Return the current health state of *provider_name*."""
        with self._lock:
            ph = self._providers.get(provider_name)
            return ph.state if ph else ProviderState.UNKNOWN

    def get_healthy_provider(self, candidates: list[str]) -> str | None:
        """Return the first healthy provider from *candidates*.

        Falls back to the first non-degraded candidate. If all are degraded,
        returns the one with the fewest consecutive failures.

        Returns None if *candidates* is empty.
        """
        with self._lock:
            if not candidates:
                return None

            # Prefer healthy providers
            for name in candidates:
                ph = self._providers.get(name)
                if ph and ph.state == ProviderState.HEALTHY:
                    return name

            # Then unknown (never tried)
            for name in candidates:
                ph = self._providers.get(name)
                if ph is None or ph.state == ProviderState.UNKNOWN:
                    return name

            # All degraded — pick the least bad one
            best = min(
                candidates,
                key=lambda n: self._providers[n].consecutive_failures
                if n in self._providers else 0,
            )
            return best

    def get_all_states(self) -> dict[str, ProviderState]:
        """Return a snapshot of all provider states."""
        with self._lock:
            return {name: ph.state for name, ph in self._providers.items()}

    def reset(self, provider_name: str | None = None) -> None:
        """Reset health state. If *provider_name* is None, reset all."""
        with self._lock:
            if provider_name is None:
                self._providers.clear()
            else:
                self._providers.pop(provider_name, None)
