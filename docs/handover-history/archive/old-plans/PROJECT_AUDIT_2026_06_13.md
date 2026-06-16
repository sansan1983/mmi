# MMI 项目全面审查与优化建议报告

> 生成时间：2026-06-13
> 审查范围：全代码库（Python 26,269 行 + TypeScript 1,132 行 + 539 测试）
> 审查方法：逐模块代码阅读 + 架构分析

---

## 1. 项目全景：代码量分布

| 模块 | 行数 | 文件数 | 定位 | 成熟度 |
|------|------|--------|------|--------|
| `mmi/core/` | ~7,500 | 24 | 记忆引擎 + LLM 网关 | ⭐⭐⭐⭐ 成熟 |
| `mmi/agent/` | ~2,000 | 15 | Agent 调度框架 | ⭐⭐⭐ 框架好，内容少 |
| `mmi/cli/` | ~1,800 | 17 | CLI 命令 | ⭐⭐⭐⭐ 完整 |
| `mmi/tui/` | ~1,500 | 8 | Python TUI (Textual) | ⭐⭐ 半成品 |
| `tui-ts/src/` | 1,132 | 24 | TypeScript TUI (Ink) | ⭐⭐⭐ 架构好，功能60% |
| `tests/` | ~8,000 | 52 | 测试套件 | ⭐⭐⭐⭐ 覆盖全面 |
| **合计** | **~27,400** | **140+** | | |

**关键发现**：70% 的代码在 core + test，这是好事——基础扎实。但 TUI 层（两套加起来 ~2,600 行）产出不了合格的用户体验。

---

## 2. Core 层：最扎实的部分

### 已建成的核心能力

| 模块 | 行数 | 功能 | 评价 |
|------|------|------|------|
| `manager.py` | 780 | 会话管理 + 流式聊天 + pipeline | ✅ 核心枢纽，功能完整 |
| `llm.py` | 750 | LLM 统一接口 + SSE 流式 + 重试 | ✅ 6 种 Provider 适配 |
| `session.py` | 350 | Session 数据模型 | ✅ 稳定 |
| `storage.py` | 450 | 文件存储 + 原子写 | ✅ 可靠 |
| `context.py` | 320 | 上下文构建 + 修剪 | ✅ 核心差异化 |
| `heat.py` | 280 | 热度计算（多因子） | ✅ 有深度 |
| `summarizer.py` | 400 | 增量摘要 | ✅ 异步 + 多策略 |
| `providers.py` | 600 | Provider 实现 | ✅ OpenAI/Anthropic/Google/DeepSeek |
| `provider_registry.py` | 200 | 插件式 Provider 发现 | ✅ 扩展性好 |
| `provider_health.py` | 150 | 健康检测 | ✅ 成功/失败计数 |
| `model_fetcher.py` | 180 | 模型列表获取 + 缓存 | ✅ TTL 缓存 |
| `search.py` | 250 | 全文搜索 + BM25 + jieba | ✅ 搜索质量不错 |
| `config.py` | 300 | 配置管理 | ✅ TOML + schema 校验 |
| `mcp_server.py` | 250 | MCP 服务端 | ✅ 已有基础实现 |
| `i18n.py` | 120 | 国际化 | ✅ 中英双语 |

### 问题与优化建议

1. **`manager.py` 780 行偏大**
   - 建议：把 `stream_chat` 和 `batch_chat` 抽到 `mmi/core/chat_engine.py`
   - 把搜索相关逻辑抽到 `mmi/core/search_engine.py`
   - 目标：manager.py < 400 行

2. **`llm.py` 750 行，SSE 解析逻辑复杂**
   - 6 种 Provider 的 SSE 解析差异处理在一个大方法里
   - 建议：每个 Provider 的 SSE 解析独立为 `_parse_sse_openAI()` / `_parse_sseAnthropic()` 等
   - 已有 `providers.py` 但 `llm.py` 仍有大量 Provider 特定逻辑

3. **`gc_daemon.py` 150 行但缺少实际调度**
   - 有 daemon 框架但没有集成到 `manager.py` 的启动流程
   - 建议：在 `SessionManager.__init__` 中可选启动 GC daemon

4. **`audit.py` 300 行但只有一种审计类型**
   - Deep Audit 依赖 LLM，成本高
   - 建议：增加轻量级规则审计（不耗 LLM token）

---

## 3. TUI 层：最大的痛点

### Python TUI（mmi/tui/）—— 问题清单

基于 `textual` 框架，~1,500 行代码。

| 问题 | 严重度 | 详情 |
|------|--------|------|
| **无 Markdown 渲染** | 🔴 致命 | LLM 回复的代码块、列表、粗体全部显示为纯文本 |
| **Token 计数显示乱码** | 🔴 严重 | topbar 显示 `~-- ctx`，turn 显示 `~?? tok`，全是占位符未实现 |
| **静默吞异常** | 🔴 严重 | 14 处 `except Exception: pass`，出错无任何反馈 |
| **无代码高亮** | 🟡 重要 | 代码块无语法高亮 |
| **流式体验差** | 🟡 重要 | 虽然调用了 `stream_chat`，但没有逐字动画效果 |
| **命令系统简陋** | 🟡 重要 | 只有 6 个 slash 命令，无补全 |
| **无会话创建 UI** | 🟡 重要 | 只能从列表进入，`/new` 命令体验差 |
| **CSS 硬编码** | 🟡 中等 | `theme_css.py` 只有 dark/light 两套，无 Tokyo Night 等主题 |
| **搜索界面残缺** | 🟡 中等 | `SearchScreen` 存在但功能极简 |

**结论**：Python TUI 确实"连半成品都达不到"。Textual 框架的 Markdown 支持（`textual.widgets.Markdown`）其实存在，但项目没有使用。

### TypeScript TUI（tui-ts/）—— 问题清单

基于 React + Ink，~1,132 行代码。

| 问题 | 严重度 | 详情 |
|------|--------|------|
| **IPC `create_session` 未实现** | 🔴 严重 | `cli.tsx` 第 39 行标注 TODO |
| **流式输出未集成到 Chat** | 🔴 严重 | `stream.tsx` 存在但未在 `Chat.tsx` 中使用 |
| **SlashMenu 未完整接入** | 🟡 重要 | `SlashMenu.tsx` 组件存在但 Chat 中未调用 |
| **FoldBlock/Citation 未使用** | 🟡 中等 | 组件写好了但没有在任何屏幕中渲染 |
| **无 Skill 管理界面** | 🟡 中等 | 后端有 SkillLibrary 但 TUI 无入口 |
| **无 Agent 状态显示** | 🟡 中等 | 不知道当前哪个 Agent 在处理 |

**结论**：TS TUI 的**架构远优于 Python TUI**——组件化清晰、有主题系统、有 Markdown 渲染工具、有测试。但功能完成度只有 ~60%，大量组件写好了但没有接入。

### 🎯 TUI 战略建议

> **核心问题：为什么要维护两套 TUI？**

两套 TUI 导致：
- 开发精力分散（修一个 bug 要考虑改哪套）
- 功能不一致（用户困惑）
- 测试翻倍

**建议方案**：

| 方案 | 描述 | 推荐度 |
|------|------|--------|
| **A. 全力 tui-ts** | 冻结 Python TUI，所有资源投入 TS TUI | ⭐⭐⭐⭐⭐ |
| B. 合并功能 | 把 tui-ts 的好组件回移到 Python TUI | ⭐⭐ 投入大收益小 |
| C. 双轨并行 | 继续两套同时开发 | ⭐ 资源不够 |

**推荐方案 A**：
1. 把 `mmi/tui/` 标记为 `legacy`，只修 bug 不加功能
2. 用 2-3 周集中补齐 tui-ts 的缺失功能
3. 优先完成：`create_session` IPC → 流式 Chat → SlashMenu 接入 → Skill 面板

---

## 4. Agent 系统：框架完整，内容单薄

### 已建成

| 组件 | 行数 | 状态 |
|------|------|------|
| `orchestrator.py` | 247 | ✅ Pipeline + 6 步流程 |
| `pipeline.py` | 213 | ✅ 可组合步骤 |
| `router.py` | 170 | ⚠️ 纯关键词规则分类 |
| `event_bus.py` | 269 | ✅ 发布/订阅 + 节流 |
| `skill.py` | 243 | ✅ CRUD + 关键词匹配 |
| `trace.py` | 150 | ✅ 追踪记录 |
| `validate.py` | 120 | ✅ 规则校验 |
| `registry.py` | 99 | ✅ 注册表 |
| `steps.py` | 180 | ✅ 6 个内建步骤 |
| `builtin/code_review.py` | 167 | ✅ 可用 |
| `builtin/doc.py` | 105 | ✅ 可用 |

### 问题

1. **Router 是玩具级**：纯正则关键词匹配，7 个 Intent 只有 2 个 Agent（code_review + doc）。`DATA_ANALYSIS`、`BRAINSTORM`、`AUDIT`、`QA`、`TOOL_CALL` 全部路由到 default agent
2. **只有 2 个 Agent**：code_review 和 doc，远不够"多 Agent 调度"的定位
3. **Skill 匹配是纯关键词**：`match()` 用 `query.lower().split()` 做词集交集，无 embedding、无语义
4. **Agent 间无协作**：没有 multi-agent 对话、没有 agent 间委托
5. **modes.py 有 5 种 ThinkingMode 但实际未使用**

---

## 5. Provider 系统：扩展性好，但缺乏治理

### 已建成

- 6 个内置 Provider（OpenAI/Anthropic/Google/DeepSeek/Kimi/Moonshot）
- 插件注册机制（`~/.mmi/providers/` 自动发现）
- 健康检测（成功/失败计数 + 错误记录）
- 模型列表获取 + 本地缓存（TTL 300s）
- SSE 流式 + 重试机制

### 问题

1. **无 Provider 切换 UI**：只能通过 `config.toml` 或 `/model` 命令手动切换
2. **无 fallback 链**：健康检测只记录，不自动切换
3. **无 token 用量统计**：不知道每次对话消耗了多少 token/费用
4. **Kimi 已移除但代码残留**：`providers.py` 中 Kimi 的 SSE 解析逻辑仍在

---

## 6. 扩展技能系统：有骨架，缺血肉

### 当前机制

```
用户请求 → Router.classify() → IntentType → AgentRegistry 选 Agent → Pipeline 执行
                                                                          ↓
                                                              SkillLibrary.propose() 匹配技能
```

### 添加新技能的 3 种路径

| 路径 | 方式 | 轻量化 | 适用场景 |
|------|------|--------|----------|
| **1. 内置 Agent** | `mmi/agent/builtin/` 加 `.py` | ⚠️ 增加包体积 | 核心能力（代码审查、文档生成） |
| **2. Skill 文件** | `~/.mmi/skills/*.json` | ✅ 零代码 | 用户自定义工作流 |
| **3. Provider 插件** | `~/.mmi/providers/*.py` | ✅ 按需加载 | 接入新 LLM |

### 推荐的轻量化扩展方案

**方案：Prompt Template 技能 + Tool 注册**

```json
// ~/.mmi/skills/translate.json — 零代码技能
{
  "skill_id": "translate-v1",
  "name": "翻译助手",
  "skill_type": "BUILTIN",
  "content": "你是一个专业翻译。将用户输入翻译为{{target_lang}}。保持原文格式。",
  "apply_scene": "用户要求翻译时",
  "tags": ["翻译", "translate", "i18n"]
}
```

```python
# ~/.mmi/tools/word_count.py — 轻量 Tool 插件
from mmi.agent.tools import register_tool

@register_tool(name="word_count", description="统计文本字数")
def word_count(text: str) -> int:
    return len(text.split())
```

**关键原则**：
- **技能 = Prompt Template + 可选 Tool**，不需要写 Agent 子类
- **Tool 用装饰器注册**，放到 `~/.mmi/tools/` 自动发现
- **Router 加 LLM 分类 fallback**：关键词匹配失败时用 LLM 判断意图
- **技能市场**：社区共享 JSON 技能文件（类似 Claude Code 的 skills marketplace）

---

## 7. 代码质量与架构问题

### 异常处理灾难

Python TUI 中 **14 处** `except Exception: pass`，核心模块中也有多处。这意味着：
- 用户操作失败无任何反馈
- 开发者无法定位问题
- 数据可能静默丢失

### 线程安全隐患

- `SkillLibrary` 有 `RLock` ✅
- `SessionManager` 的 `stream_chat` 无锁 ⚠️
- `HistoryStore` 无锁 ⚠️

### 重复代码

- `tui/app.py` 和 `tui/screens/chat.py` 多处重复的 `try/except` 模式
- `core/llm.py` 中 SSE 解析与 `providers.py` 有逻辑重叠

### 测试覆盖盲区

| 有测试 | 无测试 |
|--------|--------|
| core 模块 ✅（全面） | TUI 交互 ❌ |
| Agent pipeline ✅ | Agent 端到端对话 ❌ |
| Provider 参数 ✅ | Skill 实际使用场景 ❌ |
| LLM 流式 ✅ | 错误恢复路径 ❌ |

---

## 8. 战略建议：方向与优先级

### 核心判断

> **MMI 的 core 是一个合格的记忆引擎 + LLM 网关，但 TUI 拖了后腿。继续同时维护两套 TUI 是资源浪费。**

### 建议路线图

#### 🔴 P0 — 止血（1-2 周）

1. **砍掉 Python TUI**（或降级为 debug 工具）
   - Textual 生态太小，Markdown/代码高亮支持差
   - 把 `mmi/tui/` 改名为 `mmi/_debug_tui/`，仅做开发调试用
   - 所有用户体验投入集中到 tui-ts

2. **修异常处理**
   - 全局搜索 `except Exception: pass`，替换为有意义的错误处理
   - 至少在 TUI 中显示错误提示

3. **tui-ts 补齐核心功能**
   - 完成 `create_session` IPC
   - 集成流式输出到 Chat
   - 接入 SlashMenu 完整功能

#### 🟡 P1 — 建立差异化（2-4 周）

4. **tui-ts 做杀手级功能**
   - **记忆可视化**：侧边栏显示 heat map、session 关系图
   - **Skill 面板**：浏览/安装/管理技能
   - **多 Agent 状态**：显示当前哪个 Agent 在处理、Pipeline 步骤进度
   - 这些是 Claude Code / Aider 没有的

5. **Router 升级**
   - 关键词匹配 → LLM 分类 fallback（用小模型如 haiku 做意图判断）
   - 添加 2-3 个实用 Agent：`summarize`、`translate`、`research`

6. **技能扩展框架**
   - 实现 `~/.mmi/tools/` 自动发现
   - 技能 JSON schema 标准化
   - CLI 命令：`mmi skill install <url>`

#### 🟢 P2 — 生态（1-2 月）

7. **Provider 治理**
   - fallback 链（主 Provider 失败自动切备用）
   - token 用量 dashboard
   - 费用估算

8. **MCP 集成**
   - 让 MMI 作为 MCP client 接入外部工具
   - 或作为 MCP server 暴露记忆能力

9. **技能市场**
   - GitHub 仓库托管社区技能
   - `mmi skill search <keyword>` 搜索
   - `mmi skill install <name>` 安装

---

## 9. 总结

| 维度 | 评分 | 一句话 |
|------|------|--------|
| Core 记忆引擎 | ⭐⭐⭐⭐ | 有深度，heat/session/summary 体系完整 |
| Agent 框架 | ⭐⭐⭐ | Pipeline + EventBus 架构好，但 Agent 内容太少 |
| Provider 系统 | ⭐⭐⭐⭐ | 6 家 + 插件机制 + 健康检测，扩展性好 |
| Python TUI | ⭐⭐ | 能用但体验差，建议放弃 |
| TypeScript TUI | ⭐⭐⭐ | 架构好，功能完成度 60% |
| 技能扩展 | ⭐⭐ | 有 SkillLibrary 骨架，缺实际技能和工具发现 |
| 测试覆盖 | ⭐⭐⭐⭐ | 539 测试，core 覆盖全面 |
| 文档 | ⭐⭐⭐ | 架构文档完整，但 handover 太多（21 个） |

**最关键的一步**：**选定一个 TUI，全力投入 tui-ts**。两套半成品的体验远不如一套精品。tui-ts 的 React + Ink 架构更适合做记忆可视化、Skill 面板这些差异化功能。

**轻量化扩展的答案**：不要加更多 Python 代码到核心包里。用 **JSON 技能文件 + Tool 插件自动发现** 实现零代码扩展，用 **Provider 插件** 实现 LLM 接入扩展，用 **MCP** 实现外部工具扩展。核心包保持精简，扩展全部走插件。

---

*报告生成时间：2026-06-13*
*基于代码审查，非运行时测试*
