# TUI 重做设计 — TypeScript + Ink

> 日期: 2026-06-06
> 状态: 已批准, 待实施
> 目标: 推翻现有 Textual TUI, 重做为 TypeScript + Ink 架构, 实现 Reasonix 级别透明极简体验
> 视觉规范: `docs/design/tui-visual-design.md`
> 技术参考: `docs/design/reasonix-display-analysis.md`

---

## 1. 目标

用 TypeScript + Ink 完整重做 MMI TUI, 满足五项硬指标:

1. **透明背景** — 跟随终端底色, 不强制涂背景
2. **增量 diff** — 虚拟 DOM diff, 只刷变更区域
3. **算法居中** — Yoga Flexbox 布局, 不硬编码
4. **流式无闪烁** — LLM token 逐字追加
5. **SIGWINCH 自适应** — 终端 resize 重新布局

约束:
- Python `core/` 业务层 **0 修改**
- 现有 `mmi/tui/` (Textual, 9 文件 2109 行) **全部删除**, git 历史兜底
- `pyproject.toml` 移除 `textual>=0.50` 依赖
- 单进程单实例 (锁文件防多开)

---

## 2. 架构

### 2.1 进程模型

两个独立进程, stdio JSON-RPC 通信:

```
┌─────────────────────────────┐         ┌──────────────────────────────┐
│  TypeScript TUI (Ink)       │ stdio   │  Python core (MMI)           │
│  ─────────────              │◄───────►│  ─────────────               │
│  Node.js 18+                │ JSON-RPC│  SessionManager              │
│  React + Ink + Yoga         │         │  MemoryEngine                │
│  进程: tui-ts 入口          │         │  Agent 调度                  │
│  spawn python -m mmi.core.ipc_server       │  进程: Python 子进程     │
└─────────────────────────────┘         └──────────────────────────────┘
       ↑                                          ↑
  mmi tui 命令                          用户数据 ~/.mmi/
  spawn ['node', dist]                  sessions/, memory/
```

**边界**:
- `core/` 不感知 UI 存在 (CLAUDE.md "UI ≠ 推理" 原则)
- TUI 进程退出码透传给 `mmi tui` 命令
- 单实例锁: `~/.mmi/run/tui.lock` (portalocker)

### 2.2 启动流程

1. 用户执行 `mmi tui`
2. `cli.py` 检测 `node >= 18`, 没有则提示安装并退出
3. `cli.py` 检测 `tui-ts/dist/mmi-tui.js` 存在, 没有则触发 `npm install && tsup build`
4. `cli.py` 获取锁文件 `~/.mmi/run/tui.lock` (portalocker)
5. `cli.py` `subprocess.Popen(['node', 'tui-ts/dist/mmi-tui.js'])`
6. TUI 进程启动, 内部 `spawn('python -m mmi.core.ipc_server', { stdio: ['pipe','pipe','pipe'] })`
7. TUI 渲染首屏 `<SessionHub/>`, 同时 IPC 调 `list_sessions`
8. 用户退出时 TUI 关子进程, `cli.py` 释放锁, 透传退出码

---

## 3. 目录结构

```
mmi/
├── core/                          # 不动
│   ├── ... (现有 业务/记忆/调度)
│   └── ipc_server.py              # 新增: stdio JSON-RPC 服务 (~200 行)
│
├── tui/                           # 删除 (9 文件 2109 行作废, git 兜底)
│
├── tui-ts/                        # 新增: TypeScript TUI
│   ├── package.json
│   ├── tsconfig.json
│   ├── tsup.config.ts
│   ├── src/
│   │   ├── cli.tsx                # 入口 (~30 行)
│   │   ├── app.tsx                # 顶层 <App> 组件
│   │   ├── ipc/
│   │   │   ├── client.ts          # JSON-RPC 客户端
│   │   │   ├── protocol.ts        # 请求/响应/事件类型
│   │   │   └── stream.ts          # 流式事件订阅
│   │   ├── theme/
│   │   │   ├── tokyo-night.ts     # 暗色配色
│   │   │   ├── light.ts           # 亮色配色
│   │   │   └── detector.ts        # OSC 11 亮度检测
│   │   ├── components/
│   │   │   ├── HeaderBar.tsx
│   │   │   ├── ChatLog.tsx
│   │   │   ├── MessageBlock.tsx
│   │   │   ├── CodeBlock.tsx
│   │   │   ├── FoldBlock.tsx
│   │   │   ├── Citation.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── StatusBar.tsx
│   │   │   ├── SlashMenu.tsx
│   │   │   ├── Divider.tsx
│   │   │   └── Pill.tsx
│   │   ├── screens/
│   │   │   ├── SessionHub.tsx
│   │   │   ├── Chat.tsx
│   │   │   └── HelpModal.tsx
│   │   ├── state/
│   │   │   ├── theme.tsx
│   │   │   ├── session.tsx
│   │   │   └── stream.tsx
│   │   └── utils/
│   │       ├── keystroke.ts
│   │       └── markdown.ts
│   └── dist/                      # tsup 产物 (gitignore)
│       └── mmi-tui.js
│
├── cli.py                         # 改: mmi tui 子命令
├── pyproject.toml                 # 改: 移除 textual 依赖
└── tests/
    ├── core/                      # 不动
    ├── tui/                       # 删除
    └── tui-ts/                    # 新增: 组件 + IPC 测试
```

预估体量: ~1900 行 TypeScript + 200 行 Python (新增 `ipc_server.py`)。

---

## 4. IPC 协议

### 4.1 格式

stdio JSON-RPC 2.0, 每行一个 JSON, `\n` 分隔 (LSP 风格)。

**Python 端 stdout 行缓冲** (防死锁):
```python
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, line_buffering=True)
```

### 4.2 请求 / 响应 / 事件

**请求** (TS → Python):
```json
{"jsonrpc":"2.0","id":1,"method":"list_sessions","params":{"limit":10,"sort":"heat"}}
```

**响应** (Python → TS):
```json
{"jsonrpc":"2.0","id":1,"result":{"sessions":[{"id":"01J...","title":"...","heat":12.3}]}}
```

**事件** (Python → TS, 无 `id`):
```json
{"jsonrpc":"2.0","method":"token","params":{"session_id":"01J...","delta":"你好"}}
```

### 4.3 方法清单

| 方法 | 方向 | 用途 |
|---|---|---|
| `list_sessions` | → Py | 会话总览, 按 heat 排序 |
| `search_sessions` | → Py | fuzzy 搜索 (rapidfuzz partial_ratio ≥ 60) |
| `create_session` | → Py | 新建会话 |
| `delete_session` | → Py | 移到 trash |
| `send_message` | → Py | 发消息, 后续靠 event 推送 token |
| `cancel` | → Py | 中断当前 LLM 流 |
| `get_config` | → Py | 读 theme/语言/默认模型 |
| `set_config` | → Py | 写 theme 覆盖等 |

### 4.4 事件清单

| 事件 | 用途 |
|---|---|
| `token` | LLM 流式 chunk (delta) |
| `tool_call` | Agent 调用工具 |
| `tool_result` | 工具结果 |
| `memory_hit` | 记忆检索命中 |
| `turn_done` | 一轮结束 (tokens/duration) |
| `error` | 错误信息 |

### 4.5 取消 / 错误

- 取消: TS 调 `cancel` → Python 中断 LLM stream (asyncio.CancelledError) → 推 `turn_done` with `cancelled: true`
- 错误: Python 推 `error` event → TS 渲染 `<ErrorCard>` 在 ChatLog

---

## 5. 关键组件设计

### 5.1 透明背景

Ink 默认不画背景色, **零代码**。约定:
- 任何组件都不设 `backgroundColor`
- 例外: `<Pill>` 标签 + 选中行高亮 (用 `#161b22` 微差异色)

终端背景亮度检测 (主题自适应):
```typescript
process.stdout.write('\x1b]11;?\x07')
// 解析响应: \x1b]11;rgb:RRRR/GGGG/BBBB\x1b\\
// 亮度 L = 0.299*R + 0.587*G + 0.114*B
// L > 0.5 → 亮色变体, 否则暗色
// 超时 200ms → 默认暗色
```

用户覆盖: `/theme dark|light` 命令, 持久化 `~/.mmi/config.toml` 的 `tui.theme` 字段。

### 5.2 不到边细分割线

`<Divider>` 自定义组件, 不依赖 Ink 的 `borderStyle`。默认宽度 = 终端列数 × 80%, 两端各留 10%。压线: 文字两侧空格包住, 线段从文字边缘延伸。

### 5.3 流式追加 + 自动滚动

- React Context 维护 session → token 缓冲的 map
- `event: token` 到达 → reducer 追加 → ChatLog 重渲染 → Ink diff 只输出新增字符
- 已完成的消息用 `<Static>` 标记, 不参与 diff, 大消息下保持性能
- `useEffect` 监测 token 缓冲增长 → 滚到底部

### 5.4 Markdown 渲染

本地简化解析器 (不引外部库):
- `## 标题` / `### 标题` / `**粗体**` / `*斜体*` / `` `内联代码` ``
- ``` ```code``` ``` 三反引号 → `<CodeBlock>` (树形线 + `cli-highlight` 语法高亮)
- `- 列表` / `1. 有序列表` / `> 引用`
- `[文字](url)` 链接 → `<Citation>` (前缀 `→`)
- 扩展 `:::thinking\n...\n:::` / `:::tool\n...\n:::` → `<FoldBlock>`

`cli-highlight` 是唯一外部依赖 (~50KB, 可接受)。

### 5.5 主题

暗色 (默认): Tokyo Night 色板
- 正文 `#c0caf5`, 用户标签 `#7dcfff`, 压线 `#7aa2f7`, 分割线 `#414868`, 关键词 `#9ece6a`

亮色: 镜像变体 (深灰底色适用)
- 正文 `#3a3a3a`, 用户标签 `#005faf`, 压线 `#005faf`, 分割线 `#c0c0c0`

完整色值表见 `docs/design/tui-visual-design.md` §4。

---

## 6. 测试策略

| 层 | 工具 | 覆盖 |
|---|---|---|
| Python core | pytest (已有 564+ 测试) | 业务逻辑不变, 全部应绿 |
| IPC 协议 | pytest, mock stdio | `ipc_server.py` 请求/响应/事件 |
| TS 组件 | `ink-testing-library` | 快照测试 + 交互测试 |
| 端到端 | tmux 子进程 | 真实终端中跑 `node dist/mmi-tui.js`, 验证 OSC/SIGWINCH |
| 视觉回归 | 字符快照 diff | 关键屏的字符输出 |

CI 矩阵增加 `node 18 / 20 / 22`。

---

## 7. 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| Windows 兼容 (Conhost 不支持 ANSI) | 中 | 文档明确支持 Windows Terminal / macOS / Linux; Conhost 不支持 |
| 用户未装 Node 18+ | 中 | 启动时检测, 提示安装命令, 不强制 (降级提示用纯 CLI) |
| stdio 死锁 (Python 缓冲) | 高 | Python 端强制 `line_buffering=True` |
| Unicode 双宽字符宽度 | 中 | 用 `string-width` (~3KB), Reasonix 同款 |
| 大消息滚动性能 (10000 字符) | 中 | `<Static>` 切分历史, 流式缓冲独立 |
| Ink 5.x 快速迭代 | 低 | 锁版本 `ink@^5.0.0`, 6 个月内不升大版本 |
| 打包体积 3MB | 低 | 单文件 ESM, 一次性下载, 接受 |
| `mmi core` IPC 协议破坏性变更 | 中 | 协议版本字段 `protocol_version`, 启动时校验 |

---

## 8. 实施分期

具体任务拆分在 writing-plans 阶段产出, 时间盒标注:

- **M1 (脚手架)**: tsconfig / tsup / package.json + 空白 `<App>` 跑通 + stdio IPC hello world
- **M2 (SessionHub)**: 居中布局 + 列表 + fuzzy 搜索 + 4 快捷键
- **M3 (Chat 骨架)**: HeaderBar / Input / StatusBar 三段式 + Enter 发送
- **M4 (流式渲染)**: IPC token event + ChatLog 实时追加
- **M5 (内容渲染)**: Markdown / 代码块 / 引用
- **M6 (视觉细节)**: 主题 / 分割线 / 折叠块 收敛到 design doc
- **M7 (集成测试)**: 打包 + cli 集成 + 端到端验证

---

## 9. 验收标准

完成时必须满足:

- [ ] `mmi tui` 在 macOS / Linux / Windows Terminal 中启动正常
- [ ] SessionHub 屏: 居中布局, 4 快捷键 (n / / / q) 全部生效
- [ ] Chat 屏: 三段式布局, Enter 发送, Shift+Enter 换行
- [ ] LLM 流式输出逐字追加, 无闪烁
- [ ] 终端 resize 重新布局, 无错位
- [ ] 暗/亮色变体自动适配
- [ ] 背景透明 (终端底色直接透出, 不被涂色)
- [ ] Python `core/` 测试 100% 仍绿
- [ ] tui-ts 组件 + IPC 测试覆盖关键路径
- [ ] 视觉快照与 `docs/design/tui-visual-design.md` 一致

---

## 10. 不做 (Out of Scope)

- 鼠标交互 (TUI 不支持, 不做)
- 图片/图形渲染 (终端限制, 后续可考虑 Sixel/Kitty 协议但本期不做)
- 多 TUI 实例 (单进程单实例, 锁文件禁止)
- TUI 插件系统 (YAGNI)
- 国际化 (TUI 文案跟随 `mmi.core.i18n.t()`, 不单独做 TUI 翻译)
