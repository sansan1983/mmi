"""mmi.core._time —— 共享时间解析/格式化工具。

集中 5 处原本散落的 parse_iso_utc / format_iso_utc 重复实现,
统一签名和行为(空值 / 错类型 / naive datetime 走统一兜底)。
"""

from __future__ import annotations

from datetime import UTC, datetime


def parse_iso_utc(value: str | datetime | None) -> datetime | None:
    """把 ISO 字符串或 datetime 解析为带 tz 的 aware datetime (UTC)。

    行为:
      - None / 空字符串 → None
      - datetime 且 naive → 加 UTC tzinfo
      - datetime 且 aware → 原样返回
      - str 以 'Z' 结尾 → 替换为 '+00:00' 再 fromisoformat
      - 解析失败 → None(不抛异常, 兼容所有现有调用方)

    Returns:
        带 tz 的 datetime, 或 None (无法解析 / 输入为空)。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def format_iso_utc(dt: datetime | None) -> str:
    """把 datetime 格式化为 '2026-06-02T10:00:00.000Z'。None → ''。

    强制毫秒精度 + 'Z' 后缀(与 frontmatter 字段格式一致)。
    naive datetime 自动加 UTC tzinfo。
    """
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def utcnow_iso() -> str:
    """当前 UTC 时间的 ISO-8601 字符串(带 'Z' 后缀)。"""
    return format_iso_utc(datetime.now(UTC))
