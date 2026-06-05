# 交接文档 — R8.5.3 Kimi 从预置移除
> 日期:2026-06-05
> 状态:✅ R8.5.3 完成
> 主题:Kimi (moonshot) 从预置 provider 移除(参数 schema 不匹配,需要时走自定义)
> 覆盖:`mmi/core/providers.py` PROVIDERS 元组(5 → 4)+ 相关测试

---

## 1. 决策与改动

**用户决议(2026-06-05)**:Kimi (moonshot) 官方文档没公布 `temperature` / `top_p` 等参数,
跟 `OpenAILLMProvider` 的统一参数 schema 不匹配。按报告 `docs/dev/预置Provider官方参数差异报告.md`
§3 + B1-B3 三项估算工时 ~3-4h(Kimi `max_completion_tokens` 迁移 / 跳 temperature / `thinking` extra_body),
工作量 + 实际用量 → **直接移除**,需要时走自定义选项。

---

## 2. 改动文件清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/providers.py` | 修改 | 删 `ProviderInfo(id='moonshot', name='Moonshot (Kimi)', ...)` 条目(7 行);模块 docstring 改 `5 个国内商` → `4 个国内商` + 加 Kimi 走自定义说明 |
| `mmi/core/llm.py` | 修改 | `OpenAILLMProvider.chat()` docstring 注释:`智谱/Kimi/千问` → `智谱/千问(Kimi 已移除,要用走自定义)` |
| `tests/test_providers.py` | 修改 | `test_provider_count` 期望 5 → 4;`test_provider_ids_unique` 5 → 4;删 `test_moonshot_uses_openai`;模块 docstring 同步 |

**净变化**:-1 provider, -1 test, +0 new tests, ruff 0。

---

## 3. 行为变更

### 用户视角

- **`mmi config` wizard**:少一项 Kimi 选项(4 家 → 4 家)
- **已有 `~/.mmi/config.toml` 含 `provider = "moonshot"`**:不会报错
  - `_build_provider_from_config` 找不到 moonshot → 返 None → 回退到 env / Echo
  - 行为变化:用户得手动改 config 或走自定义,否则走 Echo

### 测试视角

- `test_provider_count` 5 → 4
- `test_provider_ids_unique` 5 → 4
- `test_moonshot_uses_openai` 整条删
- 其它测试零影响

---

## 4. 如何继续用 Kimi(给用户)

走"自定义"选项(在 `mmi config` 时选 '自定义'):

```toml
# ~/.mmi/config.toml
provider = "custom"
api_style = "openai"
base_url = "https://api.moonshot.cn/v1"
api_key = "sk-..."
model = "moonshot-v1-8k"  # 或 moonshot-v1-32k / moonshot-v1-128k
```

**注意**(报告 §3):
- Kimi 官方**已弃用** `max_tokens`,用 `max_completion_tokens`(本仓 `OpenAILLMProvider` 当前**不**特殊处理 Kimi,会发 `max_tokens` — Kimi 服务端大概率忽略或 warning)
- Kimi 跳 `temperature`(本仓会发,可能忽略或 warning)
- Kimi 独有参数 `thinking` / `prompt_cache_key` / `safety_identifier` 不通过本仓暴露

**实用建议**:Kimi 用户目前**不**建议通过本仓用,直接走 Moonshot 官方 SDK 或 curl 更直接。

---

## 5. 接手者

- `git checkout master` 即可
- `pytest tests/ --ignore=tests/test_cli.py -q` → **564 passed**
- `ruff check mmi/ tests/` → **All checks passed**
- 预置 provider 现为 4 家:DeepSeek / MiniMax / GLM / Qwen

---

> 后续如需重做 Kimi(报告 B1-B3 项),开 R8.5.4 单独 round(估时 ~3-4h)。
