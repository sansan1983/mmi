# MMI 开发路线图

> 版本：v2.0 | 制定时间：2026-06-16 | 制定者：GenericAgent

---

## 一、核心原则

| 原则 | 说明 |
|------|------|
| **用户入口优先** | TUI 是用户唯一接触窗口，任何时候不能broken |
| **小步快跑** | 每步 ≤4h，完成后即验收，禁止大合并 |
| **质量门禁** | `pytest tests/ -x` + `ruff check .` 全部通过方可提交 |

---

## 二、现状判断

| 维度 | 状态 | 说明 |
|------|------|------|
| 核心引擎 | ⭐⭐⭐⭐ | FAISS+SQLite FTS5 三层记忆，成熟可用 |
| Agent系统 | ⭐⭐⭐ | Phase3/4完成，Phase5积压20项 |
| Python TUI | ⭐⭐ | Markdown无法渲染，token乱码，14处静默吞异常 |
| TS TUI | ⭐ | IPC未实现，流式未接入 |
| 质量门禁 | ⚠️ | CI有框架但ruff未集成，GC Daemon有框架无集成 |

---

## 三、阶段路线图

### Phase 0｜止血（~6h）

| 编号 | 任务 | 工时 | 验收标准 |
|------|------|------|----------|
| 0.1 | Python TUI Markdown渲染修复 | 2h | `rich.markdown()` 正常渲染，彩色输出 |
| 0.2 | Python TUI token计数修复 | 1h | 准确显示token/字符数，无乱码 |
| 0.3 | Python TUI 异常处理修复 | 1h | 14处静默吞异常改为日志记录+回退 |
| 0.4 | GC Daemon集成到Manager | 1h | Session创建/活跃时自动激活GC，退出时取消 |
| 0.5 | ruff集成到CI | 1h | `.github/workflows/ci.yml` 加 `ruff check .` |

**核心观点**：把 TUI 修复从 P2 提升到 Phase 0，因为它是用户唯一入口。

---

### Phase 1｜架构重构（~12h）

| 编号 | 任务 | 工时 | 验收标准 |
|------|------|------|----------|
| 1.1 | `cli.py` 拆分为 `commands/` | 2h | 所有子命令迁移，逐一测试通过 |
| 1.2 | `manager.py` 职责拆分 | 3h | Session生命周期 / GC调度 / 热力计算 各归其主 |
| 1.3 | `llm.py` 职责拆分 | 3h | LLM调用 / 模型获取 / Provider管理 各归其主 |
| 1.4 | Heat 时间衰减 | 2h | `last_accessed` 超24h后热度按公式衰减 |
| 1.5 | GC 触发阈值配置化 | 1h | `~/.mmi/config.toml` 可配置触发阈值 |
| 1.6 | IPC Server 完善 | 1h | TS TUI `create_session` 正常响应 |

---

### Phase 2｜Phase 5 收尾（~20h）

| 编号 | 任务 | 优先级 | 工时 |
|------|------|--------|------|
| 2.1 | Provider 健康检测 | 🟡 | 2h |
| 2.2 | 自定义 Provider 持久化 | 🟡 | 2h |
| 2.3 | Provider 插件注册 | 🟡 | 3h |
| 2.4 | model_fetcher 本地缓存 | 🟢 | 1h |
| 2.5 | LLM Deep Audit | 🔴 | 3h |
| 2.6 | Skill 统计界面 | 🟢 | 2h |
| 2.7 | 候选提议功能 | 🟢 | 2h |
| 2.8 | 第三方 Tool 集成 | 🟢 | 3h |
| 2.9 | 评估框架 | 🟢 | 2h |

---

### Phase 3｜生态扩展（~25h）

| 编号 | 任务 | 优先级 | 工时 |
|------|------|--------|------|
| 3.1 | TS TUI Web GUI | 🟢 | 8h |
| 3.2 | MCP Server 完善 | 🟡 | 3h |
| 3.3 | Skill 管理界面 | 🟡 | 3h |
| 3.4 | Agent 状态显示 | 🟢 | 2h |
| 3.5 | SlashMenu 完整接入 | 🟢 | 2h |
| 3.6 | FoldBlock/Citation 使用 | 🟢 | 2h |
| 3.7 | 流式输出集成 | 🟡 | 3h |
| 3.8 | 性能压测框架 | 🟢 | 2h |

---

## 四、质量门禁

每阶段验收前必须通过：

| 门禁项 | 标准 |
|--------|------|
| pytest | `pytest tests/ -x` 全部通过 |
| ruff | `ruff check .` 0 error |
| pytest coverage | 不低于上一阶段 |
| 集成测试 | `test_integration.py` 全部通过 |

---

## 五、文档规范

| 目录 | 用途 |
|------|------|
| `docs/ROADMAP/` | 开发路线图、阶段计划 |
| `docs/SPECS/` | 各功能详细规格说明 |
| `docs/TESTS/` | 测试规范、测试策略 |
| `docs/ARCHITECTURE.md` | 系统架构设计（稳定不变） |
| `docs/RULES.md` | 工作规范（稳定不变） |
| `docs/handover-history/` | 阶段交接文档 |
| `docs/handover-history/archive/old-plans/` | 已废弃的旧计划（归档） |

---

## 六、版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-06-12 | 原始 Phase Plan（已归档） |
| v2.0 | 2026-06-16 | 重构版本，Phase 0 新增 TUI 修复为最高优先级 |