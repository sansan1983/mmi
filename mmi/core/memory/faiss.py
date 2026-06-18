"""mmi.core.memory.faiss —— FAISS 索引内存池 (P2-10)。

之前:每次 store_memory 都 idx.add() + write_index(全量) + write_ids
      → 1000 条记忆 ≈ 1000 次 ~2MB 文件写,IO 爆
现在:维护 _INMEM_INDEX + _INMEM_IDS,首次 lazy load(从磁盘读)
      每次 add() 仅内存操作;写盘靠 _maybe_flush() 节流

进程崩溃容忍:
  - 已 commit 到 SQLite 的 record 是"权威";FAISS 只是向量索引
  - 启动时 _ensure_loaded() 从磁盘读完整索引 → 永远一致
  - 内存里未 flush 的向量只是"少召几条",不影响正确性

失效:
  - reset_for_test() 显式清空(测试隔离)
  - 维度不匹配(_INMEM_INDEX 是按首次 embedder 维度建的)
    → 重建空索引;不报错(用户切模型是允许的)

依赖项:paths。
被依赖:store, search。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from mmi.core import paths

_INMEM_INDEX = None         # faiss.IndexFlatL2 | None
_INMEM_IDS: list[str] = []
_INMEM_DIM: int = 0
_INMEM_DIRTY: int = 0        # 累计 add 次数,达到 FLUSH_THRESHOLD 触发 flush
_INMEM_LOADED = False        # 防止重复读盘

# 50 条/5 分钟触发 flush(可调)
FLUSH_THRESHOLD = 50
FLUSH_INTERVAL_S = 300.0
_LAST_FLUSH_TIME = 0.0

_INMEM_LOCK = threading.Lock()


def _faiss_index_path() -> Path:
    return paths.get_faiss_index_path()


def _faiss_ids_path() -> Path:
    return paths.get_faiss_ids_path()


def _load_faiss_ids() -> list[str]:
    """读 vector 位置 i → memory_id 的列表。文件不存在 → 空列表。"""
    p = _faiss_ids_path()
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return [str(x) for x in data]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _save_faiss_ids(ids: list[str]) -> None:
    paths.ensure_dirs()
    p = _faiss_ids_path()
    tmp = p.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False)
    tmp.replace(p)


def _load_faiss_index(dim: int):
    """读 FAISS 索引；不存在 / 维度不匹配 → 重建空索引。"""
    import faiss  # 局部导入：不依赖时可降级
    p = _faiss_index_path()
    if p.exists():
        try:
            idx = faiss.read_index(str(p))
            if idx.d == dim:
                return idx
        except Exception:
            pass
    return faiss.IndexFlatL2(dim)


def _save_faiss_index(idx) -> None:
    import faiss
    paths.ensure_dirs()
    p = _faiss_index_path()
    tmp = p.with_suffix(".index.tmp")
    faiss.write_index(idx, str(tmp))
    tmp.replace(p)


def _ensure_loaded(dim: int) -> None:
    """懒加载:首次访问时从磁盘读索引 + ids 到内存。

    线程安全;维度不匹配 → 重建空索引(允许切 embedding 模型)。
    """
    global _INMEM_INDEX, _INMEM_IDS, _INMEM_DIM, _INMEM_LOADED
    if _INMEM_LOADED and dim == _INMEM_DIM:
        return
    with _INMEM_LOCK:
        if _INMEM_LOADED and dim == _INMEM_DIM:
            return
        _INMEM_INDEX = _load_faiss_index(dim)
        _INMEM_IDS = _load_faiss_ids()
        _INMEM_DIM = dim
        _INMEM_DIRTY = 0  # noqa: N806
        _INMEM_LOADED = True


def _maybe_flush() -> None:
    """阈值触发 flush:dirty >= FLUSH_THRESHOLD。

    写盘失败不阻塞主流程(下次再试)。
    """
    global _INMEM_DIRTY
    if _INMEM_INDEX is None:
        return
    if _INMEM_DIRTY < FLUSH_THRESHOLD:
        return
    with _INMEM_LOCK:
        if _INMEM_DIRTY < FLUSH_THRESHOLD:
            return
        _INMEM_DIRTY = 0  # reset before writing (noqa: N806)
        try:
            _save_faiss_index(_INMEM_INDEX)
            _save_faiss_ids(_INMEM_IDS)
        except Exception:
            pass


def flush_faiss() -> None:
    """显式 flush(测试 / 进程退出用)。"""
    global _INMEM_DIRTY
    if _INMEM_INDEX is None:
        return
    with _INMEM_LOCK:
        _INMEM_DIRTY = 0  # reset before writing (noqa: N806)
        try:
            _save_faiss_index(_INMEM_INDEX)
            _save_faiss_ids(_INMEM_IDS)
        except Exception:
            pass
