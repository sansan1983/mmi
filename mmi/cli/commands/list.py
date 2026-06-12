"""mmi list — 列出最近会话。"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home
from mmi.core import i18n


def cmd_list(args, mgr) -> int:
    ensure_mmi_home()
    sessions = mgr.list_sessions(limit=args.limit)
    if args.state != "all":
        sessions = [s for s in sessions if s.state == args.state]
    if not sessions:
        print(i18n.t("list.empty"))
        return 0
    print(i18n.t("list.title"))
    if args.state != "all":
        print("  [filter: state={}]".format(args.state))
    for i, s in enumerate(sessions, 1):
        if s.title:
            print(i18n.t("list.entry", index=i, title=s.title, heat=s.heat, state=s.state))
        else:
            print(i18n.t("list.entry.unnamed", index=i, heat=s.heat, state=s.state))
    return 0