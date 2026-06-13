"""Patch storage.py to add LRU cache (P2-1)."""
import re
from pathlib import Path

p = Path(r"F:\AI data\codex\mmi\mmi\core\storage.py")
content = p.read_text(encoding="utf-8")

# 1. Add 'from collections import OrderedDict' to imports
old_imports = """from __future__ import annotations

import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator"""
new_imports = """from __future__ import annotations

import re
import shutil
import tempfile
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterator"""
assert old_imports in content, "import block not found"
content = content.replace(old_imports, new_imports, 1)

# 2. Insert LRU cache code after __all__ block
lru_code = '''

# ---------------------------------------------------------------------------
# LRU 缓存（P2-1）
# ---------------------------------------------------------------------------

_MAX_CACHE_SIZE = 20  # 最多缓存 20 个 session；后续从 config.toml 读取
_session_cache: OrderedDict[str, tuple[float, "Session"]] = OrderedDict()
_meta_cache: OrderedDict[str, tuple[float, "SessionMeta"]] = OrderedDict()
_cache_lock = __import__("threading").RLock()


def _cache_get_session(session_id: str):
    """从缓存获取 Session；若文件已被修改（mtime 不匹配）则返回 None。"""
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
        return session


def _cache_get_meta(session_id: str):
    """从缓存获取 SessionMeta；mtime 不匹配则返回 None。"""
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
        return meta


def _cache_set_session(session_id: str, session: "Session") -> None:
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


def _cache_set_meta(session_id: str, meta: "SessionMeta") -> None:
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


'''

insert_marker = '''__all__ = [
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
]'''
assert insert_marker in content, "__all__ block not found"
content = content.replace(insert_marker, insert_marker + lru_code, 1)

# 3. Patch read_meta to use cache
old_read_meta = '''def read_meta(session_id: str) -> SessionMeta:
    """只读 frontmatter，构造 SessionMeta（不读正文）。

    用途：list_sessions 时大量调用，必须轻量。
    """
    p = session_path(session_id)
    if not p.exists():
        raise SessionNotFound(session_id)
    text = p.read_text(encoding="utf-8")
    meta_dict, _ = _parse_frontmatter(text, session_id)
    return SessionMeta.from_dict(meta_dict)'''
new_read_meta = '''def read_meta(session_id: str) -> SessionMeta:
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
    return meta'''
assert old_read_meta in content, "old_read_meta not found"
content = content.replace(old_read_meta, new_read_meta, 1)

# 4. Patch read_session to use cache
old_read_session = '''def read_session(session_id: str) -> Session:
    """读全文：frontmatter + body → Session。

    用途：chat 流程里需要正文。
    """
    p = session_path(session_id)
    if not p.exists():
        raise SessionNotFound(session_id)
    text = p.read_text(encoding="utf-8")
    meta_dict, body = _parse_frontmatter(text, session_id)
    meta = SessionMeta.from_dict(meta_dict)
    # 兜底：如果文件里没有 session_id 字段，用文件名补
    if not meta.session_id:
        meta.session_id = session_id
    return Session(meta=meta, body=body)'''
new_read_session = '''def read_session(session_id: str) -> Session:
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
    return s'''
assert old_read_session in content, "old_read_session not found"
content = content.replace(old_read_session, new_read_session, 1)

# 5. Patch write_session: add cache invalidate + re-cache after write
old_write_end = '''        # 同步元数据中的 updated_at
        session.meta.updated_at = utcnow_iso()'''
new_write_end = '''        # 同步元数据中的 updated_at
        session.meta.updated_at = utcnow_iso()
        # 使缓存失效（文件已更新）
        _cache_invalidate(sid)
        # 重新缓存最新内容
        _cache_set_session(sid, session)'''
assert old_write_end in content, "old_write_end not found"
content = content.replace(old_write_end, new_write_end, 1)

# 6. Patch update_access: invalidate + re-cache
old_update_tail = '''        content = _dump_frontmatter(s.meta) + s.body
        _atomic_write(session_path(session_id), content)
        return s.meta'''
new_update_tail = '''        content = _dump_frontmatter(s.meta) + s.body
        _atomic_write(session_path(session_id), content)
        # 使缓存失效并重新写入
        _cache_invalidate(session_id)
        _cache_set_meta(session_id, s.meta)
        _cache_set_session(session_id, s)
        return s.meta'''
assert old_update_tail in content, "old_update_tail not found"
content = content.replace(old_update_tail, new_update_tail, 1)

# 7. Patch append_turn: invalidate + re-cache
old_append_tail = '''        content = _dump_frontmatter(s.meta) + s.body
        _atomic_write(session_path(session_id), content)
        return s'''
new_append_tail = '''        content = _dump_frontmatter(s.meta) + s.body
        _atomic_write(session_path(session_id), content)
        # 使缓存失效并重新写入
        _cache_invalidate(session_id)
        _cache_set_session(session_id, s)
        return s'''
assert old_append_tail in content, "old_append_tail not found"
content = content.replace(old_append_tail, new_append_tail, 1)

p.write_text(content, encoding="utf-8")
print("storage.py patched successfully with LRU cache (P2-1)")
