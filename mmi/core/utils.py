"""mmi.core.utils — 合并的公共工具函数。

从 gc.py, heat.py, search.py, titler.py 中提取的重复函数。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime


def parse_iso_utc(ts: str | None) -> datetime:
    """解析 ISO 格式 UTC 时间字符串。

    Args:
        ts: ISO 格式时间字符串，如 "2024-06-03T10:00:00Z"

    Returns:
        datetime 对象
    """
    if ts is None:
        return datetime.now(UTC)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(UTC)


_TOKENIZE_EN_RE = re.compile(r'\b\w+\b', re.IGNORECASE)
_TOKENIZE_ZH_RE = re.compile(r'[\u4e00-\u9fff]+')


def tokenize_en(text: str) -> list[str]:
    """英文分词：按单词边界分割。"""
    return _TOKENIZE_EN_RE.findall(text)


def tokenize_zh(text: str) -> list[str]:
    """中文分词：按连续汉字匹配。"""
    return _TOKENIZE_ZH_RE.findall(text)
