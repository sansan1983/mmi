"""tests/test_integration.py —— P5-1 端到端集成测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.agent.event_bus import Event, EventBus
from mmi.core.llm import EchoLLMProvider
from mmi.core.provider_registry import ProviderRegistry, RegisteredProvider
from mmi.core.evaluation import EvalRunner, ExactMatchEvaluator, EvalSample
from mmi.core.mcp_server import MCPServer


# ---------------------------------------------------------------------------
# Test 1: EventBus 发布订阅
# ---------------------------------------------------------------------------

def test_event_bus_pub_sub():
    bus = EventBus()
    events = []
    bus.subscribe("msg", lambda e: events.append(e.payload))
    bus.publish(Event(name="msg", timestamp=1.0, payload={"k": 1}))
    assert len(events) == 1
    assert events[0]["k"] == 1


def test_event_bus_unsubscribe():
    bus = EventBus()
    count = []
    def handler(e):
        count.append(1)
    bus.subscribe("e", handler)
    bus.publish(Event(name="e", timestamp=1.0, payload={}))
    assert len(count) == 1
    bus.unsubscribe("e", handler)
    bus.publish(Event(name="e", timestamp=2.0, payload={}))
    assert len(count) == 1


# ---------------------------------------------------------------------------
# Test 2: EchoLLMProvider 兜底
# ---------------------------------------------------------------------------

def test_echo_llm_chat():
    p = EchoLLMProvider()
    reply = p.chat([{"role": "user", "content": "hi"}])
    assert isinstance(reply, str) and len(reply) > 0


def test_echo_llm_classify():
    p = EchoLLMProvider()
    r = p.classify("q", options=["A", "B"])
    assert r.choice == "A"
    assert 0.0 <= r.confidence <= 1.0


# ---------------------------------------------------------------------------
# Test 3: ProviderRegistry
# ---------------------------------------------------------------------------

def test_registry_singleton():
    ProviderRegistry.reset_instance()
    r1 = ProviderRegistry.get_instance()
    r2 = ProviderRegistry.get_instance()
    assert r1 is r2


def test_registry_manual_register():
    ProviderRegistry.reset_instance()
    r = ProviderRegistry.get_instance()
    cls = type("FakeProv", (EchoLLMProvider,), {"name": "fake"})
    r.register(RegisteredProvider(name="fake", cls=cls, source_file="fake.py"))
    assert r.has_provider("fake")


# ---------------------------------------------------------------------------
# Test 4: MCPServer
# ---------------------------------------------------------------------------

def test_mcp_initialize():
    MCPServer.reset_instance()
    s = MCPServer()
    resp = s.handle_request({"method": "initialize", "id": 1})
    assert resp.result["protocolVersion"] == "2024-11-05"


def test_mcp_tools_count():
    MCPServer.reset_instance()
    s = MCPServer()
    resp = s.handle_request({"method": "tools/list", "id": 1})
    assert len(resp.result["tools"]) >= 6


# ---------------------------------------------------------------------------
# Test 5: EvalRunner
# ---------------------------------------------------------------------------

def test_evalrunner_accuracy():
    runner = EvalRunner()
    samples = [
        EvalSample(input_text="a", expected_output="a", actual_output="a"),
        EvalSample(input_text="b", expected_output="b", actual_output="x"),
    ]
    report = runner.run(name="t", samples=samples, evaluator=ExactMatchEvaluator())
    assert report.passed == 1
    assert report.failed == 1


# ---------------------------------------------------------------------------
# Test 6: Config 读写
# ---------------------------------------------------------------------------

def test_config_theme():
    """测试 set_theme / get_theme 基本功能（用默认 config）。"""
    from mmi.core import config as cfg
    original = cfg.get_theme()
    cfg.set_theme("light")
    assert cfg.get_theme() == "light"
    cfg.set_theme(original)  # 恢复


# ---------------------------------------------------------------------------
# Test 7: 全链路模拟
# ---------------------------------------------------------------------------

def test_full_pipeline_mock():
    bus = EventBus()
    events = []
    bus.subscribe("message", lambda e: events.append(e.payload))
    bus.publish(Event(name="message", timestamp=1.0, payload={"role": "user", "content": "hi"}))
    p = EchoLLMProvider()
    reply = p.chat([{"role": "user", "content": "hi"}])
    bus.publish(Event(name="message", timestamp=2.0, payload={"role": "assistant", "content": reply}))
    assert len(events) == 2
    assert events[0]["role"] == "user"
    assert len(reply) > 0
