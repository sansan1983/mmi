"""mmi.core.storage —— 会话文件 IO 层。

唯一职责：会话文件 (.session.md) 的读写、原子写、并发锁、目录枚举。
不涉及：状态机、热度、LLM、UI、摘要、标题生成（见各对应模块）。

文件格式权威定义：ARCHITECTURE.md §5
并发安全：
  - 写操作全部走 portalocker 排他锁（同一文件级别的 fcntl/Windows LockFileEx）
  - 锁文件是会话文件同目录的 <session_id>.lock
  - 跨平台：portalocker 在 Windows/macOS/Linux 都给出正确实现
  - 锁是劝告性（advisory）—— 所有读操作不强制加锁（读取是 read-committed
    语义，写者负责 atomic rename）

错误模型：
  - 会话不存在 → 抛 SessionNotFound
  - 文件损坏（frontmatter 不合法）→ 抛 SessionCorrupt
  - 路径越界（试图在 sessions/ 外读写）→ 抛 StorageError
  - IO 错误（磁盘满、权限拒绝）→ 向上抛 OSError
"""

from __future__ import annotations

import re
import shutil
import tempfile
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import portalocker
import yaml

from . import heat as heat_module
from . import paths
from .session import Session, SessionMeta, utcnow_iso

__all__ = [
    "StorageError",
    "SessionNotFound",
    "SessionCorrupt",
    "list_session_ids",
    "list_trash_ids",
    "session_path",
    "trash_path",
    "lock_path",
    "read_meta",
    "read_session",
    "read_trash_session",
    "write_session",
    "append_turn",
    "move_to_trash",
    "delete_session",
    "delete_trash_session",
    "format_turn",
    "parse_turns",
    "count_user_turns",
]

# ---------------------------------------------------------------------------
# LRU 缓存（P2-1）
# ---------------------------------------------------------------------------

_MAX_CACHE_SIZE = 20  # 最多缓存 20 个 session；后续从 config.toml 读取
_session_cache: OrderedDict[str, tuple[float, Session]] = OrderedDict()
_meta_cache: OrderedDict[str, tuple[float, SessionMeta]] = OrderedDict()
_cache_lock = __import__("threading").RLock()


def _cache_get_session(session_id: str):
    """从缓存获取 Session；若文件已被修改（mtime 不匹配）则返回 None。

    返回对象的深拷贝，防止调用方修改污染缓存。
    """
    import copy
    with _cache_lock:
        if session_id not in _session_cache:
            return None
        cached_mtime, session = _session_cache[session_id]
        try:
            actual_mtime = session_path(session_id).stat().st_mtime
        except OSError:
            _session_cache.pop(session_id, None)
            return None
        if actual_mtime != cached_mtime:
            _session_cache.pop(session_id, None)
            return None
        _session_cache.move_to_end(session_id)
        return copy.deepcopy(session)


def _cache_get_meta(session_id: str):
    """从缓存获取 SessionMeta；mtime 不匹配则返回 None。

    返回对象的深拷贝，防止调用方修改污染缓存。
    """
    import copy
    with _cache_lock:
        if session_id not in _meta_cache:
            return None
        cached_mtime, meta = _meta_cache[session_id]
        try:
            actual_mtime = session_path(session_id).stat().st_mtime
        except OSError:
            _meta_cache.pop(session_id, None)
            return None
        if actual_mtime != cached_mtime:
            _meta_cache.pop(session_id, None)
            return None
        _meta_cache.move_to_end(session_id)
        return copy.deepcopy(meta)


def _cache_set_session(session_id: str, session: Session) -> None:
    """写入缓存；若已满则淘汰 LRU（队首）。"""
    with _cache_lock:
        try:
            mtime = session_path(session_id).stat().st_mtime
        except OSError:
            return
        _session_cache[session_id] = (mtime, session)
        _session_cache.move_to_end(session_id)
        if len(_session_cache) > _MAX_CACHE_SIZE:
            _session_cache.popitem(last=False)


def _cache_set_meta(session_id: str, meta: SessionMeta) -> None:
    """写入 meta 缓存。"""
    with _cache_lock:
        try:
            mtime = session_path(session_id).stat().st_mtime
        except OSError:
            return
        _meta_cache[session_id] = (mtime, meta)
        _meta_cache.move_to_end(session_id)
        if len(_meta_cache) > _MAX_CACHE_SIZE:
            _meta_cache.popitem(last=False)


def _cache_invalidate(session_id: str) -> None:
    """使缓存失效（写入后调用）。"""
    with _cache_lock:
        _session_cache.pop(session_id, None)
        _meta_cache.pop(session_id, None)


def _cache_invalidate_all() -> None:
    """清空全部缓存（如外部直接改了磁盘文件）。"""
    with _cache_lock:
        _session_cache.clear()
        _meta_cache.clear()





# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class StorageError(Exception):
    """storage 层所有自定义异常的基类。"""


class SessionNotFound(StorageError, FileNotFoundError):  # noqa: N818
    """请求的 session_id 在磁盘上找不到对应文件。"""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(f"session not found: {session_id}")


class SessionCorrupt(StorageError):  # noqa: N818
    """会话文件存在但 frontmatter 解析失败。"""

    def __init__(self, session_id: str, reason: str) -> None:
        self.session_id = session_id
        self.reason = reason
        super().__init__(f"session corrupt ({session_id}): {reason}")


# ---------------------------------------------------------------------------
# 路径工具
# ---------------------------------------------------------------------------


def session_path(session_id: str) -> Path:
    """根据 session_id 返回 .session.md 的绝对路径。

    校验：session_id 必须非空且只能包含 ULID 合法字符（防止 ../ 越界）。
    """
    _validate_session_id(session_id)
    return paths.get_sessions_dir() / f"{session_id}.session.md"


def lock_path(session_id: str) -> Path:
    """返回与 session_id 关联的锁文件路径。

    锁文件与会话文件同目录、同 session_id，后缀 .lock。
    """
    _validate_session_id(session_id)
    return paths.get_sessions_dir() / f"{session_id}.lock"


def _validate_session_id(session_id: str) -> None:
    """防止路径越界：session_id 必须是 26 字符 ULID。

    抛 ValueError 阻断来自上层的恶意 id。
    """
    import re

    if not isinstance(session_id, str):
        raise ValueError(f"session_id must be str, got {type(session_id).__name__}")
    if not re.match(r"^[0-9A-HJKMNP-TV-Z]{26}$", session_id):
        raise ValueError(f"invalid session_id (must be 26-char ULID): {session_id!r}")


# ---------------------------------------------------------------------------
# 文件锁
# ---------------------------------------------------------------------------


@contextmanager
def _exclusive_lock(session_id: str, timeout_s: float = 10.0) -> Iterator[Path]:
    """获取指定 session 的排他文件锁（portalocker 跨平台）。

    锁是阻塞的，最长等 timeout_s 秒后抛 portalocker.exceptions.LockException。
    用法：
        with _exclusive_lock(sid):
            # 你的写操作

    portalocker 3.x API：用 Lock(filename, timeout, flags=LOCK_EX) 替换旧版
    的 portalocker.lock(file_handle, ...)，避免手动管理 file handle。
    """
    paths.ensure_dirs()
    lpath = lock_path(session_id)
    # 锁文件不需要存在，Lock 类会自动创建；确保父目录在
    lpath.parent.mkdir(parents=True, exist_ok=True)
    lock = portalocker.Lock(
        str(lpath),
        mode="w",
        timeout=timeout_s,
        flags=portalocker.LOCK_EX,
    )
    try:
        lock.acquire()
        yield lpath
    finally:
        lock.release()


def _cleanup_lock_file(session_id: str) -> None:
    """Best-effort 清理 .lock 文件。**必须在 `_exclusive_lock` 之外调用**。

    Windows 上持有句柄的文件无法删除：必须在 `with _exclusive_lock(...)`
    退出（portalocker 已 release 句柄）之后才能 unlink。

    TOCTOU：释放锁到 unlink 之间，另一进程可能已 reopen 同一 .lock 并持有句柄，
    此时本调用会因 PermissionError 失败，被 except OSError 静默吞掉。**这是
    良性的**——残留的 .lock 不影响正确性，因为下次 `_exclusive_lock` 用
    `mode="w"` + LOCK_EX 打开时会 O_CREAT 复用同路径，重新走锁流程。
    """
    lp = lock_path(session_id)
    if lp.exists():
        with suppress(OSError):
            lp.unlink()


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def _dump_frontmatter(meta: SessionMeta) -> str:
    """把 SessionMeta 序列化为 YAML 块（含 --- 包围）。

    排序按 ARCHITECTURE.md §5 字段顺序，方便 diff 友好。
    """
    # 强制字段顺序：先按 ARCHITECTURE.md §5 显式列出，其它兜底
    ordered_keys = [
        "version", "type", "session_id", "agent_id",
        "title", "summary", "summary_version", "summary_history", "keywords",
        "created_at", "updated_at", "last_access",
        "access_count", "heat", "state", "trashed_at", "cold_since",
    ]
    d = asdict(meta)
    # 重新排序（缺失的字段会自然丢弃，让 YAML 更干净）
    sorted_d = {k: d[k] for k in ordered_keys if k in d}
    yaml_text = yaml.safe_dump(
        sorted_d,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=4096,
    )
    return f"---\n{yaml_text}---\n"


def _parse_frontmatter(text: str, session_id_for_error: str) -> tuple[dict, str]:
    """把完整文件解析为 (frontmatter dict, body str)。

    规则：
      - 第一个 --- 在第 0 行
      - 第二个 --- 之后是正文
      - 中间是合法 YAML
    """
    if not text.startswith("---"):
        raise SessionCorrupt(session_id_for_error, "missing opening '---'")
    # 找第二个 ---
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        raise SessionCorrupt(session_id_for_error, "missing closing '---'")
    yaml_block = text[3:end_idx].lstrip("\n")
    body_start = end_idx + 4  # \n---
    # 跳过 --- 之后的换行
    if text[body_start:body_start + 1] == "\n":
        body_start += 1
    body = text[body_start:]
    try:
        meta_dict = yaml.safe_load(yaml_block) or {}
    except yaml.YAMLError as e:
        raise SessionCorrupt(session_id_for_error, f"invalid YAML: {e}") from e
    if not isinstance(meta_dict, dict):
        raise SessionCorrupt(session_id_for_error, f"YAML root is {type(meta_dict).__name__}, expected dict")
    return meta_dict, body


def format_turn(user: str, assistant: str, date: str | None = None) -> str:
    """把一轮对话格式化为 Markdown 片段。

    例（默认日期为今天）：
        ## 2026-06-02

        **User:** 你好

        **Assistant:** hi

    注意：日期按 *turn 开始日* 切分；同一日多条 turn 共享一个 ## 标题。
    但为简单起见，Phase 1 实现里每次调用都输出一个 ## 块。
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    # 防御性：去掉 user / assistant 内的换行污染
    user_clean = user.strip()
    assistant_clean = assistant.strip()
    return f"## {date}\n\n**User:** {user_clean}\n\n**Assistant:** {assistant_clean}\n"


# ---------------------------------------------------------------------------
# 公开 API：读
# ---------------------------------------------------------------------------


def list_session_ids() -> list[str]:
    """枚举 sessions/active 下的所有 session_id（按文件名）。

    不读 frontmatter，O(N) 文件系统 stat 即可。
    返回值是按文件名字符串升序；调用方可以按需重排（比如 ULID 时序）。
    """
    paths.ensure_dirs()
    out: list[str] = []
    for p in sorted(paths.get_sessions_dir().glob("*.session.md")):
        sid = p.stem.removesuffix(".session")
        out.append(sid)
    return out


def read_meta(session_id: str) -> SessionMeta:
    """只读 frontmatter，构造 SessionMeta（不读正文）。

    用途：list_sessions 时大量调用，必须轻量。
    优先走 LRU 缓存（mtime 校验）。
    """
    cached = _cache_get_meta(session_id)
    if cached is not None:
        return cached
    p = session_path(session_id)
    if not p.exists():
        raise SessionNotFound(session_id)
    text = p.read_text(encoding="utf-8")
    meta_dict, _ = _parse_frontmatter(text, session_id)
    meta = SessionMeta.from_dict(meta_dict)
    _cache_set_meta(session_id, meta)
    return meta


def read_session(session_id: str) -> Session:
    """读全文：frontmatter + body → Session。

    用途：chat 流程里需要正文。
    优先走 LRU 缓存（mtime 校验）。
    """
    cached = _cache_get_session(session_id)
    if cached is not None:
        return cached
    p = session_path(session_id)
    if not p.exists():
        raise SessionNotFound(session_id)
    text = p.read_text(encoding="utf-8")
    meta_dict, body = _parse_frontmatter(text, session_id)
    meta = SessionMeta.from_dict(meta_dict)
    # 兜底：如果文件里没有 session_id 字段，用文件名补
    if not meta.session_id:
        meta.session_id = session_id
    s = Session(meta=meta, body=body)
    _cache_set_session(session_id, s)
    return s


# ---------------------------------------------------------------------------
# 公开 API：写
# ---------------------------------------------------------------------------


def _atomic_write(path: Path, content: str) -> None:
    """原子写：先写同目录 .tmp，再 rename 覆盖目标。

    rename 在同一文件系统上是原子的 —— 读取者要么看到旧版要么看到新版，
    永远看不到半写状态。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # 用 NamedTemporaryFile 在同目录创建（确保 rename 不跨 fs）
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as f:
            f.write(content)
        # Windows 上 rename 不覆盖现有文件，需要先 unlink
        if path.exists():
            _unlink_with_retry(path)
        Path(tmp_name).rename(path)
    except Exception:
        # 清理临时文件
        with suppress(OSError):
            Path(tmp_name).unlink()
        raise


def _unlink_with_retry(path: Path, max_retries: int = 3, base_delay: float = 0.05) -> None:
    """Windows 并发 safe unlink，加指数退避。"""
    import time as _time
    for attempt in range(max_retries):
        try:
            path.unlink()
            return
        except PermissionError:
            if attempt < max_retries - 1:
                _time.sleep(base_delay * (2 ** attempt))
            else:
                path.unlink()  # 最后一次直接抛


def write_session(session: Session) -> None:
    """写一个完整会话（frontmatter + body）到磁盘。

    走排他锁 + 原子写。即使两个进程同时调用，也只有一个会赢。
    """
    sid = session.meta.session_id
    if not sid:
        raise StorageError("write_session: session.meta.session_id is empty")

    with _exclusive_lock(sid):
        content = _dump_frontmatter(session.meta) + session.body
        _atomic_write(session_path(sid), content)
        # 同步元数据中的 updated_at
        session.meta.updated_at = utcnow_iso()
        # 使缓存失效（文件已更新）
        _cache_invalidate(sid)
        # 重新缓存最新内容
        _cache_set_session(sid, session)


def update_access(session_id: str) -> SessionMeta:
    """纯增量更新：last_access / access_count / heat（不追加正文）。

    用途：外部工具（如 GA hook）访问 session 时触发热度提升，
    不触发 LLM 调用，不产生任何对话内容。

    实现：锁 → 读 → 改 meta → 原子写 frontmatter（保留原 body）→ 解锁。

    Returns:
        更新后的 SessionMeta（heat / access_count / last_access 已刷新）
    """
    paths.ensure_dirs()
    with _exclusive_lock(session_id):
        s = read_session(session_id)
        now = utcnow_iso()
        s.meta.last_access = now
        s.meta.access_count += 1
        s.meta.updated_at = now
        # heat + state 重新算（Round 0.7：state 持久化，避免下次重新计算）
        heat_module.apply_heat_and_state(s.meta)
        # 只写 frontmatter 部分，不动 body（state 已写入 meta）
        content = _dump_frontmatter(s.meta) + s.body
        _atomic_write(session_path(session_id), content)
        # 使缓存失效并重新写入
        _cache_invalidate(session_id)
        _cache_set_meta(session_id, s.meta)
        _cache_set_session(session_id, s)
        return s.meta


def append_turn(
    session_id: str,
    user: str,
    assistant: str,
) -> Session:
    """追加一轮对话到正文，同时更新 frontmatter 的 updated_at / last_access / access_count。

    返回更新后的 Session（供 manager 立即使用）。
    实现：先锁 → 读 → 改 → 原子写 → 解锁。
    """
    paths.ensure_dirs()
    with _exclusive_lock(session_id):
        # 在锁内读最新 frontmatter（避免 stale view）
        s = read_session(session_id)
        new_turn = format_turn(user, assistant)
        s.body = s.body + ("\n" if s.body and not s.body.endswith("\n") else "") + new_turn
        now = utcnow_iso()
        s.meta.updated_at = now
        s.meta.last_access = now
        s.meta.access_count += 1
        # 重写全文
        content = _dump_frontmatter(s.meta) + s.body
        _atomic_write(session_path(session_id), content)
        # 使缓存失效并重新写入
        _cache_invalidate(session_id)
        _cache_set_session(session_id, s)
        return s


# ---------------------------------------------------------------------------
# 公开 API：删除 / 移到 trash
# ---------------------------------------------------------------------------


def move_to_trash(session_id: str) -> Path:
    """把会话从 active 移到 trash 目录。

    走锁 + 跨目录 move（shutil.move 在同 fs 上是 rename，原子的）。
    在移动前写入 trashed_at 时间戳，供后续 TTL 清理用（ARCHITECTURE §8.1）。
    """
    src = session_path(session_id)
    if not src.exists():
        raise SessionNotFound(session_id)
    paths.get_trash_dir().mkdir(parents=True, exist_ok=True)
    dst = paths.get_trash_dir() / src.name
    with _exclusive_lock(session_id):
        # 先在 active 目录写入 trashed_at（写完再 move，保留元数据）
        s = read_session(session_id)
        s.meta.trashed_at = utcnow_iso()
        content = _dump_frontmatter(s.meta) + s.body
        _atomic_write(src, content)
        # 再 move 到 trash
        shutil.move(str(src), str(dst))
    _cleanup_lock_file(session_id)
    return dst


def delete_session(session_id: str) -> None:
    """硬删除会话文件（不走 trash）。

    走锁。
    """
    p = session_path(session_id)
    if not p.exists():
        raise SessionNotFound(session_id)
    with _exclusive_lock(session_id):
        p.unlink()
    _cleanup_lock_file(session_id)


# ---------------------------------------------------------------------------
# 公开 API：trash 目录操作（Phase 2）
# ---------------------------------------------------------------------------


def trash_path(session_id: str) -> Path:
    """trash 目录里某个 session_id 的绝对路径。"""
    _validate_session_id(session_id)
    return paths.get_trash_dir() / f"{session_id}.session.md"


def list_trash_ids() -> list[str]:
    """枚举 trash 目录下的所有 session_id。"""
    paths.ensure_dirs()
    out: list[str] = []
    for p in sorted(paths.get_trash_dir().glob("*.session.md")):
        sid = p.stem.removesuffix(".session")
        out.append(sid)
    return out


def read_trash_session(session_id: str) -> Session:
    """读 trash 目录里的会话。"""
    p = trash_path(session_id)
    if not p.exists():
        raise SessionNotFound(session_id)
    text = p.read_text(encoding="utf-8")
    meta_dict, body = _parse_frontmatter(text, session_id)
    meta = SessionMeta.from_dict(meta_dict)
    if not meta.session_id:
        meta.session_id = session_id
    return Session(meta=meta, body=body)


def delete_trash_session(session_id: str) -> None:
    """硬删除 trash 目录里的会话（不走 lock，trash 文件不会被并发改）。"""
    p = trash_path(session_id)
    if not p.exists():
        raise SessionNotFound(session_id)
    p.unlink()
    # trash 目录可能也有 lock 文件残留（兼容），顺手清掉
    lp = paths.get_trash_dir() / f"{session_id}.lock"
    if lp.exists():
        with suppress(OSError):
            lp.unlink()


# ---------------------------------------------------------------------------
# 公开 API：turn 解析（Phase 2）
# ---------------------------------------------------------------------------


# 匹配 **User:** ... 或 **Assistant:** ...
_TURN_PATTERN = re.compile(
    r"\*\*(User|Assistant):\*\*\s*(.+?)(?=\n\n\*\*|\Z)", re.DOTALL
)


def parse_turns(body: str) -> list[dict]:
    """从 Markdown body 解析 turn 列表。

    容错：乱序 / 缺 reply / 多余空行都能处理。
    返回 [{"role": "user"|"assistant", "content": "..."}, ...]
    """
    if not body:
        return []
    out: list[dict] = []
    for m in _TURN_PATTERN.finditer(body):
        role = m.group(1).lower()
        content = m.group(2).strip()
        if content:
            out.append({"role": role, "content": content})
    return out


def count_user_turns(body: str) -> int:
    """统计 user 消息轮数（**User:** 出现次数）。"""
    if not body:
        return 0
    return sum(1 for m in _TURN_PATTERN.finditer(body) if m.group(1) == "User")
