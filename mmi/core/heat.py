"""mmi.core.heat —— 热度计算与状态机。

ARCHITECTURE.md §8.4：
    heat = access_count * 1.0
         + recency_bonus(last_access)   # 1 天内 +10, 7 天 +5, 30 天 +1
         - age_penalty(created_at)       # 每 30 天 -1

    heat >= 10             → active
    5 <= heat < 10         → warm
    0 <= heat < 5          → cold
    heat < 0 或 cold 持续 90 天 → zombie

设计要点：
  - 纯函数式：所有计算都不读盘、不调 LLM、不做 IO
  - 输入是 SessionMeta + now（datetime），返回新的元数据字段（避免 in-place 修改方便测）
  - cold 持续时间的追踪：用 frontmatter 里新增的 `cold_since` 字段（ISO 字符串）
    - state 从 active/warm 降为 cold 时写入当前时间
    - 已经是 cold 时保留原 cold_since
    - 从 cold 升回 active/warm 时清空 cold_since
    - cold 持续天数 > zombie_threshold_days → 标记 state="zombie"
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .session import SessionState

__all__ = [
    "recency_bonus",
    "age_penalty",
    "compute_heat",
    "derive_state",
    "apply_heat_and_state",
    "HeatConfig",
    "HEAT_ACTIVE_THRESHOLD",
    "HEAT_WARM_THRESHOLD",
    "ZOMBIE_DAYS",
]


# ---------------------------------------------------------------------------
# 常量（与 ARCHITECTURE.md §8.4 对齐）
# ---------------------------------------------------------------------------

# 状态阈值
HEAT_ACTIVE_THRESHOLD: float = 10.0
HEAT_WARM_THRESHOLD: float = 5.0

# zombie 触发：cold 持续超过 N 天
ZOMBIE_DAYS: int = 90

# 公式权重
ACCESS_WEIGHT: float = 1.0

# recency_bonus 阶梯（days_since_last_access → bonus）
# 设计：1 天内 10, 7 天 5, 30 天 1；越久越接近 0
_RECENCY_TIERS: tuple[tuple[float, float], ...] = (
    (1.0, 10.0),    # ≤1 天 → +10
    (7.0, 5.0),     # ≤7 天 → +5
    (30.0, 1.0),    # ≤30 天 → +1
    # 超过 30 天 → 0
)

# age_penalty：每 30 天 -1（线性）
_AGE_PENALTY_PER_DAYS: float = 30.0
_AGE_PENALTY_PER_UNIT: float = 1.0


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HeatConfig:
    """热量计算的阈值（可调，便于未来 A/B）。

    默认值与 ARCHITECTURE.md §8.4 一致。
    """

    active_threshold: float = HEAT_ACTIVE_THRESHOLD
    warm_threshold: float = HEAT_WARM_THRESHOLD
    zombie_days: int = ZOMBIE_DAYS


# ---------------------------------------------------------------------------
# 公式组件
# ---------------------------------------------------------------------------


def recency_bonus(last_access: datetime, *, now: datetime | None = None) -> float:
    """最近访问带来的热度加成。

    阶梯（ARCHITECTURE.md §8.4）：
        ≤ 1 天  → +10
        ≤ 7 天  → +5
        ≤ 30 天 → +1
        > 30 天 → 0
    """
    if last_access is None:
        return 0.0
    if now is None:
        now = datetime.now(timezone.utc)
    # 统一到带 tz 的 aware datetime
    if last_access.tzinfo is None:
        last_access = last_access.replace(tzinfo=timezone.utc)
    delta_days = (now - last_access).total_seconds() / 86400.0
    if delta_days < 0:
        # 时钟回拨：当作刚刚访问
        delta_days = 0.0
    for max_days, bonus in _RECENCY_TIERS:
        if delta_days <= max_days:
            return bonus
    return 0.0


def age_penalty(created_at: datetime, *, now: datetime | None = None) -> float:
    """会话年龄带来的热度惩罚。

    每 30 天 -1（线性）。created_at 缺失或晚于 now（极端情况）→ 0。
    """
    if created_at is None:
        return 0.0
    if now is None:
        now = datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta_days = (now - created_at).total_seconds() / 86400.0
    if delta_days <= 0:
        return 0.0
    return (delta_days / _AGE_PENALTY_PER_DAYS) * _AGE_PENALTY_PER_UNIT


def compute_heat(
    *,
    access_count: int,
    last_access: datetime,
    created_at: datetime,
    now: datetime | None = None,
    total_turns: int = 0,
) -> float:
    """算 heat(ARCHITECTURE.md §8.4 公式)。

    P2-9 简化版增强:
      raw = access_count * 1.0 + recency_bonus - age_penalty
      heat = raw + content_bonus
    其中 content_bonus = min(2.0, total_turns / 25)
    (50 轮以上封顶 +2 额外加分,短会话不加)

    不用乘法(content_weight)的原因:那样 0 turn → heat 0,会扰乱 state 推导。
    用加法:基础 heat 不变,长对话额外 +0~2。

    不做关键词规则(避免启发式 + 词典维护成本),纯按 turn 数衡量"内容重要度"。

    heat 可以是负数(很久没访问 + 很老的会话)
    """
    if now is None:
        now = datetime.now(timezone.utc)
    bonus = recency_bonus(last_access, now=now)
    penalty = age_penalty(created_at, now=now)
    raw = access_count * ACCESS_WEIGHT + bonus - penalty
    # P2-9:内容加成(短会话不加,长对话 50 轮以上封顶 +2)
    content_bonus = min(2.0, max(0.0, total_turns) / 25.0)
    return raw + content_bonus


# ---------------------------------------------------------------------------
# 状态推导
# ---------------------------------------------------------------------------


def derive_state(
    heat: float,
    *,
    prev_state: str,
    cold_since: datetime | None,
    now: datetime | None = None,
    config: HeatConfig | None = None,
) -> tuple[SessionState, datetime | None]:
    """从 heat + 上一态 + cold_since 推导新 state 与 cold_since。

    规则（ARCHITECTURE.md §8.4）：
        heat >= active_threshold       → active（清空 cold_since）
        warm_threshold ≤ heat < active → warm（清空 cold_since）
        0 ≤ heat < warm_threshold      → cold（首次进入时设置 cold_since=now）
        heat < 0                       → cold（首次进入时设置 cold_since=now）
        cold 持续 > zombie_days        → zombie（保留 cold_since 以便追溯）

    Args:
        heat: compute_heat() 算出的当前热度
        prev_state: 上一状态
        cold_since: 上一态记录"何时进入 cold"的时间，None 表示未在 cold
        now: 当前时间（测试时注入）
        config: 阈值配置

    Returns:
        (new_state, new_cold_since) —— cold_since 在离开 cold 时返回 None
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if config is None:
        config = HeatConfig()

    new_state: str
    new_cold_since: datetime | None

    if heat >= config.active_threshold:
        new_state = "active"
        new_cold_since = None
    elif heat >= config.warm_threshold:
        new_state = "warm"
        new_cold_since = None
    else:
        # 0 ≤ heat < warm_threshold 或 heat < 0 → cold
        new_state = "cold"
        # 保留 cold_since；仅在首次进入 cold 时写入
        # prev_state 是 "cold" 或 "zombie" 都算"已经在 cold 区间" → 保留原 cold_since
        if prev_state in ("cold", "zombie") and cold_since is not None:
            new_cold_since = cold_since
        else:
            new_cold_since = now

    # zombie 单独判：cold 持续 > zombie_days
    # 关键：cold_since 应当是"实际进入 cold 的时间"，可能是上一次的 cold_since
    # （prev_state in ["cold", "zombie"]）或本次新写的 now。
    # 用 new_cold_since（已正确填充）来算 cold 持续时间。
    if new_state == "cold" and new_cold_since is not None:
        if new_cold_since.tzinfo is None:
            cs_aware = new_cold_since.replace(tzinfo=timezone.utc)
        else:
            cs_aware = new_cold_since
        days_in_cold = (now - cs_aware).total_seconds() / 86400.0
        if days_in_cold > config.zombie_days:
            new_state = "zombie"

    # zombie 不会自愈：需要外部干预（gc 删掉 / 用户再 chat 一次让 heat 上去）
    # 注意：如果 prev_state 已经是 zombie 但本次 heat 仍 < warm_threshold，
    # 上面 zombie 判定已经把它标回 zombie 了。
    # 只有 heat 恢复到 active/warm 时才脱离 zombie。
    if str(prev_state) == SessionState.ZOMBIE and new_state not in ("zombie", "active", "warm"):
        # 兜底：保持 zombie
        return "zombie", cold_since
    if str(prev_state) == SessionState.ZOMBIE and new_state in ("active", "warm"):
        return new_state, None

    return new_state, new_cold_since


# ---------------------------------------------------------------------------
# 一站式：apply_heat_and_state
# ---------------------------------------------------------------------------


def apply_heat_and_state(
    meta,  # SessionMeta(避免在 heat.py 里强 import session.py 形成循环)
    *,
    now: datetime | None = None,
    config: HeatConfig | None = None,
    total_turns: int = 0,
) -> None:
    """原地更新 meta 的 heat / state / cold_since（写 frontmatter 时一起带出去）。

    Args:
        meta: SessionMeta 实例（in-place 修改）
        now: 当前时间（测试时注入）
        config: 阈值配置

    Side effects:
        - meta.heat = 新 heat
        - meta.state = 新 state
        - meta.cold_since = 新 cold_since（新增字段，frontmatter 多一行）
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if config is None:
        config = HeatConfig()

    # 解析时间
    last_access = _parse_iso_utc(meta.last_access)
    created_at = _parse_iso_utc(meta.created_at)
    cold_since = _parse_iso_utc(meta.cold_since) if hasattr(meta, "cold_since") else None

    # 算 heat(P2-9:total_turns 给 content_weight,默认 0 = 短会话等效旧公式)
    new_heat = compute_heat(
        access_count=meta.access_count,
        last_access=last_access if last_access is not None else now,
        created_at=created_at if created_at is not None else now,
        now=now,
        total_turns=total_turns,
    )

    # 算 state
    prev_state = meta.state
    new_state, new_cold_since = derive_state(
        new_heat,
        prev_state=prev_state,
        cold_since=cold_since,
        now=now,
        config=config,
    )

    # 写回
    meta.heat = round(new_heat, 4)  # 避免浮点尾差
    meta.state = new_state
    meta.cold_since = _format_iso_utc(new_cold_since) if new_cold_since is not None else ""


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _parse_iso_utc(value: str | datetime | None) -> datetime | None:
    """把 ISO 字符串或 datetime 解析为带 tz 的 datetime。空串/None → None。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    s = value.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _format_iso_utc(dt: datetime) -> str:
    """把 datetime 格式化为 '2026-06-02T10:00:00.000Z'。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ---------------------------------------------------------------------------
# 批处理
# ---------------------------------------------------------------------------


def sort_by_heat(metas: Iterable, *, descending: bool = True) -> list:
    """按 heat 排序（降序默认）。

    heat 相同时用 last_access 倒序兜底（让"最近用过"在同分时优先）。
    """
    return sorted(
        metas,
        key=lambda m: (m.heat, m.last_access),
        reverse=descending,
    )