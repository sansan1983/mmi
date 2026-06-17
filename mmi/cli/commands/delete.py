"""mmi delete — 硬删会话（不可恢复）。"""

from __future__ import annotations

import sys

from mmi.cli import ensure_mmi_home
from mmi.core import i18n
from mmi.core import manager as mgr_module


def cmd_delete(args, mgr) -> int:
    ensure_mmi_home()
    try:
        mgr.delete(args.session_id)
    except mgr_module.SessionNotFound:
        print(i18n.t("delete.unknown_session", session_id=args.session_id), file=sys.stderr)
        return 2
    print(i18n.t("delete.success", session_id=args.session_id))
    return 0
