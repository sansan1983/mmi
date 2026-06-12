"""mmi config — LLM 配置子命令：show / wizard。"""

from __future__ import annotations

from dataclasses import replace
from mmi.cli import ensure_mmi_home
from mmi.core import config as cfg_mod
from mmi.core import model_fetcher
from mmi.core import providers as prov_mod


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
        print(f"  请输入 0-{len(options)-1} 之间的整数")


def _prompt_text(prompt: str, *, required: bool = True, default: str = "") -> str:
    """让用户输入一段文本。空输入走 default；required 时空也再问。"""
    while True:
        suffix = f" [{default}]" if default else ""
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            raw = default
        if raw or not required:
            return raw
        print("  不能为空，请重新输入")


def _confirm(prompt: str, *, default: bool = False) -> bool:
    """Yes/No 确认。"""
    suffix = "[Y/n]" if default else "[y/N]"
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


def _config_wizard(args) -> int:
    """交互式 LLM 配置向导。"""
    print("=" * 50)
    print("  mmi LLM 配置向导")
    print("=" * 50)

    current = cfg_mod.get_llm_config()
    if any(current.values()):
        print(
            f"\n当前: provider={current.get('provider')!r}, "
            f"model={current.get('model')!r}"
        )
        print("(向导会覆盖现有配置，Ctrl+C 随时退出)\n")

    # 1) 选 provider
    providers = list(prov_mod.list_providers())
    print("\n可用的模型商:")
    for i, p in enumerate(providers):
        marker = f" [{p.notes}]" if p.notes else ""
        print(f"  [{i}] {p.name}  (id={p.id}, 默认 base_url: {p.base_url}){marker}")
    custom_idx = len(providers)
    print(f"  [{custom_idx}] 自定义(手填 base_url)")

    if getattr(args, "provider", None):
        pid = args.provider.strip().lower()
        try:
            provider = prov_mod.get_provider(pid) if pid != "custom" else None
            chosen_idx = custom_idx if pid == "custom" else next(
                i for i, p in enumerate(providers) if p.id == pid
            )
        except ValueError:
            print(f"未知 provider: {pid}")
            return 1
    else:
        chosen_idx = _prompt_choice(
            "\n选哪个? (输入编号) ",
            [p.id for p in providers] + ["custom"],
        )

    if chosen_idx == custom_idx:
        base_url = _prompt_text("自定义 base_url", default=current.get("base_url", ""))
        style_raw = _prompt_text("API 风格 (openai/anthropic)", default="openai").lower()
        if style_raw not in ("openai", "anthropic"):
            print("  style 必须是 openai 或 anthropic")
            return 1
        provider = prov_mod.make_custom_provider(base_url, preferred_api_style=style_raw)
        api_style = style_raw
    else:
        provider = providers[chosen_idx]
        base_url = provider.base_url
        if provider.anthropic_base_url:
            print(f"\n  {provider.name} 同时支持 Anthropic / OpenAI 两种协议。")
            print(f"  [0] Anthropic (推荐, 端点: {provider.anthropic_base_url})")
            print(f"  [1] OpenAI 兼容 (端点: {provider.base_url})")
            style_idx = _prompt_choice(
                "  用哪种? (默认 0) ", ["anthropic", "openai"], default=0
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
            print(f"  (单协议: {api_style})")

    # 2) api_key
    if getattr(args, "api_key", None):
        api_key = args.api_key.strip()
    else:
        env_hint = provider.api_key_env or "(无)"
        print(f"\nAPI key 来源提示: 配置在 {provider.api_key_url or '?'}")
        print(f"环境变量兼容名: {env_hint}")
        api_key = _prompt_text("粘贴 api_key", required=True)

    if not api_key:
        print("api_key 为空，取消。")
        return 1

    # 3) 拉模型列表
    if getattr(args, "no_fetch", False):
        if getattr(args, "model", None):
            model_id = args.model.strip()
        else:
            model_id = _prompt_text("模型 id(手填)", required=True)
    else:
        print(
            f"\n正在拉取 {provider.name} 的可用模型"
            f"(走 {api_style} 端点: {provider.base_url})..."
        )
        try:
            models = model_fetcher.fetch_models(
                provider, api_key, style_override=api_style,
            )
        except model_fetcher.ModelFetchError as e:
            print(f"[!] 拉取失败: {e}")
            if not _confirm("是否仍要手填模型 id 继续?", default=False):
                return 1
            models = []

        if not models:
            model_id = _prompt_text("模型 id(手填)", required=True)
        elif getattr(args, "model", None):
            mid = args.model.strip()
            ids = {m.id for m in models}
            if mid not in ids:
                print(f"  警告: {mid} 不在 API 返回列表里，继续保存")
            model_id = mid
        else:
            print(f"\n拉到 {len(models)} 个模型:")
            show_n = min(30, len(models))
            for i, m in enumerate(models[:show_n]):
                print(f"  [{i}] {m.id}")
            if len(models) > show_n:
                print(f"  ... 共 {len(models)} 个，只显示前 {show_n}")
            idx = _prompt_choice(
                f"\n选哪个? (0-{show_n-1}) ",
                [m.id for m in models[:show_n]],
            )
            model_id = models[idx].id if 0 <= idx < show_n else ""

    if not model_id:
        print("模型 id 为空，取消。")
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
        print("[!] 写盘失败(权限/磁盘?)")
        return 1
    masked = api_key[:4] + "***" + api_key[-2:] if len(api_key) > 6 else "***"
    print("\n[✓] 已写入 ~/.mmi/config.toml:")
    print(f"    provider  = {provider.id}")
    print(f"    api_style = {api_style}")
    print(f"    base_url  = {base_url}")
    print(f"    api_key   = {masked}")
    print(f"    model     = {model_id}")
    return 0


# ---------------------------------------------------------------------------
# 主命令
# ---------------------------------------------------------------------------


def cmd_config(args, mgr) -> int:
    ensure_mmi_home()
    sub = getattr(args, "config_cmd", None)
    if sub is None:
        print("usage: mmi config {show|wizard}")
        return 1

    if sub == "show":
        llm = cfg_mod.get_llm_config()
        if not any(llm.values()):
            print("未配置 LLM。运行 `mmi config wizard` 走交互式设置。")
            return 0
        print("当前 LLM 配置 (~/.mmi/config.toml):")
        for k in ("provider", "base_url", "api_key", "model"):
            v = llm.get(k, "") or ""
            if k == "api_key" and v:
                v = v[:4] + "***" + v[-2:] if len(v) > 6 else "***"
            print(f"  {k:10s} = {v}")
        return 0

    if sub == "wizard":
        return _config_wizard(args)

    print(f"unknown config subcommand: {sub}")
    return 1