"""tests/test_providers.py —— core.providers + core.model_fetcher 单元测试。

覆盖:
  - 4 个预置 provider catalog(id/name/base_url/preferred_api_style 正确)
  - R8.5.3:Kimi (moonshot) 从预置移除 — 官方参数不匹配,要走自定义
  - get_provider 找得到 / 找不到 / 是 custom 时抛
  - make_custom_provider 必填 base_url 校验
  - model_fetcher:mock HTTP 走通 OpenAI 风格响应
  - model_fetcher:mock HTTP 走通 Anthropic 风格响应
  - model_fetcher:401 / 404 / 非 JSON / 鉴权失败抛 ModelFetchError
  - model_fetcher:首选失败 → 回退;首选成功不触发回退
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from mmi.core import model_fetcher, providers


# ---------------------------------------------------------------------------
# providers catalog
# ---------------------------------------------------------------------------


def test_provider_count():
    """4 个预置 + custom 单独处理(R8.5.3 起 Kimi 移除)。"""
    assert len(providers.list_providers()) == 4


def test_provider_ids_unique():
    ids = [p.id for p in providers.list_providers()]
    assert len(set(ids)) == 4


def test_deepseek_uses_anthropic():
    p = providers.get_provider("deepseek")
    assert p.preferred_api_style == "anthropic"
    # base_url 是 OpenAI 端点,anthropic 端点单独存
    assert "anthropic" in p.anthropic_base_url
    assert p.anthropic_base_url == "https://api.deepseek.com/anthropic"


def test_minimax_uses_anthropic():
    p = providers.get_provider("minimax")
    assert p.preferred_api_style == "anthropic"
    # base_url 是 OpenAI 端点,anthropic 端点单独存
    assert "anthropic" in p.anthropic_base_url
    assert p.anthropic_base_url == "https://api.minimaxi.com/anthropic"


def test_glm_uses_openai():
    p = providers.get_provider("glm")
    assert p.preferred_api_style == "openai"


def test_qwen_uses_openai():
    p = providers.get_provider("qwen")
    assert p.preferred_api_style == "openai"


def test_get_provider_case_insensitive():
    assert providers.get_provider("DeepSeek").id == "deepseek"
    assert providers.get_provider("QWEN").id == "qwen"


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError, match="unknown provider"):
        providers.get_provider("no-such")


def test_get_provider_custom_raises():
    with pytest.raises(ValueError, match="custom provider needs"):
        providers.get_provider("custom")


def test_is_custom_provider():
    assert providers.is_custom_provider("custom") is True
    assert providers.is_custom_provider("openai") is False


def test_make_custom_provider_requires_base_url():
    with pytest.raises(ValueError, match="必须填 base_url"):
        providers.make_custom_provider("")


def test_make_custom_provider_default_style():
    p = providers.make_custom_provider("https://example.com/v1")
    assert p.id == "custom"
    assert p.preferred_api_style == "openai"
    assert p.base_url == "https://example.com/v1"  # 末尾 / 去掉


def test_make_custom_provider_anthropic_style():
    p = providers.make_custom_provider(
        "https://api.example.com/anthropic/", preferred_api_style="anthropic"
    )
    assert p.preferred_api_style == "anthropic"
    assert p.base_url == "https://api.example.com/anthropic"


# ---------------------------------------------------------------------------
# model_fetcher:URL / header 构造
# ---------------------------------------------------------------------------


def test_models_url_anthropic_with_explicit_base():
    """anthropic 走 anthropic_base_url(DeepSeek 的 case)。"""
    p = providers.get_provider("deepseek")
    url = model_fetcher._models_url(p, "anthropic")
    assert url == "https://api.deepseek.com/anthropic/v1/models"


def test_models_url_openai_with_v1_suffix():
    p = providers.get_provider("qwen")
    url = model_fetcher._models_url(p, "openai")
    assert url == "https://dashscope.aliyuncs.com/compatible-mode/v1/models"


def test_auth_headers_anthropic():
    h = model_fetcher._auth_headers("anthropic", "sk-test")
    assert h["x-api-key"] == "sk-test"
    assert "anthropic-version" in h


def test_auth_headers_openai():
    h = model_fetcher._auth_headers("openai", "sk-test")
    assert h["Authorization"] == "Bearer sk-test"


# ---------------------------------------------------------------------------
# model_fetcher:HTTP 行为(monkey-patch 注入 client)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, body: Any, text: str = ""):
        self.status_code = status_code
        self._body = body
        self.text = text or json.dumps(body)

    def json(self):
        if isinstance(self._body, (dict, list)):
            return self._body
        raise json.JSONDecodeError("not json", "x", 0)


class _FakeClient:
    """替 httpx.Client;支持多次 get 返不同响应(模拟回退场景)。

    factory 只创建一次,后续 fetch_models 的 with Client() 用同一实例。
    """

    def __init__(self, *, responses: list[tuple[int, Any]] | None = None):
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, headers=None):
        self.calls.append({"url": url, "headers": headers or {}})
        if not self.responses:
            return _FakeResponse(500, {})
        status, body = self.responses.pop(0)
        return _FakeResponse(status, body)


def _make_fake_client_factory(responses: list[tuple[int, Any]]):
    """返一个 factory —— fetch_models 内部用一次 Client(我们的 with 进单实例)"""
    state = {"client": _FakeClient(responses=list(responses))}
    def _factory(*a, **kw):
        return state["client"]
    return _factory


def test_fetch_openai_style_success():
    """OpenAI 兼容 provider 拉模型走通。"""
    fake = _make_fake_client_factory([(
        200,
        {
            "object": "list",
            "data": [
                {"id": "qwen-turbo", "object": "model", "owned_by": "aliyun"},
                {"id": "qwen-max", "object": "model", "owned_by": "aliyun"},
            ],
        },
    )])
    p = providers.get_provider("qwen")
    out = model_fetcher.fetch_models(p, "sk-test", client_factory=fake)
    ids = [m.id for m in out]
    assert ids == ["qwen-max", "qwen-turbo"]  # sorted


def test_fetch_anthropic_style_success():
    """Anthropic 端点拉模型。"""
    fake = _make_fake_client_factory([(
        200,
        {
            "data": [
                {"id": "deepseek-chat", "display_name": "DeepSeek Chat", "type": "model"},
                {"id": "deepseek-coder", "display_name": "DeepSeek Coder", "type": "model"},
            ],
            "has_more": False,
        },
    )])
    p = providers.get_provider("deepseek")
    out = model_fetcher.fetch_models(p, "sk-test", client_factory=fake)
    ids = [m.id for m in out]
    assert ids == ["deepseek-chat", "deepseek-coder"]


def test_fetch_401_raises():
    model_fetcher.clear_cache()
    fake = _make_fake_client_factory([(401, {"err": "bad key"})])
    p = providers.get_provider("qwen")
    with pytest.raises(model_fetcher.ModelFetchError, match="鉴权失败"):
        model_fetcher.fetch_models(p, "sk-bad", client_factory=fake)


def test_fetch_404_raises():
    fake = _make_fake_client_factory([(404, {"err": "no endpoint"})])
    p = providers.get_provider("qwen")
    with pytest.raises(model_fetcher.ModelFetchError, match="端点不存在"):
        model_fetcher.fetch_models(p, "sk-x", client_factory=fake)


def test_fetch_invalid_json_raises():
    """返回 200 但 body 不是 JSON,应抛。"""

    class _BadJsonClient(_FakeClient):
        def get(self, url, headers=None):
            resp = _FakeResponse(200, {})
            resp.json = lambda: (_ for _ in ()).throw(
                json.JSONDecodeError("x", "y", 0)
            )
            return resp

    state = {"client": _BadJsonClient()}
    def _factory(*a, **kw):
        return state["client"]

    p = providers.get_provider("qwen")
    with pytest.raises(model_fetcher.ModelFetchError, match="不是合法 JSON"):
        model_fetcher.fetch_models(p, "sk", client_factory=_factory)


def test_fetch_empty_data_raises():
    fake = _make_fake_client_factory([(200, {"data": []})])
    p = providers.get_provider("qwen")
    with pytest.raises(model_fetcher.ModelFetchError, match="未解析到任何 model id"):
        model_fetcher.fetch_models(p, "sk", client_factory=fake)


def test_fetch_empty_key_raises():
    p = providers.get_provider("qwen")
    with pytest.raises(model_fetcher.ModelFetchError, match="api_key 为空"):
        model_fetcher.fetch_models(p, "")


def test_fetch_preferred_anthropic_falls_back_to_openai():
    """首选 anthropic 失败 → 回退 openai(成功)。"""
    # 第一次 anthropic 401,第二次 openai 200
    fake = _make_fake_client_factory([
        (401, {"err": "no anthropic key"}),
        (200, {"data": [{"id": "gpt-4o-mini", "object": "model"}]}),
    ])
    p = providers.get_provider("deepseek")
    out = model_fetcher.fetch_models(p, "sk", client_factory=fake)
    assert [m.id for m in out] == ["gpt-4o-mini"]


def test_fetch_preferred_anthropic_fails_no_fallback_for_openai_providers():
    """OpenAI-only provider(GLM)首选失败,无可回退,直接抛。"""
    fake = _make_fake_client_factory([(404, {"err": "no"})])
    p = providers.get_provider("glm")
    with pytest.raises(model_fetcher.ModelFetchError, match="端点不存在"):
        model_fetcher.fetch_models(p, "sk", client_factory=fake)


def test_fetch_dedupes_models():
    """API 返回重复 id → 去重。"""
    fake = _make_fake_client_factory([(
        200,
        {
            "data": [
                {"id": "a", "object": "model"},
                {"id": "a", "object": "model"},  # duplicate
                {"id": "b", "object": "model"},
            ],
        },
    )])
    p = providers.get_provider("qwen")
    out = model_fetcher.fetch_models(p, "sk", client_factory=fake)
    ids = [m.id for m in out]
    assert ids == ["a", "b"]
