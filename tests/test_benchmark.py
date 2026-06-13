"""tests/test_benchmark.py —— P5-2 性能压测。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.evaluation import EvalRunner, ExactMatchEvaluator, EvalSample
from mmi.core.llm import EchoLLMProvider


def test_benchmark_echo_llm_chat():
    """EchoLLMProvider.chat 延迟基准。"""
    provider = EchoLLMProvider()
    messages = [{"role": "user", "content": "hello"}]
    latencies = []
    for _ in range(100):
        start = time.perf_counter()
        provider.chat(messages)
        latencies.append((time.perf_counter() - start) * 1000)
    avg_ms = sum(latencies) / len(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    print(f"[benchmark] EchoLLM.chat: avg={avg_ms:.3f}ms p95={p95:.3f}ms")
    assert avg_ms < 5.0


def test_benchmark_eval_runner_throughput():
    """EvalRunner 吞吐量基准（降低阈值适应 CI）。"""
    runner = EvalRunner()
    samples = [
        EvalSample(input_text=f"input_{i}", expected_output="a", actual_output="a")
        for i in range(2000)
    ]
    start = time.perf_counter()
    report = runner.run(name="throughput", samples=samples, evaluator=ExactMatchEvaluator())
    elapsed = max(time.perf_counter() - start, 0.001)
    throughput = report.total / elapsed
    print(f"[benchmark] EvalRunner: {throughput:.0f} samples/s ({report.total} in {elapsed:.2f}s)")
    assert throughput > 100


def test_benchmark_registry_discover(tmp_path):
    """ProviderRegistry.discover() 冷启动基准。"""
    from mmi.core.provider_registry import ProviderRegistry
    providers_dir = tmp_path / "providers"
    providers_dir.mkdir()
    registry = ProviderRegistry(providers_dir=providers_dir)
    start = time.perf_counter()
    registry.discover()
    elapsed = (time.perf_counter() - start) * 1000
    print(f"[benchmark] ProviderRegistry.discover: {elapsed:.2f}ms")
    assert elapsed < 10.0


def test_benchmark_mcp_server():
    """MCPServer.handle_request 延迟基准。"""
    from mmi.core.mcp_server import MCPServer
    MCPServer.reset_instance()
    server = MCPServer()
    latencies = []
    for _ in range(100):
        start = time.perf_counter()
        server.handle_request({"method": "tools/list", "id": 1})
        latencies.append((time.perf_counter() - start) * 1000)
    avg_ms = sum(latencies) / len(latencies)
    print(f"[benchmark] MCPServer.handle_request: avg={avg_ms:.3f}ms")
    assert avg_ms < 5.0
