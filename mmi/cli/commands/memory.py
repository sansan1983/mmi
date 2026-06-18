"""mmi memory — 跨会话记忆子命令：search / count / clear。"""

from __future__ import annotations

from mmi.cli import dispatch_subcommand, ensure_mmi_home
from mmi.core import i18n, memory


def _memory_count() -> int:
    n = memory.memory_count()
    print(i18n.t("memory.count.format", n=n))
    return 0


def _memory_clear(args) -> int:
    if not args.yes:
        print(i18n.t("memory.clear.confirm"))
        return 1
    memory.clear_memories()
    print(i18n.t("memory.clear.success"))
    return 0


def _memory_search(args) -> int:
    query = " ".join(args.query).strip()
    if not query:
        print(i18n.t("memory.search.usage"))
        return 1
    hits = memory.search_semantic(query, top_k=args.top_k)
    if not hits:
        print(i18n.t("memory.search.empty", query=query))
        return 0
    print(i18n.t("memory.search.found_header", count=len(hits), query=query))
    for i, h in enumerate(hits, 1):
        print(i18n.t("memory.search.entry.id", i=i, memory_id=h.memory_id))
        title_key = "memory.search.entry.title_empty" if not h.title else "memory.search.entry.title"
        title_params = {} if not h.title else {"title": h.title}
        print(i18n.t(title_key, **title_params))
        if h.conclusion:
            print(i18n.t("memory.search.entry.conclusion", text=h.conclusion[:120]))
        print(i18n.t("memory.search.entry.source", session_id=h.session_id, turns=h.turns_at))
        print(i18n.t("memory.search.entry.time", created_at=h.created_at))
        print()
    return 0


def cmd_memory(args, mgr) -> int:
    ensure_mmi_home()
    return dispatch_subcommand(
        args,
        "memory_cmd",
        {
            "count": _memory_count,
            "clear": lambda: _memory_clear(args),
            "search": lambda: _memory_search(args),
        },
        usage="usage: mmi memory {search|count|clear}",
    )
