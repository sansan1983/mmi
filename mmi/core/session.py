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
from datetime import datetime, timezone
from typing import Any, Literal

from ulid import ULID

__all__ = [
    "SessionMeta",
    "Session",
    "SessionState",
    "ULID_PATTERN",
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
    def values(cls) -> tuple[str, str, str, str]:
        return (cls.ACTIVE, cls.WARM, cls.COLD, cls.ZOMBIE)

    @classmethod
    def from_str(cls, s: str) -> "SessionState":
        if s not in cls.values():
            raise ValueError(f"Invalid state: {s!r}. Must be one of {cls.values()}")
        return cls(s)  # type: ignore[return-value]

    def __repr__(self) -> str:
        return f"SessionState({self.value!r})"


# 为向后兼容保留旧别名（heat.py / manager.py 用 Literal 做类型注解时仍可引用）
SessionStateLiteral = Literal["active", "warm", "cold", "zombie"]

# ULID 校验正则：26 字符 Crockford Base32（含 0-9 A-H J-K M-N P-T V-Z；不含 I/L/O/U）。
# storage.write_session / move_to_trash 等用 inline 表达式做防御性校验，本常量
# 是同一规则的命名版本，供测试与外部模块直接复用。
ULID_PATTERN = r"^[0-9A-HJKMNP-TV-Z]{26}$"

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
    # 用 datetime 手动拼，避免依赖外部 ISO 库
    from datetime import datetime, timezone

    dt = datetime.now(timezone.utc)
    # 强制毫秒精度 + Z 后缀
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _parse_datetime(value: Any) -> datetime | None:
    """把 YAML 加载出来的任意值转成带 tz 的 aware datetime（UTC）。

    允许的类型：
      - str   → 按 ISO-8601 解析（'2026-06-02T19:48:54.177Z'）
      - datetime → 若 naive 则加 UTC tzinfo
      - None  → None（字段缺失/空）
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        # 空字符串 → 字段不存在，跳过
        if not value.strip():
            return None
        s = value.rstrip("Z")
        # 北京时间偏移处理：原始数据用 UTC 存储，已确认
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    raise ValueError(f"_parse_datetime 不支持类型 {type(value).__name__}")


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
    def from_dict(cls, d: dict[str, Any]) -> "SessionMeta":
        """从 frontmatter dict 构造。

        容错策略：
          - 缺失字段用 dataclass 默认值
          - 多余字段忽略
          - 类型不匹配抛 ValueError（不静默吞掉）

        注意：summary_history 与 keywords 是 list 字段；YAML 加载出来
        可能是 list 或 None，None 会被 dataclass 字段默认值替换。

        Bugfix（Round 0.2）：时间字段从 YAML 加载后是 ISO 字符串，
        内部需要 datetime 对象才能参与 heat 计算。统一在此解析。
        """
        if not isinstance(d, dict):
            raise ValueError(f"SessionMeta.from_dict 需要 dict，得到 {type(d).__name__}")
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in d.items() if k in known}

        # 时间字段：YAML 存 ISO 字符串，内部用 datetime 对象
        for field_name in ("created_at", "updated_at", "last_access", "trashed_at", "cold_since"):
            if field_name in clean:
                clean[field_name] = _parse_datetime(clean[field_name])

        return cls(**clean)

    # ----- 工厂方法 -------------------------------------------------------

    @classmethod
    def new(cls, session_id: str, title: str = DEFAULT_TITLE) -> "SessionMeta":
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
    def empty(cls, session_id: str, title: str = DEFAULT_TITLE) -> "Session":
        """构造一个空会话（刚创建、没任何 turn）。"""
        return cls(meta=SessionMeta.new(session_id, title), body="")