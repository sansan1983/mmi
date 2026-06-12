"""mmi tui — 启动 TUI（TypeScript + Ink，通过 Python IPC 通信）。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import portalocker

from mmi.cli import REPO_ROOT, ensure_mmi_home
from mmi.core import paths


def cmd_tui(args, mgr) -> int:
    ensure_mmi_home()

    # 1) node 检查
    node = shutil.which("node")
    if node is None:
        print("Node.js >= 18 未安装。请到 https://nodejs.org/ 安装。", file=sys.stderr)
        return 1

    # 2) 单实例锁：portalocker 非阻塞(LOCK_NB)，抢不到就退出 1
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
        print("已有另一个 `mmi tui` 在运行（lock: {}）。".format(lock_path), file=sys.stderr)
        return 1

    try:
        # 3) dist 检查 / 按需构建
        dist = REPO_ROOT / "tui-ts" / "dist" / "mmi-tui.js"
        if args.build or not dist.exists():
            tui_ts = REPO_ROOT / "tui-ts"
            print("[tui] 安装依赖并构建 bundle（首次 / --build）...", file=sys.stderr)
            npm = shutil.which("npm")
            if npm is None:
                print("npm 未安装，无法构建。", file=sys.stderr)
                return 1
            r1 = subprocess.run([npm, "install"], cwd=str(tui_ts), check=False)
            if r1.returncode != 0:
                print("npm install 失败。", file=sys.stderr)
                return 1
            r2 = subprocess.run([npm, "run", "build"], cwd=str(tui_ts), check=False)
            if r2.returncode != 0:
                print("npm run build 失败。", file=sys.stderr)
                return 1

        # 4) 启动 TUI（注入 PYTHON 路径让 IPC 能回拉）
        tui_js = dist
        env = os.environ.copy()
        env["PYTHON"] = str(subprocess.list2cmdline([shutil.which("python")]))
        proc = subprocess.run(
            [str(node), str(tui_js)],
            cwd=str(REPO_ROOT),
            env=env,
        )
        return proc.returncode

    finally:
        lock.release()