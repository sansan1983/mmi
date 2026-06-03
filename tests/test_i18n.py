"""i18n 基线单元测试（Phase 0 验收）。

覆盖：
  - 翻译查找命中 / 缺翻译兜底
  - 双语切换
  - 占位符 .format
  - 语言检测（cli_override / 环境变量 / 默认）
  - 不支持的语言抛错
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 允许从仓库根直接 `python tests/test_i18n.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from mmi.core import i18n  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_i18n():
    """每个 case 后重置全局状态。"""
    i18n.reset_for_test()
    yield
    i18n.reset_for_test()


def test_t_returns_zh_by_default():
    i18n.set_lang("zh-CN")
    assert "主板" in i18n.t("cli.banner")


def test_t_returns_en_when_set():
    i18n.set_lang("en-US")
    assert "mainboard" in i18n.t("cli.banner")


def test_t_lang_override_does_not_mutate_global():
    i18n.set_lang("zh-CN")
    en_text = i18n.t("cli.banner", lang="en-US")
    assert "mainboard" in en_text
    # 全局仍是中文
    assert "主板" in i18n.t("cli.banner")


def test_t_missing_key_uses_placeholder():
    i18n.set_lang("zh-CN")
    text = i18n.t("definitely.not.exist")
    assert text == "[[definitely.not.exist]]"


def test_t_missing_key_uses_default():
    i18n.set_lang("zh-CN")
    text = i18n.t("definitely.not.exist", default="缺翻译")
    assert text == "缺翻译"


def test_t_format_kwargs():
    i18n.set_lang("zh-CN")
    text = i18n.t("new.success", session_id="01HXYZ")
    assert "01HXYZ" in text


def test_t_format_kwargs_in_en():
    i18n.set_lang("en-US")
    text = i18n.t("list.entry", index=1, title="demo", heat=10, state="active")
    assert text.startswith("1. demo")
    assert "heat 10" in text
    assert "active" in text


def test_detect_lang_cli_override_wins():
    assert i18n.detect_lang("en-US") == "en-US"
    # 即使 LANG=zh_CN，override 也要胜出
    old = os.environ.get("LANG")
    os.environ["LANG"] = "zh_CN.UTF-8"
    try:
        assert i18n.detect_lang("en-US") == "en-US"
    finally:
        if old is None:
            os.environ.pop("LANG", None)
        else:
            os.environ["LANG"] = old


def test_detect_lang_from_env_zh():
    old = os.environ.get("LANG")
    os.environ["LANG"] = "zh_CN.UTF-8"
    try:
        assert i18n.detect_lang() == "zh-CN"
    finally:
        if old is None:
            os.environ.pop("LANG", None)
        else:
            os.environ["LANG"] = old


def test_detect_lang_from_env_en():
    old = os.environ.get("LANG")
    os.environ["LANG"] = "en_US.UTF-8"
    try:
        assert i18n.detect_lang() == "en-US"
    finally:
        if old is None:
            os.environ.pop("LANG", None)
        else:
            os.environ["LANG"] = old


def test_detect_lang_default_when_no_env():
    old = os.environ.pop("LANG", None)
    old_lc = os.environ.pop("LC_ALL", None)
    try:
        assert i18n.detect_lang() == "zh-CN"
    finally:
        if old is not None:
            os.environ["LANG"] = old
        if old_lc is not None:
            os.environ["LC_ALL"] = old_lc


def test_set_lang_unsupported_raises():
    with pytest.raises(ValueError, match="unsupported language"):
        i18n.set_lang("ja-JP")


def test_detect_lang_fallback_for_unsupported_env():
    """不支持的语言（如 ja）应回退到默认 zh-CN。"""
    old = os.environ.get("LANG")
    os.environ["LANG"] = "ja_JP.UTF-8"
    try:
        assert i18n.detect_lang() == "zh-CN"
    finally:
        if old is None:
            os.environ.pop("LANG", None)
        else:
            os.environ["LANG"] = old


def test_locales_files_exist():
    """防止有人删了 locales/ 目录但代码还引用。"""
    locales_dir = Path(__file__).resolve().parent.parent / "mmi" / "core" / "locales"
    assert (locales_dir / "zh-CN.json").exists()
    assert (locales_dir / "en-US.json").exists()


def test_zh_and_en_have_same_keys():
    """两个 locale 的 key 集合必须一致，缺翻译立刻暴露。"""
    locales_dir = Path(__file__).resolve().parent.parent / "mmi" / "core" / "locales"
    import json

    with (locales_dir / "zh-CN.json").open(encoding="utf-8") as f:
        zh = set(json.load(f).keys())
    with (locales_dir / "en-US.json").open(encoding="utf-8") as f:
        en = set(json.load(f).keys())
    assert zh == en, f"key diff: only_zh={zh - en}, only_en={en - zh}"


def test_zh_strings_are_real_cjk_not_mojibake():
    """防止 Windows GBK 编码问题回流：locale 文件里的中文必须真的是 CJK。"""
    locales_dir = Path(__file__).resolve().parent.parent / "mmi" / "core" / "locales"
    import json

    with (locales_dir / "zh-CN.json").open(encoding="utf-8") as f:
        zh = json.load(f)
    has_cjk = any(any("一" <= ch <= "鿿" for ch in v) for v in zh.values())
    assert has_cjk, "zh-CN.json should contain real CJK characters"


def test_supported_langs_exact():
    assert i18n.SUPPORTED_LANGS == ("zh-CN", "en-US")
    assert i18n.DEFAULT_LANG == "zh-CN"
