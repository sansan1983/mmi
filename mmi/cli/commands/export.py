"""mmi export — 导出会话为 JSON 或 Markdown。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mmi.cli import ensure_mmi_home
from mmi.core import storage


def cmd_export(args, mgr) -> int:
    ensure_mmi_home()
    try:
        sess = storage.read_session(args.session_id)
    except storage.SessionNotFound:
        print(f"session not found: {args.session_id}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"{e}", file=sys.stderr)
        return 1
    meta = sess.meta

    data = {
        "session_id": meta.session_id,
        "title": meta.title,
        "agent_id": meta.agent_id,
        "created_at": str(meta.created_at),
        "updated_at": str(meta.updated_at),
        "last_access": str(meta.last_access),
        "access_count": meta.access_count,
        "heat": round(meta.heat, 4),
        "state": meta.state,
        "turns": [],
    }

    for line in sess.body.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("## "):
            role = "user"
            content = stripped[3:].strip()
        elif stripped.startswith("### "):
            role = "assistant"
            content = stripped[4:].strip()
        else:
            continue
        data["turns"].append({"role": role, "content": content})

    output = args.output
    if args.format == "json" or output.endswith(".json"):
        indent = None if args.compact else 2
        content_out = json.dumps(data, indent=indent, ensure_ascii=False)
        Path(output).write_text(content_out, encoding="utf-8")
    else:
        lines_md = [
            f"# {meta.title or 'Untitled Session'}",
            "",
            f"**Session ID**: `{meta.session_id}`  |  **Agent**: {meta.agent_id}  |  **State**: {meta.state}",
            f"**Created**: {meta.created_at.date()}  |  **Updated**: {meta.updated_at.date()}  |  **Heat**: {meta.heat:.4f}",
            "",
        ]
        for t in data["turns"]:
            lines_md.append(f"## {t['role'].capitalize()}")
            lines_md.append(t["content"])
            lines_md.append("")
        Path(output).write_text("\n".join(lines_md), encoding="utf-8")

    print(f"exported {len(data['turns'])} turns to {output}")
    return 0
