"""mmi update — 增量更新会话热度（不触发 LLM）。"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home
from mmi.core import i18n


def cmd_update(args, mgr) -> int:
    ensure_mmi_home()
    try:
        mgr.touch(args.session_id)
        print(i18n.t("update.success", session_id=args.session_id))
    except Exception as e:
        print(i18n.t("update.failed", error=str(e)))
        return 1
    return 0
