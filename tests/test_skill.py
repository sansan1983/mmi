"""tests/test_skill.py —— Skill 持久化测试（P3-1）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.agent.skill import Skill, SkillLibrary, SkillType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _tmp_library(tmp_path: Path) -> SkillLibrary:
    """Create a SkillLibrary backed by a temp directory."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    # Reset singleton so each test gets a fresh instance
    SkillLibrary._instance = None
    lib = SkillLibrary(skills_dir=skills_dir)
    return lib


def _sample_skill(skill_id: str = "test-skill") -> Skill:
    return Skill(
        skill_id=skill_id,
        name="Test Skill",
        skill_type=SkillType.BUILTIN,
        content="# How to test\nDo the thing.",
        apply_scene="When testing",
        tags=["test", "demo"],
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

def test_skill_to_dict_roundtrip():
    s = _sample_skill()
    d = s.to_dict()
    assert d["skill_type"] == "BUILTIN"
    assert d["skill_id"] == "test-skill"
    s2 = Skill.from_dict(d)
    assert s2.skill_id == s.skill_id
    assert s2.skill_type == SkillType.BUILTIN
    assert s2.tags == ["test", "demo"]


# ---------------------------------------------------------------------------
# CRUD + Persistence
# ---------------------------------------------------------------------------

def test_create_persists_to_disk(tmp_path):
    lib = _tmp_library(tmp_path)
    skill = _sample_skill()
    lib.create(skill)

    # File should exist
    fpath = lib._skill_path("test-skill")
    assert fpath.exists()

    # Content should be valid JSON
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert data["skill_id"] == "test-skill"


def test_create_duplicate_raises(tmp_path):
    lib = _tmp_library(tmp_path)
    lib.create(_sample_skill())
    try:
        lib.create(_sample_skill())
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_update_persists_to_disk(tmp_path):
    lib = _tmp_library(tmp_path)
    lib.create(_sample_skill())
    updated = lib.update("test-skill", content="updated content", tags=["new-tag"])
    assert updated.content == "updated content"
    assert updated.tags == ["new-tag"]
    assert updated.update_count == 1

    # Verify on disk
    data = json.loads(lib._skill_path("test-skill").read_text(encoding="utf-8"))
    assert data["content"] == "updated content"
    assert data["update_count"] == 1


def test_deprecate_removes_from_memory_and_disk(tmp_path):
    lib = _tmp_library(tmp_path)
    lib.create(_sample_skill())
    assert lib.get("test-skill") is not None
    assert lib._skill_path("test-skill").exists()

    lib.deprecate("test-skill")
    assert lib.get("test-skill") is None
    assert not lib._skill_path("test-skill").exists()


def test_get_returns_none_for_missing(tmp_path):
    lib = _tmp_library(tmp_path)
    assert lib.get("no-such-skill") is None


def test_load_all_on_init(tmp_path):
    """Skills saved to disk should be loaded when creating a new SkillLibrary."""
    lib = _tmp_library(tmp_path)
    lib.create(_sample_skill("alpha"))
    lib.create(_sample_skill("beta"))

    # New instance loading from same dir
    SkillLibrary._instance = None
    lib2 = SkillLibrary(skills_dir=tmp_path / "skills")
    assert lib2.get("alpha") is not None
    assert lib2.get("beta") is not None
    assert lib2.get("alpha").name == "Test Skill"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_match_by_name(tmp_path):
    lib = _tmp_library(tmp_path)
    lib.create(Skill(skill_id="py", name="Python Debug", skill_type=SkillType.BUILTIN,
                     content="debug python", tags=["python"]))
    lib.create(Skill(skill_id="js", name="JavaScript Debug", skill_type=SkillType.BUILTIN,
                     content="debug js", tags=["javascript"]))
    results = lib.match("python")
    assert len(results) == 1
    assert results[0].skill_id == "py"


def test_match_by_tag(tmp_path):
    lib = _tmp_library(tmp_path)
    lib.create(Skill(skill_id="a", name="Skill A", skill_type=SkillType.BUILTIN,
                     content="x", tags=["automation", "ci"]))
    results = lib.match("automation")
    assert len(results) == 1


def test_match_returns_empty_for_no_match(tmp_path):
    lib = _tmp_library(tmp_path)
    lib.create(_sample_skill())
    assert lib.match("zzzzz") == []


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

def test_concurrent_create(tmp_path):
    """Multiple threads creating skills should not corrupt data."""
    import threading

    lib = _tmp_library(tmp_path)
    errors: list[Exception] = []

    def create_skill(idx: int):
        try:
            lib.create(Skill(
                skill_id=f"skill-{idx}",
                name=f"Skill {idx}",
                skill_type=SkillType.BUILTIN,
                content=f"content {idx}",
            ))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=create_skill, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(lib._skills) == 20


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_skill_id_sanitization(tmp_path):
    lib = _tmp_library(tmp_path)
    skill = Skill(skill_id="my.skill/v2", name="Skill", skill_type=SkillType.BUILTIN,
                  content="x")
    lib.create(skill)
    # "/" should be stripped, file should be "my.skillv2.json"
    fpath = lib._skill_path("my.skill/v2")
    assert fpath.exists()


def test_corrupt_json_skipped(tmp_path):
    """A corrupt JSON file should not crash _load_all."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    # Write a corrupt file
    (skills_dir / "corrupt.json").write_text("{bad json", encoding="utf-8")
    # Write a valid file
    valid = _sample_skill("valid")
    (skills_dir / "valid.json").write_text(json.dumps(valid.to_dict()), encoding="utf-8")

    SkillLibrary._instance = None
    lib = SkillLibrary(skills_dir=skills_dir)
    assert lib.get("valid") is not None
    assert lib.get("corrupt") is None
