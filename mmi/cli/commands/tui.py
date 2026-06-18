"""mmi tui — 启动 TUI v3（Python Textual）。"""

from __future__ import annotations

from argparse import Namespace

import portalocker

from mmi.cli import ensure_mmi_home
from mmi.core import paths
from mmi.core.manager import SessionManager


def cmd_tui(args: Namespace, mgr: SessionManager) -> int:
    """启动 TUI v3（mmi.tui_v3.run_tui）。"""
    ensure_mmi_home()

    # 单实例锁
    paths.ensure_dirs()
    lock_path = paths.get_root() / "run" / "tui.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = portalocker.Lock(
        str(lock_path),
        mode="w",
        timeout=0.0,
        flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
    )
    try:
        lock.acquire()
    except portalocker.LockException:
        print(f"[tui] 已有另一个 TUI 在运行（lock: {lock_path}）。", file=__import__('sys').stderr)
        return 1

    try:
        from mmi.tui_v3 import run_tui
        return run_tui()
    except KeyboardInterrupt:
        return 0
    finally:
        lock.release()
