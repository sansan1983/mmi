"""mmi config — LLM 配置子命令：show / wizard。"""

from __future__ import annotations

from argparse import Namespace
from dataclasses import replace

from mmi.cli import dispatch_subcommand, ensure_mmi_home
from mmi.core import config as cfg_mod
from mmi.core import i18n, model_fetcher
from mmi.core import providers as prov_mod
from mmi.core.manager import SessionManager

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _prompt_choice(prompt: str, options: list[str], default: int = 0) -> int:
    """让用户从编号列表里选一个。返回 index。空输入走 default。"""
    while True:
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            idx = int(raw)
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print(i18n.t("wizard.invalid_choice", max=len(options) - 1))


def _prompt_text(prompt: str, *, required: bool = True, default: str = "") -> str:
    """让用户输入一段文本。空输入走 default；required 时空也再问。"""
    while True:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            raw = default
        if raw or not required:
            return raw
        print(i18n.t("wizard.empty_input"))


def _confirm(prompt: str, *, default: bool = False) -> bool:
    """Yes/No 确认。"""
    suffix = i18n.t("wizard.confirm_suffix_yes") if default else i18n.t("wizard.confirm_suffix_no")
    while True:
        raw = input(f"{prompt} {suffix}: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False


# ---------------------------------------------------------------------------
# 向导逻辑
# ---------------------------------------------------------------------------


def _config_wizard(args: Namespace) -> int:
    """交互式 LLM 配置向导。"""
    print("=" * 50)
    print(i18n.t("wizard.banner"))
    print("=" * 50)

    current = cfg_mod.get_llm_config()
    if any(current.values()):
        print(
            i18n.t("wizard.current_config", provider=current.get("provider"), model=current.get("model"))
        )
        print(i18n.t("wizard.overwrite_hint"))

    # 1) 选 provider
    providers = list(prov_mod.list_providers())
    print(i18n.t("wizard.providers_header"))
    for i, p in enumerate(providers):
        marker = f" [{p.notes}]" if p.notes else ""
        print(i18n.t("wizard.provider_entry", i=i, name=p.name, id=p.id, base_url=p.base_url, marker=marker))
    custom_idx = len(providers)
    print(i18n.t("wizard.custom_provider_option", idx=custom_idx))

    if getattr(args, "provider", None):
        pid = args.provider.strip().lower()
        try:
            provider = prov_mod.get_provider(pid) if pid != "custom" else None
            chosen_idx = custom_idx if pid == "custom" else next(
                i for i, p in enumerate(providers) if p.id == pid
            )
        except ValueError:
            print(i18n.t("wizard.unknown_provider", id=pid))
            return 1
    else:
        chosen_idx = _prompt_choice(
            i18n.t("wizard.provider_prompt"),
            [p.id for p in providers] + ["custom"],
        )

    if chosen_idx == custom_idx:
        base_url = _prompt_text("自定义 base_url", default=current.get("base_url", ""))
        style_raw = _prompt_text("API 风格 (openai/anthropic)", default="openai").lower()
        if style_raw not in ("openai", "anthropic"):
            print(i18n.t("wizard.invalid_style"))
            return 1
        provider = prov_mod.make_custom_provider(base_url, preferred_api_style=style_raw)
        api_style = style_raw
    else:
        provider = providers[chosen_idx]
        base_url = provider.base_url
        if provider.anthropic_base_url:
            print(i18n.t("wizard.dual_protocol_intro", name=provider.name))
            print(i18n.t("wizard.dual_protocol_anthropic", url=provider.anthropic_base_url))
            print(i18n.t("wizard.dual_protocol_openai", url=provider.base_url))
            style_idx = _prompt_choice(
                i18n.t("wizard.dual_protocol_prompt"), ["anthropic", "openai"], default=0
            )
            api_style = "anthropic" if style_idx == 0 else "openai"
            provider = replace(
                provider,
                preferred_api_style=api_style,
                base_url=(
                    provider.anthropic_base_url
                    if api_style == "anthropic"
                    else provider.base_url
                ),
            )
            base_url = provider.base_url
        else:
            api_style = provider.preferred_api_style
            print(i18n.t("wizard.single_protocol_hint", style=api_style))

    # 2) api_key
    if getattr(args, "api_key", None):
        api_key = args.api_key.strip()
    else:
        env_hint = provider.api_key_env or "(无)"
        print(i18n.t("wizard.api_key_url_hint", url=provider.api_key_url or '?'))
        print(i18n.t("wizard.api_key_env_hint", env=env_hint))
        api_key = _prompt_text(i18n.t("wizard.api_key_prompt"), required=True)

    if not api_key:
        print(i18n.t("wizard.api_key_empty"))
        return 1

    # 3) 拉模型列表
    if getattr(args, "no_fetch", False):
        model_id = args.model.strip() if getattr(args, "model", None) else _prompt_text(i18n.t("wizard.model_manual_prompt"), required=True)
    else:
        print(
            i18n.t("wizard.fetching_models", name=provider.name, style=api_style, url=provider.base_url)
        )
        try:
            models = model_fetcher.fetch_models(
                provider, api_key, style_override=api_style,
            )
        except model_fetcher.ModelFetchError as e:
            print(i18n.t("wizard.fetch_failed", error=str(e)))
            if not _confirm(i18n.t("wizard.continue_manual_prompt"), default=False):
                return 1
            models = []

        if not models:
            model_id = _prompt_text(i18n.t("wizard.model_manual_prompt"), required=True)
        elif getattr(args, "model", None):
            mid = args.model.strip()
            ids = {m.id for m in models}
            if mid not in ids:
                print(i18n.t("wizard.model_not_in_list", id=mid))
            model_id = mid
        else:
            print(i18n.t("wizard.models_count", n=len(models)))
            show_n = min(30, len(models))
            for i, m in enumerate(models[:show_n]):
                print(i18n.t("wizard.model_entry", i=i, id=m.id))
            if len(models) > show_n:
                print(i18n.t("wizard.models_truncated", total=len(models), n=show_n))
            idx = _prompt_choice(
                i18n.t("wizard.model_choice_prompt", max=show_n - 1),
                [m.id for m in models[:show_n]],
            )
            model_id = models[idx].id if 0 <= idx < show_n else ""

    if not model_id:
        print(i18n.t("wizard.model_empty"))
        return 1

    # 4) 写盘
    ok = cfg_mod.set_llm_config(
        provider=provider.id,
        base_url=base_url,
        api_key=api_key,
        model=model_id,
        api_style=api_style,
    )
    if not ok:
        print(i18n.t("wizard.write_failed"))
        return 1
    masked = api_key[:4] + "***" + api_key[-2:] if len(api_key) > 6 else "***"
    print(i18n.t("wizard.write_success"))
    print(i18n.t("wizard.write_field_provider", value=provider.id))
    print(i18n.t("wizard.write_field_api_style", value=api_style))
    print(i18n.t("wizard.write_field_base_url", value=base_url))
    print(i18n.t("wizard.write_field_api_key", value=masked))
    print(i18n.t("wizard.write_field_model", value=model_id))
    return 0


# ---------------------------------------------------------------------------
# 主命令
# ---------------------------------------------------------------------------


def _config_show() -> int:
    llm = cfg_mod.get_llm_config()
    if not any(llm.values()):
        print(i18n.t("config_show.empty"))
        return 0
    print(i18n.t("config_show.header"))
    for k in ("provider", "base_url", "api_key", "model"):
        v = llm.get(k, "") or ""
        if k == "api_key" and v:
            v = v[:4] + "***" + v[-2:] if len(v) > 6 else "***"
        print(f"  {k:10s} = {v}")
    return 0


def cmd_config(args: Namespace, mgr: SessionManager) -> int:
    ensure_mmi_home()
    return dispatch_subcommand(
        args,
        "config_cmd",
        {
            "show": _config_show,
            "wizard": lambda: _config_wizard(args),
        },
        usage="usage: mmi config {show|wizard}",
    )
