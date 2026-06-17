"""mmi new — 新建会话。"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home
from mmi.core import i18n


def cmd_new(args, mgr) -> int:
    ensure_mmi_home()
    title = args.title or "untitled"
    sid = mgr.create(title=title)
    print(i18n.t("new.success", session_id=sid))
    print(i18n.t("new.success.hint", session_id=sid))
    return 0
