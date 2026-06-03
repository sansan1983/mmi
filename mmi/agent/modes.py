"""Thinking-mode enumeration and associated system-prompt fragments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import auto, Enum


class ThinkingMode(Enum):
    """Operational mode that governs how the agent processes a request.

    Each mode is paired with a system-prompt fragment in :data:`MODE_PROMPTS`.
    """

    STANDARD = auto()
    """Default: concise, factual, task-focused."""

    BRAINSTORM = auto()
    """Divergent: explore multiple angles, wild ideas welcome."""

    AUDIT = auto()
    """Convergent: critical evaluation, find weaknesses and compliance gaps."""


@dataclass(frozen=True, slots=True)
class _ModePrompt:
    """Immutable prompt fragment associated with a ThinkingMode."""

    system_suffix: str
    """Text appended to the system prompt when this mode is active."""

    preamble: str
    """Instruction injected before the user's message."""


MODE_PROMPTS: dict[ThinkingMode, _ModePrompt] = {
    ThinkingMode.STANDARD: _ModePrompt(
        system_suffix="You are a helpful, precise assistant. Answer concisely.",
        preamble="",
    ),
    ThinkingMode.BRAINSTORM: _ModePrompt(
        system_suffix=(
            "You are in brainstorm mode. Generate many diverse ideas. "
            "Do not censor or self-censor. Quantity over quality. "
            "Build on previous ideas. Defer judgment."
        ),
        preamble="[Brainstorm] Consider multiple perspectives and generate bold ideas.",
    ),
    ThinkingMode.AUDIT: _ModePrompt(
        system_suffix=(
            "You are in audit mode. Critically examine the input. "
            "Identify weaknesses, logical fallacies, security risks, and compliance gaps. "
            "Prefer precision over politeness. State concerns directly."
        ),
        preamble="[Audit] Perform a thorough critical review.",
    ),
}


def get_mode_prompt(mode: ThinkingMode) -> _ModePrompt:
    """Return the prompt fragment for *mode*."""
    return MODE_PROMPTS.get(mode, MODE_PROMPTS[ThinkingMode.STANDARD])
