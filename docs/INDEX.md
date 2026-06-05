# MMI 项目文档总入口

> 整理时间：2026-06-05
> 维护原则：**主目录只放当前生效文档**,历史归档到子目录

---

## 当前生效文档(放在主目录)

| 文件 | 用途 | 状态 |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 系统架构设计说明书(三层架构 + 数据契约) | ✅ 生效 |
| [RULES.md](RULES.md) | 工作规范(每轮流程 / 质量门禁 / 提交规范) | ✅ 生效 |
| [../ROUND_LOG.md](../ROUND_LOG.md) | 当前轮工作日志(实时更新) | 🔄 进行中 |
| [handover-history/INDEX.md](handover-history/INDEX.md) | 历次 Round 交接索引(8 个 round 文件) | 📚 累积 |

**主项目根**还有:
- [../README.md](../README.md)— 项目简介
- [../CLAUDE.md](../CLAUDE.md)— Claude 工作约定(根级)

---

## 完整执行计划(整合 PLAN.md + IMPROVEMENT-PLAN.md + mmi_modules_deep_analysis.md)

### 当前阶段:三/四期推进中(改进 1-3 已完成,三期起尚未开始)

| 阶段 | 目标 | 状态 |
|---|---|---|
| 零期 | 修复基础链路(P0/P2 修复 + 队列安全) | ✅ 完成(改进 R1) |
| 一期 | 搜索与检索质量(jieba+BM25 + manager.search) | 🟡 部分完成(改 R2 上了 jieba+BM25;manager.search 全文+TF 归一化+rapidfuzz+titler jieba 剩余) |
| 二期 | 性能优化(增量摘要 + 上下文缓存 + 动态窗口 + 截断 + FAISS 池 + 热度) | 🟡 部分完成(改 R2-3 上了 1.4 截断 + 1.5 窗口 + 2.1 增量 + 2.5 池 + 2.6 简化版热度;**2.2 上下文缓存暂缓**;1.6 F1 增量+1.6 F3 池上限+1.6 F4 history 上限+2.7-2.9 summarizer 收尾剩余) |
| **三期** | **Agent 最小可用**(orchestrator + router + validator + 1 个 Agent) | ✅ 完成(R6,3.1–3.12 全清,见 [handover-history/round_6_phase3.md](handover-history/round_6_phase3.md)) |
| 四期 | 架构加固(Pipeline + EventBus + LLM 重试/流式 + 批量接口) | 🟡 R7 进行中(4.1 EventBus + 4.2 Pipeline 容器+6 Step + 4.3 LLM 重试 + 4.5 ChatResult 已合并,4.4 LLM stream + 4.6 批量 + Orchestrator 改走待续;见 [handover-history/round_7_phase4_core.md](handover-history/round_7_phase4_core.md)) |
| 五期 | 周边模块(storage/GC/titler/classifier/config/i18n/paths 改进) | ⬜ 待开始 |
| 六期 | 生态扩展(Skill/Trace 持久化 + Provider 增强 + GUI + MCP) | ⬜ 待开始 |

### 各期完整任务清单(来自 IMPROVEMENT-PLAN + mmi_modules_deep_analysis)

**三期(Agent 最小可用)— 12 项, ~22.5h**:✅ 全部完成(R6)
- 3.1 CoreAgent 接口协议(高,1h)
- 3.2 Router.classify 规则分类器(严重,2h)
- 3.3 Orchestrator.chat 核心逻辑(严重,3h)
- 3.4 Validator 规则引擎 + ValidationResult(高,2h)
- 3.5 CodeReviewAgent 最小可行(严重,3h)
- 3.6 Tools 自动发现(高,2h)
- 3.7 BaseAgent 生命周期钩子(中,2h)
- 3.8 registry 单例加锁(低,0.5h)
- 3.9 CLI: mmi agent list/invoke(中,1h)
- 3.10 DocAgent(中,2h)
- 3.11 modes.py prompt 从 locale 读(低,1h)
- 3.12 CLI: mmi skill list/create(低,1h)

**四期(架构加固)— 10 项, ~21h**:
- 4.1 EventBus(高,3h)
- 4.2 Manager Pipeline(严重,5h)
- 4.3 LLM 重试(高,2h)
- 4.4 LLM stream_chat(高,2h)
- 4.5 ChatResult 结构化(中,1h)
- 4.6 Manager 批量接口(中,1h)
- 4.7 元数据 LRU 缓存(高,3h)
- 4.8 Router 多意图(低,1h)
- 4.9 Router mapping 可配置(低,1h)
- 4.10 validate ValidationResult 结构化(低,1h)

**五期(周边模块)— 20 项, ~29.5h**:
- 1.1 session 字段分组(2h)
- 1.2 storage LRU 句柄(3h) + 读写锁(2h) + schema 校验(1h)
- 1.3 heat 指数衰减(2h) + 连续函数(1h)
- 1.4 GC 后台自动触发(高,2h) + 磁盘感知(1h) + dry-run JSON(1h)
- 1.5 TF 归一化(0.5h) + rapidfuzz(1h) + titler jieba(1h)
- 1.7 titler 永不 trash(0.5h)
- 1.8 classifier 滑动窗口(2h) + 行为模式(2h) + 滑动窗口 UNKNOWN 警告(1h)
- 1.10 config tomllib(1h) + Schema 校验(1h) + 原子写(0.5h)
- 1.13 model_fetcher 本地缓存(1h)
- 1.14 i18n fallback 原文(1h)
- 5.1-5.3 storage 三件套(略)
- 5.7 titler 话题偏移(4h)
- 5.17 session frontmatter mmi_version(1h)

**六期(生态扩展)— 16 项, ~35.5h**:
- 6.1 Skill 持久化(高,2h)
- 6.2 Skill embedding 匹配(高,3h)
- 6.3 Trace 持久化(高,2h)
- 6.5 Provider 健康检测(中,2h)
- 6.6 自定义 Provider 持久化(中,2h)
- 6.7 Provider 插件注册(中,3h)
- 6.8 model_fetcher 本地缓存(低,1h)
- 6.9 LLM Deep Audit(高,3h)
- 6.10-6.16 技能统计 / 候选提议 / 第三方 Tool / Web GUI / MCP / 评估框架 / 性能压测

**合计**:78 项,~143h

---

## 质量门禁(每轮验收前)

| 门禁项 | 标准 |
|---|---|
| pytest | `pytest tests/ -x` 全部通过 |
| ruff | `ruff check .` 0 error |
| 冒烟测试 | 本期验收表中的具体行为测试 |
| 文档 | 同步更新 `ROUND_LOG.md` + 写 `handover-history/round_X_Y.md` |
| 无退化 | 之前各期验收的测试仍然通过 |

---

## 已知暂缓队列(投出比低,后续测试有需要再做)

| 项 | 原因 |
|---|---|
| IMPROVEMENT-PLAN P1-6 上下文增量缓存 | 短对话场景多,长对话收益小;失效 bug 容易出 |
| 五期 1.6 summarizer 同步阻塞改造 | 已有 ThreadPoolExecutor,够用 |
| 五期 1.6 LLM 流式 | UI 体验升级,非核心 |
| 六期 Web GUI / MCP | 等核心能力(三期)做完 |

---

## 历史归档(不读)

| 目录 | 内容 | 何时用 |
|---|---|---|
| [history/](history/) | ctrim 历史(3 文件) + 早期 mmi 设计(6 文件) + 上下文即记忆(1 文件) | 追溯来源 / 考古 |
| [history/old-plans/](history/old-plans/) | 已过期的 PLAN.md / PLAN_COMPLETE.md / IMPROVEMENT-PLAN.md / HANDOVER.md | 对比阶段变更 |
| [history/old-design/](history/old-design/) | MMI 多 Agent 早期设计系列(6 文件) | 参考旧设计 |
| [handover-history/](handover-history/) | 历次 Round 交接文档(8 个 round 文件 + INDEX) | 回顾历史 |

---

## 维护规则(写新文档时)

1. **新加计划文档** → `docs/` 主目录(如新 PLAN / 新 ANALYSIS)
2. **过期文档** → 移到 `docs/history/` 对应子目录,头部加 `[DEPRECATED]` 标签
3. **每轮交接** → `docs/handover-history/round_X_Y.md` + 更新 INDEX
4. **每轮日志** → 项目根 `ROUND_LOG.md`(实时更新)
5. **不在主目录堆**超过 5 个生效文档,避免混乱

---

> 接手者:**先读本文档 → 看 `ROUND_LOG.md` 当前状态 → 翻 `handover-history/INDEX.md` 找历史交接**
