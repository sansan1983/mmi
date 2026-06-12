"""mmi.cli.commands —— 所有子命令实现。

每个 cmd_*.py 对应一个 mmi <subcommand>。
导入顺序无关（避免循环 import）。
"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home  # noqa: F401