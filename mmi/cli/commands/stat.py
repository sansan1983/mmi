"""mmi stat — 显示会话统计。"""

from __future__ import annotations

from argparse import Namespace
from collections import Counter

from mmi.cli import ensure_mmi_home
from mmi.core import i18n, storage
from mmi.core.manager import SessionManager


def cmd_stat(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    all_sids = storage.list_session_ids()
    trash_sids = storage.list_trash_ids()
    all_meta = [storage.read_meta(sid) for sid in all_sids]
    state_counts = Counter(s.state for s in all_meta)
    total_size = sum(
        storage.session_path(sid).stat().st_size
        for sid in all_sids
        if storage.session_path(sid).exists()
    )
    total = len(all_meta)
    print(i18n.t("stat.title"))
    print(i18n.t("stat.active", n=total))
    for state in ["active", "warm", "cold", "zombie"]:
        cnt = state_counts.get(state, 0)
        pct = cnt / total * 100 if total else 0
        print(i18n.t("stat.state", state=state, count=cnt, pct=pct))
    print(i18n.t("stat.trash", n=len(trash_sids)))
    print(i18n.t("stat.total_size", size=total_size / 1024 / 1024))
    return 0
