"""mmi doctor — 系统诊断工具。

参考 OMP ctx-doctor 设计（ANALYSIS_OMP.md §四），
直接调用 mmi.core 模块，零配置文件，零新依赖。

用法: mmi doctor
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

# 确保能找到 mmi（未通过 pip install 安装时）
_mmi_root = os.environ.get("MMI_ROOT", "/home/ubuntu/mmi-fusion")
if _mmi_root not in sys.path:
    sys.path.insert(0, _mmi_root)

from mmi.core import storage as storage_mod
from mmi.core import heat as heat_mod
from mmi.core import gc as gc_mod
from mmi.core import paths as paths_mod


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def parse_dt(val: str | datetime) -> datetime:
    """Parse ISO timestamp string or datetime to aware datetime (UTC)."""
    if isinstance(val, datetime):
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val
    # 兼容 '2026-06-02T19:48:54.177Z' 和 '2026-06-02T19:48:54.177'
    s = val.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def banner(title: str) -> None:
    sep = "=" * 62
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)


# ---------------------------------------------------------------------------
# 检查 1: 模块导入
# ---------------------------------------------------------------------------

def check_imports() -> dict:
    """检查所有核心模块是否可导入。"""
    checks = {}
    modules = [
        ("mmi.core.session", "session"),
        ("mmi.core.heat", "heat"),
        ("mmi.core.storage", "storage"),
        ("mmi.core.gc", "gc"),
        ("mmi.core.summarizer", "summarizer"),
        ("mmi.core.loader", "loader"),
        ("mmi.core.manager", "manager"),
    ]
    ok, fail = 0, 0
    print(f"\n[1/5] Module imports...")
    for mod_name, label in modules:
        try:
            __import__(mod_name)
            print(f"  [OK] {label}")
            checks[label] = True
            ok += 1
        except Exception as e:
            print(f"  [FAIL] {mod_name}: {e}")
            checks[label] = False
            fail += 1
    return {"ok": ok, "fail": fail, "checks": checks}


# ---------------------------------------------------------------------------
# 检查 2: 会话完整性
# ---------------------------------------------------------------------------

def check_sessions() -> dict:
    """遍历所有会话，检查文件完整性和状态一致性。"""
    results = {"active": 0, "warm": 0, "cold": 0, "zombie": 0, "corrupt": 0, "trash": 0}
    sids = storage_mod.list_session_ids()
    print(f"\n[2/5] Session integrity...")
    print(f"  Sessions: {len(sids)} total", end="")
    for label in ("active", "warm", "cold", "zombie", "corrupt"):
        print(f" | {label}={results[label]}", end="")
    print()

    for sid in sids:
        try:
            meta = storage_mod.read_meta(sid)
            session = storage_mod.read_session(sid)
            # state 字段可能是 Enum 或 str；统一转成字符串比较
            raw_state = meta.state
            if hasattr(raw_state, "value"):
                state = raw_state.value.lower()
            else:
                state = str(raw_state).lower()
            if state in results:
                results[state] += 1
            else:
                results["corrupt"] += 1

            # 基本完整性：非空 body
            if session.body and len(session.body.strip()) > 0:
                print(f"  [✓][{state:6s}] {sid[:12]} | "
                      f"{meta.title or 'untitled'} | heat={meta.heat:.1f} | "
                      f"body={len(session.body or '')}B | summary={meta.summary[:20] if meta.summary else '(stub)'}")
            else:
                print(f"  [⚠][{state:6s}] {sid[:12]} | empty body")

        except storage_mod.SessionNotFound:
            print(f"  [✗] {sid[:12]}: missing session file")
            results["corrupt"] += 1
        except Exception as e:
            print(f"  [✗] {sid[:12]}: {e}")
            results["corrupt"] += 1

    return results


# ---------------------------------------------------------------------------
# 检查 3: 文件系统
# ---------------------------------------------------------------------------

def check_filesystem() -> dict:
    """检查关键目录和文件。"""
    print(f"\n[3/5] File system...")
    results = {}
    for key, getter in [
        ("sessions", paths_mod.get_sessions_dir),
        ("trash", paths_mod.get_trash_dir),
    ]:
        try:
            path = getter()
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0
            status = "OK" if path.exists() else "MISSING"
            print(f"  [{status}] {key}: {path} ({size:,} bytes)")
            results[key] = {"path": str(path), "exists": path.exists(), "bytes": size}
        except Exception as e:
            print(f"  [FAIL] {key}: {e}")
            results[key] = {"error": str(e)}
    return results


# ---------------------------------------------------------------------------
# 检查 4: Heat 一致性
# ---------------------------------------------------------------------------

def check_heat_consistency() -> dict:
    """验证 stored heat 与 computed heat 是否一致。"""
    print(f"\n[4/5] Heat consistency...")
    issues = []
    sids = storage_mod.list_session_ids()

    for sid in sids:
        try:
            meta = storage_mod.read_meta(sid)
            computed = heat_mod.compute_heat(
                access_count=meta.access_count,
                last_access=parse_dt(meta.last_access),
                created_at=parse_dt(meta.created_at),
            )
            diff = abs(meta.heat - computed)
            if diff > 0.5:
                print(f"  [WARN] {sid[:12]}: stored={meta.heat:.2f} computed={computed:.2f} (diff={diff:.2f})")
                issues.append(sid)
            else:
                print(f"  [OK] {sid[:12]}: heat={meta.heat:.2f}")
        except Exception as e:
            print(f"  [FAIL] {sid[:12]}: {e}")
            issues.append(sid)

    return {"total": len(sids), "issues": len(issues), "sids": issues}


# ---------------------------------------------------------------------------
# 检查 5: GC dry-run
# ---------------------------------------------------------------------------

def check_gc() -> dict:
    """GC dry-run，检查 trash 和 zombie 状态。"""
    print(f"\n[5/5] GC dry-run...")
    try:
        report = gc_mod.gc_all(dry_run=True)
        print(f"  Trash:  {len(report.trash_entries)} entries")
        trash_bytes = sum(e.size for e in report.trash_entries)
        print(f"  Zombie: {len(report.zombie_entries)} entries")
        zombie_bytes = sum(e.size for e in report.zombie_entries)
        return {"trash_entries": len(report.trash_entries), "trash_bytes": trash_bytes,
                "zombie_entries": len(report.zombie_entries), "zombie_bytes": zombie_bytes}
    except Exception as e:
        print(f"  [FAIL] gc_all: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def run() -> int:
    banner("mmi doctor — context-mode inspired diagnostics")

    results = {}

    results["imports"] = check_imports()
    if results["imports"]["fail"] > 0:
        print("\n  Cannot proceed without core modules.")
        return 1

    results["sessions"] = check_sessions()
    results["filesystem"] = check_filesystem()
    results["heat"] = check_heat_consistency()
    results["gc"] = check_gc()

    # 汇总
    r = results["sessions"]
    banner("Summary")
    print(f"  {r['active']} active | {r['warm']} warm | {r['cold']} cold | "
          f"{r['zombie']} zombie | {r['corrupt']} corrupt | {r['trash']} trash")
    return 0


if __name__ == "__main__":
    sys.exit(run())