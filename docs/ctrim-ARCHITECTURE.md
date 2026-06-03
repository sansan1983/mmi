# C-CLI 会话记忆系统 — 架构总说明书

> 本文件是开发宪法。所有代码、数据格式、阶段任务必须以本文为准；如需偏离，先改本文档再改代码。

---

## 0. 术语表

| 术语 | 定义 |
|---|---|
| **Session（会话）** | 一组有共同主题的、用户与 LLM 之间的多轮对话，持久化到单个文件。 |
| **Turn（轮）** | 一对 User + Assistant 消息，是会话的最小可见单位。 |
| **Index（索引）** | 启动时只扫描会话 frontmatter 构建的内存清单，**不读正文**。 |
| **Loader（加载器）** | 根据当前问题，按需从正文里捞出相关段落的组件。 |
| **Frontmatter** | 会话文件第 1 行的 YAML 元数据块（`---` 包裹），机器可解析。 |
| **Body（正文）** | frontmatter 之下的 Markdown 对话记录，按日期分段。 |
| **Summary（摘要）** | 由 LLM 生成的、整段会话的浓缩文本，每次送进 LLM 时都会带上。 |
| **Heat（热度）** | 反映一个会话被访问频率和近期程度的数值，用于排序与淘汰。 |
| **State（状态）** | 会话生命周期阶段：`active` / `warm` / `cold` / `zombie`。 |
| **Trash（杂项）** | 被判定为无主题的短会话，单独存放并带 TTL 自动清理。 |
| **三态扫描** | 启动扫 frontmatter（轻）→ 用户选中扫摘要（中）→ 必要时扫正文（重）。 |
| **LLM 上下文** | 本次调用 LLM 时实际送入的 messages 列表，**永远不等于聊天记录的完整内容**。 |

---

## 1. 一句话定位

一个**自带记忆与上下文处理的智能体主板（Agent Mainboard）**。可聊天、可干活（调工具）、可看（图像/文件）、可听可说（语音）、可对接消息平台（飞书/企微/Telegram 等）。所有能力以**模块化接口**接入，核心保持**轻量但不简陋** —— 主板自带的能力必须完善好用，扩展模块按需装载，新功能像外设一样"插上就用"，不影响主板本身的精简与稳定。

类比：**电脑主机** —— 主板带 CPU/内存/总线和标准插槽（PCIe/USB），外设（显卡、声卡、网卡）通过标准接口接入，升级外设不换主板。主板出厂时自带的集成声卡/网卡虽然不如独立外设强，但必须能开箱即用、好用。

> **命名**：产品名 **C-Trim**（Context Trim，上下文修剪）。包名 / 命令 / Python 包统一使用小写 `ctrim`。产品名与包名解耦，未来如要改品牌只需更新 `__product_name__`，不影响命令。

---

## 2. 核心原则（不可违反）

```
1. UI ≠ 推理          界面只负责显示和导航，不参与上下文决策。
2. 显示 ≠ 发送         用户能看到的内容，不等于 LLM 收到内容。
3. 聊天记录 ≠ LLM 上下文  历史完整保存，但送进 LLM 的永远只是摘要 + 最近 N 轮 + 命中段。
4. 不依赖用户记 ID     用标题模糊搜索即可定位。
5. 核心可独立运行       core/ 目录可在没有 UI 的情况下被任意脚本调用。
6. 轻量优先，功能不打折  主板自身保持小而精，但自带能力必须完善（不为了"轻"而砍体验）。
                       复杂/可选能力通过模块扩展，不塞进核心。
7. 模块即外设          任何新能力（消息平台、IO、工具、LLM 提供方）都通过标准接口注册，
                       主板不感知其存在。删除/替换模块不影响主板运行。
```

---

## 3. 架构总览

```
┌────────────────────────────────────────────────────────┐
│  UI 层 (cli.py / tui.py / gui/)                        │
│  - 只调 SessionManager 的公开 API                       │
│  - 不直接读会话文件                                     │
└────────────────┬───────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────┐
│  核心层 (core/)                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ SessionManager│  │ SessionLoader│  │ LLM Client   │  │
│  │ (CRUD+状态)  │  │ (按需加载)   │  │ (OpenAI 兼容) │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │          │
│  ┌──────▼─────────────────▼──────────────────▼───────┐  │
│  │  Storage (JSONL + 文件锁) + Index (内存 frontmatter) │ │
│  └────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────────────┐
│  数据层 (~/.ctrim/)                                      │
│  ├── sessions/active/  *.session.md                    │
│  ├── sessions/trash/   *.session.md   (TTL 清理)        │
│  └── index.json     (可选持久化索引缓存)                 │
└────────────────────────────────────────────────────────┘
```

**数据流（用户发问一次）**：

1. UI 把"用户输入 + 当前 session_id"交给 `SessionManager`
2. `SessionManager` 调 `SessionLoader.build_context()` 拿上下文
3. `Loader` 返回：摘要 + 最近 N 轮 + 关键词命中的段落
4. `SessionManager` 拼上当前问题，调 `LLM Client`
5. LLM 返回后追加到会话正文，更新 frontmatter（heat / last_access / summary_version）
6. 写回磁盘（带文件锁）

---

## 3.5 主板 / 模块化扩展架构

> **同时回答两个目标**：
> - **轻量** —— 主板只定义接口与协议（薄），不实现任何具体扩展能力（不重）。
> - **开放** —— 接口契约稳定、版本化、可发现、可热插拔。
>
> 原则：**主板 = 总线；模块 = 外设。** 主板不知道也不关心外设的具体形态。

### 3.5.1 分层与依赖方向

```
┌──────────────────────────────────────────────────┐
│  扩展模块（plugins/ 或独立 pip 包）                │
│  - 消息平台（feishu/telegram/...）                 │
│  - 多模态 IO（image/audio/tts/stt）                │
│  - 工具（browser/shell/sandbox）                  │
│  - LLM 提供方（openai/anthropic/ollama）           │
└──────────────┬───────────────────────────────────┘
               │ 通过 §3.5.2 的接口契约接入
┌──────────────▼───────────────────────────────────┐
│  主板（C-Trim 仓库本体）                             │
│  - core/modules/  ← 只有接口与注册中心，零实现      │
│  - 其余 core/（session/loader/llm/summarizer...） │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│  UI（cli / tui / gui）                            │
└──────────────────────────────────────────────────┘
```

**硬约束**：主板的 `core/modules/` 目录里**只有协议定义和注册中心**，没有任何具体模块的实现代码。模块可以内置在 `plugins/` 目录里（开箱即用），也可以是用户单独 `pip install` 的第三方包。

### 3.5.2 模块清单（ModuleManifest）

每个模块根目录必须有 `module.yaml`：

```yaml
name: feishu-channel
version: 1.0.0
mainboard_min_version: ">=0.1.0"
description_zh: 飞书消息平台接入
description_en: Feishu (Lark) messaging channel
capabilities:
  - channel
entry_point: feishu_channel:FeishuChannel   # import_path:ClassName
i18n:
  zh-CN: ./locales/zh-CN.json
  en-US: ./locales/en-US.json
dependencies:
  - lark-oapi>=1.2.0
hooks:
  - on_message
  - on_session_open
```

**字段含义**：

- `capabilities`：声明模块提供哪类能力（见 §3.5.3）
- `entry_point`：Python 入口类，**必须**实现对应 Capability 的基类
- `i18n`：模块自己的多语言文案，按主板语言自动加载
- `hooks`：订阅主板生命周期事件（见 §3.5.4）

### 3.5.3 能力（Capability）注册

主板预定义五类 Capability 接口（都是抽象基类，零实现）：

| Capability | 基类 | 模块要实现的方法 | 示例模块 |
|---|---|---|---|
| `channel` | `Channel` | `start / stop / send / on_message` | feishu / telegram / wecom |
| `io` | `IO` | `read / write` | image / audio / tts / stt |
| `tool` | `Tool` | `name / description / parameters / run` | browser / shell / sandbox |
| `storage` | `Storage` | `read / write / list / lock` | 本地 FS / S3 / WebDAV |
| `llm_provider` | `LLMProvider` | `chat / stream / count_tokens` | openai / anthropic / ollama |

**关键设计**：主板只暴露**接口契约**，不暴露任何具体实现。这样：

- 主板编译产物保持极小（无飞书 SDK、无浏览器、无 TTS 模型）
- 用户可按需 `pip install ctrim[feishu]`、`ctrim[gui]`、`ctrim[voice]`（extras_require 机制）
- 第三方可以发布独立的 `ctrim-feishu-plugin` 包，无需修改主板

### 3.5.4 生命周期 Hooks

主板在以下节点广播事件，模块可订阅：

| Hook | 触发时机 | 模块可用参数 |
|---|---|---|
| `on_session_open` | 新会话创建 | `session_id` |
| `on_session_close` | 会话归档/删除 | `session_id` |
| `on_message` | 用户输入或 LLM 输出 | `session_id, role, content` |
| `on_tool_call` | Tool 被调用前后 | `tool_name, arguments, result` |
| `on_module_load` | 模块首次加载 | `module_name` |
| `on_config_change` | 用户改配置 | `key, old, new` |

**实现机制**：主板内置一个 `HookBus`，模块在 `__init__` 里 `bus.subscribe("on_message", self.handle)`。Hook 失败必须隔离（一个模块挂了不能影响其他模块和主板）。

### 3.5.5 消息平台（Channel）接入范式

消息平台是最高频的扩展需求，单独定义范式：

```python
from ctrim.core.modules import Channel, Message, ChannelMeta

class FeishuChannel(Channel):
    meta = ChannelMeta(
        name="feishu",
        display_name_zh="飞书",
        display_name_en="Feishu",
        config_keys=["app_id", "app_secret", "webhook_url"],
    )

    async def start(self): ...        # 注册 webhook
    async def stop(self): ...         # 注销
    async def send(self, msg: Message): ...
    async def on_message(self, callback): ...   # 注册消息回调
```

**关键约束**：

- Channel 与 Session **解耦**：一个飞书群的消息可路由到任意 session（通过 `session_id` 显式声明或规则匹配）
- Channel 收到消息后调 `SessionManager.ingest()`，**不直接调 LLM**
- 长连接 / Webhook / WebSocket 三种接入方式由 Channel 内部决定，主板不感知

### 3.5.6 多模态 IO 接口

`Message.content` 是一组 `ContentBlock`，支持以下类型：

```python
class ContentBlock: ...
class TextBlock(ContentBlock): ...
class ImageBlock(ContentBlock):       # 看
    url: str | None = None
    path: Path | None = None
    base64: str | None = None
class AudioBlock(ContentBlock):       # 听
    path: Path
    transcript: str | None = None     # STT 后填入
class FileBlock(ContentBlock):
    path: Path
    mime: str
```

**视觉/听觉能力检测**：

- 主板在 `LLMProvider` 上声明 `capabilities: list[VisionCapable | AudioCapable]`
- 若用户传入图像但当前 LLM 不支持视觉 → 自动降级为"提示用户当前 LLM 不支持看图"（而不是静默丢弃）

### 3.5.7 双语 i18n 规范

**这是主板基线，不是扩展。** 所有用户可见字符串必须 `t("key")` 包裹。

```python
from ctrim.core.i18n import t

print(t("session.list.empty"))   # → "暂无会话" 或 "No sessions"
print(t("session.list.empty", lang="en-US"))
```

- 主板自带 `locales/zh-CN.json`（默认）和 `locales/en-US.json`
- 启动时检测 `LANG` 环境变量；CLI 加 `--lang <zh-CN|en-US>` 覆盖
- 模块自带的 locales 与主板 locales 合并（key 冲突时模块优先）
- **禁止硬编码用户可见字符串**

### 3.5.8 模块加载机制

**发现**（按优先级）：

1. 内置模块：`ctrim/plugins/<name>/`
2. 同目录插件：`./ctrim-plugins/<name>/`
3. pip 安装的插件：`importlib.metadata.entry_points(group="ctrim.modules")`

**加载流程**：

```
启动 → 扫描所有 module.yaml → 解析 capabilities 和 entry_point
     → 校验 mainboard_min_version 兼容
     → 实例化入口类 → 调用 module.on_module_load()
     → 注册到对应 Capability 注册表
     → 模块自带的 i18n 合并到全局 t() 字典
```

**禁用模块**：`~/.ctrim/config.toml` 里加 `[modules] disabled = ["feishu-channel"]`，启动时跳过加载。

**冲突解决**：同一 Capability 多模块时（如同时装两个 LLM 提供方），由用户 `~/.ctrim/config.toml` 指定默认；运行时可在 CLI 临时切换。

### 3.5.9 主路线图（Phase 7+，可选）

> Phase 1-6 是主板 MVP。Phase 7+ 是基于主板的扩展实现，**不影响主板本身**。

| Phase | 名称 | 说明 |
|---|---|---|
| 7 | 飞书/Telegram 接入 | 第一个 Channel 模块 |
| 8 | 多模态 IO | image / tts / stt 模块 |
| 9 | 工具调用 | browser / shell / sandbox |
| 10 | 同步与备份 | S3 / WebDAV storage 扩展 |
| 11 | 第三方 LLM 提供方 | anthropic / ollama / deepseek |
| 12 | 跨会话知识库 | embedding 检索模块 |

### 3.5.10 轻量与开放的具体落地

| 维度 | 怎么做 |
|---|---|
| **主板薄** | `core/modules/` 只有协议与注册中心，零业务实现 |
| **依赖少** | 主板 `pyproject.toml` 强依赖只有 ~5 个包（typer/portalocker/pyyaml/openai/textual） |
| **可选装** | 扩展能力走 `extras_require`：`pip install ctrim[feishu,voice,gui]` |
| **协议稳** | Capability 基类与 ModuleManifest 字段走 semver，破坏性变更升 major |
| **可发现** | `ctrim modules list` 列出所有已加载模块与 capabilities |
| **可热拔** | 删除模块文件 / 改 `disabled` 列表后重启即生效，无需改主板 |
| **可独立发** | 第三方可在 PyPI 发 `ctrim-xxx-plugin`，与主板解耦迭代 |

---

## 3.6 附加协议与契约

> §3 + §3.5 之外、影响接口兼容的契约集中在这里。**任何破坏性变更必须先改本节再改代码**（§9.0 原则）。

### 3.6.1 TUI 折叠块协议（TUI 私有）

**适用范围**：TUI ChatLog 渲染层。**不动 `core.body` 契约**——LLM 输出的 Markdown 正文里用 `> [...]` 起头的块，TUI 解析后渲染为可折叠块（OMP 风格：整行高亮 + 左侧色条），CLI 不解析、按普通 Markdown 显示。

**协议格式**（单行起头 + 多行延续）：

```
> [thinking] ...思考过程...
> 后续行必须以 "> " 开头才算同一块
> 最后一行

> [tool_call name=search] ...参数/结果...
> 多行参数延续
```

**两种块**：

| 块类型 | 起头 | 渲染 |
|---|---|---|
| `ThinkingBlock` | `> [thinking] <content>` | 紫色左侧色条 + dim 文字（CollapsibleStatic.-thinking）|
| `ToolCallBlock` | `> [tool_call name=<word>] <content>` | 绿色左侧色条 + dim 文字（CollapsibleStatic.-tool）|

**解析规则**（`ctrim/tui/parse_blocks.py::parse_blocks`）：

- 只认**行首**的 `> [thinking]` / `> [tool_call name=xxx]`（行中匹配不触发）
- 块起头行后，**所有以 `> ` 起始的后续行**算同块内容（直到非 `>` 行或文件末）
- 解析不到标记的行累积为 `TextBlock`（普通文本）
- 解析失败静默退化（不报错）——LLM 输出偶尔不带标记不影响渲染

**示例**：

LLM 输出：
```
好的，我来查 PG 集群。
> [thinking] 用户问的是分库分表，可能想了解 hash sharding
> 让我先列出当前节点数
> [tool_call name=list_nodes] SELECT * FROM pg_nodes
> 返回 3 节点
好的，3 节点。hash sharding 建议用 16 桶。
```

解析为：
- TextBlock: "好的，我来查 PG 集群。"
- ThinkingBlock: "用户问的是分库分表...让我先列出当前节点数"
- ToolCallBlock(name="list_nodes"): "SELECT * FROM pg_nodes\n返回 3 节点"
- TextBlock: "好的，3 节点。hash sharding 建议用 16 桶。"

**版本约束**：`name` 字段必须是 `[A-Za-z0-9_\-]+`（避免注入到 CSS class）。本协议走 semver，破坏性变更升 major。

### 3.6.2 LLM 流式契约（`stream_chat`）

**接口**（`ctrim/core/llm.py::LLMProvider.stream_chat`）：

```python
async def stream_chat(
    self,
    messages: list[dict],
    *,
    max_tokens: int = 512,
    temperature: float = 0.7,
) -> AsyncIterator[str]:
    """流式对话：逐步 yield 文本片段。"""
```

**设计要点**：

- **不是 `abstractmethod`**：默认实现抛 `NotImplementedError`。子类（测试用 Mock）不会被强制实现。
- **调用方契约**：`try/except NotImplementedError` 降级到 `chat()` 整段（TUI 的 `_do_chat` worker 走这条路径）。
- **async generator 而非 callback**：跟 `textual.worker` / `asyncio.to_thread` 配合更好。
- **错误传播**：底层错误抛 `LLMError`（继承自 `Exception`），调用方按需要 try/except。

**实现矩阵**：

| Provider | 实现 |
|---|---|
| `EchoLLMProvider` | 调一次 `chat()`，整体 yield（一次片段）|
| `OpenAILLMProvider` | 后台线程 + `queue.Queue` 包同步 stream，async generator 从队列取（避免 `run_in_executor` 死锁）|
| 第三方模块 | 建议实现；不实现也不破坏调用方（降级路径自动生效）|

**调用方示例**（TUI `_do_chat`）：

```python
try:
    async for chunk in app.mgr.llm.stream_chat(messages, ...):
        chat_log.append_assistant_chunk(chunk)
except NotImplementedError:
    # 降级到同步 chat
    reply = await asyncio.to_thread(app.mgr.llm.chat, messages, ...)
    chat_log.append_assistant_done(reply)
```

### 3.6.3 `~/.ctrim/config.toml` schema

**文件位置**：`~/.ctrim/config.toml`（跨平台，由 `ctrim.core.paths.get_config_path()` 解析）

**格式**：YAML 语法（**不**是 TOML——历史沿袭，扩展名是 `.toml` 但内容是 YAML；改格式会破坏现有用户配置）

**当前 schema**（Phase 5 引入，Phase 6 扩展）：

```yaml
# 默认 LLM 模型（/model 命令的目标）
llm:
  model: gpt-4o-mini    # 缺省值

# （Phase 6 规划）扩展模块禁用列表
# modules:
#   disabled:
#     - feishu-channel
#     - voice-io
```

**字段定义**：

| Key | 类型 | 缺省 | 说明 |
|---|---|---|---|
| `llm.model` | str | `"gpt-4o-mini"` | `/model <name>` 写入的目标；启动时 `get_default_model()` 读 |
| `modules.disabled` | list[str] | `[]` | （Phase 6+）跳过加载的模块名列表（匹配 `module.yaml` 的 `name`）|

**优先级**（以 `llm.model` 为例）：

1. 配置文件 `llm.model`
2. 环境变量 `OPENAI_MODEL`
3. 常量 `DEFAULT_MODEL = "gpt-4o-mini"`

**健壮性约定**（所有读路径必须遵守）：

- 文件不存在 → 静默回退到缺省值（首次跑会触发自动写一份最小 config）
- YAML 解析失败 → 静默回退到缺省值（不抛）
- 字段类型错误（`model: 123` 而非 str）→ 跳过该字段，回退到下一优先级
- 写盘失败（权限、磁盘满）→ 返回 `False`，UI 走默认值 + 通知

**版本约束**：新增字段走 semver minor；**重命名 / 删除字段升 major**（用户配置会丢值，必须先发 deprecation 警告）。

---

## 4. 项目结构

```
ctrim/
├── ctrim/
│   ├── __init__.py
│   ├── core/                  # 与 UI 无关的核心
│   │   ├── __init__.py
│   │   ├── session.py         # Session 数据类 / 状态机
│   │   ├── storage.py         # JSONL 读写、文件锁
│   │   ├── index.py           # 启动扫描 frontmatter 的内存索引
│   │   ├── loader.py          # 按需加载正文 + 构建 LLM 上下文
│   │   ├── llm.py             # LLM 客户端抽象（OpenAI 兼容）
│   │   ├── summarizer.py      # 摘要生成（含版本管理）
│   │   ├── titler.py          # 标题生成（前 N 轮）
│   │   ├── classifier.py      # 杂项识别（规则 + LLM）
│   │   ├── heat.py            # 热度计算 + 状态迁移
│   │   ├── search.py          # 关键词 / 模糊搜索
│   │   ├── paths.py           # 跨平台路径（~/.ctrim/）
│   │   └── manager.py         # SessionManager（对外 API 门面）
│   ├── cli.py                 # CLI 入口（typer）
│   ├── tui.py                 # TUI 入口（textual）
│   └── gui/                   # GUI（Phase 6，Electron 或 Tauri）
├── tests/
│   ├── test_storage.py
│   ├── test_index.py
│   ├── test_loader.py
│   ├── test_heat.py
│   └── fixtures/
├── docs/
│   ├── ARCHITECTURE.md        # 本文件
│   └── CHANGELOG.md
├── pyproject.toml
└── README.md
```

---

## 5. 会话文件格式（权威定义）

```markdown
---
version: 1
type: session
session_id: 01HXYZABCDEF...     # ULID，26 字符，时序可排序
agent_id: ctrim
title: "postgres-sharding-design"
summary: "讨论 PG 分库分表，已确定 hash shard，未决定扩容方案"
summary_version: 3
summary_history:                 # 摘要变更轨迹，避免漂移
  - { version: 1, at: "2026-05-28T10:00:00Z", text: "..." }
  - { version: 2, at: "2026-05-29T12:00:00Z", text: "..." }
keywords: [postgres, sharding, connection-pool]
created_at: 2026-05-28T10:00:00Z
updated_at: 2026-05-30T15:30:00Z
last_access: 2026-05-30T15:30:00Z
access_count: 12
heat: 12
state: active                    # active / warm / cold / zombie
---

## 2026-05-28

**User:** 我有个 PG 集群想分库分表...

**Assistant:** 建议先用 hash shard...

## 2026-05-29

**User:** 那扩容的时候怎么办...

**Assistant:** 可以考虑一致性 hash...
```

**规则**：

- 文件扩展名：`.session.md`（编辑器能高亮 Markdown）
- 路径：`~/.ctrim/sessions/active/<session_id>.session.md`
- 杂项：`~/.ctrim/sessions/trash/<session_id>.session.md`（带 `trashed_at` 字段）
- frontmatter 是唯一权威源，正文可以被全文搜索重建

---

## 6. 关键数据流

### 6.1 启动流程

```
读取 ~/.ctrim/sessions/active/*.session.md
   ↓
对每个文件只读到第二个 "---"
   ↓
解析 frontmatter → SessionMeta 列表
   ↓
按 heat 降序排序 → 内存索引
   ↓
TUI/CLI 直接显示前 10 条
```

### 6.2 单次对话流程

```
用户输入
   ↓
SessionManager.chat(session_id, user_input)
   ↓
loader.build_context(session_id, user_input)
   ├─ 1. 读 frontmatter → summary
   ├─ 2. 读正文最后 N 轮（默认 10）
   └─ 3. 关键词检索 → top_k 段落（默认 3）
   ↓
messages = [system: summary, ...recent, ...hits, current]
   ↓
llm.chat(messages)
   ↓
追加 turn 到正文
更新 frontmatter（heat, last_access, updated_at, summary_version if needed）
   ↓
文件锁写入磁盘
```

### 6.3 摘要更新流程

```
新 turn 追加后
   ↓
判断是否需要重生摘要（规则见 §8.3）
   ↓
若需要：
   ├─ 把旧 summary 推入 summary_history
   ├─ 用 [旧 summary + 新增 turns] 调 LLM 生成新 summary
   └─ summary_version += 1
   ↓
写回 frontmatter（不重写正文）
```

---

## 7. 核心类 / API 草案

```python
# core/session.py
@dataclass
class SessionMeta:
    session_id: str
    title: str
    summary: str
    summary_version: int
    keywords: list[str]
    created_at: datetime
    updated_at: datetime
    last_access: datetime
    access_count: int
    heat: float
    state: Literal["active", "warm", "cold", "zombie"]

class Session:
    meta: SessionMeta
    body: str  # 完整 Markdown 正文

# core/manager.py
class SessionManager:
    def list_sessions(self, limit: int = 10) -> list[SessionMeta]: ...
    def search(self, query: str) -> list[SessionMeta]: ...
    def create(self) -> Session: ...
    def get(self, session_id: str) -> Session: ...
    def chat(self, session_id: str, user_input: str) -> str: ...
    def archive(self, session_id: str) -> None: ...
    def delete(self, session_id: str) -> None: ...
```

**UI 层只允许调 `SessionManager` 的方法**。直接读写文件的代码只能在 `core/storage.py` 内。

---

## 8. 关键规则

### 8.1 杂项识别（避免垃圾污染）

**两段判定**：

1. **规则预筛**（无 LLM 调用）：
   - 总会话 < 3 轮 **且** 总字符 < 200 → 直接 trash
2. **LLM 二次确认**（仅 3-20 轮时）：
   - prompt：判断"是否在讨论一个具体项目 / 主题"
   - 回答"否"或置信度 < 0.6 → trash
3. **trash TTL**：默认 7 天自动清理

### 8.2 标题生成

- 时机：会话达到 10 轮时触发一次；20 轮时复核
- 失败兜底：LLM 调用 3 次仍无法生成主题 → 归类 trash
- 规则：**禁止用第一轮 User 消息作为标题**（"你好"开场失效）

### 8.3 摘要更新触发条件

满足任一即重生：

- 自上次摘要以来新增 ≥ 20 轮
- 自上次摘要以来新增 ≥ 5000 字符
- 距上次摘要 > 24 小时且新增 ≥ 5 轮

### 8.4 热度计算

```python
heat = (
    access_count * 1.0
    + recency_bonus(last_access)      # 1 天内 +10, 7 天 +5, 30 天 +1
    - age_penalty(created_at)         # 每 30 天 -1
)
```

- `heat >= 10` → `active`（前 10 列表）
- `5 <= heat < 10` → `warm`（折叠显示）
- `0 <= heat < 5` → `cold`（归档，仅搜索可见）
- `heat < 0` 或 `state == cold` 持续 90 天 → `zombie`（下次清理时删除）

### 8.5 LLM 上下文预算

**单次 LLM 调用的 messages 总量硬上限：4k tokens**（可配置）。超出时按"摘要 > 命中段 > 最近轮"优先级截断。

---

## 9. 阶段任务清单

> 每个 Phase 完成后必须打 tag（`v0.1.0-phase1` 等）并写 CHANGELOG。

### 9.0 Phase 收尾交接规范（不可跳过）

每完成一个 Phase，必须按顺序执行下列五步，**未完成不得开始下一个 Phase**：

1. **跑完整测试套件** —— `pytest tests/ -v` 必须全绿，任何失败必须先修复
2. **更新 `docs/SESSION_LOG.md`** —— 追加本轮日记：做了什么、踩了什么坑、下一轮接哪里
3. **更新 `docs/HANDOVER.md`** —— 修正"当前 Phase"、"下一步"、"已完成"段落
4. **`git commit` + 打 tag** —— commit message 形如 `phase N: <summary>`；tag 形如 `v0.1.0-phaseN`
5. **`git push origin main --tags`** —— 全自动推送，无需二次确认；推送完成后向用户汇报 commit hash + tag + 推送结果

**例外**：Phase 内的子任务（如 #1 paths.py、#2 storage.py）不触发本规范；只有整个 Phase 验收通过才触发。

### Phase 1：CLI 最小闭环（2-3 天）

**目标**：不引入 LLM 也能完整跑通"新建/选择/继续"。

- [ ] `ctrim/` 目录脚手架 + `pyproject.toml`
- [ ] `core/paths.py`：跨平台 `~/.ctrim/`
- [ ] `core/storage.py`：JSONL 追加写、frontmatter 解析（**仅解析，不调 LLM**）
- [ ] `core/session.py`：`Session` / `SessionMeta` dataclass
- [ ] `core/manager.py`：`create / list / get / append_turn`（append 用 echo 模拟 LLM）
- [ ] `cli.py`（typer）：
  - `ctrim new` → 创建会话，返回 session_id
  - `ctrim list` → 列出前 10 条
  - `ctrim chat <id>` → 进入 REPL，输入 `q` 退出
- [ ] `core/storage.py` 文件锁（`portalocker`）
- [ ] 测试：`tests/test_storage.py`、`tests/test_manager.py`

**验收**：
- `ctrim new && ctrim list && ctrim chat <id>` 全流程跑通
- 关掉再开能继续上次的会话
- 同一文件被两个进程打开不会撕裂

**明确不做**：压缩、摘要、GUI、真实 LLM 调用、杂项识别。

---

### Phase 2：命名与分类（2 天）

**目标**：不再用 ID 区分会话。

- [ ] `core/llm.py`：OpenAI 兼容客户端抽象（实现可走 echo 或真实端点）
- [ ] `core/titler.py`：基于前 N 轮生成标题
- [ ] `core/classifier.py`：规则预筛 + LLM 二次判定
- [ ] `core/manager.py` 增加 `trash()` 方法
- [ ] 后台 TTL 清理任务（`ctrim gc`，手动或定时）
- [ ] `tests/test_titler.py`、`tests/test_classifier.py`

**验收**：
- 短对话（"你好"/"天气"）自动进 trash
- 10 轮以上的正经对话有合理标题
- trash 目录 7 天后自动清空

**明确不做**：摘要、热度、TUI。

---

### Phase 3：摘要 + 滚动窗口（3-4 天）

**目标**：500 条历史的会话回复延迟 < 3s。

- [ ] `core/summarizer.py`：摘要生成 + 版本管理
- [ ] `core/loader.py`：按需加载（摘要 + 最近 N 轮 + 关键词命中）
- [ ] `core/search.py`：关键词检索（基础字符串匹配 + 简单 TF）
- [ ] `core/manager.py`：`chat()` 改造为走 Loader
- [ ] LLM 上下文预算硬上限（4k tokens）
- [ ] `tests/test_loader.py`、`tests/test_summarizer.py`

**验收**：
- 500 轮会话继续聊，LLM 调用上下文 < 4k tokens
- 关键词命中段落出现在 LLM 输入中
- `summary_version` 正确递增

**明确不做**：热度、TUI、embedding 检索。

---

### Phase 4：热度排序与生命周期（2 天）

**目标**：存储不无限增长。

- [ ] `core/heat.py`：热度计算 + 状态迁移
- [ ] `core/manager.py`：每次 `chat()` 触发 heat 重算
- [ ] 后台任务：定期把 cold 降级为 zombie
- [ ] `ctrim gc` 命令增强：dry-run / 强制执行
- [ ] `tests/test_heat.py`

**验收**：
- 一周不用的会话从 active 自动降为 warm
- 90 天的 cold 会话下次 gc 时被清理
- 列表排序按 heat 降序

**明确不做**：TUI、GUI。

---

### Phase 5：TUI 交互（3 天）

**目标**：键入 `pg` 就能找到 postgres 会话。

- [ ] `core/search.py` 增强：模糊匹配（`fuzzywuzzy` 或 `rapidfuzz`）
- [ ] `tui.py`（textual）：
  - 启动界面：前 10 条列表 + `s` 搜索 + `n` 新建
  - 搜索界面：实时过滤
  - 会话界面：当前会话的最近几轮 + 输入框
- [ ] 快捷键：`Ctrl+C` 退出、`/search` 切搜索、`/new` 新建

**验收**：
- TUI 内不调 LLM 也能浏览所有会话
- 搜索响应 < 100ms
- 同一会话在 CLI 和 TUI 之间无缝切换

**明确不做**：GUI、embedding 检索。

---

### Phase 6：GUI 外壳（5-7 天，可选）

**目标**：GUI 不增加任何 token 消耗。

- [ ] 选型：Electron + 本地 HTTP / Tauri
- [ ] GUI 只调 `SessionManager` 的 HTTP 包装
- [ ] 界面：左栏会话列表 + 中栏聊天记录 + 顶栏搜索框
- [ ] **硬约束**：GUI 不持有 LLM 上下文，遵循 §2 原则 2

**验收**：
- GUI 关掉不影响会话状态
- 1000 条历史会话的列表滚动流畅（靠分页/虚拟列表）

---

## 10. 主板基线 vs 可选扩展（边界）

### 10.1 主板必须自带、完善交付的能力

> 这些是**基线**。无论用户装不装扩展模块，主板自身都必须把这些做好。不允许"为了轻量就砍掉"。

- ✅ 会话存储、检索、生命周期管理（核心，无扩展替代）
- ✅ CLI + TUI 双前端（开箱即用）
- ✅ 双语界面（中文默认，可切英文）
- ✅ 文件锁、并发安全、数据完整性
- ✅ 摘要、热度、杂项清理等自维护机制
- ✅ LLM 上下文预算与截断（防止 token 爆炸）
- ✅ 至少一个 LLM 提供方实现（OpenAI 兼容）
- ✅ 错误提示、帮助文档、配置自检

### 10.2 主路线明确不做的（边界）

- ❌ 不实时压缩原文（**不压缩原文**，只压缩送进 LLM 的视图）
- ❌ 不把所有历史塞给 LLM
- ❌ 不依赖用户记 ID
- ❌ 不做复杂知识图谱
- ❌ 不做多用户 / 多租户
- ❌ 不做云端服务端部署（仅本地优先）
- ❌ 不锁定产品最终名（本架构锁定为 C-Trim，仅品牌可独立更新）

### 10.3 通过扩展模块可选提供的（主板不内置）

> 这些**不写在主板基线里**，由独立模块实现，避免主板臃肿：

- 🔌 消息平台接入（飞书 / 企微 / Telegram / Slack / Discord...）
- 🔌 多模态 IO（图像理解 / 语音 STT-TTS / 视频）
- 🔌 第三方工具调用（浏览器、Shell、文件操作代理、代码执行沙箱）
- 🔌 高级检索（embedding 向量检索、跨会话知识库）
- 🔌 GUI 桌面壳（Electron / Tauri）
- 🔌 同步与备份（云端同步、加密备份）
- 🔌 团队协作（共享会话、协作编辑）

**判定原则**：一项能力如果"主板自己也需要、且所有用户都用得到" → 进基线；"只有部分用户用得到、或者可以独立演进" → 进扩展模块。---

## 11. 依赖清单

| 包 | 用途 | 必需阶段 |
|---|---|---|
| `typer` | CLI | Phase 1 |
| `portalocker` | 跨平台文件锁 | Phase 1 |
| `pyyaml` | frontmatter 解析 | Phase 1 |
| `openai` | LLM 客户端 | Phase 2 |
| `textual` | TUI | Phase 5 |
| `rapidfuzz` | 模糊搜索 | Phase 5 |
| `pytest` | 测试 | Phase 1 |
| （可选）`httpx` | GUI HTTP 通信 | Phase 6 |
| （可选）`rich` | CLI 美化 | Phase 2 |

最小依赖原则：能少一个就少一个。

---

## 12. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 摘要成本爆炸（1000 条历史 × 每次启动重生） | 费用不可控 | 按需生成 + 仅状态变化时重生（§8.3） |
| 关键词检索漏命中 | LLM 答非所问 | Phase 5 引入模糊匹配；Phase 6+ 预留 `embedder.py` 接口 |
| 跨平台文件锁失败 | 数据撕裂 | 用 `portalocker`，CI 跑三平台测试 |
| LLM 端点切换导致行为差异 | 摘要质量不稳 | `llm.py` 抽象层 + 一组 fixture 端点测试 |
| 用户硬要"看完整历史"的诉求 | 与原则冲突 | 提供"展开正文"按钮，仅显示，不送 LLM |

---

## 13. 第一版即可验证的价值

- ✅ 关掉窗口能回来
- ✅ 不用记 session ID
- ✅ 不怕历史长
- ✅ Token 可控
- ✅ 不丢重要信息（原文完整保存）

---

## 附录 A：版本与变更

- v1.0（创建）：初始架构定义

**变更规则**：任何对数据格式、核心 API、原则的修改，必须先更新本文件并写入 CHANGELOG。
