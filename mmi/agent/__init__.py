"""MMI Agent Layer — task orchestration, routing, and sub-agent management."""

from __future__ import annotations

from mmi.agent.base import BaseAgent
from mmi.agent.modes import MODE_PROMPTS, ThinkingMode
from mmi.agent.orchestrator import Orchestrator
from mmi.agent.registry import AgentMeta, AgentRegistry
from mmi.agent.router import IntentType, Router
from mmi.agent.skill import Skill, SkillLibrary, SkillType
from mmi.agent.trace import TraceRecord, Tracer
from mmi.agent.validate import ValidationResult, ValidationRule, Validator

__all__ = [
    # Core orchestration
    "Orchestrator",
    # Routing
    "IntentType",
    "Router",
    # Registry
    "AgentMeta",
    "AgentRegistry",
    # Base
    "BaseAgent",
    "ToolDef",
    # Modes
    "ThinkingMode",
    "MODE_PROMPTS",
    # Validation
    "Validator",
    "ValidationRule",
    "ValidationResult",
    # Skills
    "Skill",
    "SkillLibrary",
    "SkillType",
    # Trace
    "TraceRecord",
    "Tracer",
]
