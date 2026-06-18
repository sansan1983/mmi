"""mmi gc — 清理 trash 目录中超期的会话。"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home
from mmi.core import gc as gc_module
from mmi.core import i18n


def _fmt_entry(entry) -> str:
    age = f"{entry.age_days:.1f}"
    reason = getattr(entry, "reason", "") or ""
    mark = " [DEL]" if getattr(entry, "deleted", False) else ""
    err = f" [ERR: {entry.error}]" if entry.error else ""
    base = f"  {entry.session_id}  age={age}d"
    if reason:
        return base + "  " + reason + mark + err
    return base + mark + err


def cmd_gc(args, mgr) -> int:
    ensure_mmi_home()
    mode = args.gc_only
    ttl = args.ttl_days

    print(i18n.t("gc.title"))
    print(i18n.t("gc.config", ttl=ttl, mode=mode, dry_run=args.dry_run))
    print()

    if mode == "all":
        report = gc_module.gc_all(ttl_days=ttl, dry_run=args.dry_run)
    elif mode == "cold":
        report = gc_module.gc_cold(cold_ttl_days=ttl, dry_run=args.dry_run)
    elif mode == "zombie":
        report = gc_module.gc_zombies(dry_run=args.dry_run)
    else:
        report = gc_module.gc_trash(ttl_days=ttl, dry_run=args.dry_run)

    if not report.entries:
        print(i18n.t("gc.empty"))
        return 0

    header = i18n.t("gc.dry_run") + f" [{mode}]" if args.dry_run else i18n.t("gc.title") + f" [{mode}]:"
    print(header)

    cold_ents = report.cold_entries
    if cold_ents:
        kept = sum(1 for e in cold_ents if not getattr(e, "deleted", False))
        moved = sum(1 for e in cold_ents if getattr(e, "deleted", False))
        print(i18n.t("gc.cold_group", total=len(cold_ents), kept=kept, moved=moved))
        for e in cold_ents:
            print(_fmt_entry(e))

    zombie_ents = report.zombie_entries
    if zombie_ents:
        print(i18n.t("gc.zombie_group", total=len(zombie_ents)))
        for e in zombie_ents:
            print(_fmt_entry(e))

    trash_ents = report.trash_entries
    if trash_ents:
        print(i18n.t("gc.trash_group", total=len(trash_ents)))
        for e in trash_ents:
            print(_fmt_entry(e))

    if not args.dry_run:
        if report.deleted_count:
            print()
            print(i18n.t("gc.deleted", count=report.deleted_count, bytes=report.bytes_freed))
        elif report.kept_count:
            print()
            print(i18n.t("gc.nothing_to_delete", ttl_days=ttl))
    return 0
