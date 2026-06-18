"""mmi info — 显示单个会话的完整详情。"""

from __future__ import annotations

from argparse import Namespace

from mmi.cli import ensure_mmi_home, require_session
from mmi.core import i18n, storage
from mmi.core.manager import SessionManager


def cmd_info(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    sess, code = require_session(args.session_id, mgr)
    if code:
        return code
    meta = sess.meta
    turns = storage.count_user_turns(sess.body)
    print(i18n.t("info.session_id", id=meta.session_id))
    print(i18n.t("info.title", title=meta.title))
    print(i18n.t("info.agent", id=meta.agent_id))
    print(i18n.t("info.state", state=meta.state))
    print(i18n.t("info.heat", heat=meta.heat))
    print(i18n.t("info.created", created=meta.created_at))
    print(i18n.t("info.updated", updated=meta.updated_at))
    print(i18n.t("info.last_access", last_access=meta.last_access))
    print(i18n.t("info.access_count", n=meta.access_count))
    print(i18n.t("info.user_turns", n=turns))
    if meta.trashed_at:
        print(i18n.t("info.trash_yes"))
    else:
        print(i18n.t("info.trash_no"))
    if meta.cold_since:
        print(i18n.t("info.cold_since", ts=meta.cold_since))
    if meta.summary:
        print(i18n.t("info.summary", text=meta.summary))
    else:
        print(i18n.t("info.summary_empty"))
    keywords = ", ".join(meta.keywords)
    if keywords:
        print(i18n.t("info.keywords", keywords=keywords))
    else:
        print(i18n.t("info.keywords_empty"))
    return 0
