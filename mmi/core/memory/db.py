"""mmi.core.memory.db —— SQLite 连接 + schema + 锁。

依赖项:paths (从 mmi.core)。
被依赖:store, search, summary (无直接依赖)。
"""

from __future__ import annotations

import sqlite3
import threading

from mmi.core import paths

_MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    memory_id    TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    turns_at     INTEGER NOT NULL,
    title        TEXT,
    decision     TEXT,
    conclusion   TEXT,
    todos        TEXT,
    raw_excerpt  TEXT,
    content_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_hash ON memories(content_hash);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    title, decision, conclusion, todos, raw_excerpt,
    content='memories', content_rowid='rowid',
    tokenize='unicode61'
);

-- FTS5 external content 模式:用触发器自动同步,避免手工 DELETE/INSERT 撞内容表
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES (new.rowid, new.title, new.decision, new.conclusion, new.todos, new.raw_excerpt);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES ('delete', old.rowid, old.title, old.decision, old.conclusion, old.todos, old.raw_excerpt);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES ('delete', old.rowid, old.title, old.decision, old.conclusion, old.todos, old.raw_excerpt);
    INSERT INTO memories_fts(rowid, title, decision, conclusion, todos, raw_excerpt)
    VALUES (new.rowid, new.title, new.decision, new.conclusion, new.todos, new.raw_excerpt);
END;
"""


_db_lock = threading.Lock()


def _connect_db() -> sqlite3.Connection:
    """开 SQLite 连接（同步、单线程安全，靠 _db_lock 串行）。"""
    paths.ensure_dirs()
    conn = sqlite3.connect(str(paths.get_memory_db_path()), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(_MEMORY_SCHEMA)
    return conn


def _get_conn() -> sqlite3.Connection:
    """获取（每线程）连接 —— 用 thread-local 避免跨线程共享。"""
    import threading as _t
    tls = getattr(_get_conn, "_tls", None)
    if tls is None:
        tls = _t.local()
        _get_conn._tls = tls  # type: ignore[attr-defined]
    if not hasattr(tls, "conn") or tls.conn is None:
        tls.conn = _connect_db()
    return tls.conn
