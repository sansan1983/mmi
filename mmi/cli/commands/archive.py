"""mmi archive — 归档会话到 trash。"""

from __future__ import annotations

import sys

from mmi.cli import ensure_mmi_home
from mmi.core import manager as mgr_module
from mmi.core import i18n


def cmd_archive(args, mgr) -> int:
    ensure_mmi_home()
    try:
        mgr.archive(args.session_id)
    except mgr_module.SessionNotFound:
        print(i18n.t("archive.unknown_session", session_id=args.session_id), file=sys.stderr)
        return 2
    print(i18n.t("archive.success", session_id=args.session_id))
    return 0