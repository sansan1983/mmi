"""mmi export — 导出会话为 JSON 或 Markdown。"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from mmi.cli import ensure_mmi_home, require_session
from mmi.core import i18n
from mmi.core.manager import SessionManager


def cmd_export(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    sess, code = require_session(args.session_id, mgr)
    if code:
        return code
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

    from mmi.core.storage import atomic_write

    output = args.output
    if args.format == "json" or output.endswith(".json"):
        indent = None if args.compact else 2
        content_out = json.dumps(data, indent=indent, ensure_ascii=False)
        atomic_write(Path(output), content_out)
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
        atomic_write(Path(output), "\n".join(lines_md))

    print(i18n.t("export.success", turns=len(data['turns']), output=output))
    return 0
