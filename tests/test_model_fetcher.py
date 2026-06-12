"""tests/test_model_fetcher.py —— P2-5 本地缓存测试。"""

from __future__ import annotations

import sys
import time as _time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core.model_fetcher import (
    _ModelCache,
    clear_cache,
    fetch_models,
    ModelFetchError,
    ModelInfo,
)
from mmi.core.providers import ApiStyle, ProviderInfo


# ---------------------------------------------------------------------------
# Mock HTTP
# ---------------------------------------------------------------------------

_FAKE_MODELS = [
    {"id": "gpt-4o", "created": 1710, "owned_by": "openai"},
    {"id": "gpt-4o-mini", "created": 1711, "owned_by": "openai"},
]


class _HTTPResp:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._json


class _FakeClient:
    def __init__(self, resp, *, timeout=None):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, url, headers=None):
        return self._resp


class _ClientFactory:
    """持有固定 resp 的 client factory。"""

    def __init__(self, resp):
        self._resp = resp

    def __call__(self, *, timeout=None, **kw):
        return _FakeClient(self._resp, timeout=timeout)


class _FakeProvider(ProviderInfo):
    def __init__(self, name="test-provider", base_url="https://api.test.com"):
        super().__init__(
            id=name, name=name, base_url=base_url,
            api_key_env="TEST_API_KEY", preferred_api_style="openai",
        )


# ---------------------------------------------------------------------------
# _ModelCache
# ---------------------------------------------------------------------------

def test_cache_miss_returns_none():
    cache = _ModelCache(ttl_s=60.0)
    assert cache.get("nonexistent") is None


def test_cache_hit_returns_models():
    models = [ModelInfo(id="gpt-4o")]
    cache = _ModelCache(ttl_s=60.0)
    cache.set("openai", models)
    result = cache.get("openai")
    assert result == models


def test_cache_returns_copy_not_internal_ref():
    models = [ModelInfo(id="gpt-4o")]
    cache = _ModelCache(ttl_s=60.0)
    cache.set("openai", models)
    result = cache.get("openai")
    result.append(ModelInfo(id="gpt-4o-mini"))
    result2 = cache.get("openai")
    assert len(result2) == 1


def test_cache_expired_returns_none():
    cache = _ModelCache(ttl_s=0.1)
    cache.set("openai", [ModelInfo(id="gpt-4o")])
    _time.sleep(0.2)
    assert cache.get("openai") is None


def test_cache_clear():
    cache = _ModelCache(ttl_s=60.0)
    cache.set("openai", [ModelInfo(id="gpt-4o")])
    cache.set("anthropic", [ModelInfo(id="claude-3")])
    cache.clear()
    assert cache.get("openai") is None
    assert cache.get("anthropic") is None


# ---------------------------------------------------------------------------
# fetch_models + 缓存集成
# ---------------------------------------------------------------------------

def test_fetch_models_caches_on_success():
    clear_cache()
    resp = _HTTPResp({"data": _FAKE_MODELS})
    provider = _FakeProvider()
    factory = _ClientFactory(resp)

    call_count = [0]

    def counting_get(self, url, headers=None):
        call_count[0] += 1
        return resp

    with patch.object(_FakeClient, "get", counting_get):
        r1 = fetch_models(provider, "key", client_factory=factory)
        r2 = fetch_models(provider, "key", client_factory=factory)

    assert call_count[0] == 1
    assert [m.id for m in r1] == [m.id for m in r2]


def test_fetch_models_bypasses_cache_with_style_override():
    clear_cache()
    resp = _HTTPResp({"data": _FAKE_MODELS})
    provider = _FakeProvider()
    factory = _ClientFactory(resp)

    call_count = [0]

    def counting_get(self, url, headers=None):
        call_count[0] += 1
        return resp

    with patch.object(_FakeClient, "get", counting_get):
        fetch_models(provider, "key", client_factory=factory,
                     style_override="openai")
        fetch_models(provider, "key", client_factory=factory,
                     style_override="openai")

    assert call_count[0] == 2


def test_fetch_models_different_provider_separate_cache():
    clear_cache()

    resp_a = _HTTPResp({"data": [{"id": "model-a"}]})
    resp_b = _HTTPResp({"data": [{"id": "model-b"}]})

    provider_a = _FakeProvider(name="provider-a", base_url="https://a.com")
    provider_b = _FakeProvider(name="provider-b", base_url="https://b.com")

    call_count = [0]

    def counting_get(self, url, headers=None):
        call_count[0] += 1
        if "a.com" in url:
            return resp_a
        return resp_b

    with patch.object(_FakeClient, "get", counting_get):
        r_a = fetch_models(provider_a, "key",
                           client_factory=_ClientFactory(resp_a))
        r_b = fetch_models(provider_b, "key",
                           client_factory=_ClientFactory(resp_b))
        r_a2 = fetch_models(provider_a, "key",
                            client_factory=_ClientFactory(resp_a))

    assert call_count[0] == 2
    assert r_a2[0].id == "model-a"


def test_clear_cache_exported():
    clear_cache()