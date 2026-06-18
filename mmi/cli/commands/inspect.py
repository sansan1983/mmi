"""mmi inspect — 预览当前上下文裁剪结果（诊断用，不调 LLM）。"""

from __future__ import annotations

from argparse import Namespace

from mmi.cli import ensure_mmi_home, require_session
from mmi.core import context as _loader
from mmi.core import i18n
from mmi.core.manager import SessionManager


def cmd_inspect(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    sid = args.session_id
    _, code = require_session(sid, mgr)
    if code:
        return code

    user_input = args.text if args.text is not None else ""
    config = _loader.LoaderConfig()
    ctx = _loader.build_context_detailed(sid, user_input, config)
    messages = _loader.compose_messages(ctx, user_input, config, language=args.lang or "zh-CN")
    sys_msg = next((m for m in messages if m.get("role") == "system"), {})
    sys_content = sys_msg.get("content", "") or ""

    print("=" * 60)
    print(i18n.t("inspect.banner", sid=sid))
    print("=" * 60)
    print(i18n.t("inspect.turn_limit", n=config.recent_turns))
    print(i18n.t("inspect.recent_turns", n=len(ctx.recent_turns)))
    print(i18n.t("inspect.hit_paragraphs", n=len(ctx.hit_turns)))
    print(i18n.t("inspect.token_limit", n=config.max_tokens))
    print(i18n.t("inspect.tokens_used", used=ctx.estimated_tokens, pct=ctx.estimated_tokens / config.max_tokens * 100))
    print()
    print(i18n.t("inspect.system_prompt_label"))
    print(i18n.t("inspect.system_prompt_stats", chars=len(sys_content), tokens=_loader.estimate_tokens([sys_msg])))
    print(i18n.t("inspect.system_prompt_content", content=sys_content[:200]))

    if ctx.recent_turns:
        print()
        print(i18n.t("inspect.recent_turns_label", n=len(ctx.recent_turns)))
        for j, turn in enumerate(ctx.recent_turns):
            role = turn.get("role", "?")
            cont = turn.get("content", "")
            print(i18n.t("inspect.recent_turn_entry", n=j + 1, role=role, chars=len(cont)))
            print(i18n.t("inspect.recent_turn_content", content=cont[:150].replace(chr(10), " ")))

    if ctx.hit_turns:
        print()
        print(i18n.t("inspect.hit_paragraphs_label", n=len(ctx.hit_turns)))
        for j, hit in enumerate(ctx.hit_turns):
            sc = hit.get("score", "?")
            cont = hit.get("content", "")
            print(i18n.t("inspect.hit_paragraph_entry", n=j + 1, score=sc, chars=len(cont)))
            print(i18n.t("inspect.hit_paragraph_content", content=cont[:120].replace(chr(10), " ")))

    print()
    if ctx.estimated_tokens > config.max_tokens:
        over = ctx.estimated_tokens - config.max_tokens
        pct = over / config.max_tokens * 100
        print(i18n.t("inspect.warn_overflow", over=over, pct=pct))
    else:
        headroom = config.max_tokens - ctx.estimated_tokens
        print(i18n.t("inspect.ok_headroom", headroom=headroom))

    return 0
