"""mmi 内部异常类。

集中放自定义异常,避免各模块散落。R7 4.3 引入。
"""
from __future__ import annotations


class LLMRetryExhausted(Exception):  # noqa: N818
    """LLM 重试 max_attempts 次后仍失败。

    Attributes:
        attempts: 实际尝试次数(等于传入的 max_attempts)
        last_error: 最后一次失败的底层异常
    """

    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"LLM retry exhausted after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error


class StreamError(Exception):
    """流式 LLM 调用中途出错(R8+ 细化)。"""
