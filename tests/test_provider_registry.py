"""tests/test_provider_registry.py —— P4-1 自定义 Provider 插件注册测试。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.llm import LLMProvider, LLMError, Classification
from mmi.core.provider_registry import ProviderRegistry, RegisteredProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _registry(tmp_path: Path) -> ProviderRegistry:
    providers_dir = tmp_path / "providers"
    providers_dir.mkdir(parents=True, exist_ok=True)
    ProviderRegistry.reset_instance()
    return ProviderRegistry(providers_dir=providers_dir)


def _write_plugin(tmp_path: Path, filename: str, code: str) -> Path:
    providers_dir = tmp_path / "providers"
    providers_dir.mkdir(parents=True, exist_ok=True)
    path = providers_dir / filename
    path.write_text(code, encoding="utf-8")
    return path


# Minimal valid plugin
VALID_PLUGIN = '''
from mmi.core.llm import LLMProvider, LLMError, Classification

class DummyProvider(LLMProvider):
    name = "dummy"

    def __init__(self, api_key: str = "", base_url: str = None, model: str = "dummy-v1", **kw):
        self._key = api_key
        self._model = model

    def chat(self, messages, *, max_tokens=4096, temperature=0.7):
        return "[dummy] ok"

    def classify(self, prompt, *, options):
        return Classification(choice=options[0], confidence=1.0)
'''


# Plugin with no LLMProvider subclass
INVALID_PLUGIN = '''
class NotAProvider:
    pass
'''


# Plugin with syntax error
BROKEN_PLUGIN = '''
def this_is_broken(
'''


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_discover_valid_plugin(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    registry = _registry(tmp_path)
    found = registry.discover()
    assert "dummy" in found
    assert registry.has_provider("dummy")


def test_discover_multiple_plugins(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    # Second plugin with different name
    _write_plugin(tmp_path, "other.py", VALID_PLUGIN.replace(
        'name = "dummy"', 'name = "other"'
    ).replace('DummyProvider', 'OtherProvider'))
    registry = _registry(tmp_path)
    found = registry.discover()
    assert len(found) == 2
    assert "dummy" in found
    assert "other" in found


def test_discover_skips_invalid_plugin(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    _write_plugin(tmp_path, "invalid.py", INVALID_PLUGIN)
    registry = _registry(tmp_path)
    found = registry.discover()
    assert "dummy" in found
    assert "invalid" not in found


def test_discover_skips_broken_plugin(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    _write_plugin(tmp_path, "broken.py", BROKEN_PLUGIN)
    registry = _registry(tmp_path)
    found = registry.discover()
    assert "dummy" in found


def test_discover_empty_dir(tmp_path):
    registry = _registry(tmp_path)
    found = registry.discover()
    assert found == []


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_manual_register(tmp_path):
    registry = _registry(tmp_path)
    reg = RegisteredProvider(
        name="manual",
        cls=type("ManualProvider", (LLMProvider,), {"name": "manual"}),
        source_file="manual.py",
    )
    registry.register(reg)
    assert registry.has_provider("manual")


def test_unregister(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    registry = _registry(tmp_path)
    registry.discover()
    assert registry.has_provider("dummy")
    registry.unregister("dummy")
    assert not registry.has_provider("dummy")


def test_list_registered(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    registry = _registry(tmp_path)
    registry.discover()
    providers = registry.list_registered()
    assert len(providers) == 1
    assert providers[0].name == "dummy"
    assert providers[0].source_file.endswith("dummy.py")


def test_list_names(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    registry = _registry(tmp_path)
    registry.discover()
    assert registry.list_names() == ["dummy"]


# ---------------------------------------------------------------------------
# get_provider_class
# ---------------------------------------------------------------------------

def test_get_provider_class_found(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    registry = _registry(tmp_path)
    registry.discover()
    cls = registry.get_provider_class("dummy")
    assert cls is not None
    assert issubclass(cls, LLMProvider)


def test_get_provider_class_not_found(tmp_path):
    registry = _registry(tmp_path)
    assert registry.get_provider_class("nonexistent") is None


# ---------------------------------------------------------------------------
# Instantiate discovered provider
# ---------------------------------------------------------------------------

def test_instantiate_discovered_provider(tmp_path):
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    registry = _registry(tmp_path)
    registry.discover()
    cls = registry.get_provider_class("dummy")
    instance = cls(api_key="sk-test", model="v2")
    reply = instance.chat([{"role": "user", "content": "hello"}])
    assert reply == "[dummy] ok"


def test_discover_idempotent(tmp_path):
    """Calling discover() twice should not duplicate entries."""
    _write_plugin(tmp_path, "dummy.py", VALID_PLUGIN)
    registry = _registry(tmp_path)
    registry.discover()
    registry.discover()
    assert len(registry.list_registered()) == 1


# ---------------------------------------------------------------------------
# RegisteredProvider
# ---------------------------------------------------------------------------

def test_registered_provider_description():
    class MyProvider(LLMProvider):
        name = "test"
    reg = RegisteredProvider(name="test", cls=MyProvider, source_file="test.py")
    assert "test" in reg.description


def test_registered_provider_description_no_doc():
    reg = RegisteredProvider(
        name="test",
        cls=type("NoDoc", (LLMProvider,), {"name": "test"}),
        source_file="test.py",
    )
    assert "Custom provider" in reg.description
