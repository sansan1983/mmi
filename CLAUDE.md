# CLAUDE.md — MMI 多模态智能体系统

<!--
     ╔══════════════════════════════════════════════════════════╗
     ║  △ 会话交接区 — 每次开工先读这里，每次收工更新这里    ║
     ╚══════════════════════════════════════════════════════════╝
-->

## △ 当前状态

| 项目 | 内容 |
|------|------|
| **当前阶段** | Phase 0｜止血（TUI 修复 + GC 集成 + 质量门禁） |
| **当前任务** | 详见 `docs/ROADMAP/DEVELOPMENT_ROADMAP.md` |
| **最近完成** | 文档目录全盘整理 + 开发路线图 v2.0 重写（2026-06-16） |
| **下次动作** | Phase 0 Task 0.1：Python TUI Markdown 渲染修复 |

**近期日志**（最近 3 条，完整历史见 `WORKLOG.md`）：

| 日期 | 动作 | 产出 |
|------|------|------|
| 2026-06-16 | 文档全盘整理 + 路线图 v2.0 | `docs/ROADMAP/DEVELOPMENT_ROADMAP.md` |
| 2026-06-16 | 项目根目录清理 | 删除 8 个无关目录/文件 |
| 2026-06-16 | 新 CLAUDE.md + RULES.md 重写 | 本文件生效 |

---

## △ 收工仪式（每次结束前执行）

会话结束时，更新上面「当前状态」表格：
1. 把「最近完成」改为刚才做了什么
2. 把「下次动作」改为下一个任务是什么
3. 把新的日志行追加到「近期日志」顶部，保留最近 3 条
4. 把旧日志行移到 `WORKLOG.md` 尾部

---

<!--
     ╔══════════════════════════════════════════════════════════╗
     ║  §2 不可变铁律 — 每次编码前必须遵守                     ║
     ╚══════════════════════════════════════════════════════════╝
-->

## 铁律

### 1. Think Before Coding

- 先陈述假设。不确定就问。
- 有多种解释时，列出来让用户选——不要自己猜。
- 有更简单的方案就说。该 push back 就 push back。
- 遇到不清楚的地方，停下来，指出困惑点。

### 2. Simplicity First

- 不做需求以外的功能。
- 不为单次使用写抽象。
- 不做没被要求的"灵活性"或"可配置性"。
- 不对不可能出现的场景写错误处理。
- 写了 200 行能压到 50 行，就重写。

### 3. Surgical Changes

- 不改相邻代码的注释、格式、风格。
- 不重构没坏的东西。
- 匹配现有风格，即便不是你的偏好。
- 发现无关的 dead code，提出来——但别删。
- 只清理你引入的 orphan（import、变量、函数）。

### 4. Goal-Driven Execution

- 每个任务写成可验证目标："加验证" → "先写失败测试，再让它通过"。
- 多步骤任务先列简要 plan，每步带 verify 检查点。
- 不写模糊的成功标准。

### 5. 开工必做

- **读 CLAUDE.md 顶部「当前状态」表格** — 这就是你的接班指令
- **读 `docs/ROADMAP/DEVELOPMENT_ROADMAP.md`** — 确认当前 Phase/Task 的详细步骤
- **开工前说一句**你在做什么 — "开始 Task X: [描述]"
- **严格按 Task 的 Step 顺序执行** — 每个 Step 做完再进下一个

### 6. 交接必做

- **更新 CLAUDE.md 顶部「当前状态」表格**
- **把旧日志移到 WORKLOG.md**
- commit 时写清楚做了什么

### 7. Python 特定

- `ruff check mmi/` 零告警（warning = fail）
- `pytest tests/ -x` 全部通过
- 不跳过测试直接提交
- 类型标注：所有公共函数参数 + 返回值
- 原子写：先写 `.tmp` 再 `os.replace()`

---

<!--
     ╔══════════════════════════════════════════════════════════╗
     ║  §3 项目速览 — 理解项目结构用                            ║
     ╚══════════════════════════════════════════════════════════╝
-->

## 项目速览

**MMI = Multimodal Intelligence** — 带记忆引擎与多Agent调度的智能体系统。从 C-Trim 演进而来。

### 核心模块

| 模块 | 文件 | 用途 |
|------|------|------|
| 记忆引擎 | `mmi/core/memory.py` | FAISS 向量检索 + SQLite FTS5 关键词双路合并 |
| 上下文构建 | `mmi/core/context.py` | 三源合并（summary + hit_paragraphs + recent_turns） |
| 会话管理 | `mmi/core/session.py` | Session 数据契约 + ULID |
| 热 度 | `mmi/core/heat.py` | 热度公式 + 四态状态机 |
| 垃圾回收 | `mmi/core/gc.py` | GC Daemon（框架已有，未集成） |
| Agent调度 | `mmi/agent/` | 意图分类 + 路由 |
| TUI | `mmi/tui_v3.py` | Python 终端界面（Phase 0 重点修复） |
| TS TUI | `tui-ts/` | TypeScript Ink 界面（IPC 未完成） |

### 三层架构

```
接入层（CLI / TUI）→ Agent调度层（意图分类/路由）→ 记忆引擎层（FAISS + SQLite + LLM重排）
```

### 关键设计原则

- **UI ≠ 推理** — `mmi/core/` 不依赖任何 UI
- **显示 ≠ 发送** — LLM 上下文是修剪过的视图，原文完整保留
- **不压缩原文** — 只修剪 LLM 视图，不改变 session.md 内容

### 关键类型

```python
class SessionState(str, Enum):
    ACTIVE = "active"   # heat ≥ 10
    WARM   = "warm"     # heat ≥ 5
    COLD   = "cold"     # 其他
    ZOMBIE = "zombie"   # cold 持续 90 天

# Session ID 使用 ULID（26 字符）
```

### 技术栈

Python 3.12 + pytest + ruff + FAISS + SQLite + rich

---

## 文档结构

| 文件 | 用途 |
|------|------|
| `docs/ROADMAP/DEVELOPMENT_ROADMAP.md` | **总开发路线图（必读）** |
| `docs/INDEX.md` | 文档总入口 |
| `docs/ARCHITECTURE.md` | 系统架构设计 |
| `docs/SPECS/*.md` | 各功能详细规格 |
| `docs/TESTS/test-policy.md` | 测试规范 |
| `docs/handover-history/round_*.md` | 阶段交接文档 |

---

## 常用命令

```bash
# 测试
pytest tests/ -x

# 代码检查
ruff check mmi/

# 配置 LLM
export MMI_API_KEY=sk-...
export MMI_BASE_URL=https://api.deepseek.com/v1
# 或
mmi config wizard
```

---

## Session 存储

- 路径：`~/.mmi/sessions/{active,trash}/`
- 格式：`{id}.session.md`（YAML frontmatter + Markdown body）
- 摘要触发：≥20 轮 或 ≥5000 字符 或 >24h 且 ≥5 轮