"""mmi archive — 归档会话到 trash。"""

from __future__ import annotations

from argparse import Namespace

from mmi.cli import ensure_mmi_home, require_session
from mmi.core import i18n
from mmi.core.manager import SessionManager


def cmd_archive(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    _, code = require_session(args.session_id, mgr, code=2, err_key="archive.unknown_session")
    if code:
        return code
    mgr.archive(args.session_id)
    print(i18n.t("archive.success", session_id=args.session_id))
    return 0
