"""mmi.core.llm.factory —— 默认 provider 工厂。

依赖项:_types, base, 所有 provider, anthropic, openai。
被依赖:__init__.py re-export。
"""

from __future__ import annotations

import os

from mmi.core.llm._types import LLMError
from mmi.core.llm.anthropic import AnthropicLLMProvider
from mmi.core.llm.base import LLMProvider
from mmi.core.llm.echo import EchoLLMProvider
from mmi.core.llm.openai import OpenAILLMProvider


def _build_provider_from_config() -> LLMProvider:
    """按 ~/.mmi/config.toml [llm] 构造 provider(供 get_default_provider 优先用)。

    支持三种来源:
      1. 预置 provider (deepseek, glm, qwen, minimax)
      2. 自定义插件 provider (~/.mmi/providers/*.py)
      3. custom provider (用户手填 base_url)
    """
    from mmi.core import config as cfg_mod
    from mmi.core import providers as prov_mod
    from mmi.core.provider_registry import ProviderRegistry

    llm = cfg_mod.get_llm_config()
    provider_id = llm.get("provider", "").strip().lower()
    api_key = cfg_mod.resolve_api_key(provider_id)
    base_url = llm.get("base_url", "").strip() or None
    model = llm.get("model", "").strip() or "gpt-4o-mini"
    api_style = llm.get("api_style", "").strip()

    if not provider_id or not api_key:
        return None  # 没配完整,回退到 env

    # --- 尝试自定义插件 ---
    registry = ProviderRegistry.get_instance()
    registry.discover()  # 扫描 ~/.mmi/providers/
    plugin_cls = registry.get_provider_class(provider_id)
    if plugin_cls is not None:
        try:
            return plugin_cls(api_key=api_key, base_url=base_url, model=model)
        except Exception:
            pass  # 插件构造失败,继续走预置逻辑

    # --- 预置 provider ---
    if not api_style:
        try:
            info = prov_mod.get_provider(provider_id)
            api_style = info.preferred_api_style
        except (ValueError, KeyError):
            api_style = "openai"
    try:
        if api_style == "anthropic":
            return AnthropicLLMProvider(api_key=api_key, base_url=base_url, model=model)
        return OpenAILLMProvider(api_key=api_key, base_url=base_url, model=model)
    except LLMError:
        return None


_DEFAULT_LLM: LLMProvider | None = None


def get_default_provider() -> LLMProvider:
    """从 config / env 推断应该用哪个 provider。

    优先级:
      1. ~/.mmi/config.toml [llm] 完整配置(provider + api_key + model)
      2. 环境变量 OPENAI_API_KEY → OpenAILLMProvider
      3. 环境变量 ANTHROPIC_API_KEY → AnthropicLLMProvider
      4. 兜底 → EchoLLMProvider

    返回的实例会缓存(单例),节省重复构造。
    测试时用 reset_default_provider_for_test() 重置。
    """
    global _DEFAULT_LLM
    if _DEFAULT_LLM is not None:
        return _DEFAULT_LLM

    # 1) config.toml
    configured = _build_provider_from_config()
    if configured is not None:
        _DEFAULT_LLM = configured
        return _DEFAULT_LLM

    # 2/3) env vars
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            _DEFAULT_LLM = AnthropicLLMProvider(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                model=os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            )
            return _DEFAULT_LLM
        except LLMError:
            pass
    if os.environ.get("OPENAI_API_KEY"):
        try:
            _DEFAULT_LLM = OpenAILLMProvider(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL"),
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            )
            return _DEFAULT_LLM
        except LLMError:
            pass

    # 4) 兜底 echo
    _DEFAULT_LLM = EchoLLMProvider()
    return _DEFAULT_LLM


def reset_default_provider_for_test() -> None:
    """测试用:清空缓存的 provider。"""
    global _DEFAULT_LLM
    _DEFAULT_LLM = None
