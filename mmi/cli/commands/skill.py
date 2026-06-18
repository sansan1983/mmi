"""mmi skill — 管理 Skill（列表/搜索/创建）。"""

from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime

from mmi.agent.skill import Skill, SkillLibrary, SkillType
from mmi.cli import dispatch_subcommand, ensure_mmi_home
from mmi.core import i18n
from mmi.core.manager import SessionManager


def _skill_list() -> int:
    lib = SkillLibrary.get_instance()
    skills = list(lib._skills.values()) if hasattr(lib, "_skills") else []
    if not skills:
        print(i18n.t("skill.list.empty"))
        return 0
    print(i18n.t("skill.list.header", count=len(skills)))
    for s in skills:
        print(i18n.t("skill.list.entry", skill_id=s.skill_id, name=s.name, type=s.skill_type.name, scene=s.apply_scene))
    return 0


def _skill_search(args: Namespace) -> int:
    lib = SkillLibrary.get_instance()
    query = args.query
    matches = lib.match(query, limit=10)
    if not matches:
        print(i18n.t("skill.search.empty", query=query))
        return 0
    print(i18n.t("skill.search.found", count=len(matches)))
    for s in matches:
        print(i18n.t("skill.search.entry", skill_id=s.skill_id, name=s.name, type=s.skill_type.name, scene=s.apply_scene[:60]))
    return 0


def _skill_create(args: Namespace) -> int:
    lib = SkillLibrary.get_instance()
    now = datetime.now(UTC).isoformat()
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
        print(i18n.t("skill.create.success", id=args.skill_id))
        return 0
    except ValueError as e:
        print(i18n.t("skill.create.error", error=str(e)))
        return 1


def cmd_skill(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    return dispatch_subcommand(
        args,
        "skill_cmd",
        {
            "list": _skill_list,
            "search": lambda: _skill_search(args),
            "create": lambda: _skill_create(args),
        },
        usage="usage: mmi skill {list|search|create}",
    )
