"""mmi.core.config —— 用户配置文件读写。

ARCHITECTURE.md §3.5.8：~/.mmi/config.toml 是用户偏好（disabled 模块、
默认 LLM、第三方 provider 配置等）的存储点。

Phase 5 范围（最小集合）：
  - get_default_model() / set_default_model()
  - 读 ~/.mmi/config.toml；缺省值 "gpt-4o-mini"
  - 配置文件不存在 / 解析失败 → 静默回退到缺省值

设计原则：
  - 不强制配置文件存在：第一次跑时自动写一份最小 config
  - 用 PyYAML（不引 tomli / tomllib，保持依赖最少）
  - 任何 I/O 异常（权限、磁盘）→ 静默回退到缺省值 + 不抛（让 UI 能继续工作）
"""

from __future__ import annotations

import os
import re
from typing import Any

import yaml

from . import paths
from .providers import get_provider

__all__ = [
    "get_default_model",
    "set_default_model",
    "validate_model_name",
    "load_config",
    "save_config",
    "DEFAULT_MODEL",
    "get_llm_config",
    "set_llm_config",
    "resolve_api_key",
    "mask_api_key",
    "API_KEY_SOURCE_ENV",
    "API_KEY_SOURCE_KEYRING",
    "API_KEY_SOURCE_PLAIN",
]


# 缺省模型：与 OpenAI 客户端 get_default_provider 默认值一致
DEFAULT_MODEL = "gpt-4o-mini"


# 模型名校验：长度 1-128，常见模型名字符集
# 覆盖：gpt-4o-mini / claude-3-5-sonnet / qwen2.5-7b / deepseek_chat
# 不允许：空格 / 路径分隔（/）/ URL 风格（:）/ shell 特殊（$ ; 等）/ 非 ASCII
_MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")

# API Key 来源标记（供 config show 遮蔽显示）
API_KEY_SOURCE_ENV = "env"
API_KEY_SOURCE_KEYRING = "keyring"
API_KEY_SOURCE_PLAIN = "plain"

# 环境变量引用语法：config.toml 中写 ${VAR_NAME}，运行时从 os.environ 取
_ENV_REF_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}\s*$")


# ---------------------------------------------------------------------------
# 低层：整份 config 读写
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """读 ~/.mmi/config.toml。失败回退到空 dict（调用方走缺省）。

    Returns:
        dict: 配置文件内容；不存在 / 解析失败 → {}
    """
    cfg_path = paths.get_config_path()
    if not cfg_path.exists():
        return {}
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_config(cfg: dict[str, Any]) -> bool:
    """写 ~/.mmi/config.toml（覆盖）。失败不抛，返回 False。

    Returns:
        True 写盘成功；False 任何 OSError
    """
    try:
        paths.ensure_dirs()
        with paths.get_config_path().open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                cfg,
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=4096,
            )
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# 高层：具体字段读写
# ---------------------------------------------------------------------------


def get_default_model() -> str:
    """返回当前默认 LLM 模型名。

    优先级：
      1. 配置文件 llm.model
      2. 环境变量 OPENAI_MODEL
      3. DEFAULT_MODEL（"gpt-4o-mini"）
    """
    cfg = load_config()
    llm_section = cfg.get("llm", {})
    if isinstance(llm_section, dict):
        m = llm_section.get("model")
        if isinstance(m, str) and m.strip():
            return m.strip()
    env_m = os.environ.get("OPENAI_MODEL")
    if env_m and env_m.strip():
        return env_m.strip()
    return DEFAULT_MODEL


def set_default_model(name: str) -> bool:
    """把模型名写到 config.toml 的 [llm].model。

    行为：
      - 校验 name（validate_model_name，长度 1-128，字符集合法）
      - 读现有 config（保留其它字段）
      - 设置 llm.model = name
      - 写回
      - 失败 → False（不抛）

    注意：只校验**格式**合法，不验证模型是否真实存在。
    """
    if not validate_model_name(name):
        return False
    cfg = load_config()
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg["llm"] = {}
    cfg["llm"]["model"] = name.strip()
    return save_config(cfg)


def validate_model_name(name: str) -> bool:
    """校验模型名字符串（不验证模型是否存在）。

    规则：
      - 非空（strip 后）
      - 长度 1-128
      - 字符集：字母、数字、`._-`（覆盖 gpt-4o-mini / claude-3-5-sonnet
        / qwen2.5-7b 等常见格式；保守起见拒绝 / : + 等特殊字符）

    Returns:
        True = 格式合法；False = 不合法
    """
    if not name or not name.strip():
        return False
    return bool(_MODEL_NAME_PATTERN.match(name.strip()))


# ---------------------------------------------------------------------------
# 完整 LLM 配置(供交互式 config wizard 写入)
# ---------------------------------------------------------------------------


def get_llm_config() -> dict[str, str]:
    """读 [llm] section 的全字段(供 wizard 显示当前状态)。

    Returns:
        dict with keys: provider, base_url, api_key, model, api_style
        缺失字段返回空字符串(不抛)
    """
    cfg = load_config()
    section = cfg.get("llm", {})
    if not isinstance(section, dict):
        section = {}
    return {
        "provider": str(section.get("provider", "") or ""),
        "base_url": str(section.get("base_url", "") or ""),
        "api_key": str(section.get("api_key", "") or ""),
        "model": str(section.get("model", "") or ""),
        "api_style": str(section.get("api_style", "") or ""),
    }


def set_llm_config(
    *,
    provider: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    api_style: str | None = None,
) -> bool:
    """更新 [llm] section。None 的字段保留旧值。

    注意:此处不写 env var,key 持久化在 config.toml(用户显式选)。
    写盘失败返回 False(不抛)。
    """
    cfg = load_config()
    if "llm" not in cfg or not isinstance(cfg.get("llm"), dict):
        cfg["llm"] = {}
    section = cfg["llm"]
    if provider is not None:
        section["provider"] = provider.strip()
    if base_url is not None:
        section["base_url"] = base_url.strip()
    if api_key is not None:
        section["api_key"] = api_key.strip()
    if model is not None:
        section["model"] = model.strip()
    if api_style is not None:
        section["api_style"] = api_style.strip()
    return save_config(cfg)


def resolve_api_key(provider: str | None) -> str:
    """按 provider 解析 api_key,优先级:
      1. config.toml [llm].api_key(用户显式配)
         - 若为 ${ENV_VAR} 格式 → 从 os.environ 取
         - 若为 keyring:// 格式 → 从 keyring 取
      2. 环境变量 <PROVIDER>_API_KEY(回退)
      3. 空字符串(用户得配)

    provider 为 None 或未知 → 只查 config。
    """
    cfg = get_llm_config()
    raw_key = cfg["api_key"]

    # 解析 ${ENV_VAR} 语法
    m = _ENV_REF_PATTERN.match(raw_key)
    if m:
        env_name = m.group(1)
        return os.environ.get(env_name, "")

    # 解析 keyring:// 语法
    if raw_key.startswith("keyring://"):
        keyring_key = raw_key[len("keyring://"):]
        return _get_keyring_password(keyring_key)

    # 明文 key（向后兼容）
    if raw_key:
        return raw_key

    # 无 config key → 回退到环境变量
    if provider:
        try:
            info = get_provider(provider)
            env_k = os.environ.get(info.api_key_env, "")
            if env_k:
                return env_k
        except ValueError:
            pass
        # provider 未知 → 也尝试通用 <PROVIDER>_API_KEY（兼容性兜底）
        generic_env = f"{provider.upper()}_API_KEY"
        env_k = os.environ.get(generic_env, "")
        if env_k:
            return env_k
    return ""


def _get_keyring_password(service: str) -> str:
    """从 keyring 取密码（失败返回空字符串，不抛）。"""
    try:
        import keyring as _kr
        return _kr.get_password("mmi", service) or ""
    except Exception:
        return ""



def _set_keyring_password(service: str, password: str) -> bool:
    """存密码到 keyring（失败返回 False，不抛）。"""
    try:
        import keyring as _kr
        _kr.set_password("mmi", service, password)
        return True
    except Exception:
        return False


def mask_api_key(key: str, visible_chars: int = 3) -> str:
    """把 api_key 遮蔽为 sk-***XXXX（安全显示）。

    Args:
        key: 原始 api_key（空时返回空字符串）。
        visible_chars: 末尾可见字符数（默认 3）。

    Returns:
        遮蔽后的字符串，例如 "sk-***abc" 或 "sk-***"（key 过短时）。
    """
    if not key:
        return ""
    prefix = "sk-"
    if key.startswith(prefix):
        key_body = key[len(prefix):]
    else:
        key_body = key
    if len(key_body) <= visible_chars:
        return "sk-***"
    return f"sk-***{key_body[-visible_chars:]}"


def get_api_key_source(key: str) -> str:
    """判断 api_key 的存储来源类型。

    Returns:
        API_KEY_SOURCE_ENV | API_KEY_SOURCE_KEYRING | API_KEY_SOURCE_PLAIN
    """
    if not key:
        return API_KEY_SOURCE_PLAIN
    if _ENV_REF_PATTERN.match(key):
        return API_KEY_SOURCE_ENV
    if key.startswith("keyring://"):
        return API_KEY_SOURCE_KEYRING
    return API_KEY_SOURCE_PLAIN


def store_api_key(api_key: str, *, use_keyring: bool = False) -> bool:
    """安全存储 api_key。

    Args:
        api_key: 要存储的 key（可带 ${ENV_VAR} 前缀）
        use_keyring: True 时强制存 keyring（忽略 api_key 内容）

    Returns:
        True = 存储成功；False = 失败（不抛）
    """
    if use_keyring:
        # 生成确定性 service 名（基于 provider）
        cfg = get_llm_config()
        provider = cfg.get("provider", "default")
        ok = _set_keyring_password(provider, api_key)
        if ok:
            # config.toml 只存引用，不存明文
            return set_llm_config(api_key=f"keyring://{provider}")
        return False
    return set_llm_config(api_key=api_key)