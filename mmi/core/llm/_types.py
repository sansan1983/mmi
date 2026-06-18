"""mmi.core.llm._types —— 公共异常 + 数据类。

依赖项:无。
被依赖:base.py, 所有 provider 模块, factory.py。
"""

from __future__ import annotations

from dataclasses import dataclass


class LLMError(Exception):
    """LLM 调用失败（网络 / 鉴权 / 解析错误等）。调用方应安全降级。"""


@dataclass
class Classification:
    """classify() 的结构化结果。"""

    choice: str          # 选中的选项（必须在 options 内）
    confidence: float     # 0.0 - 1.0，调用方按阈值过滤
    raw: str = ""         # 原始返回（调试用）

    def is_high_confidence(self, threshold: float = 0.6) -> bool:
        return self.confidence >= threshold
