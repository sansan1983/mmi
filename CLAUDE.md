# CLAUDE.md — MMI 多模态智能体系统

<!--
     ╔══════════════════════════════════════════════════════════╗
     ║  △ 会话交接区 — 每次开工先读这里，每次收工更新这里    ║
     ╚══════════════════════════════════════════════════════════╝
-->

## △ 当前状态

| 项目 | 内容 |
|------|------|
| **当前阶段** | Phase 7 完成（chat.py inspect 模式抽 helper） |
| **最近完成** | P7：抽 `chat.py` 的 `--inspect` 模式 30 行诊断输出为私有 helper `_chat_inspect(sid, lang) -> int`。**Surgical 原则**：保留在 chat.py 内（无第二调用方，不污染 `cli/__init__.py`）；保留 `from mmi.core import context as _loader` 的 import 模式（cmd_chat 不需要，避免环依赖） |
| **下次动作** | P8 候选：i18n 化 7 个 LLM 提示词模板（`audit/classifier/llm/titler/summarizer/memory`）；或 P7 收尾 commit |
| **代码质量** | ruff 0 errors ✅, pytest 690 pass ✅, 原子写 ✅, 单例线程安全 ✅, 时间工具统一 ✅, 子命令 dispatch 统一 ✅, 主入口 dispatch 字典化 ✅, chat pipeline 统一 ✅, llm 包化 ✅, memory 包化 ✅, tui_v3 包化 ✅, cmd_*.py i18n 化（13 文件,~120 处）✅, cmd_*.py 类型标注（18 公共 + 8 内部 + 2 dispatch）✅, chat inspect 抽 helper（-29 行）✅ |
| **Git 提交** | P0+P1+P2-1~5+P3-A+B+C+D+E+P4+P5+P6 改动 **已提交**（commit 1-5）；P7 改动 **未提交** |

**已完成的 Phase 概览**：

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 0 | TUI修复、GC集成、ruff门禁、token计数 | ✅ 完成 |
| Phase 1 | CLI拆分、manager职责拆分、provider注册、Heat衰减、IPC修复 | ✅ 完成 |
| Phase 2 | 跨会话记忆、chain-memory、多会话聚合 | 🔄 进行中 |

**近期日志**（最近 3 条，完整历史见 `WORKLOG.md`）：

| 日期 | 动作 | 产出 |
|------|------|------|
| 2026-06-18 | P7：抽 `chat.py` `--inspect` 模式为 `_chat_inspect(sid, lang) -> int` 私有 helper | chat.py -29 行（30 行内联 → 1 行 dispatch + 30 行 helper）；cmd_chat 主路径更清晰；保留 `from mmi.core import context as _loader` lazy import 模式 |
| 2026-06-18 | P6：补全 cmd_*.py 公共 API 类型标注 | 18 个 `cmd_X(args: Namespace, mgr: SessionManager) -> int` + 8 个内部 helper（agent/memory/skill/config）+ `_dispatch`/`_load_command` 同样加。统一 `from argparse import Namespace` + `from mmi.core.manager import SessionManager` import 模式 |
| 2026-06-18 | P5：i18n 化 `config.py` wizard 32 处 + show 3 处 | 38 词条（`wizard.*` 36 + `config_show.*` 2），含 banner/标题/错误/提示/双协议/单协议/api_key/拉模型/写盘/confirm suffix。format spec 保留（`{provider!r}` repr + `{k:10s}` 宽度） |
| 2026-06-18 | P4：i18n 化 12 个 cmd_*.py 硬编码 | 3 批完成。批 1（6 文件：memory/skill/stat/list/update/rename）~30 处；批 2（4 文件：info/inspect/agent/export）~45 处；批 3（2 文件：gc/chat inspect 模式）~19 处。补 70+ 词条到 `zh-CN.json`/`en-US.json`。跳过 `config.py` wizard 32 处（P5） |
| 2026-06-18 | P3-D：拆 `core/memory.py` 978 行 → `core/memory/` 包 | 9 子模块（总 1033 行）+ `__init__.py` 155 行（PEP 562 `__getattr__` 转发）。store.py 改用 `_faiss_mod` 模块引用（避免 clear_memories 后 stale binding）。3 test monkeypatch 改 `memory.faiss._XXX`。顺手修 `memory_tools.py:72` 死代码（`from memory import search` 不存在） |
| 2026-06-18 | P3-C：拆 `core/llm.py` 903 行 → `core/llm/` 包 | 7 子模块: `_types`(20行) / `base`(221行) / `echo`(47行) / `openai`(157行) / `anthropic`(257行) / `factory`(112行) / `ipc_stub`(17行) + `__init__.py` re-export(50行)。test mock 路径 6 处从 `mmi.core.llm.time.sleep` 改 `mmi.core.llm.base.time.sleep` |
| 2026-06-18 | P3-B：`manager.chat`+`stream_chat` 抽 `_post_chat_pipeline` | 净 -19 行（+65/-84），顺手修复 `stream_chat` trashed 时丢 `trashed_reason` 的 bug（helper 给两者都填了 reason） |
| 2026-06-18 | P3-A：`cli/main.py::_dispatch` 70 行 elif 改 dict 查表 | 净 -27 行（+39/-66），`_COMMANDS` 字典（18 子命令）+ `_load_command` 懒加载 helper |
| 2026-06-18 | P2 步骤 5：`dispatch_subcommand` helper 统一 4 处子命令 | `memory/agent/config/skill` 改 `dispatch_subcommand` 字典查表（每处提 `_do_X` 内部 helper）；helper 在 `cli/__init__.py`；不瘦身（+77 行）但统一抽象 |
| 2026-06-18 | P2 步骤 4：抽 `core/_time.py` 统一时间工具 | 删 `heat.py` 的 `parse_iso_utc` + `_format_iso_utc`（28 行）；`session.utcnow_iso` 改包装（5 行）；删 `gc.py` 死代码 `parse_iso_utc`（11 行） |
| 2026-06-18 | P2 步骤 3：抽 `Singleton` 基类(DCL)统一 6 处 | 新建 `core/_patterns.py`（46 行 DCL 基类）；`agent/{skill,tools,trace}` + `core/{evaluation,mcp_server,gc_daemon,provider_registry}` 改基类继承；净 -71 行 |
| 2026-06-18 | P2 步骤 2：抽 `atomic_modify_session` + 公开 `atomic_write` | `update_access`/`append_turn` 走 helper；`config.toml`/`skill`/`export` 从非原子改原子写 |
| 2026-06-18 | P2 步骤 1：`require_session` helper 抽取 | 7 CLI 命令去重，-20 行；新增 `cli.unknown_session` i18n；修 `inspect.py` 宽 except |

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
| 垃圾回收 | `mmi/core/gc.py` | GC 清理（trash/zombie/cold）|
| GC Daemon | `mmi/core/gc_daemon.py` | 后台GC线程（已集成到Manager） |
| Agent调度 | `mmi/agent/` | 意图分类 + 路由 |
| TUI | `mmi/tui_v3.py` | Python 终端界面（已修复：token计数+异常处理） |
| ~~TS TUI~~ | ~~`tui-ts/`~~ | 已删除（TS TUI 已废弃） |
| Provider管理 | `mmi/core/provider_registry.py` | 插件注册 + 多Provider管理 |
| Provider健康 | `mmi/core/provider_health.py` | 故障检测 + 自动切换 |
| LLM审计 | `mmi/core/audit.py` | 双层审计（规则引擎 + LLM） |
| CLI命令 | `mmi/cli/commands/` | 21个子命令（已拆分） |
| IPC通信 | `mmi/core/ipc_server.py` | JSON-RPC 2.0（已补全 create_session） |
| 模型获取 | `mmi/core/model_fetcher.py` | 多级缓存 |

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

Python 3.11 + pytest + ruff + FAISS + SQLite + rich + tiktoken + rapidfuzz + faiss-cpu

### 质量门禁（每次 commit 前必须通过）

```bash
ruff check mmi/                    # 0 errors（pyproject.toml [tool.ruff] 配置已启用）
pytest tests/ -x                   # 全部通过，无 skip
```

| 门禁 | 状态 | 说明 |
|------|------|------|
| Ruff 零告警 | ✅ | `ruff check mmi/` → All checks passed |
| pytest -x | ✅ | 719 passed |
| 原子写 | ✅ | `_atomic_write()` 用 `.tmp` + `os.rename()` |
| 类型标注 | 🔄 | 核心公共函数已标注，剩余 16 处子类实现方法 |

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