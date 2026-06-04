"""mmi.core.providers —— 预置模型商 catalog + 工厂。

5 个国内商 + 1 个自定义(后续要扩海外商再补)。

API 风格:多数国内商只有 OpenAI 兼容;DeepSeek 和 MiniMax 同时支持
Anthropic 协议。`preferred_api_style` 标首选风格,model_fetcher 优先用
首选拉模型列表,失败再退回另一种(如果该商支持)。

API 文档来源(各商官方 docs,2026-06 验证):
  DeepSeek:  https://api-docs.deepseek.com/
              Anthropic 端点:https://api.deepseek.com/anthropic
  MiniMax:   https://api.minimaxi.com/anthropic
  智谱 GLM:  https://open.bigmodel.cn/dev/api
  Kimi:      https://platform.moonshot.cn/docs/intro
  Qwen:      https://help.aliyun.com/zh/model-studio/developer-reference/
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "ProviderInfo",
    "PROVIDERS",
    "CUSTOM_PROVIDER_ID",
    "get_provider",
    "list_providers",
    "is_custom_provider",
]


ApiStyle = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class ProviderInfo:
    """单个模型商的接入信息。"""

    id: str                       # 内部 id,小写英文,如 "deepseek"
    name: str                     # 显示名,如 "DeepSeek"
    preferred_api_style: ApiStyle # 首选 API 风格
    base_url: str                 # 默认 base_url(用户可改)
    anthropic_base_url: str = ""  # Anthropic 端点(仅 DeepSeek / MiniMax)
    api_key_url: str = ""         # 在哪里拿 key(给用户提示)
    api_key_env: str = ""         # 兼容 env var 名(用户可放环境变量)
    notes: str = ""               # 备注


# 预置 5 个国内商
PROVIDERS: tuple[ProviderInfo, ...] = (
    ProviderInfo(
        id="deepseek",
        name="DeepSeek",
        preferred_api_style="anthropic",   # 同时支持 Anthropic,优先用
        base_url="https://api.deepseek.com",
        anthropic_base_url="https://api.deepseek.com/anthropic",
        api_key_url="https://platform.deepseek.com/api_keys",
        api_key_env="DEEPSEEK_API_KEY",
        notes="Anthropic 端点已验证;OpenAI 兼容也支持(https://api.deepseek.com/v1)",
    ),
    ProviderInfo(
        id="minimax",
        name="MiniMax (MiniMax)",
        preferred_api_style="anthropic",
        base_url="https://api.minimaxi.com/v1",
        anthropic_base_url="https://api.minimaxi.com/anthropic",
        api_key_url="https://api.minimaxi.com/user-center/basic-information/interface-key",
        api_key_env="MiniMax_API_KEY",
        notes="Anthropic 端点 https://api.minimaxi.com/anthropic",
    ),
    ProviderInfo(
        id="glm",
        name="智谱 GLM",
        preferred_api_style="openai",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        api_key_url="https://bigmodel.cn/user-center/apikeys",
        api_key_env="GLM_API_KEY",
        notes="OpenAI 兼容",
    ),
    ProviderInfo(
        id="moonshot",
        name="Moonshot (Kimi)",
        preferred_api_style="openai",
        base_url="https://api.moonshot.cn/v1",
        api_key_url="https://platform.moonshot.cn/console/api-keys",
        api_key_env="MOONSHOT_API_KEY",
        notes="OpenAI 兼容",
    ),
    ProviderInfo(
        id="qwen",
        name="通义千问 (Qwen / DashScope)",
        preferred_api_style="openai",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_url="https://dashscope.console.aliyun.com/apiKey",
        api_key_env="DASHSCOPE_API_KEY",
        notes="OpenAI 兼容模式",
    ),
)


# 自定义 provider 哨兵(用 list_providers() 不会列出来,走单独路径)
CUSTOM_PROVIDER_ID = "custom"


def get_provider(provider_id: str) -> ProviderInfo:
    """按 id 找 provider。"custom" 抛 ValueError(自定义走 _custom_provider_factory)。

    Raises:
        ValueError: 找不到 / 是 custom
    """
    if provider_id == CUSTOM_PROVIDER_ID:
        raise ValueError(
            "custom provider needs base_url + api_style from user "
            "(see _custom_provider_factory)"
        )
    for p in PROVIDERS:
        if p.id == provider_id.lower():
            return p
    avail = ", ".join(list(p.id for p in PROVIDERS) + [CUSTOM_PROVIDER_ID])
    raise ValueError(f"unknown provider: {provider_id!r}. Available: {avail}")


def list_providers() -> tuple[ProviderInfo, ...]:
    """返回所有预置 provider(不含 custom)。"""
    return PROVIDERS


def is_custom_provider(provider_id: str) -> bool:
    return provider_id == CUSTOM_PROVIDER_ID


# ---------------------------------------------------------------------------
# 自定义 provider 工厂
# ---------------------------------------------------------------------------


def make_custom_provider(
    base_url: str,
    preferred_api_style: ApiStyle = "openai",
) -> ProviderInfo:
    """用户手填 base_url 时构造一个 ProviderInfo(不写 catalog)。"""
    if not base_url or not base_url.strip():
        raise ValueError("custom provider 必须填 base_url")
    return ProviderInfo(
        id=CUSTOM_PROVIDER_ID,
        name="自定义",
        preferred_api_style=preferred_api_style,
        base_url=base_url.strip().rstrip("/"),
        anthropic_base_url="",   # 自定义不预填;用户用同 base_url 试
        api_key_url="(用户自己提供)",
        api_key_env="",
        notes="custom",
    )
