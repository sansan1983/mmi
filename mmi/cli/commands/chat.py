"""mmi chat — 继续指定会话的聊天 loop。"""

from __future__ import annotations

import sys

from mmi.cli import ensure_mmi_home
from mmi.core import i18n
from mmi.core import storage


def cmd_chat(args, mgr) -> int:
    ensure_mmi_home()
    sid = args.session_id

    try:
        mgr.get(sid)
    except storage.SessionNotFound:
        print(i18n.t("chat.unknown_session", session_id=sid), file=sys.stderr)
        return 1

    # --inspect mode: preview prompt before entering loop
    if args.inspect:
        from mmi.core import context as _loader

        try:
            mgr.get(sid)
        except Exception:
            print(f"session not found: {sid}", file=sys.stderr)
            return 1
        meta = storage.read_meta(sid)
        config = _loader.LoaderConfig()
        ctx = _loader.build_context_detailed(sid, "", config)
        messages = _loader.compose_messages(ctx, "", config, language=args.lang or "zh-CN")
        sys_msg = next((m for m in messages if m.get("role") == "system"), {})
        sys_content = sys_msg.get("content", "") or ""
        print("=" * 60)
        print(f"mmi chat --inspect  |  session={sid}")
        print("=" * 60)
        print(f"  title          : {meta.title}")
        print(f"  state          : {meta.state}")
        print(f"  recent_turns   : {len(ctx.recent_turns)} pairs")
        print(f"  hit_paragraphs : {len(ctx.hit_turns)} kept")
        print(f"  token_limit    : {config.max_tokens}")
        print(f"  tokens used    : {ctx.estimated_tokens} ({ctx.estimated_tokens/config.max_tokens*100:.1f}%)")
        print()
        print("[system prompt]")
        print(f"  {len(sys_content)} chars  |  {_loader.estimate_tokens([sys_msg])} tokens")
        print("  %s" % sys_content[:200])
        print()
        if ctx.estimated_tokens > config.max_tokens * 0.8:
            print(f"  [WARN] Within {int(config.max_tokens*0.8)} tokens (80%), consider compacting")
        else:
            print(f"  [OK] {config.max_tokens - ctx.estimated_tokens} tokens headroom")
        print()
        print(f"Use 'mmi chat {sid}' to start the conversation loop")
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