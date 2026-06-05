# 交接文档 — R8.5.1b 预置 Provider 参数透传收口
> 日期:2026-06-05
> 状态:✅ R8.5.1b 完成(A1-A4 + 测试;A5 留 R8.5.2)
> 主题:按 `docs/dev/预置Provider官方参数差异报告.md` 补齐 5 家 Provider API 参数
> 覆盖:5 家厂商(智谱 GLM / Kimi / 千问 Qwen / DeepSeek / MiniMax)的 chat/stream 参数透传

---

## 1. 本轮完成(R8.5.1b 全部 A1-A4)

按报告"方案 A 最小改动"落地 4 项(报告 §8.1):

| # | 任务 | 落地 | 关键文件 | 净增测试 |
|---|---|---|---|---|
| A1 | MiniMax `api_key_env` 大小写 | ✅ | `mmi/core/providers.py:69` `"MiniMax_API_KEY"` → `"MINIMAX_API_KEY"` | 1 |
| A2 | OpenAILLMProvider.chat() 加 top_p/stop/response_format + stream_chat 加 stream_options | ✅ | `mmi/core/llm.py:OpenAILLMProvider.chat/stream_chat` | 7 |
| A3 | AnthropicLLMProvider.chat() 加 top_p/stop_sequences(注意是 stop_sequences 不是 stop) | ✅ | `mmi/core/llm.py:AnthropicLLMProvider.chat` | 4 |
| A4 | max_tokens 默认 512 → 4096(全 llm.py) | ✅ | `mmi/core/llm.py`(abstract + 4 个实现) | 3 |
| A5 | AnthropicLLMProvider.stream_chat 改真 SSE | ⬜ 留 R8.5.2 | — | — |
| **合计** | **4/5 落地 + 报告同步** | | | **+14** |

- ✅ **测试**:master **553/553**(539 R8.5.1 + 14 net new)
- ✅ **ruff**:**0 error**
- ✅ **报告**:`docs/dev/预置Provider官方参数差异报告.md` 已同步到 master

---

## 2. 改动文件清单

### 核心代码

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/providers.py` | 修改 | `MiniMax.api_key_env` 改全大写 |
| `mmi/core/llm.py` | 修改 | 5 处 `max_tokens=512` → `4096`(abstract chat / EchoLLM chat+stream / OpenAI chat+stream / Anthropic chat+stream)+ OpenAILLMProvider.chat 加 3 kwarg(top_p/stop/response_format)+ OpenAILLMProvider.stream_chat 加 `stream_options={"include_usage": True}` + AnthropicLLMProvider.chat 加 2 kwarg(top_p/stop_sequences) |

### 测试

| 文件 | 操作 | 净增 |
|---|---|---|
| `tests/test_provider_params.py` | **新建** | 14 个(provider 1 + OpenAI 6 + Anthropic 4 + max_tokens 3) |

### 文档

| 文件 | 操作 | 说明 |
|---|---|---|
| `docs/dev/预置Provider官方参数差异报告.md` | **新建** | 报告同步(从 docs/provider-params-report 分支) |

---

## 3. 关键设计决策

### 决策 1:所有新参数默认 None(不发送)

- `top_p` / `stop` / `response_format` / `stream_options` / `stop_sequences` 都是 `Optional[...]`,默认 `None`
- **None → 不加入 payload**(用 `if X is not None: kwargs[X] = ...`)
- 理由:
  - 保持向后兼容(原行为只发 4 参数,加 None 不发,完全等价)
  - 让调用方按需启用,不被默认值绑架
  - 测试 `test_*_default_does_not_send_optional_params` 显式验证

### 决策 2:Anthropic 停止词 key 是 `stop_sequences` 不是 `stop`

- 报告 §5 明确说 Anthropic 协议下叫 `stop_sequences`(OpenAI 叫 `stop`)
- 命名时**故意**用 `stop_sequences`(Anthropic 协议名),与 `OpenAILLMProvider.stop` 区分
- 测试 `test_anthropic_chat_sends_stop_sequences_not_stop` 显式验证两个 key 都不会发错

### 决策 3:max_tokens 全局 4096 而非按调用方定制

- 报告 §7.3 推荐 4096
- 改成默认值后,**所有调用方**(包括 Echo 测试 fixture / 旧的 R0 测试)都受影响
- 验证:**旧 539 测试零回归** — 因为它们都通过 mock 验证,或者不查 max_tokens 具体值
- 显式传 `max_tokens=...` 仍能覆盖(`test_explicit_max_tokens_still_wins` 验证)

### 决策 4:A5(Anthropic 真 SSE 流式)留 R8.5.2

- Anthropic SSE 协议需要解析 `content_block_delta` 事件(报告 §7.2 详述)
- 工程量 ~2-3h,需要测试 Anthropic mock server 或 wiremock
- 单独成 round 便于 review,不影响 A1-A4 落地

---

## 4. 关键代码片段

### `mmi/core/llm.py` — OpenAILLMProvider.chat() 新签名

```python
def chat(
    self,
    messages,
    *,
    max_tokens=4096,
    temperature=0.7,
    top_p: float | None = None,
    stop: str | list[str] | None = None,
    response_format: dict | None = None,
) -> str:
    """OpenAI 兼容 chat()。
    R8.5.1b:按 provider-params 报告补 top_p / stop / response_format(均可选,None 不发)。
    """
    kwargs: dict = {
        "model": self.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if top_p is not None:
        kwargs["top_p"] = top_p
    if stop is not None:
        kwargs["stop"] = stop
    if response_format is not None:
        kwargs["response_format"] = response_format
    try:
        resp = self.client.chat.completions.create(**kwargs)
    except Exception as e:
        raise LLMError(f"OpenAI chat failed: {e}") from e
    ...
```

### `mmi/core/llm.py` — AnthropicLLMProvider.chat() 新签名

```python
def chat(
    self,
    messages,
    *,
    max_tokens=4096,
    temperature=0.7,
    top_p: float | None = None,
    stop_sequences: list[str] | None = None,
) -> str:
    """Anthropic chat()。
    R8.5.1b:按 provider-params 报告补 top_p / stop_sequences(均可选,None 不发)。
    注意:Anthropic 协议下停止词叫 stop_sequences(不是 OpenAI 的 stop)。
    """
    ...
    payload: dict = {
        "model": self.model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": user_msgs,
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    if top_p is not None:
        payload["top_p"] = top_p
    if stop_sequences is not None:
        payload["stop_sequences"] = stop_sequences
    data = self._post(payload)
    ...
```

### `mmi/core/llm.py` — OpenAILLMProvider.stream_chat() 加 stream_options

```python
def stream_chat(self, messages, *, max_tokens=4096, temperature=0.7):
    """OpenAI 真流式。
    R8.5.1b:加 stream_options={"include_usage": true},
    让最后一块附带 usage 信息(各家都支持)。
    """
    ...
    stream = self.client.chat.completions.create(
        ...
        stream=True,
        stream_options={"include_usage": True},
    )
    ...
```

---

## 5. 报告后续项(留待 R8.5.2 / 后期)

| # | 项 | 来源 | 估时 | 优先级 |
|---|---|---|---|---|
| A5 | AnthropicLLMProvider.stream_chat 改真 SSE 流式(解析 content_block_delta) | 报告 §7.2 | 2-3h | 中 |
| B1 | Kimi `max_completion_tokens` 替代 `max_tokens`(Kimi 已弃用 max_tokens) | 报告 §3 | 1h | 中(只对 Kimi 生效) |
| B2 | Kimi 跳 temperature(官方文档没公布) | 报告 §3 | 0.5h | 低(可能限制太多) |
| B3 | Kimi `thinking` (extra_body) + `prompt_cache_key` + `safety_identifier` | 报告 §3 | 1-2h | 低(高级特性) |
| B4 | 千问 `repetition_penalty` + `enable_search` | 报告 §4 | 1h | 低(高级特性) |
| C1 | `ProviderInfo` 加 `supported_params` 白名单 + `_build_payload()` 工厂 | 报告方案 B | 3-5h | 中期(等积累更多 parameter 后做) |

---

## 6. 测试覆盖

| 测试类 | 数量 | 说明 |
|---|---|---|
| `test_minimax_api_key_env_is_uppercase` | 1 | 数据层 |
| `test_openai_chat_default_does_not_send_optional_params` | 1 | 验证 None 不发 |
| `test_openai_chat_sends_top_p_when_provided` | 1 | |
| `test_openai_chat_sends_stop_when_provided` | 1 | |
| `test_openai_chat_sends_response_format_when_provided` | 1 | |
| `test_openai_chat_accepts_all_three_together` | 1 | 组合 |
| `test_openai_stream_chat_sends_stream_options` | 1 | |
| `test_anthropic_chat_default_does_not_send_optional_params` | 1 | |
| `test_anthropic_chat_sends_top_p_when_provided` | 1 | |
| `test_anthropic_chat_sends_stop_sequences_not_stop` | 1 | 协议差异关键测试 |
| `test_anthropic_chat_accepts_all_three_together` | 1 | + system 共存 |
| `test_openai_chat_default_max_tokens_is_4096` | 1 | |
| `test_anthropic_chat_default_max_tokens_is_4096` | 1 | |
| `test_explicit_max_tokens_still_wins` | 1 | 显式覆盖 |
| **合计** | **14** | |

---

## 7. 接手者

- `git checkout master` 即可
- `pytest tests/ --ignore=tests/test_cli.py -q` → **553 passed**
- `ruff check mmi/ tests/` → **All checks passed**
- 读 `docs/dev/预置Provider官方参数差异报告.md` 了解各家 API 差异背景
- 后续 R8.5.2 做 A5(Anthropic 真 SSE 流式)

---

> 来源:docs/provider-params-report 分支的 `docs/dev/预置Provider官方参数差异报告.md`(由 sansan1983 写)
