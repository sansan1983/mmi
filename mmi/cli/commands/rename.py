"""mmi rename — 重命名会话标题。"""

from __future__ import annotations

import sys

from mmi.cli import ensure_mmi_home
from mmi.core import storage


def cmd_rename(args, mgr) -> int:
    ensure_mmi_home()
    try:
        sess = storage.read_session(args.session_id)
    except storage.SessionNotFound:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"{e}", file=sys.stderr)
        return 1

    # Check duplicate title unless --force
    if not args.force:
        for sid in storage.list_session_ids():
            if sid == args.session_id:
                continue
            try:
                other = storage.read_session(sid)
                if other.meta.title == args.title:
                    print(
                        f"title already in use: '{args.title}' (session: {other.meta.session_id})",
                        file=sys.stderr,
                    )
                    print("use --force to override", file=sys.stderr)
                    return 1
            except Exception:
                pass

    old_title = sess.meta.title
    sess.meta.title = args.title
    storage.write_session(sess)
    print(f"renamed: '{old_title}' → '{args.title}'")
    return 0