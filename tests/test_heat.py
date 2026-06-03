"""tests/test_heat.py —— core.heat 单元测试。

覆盖（ARCHITECTURE.md §8.4）：
  - recency_bonus 阶梯（1/7/30 天）
  - age_penalty 线性（每 30 天 -1）
  - compute_heat 公式正确
  - derive_state 阈值（active/warm/cold）
  - cold_since 写入/清空时序
  - zombie 触发（cold 持续 > 90 天）
  - apply_heat_and_state 原地更新 SessionMeta
  - sort_by_heat 排序
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.heat import (  # noqa: E402
    HEAT_ACTIVE_THRESHOLD,
    HEAT_WARM_THRESHOLD,
    ZOMBIE_DAYS,
    HeatConfig,
    age_penalty,
    apply_heat_and_state,
    compute_heat,
    derive_state,
    recency_bonus,
    sort_by_heat,
)
from mmi.core.session import Session, SessionMeta, new_session_id  # noqa: E402


# ---------------------------------------------------------------------------
# 时间工具
# ---------------------------------------------------------------------------


def _ago(days: float, **kw) -> datetime:
    """N 天前的 UTC datetime。"""
    return datetime.now(timezone.utc) - timedelta(days=days, **kw)


def _at_iso(dt: datetime) -> str:
    """datetime → ISO 字符串（与 session.utcnow_iso 同格式）。"""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ---------------------------------------------------------------------------
# recency_bonus
# ---------------------------------------------------------------------------


class TestRecencyBonus:
    def test_within_1_day(self):
        now = datetime.now(timezone.utc)
        assert recency_bonus(now, now=now) == 10.0

    def test_within_7_days(self):
        now = datetime.now(timezone.utc)
        assert recency_bonus(now - timedelta(days=3), now=now) == 5.0

    def test_within_30_days(self):
        now = datetime.now(timezone.utc)
        assert recency_bonus(now - timedelta(days=15), now=now) == 1.0

    def test_beyond_30_days(self):
        now = datetime.now(timezone.utc)
        assert recency_bonus(now - timedelta(days=60), now=now) == 0.0

    def test_clock_skew_negative_delta_clamped(self):
        """last_access 在未来（时钟回拨）→ 当作 0。"""
        now = datetime.now(timezone.utc)
        future = now + timedelta(hours=1)
        assert recency_bonus(future, now=now) == 10.0

    def test_naive_datetime_treated_as_utc(self):
        now = datetime.now(timezone.utc)
        naive = (now - timedelta(days=2)).replace(tzinfo=None)
        assert recency_bonus(naive, now=now) == 5.0

    def test_none_returns_zero(self):
        assert recency_bonus(None) == 0.0


# ---------------------------------------------------------------------------
# age_penalty
# ---------------------------------------------------------------------------


class TestAgePenalty:
    def test_30_days(self):
        now = datetime.now(timezone.utc)
        assert age_penalty(now - timedelta(days=30), now=now) == pytest.approx(1.0)

    def test_60_days(self):
        now = datetime.now(timezone.utc)
        assert age_penalty(now - timedelta(days=60), now=now) == pytest.approx(2.0)

    def test_zero_days(self):
        now = datetime.now(timezone.utc)
        assert age_penalty(now, now=now) == 0.0

    def test_negative_delta_treated_as_zero(self):
        now = datetime.now(timezone.utc)
        # created_at 在未来（极端情况）
        assert age_penalty(now + timedelta(days=10), now=now) == 0.0

    def test_none_returns_zero(self):
        assert age_penalty(None) == 0.0


# ---------------------------------------------------------------------------
# compute_heat
# ---------------------------------------------------------------------------


class TestComputeHeat:
    def test_fresh_active_session(self):
        """刚创建、access=1、当天访问 → heat ≈ 1 + 10 - 0 = 11 → active。"""
        now = datetime.now(timezone.utc)
        h = compute_heat(
            access_count=1,
            last_access=now,
            created_at=now,
            now=now,
        )
        assert h == pytest.approx(11.0)

    def test_aged_but_recently_used(self):
        """60 天前创建、今天访问、access=1 → 1 + 10 - 2 = 9 → warm。"""
        now = datetime.now(timezone.utc)
        h = compute_heat(
            access_count=1,
            last_access=now,
            created_at=now - timedelta(days=60),
            now=now,
        )
        assert h == pytest.approx(9.0)

    def test_frequently_accessed(self):
        """access=20、今天访问、新建 → 20 + 10 = 30 → active。"""
        now = datetime.now(timezone.utc)
        h = compute_heat(
            access_count=20,
            last_access=now,
            created_at=now,
            now=now,
        )
        assert h == pytest.approx(30.0)

    def test_ancient_session_with_no_recent_access(self):
        """200 天前创建、access=1、60 天前最后访问 → 1 + 0 - 6.67 ≈ -5.67。"""
        now = datetime.now(timezone.utc)
        h = compute_heat(
            access_count=1,
            last_access=now - timedelta(days=60),
            created_at=now - timedelta(days=200),
            now=now,
        )
        # 1 + 0 - 200/30 = 1 - 6.667 = -5.667
        assert h < 0
        assert h == pytest.approx(-5.667, rel=1e-3)


# ---------------------------------------------------------------------------
# derive_state
# ---------------------------------------------------------------------------


class TestDeriveState:
    def test_high_heat_is_active(self):
        state, cs = derive_state(HEAT_ACTIVE_THRESHOLD, prev_state="warm", cold_since=None)
        assert state == "active"
        assert cs is None

    def test_warm_heat_is_warm(self):
        state, cs = derive_state(HEAT_WARM_THRESHOLD, prev_state="active", cold_since=None)
        assert state == "warm"
        assert cs is None

    def test_low_heat_is_cold(self):
        state, cs = derive_state(0.0, prev_state="warm", cold_since=None)
        assert state == "cold"
        assert cs is not None

    def test_negative_heat_is_cold(self):
        state, cs = derive_state(-1.0, prev_state="warm", cold_since=None)
        assert state == "cold"
        assert cs is not None

    def test_cold_to_active_clears_cold_since(self):
        """heat 回升：cold_since 应当清空。"""
        now = datetime.now(timezone.utc)
        old_cold_since = now - timedelta(days=10)
        state, cs = derive_state(15.0, prev_state="cold", cold_since=old_cold_since, now=now)
        assert state == "active"
        assert cs is None

    def test_cold_to_warm_clears_cold_since(self):
        now = datetime.now(timezone.utc)
        old_cold_since = now - timedelta(days=10)
        state, cs = derive_state(7.0, prev_state="cold", cold_since=old_cold_since, now=now)
        assert state == "warm"
        assert cs is None

    def test_cold_preserves_cold_since(self):
        """已经在 cold：cold_since 不变（避免被每次重算覆盖）。"""
        now = datetime.now(timezone.utc)
        old_cold_since = now - timedelta(days=20)
        state, cs = derive_state(1.0, prev_state="cold", cold_since=old_cold_since, now=now)
        assert state == "cold"
        assert cs == old_cold_since

    def test_zombie_when_cold_too_long(self):
        now = datetime.now(timezone.utc)
        old_cold_since = now - timedelta(days=ZOMBIE_DAYS + 5)
        state, cs = derive_state(1.0, prev_state="cold", cold_since=old_cold_since, now=now)
        assert state == "zombie"
        assert cs == old_cold_since  # 保留 cold_since 便于追溯

    def test_zombie_persists_when_heat_still_low(self):
        """prev_state=zombie 且新算出的 heat 仍 < warm_threshold → 保持 zombie。"""
        now = datetime.now(timezone.utc)
        state, cs = derive_state(2.0, prev_state="zombie", cold_since=now - timedelta(days=100), now=now)
        assert state == "zombie"

    def test_zombie_recovers_when_heat_high(self):
        """prev_state=zombie 但 heat 回到 active 区间 → 离开 zombie。"""
        now = datetime.now(timezone.utc)
        state, cs = derive_state(15.0, prev_state="zombie", cold_since=now - timedelta(days=100), now=now)
        assert state == "active"
        assert cs is None

    def test_active_to_cold_sets_cold_since_to_now(self):
        now = datetime.now(timezone.utc)
        state, cs = derive_state(0.0, prev_state="active", cold_since=None, now=now)
        assert state == "cold"
        assert cs == now


# ---------------------------------------------------------------------------
# apply_heat_and_state
# ---------------------------------------------------------------------------


class TestApplyHeatAndState:
    def test_updates_heat_and_state(self):
        meta = SessionMeta.new(new_session_id(), title="t")
        # 新建默认 heat=1.0, state=active
        assert meta.heat == 1.0
        assert meta.state == "active"
        assert meta.cold_since == ""

        apply_heat_and_state(meta)
        # 1 次访问 + 刚刚 + 今天创建 → heat ≈ 1 + 10 - 0 = 11
        assert meta.heat == pytest.approx(11.0, rel=1e-3)
        assert meta.state == "active"
        assert meta.cold_since == ""

    def test_aged_session_becomes_warm(self):
        """60 天前创建、今天访问、access=1 → heat=9 → warm。"""
        meta = SessionMeta.new(new_session_id(), title="t")
        meta.created_at = _at_iso(_ago(60))
        meta.last_access = _at_iso(_ago(0))
        meta.access_count = 1
        meta.heat = 0.0

        apply_heat_and_state(meta)
        assert meta.state == "warm"
        assert meta.heat == pytest.approx(9.0, rel=1e-3)

    def test_very_old_session_becomes_cold(self):
        """200 天前创建、60 天前最后访问、access=1 → heat<0 → cold + cold_since 写入。"""
        meta = SessionMeta.new(new_session_id(), title="t")
        meta.created_at = _at_iso(_ago(200))
        meta.last_access = _at_iso(_ago(60))
        meta.access_count = 1
        meta.heat = 0.0

        apply_heat_and_state(meta)
        assert meta.state == "cold"
        assert meta.heat < 0
        assert meta.cold_since != ""

    def test_cold_since_preserved_on_repeated_apply(self):
        """连续两次 apply 在 cold 区间 → cold_since 不被覆盖。"""
        meta = SessionMeta.new(new_session_id(), title="t")
        meta.created_at = _at_iso(_ago(200))
        meta.last_access = _at_iso(_ago(60))
        meta.access_count = 1

        apply_heat_and_state(meta)
        first_cs = meta.cold_since
        assert first_cs

        apply_heat_and_state(meta)
        assert meta.cold_since == first_cs

    def test_cold_to_active_clears_cold_since(self):
        meta = SessionMeta.new(new_session_id(), title="t")
        meta.created_at = _at_iso(_ago(200))
        meta.last_access = _at_iso(_ago(60))
        meta.access_count = 1

        apply_heat_and_state(meta)
        assert meta.state == "cold"
        assert meta.cold_since

        # 用户回来 chat 几次 → access_count 涨、last_access 更新
        # 200 天老会话：需要 access=10+ 才能让 heat 突破 active_threshold
        meta.access_count = 20
        meta.last_access = _at_iso(_ago(0))
        apply_heat_and_state(meta)
        assert meta.state == "active"
        assert meta.cold_since == ""


# ---------------------------------------------------------------------------
# sort_by_heat
# ---------------------------------------------------------------------------


class TestSortByHeat:
    def test_sort_descending(self):
        m1 = SessionMeta.new(new_session_id(), title="a"); m1.heat = 1.0
        m2 = SessionMeta.new(new_session_id(), title="b"); m2.heat = 5.0
        m3 = SessionMeta.new(new_session_id(), title="c"); m3.heat = 3.0
        result = sort_by_heat([m1, m2, m3])
        assert [m.title for m in result] == ["b", "c", "a"]

    def test_sort_ascending(self):
        m1 = SessionMeta.new(new_session_id(), title="a"); m1.heat = 1.0
        m2 = SessionMeta.new(new_session_id(), title="b"); m2.heat = 5.0
        result = sort_by_heat([m1, m2], descending=False)
        assert [m.title for m in result] == ["a", "b"]

    def test_tie_breaker_uses_last_access(self):
        m1 = SessionMeta.new(new_session_id(), title="older")
        m1.heat = 5.0
        m1.last_access = _at_iso(_ago(10))
        m2 = SessionMeta.new(new_session_id(), title="newer")
        m2.heat = 5.0
        m2.last_access = _at_iso(_ago(1))
        result = sort_by_heat([m1, m2])
        assert result[0].title == "newer"

    def test_empty(self):
        assert sort_by_heat([]) == []


# ---------------------------------------------------------------------------
# HeatConfig
# ---------------------------------------------------------------------------


class TestHeatConfig:
    def test_default_matches_arch(self):
        cfg = HeatConfig()
        assert cfg.active_threshold == HEAT_ACTIVE_THRESHOLD
        assert cfg.warm_threshold == HEAT_WARM_THRESHOLD
        assert cfg.zombie_days == ZOMBIE_DAYS

    def test_custom_threshold(self):
        cfg = HeatConfig(active_threshold=20.0, warm_threshold=2.0)
        # heat=15 在默认下是 active，在自定义下是 warm
        state, _ = derive_state(15.0, prev_state="active", cold_since=None, config=cfg)
        assert state == "warm"


# ---------------------------------------------------------------------------
# 端到端：Session 落盘 + 重读
# ---------------------------------------------------------------------------


class TestRoundtrip:
    def test_cold_since_persists_in_frontmatter(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MMI_HOME", str(tmp_path))
        from mmi.core import paths
        paths.ensure_dirs()

        meta = SessionMeta.new(new_session_id(), title="persist-test")
        meta.created_at = _at_iso(_ago(200))
        meta.last_access = _at_iso(_ago(60))
        meta.access_count = 1
        apply_heat_and_state(meta)
        assert meta.state == "cold"

        # 落盘
        s = Session(meta=meta, body="")
        from mmi.core import storage
        storage.write_session(s)

        # 重读
        s2 = storage.read_session(meta.session_id)
        assert s2.meta.state == "cold"
        assert s2.meta.cold_since != ""
        assert s2.meta.heat < 0
