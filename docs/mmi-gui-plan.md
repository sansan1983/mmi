# MMI GUI 建设方案

> 基于 Galley (github.com/wangjc683/galley) 源码改造  
> 日期：2026-06-05  
> 协议：MIT（Galley 原生协议）

---

## 一、背景

MMI 目前有：
- `mmi/core/` — 记忆引擎层（session/storage/llm/search/heat/GC/…），**基本成熟**
- `mmi/agent/` — Agent 调度层（四期推进中），GUI **不依赖**
- `mmi/tui/` — Textual 终端 UI（技术用户使用）
- **缺少**普通用户可用的桌面 GUI

目标：为 MMI 添加原生桌面 GUI，让小白用户也能方便使用。

---

## 二、为什么选 Galley 改造而非从零建

| 方案 | 估时 | 优点 | 缺点 |
|---|---|---|---|
| 🅰 从零建 | 13-19天 | 完全可控 | 工程量大 |
| 🅱 **改 Galley** | **4-6天** | UI 现成、少写大量代码 | 需适配 mmi 数据模型 |
| 🅲 改 Galley + 不做 Rust | **3-4天** | 最快出活 | Tauri 只做壳 |

**结论：改 Galley 是最快路线。** Galley 是 MIT 协议，可以自由 fork。

---

## 三、Galley 源码可复用度评估

| 层 | 位置 | 可复用度 | 策略 |
|---|---|---|---|
| React 前端组件 | `gui/src/components/` | ~80% ✅ | 布局/气泡/折叠块/输入框直接照搬 |
| 状态管理 | `gui/src/stores/` | ~50% ⚡ | state 结构保留，action 从 Tauri IPC 改成 HTTP API |
| 前端类型定义 | `gui/src/types/` | ~60% ⚡ | 需对齐 mmi 数据模型 |
| 工具库 | `gui/src/lib/` | ~30% 🔄 | bridge/ipc-handlers 需重写 |
| **Rust 核心** | **`core/src/`** | **~10% ❌** | **直接用 mmi.api Python 层替代** |
| **Python runner** | **`runner/`** | **~20% ❌** | **不需要了，API 直调 mmi.core** |
| Tauri 配置 | `tauri.conf.json` | ~70% ✅ | 窗口/bundler 配置可复用 |

---

## 四、最终架构

```
┌──────────────────────────────────────────────────┐
│  Tauri Desktop Shell                              │
│  ├─ 窗口管理 / 菜单 / 系统托盘                     │
│  ├─ 管理 Python API 侧车进程（启动/停止/守护）       │
│  └─ 系统集成（深色模式/通知）                       │
├──────────────────────────────────────────────────┤
│  React 19 + TypeScript + Tailwind v4 前端          │
│  ├─ 从 Galley 拿：AppShell/Sidebar/TopBar/         │
│  │  Conversation/Composer/MessageBubble/布局       │
│  ├─ 重写 stores：从 Tauri IPC → fetch('http://…') │
│  └─ Zustand 状态管理                               │
├──────────────────────────────────────────────────┤
│  mmi/api/（新增 Python FastAPI 层）                 │
│  ├─ 薄封装，from mmi.core import SessionManager    │
│  ├─ REST API + WebSocket（流式聊天）               │
│  └─ 不修改 mmi.core 任何代码                       │
├──────────────────────────────────────────────────┤
│  mmi.core（已存在，不变）                            │
│  session / storage / llm / search / config / …    │
└──────────────────────────────────────────────────┘
```

---

## 五、实施步骤

### 第一阶段：Fork Galley + 清理（0.5 天）

1. `git clone https://github.com/wangjc683/galley.git gui/`
2. 删除 `core/`（Rust 核心）、`runner/`（Python runner）、`managed-ga/`（内置 GA）、`cli/`（CLI）
3. 删除 `gui/src/lib/ipc-handlers.ts`、`gui/src/lib/bridge.ts` 等 Tauri IPC 相关代码
4. 清理 `tauri.conf.json`，去掉 Galley 专属配置
5. 清理 `Cargo.toml`、`package.json` 中不需要的依赖

### 第二阶段：新增 mmi/api/ Python 层（1-2 天）

1. 创建 `mmi/api/__init__.py`
2. 创建 `mmi/api/server.py` — FastAPI app
3. 创建 `mmi/api/models.py` — Pydantic 请求/响应模型
4. 创建路由模块：
   - `routes_sessions.py` — 会话 CRUD
   - `routes_chat.py` — 对话 + WebSocket 流式
   - `routes_search.py` — 搜索
   - `routes_config.py` — LLM 配置
5. 添加 `pyproject.toml` 可选依赖 `[gui]` (fastapi, uvicorn, pydantic)

#### API 端点设计

```
会话管理:
  GET    /api/sessions                   # 列表（?limit=&state=）
  POST   /api/sessions                   # 新建
  GET    /api/sessions/{id}              # 详情
  DELETE /api/sessions/{id}              # 删除
  PATCH  /api/sessions/{id}/title        # 改标题
  POST   /api/sessions/{id}/archive      # 归档

对话:
  POST   /api/sessions/{id}/chat         # 发送消息
  WS     /api/sessions/{id}/chat/stream  # 流式对话

搜索:
  GET    /api/search?q=&limit=           # 全文搜索

配置:
  GET    /api/config                     # 读配置
  PUT    /api/config                     # 写配置
  GET    /api/config/llm                 # LLM 配置
  PUT    /api/config/llm                 # 更新 LLM 配置
  POST   /api/config/llm/test            # 测试 LLM 连接
```

### 第三阶段：改造前端 stores 层（1 天）

将 Galley 的 Zustand stores 从 Tauri IPC 调用改为 HTTP API 调用：

| 文件 | 改动 |
|---|---|
| `stores/sessions.ts` | `invoke('create_session')` → `fetch('POST /api/sessions')` |
| `stores/messages.ts` | `invoke('chat')` → `fetch('POST /api/sessions/{id}/chat')` |
| `stores/runtime.ts` | 改为检测 Python API 健康状态 |
| `stores/prefs.ts` | `invoke('get_config')` → `fetch('GET /api/config')` |
| `lib/api.ts`（新建） | 封装所有 HTTP 调用，统一错误处理 |

### 第四阶段：Tauri 侧车配置（0.5 天）

1. 配置 `tauri.conf.json` 的 `bundle.externalBin` 指向 Python 启动脚本
2. 或在 Rust 层用 `Command::new("python3")` 启动 API server
3. 窗口关闭时自动 kill 子进程
4. 开发模式：`pnpm tauri dev` 自动启动 API

### 第五阶段：联调 + 界面微调（1 天）

1. 适配 mmi 数据字段到 Galley 前端组件
2. 调整主题色/字体等品牌设置
3. 全链路测试：前端 → API → mmi.core
4. 修复适配问题

### 第六阶段：打包（1 天，可选）

1. Tauri bundler 配置（.deb / .AppImage / .dmg）
2. 嵌入 Python 运行时（PyInstaller）
3. 应用图标

---

## 六、工作量汇总

| 阶段 | 内容 | 估时 |
|---|---|---|
| 一 | Fork Galley + 清理 | 0.5 天 |
| 二 | 新增 mmi/api/ Python 层 | 1-2 天 |
| 三 | 改造前端 stores | 1 天 |
| 四 | Tauri 侧车配置 | 0.5 天 |
| 五 | 联调 + 界面微调 | 1 天 |
| 六 | 打包（可选） | 1 天 |
| **合计** | | **4-6 天** |

---

## 七、注意事项

1. **API 层是解耦关键** — `mmi/api/` 只依赖 `mmi.core`（已稳定），mmi agent 层怎么改都不影响 GUI
2. **不解耦也可以直接调** — 如果 mmi 变化少，前端可以直接 `subprocess` 调 `mmi.cli`，但推荐 API 层方案
3. **MVP 优先** — 第一阶段只做会话列表 + 聊天 + 搜索，后续再加设置/审批/工具面板
4. **不强制 Rust 重写** — Rust 层只做侧车管理和窗口集成，业务逻辑全部在 Python API 层
5. **前端组件高度复用** — Galley 的对话气泡、折叠块（thinking/tool call）、Markdown 渲染等都可以直接拿

---

## 八、参考

- Galley 源码: https://github.com/wangjc683/galley
- MMI 项目: `/home/ubuntu/mmi/`
- MMI 架构文档: `docs/ARCHITECTURE.md`
