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

__all__ = [
    "get_default_model",
    "set_default_model",
    "validate_model_name",
    "load_config",
    "save_config",
    "DEFAULT_MODEL",
]


# 缺省模型：与 OpenAI 客户端 get_default_provider 默认值一致
DEFAULT_MODEL = "gpt-4o-mini"


# 模型名校验：长度 1-128，常见模型名字符集
# 覆盖：gpt-4o-mini / claude-3-5-sonnet / qwen2.5-7b / deepseek_chat
# 不允许：空格 / 路径分隔（/）/ URL 风格（:）/ shell 特殊（$ ; 等）/ 非 ASCII
_MODEL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")


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