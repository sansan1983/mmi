"""mmi inspect — 预览当前上下文裁剪结果（诊断用，不调 LLM）。"""

from __future__ import annotations

import sys

from mmi.cli import ensure_mmi_home
from mmi.core import context as _loader


def cmd_inspect(args, mgr) -> int:
    ensure_mmi_home()
    sid = args.session_id
    try:
        mgr.get(sid)
    except Exception:
        print(f"session not found: {sid}", file=sys.stderr)
        return 1

    user_input = args.text if args.text is not None else ""
    config = _loader.LoaderConfig()
    ctx = _loader.build_context_detailed(sid, user_input, config)
    messages = _loader.compose_messages(ctx, user_input, config, language=args.lang or "zh-CN")
    sys_msg = next((m for m in messages if m.get("role") == "system"), {})
    sys_content = sys_msg.get("content", "") or ""

    print("=" * 60)
    print(f"mmi inspect  |  session={sid}")
    print("=" * 60)
    print(f"  turn_limit    : {config.recent_turns}")
    print(f"  recent_turns  : {len(ctx.recent_turns)} pairs kept")
    print(f"  hit_paragraphs: {len(ctx.hit_turns)} kept")
    print(f"  token_limit   : {config.max_tokens}")
    print(f"  tokens used   : {ctx.estimated_tokens} ({ctx.estimated_tokens/config.max_tokens*100:.1f}%)")
    print()
    print("[system prompt]")
    print(f"  {len(sys_content)} chars  |  {_loader.estimate_tokens([sys_msg])} tokens")
    print(f"  {sys_content[:200]}")

    if ctx.recent_turns:
        print(f"\n[recent turns]  last {len(ctx.recent_turns)} pairs")
        for j, turn in enumerate(ctx.recent_turns):
            role = turn.get("role", "?")
            cont = turn.get("content", "")
            print(f"  #{j+1} [{role}] {len(cont)} chars")
            print(f"    {cont[:150].replace(chr(10), ' ')}")

    if ctx.hit_turns:
        print(f"\n[hit paragraphs]  {len(ctx.hit_turns)}")
        for j, hit in enumerate(ctx.hit_turns):
            sc = hit.get("score", "?")
            cont = hit.get("content", "")
            print(f"  #{j+1}  score={sc}  {len(cont)} chars")
            print(f"    {cont[:120].replace(chr(10), ' ')}")

    if ctx.estimated_tokens > config.max_tokens:
        over = ctx.estimated_tokens - config.max_tokens
        pct = over / config.max_tokens * 100
        print(f"\n[!] WARNING: {over} tokens over limit (+{pct:.1f}% overflow)")
    else:
        headroom = config.max_tokens - ctx.estimated_tokens
        print(f"\n[OK] Within limit (headroom={headroom} tokens)")

    return 0
