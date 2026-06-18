"""Document generation / translation sub-agent.

3.10 改进:DocAgent 最小可行实现。
支持:文档生成 + 中英翻译(由 user_message 关键词自动判断)。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mmi.agent.base import BaseAgent

if TYPE_CHECKING:
    from mmi.agent.modes import ThinkingMode
    from mmi.core.llm import LLMProvider


DEFAULT_SYSTEM_PROMPT = """You are a documentation specialist.
Generate clear, accurate documentation for the given code or text.
Output should be Markdown with appropriate headers, code blocks, and examples.
Reply in the target language requested by the user, or English if unclear."""


_TRANSLATION_TRIGGERS = re.compile(
    r"翻译|translate|译成|转成\s*英文|转成\s*中文", re.IGNORECASE
)


class DocAgent(BaseAgent):
    """Documentation / translation sub-agent.

    3.10 改进:run() 根据 user_message 关键词判断是"生成文档"还是"翻译",
    自动调整 system_prompt 后调 LLM。
    """

    __slots__ = ()

    def __init__(
        self,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        llm: LLMProvider | None = None,
    ) -> None:
        super().__init__(
            agent_id="doc",
            name="Doc",
            system_prompt=system_prompt,
            llm=llm,
        )

    def run(
        self,
        user_message: str,
        mode: ThinkingMode | None = None,
    ) -> str:
        """Generate documentation or translate text based on user request.

        Parameters
        ----------
        user_message : str
            User's doc/translation request.
        mode : ThinkingMode, optional
            Thinking mode override.

        Returns
        -------
        str
            Generated docs or translated text.
        """
        from mmi.core.llm import LLMError

        # 模式切换:检测到"翻译" → 覆盖 system_prompt
        original_prompt = self.system_prompt
        try:
            if _TRANSLATION_TRIGGERS.search(user_message):
                self.system_prompt = (
                    "You are a professional translator. "
                    "Translate the user's text accurately. "
                    "Preserve code blocks verbatim. "
                    "Reply only with the translation, no preamble."
                )
            self.on_start()
            reply = self._chat_with_llm(user_message, mode=mode, max_tokens=2048)
            return reply
        except LLMError as e:
            self.on_error(e)
            return f"[DocAgent error] {e}"
        finally:
            self.system_prompt = original_prompt  # 恢复
            self.on_stop()
