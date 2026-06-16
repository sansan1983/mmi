"""mmi.__main__ — 支持 `python -m mmi` 入口。

当用户运行 `python -m mmi` 时，Python 会自动执行本模块。
"""

from mmi.cli.main import main

raise SystemExit(main())