"""mmi delete — 硬删会话（不可恢复）。"""

from __future__ import annotations

from argparse import Namespace

from mmi.cli import ensure_mmi_home, require_session
from mmi.core import i18n
from mmi.core.manager import SessionManager


def cmd_delete(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    _, code = require_session(args.session_id, mgr, code=2, err_key="delete.unknown_session")
    if code:
        return code
    mgr.delete(args.session_id)
    print(i18n.t("delete.success", session_id=args.session_id))
    return 0
