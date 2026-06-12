"""mmi info — 显示单个会话的完整详情。"""

from __future__ import annotations

import sys

from mmi.cli import ensure_mmi_home
from mmi.core import storage


def cmd_info(args, mgr) -> int:
    ensure_mmi_home()
    try:
        sess = storage.read_session(args.session_id)
    except storage.SessionNotFound:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return 1
    meta = sess.meta
    turns = storage.count_user_turns(sess.body)
    print(f"  Session ID : {meta.session_id}")
    print(f"  Title      : {meta.title}")
    print(f"  Agent      : {meta.agent_id}")
    print(f"  State      : {meta.state}")
    print(f"  Heat       : {meta.heat:.4f}")
    print(f"  Created    : {meta.created_at}")
    print(f"  Updated    : {meta.updated_at}")
    print(f"  Last Access: {meta.last_access}")
    print(f"  Access Count: {meta.access_count}")
    print(f"  User Turns : {turns}")
    print(f"  Trash      : {'yes' if meta.trashed_at else 'no'}")
    if meta.cold_since:
        print(f"  Cold Since : {meta.cold_since}")
    print(f"  Summary    : {meta.summary or '(none)'}")
    print(f"  Keywords   : {', '.join(meta.keywords) or '(none)'}")
    return 0