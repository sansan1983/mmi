# CLAUDE.md — MMI 多模态智能体系统

> **计划文档已整理**——主目录只留生效文档,历史归档到子目录。
> **新总入口**:`docs/INDEX.md`(完整计划 + 各期任务 + 质量门禁)
> **历史交接**:`docs/handover-history/INDEX.md`

## 项目概述

MMI = 带记忆引擎与多Agent调度的智能体系统，从 C-Trim 演进而来。

## 核心原则

- **UI ≠ 推理** — 界面只负责显示，`mmi/core/` 不依赖任何 UI
- **显示 ≠ 发送** — LLM 上下文是修剪过的视图，原文完整保留
- **不压缩原文** — 只修剪 LLM 视图，不改变 session.md 内容

## 目录结构

```
mmi/
├── core/        # 记忆引擎（session/storage/heat/context/memory/gc等）
├── agent/       # Agent调度层（orchestrator/router/validator等）
├── cli.py       # CLI入口（mmi命令）
└── tools/       # 诊断工具

tui-ts/         # TUI 终端界面（TypeScript + Ink,通过 Python IPC 通信）
```

## 文档结构(`docs/`)

```
docs/
├── INDEX.md                                # 总入口（**先读**）
├── ARCHITECTURE.md                         # 系统架构(生效)
├── RULES.md                                # 工作规范(生效)
├── handover-history/                       # 历次 Round 交接
│   ├── INDEX.md                            # Round 1-3 + 2.5 索引
│   └── round_2*.md / round_3-5.md         # 各轮交接
├── history/                                # 归档(不读)
│   ├── ctrim-ARCHITECTURE.md              # ctrim 旧架构
│   ├── ctrim-PLAN.md / ctrim-SESSION_LOG.md
│   ├── 上文即记忆.md
│   ├── old-plans/                          # 早期 PLAN/IMPROVEMENT-PLAN
│   └── old-design/                         # MMI 多 Agent 早期设计
```

## 常用命令

```bash
# 测试
pytest tests/ -v

# 代码检查
ruff check mmi/

# LLM API（可选）
export MMI_API_KEY=sk-...
export MMI_BASE_URL=https://api.deepseek.com/v1
# 或用 mmi config wizard 交互配置(推荐,见 docs/handover-history/round_2_5.md)
```

## 测试规范

- 测试文件：`tests/test_*.py`，使用 pytest
- 测试使用 `pytest fixtures`（conftest.py）
- Session 文件格式：`{id}.session.md`（YAML frontmatter + Markdown body）

## 关键类型定义

```python
class SessionState(str, Enum):
    ACTIVE = "active"   # heat ≥ 10
    WARM   = "warm"     # heat ≥ 5
    COLD   = "cold"     # 其他
    ZOMBIE = "zombie"   # cold持续90天

# Session ID 使用 ULID（26字符）
```

## 编码规范

- 公共函数：类型标注（参数 + 返回值）
- 类名：`PascalCase`
- 函数：`snake_case`
- 常量：`UPPER_SNAKE`
- 私有：`_leading_underscore`

## 质量门禁

- `ruff check mmi/` 必须 0 error
- `pytest tests/ -x` 全部通过
- 不跳过测试直接提交

## 注意事项

- Session 存储在 `~/.mmi/sessions/{active,trash}/`
- 原子写：先写 `.tmp` 再 `os.replace()`
- 摘要触发条件：≥20轮 或 ≥5000字符 或 >24h且≥5轮
- 改进 1-3 已完成,当前阶段是**三期 Agent 最小可用**(详见 docs/INDEX.md)