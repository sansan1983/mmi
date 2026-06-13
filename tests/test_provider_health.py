"""tests/test_provider_health.py —— P3-3 Provider 健康检测测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.provider_health import (
    ProviderHealthConfig,
    ProviderHealthMonitor,
    ProviderState,
)


def _monitor(**kw) -> ProviderHealthMonitor:
    ProviderHealthMonitor.reset_instance()
    return ProviderHealthMonitor(**kw)


# ---------------------------------------------------------------------------
# report_success / report_failure
# ---------------------------------------------------------------------------

def test_initial_state_is_unknown():
    m = _monitor()
    assert m.get_state("openai") == ProviderState.UNKNOWN


def test_success_marks_healthy():
    m = _monitor()
    m.report_success("openai")
    assert m.get_state("openai") == ProviderState.HEALTHY


def test_single_failure_stays_healthy():
    m = _monitor()
    m.report_success("openai")
    m.report_failure("openai")
    assert m.get_state("openai") == ProviderState.HEALTHY


def test_consecutive_failures_mark_degraded():
    m = _monitor(config=ProviderHealthConfig(failure_threshold=3))
    m.report_success("openai")
    m.report_failure("openai")
    m.report_failure("openai")
    assert m.get_state("openai") == ProviderState.HEALTHY
    m.report_failure("openai")
    assert m.get_state("openai") == ProviderState.DEGRADED


def test_success_resets_consecutive_failures():
    m = _monitor(config=ProviderHealthConfig(failure_threshold=3))
    m.report_success("openai")
    m.report_failure("openai")
    m.report_failure("openai")
    m.report_success("openai")  # reset
    m.report_failure("openai")  # consecutive=1, still healthy
    assert m.get_state("openai") == ProviderState.HEALTHY


def test_degraded_recovers_on_success():
    m = _monitor(config=ProviderHealthConfig(failure_threshold=2))
    m.report_failure("openai")
    m.report_failure("openai")
    assert m.get_state("openai") == ProviderState.DEGRADED
    m.report_success("openai")
    assert m.get_state("openai") == ProviderState.HEALTHY


# ---------------------------------------------------------------------------
# get_healthy_provider
# ---------------------------------------------------------------------------

def test_prefers_healthy_over_unknown():
    m = _monitor()
    m.report_success("openai")
    # anthropic never tried
    assert m.get_healthy_provider(["anthropic", "openai"]) == "openai"


def test_unknown_over_degraded():
    m = _monitor(config=ProviderHealthConfig(failure_threshold=2))
    m.report_failure("openai")
    m.report_failure("openai")
    # openai degraded, anthropic unknown
    assert m.get_healthy_provider(["openai", "anthropic"]) == "anthropic"


def test_all_degraded_picks_least_bad():
    m = _monitor(config=ProviderHealthConfig(failure_threshold=2))
    m.report_failure("openai")
    m.report_failure("openai")
    m.report_failure("openai")  # 3 consecutive
    m.report_failure("anthropic")
    m.report_failure("anthropic")  # 2 consecutive
    # anthropic has fewer failures
    assert m.get_healthy_provider(["openai", "anthropic"]) == "anthropic"


def test_empty_candidates_returns_none():
    m = _monitor()
    assert m.get_healthy_provider([]) is None


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

def test_reset_specific_provider():
    m = _monitor()
    m.report_success("openai")
    m.report_success("anthropic")
    m.reset("openai")
    assert m.get_state("openai") == ProviderState.UNKNOWN
    assert m.get_state("anthropic") == ProviderState.HEALTHY


def test_reset_all():
    m = _monitor()
    m.report_success("openai")
    m.report_success("anthropic")
    m.reset()
    assert m.get_state("openai") == ProviderState.UNKNOWN
    assert m.get_state("anthropic") == ProviderState.UNKNOWN


# ---------------------------------------------------------------------------
# get_all_states
# ---------------------------------------------------------------------------

def test_get_all_states():
    m = _monitor()
    m.report_success("openai")
    m.report_failure("anthropic")
    states = m.get_all_states()
    assert states["openai"] == ProviderState.HEALTHY
    assert states["anthropic"] == ProviderState.UNKNOWN  # only 1 failure


# ---------------------------------------------------------------------------
# Concurrent access
# ---------------------------------------------------------------------------

def test_concurrent_reports():
    import threading

    m = _monitor(config=ProviderHealthConfig(failure_threshold=100))
    errors: list[Exception] = []

    def report(idx: int):
        try:
            if idx % 2 == 0:
                m.report_success("openai")
            else:
                m.report_failure("openai")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=report, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
