"""mmi update — 增量更新会话热度（不触发 LLM）。"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home


def cmd_update(args, mgr) -> int:
    ensure_mmi_home()
    try:
        mgr.touch(args.session_id)
        print(f"[✓] 会话 {args.session_id} 已更新热度")
    except Exception as e:
        print(f"[✗] 更新失败: {e}")
        return 1
    return 0