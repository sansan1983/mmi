"""mmi.core.session —— 会话数据契约。

定义 SessionMeta / Session 两个核心 dataclass，以及 frontmatter 互转
方法。**不**涉及 IO（读写文件是 storage.py 的职责）、**不**涉及 LLM、
**不**涉及状态迁移（那是 heat.py / manager.py 的事）。

数据格式权威定义：ARCHITECTURE.md §5
类设计参考：ARCHITECTURE.md §7

注意：
  - session_id 走 ULID（26 字符 Crockford Base32，时序可排序）
  - state 必须是四态字面量之一
  - 所有时间字段一律 ISO-8601 UTC 字符串（带 'Z' 后缀），不存 datetime 对象
    —— 因为要直接序列化到 YAML，datetime 在 frontmatter 里很难看
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any

from ulid import ULID

__all__ = [
    "SessionMeta",
    "Session",
    "SessionState",
    "new_session_id",
    "utcnow_iso",
    "DEFAULT_TITLE",
    "DEFAULT_SUMMARY",
]


# ---------------------------------------------------------------------------
# State 枚举
# ---------------------------------------------------------------------------

class SessionState(str):
    """会话状态枚举（四态字面量强化版）。

    继承 str 保证与旧 frontmatter YAML 字面量完全兼容（"active" in state_enum）。
    """
    ACTIVE = "active"
    WARM   = "warm"
    COLD   = "cold"
    ZOMBIE = "zombie"

    @classmethod
    def values(cls: type[SessionState]) -> tuple[str, str, str, str]:
        return (cls.ACTIVE, cls.WARM, cls.COLD, cls.ZOMBIE)

    @classmethod
    def from_str(cls: type[SessionState], s: str) -> SessionState:
        if s not in cls.values():
            raise ValueError(f"Invalid state: {s!r}. Must be one of {cls.values()}")
        return cls(s)  # type: ignore[return-value]

    def __repr__(self) -> str:
        return f"SessionState({self.value!r})"


# 新建会话的占位标题 / 摘要
# 真实生成在 Phase 2（titler.py / summarizer.py）
DEFAULT_TITLE = "untitled"
DEFAULT_SUMMARY = ""


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def new_session_id() -> str:
    """生成新的 session_id（26 字符 ULID，时序可排序）。

    用法：manager.create() 里生成后写入 frontmatter。
    """
    return str(ULID())


def utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO-8601 字符串（带 'Z' 后缀）。

    例：'2026-06-02T10:00:00.000Z'

    frontmatter 里所有时间字段都用这个格式。
    """
    from mmi.core import _time
    return _time.utcnow_iso()


def _parse_datetime(value: Any) -> datetime | None:
    """把任意值转成带 tz 的 aware datetime（UTC）。

    允许的类型：
      - str   → 按 ISO-8601 解析（'2026-06-02T19:48:54.177Z'）
      - datetime → 若 naive 则加 UTC tzinfo
      - None  → None（字段缺失/空）
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        # 空字符串 → 字段不存在，跳过
        if not value.strip():
            return None
        s = value.rstrip("Z")
        # 北京时间偏移处理：原始数据用 UTC 存储，已确认
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    raise ValueError(f"_parse_datetime 不支持类型 {type(value).__name__}")


def _coerce_iso_str(value: Any) -> str:
    """把任意时间值规整成 ISO-8601 字符串（空值归一为 ""）。

    from_dict 用：保证字段类型始终是 str，与 dataclass 声明一致。
      - str   → 去掉首尾空白
      - datetime → 转 UTC aware 再格式化
      - None  → ""
      - 其他  → ValueError
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"
    raise ValueError(f"_coerce_iso_str 不支持类型 {type(value).__name__}")


# ---------------------------------------------------------------------------
# 核心数据类
# ---------------------------------------------------------------------------


@dataclass
class SessionMeta:
    """会话的元数据子集（对应 frontmatter）。

    与 Session 的区别：SessionMeta 不含 body，启动期只读 frontmatter 即可
    构造，O(1) 开销；Session 多了 body，构造时需要读全文，O(N) 开销。

    字段顺序与 ARCHITECTURE.md §5 一致，**禁止随意增删**（破坏格式契约）。
    """

    # 标识
    version: int = 1
    type: str = "session"
    session_id: str = ""                # ULID，26 字符
    agent_id: str = "mmi"

    # 人类可读
    title: str = DEFAULT_TITLE
    summary: str = DEFAULT_SUMMARY
    summary_version: int = 1
    summary_history: list[dict[str, Any]] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    # 时间
    created_at: str = ""                # ISO-8601 UTC
    updated_at: str = ""
    last_access: str = ""

    # 活跃度
    access_count: int = 0
    heat: float = 0.0

    # 生命周期
    state: SessionState = "active"
    trashed_at: str = ""           # ISO-8601 UTC；仅 trash 目录里的会话有值
    cold_since: str = ""           # ISO-8601 UTC；state 首次进入 cold 时写入，
                                   # 离开 cold 时清空。zombie 判定依赖此字段。

    # ----- frontmatter 互转 -----------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（供 PyYAML.dump 写入 frontmatter）。

        保留字段顺序与 ARCHITECTURE.md §5 一致，方便 diff 友好。
        """
        d = asdict(self)
        # 去掉空字符串与空列表，让 YAML 更干净；但保留 0 / False
        return d

    @classmethod
    def from_dict(cls: type[SessionMeta], d: dict[str, Any]) -> SessionMeta:
        """从 frontmatter dict 构造。

        容错策略：
          - 缺失字段用 dataclass 默认值
          - 多余字段忽略
          - 类型不匹配抛 ValueError（不静默吞掉）

        时间字段统一保持为 ISO-8601 字符串（与字段类型 `str` 一致），
        需要 datetime 时用对应的 `*_parsed` 属性（懒解析）。
        """
        if not isinstance(d, dict):
            raise ValueError(f"SessionMeta.from_dict 需要 dict，得到 {type(d).__name__}")
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}

        # 时间字段：YAML 加载后可能是 str、datetime 或 None。
        # 统一规范成 str（与字段类型一致；空值归一为 ""）。
        for field_name in (
            "created_at", "updated_at", "last_access", "trashed_at", "cold_since",
        ):
            if field_name in clean:
                clean[field_name] = _coerce_iso_str(clean[field_name])

        return cls(**clean)

    # ----- 懒解析的 datetime 属性 ------------------------------------------
    #
    # heat.py / gc.py 等需要把 ISO 字符串转成 datetime 做差值计算，
    # 单独提供 `*_parsed` 属性避免在 from_dict 里集中转换。
    # 空字符串/缺失字段 → None（不抛错，调用方应自行处理）。

    @property
    def created_at_parsed(self) -> datetime | None:
        return _parse_datetime(self.created_at)

    @property
    def updated_at_parsed(self) -> datetime | None:
        return _parse_datetime(self.updated_at)

    @property
    def last_access_parsed(self) -> datetime | None:
        return _parse_datetime(self.last_access)

    @property
    def trashed_at_parsed(self) -> datetime | None:
        return _parse_datetime(self.trashed_at)

    @property
    def cold_since_parsed(self) -> datetime | None:
        return _parse_datetime(self.cold_since)

    # ----- 工厂方法 -------------------------------------------------------

    @classmethod
    def new(cls: type[SessionMeta], session_id: str, title: str = DEFAULT_TITLE) -> SessionMeta:
        """构造一个全新的、刚创建的 SessionMeta（所有时间戳对齐到当下）。"""
        now = utcnow_iso()
        return cls(
            session_id=session_id,
            title=title,
            created_at=now,
            updated_at=now,
            last_access=now,
            state="active",
            access_count=1,
            heat=1.0,
        )


@dataclass
class Session:
    """会话全文 = 元数据 + 正文。

    body 是 Markdown 字符串，按日期分段，结构：
        ## 2026-05-28
        **User:** ...
        **Assistant:** ...
    """
    meta: SessionMeta
    body: str = ""

    # ----- 工厂方法 -------------------------------------------------------

    @classmethod
    def empty(cls: type[Session], session_id: str, title: str = DEFAULT_TITLE) -> Session:
        """构造一个空会话（刚创建、没任何 turn）。"""
        return cls(meta=SessionMeta.new(session_id, title), body="")
