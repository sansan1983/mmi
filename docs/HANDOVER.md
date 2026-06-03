# 明日续接 HANDOVER

> 日期：2026-06-03  
> 状态：✅ 一期 MVP 完成，进入二期准备  
> 写给：明天的开发者 / Claude / 接手者

---

## 1. 一句话定位

**MMI = Multimodal Intelligence（多模态智能体）**。从 C-Trim（ctrim v0.5.0a5）迁移而来，在会话记忆、上下文修剪、生命周期管理之上新增多Agent调度、技能管理、输出校验能力。

---

## 2. 关键信息速查

| 项目 | 值 |
|---|---|
| 仓库 | `https://github.com/sansan1983/mmi.git` |
| 本地路径 | `F:/AI data/omp/mmi/` |
| 当前版本 | v0.1.0 |
| 当前分支 | master |
| Python | 3.12（要求 ≥3.11） |
| 测试 | 302/312 核心通过，10个遗留 |
| 包名/命令 | `mmi` |
| 存储位置 | `~/.mmi/sessions/{active,trash}/` |
| 配置文件 | `~/.mmi/config.toml` |

---

## 3. 今天完成了什么

### 3.1 ctrim → MMI 全量迁移

- ✅ 所有核心模块从 `ctrim.core` 迁移到 `mmi.core`，import 路径全部更新
- ✅ `loader.py` 重命名为 `context.py`
- ✅ 所有 `~/.ctrim` → `~/.mmi`，`CTRIM_HOME` → `MMI_HOME`
- ✅ CLI 命令从 `ctrim` 改为 `mmi`（15+ 子命令保留）
- ✅ TUI 完整迁移（import 路径更新）
- ✅ 351 个测试迁移，302 个通过
- ✅ i18n 双语基线迁移（locales 路径修正）

### 3.2 新建 Agent 调度层

- ✅ `mmi/agent/` 完整骨架：orchestrator / router / registry / base / modes / validate / skill / tools / trace
- ✅ 3 个内置 Agent 骨架：CodeReviewAgent / DocAgent / DataAgent
- ✅ 所有方法均为 `NotImplementedError`，待实现

### 3.3 新建记忆模块

- ✅ `mmi/core/memory.py` 骨架：store_memory / search_semantic / rerank / build_structured_summary

### 3.4 文档

- ✅ `ARCHITECTURE.md`（总设计说明）
- ✅ `PLAN.md`（四期分期计划）
- ✅ `RULES.md`（工作规范 v2.0）
- ✅ `README.md`（快速开始）
- ✅ `MMI统一架构设计.md`（全面架构，在 MMI Agent 目录）

### 3.5 首轮提交

- ✅ `git init` + 首轮 commit（118 files, 14,017 lines）
- ✅ push 到 `https://github.com/sansan1983/mmi.git`，master 分支

---

## 4. 当前还没做的事（按优先级）

### P0 — 必须修

| # | 任务 | 详情 |
|---|---|---|
| 1 | 修复 SessionMeta 遗留测试 | 10个失败，根因：`from_dict()` 把时间字符串解析为 datetime，但个别测试和代码依赖字符串类型。涉及：test_session.py roundtrip、test_storage.py 时间比较、test_gc.py 垃圾回收 |
| 2 | 添加 `cold_since_parsed` 属性 | `gc.py:237` 引用了 SessionMeta 上不存在的 `cold_since_parsed` 属性 |
| 3 | 清理 `__pycache__/` | 加入 `.gitignore`，`git rm --cached` 已提交的 pyc 文件 |

### P1 — 二期准备

| # | 任务 | 详情 |
|---|---|---|
| 4 | 安装 FAISS 环境 | `pip install faiss-cpu sentence-transformers` |
| 5 | 实现 memory.store_memory() | 对话结束 → embedding → FAISS + SQLite |
| 6 | 实现 memory.search_semantic() | 用户输入 → embedding → FAISS top-20 |
| 7 | 实现 memory.rerank() | LLM 动态重排 top-20 → top-3 |
| 8 | 集成到 context.py | build_context() 调用 memory 注入历史记忆 |

### P2 — 后续

| # | 任务 | 详情 |
|---|---|---|
| 9 | 实现 orchestrator.py | 完整 chat() 流程 |
| 10 | 实现 router.py | 意图分类 + 路由 |
| 11 | 实现 validate.py 规则引擎 | 敏感词/格式/空输出校验 |
| 12 | 实现 skill.py | 技能库 CRUD |

---

## 5. 明天要做的具体动作

```bash
# 1. 拉最新代码
cd "F:/AI data/omp/mmi"
git pull

# 2. 跑测试看当前状态
python -m pytest tests/ -q --tb=line -k "not fuzzy" --ignore=tests/test_cli.py --ignore=tests/test_tui_list.py

# 3. 确认 302 passed / 10 failed，然后从 P0 #1 开始修

# 4. 安装 mmi 包（可选）
pip install -e ".[test]"
```

---

## 6. 重要约束

- 📜 **ARCHITECTURE.md 是开发宪法**，任何对数据格式/核心API/原则的修改必须先改文档再改代码
- 🚫 **i18n 是基线不是扩展**，所有用户可见字符串必须 `t("key")` 包裹
- 🚫 **不压缩原文**，只修剪 LLM 视图
- 🚫 **不把所有历史塞给 LLM**，永远只发：摘要 + 记忆 + 最近N轮
- 🔧 **核心可独立运行**，`mmi/core/` 不依赖 UI
- 🚫 **不做全自动技能入库**，技能只人工创建
- 🔄 **每轮完工必须写交接文档**，格式见 RULES.md §四

---

## 7. 关键文件速查

| 想了解 | 读这个 |
|---|---|
| 整体设计 | `ARCHITECTURE.md` |
| 分期计划 | `PLAN.md` |
| 工作规范 | `RULES.md` |
| Agent层设计 | `MMI Agent/MMI统一架构设计.md` |
| 融合分析 | `MMI Agent/ctrim源码分析+MMI融合方案报告.md` |
| session数据格式 | `ARCHITECTURE.md` §4.1 |
| 热度状态机 | `ARCHITECTURE.md` §4.3 |
| 上下文构建 | `mmi/core/context.py` |
| 摘要触发策略 | `mmi/core/summarizer.py` |
| i18n怎么用 | `mmi/core/i18n.py` 顶部 docstring |
| CLI命令列表 | `mmi/cli.py` build_parser() |
| 配置格式 | `~/.mmi/config.toml` 或 `ARCHITECTURE.md` §7 |

---

## 8. 已确认的技术决策（不要重新讨论）

| 决策 | 结论 |
|---|---|
| 包名/命令 | `mmi` |
| 产品名 | MMI（Multimodal Intelligence） |
| 存储格式 | Markdown + YAML frontmatter, `.session.md` |
| 存储位置 | `~/.mmi/sessions/{active,trash}/` |
| LLM协议 | OpenAI 兼容 |
| CLI框架 | typer |
| TUI框架 | textual |
| 文件锁 | portalocker |
| i18n | 自写 `t()`, locales 在 `mmi/core/locales/` |
| 向量DB(v1) | FAISS |

---

## 9. 遗留问题

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | SessionMeta.from_dict() 返回 datetime 而非字符串 | test_session roundtrip、test_storage 时间比较、test_gc 失败 | 统一 from_dict 返回字符串，保持与原 ctrim 一致 |
| 2 | SessionMeta 缺 `cold_since_parsed` 属性 | gc.py zombies 处理报错 | 添加 property 返回 parsed datetime |
| 3 | `__pycache__/` 已提交 | 仓库不干净 | 加 .gitignore + git rm --cached |

---

## 10. 下轮计划

**下一轮：二期 P0 — 修复遗留 + 环境准备**

1. 修复 10 个 SessionMeta 测试（P0 #1-2）
2. 清理 __pycache__（P0 #3）
3. 安装 FAISS 环境（P1 #4）
4. 跑全量测试确认 312/312 通过

之后进入二期 P1：实现 memory.py 向量检索。

---

> **给接手者：先跑 §5 的命令，看测试状态，然后从 P0 #1 开始修。不要重读所有源码，按 §7 速查表按需读。**
