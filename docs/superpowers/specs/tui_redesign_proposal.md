# Atlas TUI 重构设计方案

> **设计原则：不将就 · 不妥协 · 不敷衍**
>
> 本文档基于 Atlas TUI 现状 与 GenericAgent TUI (Textual v2) 的深度对比分析，提出 Atlas TUI 的全面重构方案。

---

## 一、设计背景与目标

### 1.1 三个"不"字承诺

Atlas 的设计初衷是「让 AI 成为你这个行业的专业员工」，而非什么都略懂的万能助手。TUI 作为 Atlas 的核心交互界面，其品质必须与这一承诺相匹配：

| 承诺 | 含义 | 在 TUI 重构中的落地 |
|------|------|---------------------|
| **不将就** | 不因技术限制降低产品标准 | 交互流畅度、视觉设计必须达到专业工具级别 |
| **不妥协** | 不因进度压力牺牲架构质量 | 重构是一次性的深度工程，不是修补式的打补丁 |
| **不敷衍** | 每个细节都要经得起推敲 | 从输入体验到流式输出，从 resize 到主题切换，每个角落都要精细打磨 |

### 1.2 重构目标

**核心目标**：将 Atlas TUI 从「功能性实现」升级为「工业级品质」。

具体指标：
- 输入延迟：< 16ms（60fps 感知阈值），每次按键后下一帧必须呈现
- 流式输出：LLM 输出时 spinner 动画流畅，不因打字而卡顿
- resize 响应：窗口拖拽时无视觉撕裂，最终布局在 100ms 内稳定
- 列表加载：千级会话列表可交互，不因渲染阻塞用户输入
- 内存占用：万级历史消息场景下，remount 时间 < 200ms
- 主题切换：切换主题时完整重绘，< 50ms 无闪烁

### 1.3 设计愿景

> **「Atlas TUI 应该是 Go 生态中，最接近 Textual 体验的自绘 TUI 框架」**

不是简单的"能用"，而是"专业"、"精致"、"流畅"。

---

## 二、现状分析

### 2.1 当前架构

Atlas TUI 的核心代码结构：

```
internal/tui/
├── tui.go          # 1960 行，51KB — 主 TUI 引擎，单文件耦合
├── state.go        # 344 行 — 状态机定义（11 种 Mode）
├── state_test.go   # 7631 行 — 状态机测试（严格覆盖）
├── undo.go         # 2393 行 — Undo/Redo 系统
├── undo_test.go    # 7028 行 — Undo 测试
├── command.go      # — 命令面板（/btw、/session 等）
├── prompt.go       # — Prompt 管理
├── render.go       # — 渲染输出
├── verbose.go      # — 工具输出详情模式
├── askuser.go      # — ask_user 交互
├── audit_dump.go   # — 审计日志
├── signal.go       # — 信号处理
├── clipboard.go # — 剪贴板
└── i18n.go         # — 国际化
```

### 2.2 当前渲染模型

```
┌─────────────────────────────────────────┐
│  Run() 主循环                            │
│  ┌─────────────────────────────────┐   │
│  │ for { │   │
│  │   t.drainStream()               │ ← 非阻塞，channel 消费 │
│  │   key, err := readKey() │ ← 阻塞！核心问题 │
│  │   if consumed { renderLive() }  │ ← 同步渲染，write syscall│
│  │   if idle { editInput(); renderLive() } │
│  │ } │   │
│└─────────────────────────────────┘   │
│ │
│  Spinner goroutine (独立) │
│  ┌─────────────────────────────────┐   │
│  │ for { time.Sleep(1.2s) │   │
│  │   t.renderLive()  ← 争抢主循环   │   │
│  │ }                               │   │
│└─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

**主循环阻塞问题**：当 `readKey()` 等待用户输入时，整个渲染管道都被暂停。spinner goroutine 调用 `renderLive()` 的时机完全依赖于主循环的下一次 tick，无法保证60fps 的动画刷新。

### 2.3 当前布局计算

`layout()` 函数手动计算每个区域的行数：

```go
// 当前 layout() 的问题：
// 1. 每次 renderLiveFull 都重新计算所有区域
// 2. 没有 dirty tracking，无法判断哪些区域需要重绘
// 3. 硬编码的行数计算，脆弱且难以维护
func (t *TUI) layout() Layout {
    inputH := min(max(len(t.inputText), 1), 3) + 2
    // ... 手动计算每个区域的 top/bottom
}
```

### 2.4 渲染全量重绘

`renderLiveFull` 和 `repaintScrollback` 使用全屏清屏：

```go
func (t *TUI) repaintScrollback() {
    fmt.Fprint(os.Stdout, "\x1b[2J\x1b[H") // 全屏清屏 ← 性能杀手
    t.renderBlocks() // 重新渲染所有 blocks
    t.renderLive() // 重绘底部区域
}
```

**问题**：
- 清屏 + 重绘所有区域 = O(n) syscall（n = 可见行数）
- 每次渲染都是"从零开始"，没有任何增量判断
- 流式输出时每收到一个字都调用 `printStreamLine`，高频 syscall

### 2.5 会话列表全量加载

```go
// 当前 openSessionPicker() 的实现：
// 一次性加载所有会话 →数千条记录时 mount 卡顿
for _, s := range t.sessions {
    lines = append(lines, formatSession(s))
}
```

**问题**：没有 lazy loading 机制，所有列表项一次性渲染。

### 2.6 Resize 无防抖

当前 `handleResize`可能在窗口拖拽过程中被连续调用数十次，每次都触发完整重算。

---

## 三、对标分析：GA TUI 的优势

### 3.1 架构层面

|维度 | GA TUI (Textual) | Atlas TUI (自绘) |
|------|-----------------|------------------|
| **框架** | Textual框架（类 React/Elm） | 纯手写 ANSI |
| **渲染模型** | Textual 自动 diff +批量 DOM | 手动全量重绘 |
| **输入模型** | Textual message bus（异步） | `readKey()` 阻塞主循环 |
| **布局系统** | CSS 声明式 | 手写 `layout()` 函数 |
| **列表** | LazyChoiceList懒加载 | 全量加载 |
| **消息缓存** | `_cache_key` + `_cached_body` | 无缓存，每次 remount 全量重渲染 |
| **Resize** | 80ms debounce + no-op guard | 无防抖，直接全量重算 |
| **Scroll保持** | remount 时保持 `scroll_y` | 重置到顶部 |
| **主题系统** | 完整的多主题 +实时预览 | 仅 `tr()` i18n |

### 3.2 GA 的核心设计模式

#### 模式 1：Lazy ChoiceList（懒加载列表）

```python
class LazyChoiceList(ChoiceList):
    def __init__(self, msg, labels, batch=50):
        # 首屏只 mount 前 50 条，立即可交互
        self._load_more(self._lazy_batch)

    def _ensure_window(self):
        # cursor 接近尾部时再加载下一批
        if self.highlighted >= self._lazy_loaded - 5:
            self._load_more(self._lazy_batch)
```

**效果**：千级列表首屏可交互，后续条目按需加载。

#### 模式 2：消息缓存 + 失效机制

```python
# 缓存键：会话 ID + 角色 + 内容哈希 + 折叠状态
m._cache_key = (sess.id, m.role, hash(m.content), frozenset(m._toggled_folds))
if m._cache_key != m._cached_key or m._force_refresh:
    # 重新渲染
```

**效果**：大部分消息不需要重新渲染，只需 diff 后更新变化的 widgets。

#### 模式 3：Resize Debounce + No-op Guard

```python
def on_resize(self, event):
    if size == self._last_size: return  # 短路重复 resize
    self._resize_timer = self.set_timer(0.08, self._flush_resize)

def _resize_input(self, inp):
    target = min(max(lines, 1), 3) + 2
    if target == self._last_input_height: return  # no-op guard
    self._last_input_height = target
    inp.styles.height = target
```

**效果**：窗口拖拽时只触发一次完整重算，输入高度不变时跳过硬计算。

#### 模式 4：滚动位置保护

```python
was_at_bottom = container.scroll_y + container.size.height >= container.virtual_size.height - 2
# ... remount ...
if was_at_bottom:
    container.scroll_end(animate=False)  # 流式时自动滚到底
else:
    container.scroll_to(y=prev_scroll_y, animate=False)  # 保持阅读位置
```

**效果**：用户翻看历史消息时，remount 不会打断阅读。

#### 模式 5：主题系统双向同步

```python
def watch_theme(self, old_theme, new_theme):
    # CSS 变量 → Python 全局常量 → 缓存的 Rich Text 全部失效
    for m in sess.messages:
        m._cache_key = None
        m._cached_body = None
        m._seg_render_cache.clear()
    self._remount_current_session()
```

**效果**：主题切换时完整更新，无残留旧颜色。

---

## 四、核心问题汇总

### 4.1 问题清单

| # | 问题 | 影响 | 优先级 |
|---|------|------|--------|
| P1 | 主循环阻塞导致渲染与输入争抢 | spinner 动画卡顿，流式输出时无法响应按键 | ⭐⭐⭐⭐⭐ |
| P2 | 全量重绘，无 dirty tracking | 每次渲染都清屏 + 重画所有区域，高频 syscall | ⭐⭐⭐⭐⭐ |
| P3 | 流式渲染无节流 | LLM 快速输出时每字一次 write syscall | ⭐⭐⭐⭐ |
| P4 | Resize 无防抖 | 窗口拖拽时大量重复全量重算 | ⭐⭐⭐ |
| P5 | 会话列表全量加载 | 千级列表时 mount 阻塞主线程 | ⭐⭐⭐ |
| P6 | 消息无缓存机制 | remount 时所有消息重新渲染 | ⭐⭐⭐ |
| P7 | Scroll 位置不保持 | 交互后重置到顶部，打断阅读 | ⭐⭐ |
| P8 | 输入高度重算无 guard | 每次按键都触发 layout reflow | ⭐⭐ |
| P9 | 单文件耦合严重 | 51KB 单文件，所有逻辑纠缠，难以维护 | ⭐⭐ |

### 4.2 问题因果链

```
P1 (主循环阻塞)
  └─→ spinner 动画卡顿
  └─→ 流式输出时用户无法编辑输入框
  └─→ 输入延迟感知明显

P2 (全量重绘)
  └─→ 高频 write syscall (LLM 每字一次)
  └─→ 长对话滚动卡顿
  └─→ resize 闪烁

P4 (Resize 无防抖)
  └─→窗口拖拽时视觉撕裂
  └─→ CPU 占用飙升

P9 (单文件耦合)
  └─→ 难以单独测试各模块
  └─→ 新增功能只能往末尾追加
  └─→ 代码腐化加速
```

---

## 五、设计方案

### 5.1 架构选择：自研还是引入框架？

| 选项 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| **A. 继续自绘，引入架构模式** | 在现有 ANSI 渲染基础上，借鉴 Textual 的设计模式，深度组件化 | 零依赖，完全控制每字节输出，符合 Atlas 极简哲学 | 工作量大，需要自己实现 diff 算法 |
| **B. 引入 bubbletea** | Go 生态最成熟的 TUI 框架（Elm Architecture） | 输入/渲染/事件框架完备，社区活跃 | 不是 CSS-based，声明式 view 灵活性受限 |
| **C. 引入 tview** | 基于 tui.go 的组件库 | 兼容当前部分实现，有列表/表格/弹窗 | 同样是手写布局，不如 Textual 的 CSS 直观 |

**推荐：选项 A — 自研架构 + Textual 设计模式**

理由：
1. Atlas 的设计初衷是「极简依赖」（golang.org/x/term + sys），引入第三方框架与核心哲学冲突
2. GA 的 Textual 设计模式可以完整借鉴，不需要引入 Python 框架的重量
3. 自研渲染引擎可以针对 Atlas 的具体场景（流式输出、Block 历史、Tool 调用）做极致优化
4. 架构重构是一次性的深度工程，「不将就、不妥协、不敷衍」要求我们做彻底，而不是引入一个"差不多"的框架然后继续妥协

### 5.2 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        TUI Layer │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐  │
│  │  InputArea  │ │  MessageList│ │  Header/ │ │  Picker │  │
│  │ │ │             │ │  Topbar │ │  (Modal)  │  │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └─────┬─────┘  │
│         │               │               │               │        │
│  ┌──────▼───────────────▼───────────────▼───────────────▼─────┐  │
│  │                    Layout Engine                          │  │
│  │  Declarative Layout DSL → Physical Position Calculator │  │
│  │  - grid: rows × cols, span, fraction │  │
│  │  - flex: direction, justify, align                       │  │
│  │  - auto: fit content, max-height │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │                    Render Pipeline │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │  │
│  │  │ Cache Layer │→│ Dirty Diff  │→│ Batch Writer │    │  │
│  │  └─────────────┘  └─────────────┘  └─────────────────┘    │  │
│  │  - _cache_key   - 只重绘变化区域  - bytes.Buffer 合并写 │  │
│  │  - _dirty_set  - 行级/区域级 diff - write syscall 减少 │  │
│  └──────────────────────────┬───────────────────────────────┘  │
│                             │                                   │
│  ┌──────────────────────────▼───────────────────────────────┐  │
│  │                    Event Bus                             │  │
│  │ ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐    │  │
│  │  │ RenderLoop │  │ InputLoop   │  │ StreamLoop     │    │  │
│  │  │ (16ms tick)│  │ (blocking) │  │ (async drain)  │    │  │
│  │  └─────────────┘  └─────────────┘└─────────────────┘    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Infrastructure Layer                                          │
│  term (golang.org/x/term) ← raw mode, resize, clipboard │
└─────────────────────────────────────────────────────────────────┘
```

### 5.3 模块划分

```
internal/tui/
├── engine/ # 【新增】渲染引擎核心
│   ├── engine.go # Engine 主入口，事件循环
│   ├── cache.go              # 消息缓存层（cache_key → cached_body）
│   ├── diff.go              # Dirty diff 算法
│   ├── writer.go           # Batch writer，合并 write syscall
│   └── buffer.go           # ANSI 转义序列构建器
│
├── layout/ # 【新增】声明式布局引擎
│   ├── layout.go            # Layout DSL 定义
│   ├── grid.go             # Grid 布局算法
│   ├── flex.go             # Flex 布局算法
│   ├── measure.go          # 尺寸测量（auto-fit）
│   └── measure_cache.go    # 尺寸测量缓存（no-op guard）
│
├── component/               # 【重构自 tui.go】UI 组件
│   ├── component.go         # Component 接口定义
│   ├── topbar.go            # 顶部状态栏
│   ├── input_area.go       # 输入区域（undo/redo + 编辑）
│   ├── message_list.go     # 消息列表（懒加载）
│   ├── block.go # Block 历史（折叠/展开）
│   ├── spinner.go          # Spinner 动画
│   ├── stream_output.go    # 流式输出
│   ├── palette.go # 命令面板
│   ├── picker.go           # 选择器基类（Session/Export/Theme）
│   ├── modal.go # 模态对话框基类
│   ├── confirm.go          # 确认对话框
│   ├── scrollbar.go        # 滚动条
│   └── status_bar.go       # 底部状态栏
│
├── state/                   # 【重构自 state.go】状态机
│   ├── machine.go          # 状态机核心
│   ├── modes.go            # Mode 定义
│   ├── transitions.go      # 状态转换
│   └── transitions_test.go
│
├── i18n/                    # 【重构自 i18n.go】国际化
│   ├── i18n.go             # tr() 核心
│   ├── locale/ # 语言资源
│   │   ├── en.toml
│   │   └── zh.toml
│   └── locale_test.go
│
├── theme/                   # 【新增】主题系统
│   ├── theme.go            # Theme 定义
│   ├── palette.go          # Palette（GA 的 ga-default/nord/gruvbox）
│   ├── css_var.go          # CSS 变量解析
│   └── watcher.go          # 主题切换时的全局同步
│
├── storage/                 # 【新增】会话持久化
│   └── session_cache.go    # 会话列表缓存（懒加载）
│
├── tui.go                   # 【保留】主入口，组装各模块
├── tui_test.go
├── main_test.go
├── main_integration_test.go
└── README.md
```

**模块拆分原则**：
- 每个模块 ≤ 300 行
- 模块间通过接口通信，禁止直接引用其他模块的内部状态
- 独立测试文件覆盖每个模块

### 5.4 渲染管道（核心创新）

这是「不将就」的核心：自研一套接近 Textual 体验的增量渲染引擎。

```
┌──────────────────────────────────────────────────────────────────┐
│ Render Pipeline                              │
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐    ┌──────────────┐        │
│  │  Cache Layer │ → │  Dirty Diff  │ →  │ Batch Write │        │
│  └──────────────┘    └──────────────┘    └──────────────┘        │
│                                                                  │
│  1. Cache Layer                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ 每个 Component 持有一个 _cache_key                          │ │
│  │ type CacheKey struct {                                      │ │
│  │     version int       // 主题版本，每次 theme切换 +1 │ │
│  │     content   string // 内容哈希                        │ │
│  │     width int       // 可见宽度（影响 truncation）      │ │
│  │     foldState *FoldState // 折叠状态哈希 │ │
│  │ }                                                          │ │
│  │                                                            │ │
│  │ func (c *Component) Render(ctx *RenderCtx) string { │ │
│  │     key := CacheKey{...}                                    │ │
│  │     if key == c._cached_key { │ │
│  │         return c._cached_output │ │
│  │     } │ │
│  │     c._cached_output = c.doRender(ctx)                     │ │
│  │     c._cached_key = key │ │
│  │     return c._cached_output                                │ │
│  │ }                                                          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  2. Dirty Diff                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ // 区域级 diff：只重绘变化的区域                            │ │
│  │ type DirtySet map[RegionID]struct{} │ │
│  │                                                             │ │
│  │ func (e *Engine) MarkDirty(id RegionID) { │ │
│  │     e._dirty.Add(id)                                       │ │
│  │ } │ │
│  │                                                             │ │
│  │ func (e *Engine) Diff() *DirtySet {                        │ │
│  │     // 分析哪些区域需要重绘                                  │ │
│  │     // 1. 事件触发的区域（立即标记 dirty）                   │ │
│  │     // 2. 受影响的父区域（向上传播）                         │ │
│  │     // 3. 依赖该区域的子区域（向下传播）                     │ │
│  │ }                                                          │ │
│  │                                                             │ │
│  │ // 行级 diff：流式输出时的细粒度优化 │ │
│  │ func (e *Engine) DiffStreamLine(old, new string) []int {   │ │
│  │     // 返回需要重绘的行号列表 │ │
│  │     // LCS 算法找最长公共子序列                              │ │
│  │     // 变化部分标记 dirty │ │
│  │ }                                                          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  3. Batch Writer │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ // 合并多次 fmt.Fprint 为一次 syscall │ │
│  │ type BatchWriter struct {                                  │ │
│  │     buf bytes.Buffer                                      │ │
│  │ } │ │
│  │                                                             │ │
│  │ func (w *BatchWriter) Write(s string) {                   │ │
│  │     w.buf.WriteString(s)                                  │ │
│  │ }                                                         │ │
│  │                                                             │ │
│  │ func (w *BatchWriter) Flush(wr io.Writer) error {          │ │
│  │     _, err := wr.Write(w.buf.Bytes())                      │ │
│  │     w.buf.Reset()                                          │ │
│  │     return err                                             │ │
│  │ }                                                         │ │
│  │                                                             │ │
│  │ // 在 Engine.Render() 中使用                                │ │
│  │ func (e *Engine) Render(w io.Writer) {                   │ │
│  │     bw := &BatchWriter{} │ │
│  │     for id := range e.Diff().Sorted() {                   │ │
│  │         comp := e.component(id)                           │ │
│  │         bw.Write(comp.Render(e.ctx))                      │ │
│  │     }                                                      │ │
│  │     bw.Flush(w) │ │
│  │ }                                                          │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 5.5 事件循环（解决 P1）

```
┌──────────────────────────────────────────────────────────────────┐
│ Event Loop Architecture │
│                                                                  │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐            │
│  │ InputLoop  │    │ RenderLoop │    │ StreamLoop │            │
│  │ (goroutine)│ │ (goroutine) │    │ (goroutine) │            │
│  └─────┬──────┘    └─────┬──────┘    └─────┬──────┘            │
│        │                 │                 │                    │
│        ▼                 ▼                 ▼                    │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Event Bus                             │  │
│  │  - 非阻塞 channel，环形缓冲区 │  │
│  │  - 三种事件类型：Input / Render / Stream                  │  │
│  │  - 每个事件携带 priority（高优先级打断低优先级）           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  Render Pipeline │  │
│  │  Cache → Diff → Batch → Write                             │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  InputLoop: │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ for {                                                    │  │
│  │     key := t.readKey()  // 阻塞读取 │  │
│  │     evt := Event{Type: EventInput, Key: key} │  │
│  │     select { │  │
│  │     case t.evCh <- evt:                                  │  │
│  │     default:                                             │  │
│  │         // channel 满，丢弃低优先级事件 │  │
│  │         t.evCh <- evt  // 强制发送 │  │
│  │     } │  │
│  │ }                                                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  RenderLoop:                                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ ticker := time.NewTicker(16 * time.Millisecond) // 60fps   │  │
│  │ for {                                                    │  │
│  │     select {                                            │  │
│  │     case <-ticker.C:                                     │  │
│  │         t.evCh <- Event{Type: EventTick}                │  │
│  │     case evt := <-t.evCh: │  │
│  │         t.processEvent(evt)                             │  │
│  │     }                                                    │  │
│  │ }                                                        │  │
│  │ ticker.Stop()                                            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  StreamLoop:                                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ for {                                                    │  │
│  │     select {                                            │  │
│  │     case ev := <-t.streamCh:                             │  │
│  │         t.handleStreamEvent(ev)                          │  │
│  │         // 流式节流：16ms 内合并多次事件                   │  │
│  │         t.evCh <- Event{Type: EventRender}              │  │
│  │     case <-t.throttle.C:                                 │  │
│  │         //16ms 定时器到期，必须渲染 │  │
│  │         t.evCh <- Event{Type: EventRender}              │  │
│  │     }                                                    │  │
│  │ }                                                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**解决 P1 的核心原理**：
- 主循环不再是唯一的渲染触发者
- `readKey()` 阻塞时，RenderLoop继续以 60fps 运行，spinner 动画不受影响
- InputLoop 和 StreamLoop 通过 event channel 与 RenderLoop 通信，完全异步

### 5.6 声明式布局引擎

```
┌──────────────────────────────────────────────────────────────────┐
│                     Declarative Layout DSL                       │
│                                                                  │
│  设计目标：让布局定义像 CSS 一样声明式，测量计算自动化 │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ // 示例：Atlas 主界面布局                                   │  │
│  │                                                             │  │
│  │ type LayoutSpec struct {                                   │  │
│  │     Rows []RowSpec │  │
│  │     Columns []ColSpec                                      │  │
│  │ } │  │
│  │                                                             │  │
│  │ type RowSpec struct {                                      │  │
│  │     Height Length // px / fr / auto / min / max     │  │
│  │     Content Component │  │
│  │ }                                                         │  │
│  │                                                             │  │
│  │ // Length 类型支持：                                        │  │
│  │ // Fixed(10)        → 固定 10 行                          │  │
│  │ //   Fraction(1, 3)  → 3 等分中的 1 份（flex-grow）         │  │
│  │ //   Auto            → 自适应内容高度 │  │
│  │ //   Min(3, Auto)    → 最少 3 行，最多自适应 │  │
│  │ //   Max(20, Auto)   → 最多 20 行                          │  │
│  │                                                             │  │
│  │ func (t *TUI) ComputeLayout(termW, termH int) *PhysicalLayout { │
│  │     //1. 第一次遍历：计算所有 Fixed 和 Fraction │  │
│  │     // 2. 第二次遍历：计算 Auto（自适应内容）               │  │
│  │     // 3. 缓存测量结果，no-op guard                         │  │
│  │ }                                                          │  │
│  │                                                             │  │
│  │ func (t *TUI) Render() string {                           │  │
│  │     layout := t.ComputeLayout(t.termW, t.termH)           │  │
│  │     var buf bytes.Buffer                                  │  │
│  │     for i, row := range layout.Rows {                     │  │
│  │         cursorTo(row.Top, 1) │  │
│  │         fmt.Fprint(&buf, "\x1b[K")  // 清除行 │  │
│  │         buf.WriteString(row.Content.Render(ctx))           │  │
│  │     }                                                      │  │
│  │     return buf.String()                                   │  │
│  │ }                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  布局算法：                                                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ func ComputeLayout(spec LayoutSpec, termW, termH int) *Physical { │
│  │     // Step 1: 收集所有 Fixed 行高度 │  │
│  │     fixedTotal := 0                                       │  │
│  │     for _, row := range spec.Rows {                       │  │
│  │         if f, ok := row.Height.(Fixed); ok {             │  │
│  │             fixedTotal += f.Pixels │  │
│  │         } │  │
│  │     }                                                      │  │
│  │                                                             │  │
│  │     // Step 2: 计算剩余空间 │  │
│  │     remaining := termH - fixedTotal                        │  │
│  │                                                             │  │
│  │     // Step 3: 处理 Fraction（按比例分配）                 │  │
│  │     // Step 4: 处理 Auto（测量内容，取 min/max 约束）        │  │
│  │     // Step 5: 应用 min/max 约束                           │  │
│  │     // Step 6: 缓存测量结果                                 │  │
│  │ }                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.7 懒加载消息列表

```
┌──────────────────────────────────────────────────────────────────┐
│                    Lazy Message List                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ type MessageList struct {                                  │  │
│  │     messages []Message // 全部消息（可能数千条）          │  │
│  │     visible []Message   // 当前可见消息（按需加载）        │  │
│  │     scrollY    int        // 当前滚动位置                    │  │
│  │     batchSize  int = 50   // 每次加载的批次大小 │  │
│  │     loadedUp   int = 0    // 已加载的消息数量（从顶部）      │  │
│  │     loadedDown int = 0    // 已加载的消息数量（从底部）      │  │
│  │ }                                                         │  │
│  │                                                             │  │
│  │ func (ml *MessageList) LoadMore(direction Direction) bool { │  │
│  │     switch direction {                                     │  │
│  │     case Down:                                             │  │
│  │         if ml.loadedDown >= len(ml.messages) {            │  │
│  │             return false                                   │  │
│  │         } │  │
│  │         end := min(ml.loadedDown+ml.batchSize, len(ml.messages)) │
│  │         ml.visible = append(ml.visible, ml.messages[ml.loadedDown:end]...) │
│  │         ml.loadedDown = end                               │  │
│  │     case Up:                                               │  │
│  │         if ml.loadedUp <= 0 { │  │
│  │             return false                                   │  │
│  │         }                                                  │  │
│  │         start := max(0, ml.loadedUp-ml.batchSize)          │  │
│  │         ml.visible = append(ml.messages[start:ml.loadedUp], ml.visible...) │
│  │         ml.loadedUp = start                               │  │
│  │     }                                                      │  │
│  │     return true                                            │  │
│  │ }                                                          │  │
│  │                                                             │  │
│  │ func (ml *MessageList) OnScroll(scrollY int) { │  │
│  │     ml.scrollY = scrollY                                  │  │
│  │     // 当 cursor 接近已加载区域的边界时，触发下一批加载       │  │
│  │     if scrollY < ml.loadedUp + 5 {                        │  │
│  │         ml.LoadMore(Up)                                   │  │
│  │     } │  │
│  │     if scrollY > ml.loadedDown - 5 {                      │  │
│  │         ml.LoadMore(Down)                                  │  │
│  │     }                                                      │  │
│  │ }                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  与 GA LazyChoiceList 的对比：                                    │
│                                                                  │
│  │ GA (Python/Textual)     │ Atlas (Go/自绘)                   │  │
│  │─────────────────────────│───────────────────────────────────│  │
│  │ ChoiceList widget │ MessageList component │  │
│  │ OptionList组件        │ []Message slice + visible window │  │
│  │ add_options() 追加 │ LoadMore() 追加到 visible │  │
│  │ highlighted跟踪 cursor │ scrollY 跟踪滚动位置               │  │
│  │ _ensure_window()       │ OnScroll() 触发加载 │  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.8 Resize 防抖 + No-op Guard

```
┌──────────────────────────────────────────────────────────────────┐
│                  Resize Debounce + No-op Guard                    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ type ResizeState struct {                                 │  │
│  │     lastSize       (int, int)                            │  │
│  │     debounceTimer  *time.Timer │  │
││  │     debounceTimer  *time.Timer                           │  │
│  │     lastInputH int                                   │  │
│  │ } │  │
│  │                                                               │  │
│  │ func (t *TUI) handleResize(w, h int) {                    │  │
│  │     // No.1: 重复 resize 短路                             │  │
│  │     if t.resize.lastSize == (w, h) {                      │  │
│  │         return                                             │  │
│  │     } │  │
│  │     t.resize.lastSize = (w, h)                            │  │
│  │                                                               │  │
│  │     // No.2: Debounce，80ms 内只触发一次完整重算              │  │
│  │     if t.resize.debounceTimer != nil {                    │  │
│  │         t.resize.debounceTimer.Stop()                     │  │
│  │     }                                                       │  │
│  │     t.resize.debounceTimer = time.AfterFunc(80*time.Millisecond, func() { │
│  │         t.doFullResize(w, h)                              │  │
│  │     })                                                       │  │
│  │ } │  │
│  │                                                               │  │
│  │ func (t *TUI) doFullResize(w, h int) {                    │  │
│  │     t.termW, t.termH = w, h                              │  │
│  │     t.layout = t.ComputeLayout(w, h)                      │  │
│  │     t.markAllDirty()                                       │  │
│  │     t.evCh <- Event{Type: EventRender}                    │  │
│  │ }                                                            │  │
│  │                                                               │  │
│  │ func (t *TUI) resizeInput(inp InputArea) {                │  │
│  │     target := min(max(inp.lineCount, 1), 3) + 2           │  │
│  │     // No.3: No-op guard，高度没变化就不触发 reflow           │  │
│  │     if target == t.resize.lastInputH {                    │  │
│  │         return                                             │  │
│  │     }                                                       │  │
│  │     t.resize.lastInputH = target │  │
│  │     // 更新输入框高度，更新 layout，重新渲染 │  │
│  │ }                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

**对比 GA 的实现**：

| 机制 | GA (Python/Textual) | Atlas (Go/自绘) |
|------|---------------------|----------------|
| 重复短路 | `if size == self._last_size: return` | `if t.resize.lastSize == (w, h)` |
| Debounce | `self.set_timer(0.08, self._flush_resize)` | `time.AfterFunc(80*time.Millisecond, ...)` |
| No-op guard | `if target == self._last_input_height: return` | `if target == t.resize.lastInputH` |

### 5.9 滚动位置保护

```
┌──────────────────────────────────────────────────────────────────┐
│                   Scroll Position Preservation                  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ func (t *TUI) remountMessages() {                        │  │
│  │     // Step 1: 记录 scroll 位置                          │  │
│  │     container := t.queryOne("#messages")                 │  │
│  │     atBottom := container.scrollY + container.height │  │
│  │                >= container.maxScrollY - 2 │  │
│  │     prevScrollY := container.scrollY                     │  │
│  │                                                             │  │
│  │     // Step 2: remount messages │  │
│  │     container.removeChildren()                            │  │
│  │     for _, m := range t.current.messages {               │  │
│  │         m._widget = nil  // 强制重新渲染                   │  │
│  │         t.mountMessage(container, m)                     │  │
│  │     } │  │
│  │                                                             │  │
│  │     // Step 3: 恢复 scroll 位置 │  │
│  │     if atBottom { │  │
│  │         container.scrollEnd(animate=false)                 │  │
│  │     } else {                                              │  │
│  │         container.scrollTo(y=prevScrollY, animate=false) │  │
│  │     } │  │
│  │ }                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  三种 scroll 策略：                                               │
│  - atBottom=true：流式输出时自动滚到底，用户在看最新内容            │
│  - atBottom=false：用户在翻历史，remount 后保持原位 │
│  - 2行容差：避免滚动到精确像素位置导致的抖动 │
└──────────────────────────────────────────────────────────────────┘
```

### 5.10 主题系统

```
┌──────────────────────────────────────────────────────────────────┐
│ Theme System                                │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ //主题定义（GA 的 ga-default / nord / gruvbox） │  │
│  │ type Theme struct {                                       │  │
│  │     Name string │  │
│  │     Palette Palette │  │
│  │ } │  │
│  │                                                             │  │
│  │ type Palette struct {                                      │  │
│  │     BG string // #1e1e2e │  │
│  │     FG       string // #cdd6f4                             │  │
│  │     Dim      string // #6c7086                             │  │
│  │     Green string // #a6e3a1                             │  │
│  │     Blue     string // #89b4fa                             │  │
│  │     Purple   string // #cba6f7                             │  │
│  │     ChipName string                                       │  │
│  │     ChipModel string                                       │  │
│  │     SelBG string // selection background │  │
│  │     Border string                                       │  │
│  │ }                                                         │  │
│  │                                                             │  │
│  │ var THEMES = map[string]Theme{ │  │
│  │     "atlas-default": { Name: "atlas-default", Palette: gaDarkPalette }, │
│  │     "atlas-light":  { Name: "atlas-light", Palette: gaLightPalette }, │
│  │     "nord":         { Name: "nord",         Palette: nordPalette },   │
│  │ } │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  主题切换时的全局同步： │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ func (t *TUI) switchTheme(name string) {                   │  │
│  │     old := t.theme │  │
│  │     t.theme = THEMES[name]                                 │  │
│  │     t.themeVersion++ // 版本号递增，cache全部失效          │  │
│  │                                                             │  │
│  │     // 通知所有组件：缓存失效                               │  │
│  │     for _, comp := range t.components { │  │
│  │         comp._cached_key = nil │  │
│  │         comp._cached_output = "" │  │
│  │     } │  │
│  │                                                             │  │
│  │     // 局部 remount                                        │  │
│  │     t._remountCurrentSession()                             │  │
│  │     t._refreshTopbar()                                     │  │
│  │     t._refreshBottombar()                                   │  │
│  │ }                                                          │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.11 输入区域增强

```
┌──────────────────────────────────────────────────────────────────┐
│ Input Area Improvements │
│                                                                  │
│  当前问题：                                                        │
│  1. Ctrl+Z/Y Undo/Redo 未与 render同步                            │
│  2. 输入高度变化时没有 no-op guard                                 │
│  3. 没有自动完成（command palette）的基础设施 │
│                                                                  │
│  改进方案：                                                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ type InputArea struct {                                   │  │
│  │     text         []rune │  │
│  │     cursor      int │  │
│  │     history [][]rune          // 命令历史 │  │
│  │     historyIdx  int                                       │  │
│  │     undoStack *undo.Stack[[]rune]                      │  │
│  │     redoStack   *undo.Stack[[]rune]                      │  │
│  │     lastHeight int                                       │  │
│  │     paletteActive bool                                   │  │
│  │ }                                                         │  │
│  │                                                             │  │
│  │ func (ia *InputArea) handleKey(key KeyEvent) bool { │  │
│  │     // 每个按键都触发 undo snapshot │  │
│  │     ia.undoStack.Push(copyRunes(ia.text))                │  │
│  │     ia.redoStack.Clear()                                  │  │
│  │     // ... edit operations ... │  │
│  │     ia.markDirty()                                       │  │
│  │     return true │  │
│  │ }                                                        │  │
│  │                                                             │  │
│  │ func (ia *InputArea) undo() {                             │  │
│  │     if ia.undoStack.Empty() { return } │  │
│  │     ia.redoStack.Push(copyRunes(ia.text))                │  │
│  │     ia.text = ia.undoStack.Pop()                         │  │
│  │     ia.cursor = min(ia.cursor, len(ia.text))             │  │
│  │     ia.markDirty()                                       │  │
│  │ }                                                        │  │
│  │                                                             │  │
│  │ func (ia *InputArea) redo() {                             │  │
│  │     if ia.redoStack.Empty() { return }                   │  │
│  │     ia.undoStack.Push(copyRunes(ia.text))                │  │
│  │     ia.text = ia.redoStack.Pop()                         │  │
│  │     ia.cursor = min(ia.cursor, len(ia.text))             │  │
│  │     ia.markDirty()                                       │  │
│  │ }                                                        │  │
│  │                                                             │  │
│  │ // 自动完成触发条件（与 GA 一致）                            │  │
│  │ func (ia *InputArea) onTextChange() {                    │  │
│  │     firstLine := ia.firstLine()                           │  │
│  │     if firstLine.startswith("/")                         │  │
│  │        and " " not in firstLine                          │  │
│  │        and "\n" not in ia.text { │  │
│  │         ia.paletteActive = true                          │  │
│  │         t.showPalette(ia.text[1:])                      │  │
│  │     } else {                                             │  │
│  │         ia.paletteActive = false                        │  │
│  │         t.hidePalette()                                │  │
│  │     }                                                    │  │
│  │ } │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.12 命令面板（Command Palette）

```
┌──────────────────────────────────────────────────────────────────┐
│                    Command Palette (Modal)                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ type CommandPalette struct {                              │  │
│  │     Modal                                              │  │
│  │     query string                                   │  │
│  │     commands []Command //全部命令 │  │
│  │     filtered []Command     // 过滤后的命令             │  │
│  │     selectedIdx int                                   │  │
│  │ } │  │
│  │                                                             │  │
│  │ type Command struct {                                     │  │
│  │     Name string                                   │  │
│  │     Description string                                   │  │
│  │     Aliases     []string                                 │  │
│  │     Run func(*TUI)                               │  │
│  │ }                                                       │  │
│  │                                                             │  │
│  │ func (cp *CommandPalette) filter(query string) []Command { │  │
│  │     if query == "" { return cp.commands }               │  │
│  │     q := strings.ToLower(query)                         │  │
│  │     return slices.Filter(cp.commands, func(c Command) bool { │
│  │         return strings.Contains(c.Name, q)              │  │
│  │            || slices.Contains(c.Aliases, q) │  │
│  │     }) │  │
│  │ }                                                        │  │
│  │                                                             │  │
│  │ // 命令列表（示例） │  │
│  │ var COMMANDS = []Command{                                 │  │
│  │     {Name: "btw",      Description: tr("cmd.btw"), │  │
│  │          Run: func(t *TUI) { t.runBtw() }}, │  │
│  │     {Name: "session",  Description: tr("cmd.session"),   │  │
│  │          Aliases: []string{"sessions"},                  │  │
│  │          Run: func(t *TUI) { t.openSessionPicker() }}, │  │
│  │     {Name: "new",      Description: tr("cmd.new"),       │  │
│  │          Run: func(t *TUI) { t.newSession() }}, │  │
│  │     {Name: "export",   Description: tr("cmd.export"),    │  │
│  │          Run: func(t *TUI) { t.openExportPicker() }},  │  │
│  │     {Name: "theme",    Description: tr("cmd.theme"),     │  │
│  │          Run: func(t *TUI) { t.openThemePicker() }}, │  │
│  │     {Name: "fold",     Description: tr("cmd.fold"),      │  │
│  │          Run: func(t *TUI) { t.toggleFold() }}, │  │
│  │     {Name: "rewind",   Description: tr("cmd.rewind"),    │  │
│  │          Run: func(t *TUI) { t.openRewindPicker() }}, │  │
│  │     // ... more commands ... │  │
│  │ }                                                        │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 六、主题定义

### 6.1 默认主题（Atlas Dark）

```go
var gaDarkPalette = Palette{
    BG:        "#1e1e2e", // 深紫灰背景
    AltBG:     "#313244",   // 次级背景
    FG:        "#cdd6f4",   // 主文字
    Muted:     "#a6adc8",   // 次级文字
    Dim:       "#6c7086",   // 暗淡文字
    Green:     "#a6e3a1",   // 成功/用户消息
    Blue:      "#89b4fa",   // 链接/操作
    Purple:    "#cba6f7",   // 特殊强调
    ChipName:  "#fab387",   // 会话名
    ChipModel: "#89b4fa",   // 模型名
    ChipEffort:"#f5c2e7",   // effort 标签
    ChipTasks: "#fab387",   // 任务数
    ChipTime:  "#a6e3a1",   // 时钟
    SelBG:     "#45475a",   // 选择背景
    Border:    "#6c7086",   // 边框
}
```

### 6.2 ANSI 转义序列常量

```go
var (
    ansiReset = "\x1b[0m"
    ansiBold = "\x1b[1m"
    ansiDim = "\x1b[2m"
    ansiItalic = "\x1b[3m"
    ansiUnderline = "\x1b[4m"
    ansiBlink       = "\x1b[5m"
    ansiReverse = "\x1b[7m"
    ansiStrike = "\x1b[9m"
    ansiBlack = "\x1b[30m"
    ansiRed         = "\x1b[31m"
    ansiGreen       = "\x1b[32m"
    ansiYellow      = "\x1b[33m"
    ansiBlue        = "\x1b[34m"
    ansiMagenta     = "\x1b[35m"
    ansiCyan        = "\x1b[36m"
    ansiWhite       = "\x1b[37m"
    ansiCursorHide = "\x1b[?25l"
    ansiCursorShow  = "\x1b[?25h"
    ansiClearScreen = "\x1b[2J"
    ansiCursorHome  = "\x1b[H"
    ansiEraseLine   = "\x1b[K"
    ansiSaveCursor  = "\x1b[s"
    ansiRestoreCursor= "\x1b[u"
    ansiCursorUp = "\x1b[%dA"
    ansiCursorDown  = "\x1b[%dB"
    ansiCursorRight = "\x1b[%dC"
    ansiCursorLeft  = "\x1b[%dD"
    ansiCursorTo    = "\x1b[%d;%df"
    ansiScrollUp    = "\x1b[%dS"
    ansiScrollDown  = "\x1b[%dT"
)
```

---

## 七、组件接口定义

```go
// Component 是所有 UI 组件的通用接口
type Component interface {
    // ID 返回组件的唯一标识符，用于 dirty tracking
    ID() ComponentID
    
    // Render 渲染组件内容到 ANSI 转义序列字符串
    // 每次调用可能很重，调用方应检查缓存
    Render(ctx *RenderCtx) string
    
    // OnEvent 处理来自事件总线的事件
    OnEvent(evt Event) bool // 返回是否消费了事件
    
    // MarkDirty 标记组件需要重新渲染
    MarkDirty()
    
    // Dirty 返回组件是否处于 dirty 状态
    Dirty() bool
    
    // ClearDirty 清除 dirty 标记（渲染后调用）
    ClearDirty()
}

// RenderCtx 渲染上下文，包含所有渲染所需的信息
type RenderCtx struct {
    TermW, TermH int              // 终端尺寸
    Theme *Theme // 当前主题
    ThemeVer int               // 主题版本号（用于 cache key）
    ScrollY int               // 当前滚动位置
    Focused ComponentID       // 当前焦点的组件 ID
}

// Modal 是模态对话框的基接口
type Modal interface {
    Component
    Dismiss()
    OnDismiss(fn func())
}
```

---

## 八、实现路线图

### Phase 1: 基础设施（优先级最高）

| 任务 | 描述 | 验收标准 |
|------|------|----------|
| TUI-1.1 | 创建 `internal/tui/engine/` 模块，定义 `Engine` 结构 | 独立 goroutine 事件循环，3 种事件类型 |
| TUI-1.2 | 实现 `BatchWriter`，合并 write syscall | 基准测试：write 次数减少 80% |
| TUI-1.3 | 实现 `Cache` 层，`_cache_key` + `_cached_output` | 相同输入的第二次 render 时间 < 0.1ms |
| TUI-1.4 | 实现 `DirtySet`，区域级 diff | 局部变化只重绘该区域 |
| TUI-1.5 | 创建 `internal/tui/layout/` 模块 | 支持 Fixed/Fraction/Auto/Min/Max |
| TUI-1.6 | Resize debounce + no-op guard | 窗口拖拽时 CPU 占用下降 50% |

**Phase 1 完成后**：渲染管道完整，60fps 输入响应。

### Phase 2: 组件化（核心功能）

| 任务 | 描述 | 验收标准 |
|------|------|----------|
| TUI-2.1 |拆分 `tui.go` → `component/` 模块 | 单文件从 1960 行降至 < 500 行 |
| TUI-2.2 | 实现 `Topbar` 组件 | 三段式布局（2:2:1 比例），model chip居中 |
| TUI-2.3 | 实现 `InputArea` 组件 | undo/redo、cursor、光标选择、height auto-fit |
| TUI-2.4 | 实现 `MessageList` 组件 | 懒加载（batch=50），滚动加载更多 |
| TUI-2.5 | 实现 `Block` 组件 | 折叠/展开，标题提取（`<summary>` 优先） |
| TUI-2.6 | 实现 `Spinner` 组件 | 16ms tick，5 种动画样式 |
| TUI-2.7 | 实现 `StreamOutput` 组件 | 流式节流（16ms），打字效果可选 |

**Phase 2 完成后**：主界面完整功能，组件独立可测试。

### Phase 3: 交互增强

| 任务 | 描述 | 验收标准 |
|------|------|----------|
| TUI-3.1 | 实现 `CommandPalette` | 搜索过滤，Tab 自动完成 |
| TUI-3.2 | 实现 `SessionPicker` | 懒加载会话列表 |
| TUI-3.3 | 实现 `ThemePicker` | 实时预览主题 |
| TUI-3.4 | 实现 `ConfirmDialog` | Esc 回退机制 |
| TUI-3.5 | 实现 `RewindPicker` | 回滚历史选择 |
| TUI-3.6 | Scroll 位置保护 | 翻历史时 remount 不打断 |

**Phase 3 完成后**：完整交互体验，接近 GA TUI 品质。

### Phase 4: 打磨

| 任务 | 描述 | 验收标准 |
|------|------|----------|
| TUI-4.1 | i18n 完善 | `internal/tui/i18n/locale/en.toml` + `zh.toml` |
| TUI-4.2 | 性能基准测试 | 万级消息 remount < 200ms |
| TUI-4.3 | 多主题支持 | atlas-default / atlas-light / nord / gruvbox |
| TUI-4.4 | 键盘快捷键覆盖 | 全部快捷键可配置 |
| TUI-4.5 | 边界情况测试 | 空会话、极窄终端、超长消息 |

**Phase 4 完成后**：正式发布 v0.6.0。

---

## 九、测试策略

### 9.1 分层测试

```
┌──────────────────────────────────────────────────────────────────┐
│                    Pyramid Test Strategy │
│                                                                  │
│                          ▲ │
│                         /│\ │
│                        / │ \ E2E Tests │
│                       /  │  \      (20% of tests)                 │
│                      /   │   \    - Full TUI interaction flow │
│                     /────│────\ - Session lifecycle │
│                    /     │     \  - Multi-agent orchestration │
│                   /      │      \                                 │
│                  /───────│───────\ Integration Tests           │
│                 /        │        \ (30% of tests) │
│                /         │         \- Component integration │
│               /──────────│──────────\ - Layout computation │
│              /           │           \ - Event bus coordination │
│             /────────────│────────────\                           │
│            /             │             \  Unit Tests              │
│           /              │              \(50% of tests)           │
│          ▼───────────────▼──────────────▼ │
│     Component    Layout    Cache    Event Bus    Undo/Redo       │
│     Tests        Tests     Tests     Tests        Tests          │
└──────────────────────────────────────────────────────────────────┘
```

### 9.2 关键测试用例

| 测试 | 描述 | 预期 |
|------|------|------|
| `TestCache_SameInputReturnsCached` | 相同 CacheKey 的两次 Render |第二次 < 0.1ms |
| `TestDirtySet_MarksParentOnChildChange` | 子组件 dirty 时父组件也被标记 | 父组件 Dirty() == true |
| `TestLazyList_LoadsOnDemand` | scroll 到边界时触发 LoadMore | visible 数量增加 batch |
| `TestResizeDebounce_SingleFlush` | 80ms 内多次 resize | 只触发一次 doFullResize |
| `TestInputHeight_NoOpGuard` | 输入行数不变时 resizeInput | layout 不重算 |
| `TestScrollPreserve_AtBottom` | atBottom=true 时 remount | 自动 scrollEnd |
| `TestScrollPreserve_MidScroll` | mid-scroll 时 remount | 保持原 scrollY |
| `TestThemeSwitch_InvalidatesCache` | 切换主题后所有缓存失效 | `_cached_key == nil` |
| `TestUndoRedo_StackIsolated` | undo 和 redo 栈隔离 | undo 后 redo 不为空 |

---

## 十、迁移计划

### 10.1 渐进式迁移（不对用户暴露中间状态）

**策略**：在 `internal/tui/v2/` 中开发新架构，原 `internal/tui/` 作为 v1 保持兼容，最终通过 feature flag 切换。

```
internal/tui/
├── v1/                   # 【保留】当前实现
│   ├── tui.go
│   ├── state.go
│   └── ...
├── v2/                   # 【新增】重构实现
│   ├── engine/
│   ├── layout/
│   ├── component/
│   └── tui.go
├── state/ # 【共享】状态机定义（v1 和 v2 共用）
├── i18n/                 # 【共享】国际化
└── theme/                # 【共享】主题系统
```

### 10.2 Feature Flag 切换

```go
// cmd/atlas/main.go
func main() {
    if os.Getenv("ATLAS_TUI_V2") == "1" {
        tui.RunV2()  // 新架构
    } else {
        tui.RunV1()  // 当前实现
    }
}
```

**切换时机**：
- v2 开发完成并通过全部测试
- 邀请核心用户（3-5 人）灰度测试 1 周
- 无阻断问题后，默认开启 v2
- v1 代码保留 1 个 minor 版本后删除

### 10.3 API 兼容性保证

| 接口 | v1 | v2 | 兼容性 |
|------|----|----|--------|
| `tui.Run(ctx)` | ✅ | ✅ | 签名一致 |
| `agent.StreamEvent` | ✅ | ✅ | 结构一致 |
| `session.Session` | ✅ | ✅ | 结构一致 |
| `config.Config` | ✅ | ✅ | 完全兼容 |
| 命令行参数 | ✅ | ✅ | 完全兼容 |

---

##十一、关键技术决策（ADR）

### ADR-001: 选择自研渲染引擎而非引入框架

**状态**：已采纳

**背景**：评估了 bubbletea、tview 等框架，最终选择自研架构。

**理由**：
1. Atlas 的设计哲学是极简依赖，引入第三方框架违背核心原则
2. GA 的 Textual 设计模式可以完整迁移到 Go 自研实现
3. 自研渲染引擎可以针对 Atlas 的流式输出场景做极致优化
4. 一次性深度工程，「不将就、不妥协、不敷衍」

**后果**：
- 开发工作量增加，但架构质量由我们完全控制
- 需要实现自己的 dirty diff 算法（类似 React/Virtual DOM 的思路）

### ADR-002: 三 goroutine 事件循环架构

**状态**：已采纳

**背景**：解决主循环阻塞导致的渲染与输入争抢问题。

**方案**：InputLoop / RenderLoop / StreamLoop 通过 channel 通信，RenderLoop 独立以 60fps 运行。

**理由**：
- InputLoop 可以阻塞等待按键，不影响渲染
- StreamLoop 可以异步处理 LLM 流式事件
- RenderLoop 是唯一的渲染入口，避免竞态条件

### ADR-003: 消息缓存机制

**状态**：已采纳

**方案**：每个 Component 持有一个 `_cache_key`，相同 key 时返回缓存的输出。

**理由**：
- 大部分消息在交互过程中不需要重新渲染
- cache key 包含 version/content/width/foldState，精确控制失效时机
- 万级消息场景下，缓存机制可将 remount 时间从秒级降至百毫秒级

---

## 十二、风险与缓解

| 风险 | 严重程度 | 缓解措施 |
|------|----------|----------|
| dirty diff 算法实现复杂度高 | 高 | 参考 React/Virtual DOM 实现，测试先行 |
| 组件拆分后接口不兼容 | 中 | feature flag 切换，保留 v1 兼容层 |
| 性能提升不及预期 | 中 | Phase 4 专门做基准测试，未达标则迭代优化 |
| 单文件拆分工作量大 | 低 | 渐进式拆分，保留 git history |
| Go 不支持 async/await，goroutine 泄露 | 中 | 严格的 context 传递，defer 清理所有资源 |

---

## 十三、总结

这份设计方案的核心是「**自研一套接近 Textual 体验的增量渲染引擎**」，而不是简单地「引入一个框架然后打补丁」。

关键创新点：
1. **三 goroutine 事件循环**：彻底解决渲染与输入争抢
2. **声明式布局 DSL**：让布局定义像 CSS 一样声明式，测量计算自动化
3. **消息缓存层**：相同输入不重复渲染，万级消息秒级 remount
4. **dirty diff 算法**：只重绘变化的区域，write syscall 减少 80%
5. **懒加载列表**：千级列表首屏可交互，按需加载
6. **Resize 防抖 + no-op guard**：窗口拖拽无视觉撕裂
7. **主题系统**：多主题支持，切换时完整更新

这是 Atlas TUI 从「功能性实现」到「工业级品质」的必经之路。

---

*文档版本：v1.0*
*作者：基于 Atlas TUI 现状 与 GA TUI (Textual v2) 对比分析*
*日期：2026-06-09*