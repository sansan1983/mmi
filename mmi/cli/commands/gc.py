"""mmi gc — 清理 trash 目录中超期的会话。"""

from __future__ import annotations

from mmi.cli import ensure_mmi_home
from mmi.core import gc as gc_module
from mmi.core import i18n


def _fmt_entry(entry) -> str:
    age = "{:.1f}".format(entry.age_days)
    reason = getattr(entry, "reason", "") or ""
    mark = " [DEL]" if getattr(entry, "deleted", False) else ""
    err = " [ERR: {}]".format(entry.error) if entry.error else ""
    base = "  {}  age={}d".format(entry.session_id, age)
    if reason:
        return base + "  " + reason + mark + err
    return base + mark + err


def cmd_gc(args, mgr) -> int:
    ensure_mmi_home()
    mode = args.gc_only
    ttl = args.ttl_days

    print(i18n.t("gc.title"))
    print("  ttl={}d  mode={}  dry-run={}".format(ttl, mode, args.dry_run))
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

    header = i18n.t("gc.dry_run") + " [{}]".format(mode) if args.dry_run else i18n.t("gc.title") + " [{}]:".format(
        mode
    )
    print(header)

    cold_ents = report.cold_entries
    if cold_ents:
        kept = sum(1 for e in cold_ents if not getattr(e, "deleted", False))
        moved = sum(1 for e in cold_ents if getattr(e, "deleted", False))
        print("\n  [cold] {} total  kept={}  moved->trash={}".format(len(cold_ents), kept, moved))
        for e in cold_ents:
            print(_fmt_entry(e))

    zombie_ents = report.zombie_entries
    if zombie_ents:
        print("\n  [zombie] {} total".format(len(zombie_ents)))
        for e in zombie_ents:
            print(_fmt_entry(e))

    trash_ents = report.trash_entries
    if trash_ents:
        print("\n  [trash] {} total".format(len(trash_ents)))
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