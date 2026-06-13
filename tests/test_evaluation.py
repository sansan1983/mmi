"""tests/test_evaluation.py —— P4-4 评估框架测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.evaluation import (
    ContainsEvaluator,
    EvalReport,
    EvalRunner,
    EvalSample,
    ExactMatchEvaluator,
    FuncEvaluator,
)


# ---------------------------------------------------------------------------
# ExactMatchEvaluator
# ---------------------------------------------------------------------------

def test_exact_match_pass():
    e = ExactMatchEvaluator()
    sample = EvalSample(input_text="hello", expected_output="hello", actual_output="hello")
    r = e.evaluate(sample)
    assert r.passed
    assert r.score == 1.0


def test_exact_match_fail():
    e = ExactMatchEvaluator()
    sample = EvalSample(input_text="hello", expected_output="hello", actual_output="world")
    r = e.evaluate(sample)
    assert not r.passed
    assert r.score == 0.0


def test_exact_match_case_insensitive():
    e = ExactMatchEvaluator(case_sensitive=False)
    sample = EvalSample(input_text="Hello", expected_output="hello", actual_output="HELLO")
    r = e.evaluate(sample)
    assert r.passed


def test_exact_match_case_sensitive():
    e = ExactMatchEvaluator(case_sensitive=True)
    sample = EvalSample(input_text="hello", expected_output="hello", actual_output="HELLO")
    r = e.evaluate(sample)
    assert not r.passed


# ---------------------------------------------------------------------------
# ContainsEvaluator
# ---------------------------------------------------------------------------

def test_contains_pass():
    e = ContainsEvaluator()
    sample = EvalSample(input_text="x", expected_output="hello", actual_output="hello world")
    r = e.evaluate(sample)
    assert r.passed


def test_contains_fail():
    e = ContainsEvaluator()
    sample = EvalSample(input_text="x", expected_output="xyz", actual_output="hello world")
    r = e.evaluate(sample)
    assert not r.passed


# ---------------------------------------------------------------------------
# FuncEvaluator
# ---------------------------------------------------------------------------

def test_func_evaluator():
    def check(sample):
        return (0.8, True, "good")
    e = FuncEvaluator(fn=check)
    sample = EvalSample(input_text="x")
    r = e.evaluate(sample)
    assert r.score == 0.8
    assert r.passed
    assert r.reason == "good"


# ---------------------------------------------------------------------------
# EvalReport
# ---------------------------------------------------------------------------

def test_report_accuracy():
    report = EvalReport(name="test", total=10, passed=8, failed=2, scores=[1.0]*8 + [0.0]*2)
    assert report.accuracy == 0.8


def test_report_avg_score():
    report = EvalReport(name="test", scores=[1.0, 0.5, 0.0])
    assert abs(report.avg_score - 0.5) < 0.001


def test_report_latency_percentiles():
    report = EvalReport(name="test", latency_ms=[10, 20, 30, 40, 50])
    assert report.latency_p50() == 30.0
    assert report.latency_p95() == 50.0


def test_report_empty():
    report = EvalReport(name="test")
    assert report.accuracy == 0.0
    assert report.avg_score == 0.0
    assert report.latency_p50() == 0.0


def test_report_summary():
    report = EvalReport(name="test", total=2, passed=1, failed=1, scores=[1.0, 0.0])
    text = report.summary()
    assert "test" in text
    assert "50.00%" in text


# ---------------------------------------------------------------------------
# EvalRunner
# ---------------------------------------------------------------------------

def test_runner_run():
    runner = EvalRunner()
    samples = [
        EvalSample(input_text="a", expected_output="a", actual_output="a"),
        EvalSample(input_text="b", expected_output="b", actual_output="c"),
    ]
    report = runner.run(
        name="test-run",
        samples=samples,
        evaluator=ExactMatchEvaluator(),
    )
    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1


def test_runner_run_function_eval():
    runner = EvalRunner()
    report = runner.run_function_eval(
        name="identity",
        fn=lambda x: x.upper(),
        test_cases=[("hello", "HELLO"), ("world", "WORLD"), ("hi", "NOPE")],
    )
    assert report.total == 3
    assert report.passed == 2


def test_runner_run_function_eval_exception():
    runner = EvalRunner()
    def boom(x):
        raise ValueError("boom")

    report = runner.run_function_eval(
        name="error-test",
        fn=boom,
        test_cases=[("x", "y")],
    )
    assert report.total == 1
    assert report.failed == 1
    assert "boom" in report.details[0].reason


def test_runner_get_reports():
    runner = EvalRunner()
    runner.run(name="a", samples=[], evaluator=ExactMatchEvaluator())
    runner.run(name="b", samples=[], evaluator=ExactMatchEvaluator())
    assert len(runner.get_reports()) == 2


def test_runner_reset():
    EvalRunner.reset_instance()
    runner = EvalRunner()
    assert runner.get_reports() == []
