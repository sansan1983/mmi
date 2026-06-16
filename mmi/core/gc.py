"""mmi.core.gc —— trash 目录的 TTL 垃圾回收 + zombie/cold 清理。

ARCHITECTURE.md §8.1 / §9 Phase 4：
  - 默认 trash TTL = 7 天
  - 触发方式：`mmi gc` 手动 / 后续 Phase 可加后台定时
  - 判定依据：会话 frontmatter 的 trashed_at 字段
  - 兜底：trashed_at 缺失时退回到文件 mtime

Phase 4 范围：
  - cold / zombie 状态迁移：heat.py（独立模块）
  - zombie 直接删不进 trash（死了就直接埋）
  - cold ≥7 天 → 进 trash（还有7天兜底）
  - trash ≥7 天 → 彻底删

GC 冷热分层设计（Round 0.4）：
  - zombie：≥3 天不访问 → 直接删除（不进 trash）
  - cold：≥7 天在 cold 状态 → 进 trash（再留 7 天）
  - trash：≥7 天在 trash → 彻底删除
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import paths, storage, heat as heat_module
from .session import SessionState

__all__ = [
    "gc_trash",
    "gc_zombies",
    "gc_cold",
    "gc_all",
    "GcReport",
    "GcEntry",
    "GcKind",
    "DEFAULT_TRASH_TTL_DAYS",
]


DEFAULT_TRASH_TTL_DAYS = 7

# GcEntry 的类别
GcKind = str  # "trash" | "zombie" | "cold"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class GcEntry:
    """一个被 gc 检查的会话条目。"""

    session_id: str
    kind: GcKind                     # "trash" | "zombie" | "cold"
    trashed_at: str                 # ISO 字符串（zombie/cold 时为 cold_since）
    age_days: float
    deleted: bool = False           # dry_run 时为 False
    bytes_freed: int = 0            # dry_run 时为 0
    error: str = ""                 # 删除失败时填
    reason: str = ""                # 详细原因（供详细报告用）


@dataclass
class GcReport:
    """gc_*() 的返回。"""

    ttl_days: int
    dry_run: bool
    entries: list[GcEntry] = field(default_factory=list)

    @property
    def deleted_count(self) -> int:
        return sum(1 for e in self.entries if e.deleted)

    @property
    def kept_count(self) -> int:
        return sum(1 for e in self.entries if not e.deleted and not e.error)

    @property
    def failed_count(self) -> int:
        return sum(1 for e in self.entries if e.error)

    @property
    def bytes_freed(self) -> int:
        return sum(e.bytes_freed for e in self.entries)

    @property
    def trash_entries(self) -> list[GcEntry]:
        return [e for e in self.entries if e.kind == "trash"]

    @property
    def zombie_entries(self) -> list[GcEntry]:
        return [e for e in self.entries if e.kind == "zombie"]

    @property
    def cold_entries(self) -> list[GcEntry]:
        return [e for e in self.entries if e.kind == "cold"]


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def parse_iso_utc(s: str | None) -> datetime | None:
    """解析 ISO 字符串为 UTC datetime。"""
    if s is None:
        return None
    try:
        # 兼容 +00:00 和 Z
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def gc_trash(
    *,
    ttl_days: int = DEFAULT_TRASH_TTL_DAYS,
    dry_run: bool = False,
    trash_dir: Path | None = None,
) -> GcReport:
    """扫 trash 目录，删超过 ttl_days 的会话。

    Args:
        ttl_days: TTL 天数（默认 7）
        dry_run: True 时只列不删
        trash_dir: 自定义 trash 路径（测试用）

    Returns:
        GcReport，每条都列出来，标记 deleted / error
    """
    report = GcReport(ttl_days=ttl_days, dry_run=dry_run)
    paths.ensure_dirs()
    tdir = trash_dir or paths.get_trash_dir()
    if not tdir.exists():
        return report

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=ttl_days)

    for sid in storage.list_trash_ids():
        try:
            s = storage.read_trash_session(sid)
            trashed_at_str = s.meta.trashed_at
            trashed_at = s.meta.trashed_at_parsed
            if trashed_at is None:
                # 兜底：用文件 mtime
                p = storage.trash_path(sid)
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
                trashed_at = mtime
                trashed_at_str = mtime.strftime("%Y-%m-%dT%H:%M:%S.") + f"{mtime.microsecond // 1000:03d}Z"

            age = now - trashed_at
            age_days = age.total_seconds() / 86400
            entry = GcEntry(
                session_id=sid,
                kind="trash",
                trashed_at=trashed_at_str,
                age_days=age_days,
                reason=f"TTL {ttl_days}d, age {age_days:.1f}d",
            )
            if trashed_at < cutoff:
                # 过期
                if dry_run:
                    entry.deleted = False  # dry_run 不真删
                else:
                    try:
                        p = storage.trash_path(sid)
                        size = p.stat().st_size if p.exists() else 0
                        storage.delete_trash_session(sid)
                        entry.deleted = True
                        entry.bytes_freed = size
                    except OSError as e:
                        entry.error = str(e)
            report.entries.append(entry)
        except storage.SessionCorrupt:
            entry = GcEntry(
                session_id=sid,
                kind="trash",
                trashed_at="",
                age_days=0.0,
                error="corrupt",
            )
            report.entries.append(entry)

    return report


def gc_zombies(
    *,
    dry_run: bool = False,
    sessions_dir: Path | None = None,
    config: heat_module.HeatConfig | None = None,
) -> GcReport:
    """扫 active 目录，删 state==zombie 的会话。

    Phase 4：heat 已经在 chat() 末尾自动算，zombie 状态会自然出现。
    本函数在 gc 时落地：zombie 不进 trash（不进 trash 才是关键 ——
    zombie 是"已经死了"，没必要再保留 7 天兜底）。

    Args:
        dry_run: True 时只列不删
        sessions_dir: 自定义 active 路径（测试用）
        config: 热度阈值（默认 HeatConfig()）
    """
    if config is None:
        config = heat_module.HeatConfig()
    report = GcReport(ttl_days=0, dry_run=dry_run)
    paths.ensure_dirs()
    sdir = sessions_dir or paths.get_sessions_dir()
    if not sdir.exists():
        return report

    now = datetime.now(timezone.utc)

    for sid in storage.list_session_ids():
        try:
            s = storage.read_session(sid)
            state_str = str(s.meta.state)
            # 升级：cold 持续 > zombie_days 时先升为 zombie，再删
            if state_str == SessionState.COLD:
                heat_module.apply_heat_and_state(s.meta, now=now, config=config)
                state_str = str(s.meta.state)
            if state_str == SessionState.ZOMBIE:
                # zombie 直接删，不进 trash
                entry = GcEntry(
                    session_id=sid,
                    kind="zombie",
                    trashed_at=s.meta.cold_since or "",
                    age_days=(now - (s.meta.cold_since_parsed or now)).total_seconds() / 86400,
                    reason="state=zombie (no longer in use)",
                )
                if not dry_run:
                    try:
                        p = storage.session_path(sid)
                        size = p.stat().st_size if p.exists() else 0
                        storage.delete_session(sid)
                        entry.deleted = True
                        entry.bytes_freed = size
                    except OSError as e:
                        entry.error = str(e)
                report.entries.append(entry)
        except storage.SessionNotFound:
            pass
        except storage.SessionCorrupt:
            entry = GcEntry(
                session_id=sid,
                kind="zombie",
                trashed_at="",
                age_days=0.0,
                error="corrupt",
            )
            report.entries.append(entry)

    return report


def gc_cold(
    *,
    cold_ttl_days: int = 7,
    dry_run: bool = False,
    sessions_dir: Path | None = None,
) -> GcReport:
    """扫 active 目录，把 cold ≥ cold_ttl_days 的会话移入 trash。

    GC 冷热分层设计（Round 0.4）：
      cold ≥7 天 → 进 trash（再留 7 天）
      trash ≥7 天 → 彻底删（由 gc_trash 处理）

    Args:
        cold_ttl_days: cold 状态存活天数（默认 7）
        dry_run: True 时只列不删
        sessions_dir: 自定义 active 路径（测试用）

    Returns:
        GcReport，每条 cold 条目标记 deleted（已移动）/ error
    """
    report = GcReport(ttl_days=cold_ttl_days, dry_run=dry_run)
    paths.ensure_dirs()
    sdir = sessions_dir or paths.get_sessions_dir()
    if not sdir.exists():
        return report

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=cold_ttl_days)

    for sid in storage.list_session_ids():
        try:
            s = storage.read_session(sid)
            state_str = str(s.meta.state)
            if state_str == SessionState.COLD:
                cold_since_dt = s.meta.cold_since_parsed
                if cold_since_dt is not None and cold_since_dt < cutoff:
                    # cold 已超期，进 trash
                    cold_age = (now - cold_since_dt).total_seconds() / 86400
                    entry = GcEntry(
                        session_id=sid,
                        kind="cold",
                        trashed_at=s.meta.cold_since or "",
                        age_days=cold_age,
                        reason=f"cold {cold_age:.1f}d >= {cold_ttl_days}d threshold",
                    )
                    if not dry_run:
                        try:
                            p = storage.session_path(sid)
                            size = p.stat().st_size if p.exists() else 0
                            storage.move_to_trash(sid)
                            entry.deleted = True
                            entry.bytes_freed = size
                        except OSError as e:
                            entry.error = str(e)
                    report.entries.append(entry)
                else:
                    # cold 未超期，列出但保留
                    cold_age = (cold_since_dt and (now - cold_since_dt).total_seconds() / 86400) or 0.0
                    entry = GcEntry(
                        session_id=sid,
                        kind="cold",
                        trashed_at=s.meta.cold_since or "",
                        age_days=cold_age,
                        reason=f"cold {cold_age:.1f}d < {cold_ttl_days}d, kept",
                    )
                    report.entries.append(entry)
        except storage.SessionNotFound:
            pass
        except storage.SessionCorrupt:
            entry = GcEntry(
                session_id=sid,
                kind="cold",
                trashed_at="",
                age_days=0.0,
                error="corrupt",
            )
            report.entries.append(entry)

    return report


def gc_all(
    *,
    ttl_days: int = DEFAULT_TRASH_TTL_DAYS,
    dry_run: bool = False,
) -> GcReport:
    """一键清：cold 超期 + trash 过期 + zombie 全部。

    返回合并的 GcReport（entries 里三种 kind 都有）。

    调用顺序：gc_cold → gc_zombies → gc_trash
    （gc_cold 产生的新 trash 条目也会被 gc_trash 处理）
    """
    cold_report = gc_cold(cold_ttl_days=ttl_days, dry_run=dry_run)
    zombie_report = gc_zombies(dry_run=dry_run)
    trash_report = gc_trash(ttl_days=ttl_days, dry_run=dry_run)

    merged = GcReport(ttl_days=ttl_days, dry_run=dry_run)
    merged.entries = cold_report.entries + zombie_report.entries + trash_report.entries
    return merged