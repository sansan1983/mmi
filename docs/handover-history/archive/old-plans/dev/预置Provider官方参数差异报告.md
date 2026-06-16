# 预置 Provider 官方 API 参数差异报告

> 生成日期：2026-06-05  
> 对比范围：mmi 预置的 5 家模型商（智谱 GLM、Kimi 月之暗面、千问 Qwen、DeepSeek、MiniMax）  
> 对比依据：各厂商 2026-06-05 官方文档  
> 对比对象：`OpenAILLMProvider.chat()` / `AnthropicLLMProvider.chat()` 实际发送的参数

---

## 目录

1. [当前实现发什么](#1-当前实现发什么)
2. [智谱 GLM](#2-智谱-glm)
3. [Kimi 月之暗面](#3-kimi-月之暗面)
4. [千问 Qwen（阿里百炼）](#4-千问-qwen阿里百炼)
5. [DeepSeek](#5-deepseek)
6. [MiniMax（稀宇）](#6-minimax稀宇)
7. [跨 Provider 共性问题](#7-跨-provider-共性问题)
8. [建议改法](#8-建议改法)

---

## 1. 当前实现发什么

### OpenAILLMProvider（智谱 / Kimi / 千问 使用）

```python
# llm.py L316-323  chat()
resp = self.client.chat.completions.create(
    model=self.model,
    messages=messages,
    max_tokens=max_tokens,     # 默认 512
    temperature=temperature,   # 默认 0.7
)
```

**只发了 4 个参数**，大量标准 OpenAI 兼容参数未传递。

### AnthropicLLMProvider（DeepSeek / MiniMax 使用）

```python
# llm.py L480-488  chat()
payload = {
    "model": self.model,
    "max_tokens": max_tokens,   # 默认 512
    "temperature": temperature, # 默认 0.7
    "messages": user_msgs,
}
if system_parts:
    payload["system"] = "\n\n".join(system_parts)
```

**也只发了 4-5 个参数**，大量 Anthropic 兼容参数未传递。

### stream_chat 问题

- **OpenAILLMProvider.stream_chat()**：正确使用了 `stream=True`，参数与 chat() 一致，但缺少 `stream_options`（如 `{"include_usage": true}`）。
- **AnthropicLLMProvider.stream_chat()**：**不是真流式**，目前只是 `yield self.chat(...)` 整段返回（L500）。DeepSeek 和 MiniMax 都支持 SSE 真流式。

---

## 2. 智谱 GLM

- **文档**：https://docs.bigmodel.cn/cn/api
- **API 风格**：OpenAI 兼容
- **端点**：`https://open.bigmodel.cn/api/paas/v4/chat/completions`
- **代码中 api_key_env**：`GLM_API_KEY`
- **代码中 base_url**：`https://open.bigmodel.cn/api/paas/v4`

### 参数对照表

| 官方参数 | 类型 | 必需 | 代码是否发送 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | ✅ | |
| `messages` | array | 是 | ✅ | |
| `max_tokens` | integer | 否 | ✅ | 默认 512，建议改为 4096 |
| `temperature` | number | 否 | ✅ | 默认 0.7 |
| `top_p` | number | 否 | ❌ | 0-1，默认 0.95 |
| `stop` | string/array | 否 | ❌ | 停止词 |
| `stream` | boolean | 否 | ❌ | chat() 不传；stream_chat() 传了 |
| `stream_options` | object | 否 | ❌ | 含 `include_usage` |
| `response_format` | object | 否 | ❌ | `{"type": "json_object"}` |
| `tools` | array | 否 | ❌ | GLM-4 支持工具调用 |
| `tool_choice` | object | 否 | ❌ | |

**独有参数**：无特殊项。

---

## 3. Kimi 月之暗面

- **文档**：https://platform.kimi.com/docs/api/overview
- **API 风格**：OpenAI 兼容
- **端点**：`https://api.moonshot.cn/v1/chat/completions`
- **代码中 api_key_env**：`MOONSHOT_API_KEY` ✅
- **代码中 base_url**：`https://api.moonshot.cn/v1` ✅

### 参数对照表

| 官方参数 | 类型 | 必需 | 代码是否发送 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | ✅ | |
| `messages` | array | 是 | ✅ | |
| `max_tokens` | integer | 否 | ✅ | ⚠️ 官方已弃用，用 `max_completion_tokens` 替代 |
| `max_completion_tokens` | integer | 否 | ❌ | 替代 `max_tokens` |
| `response_format` | object | 否 | ❌ | |
| `stop` | string/array | 否 | ❌ | |
| `stream` | boolean | 否 | ❌ | |
| `stream_options` | object | 否 | ❌ | |
| `tools` | array | 否 | ❌ | Kimi 支持函数调用 |

### 关于 `temperature` / `top_p` / `presence_penalty` / `frequency_penalty`

**Kimi 官方文档中没有公布这些参数**。实测/API 层面可能忽略它们，建议对 Kimi 不发送这些参数。

### Kimi 独有参数（需 `extra_body` 传递）

| 参数 | 类型 | 说明 |
|---|---|---|
| `thinking` | object | 推理参数（见 overview 页），需要通过 `extra_body` 传递 |
| `prompt_cache_key` | string | 提示缓存（文档中有的参数） |
| `safety_identifier` | string | 安全标识 |

### 额外说明

- Kimi 支持 messages 中的 `partial` 角色（部分内容模式）
- Kimi 支持联网搜索（需额外参数）
- 不支持 `seed`、`user`、`tool_choice`（文档中未出现）

---

## 4. 千问 Qwen（阿里百炼）

- **文档**：https://help.aliyun.com/zh/model-studio/developer-reference/use-qwen-by-chat-completions-json-input
- **API 风格**：OpenAI 兼容
- **端点**：`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`
- **代码中 api_key_env**：`DASHSCOPE_API_KEY` ✅
- **代码中 base_url**：`https://dashscope.aliyuncs.com/compatible-mode/v1` ✅

### 参数对照表

| 官方参数 | 类型 | 必需 | 代码是否发送 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | ✅ | |
| `messages` | array | 是 | ✅ | |
| `max_tokens` | integer | 否 | ✅ | 默认 512 |
| `temperature` | number | 否 | ✅ | 默认 0.7 |
| `top_p` | number | 否 | ❌ | 0-1，默认 0.9 |
| `stop` | string/array | 否 | ❌ | string 或 array of strings |
| `stream` | boolean | 否 | ❌ | |
| `stream_options` | object | 否 | ❌ | |
| `response_format` | object | 否 | ❌ | 支持 `{"type": "json_object"}` |
| `tools` | array | 否 | ❌ | 千问支持函数调用 |
| `tool_choice` | string | 否 | ❌ | |

### 千问独有参数

| 参数 | 类型 | 说明 | 推荐发送 |
|---|---|---|---|
| `repetition_penalty` | number | 1.0-2.0，默认 1.1。**不是 `presence_penalty`** | 按需 |
| `enable_search` | boolean | 是否启用联网搜索，默认 false | 按需 |
| `search_options` | object | 搜索参数配置 | 按需 |

### ⚠️ 注意

千问的 `repetition_penalty` 与 OpenAI 的 `presence_penalty` / `frequency_penalty` 是不同的参数，不能混用。

---

## 5. DeepSeek

- **文档**：https://api-docs.deepseek.com/zh-cn/
- **API 风格**：**Anthropic**（首选）/ OpenAI 兼容（备选）
- **Anthropic 端点**：`https://api.deepseek.com/anthropic/v1/messages`
- **代码中 api_key_env**：`DEEPSEEK_API_KEY` ✅
- **代码中 base_url**：`https://api.deepseek.com` ✅
- **代码中 anthropic_base_url**：`https://api.deepseek.com/anthropic` ✅

### 参数对照表（Anthropic 风格）

| 官方参数 | 类型 | 必需 | 代码是否发送 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | ✅ | |
| `messages` | array | 是 | ✅ | |
| `max_tokens` | integer | 是 | ✅ | 默认 512，建议 4096 |
| `temperature` | number | 否 | ✅ | 默认 0.7 |
| `system` | string | 否 | ✅ | |
| `top_p` | number | 否 | ❌ | |
| `stop_sequences` | array of string | 否 | ❌ | 最多 5 条（Anthropic 协议名称，与 OpenAI 的 `stop` 不同） |
| `stream` | boolean | 否 | ❌ | `stream_chat()` 不是真流式 |

### DeepSeek 特殊说明

- **Anthropic 协议下 `stop_sequences` 是正确参数名**，不是 OpenAI 的 `stop`
- stream 支持 SSE，但当前 `AnthropicLLMProvider.stream_chat()` 是假的（只 yield 整段）
- DeepSeek 的 function calling 走 OpenAI 风格参数，在 Anthropic 协议下需要做格式转换

---

## 6. MiniMax（稀宇）

- **文档**：https://platform.minimaxi.com/docs/api-reference/text-anthropic-api
- **API 风格**：**Anthropic**（首选）/ OpenAI 兼容（备选）
- **Anthropic 端点**：`https://api.minimax.chat/v1/text/anthropic-chat`
- **代码中 api_key_env**：`MiniMax_API_KEY` ⚠️
- **代码中 base_url**：`https://api.minimax.chat/v1/text/anthropic-chat` ✅
- **代码中 minmax_base_url_for_openai**：`https://api.minimax.chat/v1/text/chatcompletion_v2` ✅

### 参数对照表（Anthropic 风格）

| 官方参数 | 类型 | 必需 | 代码是否发送 | 说明 |
|---|---|---|---|---|
| `model` | string | 是 | ✅ | |
| `messages` | array | 是 | ✅ | |
| `max_tokens` | integer | 是 | ✅ | 默认 512 |
| `temperature` | number | 否 | ✅ | 默认 0.7 |
| `system` | string | 否 | ✅ | |
| `top_p` | number | 否 | ❌ | 0-1，默认 0.95 |
| `stop_sequences` | array of string | 否 | ❌ | 最多 5 条 |
| `stream` | boolean | 否 | ❌ | `stream_chat()` 不是真流式 |
| `frequency_penalty` | number | 否 | ❌ | MiniMax 支持的独有参数 |

### ⚠️ `api_key_env` 大小写

**当前代码**：`"MiniMax_API_KEY"`  
**文档写法**：`Bearer $MINIMAX_API_KEY`  
**建议**：改为 `"MINIMAX_API_KEY"`（全大写），与环境变量命名惯例一致。

---

## 7. 跨 Provider 共性问题

### 7.1 `providers.py` 中 API Key 环境变量名

| Provider | 当前值 | 官方文档值 | 正确？ |
|---|---|---|---|
| DeepSeek | `DEEPSEEK_API_KEY` | `$DEEPSEEK_API_KEY` | ✅ |
| MiniMax | `MiniMax_API_KEY` | `$MINIMAX_API_KEY`（文档暗示） | ❌ 建议 `MINIMAX_API_KEY` |
| 智谱 | `GLM_API_KEY` | 文档未指定 | 可以接受 |
| Kimi | `MOONSHOT_API_KEY` | `$MOONSHOT_API_KEY` | ✅ |
| 千问 | `DASHSCOPE_API_KEY` | `$DASHSCOPE_API_KEY` | ✅ |

### 7.2 `stream_chat` 真流式问题

- **OpenAILLMProvider.stream_chat()** — 已用 `stream=True`，正确。
- **AnthropicLLMProvider.stream_chat()** — 当前实现不是真流式：

```python
# llm.py L498-500
def stream_chat(self, messages, *, max_tokens=512, temperature=0.7):
    yield self.chat(messages, max_tokens=max_tokens, temperature=temperature)
```

DeepSeek 和 MiniMax 的 Anthropic 端点都支持 SSE 流式，需要按 Anthropic SSE 协议解析增量 `content_block_delta` 事件。

### 7.3 `max_tokens` 默认值

当前默认 512，对于实际对话生成太短。各家默认推荐值：
- 智谱：4096
- Kimi：用 `max_completion_tokens`，推荐 4096
- 千问：4096
- DeepSeek：4096
- MiniMax：4096

### 7.4 缺少的关键参数（两套协议分别）

**OpenAILLMProvider 缺少：**
- `top_p`（所有 3 家都支持）
- `stop`（所有 3 家都支持）
- `response_format`（所有 3 家都支持 JSON Mode）
- `tools` / `tool_choice`（智谱/Kimi/千问都支持函数调用）
- `stream_options`（所有 3 家都支持）
- `presence_penalty` / `frequency_penalty`（部分支持）

**AnthropicLLMProvider 缺少：**
- `top_p`（DeepSeek/MiniMax 都支持）
- `stop_sequences`（DeepSeek/MiniMax 都支持）
- 真 SSE stream（两家都支持）

---

## 8. 建议改法

### 方案 A：最小改动（推荐，约半天）

**不改架构**，只在当前两个 LLM Provider 内部补充参数：

1. **`OpenAILLMProvider.chat()`** — 在 payload 中加入：
   - `top_p`（从 `**kwargs` 或固定默认）
   - `stop`（同上）
   - `response_format`（同上）
   - `stream_options`（同上）

2. **`AnthropicLLMProvider.chat()`** — 在 payload 中加入：
   - `top_p`
   - `stop_sequences`

3. **`AnthropicLLMProvider.stream_chat()`** — 改为真 SSE 流式

4. **`providers.py`** — MiniMax `api_key_env` 改为 `"MINIMAX_API_KEY"`

5. **`max_tokens` 默认值** — 改为 4096

### 方案 B：完整方案（3-5 天）

1. `ProviderInfo` 增加 `supported_params` 白名单
2. 两个 LLM Provider 创建 `_build_payload()`，根据 Provider 过滤参数
3. 每家独有参数分别处理：
   - Kimi：`thinking` (extra_body), `prompt_cache_key`, `safety_identifier`, `max_completion_tokens`，**跳过 temperature**
   - 千问：`repetition_penalty`, `enable_search`
   - DeepSeek/MiniMax：`stop_sequences`（Anthropic 协议名）
4. 实现 Anthropic SSE 真流式
5. 完整的单元测试覆盖参数组合

### 方案 C：暂不处理（等后续架构重构）

涉及重构 LLM Provider 层的参数 schema 定义，建议放到后续架构升级中统一实现。

---

## 附录：相关代码文件

| 文件 | 作用 |
|---|---|
| `mmi/core/providers.py` | Provider 信息定义（名称/端点/API Key env 等） |
| `mmi/core/llm.py` | LLM Provider 实现（OpenAILLMProvider / AnthropicLLMProvider） |
| `mmi/core/config.py` | 配置加载（`resolve_api_key` 等） |

## 附录：官方文档来源（2026-06-05 验证）

| Provider | 文档 URL |
|---|---|
| 智谱 GLM | https://docs.bigmodel.cn/cn/api |
| Kimi 月之暗面 | https://platform.kimi.com/docs/api/overview |
| 千问 Qwen | https://help.aliyun.com/zh/model-studio/developer-reference/use-qwen-by-chat-completions-json-input |
| DeepSeek | https://api-docs.deepseek.com/zh-cn/ |
| MiniMax | https://platform.minimaxi.com/docs/api-reference/text-anthropic-api |
