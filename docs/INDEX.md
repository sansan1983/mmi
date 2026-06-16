# MMI 项目文档总入口

> 整理时间：2026-06-16 | 版本：v2.0

---

## 当前生效文档

| 文件 | 用途 | 状态 |
|------|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统架构设计说明书（三层架构 + 数据契约） | ✅ 生效 |
| [RULES.md](RULES.md) | 工作规范（每轮流程 / 质量门禁 / 提交规范） | ✅ 生效 |
| [ROADMAP/DEVELOPMENT_ROADMAP.md](ROADMAP/DEVELOPMENT_ROADMAP.md) | **总开发路线图**（v2.0，2026-06-16） | ✅ 生效 |

---

## 目录结构说明

```
docs/
├── ARCHITECTURE.md         系统架构（稳定）
├── RULES.md                工作规范（稳定）
├── ROADMAP/                开发路线图
│   └── DEVELOPMENT_ROADMAP.md   总路线图 v2.0
├── SPECS/                  功能详细规格说明
├── TESTS/                  测试规范与策略
└── handover-history/       阶段交接文档
    └── archive/
        └── old-plans/     已废弃的旧计划（勿用）
```

---

## 当前开发阶段

**Phase 0｜止血**（2026-06-16 起）

优先级最高任务：Python TUI 渲染/计数/异常修复 + GC Daemon 集成

详见 [ROADMAP/DEVELOPMENT_ROADMAP.md](ROADMAP/DEVELOPMENT_ROADMAP.md)

---

## 快速链接

- **README.md**（项目主说明）：`../README.md`
- **CLAUDE.md**（开发者指南）：`../CLAUDE.md`
- **GitHub**：https://github.com/sansan1983/mmi
- **Issue Tracker**：https://github.com/sansan1983/mmi/issues