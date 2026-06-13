"""mmi.core.evaluation —— 评估框架 + 性能基准测试。

P4-4: 建立可量化的质量评估体系，支持以下评估维度：
  - Router 分类准确率（ground truth 数据集）
  - Pipeline 端到端延迟（p50 / p95 / p99）
  - Memory 召回准确率（recall@k）
  - Provider 响应质量（LLM-as-judge）
"""

from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class EvalSample:
    """A single evaluation sample."""

    input_text: str
    expected_output: str | None = None
    actual_output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """Result of a single evaluation sample."""

    sample: EvalSample
    score: float
    """0.0 (worst) to 1.0 (best)."""

    passed: bool
    reason: str = ""


@dataclass
class EvalReport:
    """Aggregated evaluation report."""

    name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    scores: list[float] = field(default_factory=list)
    latency_ms: list[float] = field(default_factory=list)
    details: list[EvalResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.passed / max(self.total, 1)

    @property
    def avg_score(self) -> float:
        return statistics.mean(self.scores) if self.scores else 0.0

    def latency_p50(self) -> float:
        return self._percentile(50)

    def latency_p95(self) -> float:
        return self._percentile(95)

    def latency_p99(self) -> float:
        return self._percentile(99)

    def _percentile(self, p: int) -> float:
        if not self.latency_ms:
            return 0.0
        sorted_vals = sorted(self.latency_ms)
        idx = int(len(sorted_vals) * p / 100)
        idx = min(idx, len(sorted_vals) - 1)
        return sorted_vals[idx]

    def summary(self) -> str:
        lines = [
            f"EvalReport: {self.name}",
            f"  Total: {self.total} | Passed: {self.passed} | Failed: {self.failed}",
            f"  Accuracy: {self.accuracy:.2%}",
            f"  Avg Score: {self.avg_score:.3f}",
            f"  Latency: p50={self.latency_p50():.1f}ms p95={self.latency_p95():.1f}ms p99={self.latency_p99():.1f}ms",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------


@dataclass
class ExactMatchEvaluator:
    """Exact string match evaluator."""

    case_sensitive: bool = False

    def evaluate(self, sample: EvalSample) -> EvalResult:
        start = time.monotonic()
        expected = sample.expected_output or ""
        actual = sample.actual_output or ""
        if not self.case_sensitive:
            expected = expected.lower()
            actual = actual.lower()
        score = 1.0 if expected == actual else 0.0
        latency = (time.monotonic() - start) * 1000
        return EvalResult(
            sample=sample,
            score=score,
            passed=score >= 1.0,
            reason="exact match" if score >= 1.0 else "mismatch",
        )


@dataclass
class ContainsEvaluator:
    """Checks if actual output contains expected substring."""

    case_sensitive: bool = False

    def evaluate(self, sample: EvalSample) -> EvalResult:
        expected = sample.expected_output or ""
        actual = sample.actual_output or ""
        if not self.case_sensitive:
            expected = expected.lower()
            actual = actual.lower()
        score = 1.0 if expected in actual else 0.0
        return EvalResult(
            sample=sample,
            score=score,
            passed=score >= 1.0,
            reason="contains" if score >= 1.0 else "not found",
        )


@dataclass
class FuncEvaluator:
    """Custom function-based evaluator.

    The evaluator function receives ``(sample: EvalSample) -> tuple[float, bool, str]``
    returning (score, passed, reason).
    """

    fn: Callable[[EvalSample], tuple[float, bool, str]]

    def evaluate(self, sample: EvalSample) -> EvalResult:
        score, passed, reason = self.fn(sample)
        return EvalResult(sample=sample, score=score, passed=passed, reason=reason)


# ---------------------------------------------------------------------------
# EvalRunner
# ---------------------------------------------------------------------------


class EvalRunner:
    """Run evaluations and produce reports.

    Usage::

        runner = EvalRunner()
        report = runner.run(
            name="router-accuracy",
            samples=[...],
            evaluator=ExactMatchEvaluator(),
        )
        print(report.summary())
    """

    _instance: ClassVar[EvalRunner | None] = None

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._reports: list[EvalReport] = []

    @classmethod
    def get_instance(cls) -> EvalRunner:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def run(
        self,
        *,
        name: str,
        samples: list[EvalSample],
        evaluator: ExactMatchEvaluator | ContainsEvaluator | FuncEvaluator,
    ) -> EvalReport:
        """Run evaluation on all samples.

        Parameters
        ----------
        name : str
            Evaluation name for the report.
        samples : list[EvalSample]
            Test samples.
        evaluator
            One of the evaluator types.

        Returns
        -------
        EvalReport
            Aggregated results.
        """
        report = EvalReport(name=name)
        report.total = len(samples)

        for sample in samples:
            start = time.monotonic()
            result = evaluator.evaluate(sample)
            latency = (time.monotonic() - start) * 1000

            report.details.append(result)
            report.scores.append(result.score)
            report.latency_ms.append(latency)
            if result.passed:
                report.passed += 1
            else:
                report.failed += 1

        with self._lock:
            self._reports.append(report)

        return report

    def run_function_eval(
        self,
        *,
        name: str,
        fn: Callable[[str], str],
        test_cases: list[tuple[str, str]],
    ) -> EvalReport:
        """Convenience: run a function on inputs and evaluate against expected outputs.

        Parameters
        ----------
        fn : callable
            Function to test. Takes input string, returns output string.
        test_cases : list[tuple[str, str]]
            (input, expected_output) pairs.

        Returns
        -------
        EvalReport
        """
        samples = [
            EvalSample(input_text=inp, expected_output=exp)
            for inp, exp in test_cases
        ]

        def _eval(sample: EvalSample) -> tuple[float, bool, str]:
            start = time.monotonic()
            try:
                actual = fn(sample.input_text)
                latency = (time.monotonic() - start) * 1000
                match = actual.strip() == sample.expected_output.strip()
                return (1.0 if match else 0.0, match,
                        f"actual={actual[:50]}" if not match else "match")
            except Exception as e:
                return (0.0, False, str(e))

        evaluator = FuncEvaluator(fn=_eval)
        return self.run(name=name, samples=samples, evaluator=evaluator)

    def get_reports(self) -> list[EvalReport]:
        with self._lock:
            return list(self._reports)
