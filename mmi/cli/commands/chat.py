"""mmi chat — 继续指定会话的聊天 loop。"""

from __future__ import annotations

from argparse import Namespace

from mmi.cli import ensure_mmi_home, require_session
from mmi.core import i18n, storage
from mmi.core.manager import SessionManager


def cmd_chat(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    sid = args.session_id

    _, code = require_session(sid, mgr, err_key="chat.unknown_session")
    if code:
        return code

    # --inspect mode: preview prompt before entering loop
    if args.inspect:
        from mmi.core import context as _loader

        meta = storage.read_meta(sid)
        config = _loader.LoaderConfig()
        ctx = _loader.build_context_detailed(sid, "", config)
        messages = _loader.compose_messages(ctx, "", config, language=args.lang or "zh-CN")
        sys_msg = next((m for m in messages if m.get("role") == "system"), {})
        sys_content = sys_msg.get("content", "") or ""
        print("=" * 60)
        print(i18n.t("chat.inspect.banner", sid=sid))
        print("=" * 60)
        print(i18n.t("chat.inspect.title", title=meta.title))
        print(i18n.t("chat.inspect.state", state=meta.state))
        print(i18n.t("chat.inspect.recent_turns", n=len(ctx.recent_turns)))
        print(i18n.t("chat.inspect.hit_paragraphs", n=len(ctx.hit_turns)))
        print(i18n.t("chat.inspect.token_limit", n=config.max_tokens))
        print(i18n.t("chat.inspect.tokens_used", used=ctx.estimated_tokens, pct=ctx.estimated_tokens / config.max_tokens * 100))
        print()
        print(i18n.t("chat.inspect.system_prompt_label"))
        print(i18n.t("chat.inspect.system_prompt_stats", chars=len(sys_content), tokens=_loader.estimate_tokens([sys_msg])))
        print(i18n.t("chat.inspect.system_prompt_content", content=sys_content[:200]))
        print()
        if ctx.estimated_tokens > config.max_tokens * 0.8:
            print(i18n.t("chat.inspect.warn_80pct", n=int(config.max_tokens * 0.8)))
        else:
            print(i18n.t("chat.inspect.ok_headroom", n=config.max_tokens - ctx.estimated_tokens))
        print()
        print(i18n.t("chat.inspect.hint", sid=sid))
        return 0

    print(i18n.t("chat.welcome", session_id=sid))
    print(i18n.t("chat.echo_disabled"))
    print(i18n.t("chat.exit_hint"))
    print()

    try:
        while True:
            try:
                line = input(i18n.t("chat.prompt"))
            except EOFError:
                print()
                break
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ("q", "quit", "exit"):
                break

            try:
                result = mgr.chat(sid, stripped)
            except storage.SessionNotFound:
                print(i18n.t("chat.session_trashed"))
                break
            print(i18n.t("chat.assistant_said", content=result.reply))
            if result.trashed:
                print(i18n.t("chat.moved_to_trash", reason=result.trashed_reason))
            if result.title_updated:
                print(i18n.t("chat.title_updated"))
            if result.summary_updated:
                try:
                    meta = storage.read_meta(sid)
                    print(i18n.t("chat.summary_updated", version=meta.summary_version))
                except storage.SessionNotFound:
                    pass
            if result.context_truncated:
                print(i18n.t("chat.context_truncated"))
            print()
    except KeyboardInterrupt:
        print()

    return 0
