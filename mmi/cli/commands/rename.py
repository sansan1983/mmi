"""mmi rename — 重命名会话标题。"""

from __future__ import annotations

import sys
from argparse import Namespace

from mmi.cli import ensure_mmi_home, require_session
from mmi.core import i18n, storage
from mmi.core.manager import SessionManager


def cmd_rename(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    sess, code = require_session(args.session_id, mgr, code=2)
    if code:
        return code

    # Check duplicate title unless --force
    if not args.force:
        for sid in storage.list_session_ids():
            if sid == args.session_id:
                continue
            try:
                other = storage.read_session(sid)
                if other.meta.title == args.title:
                    print(
                        i18n.t("rename.dup", title=args.title, session_id=other.session_id),
                        file=sys.stderr,
                    )
                    print(i18n.t("rename.dup_hint"), file=sys.stderr)
                    return 1
            except Exception:
                pass

    old_title = sess.meta.title
    sess.meta.title = args.title
    storage.write_session(sess)
    print(i18n.t("rename.success", old=old_title, new=args.title))
    return 0
