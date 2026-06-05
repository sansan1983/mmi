"""Round 0.8: CLI rename + info tests (pytest风格验证脚本)。"""
import subprocess
import sys
import os
import tempfile
import json
from pathlib import Path

VENV = "/home/ubuntu/ctrim/.venv/bin/python"
ROOT = "/home/ubuntu/ctrim-fusion"

def run(*args):
    r = subprocess.run(
        [VENV, "-c", f"import sys; sys.path.insert(0,'{ROOT}'); from ctrim.cli import main; sys.exit(main({list(args)}))"],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": ROOT, "MMI_HOME": str(Path.home()/".mmi-fusion")}
    )
    return r

def get_sid():
    from mmi.core import storage
    ids = storage.list_session_ids()
    assert ids, "No sessions found in ~/.mmi-fusion — run `ctrim new` first"
    return ids[0]

def test_info_help():
    r = run("info", "--help")
    assert r.returncode == 0, f"info --help failed: {r.stderr}"
    assert "session_id" in r.stdout, "info --help missing session_id"
    print("PASS: info --help")

def test_rename_help():
    r = run("rename", "--help")
    assert r.returncode == 0, f"rename --help failed: {r.stderr}"
    assert "session_id" in r.stdout, "rename --help missing session_id"
    print("PASS: rename --help")

def test_info_valid_sid():
    sid = get_sid()
    r = run("info", sid)
    assert r.returncode == 0, f"info valid SID failed: {r.stderr}"
    assert "Session ID" in r.stdout, "info output missing header"
    print("PASS: info valid SID")

def test_rename_valid_sid():
    sid = get_sid()
    r = run("rename", sid, "测试标题-R8")
    assert r.returncode == 0, f"rename valid SID failed: {r.stderr}"
    assert "测试标题-R8" in r.stdout, "rename confirmation missing new title"
    # Revert
    run("rename", sid, "untitled")
    print("PASS: rename valid SID")

def test_bad_sid_info():
    r = run("info", "BADSID")
    assert r.returncode != 0, "info bad SID should fail"
    print("PASS: info bad SID (returns error)")

def test_bad_sid_rename():
    r = run("rename", "BADSID", "t")
    assert r.returncode != 0, "rename bad SID should fail"
    print("PASS: rename bad SID (returns error)")

def test_doctor():
    r = run("doctor")
    assert r.returncode == 0, f"doctor failed: {r.stderr}"
    assert "[OK]" in r.stdout or "Summary" in r.stdout, "doctor output unexpected"
    print("PASS: doctor")

def test_export():
    sid = get_sid()
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    try:
        r = run("export", sid, out)
        assert r.returncode == 0, f"export failed: {r.stderr}"
        with open(out) as f:
            d = json.load(f)
        assert "session_id" in d, "export JSON missing session_id"
        assert "state" in d, "export JSON missing state"
        print("PASS: export JSON")
    finally:
        os.unlink(out)

def test_list():
    r = run("list")
    assert r.returncode == 0, f"list failed: {r.stderr}"
    print("PASS: list")

def test_stat():
    r = run("stat")
    assert r.returncode == 0, f"stat failed: {r.stderr}"
    print("PASS: stat")

if __name__ == "__main__":
    tests = [
        test_info_help, test_rename_help,
        test_info_valid_sid, test_rename_valid_sid,
        test_bad_sid_info, test_bad_sid_rename,
        test_doctor, test_export, test_list, test_stat,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e}")
    print(f"\n{'='*50}")
    print(f"Result: {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)
