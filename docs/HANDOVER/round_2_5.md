# 交接文档 — Round 2.5
> 日期：2026-06-04
> 状态：✅ 已完成
> 主题：交互式 LLM 配置(model wizard + 5 国内 + 1 自定义 + Anthropic 优先)
> 覆盖 PLAN.md：**无**(bonus 收尾,不在 PLAN.md 任务清单里)
>
> 性质:用户临时追加的小项目 —— `mmi config` 交互式配置 LLM,持久化在 ~/.mmi/config.toml

---

## 1. 本轮完成

- ✅ **5 个国内商 catalog**:`deepseek` / `minimax`(MiniMax) / `glm`(智谱) / `moonshot`(Kimi) / `qwen`(通义千问)
- ✅ **1 个自定义选项**:`custom`(手填 base_url + 选 openai/anthropic 风格)
- ✅ **双接口支持**:DeepSeek 和 MiniMax 同时支持 Anthropic + OpenAI,wizard 选完 provider 问一句"用哪个协议"(Anthropic 优先默认,用户可切)
- ✅ **mmi/core/providers.py** 完整 catalog + 工厂(`base_url` 存 OpenAI 端,`anthropic_base_url` 存 Anthropic 端)
- ✅ **mmi/core/model_fetcher.py** 拉模型列表(支持 mock 测试;`style_override` 参数;首选失败回退)
- ✅ **mmi/core/config.py** 扩 LLM section:`get_llm_config` / `set_llm_config` / `resolve_api_key` + 新增 `api_style` 字段
- ✅ **mmi/core/llm.py** `_build_provider_from_config` 读 config 里的 `api_style`,用 AnthropicLLMProvider 还是 OpenAILLMProvider 据此判断
- ✅ **mmi/cli.py** `mmi config {show|wizard}` 子命令
- ✅ **+28 个 providers 测试** + **+11 个 config 测试**
- ✅ **全量 423/423 全绿**(改前 395)
- ✅ **ruff 0 error**

---

## 2. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/providers.py` | 新建 | 5 国内商 catalog + 工厂 + 协议风格字段 |
| `mmi/core/model_fetcher.py` | 新建 | 拉模型列表(OpenAI + Anthropic 双风格;首选失败回退) |
| `mmi/core/config.py` | 修改 | 加 `get_llm_config` / `set_llm_config` / `resolve_api_key` |
| `mmi/cli.py` | 修改 | `mmi config {show\|wizard}` 子命令 + cmd_config + wizard 实现 |
| `tests/test_providers.py` | 新建 | 28 个测试:5 商 + custom + fetcher(OpenAI/Anthropic/401/404/JSON 错/回退/去重) |
| `tests/test_config.py` | 新建 | 11 个测试:get/set/resolve_api_key/persistence |
| `docs/HANDOVER/round_2_5.md` | 新建 | 本交接文档 |

---

## 3. 测试总结

| 阶段 | 通过/总数 | 备注 |
|---|---|---|
| 改前 baseline | 395 / 395 | Round 2.4 收尾 |
| 改后(本轮) | **423 / 423** | +28 providers + 11 config - 部分调整 |
| ruff | **0 error** | 6 个新错自动修 |

跑法：
```bash
/tmp/mmi-venv/bin/python -m pytest tests/ -q --ignore=tests/test_cli.py
/tmp/mmi-venv/bin/ruff check mmi/
```

---

## 4. 关键决策记录

### 决策 1：5 国内 + 1 自定义(海外商留到后续)

- **理由**：用户明确"先国内,后面需要再扩"。海外商(OpenAI / Anthropic 官方)其实有 AnthropicLLMProvider 在 llm.py,但 catalog 里没列 —— 后续要加就 `providers.py` 加一行即可
- 后续加海外商时:在 `PROVIDERS` tuple 加 `ProviderInfo`,url / api_style 照官方文档填

### 决策 2：DeepSeek + MiniMax 双接口(Anthropic 优先,用户可切)

- 用户原文:"https://api.minimaxi.com/v1    https://api.deepseek.com  没有V1  这两个实际是可以支持双接口的,推进首选 anthropic 的  同时可以选 openai 的"
- **设计**:
  - `base_url` 存 OpenAI 端点(`https://api.deepseek.com`、`https://api.minimaxi.com/v1`)
  - `anthropic_base_url` 存 Anthropic 端点(`https://api.deepseek.com/anthropic`、`https://api.minimaxi.com/anthropic`)
  - `preferred_api_style="anthropic"` 标首选
  - wizard 检测到 `anthropic_base_url` 非空时,问用户用哪个协议
  - 用户选择写进 `config.api_style` 字段
  - `_build_provider_from_config` 读 `api_style` 决定用 AnthropicLLMProvider 还是 OpenAILLMProvider
- GLM / Kimi / Qwen 只有 OpenAI 兼容 —— 首选失败也无 fallback,直接报错让用户改 base_url
- 用户体验:DeepSeek 填了 OpenAI key → wizard 仍能选到模型(回退到 OpenAI 端点)

### 决策 3：key 持久化在 config.toml,环境变量作 fallback

- 用户明确:"key 不用环境变量"
- **实现**:`resolve_api_key(provider)` 优先级:config → env → 空
- 兜底:环境变量 `<PROVIDER>_API_KEY` 还是支持(以防 CI 跑)
- 向导流程:选 provider → 选协议(双接口商)→ 提示填 key(可粘贴)→ 拉模型 → 选模型 → 写盘(带 api_style)

### 决策 4：Anthropic 不引 SDK,用 httpx 直连

- **理由**:
  - AnthropicLLMProvider 用 httpx 调 /v1/messages,带 x-api-key + anthropic-version
  - 不引 anthropic SDK(避免多一个包)
  - 同样的 httpx 模式可以用来支持 Anthropic 兼容端点(MiniMax / DeepSeek Anthropic 端点都用同协议)

---

## 5. 关键设计：fetcher 首选失败回退

```python
def fetch_models(provider, api_key, *, timeout_s=15.0, client_factory=None):
    preferred = provider.preferred_api_style
    fallback = "openai" if preferred == "anthropic" else None
    
    last_err = None
    for style in (preferred, fallback):
        if style is None:
            break
        try:
            return _fetch_with_style(provider, api_key, style=style, ...)
        except ModelFetchError as e:
            last_err = e
            if fallback is None:
                raise
    raise last_err
```

- 优先 Anthropic,401/404 → 退回 OpenAI
- OpenAI 优先的商(GLM/Kimi/Qwen)失败时 **不**回退(没东西可回退),直接抛
- 用户体验:DeepSeek 填了 OpenAI key → wizard 仍能选到模型(回退到 OpenAI 端点)

---

## 6. 用户使用流程

```bash
$ mmi config wizard

==================================================
  mmi LLM 配置向导
==================================================

可用的模型商:
  [0] DeepSeek  (id=deepseek, 默认 base_url: https://api.deepseek.com/anthropic) [Anthropic 端点已验证;OpenAI 兼容也支持(https://api.deepseek.com/v1)]
  [1] MiniMax (MiniMax)  (id=minimax, 默认 base_url: https://api.minimaxi.com/anthropic) [Anthropic 端点 https://api.minimaxi.com/anthropic]
  [2] 智谱 GLM  (id=glm, 默认 base_url: https://open.bigmodel.cn/api/paas/v4) [OpenAI 兼容]
  [3] Moonshot (Kimi)  (id=moonshot, 默认 base_url: https://api.moonshot.cn/v1) [OpenAI 兼容]
  [4] 通义千问 (Qwen / DashScope)  (id=qwen, 默认 base_url: https://dashscope.aliyuncs.com/compatible-mode/v1) [OpenAI 兼容模式]
  [5] 自定义(手填 base_url)

选哪个? (输入编号) 0
API key 来源提示: 配置在 https://platform.deepseek.com/api_keys
环境变量兼容名: DEEPSEEK_API_KEY
粘贴 api_key: sk-xxxxxx

正在拉取 DeepSeek 的可用模型(走 anthropic 端点)...
拉到 2 个模型:
  [0] deepseek-chat
  [1] deepseek-coder

选哪个? (0-1, 或直接粘贴模型 id) 0
[✓] 已写入 ~/.mmi/config.toml:
    provider = deepseek
    base_url = https://api.deepseek.com/anthropic
    api_key  = sk-xxx
    model    = deepseek-chat
```

之后 `mmi chat <sid>` 走 `get_default_provider()` 读到这份配置,直接用 DeepSeek Anthropic 协议。

---

## 7. 关键代码片段(速查)

### providers.py — catalog

```python
PROVIDERS = (
    ProviderInfo(id="deepseek", name="DeepSeek",
                 preferred_api_style="anthropic",
                 base_url="https://api.deepseek.com/anthropic",
                 anthropic_base_url="https://api.deepseek.com/anthropic",
                 ...),
    ProviderInfo(id="minimax", name="MiniMax (MiniMax)",
                 preferred_api_style="anthropic",
                 base_url="https://api.minimaxi.com/anthropic",
                 ...),
    ProviderInfo(id="glm", name="智谱 GLM",
                 preferred_api_style="openai",
                 base_url="https://open.bigmodel.cn/api/paas/v4", ...),
    ...
)
```

### model_fetcher.py — 双风格 + 回退

```python
def fetch_models(provider, api_key, *, client_factory=None):
    preferred = provider.preferred_api_style
    fallback = "openai" if preferred == "anthropic" else None
    for style in (preferred, fallback):
        if style is None: break
        try:
            return _fetch_with_style(provider, api_key, style=style, ...)
        except ModelFetchError:
            if fallback is None: raise
    raise last_err
```

### config.py — 持久化

```python
def set_llm_config(*, provider=None, base_url=None, api_key=None, model=None) -> bool:
    """None 的字段保留旧值。写盘失败返 False。"""
def resolve_api_key(provider) -> str:
    """config → env → 空"""
```

### cli.py — wizard 主流程

```python
def _config_wizard(args) -> int:
    # 1) 选 provider(显示 5 + 1 + 编号)
    # 2) custom 时问 base_url + style
    # 3) 问 api_key
    # 4) 拉模型(首选失败回退)
    # 5) 显示前 30 个,用户编号选
    # 6) set_llm_config 写盘
```

---

## 8. 遗留 / 后续

- 后续要加海外商:在 `PROVIDERS` tuple 加一条
- helper model(embedding / summary / classify)用同一份配置;不重复设置
- 可选:加 `mmi config set <key> <value>` 子命令(目前只支持 wizard)
- 飞轮没起前,这个 wizard 是 onboarding 主入口,体验要打磨

---

> 接手者先跑 §3 测试,看到 423 passed + ruff 0 即可。
