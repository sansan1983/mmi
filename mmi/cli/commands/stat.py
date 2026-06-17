"""mmi stat — 显示会话统计。"""

from __future__ import annotations

from collections import Counter

from mmi.cli import ensure_mmi_home
from mmi.core import storage


def cmd_stat(args, mgr) -> int:
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
    print("MMI Statistics")
    print(f"  active:    {total:4d}")
    for state in ["active", "warm", "cold", "zombie"]:
        cnt = state_counts.get(state, 0)
        pct = cnt / total * 100 if total else 0
        print(f"    {state}: {cnt:4d} ({pct:.1f}%)")
    print(f"  trash:     {len(trash_sids):4d}")
    print(f"  total size: {total_size / 1024 / 1024:.2f} MB")
    return 0
