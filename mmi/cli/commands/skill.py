"""mmi skill — 管理 Skill（列表/搜索/创建）。"""

from __future__ import annotations

from datetime import datetime, timezone

from mmi.agent.skill import Skill, SkillLibrary, SkillType
from mmi.cli import ensure_mmi_home


def cmd_skill(args, mgr) -> int:
    ensure_mmi_home()
    sub = getattr(args, "skill_cmd", None)
    if sub is None:
        print("usage: mmi skill {list|search|create}")
        return 1

    lib = SkillLibrary.get_instance()

    if sub == "list":
        skills = list(lib._skills.values()) if hasattr(lib, "_skills") else []
        if not skills:
            print("无 Skill。试用 `mmi skill create` 添加。")
            return 0
        print(f"共 {len(skills)} 个 Skill:\n")
        for s in skills:
            print(f"  [{s.skill_id:20s}] {s.name}  ({s.skill_type.name})")
            print(f"      {s.apply_scene}")
        return 0

    if sub == "search":
        query = args.query
        matches = lib.match(query, limit=10)
        if not matches:
            print(f"未找到匹配 {query!r} 的 Skill")
            return 0
        print(f"找到 {len(matches)} 个匹配:\n")
        for s in matches:
            print(f"  [{s.skill_id:20s}] {s.name}  ({s.skill_type.name})")
            print(f"      {s.apply_scene[:60]}")
        return 0

    if sub == "create":
        now = datetime.now(timezone.utc).isoformat()
        tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
        skill = Skill(
            skill_id=args.skill_id,
            name=args.name,
            skill_type=SkillType.BUILTIN,
            content=args.content,
            apply_scene=args.apply_scene,
            tags=tags,
            created_at=now,
            updated_at=now,
        )
        try:
            lib.create(skill)
            print(f"[✓] Skill {args.skill_id!r} 已创建")
            return 0
        except ValueError as e:
            print(f"[!] {e}")
            return 1

    print(f"unknown skill subcommand: {sub}")
    return 1