"""tests/test_config.py —— core.config 单元测试。

覆盖：
  - 配置文件不存在 → get_default_model 走缺省
  - 配置文件存在且含 llm.model → 用配置
  - 配置文件有但 llm.model 缺失 → 走 env 或缺省
  - 环境变量 OPENAI_MODEL 优先级（在 config 之后）
  - set_default_model 写回 + 读出
  - 写盘失败（无权限）→ 不抛，返回 False
  - 配置文件 YAML 损坏 → 静默回退到缺省
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mmi.core import config, paths  # noqa: E402


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MMI_HOME", str(tmp_path))
    paths.ensure_dirs()
    yield tmp_path


# ---------------------------------------------------------------------------
# get_default_model
# ---------------------------------------------------------------------------


def test_get_default_model_no_config_returns_default(isolated_home, monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert config.get_default_model() == "gpt-4o-mini"


def test_get_default_model_env_var(isolated_home, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    assert config.get_default_model() == "gpt-4o"


def test_get_default_model_from_config_file(isolated_home, monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    # 写一份 config
    cfg = {"llm": {"model": "deepseek-chat"}}
    assert config.save_config(cfg) is True
    assert config.get_default_model() == "deepseek-chat"


def test_get_default_model_config_takes_priority_over_env(isolated_home, monkeypatch):
    """config 优先于环境变量（用户显式 set_default_model 后不该被 env 覆盖）。"""
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    config.save_config({"llm": {"model": "from-config"}})
    assert config.get_default_model() == "from-config"


def test_get_default_model_corrupt_yaml_falls_back(isolated_home, monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    paths.get_config_path().write_text("{ not valid yaml [", encoding="utf-8")
    assert config.get_default_model() == "gpt-4o-mini"


def test_get_default_model_empty_model_value_falls_back(isolated_home, monkeypatch):
    """model 是空字符串 → 走 env / 缺省。"""
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    config.save_config({"llm": {"model": "   "}})
    assert config.get_default_model() == "gpt-4o-mini"


def test_get_default_model_preserves_other_keys(isolated_home, monkeypatch):
    """set_default_model 不应该抹掉 config 里其它字段。"""
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    config.save_config({"modules": {"disabled": ["feishu"]}})
    config.set_default_model("gpt-4o")
    cfg = config.load_config()
    assert cfg["llm"]["model"] == "gpt-4o"
    assert cfg["modules"]["disabled"] == ["feishu"]


# ---------------------------------------------------------------------------
# set_default_model
# ---------------------------------------------------------------------------


def test_set_default_model_roundtrip(isolated_home):
    assert config.set_default_model("gpt-4-turbo") is True
    assert config.get_default_model() == "gpt-4-turbo"


def test_set_default_model_empty_string_noop(isolated_home):
    """空字符串 → 不写，返回 False。"""
    assert config.set_default_model("") is False
    assert config.set_default_model("   ") is False
    # 配置文件仍未创建
    assert not paths.get_config_path().exists()


def test_set_default_model_overwrites(isolated_home):
    config.set_default_model("first-model")
    config.set_default_model("second-model")
    assert config.get_default_model() == "second-model"


# ---------------------------------------------------------------------------
# load_config 边界
# ---------------------------------------------------------------------------


def test_load_config_missing_returns_empty(isolated_home):
    assert config.load_config() == {}


def test_load_config_non_dict_returns_empty(isolated_home):
    paths.get_config_path().write_text("- a\n- b\n", encoding="utf-8")
    assert config.load_config() == {}


def test_load_config_extra_fields_preserved(isolated_home):
    """未知字段不被删除（Phase 6+ 扩展用）。"""
    config.save_config({"custom_section": {"foo": "bar"}})
    cfg = config.load_config()
    assert cfg["custom_section"] == {"foo": "bar"}


# ---------------------------------------------------------------------------
# save_config 失败
# ---------------------------------------------------------------------------


def test_save_config_returns_false_on_oserror(isolated_home, monkeypatch):
    """模拟只读目录 → 写失败 → 返回 False，不抛。"""
    # 把 config path 指向一个不可写的"目录"
    fake = isolated_home / "not_a_dir"
    fake.write_text("hi", encoding="utf-8")
    monkeypatch.setattr(
        "mmi.core.paths.get_config_path", lambda: fake / "config.toml"
    )
    assert config.save_config({"llm": {"model": "x"}}) is False


# ---------------------------------------------------------------------------
# validate_model_name（Phase 6 技术债：/model 名字校验）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [
    "gpt-4o-mini",
    "claude-3-5-sonnet",
    "deepseek-chat",
    "qwen2.5-7b",
    "gpt-4",
    "a",  # 单字符
    "A.B_C-D",  # 所有合法字符
])
def test_validate_model_name_accepts_valid(isolated_home, name):
    assert config.validate_model_name(name) is True


@pytest.mark.parametrize("name", [
    "",  # 空
    "   ",  # 空白
    "gpt 4o mini",  # 空格
    "gpt-4o\nmini",  # 换行
    "ollama:llama3",  # 冒号（保守起见拒绝）
    "model/with/slash",  # 路径分隔
    "model+plus",  # 加号
    "model;injection",  # SQL-ish
    "../etc/passwd",  # 路径穿越
    "name$with$dollars",  # shell 特殊字符
    "a" * 129,  # 超过 128 字符
    "中文模型",  # 非 ASCII
])
def test_validate_model_name_rejects_invalid(isolated_home, name):
    assert config.validate_model_name(name) is False


def test_set_default_model_rejects_invalid(isolated_home):
    """非法名字 → set_default_model 返 False，不写盘。"""
    assert config.set_default_model("gpt 4o mini") is False
    # 文件不应该被创建
    assert config.load_config() == {}


def test_set_default_model_accepts_valid(isolated_home):
    """合法名字 → 写盘成功 + 读出来一致。"""
    assert config.set_default_model("claude-3-5-sonnet") is True
    assert config.get_default_model() == "claude-3-5-sonnet"
