"""Thinking-mode enumeration and associated system-prompt fragments.

3.11 改进:prompt 改为从 locales 文件读,3.11 之前是硬编码字符串。
- 优先走 mmi.core.i18n.t() 走当前语言
- 兜底:locale 缺翻译时用英文原文(在 _FALLBACK_PROMPTS 里)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ThinkingMode(Enum):
    """Operational mode that governs how the agent processes a request."""

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


# 兜底硬编码(3.11 之前版本;i18n 找不到时用这个)
_FALLBACK_PROMPTS: dict[ThinkingMode, _ModePrompt] = {
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
    """Return the prompt fragment for *mode*。

    3.11 改进:
      1. 优先从 mmi.core.i18n.t() 读(按当前语言 zh-CN / en-US)
      2. 翻译缺失 → 兜底到 _FALLBACK_PROMPTS
    """
    try:
        from mmi.core.i18n import t
        suffix = t(f"agent.mode.{mode.name}.suffix", default="")
        preamble = t(f"agent.mode.{mode.name}.preamble", default="")
        if suffix:  # locale 翻译存在
            return _ModePrompt(system_suffix=suffix, preamble=preamble)
    except Exception:
        pass
    # 兜底
    return _FALLBACK_PROMPTS.get(mode, _FALLBACK_PROMPTS[ThinkingMode.STANDARD])
