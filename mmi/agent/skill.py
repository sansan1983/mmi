"""Skill library — CRUD operations, versioning, and proposal logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import ClassVar


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


class SkillLibrary:
    """Global repository of skills, persisted to storage.

    Supports CRUD, tagging, search, and proposal of skills for a given
    task context.
    """

    _instance: ClassVar[SkillLibrary | None] = None

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    @classmethod
    def get_instance(cls) -> SkillLibrary:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, skill: Skill) -> None:
        """Add a new skill to the library.

        Raises
        ------
        ValueError
            If a skill with the same ``skill_id`` exists.
        """
        if skill.skill_id in self._skills:
            raise ValueError(f"Skill already exists: {skill.skill_id!r}")
        self._skills[skill.skill_id] = skill

    def update(self, skill_id: str, **kwargs: str | list[str]) -> Skill:
        """Update mutable fields of an existing skill.

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
        skill = self._skills[skill_id]
        for key, value in kwargs.items():
            if hasattr(skill, key):
                setattr(skill, key, value)
        skill.update_count += 1
        skill.updated_at = datetime.now(timezone.utc).isoformat()
        return skill

    def deprecate(self, skill_id: str) -> None:
        """Soft-delete a skill (remove from active pool)."""
        self._skills.pop(skill_id, None)

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
