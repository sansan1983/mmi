"""mmi.core.model_fetcher —— 从模型商拉取可用模型列表。

支持 OpenAI 兼容 + Anthropic 原生两类(都暴露 /v1/models 端点)。
返回去重 + 排序后的 model id 列表。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from .providers import ApiStyle, ProviderInfo

__all__ = [
    "ModelInfo",
    "fetch_models",
    "ModelFetchError",
]


@dataclass
class ModelInfo:
    """单条模型信息(provider 不一定全给字段,尽力解析)。"""

    id: str
    display_name: str = ""
    created: int = 0
    owned_by: str = ""


class ModelFetchError(Exception):
    """拉取模型失败(网络/鉴权/协议错误)。"""


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def fetch_models(
    provider: ProviderInfo,
    api_key: str,
    *,
    timeout_s: float = 15.0,
    client_factory: Any = None,    # 测试用:替换 httpx.Client
    style_override: ApiStyle | None = None,    # wizard 可强制覆盖
) -> list[ModelInfo]:
    """从 provider 拉可用模型列表。

    策略:按 `provider.preferred_api_style` 试,失败则回退到另一种风格
    (Anthropic 优先时回退到 OpenAI;OpenAI 优先时不回退,因为国内商
    多数只有 OpenAI 兼容)。

    `style_override` 强制单跑一种风格(不回退),供 wizard 在用户选
    完协议后调用。

    Args:
        provider: 预置 provider 信息
        api_key: 用户填的 API key
        timeout_s: HTTP 超时
        client_factory: 注入 httpx.Client 类(测试用,默认 None → 用真 httpx.Client)
        style_override: 强制单跑这一种风格,不回退

    Returns:
        去重 + 排序后的 ModelInfo 列表

    Raises:
        ModelFetchError: 网络/鉴权/JSON 解析失败,且无回退可走
    """
    if not api_key or not api_key.strip():
        raise ModelFetchError("api_key 为空,无法拉取模型列表")

    if style_override is not None:
        return _fetch_with_style(
            provider, api_key, style=style_override,
            timeout_s=timeout_s, client_factory=client_factory,
        )

    preferred = provider.preferred_api_style
    fallback: ApiStyle | None = (
        "openai" if preferred == "anthropic" else None
    )

    last_err: ModelFetchError | None = None
    for style in (preferred, fallback):
        if style is None:
            break
        try:
            return _fetch_with_style(provider, api_key, style=style,
                                     timeout_s=timeout_s, client_factory=client_factory)
        except ModelFetchError as e:
            last_err = e
            if fallback is None:
                raise
            # 继续试 fallback
            continue
    # 走到这说明 fallback 也失败
    if last_err is not None:
        raise last_err
    raise ModelFetchError("unknown fetch error")


def _fetch_with_style(
    provider: ProviderInfo,
    api_key: str,
    *,
    style: ApiStyle,
    timeout_s: float,
    client_factory: Any,
) -> list[ModelInfo]:
    """单跑一种风格。失败抛 ModelFetchError。"""
    url = _models_url(provider, style)
    headers = _auth_headers(style, api_key)

    Client = client_factory or httpx.Client
    try:
        with Client(timeout=timeout_s) as client:
            resp = client.get(url, headers=headers)
    except httpx.HTTPError as e:
        raise ModelFetchError(f"网络错误: {e}") from e

    if resp.status_code == 401 or resp.status_code == 403:
        raise ModelFetchError(
            f"鉴权失败 (HTTP {resp.status_code}, style={style}): 请检查 api_key"
        )
    if resp.status_code == 404:
        raise ModelFetchError(
            f"端点不存在 (HTTP 404, style={style}): {url}"
        )
    if resp.status_code >= 400:
        body_snip = (resp.text or "")[:200]
        raise ModelFetchError(
            f"HTTP {resp.status_code} (style={style}): {body_snip}"
        )

    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        raise ModelFetchError(f"返回不是合法 JSON: {e}") from e

    return _parse_models(data, style)


# ---------------------------------------------------------------------------
# 内部:URL / Header / 解析
# ---------------------------------------------------------------------------


def _models_url(provider: ProviderInfo, style: ApiStyle) -> str:
    """根据 provider + style 拼 /v1/models 端点。"""
    if style == "anthropic":
        base = (provider.anthropic_base_url or provider.base_url).rstrip("/")
    else:
        base = provider.base_url.rstrip("/")
    if style == "anthropic":
        # Anthropic: {base}/v1/models
        return f"{base}/v1/models"
    # OpenAI 兼容
    parsed = urlparse(base)
    if parsed.path.endswith("/v1") or parsed.path.endswith("/v1/"):
        return f"{base}/models"
    return f"{base}/v1/models"


def _auth_headers(style: ApiStyle, api_key: str) -> dict[str, str]:
    if style == "anthropic":
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _parse_models(data: Any, style: ApiStyle) -> list[ModelInfo]:
    """从响应 JSON 抠 model id + 字段。两种风格都兼容。"""
    if not isinstance(data, dict):
        raise ModelFetchError(f"返回根不是 dict,实际 {type(data).__name__}")
    items = data.get("data")
    if not isinstance(items, list):
        raise ModelFetchError(
            f"返回 data 字段不是 list,实际 {type(items).__name__ if items is not None else 'None'}"
        )

    seen: set[str] = set()
    out: list[ModelInfo] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mid = item.get("id")
        if not isinstance(mid, str) or not mid or mid in seen:
            continue
        seen.add(mid)
        out.append(ModelInfo(
            id=mid,
            display_name=str(item.get("display_name", "") or ""),
            created=int(item.get("created", 0) or 0),
            owned_by=str(item.get("owned_by", "") or ""),
        ))

    if not out:
        raise ModelFetchError(f"未解析到任何 model id(style={style}, 返回 {len(items)} 条)")
    out.sort(key=lambda m: m.id)
    return out
