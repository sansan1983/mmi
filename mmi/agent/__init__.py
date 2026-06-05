"""MMI Agent Layer — task orchestration, routing, and sub-agent management."""

from __future__ import annotations

from mmi.agent.base import BaseAgent, ToolDef
from mmi.agent.modes import ThinkingMode, get_mode_prompt
from mmi.agent.orchestrator import Orchestrator
from mmi.agent.pipeline import Pipeline, PipelineCtx, PipelineStep, StepError
from mmi.agent.registry import AgentMeta, AgentRegistry
from mmi.agent.result import ChatResult
from mmi.agent.router import IntentType, Router
from mmi.agent.skill import Skill, SkillLibrary, SkillType
from mmi.agent.steps import (
    ClassifyStep,
    InstantiateStep,
    PersistStep,
    RouteStep,
    RunStep,
    ValidateStep,
    default_steps,
)
from mmi.agent.trace import TraceRecord, Tracer
from mmi.agent.validate import ValidationResult, ValidationRule, Validator

__all__ = [
    # Core orchestration
    "Orchestrator",
    # Pipeline (R7 4.2)
    "Pipeline",
    "PipelineCtx",
    "PipelineStep",
    "StepError",
    "ClassifyStep",
    "RouteStep",
    "InstantiateStep",
    "RunStep",
    "ValidateStep",
    "PersistStep",
    "default_steps",
    # Chat result (R7 4.1)
    "ChatResult",
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
    "get_mode_prompt",
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

