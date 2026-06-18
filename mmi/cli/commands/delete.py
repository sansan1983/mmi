"""mmi delete — 硬删会话（不可恢复）。"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home, require_session
from mmi.core import i18n


def cmd_delete(args, mgr) -> int:
    ensure_mmi_home()
    _, code = require_session(args.session_id, mgr, code=2, err_key="delete.unknown_session")
    if code:
        return code
    mgr.delete(args.session_id)
    print(i18n.t("delete.success", session_id=args.session_id))
    return 0
