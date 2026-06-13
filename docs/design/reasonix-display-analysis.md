# Reasonix 展示层深度分析报告

> 分析日期：2026-06-05
> 分析版本：reasonix v0.53.2
> 目的：为 MMI TUI 设计提供技术参考

---

## 1. 定位：混合型架构

Reasonix 的展示层是 **CLI 入口 + TUI 核心** 的混合体：

```
reasonix chat         → 全屏交互式 TUI
reasonix <command>    → 一次性 CLI 输出
reasonix --help       → 传统 CLI 帮助
```

TUI 模式是主力交互形式，CLI 一次性模式是补充。

---

## 2. 技术栈全景

| 层级 | 技术 | 说明 |
|---|---|---|
| **语言** | TypeScript (5.x) | 编译为 Node.js ESM |
| **TUI 框架** | **Ink** (v5.x) | React 的终端渲染器 |
| **底层渲染** | `react-reconciler` | React Fiber 架构的自定义渲染器 |
| **布局引擎** | Yoga (Flexbox) | Facebook 的跨平台 Flexbox 实现 |
| **UI 库** | React (18.x) | 组件化、状态管理、Hooks |
| **CLI 解析** | `commander` | 命令注册与参数解析 |
| **构建** | `tsup` | TypeScript → 单文件 bundle |
| **代码高亮** | `cli-highlight` | 多语言语法高亮 |
| **盒子边框** | `cli-boxes` | 单/双线 Unicode 框字符 |

**关键发现**：Ink 和 React 被 `tsup` 直接 **bundle 进产物**（chunk-O7VQOZQR.js = 2.7MB），不依赖外部安装。这意味着整个 TUI 运行时是自包含的。

---

## 3. Ink 的渲染原理

Ink 不是普通的 "打印字符串到终端"——它是一个 **完整的 React 渲染器**。

### 3.1 渲染管线

```
React State 变化
    ↓
React Reconciler (Fiber diff)
    ↓
Ink 计算 DOM 差异
    ↓
Yoga Flexbox 布局计算
    ↓
ANSI 转义码输出 (只刷差异区域)
    ↓
终端显示
```

### 3.2 增量渲染

关键区别：

| 方式 | 行为 |
|---|---|
| `os.system("clear")` + 全量打印 | 整屏闪烁，肉眼可见 |
| Ink 的增量渲染 | 只输出变更的字符位置，**无闪烁** |

Ink 通过维护一个"虚拟终端 DOM"来实现——每次状态变化时，对比新旧 DOM，生成最小的 ANSI 转义序列，只改写变化的部分。这和 React 的虚拟 DOM diff 是同一套思想。

### 3.3 布局：Flexbox (Yoga)

Ink 使用 Facebook 的 **Yoga** 引擎做 Flexbox 布局。所有的定位都是算法驱动的：

```
<Box flexDirection="column" height="100%">
  <Box flexShrink={0}>            ← 顶部信息条，固定高度
    <Text>MMI · deepseek-chat</Text>
  </Box>
  <Box flexGrow={1}>              ← 消息区，填满剩余空间
    ...
  </Box>
  <Box flexShrink={0}>            ← 输入区，固定高度
    <Text>> 输入...</Text>
  </Box>
</Box>
```

**窗口缩放时**：终端发出 `SIGWINCH` → Ink 通过 `useStdout().onResize()` 捕获 → 触发 React re-render → Yoga 重新计算全部位置 → 增量输出。整个过程无闪烁。

---

## 4. 组件架构

### 4.1 基础组件（Ink 内置）

```
<Box>    ← Flexbox 容器（相当于 div）
<Text>   ← 文本（颜色/样式/背景）
<Static> ← 静态内容（不参与增量渲染）
```

`Box` 的属性：

| 属性 | 值示例 | 说明 |
|---|---|---|
| `flexDirection` | `"column"` / `"row"` | 主轴方向 |
| `flexGrow` | `0` / `1` | 拉伸比例 |
| `flexShrink` | `0` / `1` | 收缩比例 |
| `marginY` / `marginX` | `1` | 外边距（字符单位） |
| `paddingY` / `paddingX` | `1` | 内边距（字符单位） |
| `width` / `height` | `"100%"` / `1` | 尺寸 |
| `alignItems` | `"center"` | 交叉轴对齐 |
| `justifyContent` | `"center"` | 主轴对齐 |

`Text` 的属性：

| 属性 | 值示例 | 说明 |
|---|---|---|
| `color` | `"#c0caf5"` / `"blue"` | 前景色 |
| `backgroundColor` | `"#161b22"` | 背景色（不设则透明） |
| `bold` | `true` | 粗体 |
| `dim` | `true` | 暗色 |
| `italic` | `true` | 斜体 |
| `underline` | `true` | 下划线 |
| `wrap` | `"wrap"` / `"truncate"` | 换行策略 |

### 4.2 自定义组件（Reasonix 定义）

按功能分类：

**消息卡片：**

| 组件 | 用途 |
|---|---|
| `Card` | 通用消息卡片容器 |
| `LiveCard` | 流式输出的实时卡片 |
| `StreamingCard` | 流式文字面板 |
| `ToolCard` | 工具调用展示 |
| `ToolCallCard` | 工具调用详情 |
| `MemoryCard` | 记忆检索结果 |
| `DiffCard` | Git diff 展示 |
| `ErrorCard` | 错误信息 |
| `ReasoningCard` | 推理过程 |
| `PlanCard` / `PlanStepList` | 计划步骤列表 |
| `CtxCard` | 上下文展示 |
| `ApprovalCard` | 用户确认面板 |
| `DocAgent` → `SearchCard` | 文档搜索 |

**文本内容：**

| 组件 | 用途 |
|---|---|
| `BodyLines` | 消息正文 |
| `BlockToken` | 文本片段（流式逐片） |
| `CodeBlock` | 代码块 |
| `Markdown` / `MarkdownView` | Markdown 渲染 |
| `ThinkingRow` | 思考链 |
| `Blockquote` | 引用块 |
| `Heading` | 标题 |
| `Paragraph` | 段落 |
| `List` | 列表 |
| `HorizontalRule` | 分隔线 |
| `HighlightedLine` | 高亮行 |
| `Inline` / `InlineToken` | 行内元素 |

**交互与控制：**

| 组件 | 用途 |
|---|---|
| `KeystrokeProvider` | 键盘输入捕获 |
| `InflightProvider` | 请求中状态管理 |
| `ThemeProvider` | 主题上下文 |
| `ChatScrollProvider` | 聊天滚动管理 |
| `TickerProvider` | 定时刷新 |
| `StoreCtx` / `Ctx` | 状态管理 |
| `AgentStoreProvider` | Agent 状态 |
| `ShortcutsHelpModal` | 快捷键帮助弹窗 |
| `AtMentionSuggestions` | @ 提及建议 |

**UI 元素：**

| 组件 | 用途 |
|---|---|
| `Pill` | 标签/徽章（状态、模型名） |
| `Gap` | 间距占位 |
| `Spans` | 文本片段组 |
| `Row` | 单行内容 |
| `HeaderRow` / `FooterRow` | 顶/底部信息行 |
| `StatusRow` | 状态行 |
| `CountdownRow` / `Countdown` | 倒计时 |
| `ModePill` | 思维模式标签 |
| `TabPill` | Tab 切换 |
| `CharBar` | 字符级别的进度条 |
| `ScrollIndicator` | 滚动提示 |
| `ScrollPastHint` | 已滚动提示 |
| `BootSplash` | 启动画面 |
| `ToastRail` | 通知条 |

---

## 5. 交互模式

### 5.1 键盘事件流

```
终端按键
  ↓
KeystrokeProvider 捕获原始按键
  ↓
解析为语义事件 (up / down / enter / ctrl_c / /)
  ↓
React state 更新
  ↓
Ink 增量重渲染
```

### 5.2 快捷键

| 按键 | 行为 |
|---|---|
| `Enter` | 发送消息 / 确认 |
| `↑` / `↓` | 历史导航 / 选择切换 |
| `/` | 触发命令面板 |
| `@` | 触发 Agent 提及 |
| `Ctrl+C` | 退出 / 中断 |
| `Esc` | 取消 / 返回 |
| `Tab` | 补全 / 焦点切换 |

### 5.3 流式输出

```
用户输入 → LLM API 调用
           ↓
      stream_chunk 到达
           ↓
      React setState (增量追加)
           ↓
      Ink diff → 只渲染新增字符
           ↓
      终端实时显示
```

流式输出时，`BlockToken` 组件接收每个 chunk，追加到 `LiveCard` 或 `StreamingCard` 的缓冲区中。Ink 的增量渲染确保只有新增的字符被输出到终端。

---

## 6. 背景与颜色

### 6.1 默认透明

Ink 的 `Text` 组件**不设 `backgroundColor` 就不会画背景色**。终端底色直接透出。只有以下情况才设背景：

- **选中行**：浅底色（如 `#161b22`）
- **高亮文本**：短时背景闪烁
- **Pill 标签**：标签背景色

### 6.2 颜色系统

```typescript
FG = {
  body: "#c0caf5",     // 正文
  faint: "#565f89",    // 次要文字
  meta: "#7aa2f7",     // 元信息
  accent: "#2ac3de",   // 强调
  info: "#7dcfff",     // 信息
  error: "#f7768e",    // 错误
  warning: "#e0af68",  // 警告
  success: "#9ece6a",  // 成功
}

SURFACE = {
  bg: undefined,       // 透明 (不设背景)
  bgElev: "#161b22",   // 选中/高亮底色
}
```

### 6.3 主题切换

通过 `ThemeProvider` 组件实现主题上下文。目前是 Tokyo Night 暗色系 + 亮色终端自适应。

---

## 7. 字体

**不指定字体**——完全跟随终端配置。Ink 的所有尺寸计算基于字符宽度（`wcwidth`），不是像素。这意味着：

- 终端设什么字体 → Reasonix 就用什么字体
- 用户自选等宽/非等宽字体均可
- 中文字符自动按双宽字符处理

---

## 8. 关键架构决策总结

| 决策 | Reasonix 的选择 | 为什么 |
|---|---|---|
| **语言** | TypeScript / Node.js | React 生态、组件化 |
| **渲染框架** | Ink + React | 增量渲染、组件复用、声明式 UI |
| **布局** | Flexbox (Yoga) | 算法居中、窗口缩放自适应 |
| **背景** | 默认透明 | 跟随终端，不出戏 |
| **刷新** | Virtual DOM diff | 无闪烁，性能好 |
| **状态管理** | React Context + useState | 天然继承 React 生态 |
| **键盘输入** | raw mode + KeystrokeProvider | 完整的键盘交互控制 |
| **流式输出** | React 增量 state | 逐字渲染不需要全屏重绘 |

---

## 9. 对 MMI TUI 的启示

### 9.1 方案选择

| 方案 | 语言 | 透明背景 | 增量刷新 | 算法居中 | 流式渲染 |
|---|---|---|---|---|---|
| **Ink + React** | TypeScript | ✅ | ✅ | ✅ | ✅ |
| **Rich + Live** | Python | ✅ | ✅ | ❌ partial | ✅ |
| **Textual** | Python | ❌ | ✅ | ❌ CSS | ✅ |

### 9.2 关键门槛

要实现 Reasonix 级别的 TUI 质量，必须解决：

1. **透明背景** — 框架不能强制涂背景色
2. **增量刷新** — 不能 `clear` 全屏，必须 diff 增量
3. **算法居中** — Flexbox 或等价的算法布局，不能硬编码
4. **虚拟终端 DOM** — 维护一份"期望的"终端状态，只刷差异
5. **窗口 resize** — 监听 `SIGWINCH`，自动重新布局

### 9.3 Ink 核心代码参考

Ink 的核心机制可参考其开源实现：

```
ink/
├── src/
│   ├── render.ts          # 渲染入口（virtual console → real console）
│   ├── reconciler.ts      # react-reconciler 配置
│   ├── dom.ts             # 虚拟 DOM 节点
│   ├── output.ts          # ANSI 输出（只写差异）
│   ├── layout.ts          # Yoga Flexbox 布局
│   ├── instances.ts       # 文本实例管理
│   ├── measure-text.ts    # 字符宽度测量 (wcwidth)
│   └── styles.ts          # 样式→ANSI 转换
```

核心算法：`output.ts` 中计算新旧两帧之间每个单元格的差异，只输出变化的 ANSI 转义码。
