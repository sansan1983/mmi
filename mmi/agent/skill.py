"""Skill library — CRUD operations, versioning, proposal logic, and disk persistence."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from pathlib import Path
from typing import ClassVar

from mmi.core.paths import ensure_dirs, get_skills_dir


class SkillType(Enum):
    """Category of a skill, driving how it is evolved and ranked."""

    EVOLUTION = auto()
    """Derived from memory / usage patterns (user habits, optimal flows)."""

    BRAINSTORM = auto()
    """Produced by the brainstorm agent."""

    AUDIT = auto()
    """Produced by the audit agent."""

    BUILTIN = auto()
    """Shipped with the framework."""


@dataclass
class Skill:
    """A discrete, reusable capability extracted from agent runs."""

    skill_id: str
    name: str
    skill_type: SkillType
    content: str
    """Markdown or structured text describing how to apply the skill."""

    apply_scene: str = ""
    """Free-text description of when to use this skill."""

    tags: list[str] = field(default_factory=list)
    update_count: int = 0
    version: str = "0.1.0"
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d["skill_type"] = self.skill_type.name
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Skill:
        """Reconstruct from a dict (e.g. loaded from JSON)."""
        data = dict(data)  # shallow copy
        data["skill_type"] = SkillType[data.pop("skill_type")]
        return cls(**data)


class SkillLibrary:
    """Global repository of skills, persisted to disk as JSON files.

    Storage layout::

        ~/.mmi/skills/<skill_id>.json

    Each file contains the JSON-serialized :class:`Skill` object.
    The in-memory ``_skills`` dict acts as a write-through cache.
    Thread safety is provided via an internal ``RLock``.
    """

    _instance: ClassVar[SkillLibrary | None] = None

    def __init__(self, *, skills_dir: Path | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        self._lock = threading.RLock()
        self._skills_dir = skills_dir or get_skills_dir()
        self._load_all()

    @classmethod
    def get_instance(cls) -> SkillLibrary:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _skill_path(self, skill_id: str) -> Path:
        """Return the JSON file path for *skill_id*."""
        # Sanitize: only allow alphanumeric, dash, underscore, dot
        safe = "".join(c for c in skill_id if c.isalnum() or c in "-_.")
        if not safe:
            raise ValueError(f"Invalid skill_id: {skill_id!r}")
        return self._skills_dir / f"{safe}.json"

    def _save(self, skill: Skill) -> None:
        """Write a single skill to disk (write-through)."""
        path = self._skill_path(skill.skill_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(skill.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")

    def _delete_file(self, skill_id: str) -> None:
        """Remove the JSON file for *skill_id* (best-effort)."""
        try:
            self._skill_path(skill_id).unlink(missing_ok=True)
        except OSError:
            pass

    def _load_all(self) -> None:
        """Load all skills from disk into ``_skills``."""
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        for path in self._skills_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                skill = Skill.from_dict(data)
                self._skills[skill.skill_id] = skill
            except (json.JSONDecodeError, KeyError, TypeError):
                # Skip corrupt files silently
                pass

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, skill: Skill) -> None:
        """Add a new skill to the library and persist to disk.

        Raises
        ------
        ValueError
            If a skill with the same ``skill_id`` exists.
        """
        with self._lock:
            if skill.skill_id in self._skills:
                raise ValueError(f"Skill already exists: {skill.skill_id!r}")
            self._skills[skill.skill_id] = skill
            self._save(skill)

    def update(self, skill_id: str, **kwargs: str | list[str]) -> Skill:
        """Update mutable fields of an existing skill and persist.

        Parameters
        ----------
        skill_id : str
            Skill to update.
        **kwargs
            Fields to patch (``content``, ``apply_scene``, ``tags``, etc.).

        Returns
        -------
        Skill
            Updated skill instance.

        Raises
        ------
        KeyError
            If *skill_id* is not found.
        """
        with self._lock:
            skill = self._skills[skill_id]
            for key, value in kwargs.items():
                if hasattr(skill, key):
                    setattr(skill, key, value)
            skill.update_count += 1
            skill.updated_at = datetime.now(timezone.utc).isoformat()
            self._save(skill)
            return skill

    def deprecate(self, skill_id: str) -> None:
        """Soft-delete a skill (remove from active pool and disk)."""
        with self._lock:
            self._skills.pop(skill_id, None)
            self._delete_file(skill_id)

    def get(self, skill_id: str) -> Skill | None:
        """Return a skill by ID, or None."""
        return self._skills.get(skill_id)

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def match(self, query: str, limit: int = 5) -> list[Skill]:
        """Return skills relevant to *query* (simple keyword scoring).

        Parameters
        ----------
        query : str
            Search terms.
        limit : int
            Maximum number of results.

        Returns
        -------
        list[Skill]
        """
        tokens = set(query.lower().split())
        scored: list[tuple[int, Skill]] = []
        for skill in self._skills.values():
            score = sum(
                1 for t in tokens
                if t in skill.name.lower()
                or t in skill.apply_scene.lower()
                or any(t in tag.lower() for tag in skill.tags)
            )
            if score > 0:
                scored.append((score, skill))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]

    def propose(self, task_context: str) -> list[Skill]:
        """Suggest skills for the given task context.

        Uses :meth:`match` internally; in future may invoke LLM ranking.

        Parameters
        ----------
        task_context : str
            Description of the current task / user request.

        Returns
        -------
        list[Skill]
            Top matched skills, up to 5.
        """
        return self.match(task_context, limit=5)
