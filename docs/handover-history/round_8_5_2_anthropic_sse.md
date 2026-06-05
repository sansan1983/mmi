# 交接文档 — R8.5.2 AnthropicLLMProvider 真 SSE 流式
> 日期:2026-06-05
> 状态:✅ R8.5.2 完成
> 主题:替换 AnthropicLLMProvider.stream_chat 的 fake 实现,按 Anthropic SSE 协议做真流式
> 覆盖:DeepSeek / MiniMax(两家走 Anthropic 端点)的 stream_chat 流式输出

---

## 1. 本轮完成

按 R7 4.4 报告 §7.2 + R8.5.1b 报告 §5 A5 决议:

| 任务 | 落地 | 关键文件 | 净增测试 |
|---|---|---|---|
| A5 AnthropicLLMProvider.stream_chat 真 SSE | ✅ | `mmi/core/llm.py:AnthropicLLMProvider.stream_chat` | +12 |

- ✅ **测试**:master **565/565**(553 R8.5.1b + 12 net new)
- ✅ **ruff**:**0 error**

---

## 2. 改动文件清单

### 核心代码

| 文件 | 操作 | 说明 |
|---|---|---|
| `mmi/core/llm.py` | 修改 | `AnthropicLLMProvider.stream_chat` 从 4 行 fake 实现(yield 整段 chat)→ ~110 行真 SSE 解析 |

### 测试

| 文件 | 操作 | 净增 |
|---|---|---|
| `tests/test_anthropic_sse.py` | **新建** | 12 个(5 happy path + 4 错误 + 3 payload) |

---

## 3. 关键设计决策

### 决策 1:同步生成器 + `httpx.Client.stream()`(不开 async)

- 与 R7 4.4 决议一致:本仓 SDK 同步(httpx + OpenAI 兼容),不开 async
- `httpx.Client` 自带 `.stream(method, url)` 返回 context manager 包 Response
- `resp.iter_lines()` 同步迭代 SSE 行(底层 httpx 用 `httpx._transports` 内部 buffer)

### 决策 2:SSE 状态机(行级)— 不依赖 sse-starlette 等第三方库

- 自己写 ~50 行解析:`event:` / `data:` / 空行边界
- Anthropic 协议下:
  - `event: <name>` 行 → 更新 current_event
  - `data: <line>` → 累积到 data_buf(支持多行 JSON 折行)
  - 空行 → 触发:检查 current_event == "content_block_delta",解析 data,只 yield text_delta 文本
  - `:` 开头的注释行 → 跳过
- 不引入新依赖,纯 stdlib(`json` + `httpx` 已有)

### 决策 3:只 yield `text_delta`,忽略其它所有 event

- 我们只关心 LLM 文本输出
- `content_block_delta` 里可能有:
  - `text_delta`(普通文本)→ yield text
  - `input_json_delta`(tool use)→ **不 yield**(后续 R9/R10 接 tools 再考虑)
  - `thinking_delta`(extended thinking,Anthropic 特有)→ **不 yield**(R10+ 再说)
- `message_start` / `content_block_start` / `content_block_stop` / `message_delta` / `message_stop` 都是控制/元数据事件,全忽略

### 决策 4:错误分类对齐 `stream_chat_with_retry`

- HTTP 4xx → `LLMError`(stream_chat_with_retry 看到 4xx 不可重试,直接抛)
- HTTP 5xx → `LLMError`(stream_chat_with_retry 看到 5xx 在 pre-yield 阶段可重试)
- 网络错误(Timeout/ConnectError)→ `LLMError`(同 chat_with_retry 的网络重试逻辑)
- 其它(解析失败 / 未知)→ `StreamError`(中流错误,让 stream_chat_with_retry 转 mid-stream 行为)

注意:`stream_chat_with_retry` 是 R8 Task 3 实现的,这里 stream_chat 的错误分类跟它**契约对齐** — 上层 retry 逻辑不需要改。

### 决策 5:payload 加 `"stream": True`

- Anthropic messages API 不传 `stream=True` 就走非流式,返单 JSON
- 必须传(否则就是非流式)
- 测试 `test_stream_payload_includes_stream_flag` 显式验证

### 决策 6:不解 `message_delta` 的 `usage` 字段

- Anthropic 流式也会附 token usage 信息(在 message_delta event 里)
- 我们目前不关心 usage(后续 R10+ 再说,跟 R8 的 `Tracer` 接 EventBus 一起做)
- `message_delta` event 整个被忽略,顺带忽略 usage — 简单干净

---

## 4. 关键代码片段

### `mmi/core/llm.py` — AnthropicLLMProvider.stream_chat 新实现

```python
def stream_chat(self, messages, *, max_tokens=4096, temperature=0.7):
    """Anthropic 真 SSE 流式(DeepSeek / MiniMax 用 Anthropic 端点时也走这路径)。

    协议(SSE):
      event: message_start
      event: content_block_start
      event: content_block_delta
        data: {"type":"content_block_delta","index":N,
               "delta":{"type":"text_delta","text":"Hello"}}
      event: content_block_stop
      event: message_delta
      event: message_stop
    """
    from mmi.core.exceptions import StreamError
    import httpx
    import json as _json

    # 构造 payload(同 chat())
    system_parts, user_msgs = [], []
    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""
        if role == "system":
            system_parts.append(content)
        else:
            user_msgs.append({"role": role, "content": content})
    payload = {
        "model": self.model, "max_tokens": max_tokens,
        "temperature": temperature, "messages": user_msgs,
        "stream": True,  # 关键
    }
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)

    url = f"{self.base_url}/v1/messages"
    headers = {
        "x-api-key": self.api_key,
        "anthropic-version": self.anthropic_version,
        "Content-Type": "application/json",
    }

    try:
        with self._client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", errors="replace")[:300]
                raise LLMError(f"Anthropic stream HTTP {resp.status_code}: {body}")
            # SSE 状态机
            current_event = ""
            data_buf = []
            for raw_line in resp.iter_lines():
                line = raw_line if isinstance(raw_line, str) else raw_line.decode("utf-8", errors="replace")
                if not line:
                    # 空行 = event 边界
                    if data_buf:
                        data_text = "\n".join(data_buf)
                        if current_event == "content_block_delta":
                            try:
                                evt = _json.loads(data_text)
                                delta = evt.get("delta") or {}
                                if delta.get("type") == "text_delta":
                                    text = delta.get("text") or ""
                                    if text:
                                        yield text
                            except _json.JSONDecodeError:
                                pass
                        data_buf, current_event = [], ""
                    continue
                if line.startswith(":"):
                    continue  # SSE 注释
                if line.startswith("event:"):
                    current_event = line[len("event:"):].strip()
                elif line.startswith("data:"):
                    data_buf.append(line[len("data:"):].lstrip())
            # 流结束,处理最后一批
            if data_buf and current_event == "content_block_delta":
                ...
    except LLMError:
        raise
    except (httpx.TimeoutException, httpx.ConnectError, ConnectionError) as e:
        raise LLMError(f"Anthropic stream network error: {e}") from e
    except Exception as e:
        raise StreamError(f"Anthropic stream error: {e}") from e
```

---

## 5. 测试覆盖

| 测试 | 说明 |
|---|---|
| `test_stream_yields_only_text_delta_chunks` | 标准 happy path:3 个 text_delta 拼起来 |
| `test_stream_handles_multiple_content_blocks` | 3 个 content block(2 text + 1 tool_use)→ 只 yield text |
| `test_stream_ignores_sse_comments` | `:` 开头的注释行忽略 |
| `test_stream_handles_multiline_data` | data: 多行(JSON 折行)累积处理 |
| `test_stream_empty_response_yields_nothing` | 空流(没有 text_delta)→ 0 yield |
| `test_stream_ignores_malformed_json_chunk` | 单个 chunk JSON 损坏 → 跳过,不崩 |
| `test_stream_http_4xx_raises_llm_error` | 4xx 错误 |
| `test_stream_http_5xx_raises_llm_error` | 5xx 错误 |
| `test_stream_network_error_raises_llm_error` | ConnectError → LLMError |
| `test_stream_payload_includes_stream_flag` | payload 必带 stream:True |
| `test_stream_payload_splits_system_message` | system 移到 payload.system,messages 不含 system |
| `test_stream_payload_uses_max_tokens_4096_by_default` | R8.5.1b 默认 4096 |

---

## 6. 跟 R8 Task 3 (4.8 stream_chat_with_retry) 的契约

- R8 Task 3 的 `stream_chat_with_retry` 假设 stream_chat 错误分类:
  - `LLMError`(网络/4xx/5xx)→ 走 retry 路径
  - `StreamError`(中流)→ mid-stream 不可重试
- 本轮 stream_chat 错误分类**完全对齐**
- 单元测试不重复测 retry 行为(在 test_llm_stream_retry.py 已覆盖 11 个)
- 集成验证:`stream_chat_with_retry(AnthropicLLMProvider_instance, ...)` 应该无缝工作(没显式加测试,因为 retry 测试用 `_ScriptedStreamLLM` mock 的)

---

## 7. 后续可能的工作

- A5 完成,Anthropic 协议这块暂时收口
- R8.5.1b 报告 §5 还有 B1-B4 + C1(4 家厂商的独有参数 / ProviderInfo 白名单),跟流式无关,等下次单独 round
- 流式 `usage` 解析(message_delta 里的 token 用量)留 R10+,跟 Tracer→EventBus 一起做
- `thinking_delta` / `input_json_delta` 支持留 R10+(extended thinking + tool use)

---

> 接手者:`git checkout master` 即可;`pytest tests/ --ignore=tests/test_cli.py -q` 看到 565 passed + ruff 0 即可接 R8.5.3 或 五期。
