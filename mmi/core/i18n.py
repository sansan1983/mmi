"""mmi.core.i18n —— 主板自带的双语基线。

本模块是**基线功能**（见 ARCHITECTURE.md §10.1），不允许放到扩展模块里。
所有用户可见字符串必须经过 t() 包裹，禁止在代码中硬编码中英文。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

# 支持的语言（白名单；新增语言必须同步更新 ARCHITECTURE.md §3.5.7）
SUPPORTED_LANGS: tuple[str, ...] = ("zh-CN", "en-US")
DEFAULT_LANG: str = "zh-CN"

# mmi locales 目录：<package_root>/mmi/locales/
_LOCALES_DIR = Path(__file__).resolve().parent / "locales"

# 全局当前语言（运行时由 set_lang / detect_lang 写入；测试可重置）
_current_lang: str = DEFAULT_LANG

# 全局 locale 缓存：{lang: {key: text}}
_cache: dict[str, dict[str, str]] = {}


def detect_lang(cli_override: str | None = None) -> str:
    """检测当前应使用的语言。

    优先级：
      1. cli_override（CLI --lang 参数）
      2. LANG / LC_ALL 环境变量
      3. 默认 zh-CN
    """
    if cli_override and cli_override in SUPPORTED_LANGS:
        return cli_override

    env = os.environ.get("LANG") or os.environ.get("LC_ALL") or ""
    # 环境变量形如 "zh_CN.UTF-8" 或 "en_US.UTF-8"
    env = env.split(".")[0]  # 去掉 .UTF-8
    env = env.replace("_", "-")

    if env.startswith("zh"):
        return "zh-CN"
    if env.startswith("en"):
        return "en-US"
    return DEFAULT_LANG


def set_lang(lang: str) -> None:
    """显式设置当前语言。必须在 detect_lang 之后调用以覆盖。"""
    global _current_lang
    if lang not in SUPPORTED_LANGS:
        raise ValueError(
            f"unsupported language: {lang!r}; supported: {SUPPORTED_LANGS}"
        )
    _current_lang = lang


def get_lang() -> str:
    return _current_lang


def _load_lang(lang: str) -> dict[str, str]:
    """加载指定语言的 locale 字典（带缓存）。"""
    if lang in _cache:
        return _cache[lang]

    path = _LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        # 找不到时返回空字典（不抛错，避免一个缺翻译就崩溃）
        _cache[lang] = {}
        return _cache[lang]

    with path.open("r", encoding="utf-8") as f:
        data: dict[str, str] = json.load(f)

    _cache[lang] = data
    return data


def t(
    key: str,
    *,
    lang: str | None = None,
    default: str | None = None,
    **kwargs: object,
) -> str:
    """翻译查找。

    Args:
        key: 翻译键，dot-separated，如 "cli.list.empty"。
        lang: 临时指定语言（不传则用全局当前语言）。
        default: 兜底字符串，key 缺失时返回（仍会做 kwargs.format）。
                 不传时 key 缺失返回 "[[key]]" 以便发现漏翻译。
        **kwargs: 命名占位符，模板中用 {name} 引用。

    Returns:
        翻译后的字符串。

    Examples:
        >>> t("cli.greeting")
        '你好，欢迎使用 mmi。'
        >>> t("cli.greeting", lang="en-US")
        'Hello, welcome to mmi.'
        >>> t("cli.list.count", count=3)
        '共 3 条会话'
    """
    target = lang or _current_lang
    data = _load_lang(target)

    text = data.get(key)
    if text is None:
        # 缺翻译：开发期用占位符高亮，生产期可改 logging.warning
        text = default if default is not None else f"[[{key}]]"

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            # 占位符不匹配时，原样返回（不要因为翻译 bug 让程序崩）
            return text
    return text


def reset_for_test() -> None:
    """测试用：重置全局状态。"""
    global _current_lang, _cache
    _current_lang = DEFAULT_LANG
    _cache = {}