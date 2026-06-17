"""mmi memory — 跨会话记忆子命令：search / count / clear。"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home
from mmi.core import memory


def cmd_memory(args, mgr) -> int:
    ensure_mmi_home()
    sub = getattr(args, "memory_cmd", None)
    if sub is None:
        print("usage: mmi memory {search|count|clear}")
        return 1

    if sub == "count":
        n = memory.memory_count()
        print(f"当前记忆条数: {n}")
        return 0

    if sub == "clear":
        if not args.yes:
            print("[!] 这会清空所有跨会话记忆。继续请加 --yes")
            return 1
        memory.clear_memories()
        print("[✓] 记忆已清空")
        return 0

    if sub == "search":
        query = " ".join(args.query).strip()
        if not query:
            print("usage: mmi memory search <关键词...>")
            return 1
        hits = memory.search_semantic(query, top_k=args.top_k)
        if not hits:
            print(f"未找到与「{query}」相关的记忆。")
            return 0
        print(f"找到 {len(hits)} 条与「{query}」相关的记忆:\n")
        for i, h in enumerate(hits, 1):
            print(f"  [{i}] {h.memory_id}")
            print(f"      标题:   {h.title or '(无)'}")
            if h.conclusion:
                print(f"      结论:   {h.conclusion[:120]}")
            print(f"      来源:   session {h.session_id} (turns={h.turns_at})")
            print(f"      时间:   {h.created_at}")
            print()
        return 0

    print(f"unknown memory subcommand: {sub}")
    return 1
