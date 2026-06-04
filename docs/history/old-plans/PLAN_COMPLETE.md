# MMI 完整执行计划

> 版本：v2.0 | 2026-06-04
> 来源：PLAN.md + IMPROVEMENT-PLAN.md + mmi_modules_deep_analysis.md
> 范围：全项目 24 模块覆盖，无遗漏

---

## 总览

| 阶段 | 目标 | 核心交付 | 状态 |
|---|---|---|---|
| 一期 | MVP — 有记忆的单Agent | 会话+上下文+摘要+热度+GC+CLI+TUI | ✅ 完成 |
| 二期 | 向量记忆 | FAISS检索 + 结构化摘要 + 动态重排 | ✅ 完成 |
| **零期** | **修复基础链路** | P0 级修复 + 短会话入库 + 队列安全 | ⬜ 待开始 |
| **一期（新）** | **搜索与检索** | jieba+BM25 + 精确token + manager.search全文 | ⬜ 待开始 |
| **二期（新）** | **性能优化** | 增量摘要 + 上下文缓存 + 动态窗口 + 截断优先 | ⬜ 待开始 |
| **三期（新）** | **Agent最小可用** | orchestrator + router + validator + 1个Agent | ⬜ 待开始 |
| **四期（新）** | **架构加固** | Pipeline + EventBus + LLM完善 + 批量接口 | ⬜ 待开始 |
| **五期（新）** | **周边模块** | storage/GC/titler/classifier/config/i18n/paths 改进 | ⬜ 待开始 |
| **六期（新）** | **生态扩展** | Skill持久化 + Trace持久化 + Provider增强 + GUI + MCP | ⬜ 待开始 |

---

## 零期：修复基础链路

**来源**：IMPROVEMENT-PLAN P0/P2 + 深度分析

| # | 任务 | 来源 | 严重度 | 工作量 | 落点 |
|---|---|---|---|---|---|
| 0.1 | tiktoken 精确 Token 估算 | P0-3 | 🔴 必须 | 1h | `context.py` |
| 0.2 | 每轮记忆入库（短会话打通） | P0-1 | 🔴 必须 | 1h | `summarizer.py` / `manager.py` |
| 0.3 | 后台任务队列化（FIFO） | P2-8 | 🟠 值得修 | 2h | `summarizer.py` |
| 0.4 | Manager 错误分级与优雅降级 | 深度分析 1.11-F4 | 🟡 高 | 1h | `manager.py` |
| 0.5 | LLM 超时控制（httpx timeout=30s） | 深度分析 1.9-F4 | 🟡 高 | 1h | `llm.py` |
| 0.6 | titler 失败不回退到 trash | 深度分析 1.7-F1 | 🟡 高 | 0.5h | `titler.py` |

**验收**：✅ pytest -x 全绿 | ✅ ruff 0 error | ✅ 冒烟测试通过

---

## 一期：搜索与检索质量

| # | 任务 | 来源 | 严重度 | 工作量 | 落点 |
|---|---|---|---|---|---|
| 1.1 | jieba 分词 + BM25 评分 | P0-2 | 🔴 必须 | 3h | `search.py` |
| 1.2 | Manager.search() 改为全文搜索 | 深度分析 1.5-F2 | 🔴 高 | 1h | `manager.py` |
| 1.3 | TF 分数归一化 | 深度分析 1.5-F4 | 🟡 中 | 0.5h | `search.py` |
| 1.4 | RapidFuzz 模糊匹配（可选） | 深度分析 1.5-F1 | 🟠 可选 | 1h | `search.py` |
| 1.5 | titler 中文 jieba 分词关键词提取 | 深度分析 1.7-F5 | 🟡 中 | 1h | `titler.py` |

**验收**：✅ 搜索"项目方案"不召回"案讨" | ✅ manager search 搜正文

---

## 二期：性能优化

| # | 任务 | 来源 | 严重度 | 工作量 | 落点 |
|---|---|---|---|---|---|
| 2.1 | 增量摘要（旧摘要+新turns，100轮全量兜底） | P1-7 | 🟡 应修复 | 4h | `summarizer.py` |
| 2.2 | 上下文增量缓存（LRU + 失效条件） | P1-6 | 🟡 应修复 | 4h | `context.py` / `manager.py` |
| 2.3 | 动态最近轮窗口（按token余量自适应） | P1-5 | 🟡 应修复 | 2h | `context.py` |
| 2.4 | 截断优先级修复（结构化返回+按段截断） | P1-4 | 🟡 应修复 | 3h | `context.py` / `manager.py` |
| 2.5 | FAISS 写入池化（内存批量+异步持久化） | P2-10 | 🟠 值得修 | 4h | `memory.py` |
| 2.6 | 增强热度公式（内容权重+关键词加权） | P2-9 | 🟠 值得修 | 2h | `heat.py` |
| 2.7 | summarizer body 只读一次（合并判断+更新） | 深度分析 1.6-F5 | 🟠 低 | 1h | `summarizer.py` |
| 2.8 | summarizer 线程池加上限（max_workers=2） | 深度分析 1.6-F3 | 🟠 低 | 0.5h | `summarizer.py` |
| 2.9 | summary_history 限制最大条目（保留10条） | 深度分析 1.6-F4 | 🟠 低 | 0.5h | `summarizer.py` |

**验收**：✅ 100轮对话增量摘要节省70%+token | ✅ 连续5轮命中缓存 | ✅ hits>recent截断保留更多hits

---

## 三期：Agent 最小可用系统

| # | 任务 | 来源 | 严重度 | 工作量 | 落点 |
|---|---|---|---|---|---|
| 3.1 | CoreAgent 接口协议 | 深度分析 P2 | 🔴 严重 | 1h | `agent/core_bridge.py` |
| 3.2 | Router.classify() 规则分类器 | 深度分析 2.2-F1 | 🔴 严重 | 2h | `agent/router.py` |
| 3.3 | Orchestrator.chat() 核心逻辑（同步先跑通） | 深度分析 2.1-F1 | 🔴 严重 | 3h | `agent/orchestrator.py` |
| 3.4 | Validator 规则引擎（ValidationResult） | 深度分析 2.8-F3 | 🔴 高 | 2h | `agent/validate.py` |
| 3.5 | CodeReviewAgent（最小可行示例） | 深度分析 2.4-F1 | 🔴 严重 | 3h | `agent/builtin/code_review.py` |
| 3.6 | Tools 自动发现 + 启动时注册 | 深度分析 2.6-F1 | 🟡 高 | 2h | `agent/tools.py` |
| 3.7 | BaseAgent 生命周期钩子 | 深度分析 2.4-F2 | 🟡 中 | 2h | `agent/base.py` |
| 3.8 | registry 单例加锁 | 深度分析 2.3-F1 | 🟠 低 | 0.5h | `agent/registry.py` |
| 3.9 | CLI: mmi agent list/invoke | PLAN 3.11 | 🟡 中 | 1h | `cli.py` |
| 3.10 | DocAgent（文档生成/翻译） | PLAN 3.5 | 🟡 中 | 2h | `agent/builtin/doc.py` |
| 3.11 | modes.py prompt 从 locale 文件读取 | 深度分析 2.5-F1 | 🟠 低 | 1h | `agent/modes.py` |
| 3.12 | CLI: mmi skill list/create | PLAN 3.12 | 🟠 低 | 1h | `cli.py` |

**验收**：✅ 输入意图正确路由到对应Agent | ✅ 输出通过规则引擎校验 | ✅ Agent调用链可追踪

---

## 四期：架构加固

| # | 任务 | 来源 | 严重度 | 工作量 | 落点 |
|---|---|---|---|---|---|
| 4.1 | EventBus 引入（发布订阅 + Hook点） | 深度分析 P3 | 🟡 高 | 3h | `mmi/core/event_bus.py` |
| 4.2 | Manager Pipeline 改造（Hook点 + 异步后台分离） | 深度分析 1.11-F1, P1 | 🔴 严重 | 5h | `manager.py` |
| 4.3 | LLM 重试机制（tenacity 指数退避） | 深度分析 1.9-F2 | 🟡 高 | 2h | `llm.py` |
| 4.4 | LLM stream_chat() 骨架 | 深度分析 1.9-F1 | 🟡 高 | 2h | `llm.py` |
| 4.5 | LLM 返回 ChatResult 结构化（tokens/latency） | 深度分析 1.9-F3 | 🟠 中 | 1h | `llm.py` |
| 4.6 | Manager 批量接口（batch_touch + batch_get_meta） | 深度分析 1.11-F5 | 🟠 中 | 1h | `manager.py` |
| 4.7 | Manager 元数据 LRU 缓存（+ 写穿 index.json） | 深度分析 1.11-F2 | 🟡 高 | 3h | `manager.py` / `storage.py` |
| 4.8 | Router 返回 list[IntentType] + confidence | 深度分析 2.2-F3 | 🟠 低 | 1h | `agent/router.py` |
| 4.9 | Router mapping 可配置化 | 深度分析 2.2-F2 | 🟠 低 | 1h | `agent/router.py` |
| 4.10 | validate 返回 ValidationResult 结构化 | 深度分析 2.8-F3 | 🟠 低 | 1h | `agent/validate.py` |

**验收**：✅ EventBus 事件订阅/发布正常 | ✅ Pipeline Hook 可注入自定义处理 | ✅ Manager 各环节独立可测

---

## 五期：周边模块改进

| # | 任务 | 来源 | 严重度 | 工作量 | 落点 |
|---|---|---|---|---|---|
| 5.1 | storage 文件句柄 LRU 缓存 | 深度分析 1.2-F1 | 🟡 高 | 3h | `storage.py` |
| 5.2 | storage 读写锁（原子性保证） | 深度分析 1.2-F2 | 🟠 中 | 2h | `storage.py` |
| 5.3 | storage write 前 schema 校验 | 深度分析 1.2-F5 | 🟠 低 | 1h | `storage.py` |
| 5.4 | GC 后台自动触发（chat后异步检查） | 深度分析 1.4-F1 | 🔴 高 | 2h | `gc.py` / `manager.py` |
| 5.5 | GC 磁盘空间感知（shutil.disk_usage） | 深度分析 1.4-F3 | 🟠 中 | 1h | `gc.py` |
| 5.6 | GC dry-run 输出 JSON + --from-report | 深度分析 1.4-F5 | 🟠 低 | 1h | `gc.py` |
| 5.7 | titler 话题偏移检测触发重命名 | 深度分析 1.7-F2 | 🟡 中 | 4h | `titler.py` |
| 5.8 | titler 用户覆盖机制（已有CLI） | 深度分析 1.7-F3 | 🟡 低 | 0.5h | 已覆盖（PLAN 3.11 CLI rename） |
| 5.9 | classifier 滑动窗口替代固定轮次 | 深度分析 1.8-F1 | 🟡 高 | 2h | `classifier.py` |
| 5.10 | classifier LLM prompt 输出结构化 JSON | 深度分析 1.8-F2 | 🟠 低 | 1h | `classifier.py` |
| 5.11 | classifier 行为模式分析（重复/单字/模板检测） | 深度分析 1.8-F4 | 🟠 中 | 2h | `classifier.py` |
| 5.12 | classifier UNKNOWN 时 TUI 显示警告 | 深度分析 1.8-F5 | 🟠 低 | 1h | `classifier.py` / `tui/` |
| 5.13 | config 用 tomllib 替代 YAML 解析 | 深度分析 1.10-F1 | 🟠 中 | 1h | `config.py` |
| 5.14 | config 配置 Schema 验证 | 深度分析 1.10-F3 | 🟠 低 | 1h | `config.py` |
| 5.15 | config 原子写入 | 深度分析 1.10-F5 | 🟠 低 | 0.5h | `config.py` |
| 5.16 | i18n 缺翻译 fallback 到英文原文 | 深度分析 1.14-F1 | 🟠 低 | 1h | `i18n.py` |
| 5.17 | session 字段分组（核心元数据 vs 状态机） | 深度分析 1.1-F1 | 🟡 中 | 2h | `session.py` |
| 5.18 | session frontmatter 加 mmi_version 校验 | 深度分析 1.3-F3 | 🟠 低 | 1h | `session.py` |
| 5.19 | heat 指数衰减模型（替代线性公式） | 深度分析 1.3-F1 | 🟡 高 | 2h | `heat.py` |
| 5.20 | heat 连续衰减函数（替代分段粗糙） | 深度分析 1.3-F2 | 🟡 中 | 1h | `heat.py` |

**验收**：✅ storage 高频 IO 不产生额外开销 | ✅ GC 后台自动运行 | ✅ classifier 行为模式检测正常

---

## 六期：生态扩展

| # | 任务 | 来源 | 严重度 | 工作量 | 落点 |
|---|---|---|---|---|---|
| 6.1 | Skill 持久化（~/.mmi/skills.json） | 深度分析 2.7-F2 | 🔴 高 | 2h | `agent/skill.py` |
| 6.2 | Skill embedding 语义匹配 | 深度分析 2.7-F1 | 🟡 高 | 3h | `agent/skill.py` |
| 6.3 | Trace 持久化（JSONL append-only） | 深度分析 2.9-F1 | 🔴 高 | 2h | `agent/trace.py` |
| 6.4 | Trace ULID 唯一 ID | 深度分析 2.9-F3 | 🟠 低 | 0.5h | `agent/trace.py` |
| 6.5 | Provider 健康检测 + 自动降级 | 深度分析 1.12-F3 | 🟡 中 | 2h | `providers.py` |
| 6.6 | 自定义 Provider 持久化（api_key/base_url） | 深度分析 1.12-F2 | 🟠 中 | 2h | `providers.py` |
| 6.7 | Provider 插件注册制（动态扫描扩展） | 深度分析 1.12-F1 | 🟠 中 | 3h | `providers.py` |
| 6.8 | model_fetcher 本地缓存（TTL 24h） | 深度分析 1.13-F1 | 🟠 低 | 1h | `model_fetcher.py` |
| 6.9 | LLM Deep Audit 实现 | 深度分析 2.8-F1 | 🟡 高 | 3h | `validate.py` |
| 6.10 | 技能统计看板（使用率/采纳率） | PLAN 4.1 | 🟠 低 | 2h | `agent/skill.py` |
| 6.11 | 候选技能提议（LLM提议+人工确认） | PLAN 4.2 | 🟠 低 | 3h | `agent/skill.py` |
| 6.12 | 第三方 Tool 注册 | PLAN 4.5 | 🟠 低 | 3h | `agent/tools.py` |
| 6.13 | Web GUI 骨架（Vue3 单页对话） | PLAN 4.6 | 🟠 低 | 5h | `gui/` |
| 6.14 | MCP 协议集成 | PLAN 4.7 | 🟠 低 | 4h | `mcp/` |
| 6.15 | 评估框架（100个典型场景自动化评估） | PLAN 4.4 | 🟠 低 | 4h | `eval/` |
| 6.16 | 性能压测 + 调优 | PLAN 4.8 | 🟠 低 | 3h | `benchmark/` |

**验收**：✅ Skill 重启后不丢失 | ✅ Trace 历史可查 | ✅ Provider 失败自动降级

---

## 工作量汇总

| 阶段 | 任务数 | 总工作量 | 核心任务 |
|---|---|---|---|
| 零期 | 6 | ~7h | P0-1/3, P2-8, titler, LLM超时 |
| 一期 | 5 | ~6.5h | jieba+BM25, manager.search全文 |
| 二期 | 9 | ~21h | 增量摘要, 上下文缓存, 动态窗口 |
| 三期 | 12 | ~22.5h | orchestrator, router, validator, CodeReviewAgent |
| 四期 | 10 | ~21h | Pipeline, EventBus, LLM重试/流式 |
| 五期 | 20 | ~29.5h | storage缓存, GC后台, classifier, heat指数衰减 |
| 六期 | 16 | ~35.5h | Skill持久化, Trace持久化, Provider增强, GUI/MCP |
| **合计** | **78** | **~143h** | |

---

## 质量门禁

每期验收前必须满足：

| 门禁项 | 标准 |
|---|---|
| pytest | `pytest tests/ -x` 全部通过 |
| ruff | `ruff check .` 0 error |
| 冒烟测试 | 本期验收表中的具体行为测试 |
| 文档 | 同步更新 `ROUND_LOG.md` |
| 无退化 | 之前各期验收的测试仍然通过 |

---

## 关键依赖关系

```
零期
  ├─ P0-3(tiktoken) ──────┐
  ├─ P0-1(短会话入库) ─────┤
  └─ P2-8(任务队列) ───────┤
                           ▼
  一期 ───────────────────────────────────────▶ 二期
  (搜索质量)                                  (性能优化)
  ├─ 1.1 jieba+BM25 ───┐                      └─ 2.1 增量摘要 ──┐
  └─ 1.2 manager搜索 ──┘                           ├─ 2.5 FAISS池化  │
                                                    └─ 2.6 热度加权   │
                                                       ▼
  三期 ───────────────────────────────────────▶ 四期 ──────────▶ 五期
  (Agent最小可用)                               (架构加固)        (周边模块)
  ├─ 3.1 CoreAgent接口 ──┐                      ├─ 4.1 EventBus ──┼──▶ 六期
  ├─ 3.2 router ────────┤                      ├─ 4.2 Pipeline ───┘
  ├─ 3.3 orchestrator ──┤                      └─ 4.3 LLM重试 ─────┘
  ├─ 3.4 validator ────┤
  └─ 3.5 CodeReviewAgent┘
```

---

## 风险与对策

| 风险 | 概率 | 对策 |
|---|---|---|
| tiktoken 降级 | 低 | 保留中英文区分估算 fallback |
| jieba 分词效果差 | 低 | 保留 2-gram fallback |
| 上下文缓存一致性问题 | 中 | 严格失效条件 + 单元测试 |
| 增量摘要漂移 | 中 | 每 100 轮强制全量重建 |
| 任务队列阻塞主流程 | 低 | ThreadPoolExecutor 异步提交 |
| Pipeline 改造引入回归 | 中 | 每步独立测试后合入 |
| classifier 滑动窗口误判 | 低 | 保留 LLM 二次确认兜底 |
| storage LRU 缓存内存泄漏 | 低 | weakref 保护 + 内存上限 |

---

> 参考：PLAN.md（历史计划）、IMPROVEMENT-PLAN.md（P0-P2 级修复）、mmi_modules_deep_analysis.md（全项目审计）
