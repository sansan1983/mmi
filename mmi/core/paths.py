"""mmi.core.paths —— 跨平台数据根目录。

唯一职责：把 ~/.mmi/ 及其子目录在不同操作系统下解析成统一的 pathlib.Path，
并提供 idempotent 的目录创建函数（重复调用不报错）。

不关心：会话格式、文件锁、frontmatter —— 那些是 storage.py 的事。

环境变量覆盖（用于测试隔离与高级用户自定义）：
  MMI_HOME  —— 整体根目录覆盖（默认 ~/.mmi/）

示例：
    from mmi.core import paths
    paths.ensure_dirs()                          # 启动时调一次
    sessions_dir = paths.get_sessions_dir()      # → ~/.mmi/sessions/active/

设计参考：ARCHITECTURE.md §3 数据层 / §4 项目结构。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "get_root",
    "get_sessions_dir",
    "get_trash_dir",
    "get_index_path",
    "get_config_path",
    "get_memory_db_path",
    "get_faiss_index_path",
    "get_faiss_ids_path",
    "ensure_dirs",
]


# ---------------------------------------------------------------------------
# 常量：相对子路径（相对于 root 的固定结构，禁止外部修改）
# ---------------------------------------------------------------------------

_SESSIONS_SUBDIR = "sessions"
_ACTIVE_SUBDIR = "active"
_TRASH_SUBDIR = "trash"
_INDEX_FILENAME = "index.json"
_CONFIG_FILENAME = "config.toml"
_MEMORY_DB_FILENAME = "memory.db"
_FAISS_INDEX_FILENAME = "faiss.index"
_FAISS_IDS_FILENAME = "faiss_ids.json"
_ENV_HOME_OVERRIDE = "MMI_HOME"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_root() -> Path:
    """返回 mmi 数据根目录（默认 ~/.mmi/）。

    解析顺序：
      1. 环境变量 MMI_HOME（绝对路径或可解析为绝对的相对路径）
      2. Path.home() / ".mmi"

    这是纯计算函数 —— 不创建目录、不检查存在性。需要确保目录存在请调
    `ensure_dirs()`。

    Returns:
        Path: 已解析的绝对路径。
    """
    override = os.environ.get(_ENV_HOME_OVERRIDE)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".mmi").resolve()


def get_sessions_dir() -> Path:
    """返回活动会话目录（默认 ~/.mmi/sessions/active/）。

    .session.md 文件存放在这里。会话状态由 frontmatter 中的 `state` 字段
    决定，目录本身不区分 warm / cold —— 只有 trash 单独分目录（见 §10.2）。
    """
    return get_root() / _SESSIONS_SUBDIR / _ACTIVE_SUBDIR


def get_trash_dir() -> Path:
    """返回杂项垃圾桶目录（默认 ~/.mmi/sessions/trash/）。

    被规则预筛或 LLM 判定为"无主题短对话"的会话进入这里，带 TTL 自动清理
    （见 ARCHITECTURE.md §8.1）。
    """
    return get_root() / _SESSIONS_SUBDIR / _TRASH_SUBDIR


def get_index_path() -> Path:
    """返回可选的内存索引持久化文件路径（默认 ~/.mmi/index.json）。

    Phase 1 还不使用，预留给后续 Phase。
    """
    return get_root() / _INDEX_FILENAME


def get_config_path() -> Path:
    """返回用户配置文件路径（默认 ~/.mmi/config.toml）。

    Phase 1 还不使用，预留给后续 Phase（模块禁用列表、默认 LLM 等）。
    """
    return get_root() / _CONFIG_FILENAME


def get_memory_db_path() -> Path:
    """返回向量记忆元数据 SQLite 路径（默认 ~/.mmi/memory.db）。"""
    return get_root() / _MEMORY_DB_FILENAME


def get_faiss_index_path() -> Path:
    """返回 FAISS 索引文件路径（默认 ~/.mmi/faiss.index）。"""
    return get_root() / _FAISS_INDEX_FILENAME


def get_faiss_ids_path() -> Path:
    """返回 FAISS 索引位置 → memory_id 的映射文件（默认 ~/.mmi/faiss_ids.json）。

    FAISS 本身只存向量不存元数据；vector 位置 i 对应哪个 memory_id 需
    单独持久化（顺序追加，永不删除——gc 时同步移除即可）。
    """
    return get_root() / _FAISS_IDS_FILENAME


def ensure_dirs() -> Path:
    """确保数据根目录及标准子目录全部存在（idempotent）。

    创建以下目录（已存在则跳过）：
      - <root>/
      - <root>/sessions/active/
      - <root>/sessions/trash/

    Returns:
        Path: 数据根目录路径（方便链式调用）。
    """
    root = get_root()
    for d in (root, get_sessions_dir(), get_trash_dir()):
        d.mkdir(parents=True, exist_ok=True)
    return root