# 工作日志 — 四期 架构加固 R8(全部收口)
> Phase: 四期 | Round: 8
> 标题:R8 — 4.7/4.8/4.9/4.10 + 跨期 #7/#8 全部收口
> 开始:2026-06-05
> 状态:✅ 全部收口

---

## 上轮交接摘要(R7 末)
- 四期 R7 全部完成:4.1/4.2/4.3/4.4/4.5/4.6
- 测试 506/506,ruff 0
- R8 起点 4 项(4.7/4.8/4.9/4.10)+ 跨期 #7/#8

## 本轮完成(R8 全 6 项)
- [x] 4.10 ValidationIssue 4 字段 + ValidationRule.severity + frozen=True(Task 1)
- [x] 4.7 Tracer → EventBus — `Tracer(event_bus=bus)` + `trace.recorded` 事件(Task 2)
- [x] 4.9 Validate / Persist 拆 hook — `validation.complete` / `validation.issue` / `persist.complete` 事件(Task 2)
- [x] 4.8 `stream_chat_with_retry` 流式重试 — pre-yield 可重试 / mid-stream 转 StreamError(Task 3)
- [x] 跨期 #7 `chat_legacy()` 评估 — 决议保留(理由见 round_8_phase4_fb.md 第 4 节决策 1)
- [x] 跨期 #8 `tests/_fakes.py` 抽公共(ScriptedLLM / KeywordStubLLM / MinimalStubLLM) + conftest 重构
- [x] ruff 跨期 44 error → 0(13 个测试文件,auto-fix + 手动清)
- [x] R8 收口文档 + 索引更新 + round_7 第 7 节标 ✅

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 晚上 | 建 worktree r8/phase4-fb | ✅ | /home/ubuntu/mmi-r8 |
| 晚上 | Task 1: 4.10 ValidationIssue | ✅ | 12 个测试,fd72c69 |
| 晚上 | Task 2: 4.7+4.9 EventBus 化 | ✅ | 10 个测试,9e96323 |
| 晚上 | Task 3: 4.8 流式重试 | ✅ | 11 个测试,d0afd2f |
| 晚上 | Task 4: chat_legacy 评估 + _fakes 抽取 + ruff 清 0 | ✅ | 0 新增测试,2 个 commit(d1266a4 / 806293f) |
| 晚上 | 收口文档 + 索引 + merge + push + 清理 | ✅ | 本文档 |

## 测试结果
- master 状态:**539 passed**(506 R7 末 + 33 net new)
  - Task 1: +12(ValidationIssue 4 字段)
  - Task 2: +10(Tracer→EventBus + Validate/Persist hooks)
  - Task 3: +11(stream_chat_with_retry)
  - Task 4: +0(纯重构 + ruff 清)
- ruff:**0 error**(维持 0)

## 改动文件清单(R8 全 5 个功能 commit)
### 核心代码
| 文件 | 操作 | 关键点 |
|---|---|---|
| mmi/agent/validate.py | 改 | ValidationIssue 4 字段 frozen=True; ValidationRule.severity; _check_rules 重写填字段 |
| mmi/agent/trace.py | 改 | Tracer(event_bus=...) 可选注入; record() 后 publish trace.recorded; reset_instance() |
| mmi/agent/orchestrator.py | 改 | 默认 Tracer(event_bus=self.bus); default_steps 透传 bus |
| mmi/agent/steps.py | 改 | ValidateStep / PersistStep 加 event_bus; 3 个新事件; default_steps 透传 |
| mmi/core/llm.py | 改 | stream_chat_with_retry — pre-yield 可重试 / mid-stream 转 StreamError |

### 测试
| 文件 | 操作 | 净增 |
|---|---|---|
| tests/test_validate.py | 新 | 12 |
| tests/test_event_bus_hooks.py | 新 | 10 |
| tests/test_llm_stream_retry.py | 新 | 11 |
| tests/_fakes.py | 新 | 0(共享 3 个 LLM 假实现) |
| tests/conftest.py | 改 | 删 ScriptedLLM 类(改 import 自 _fakes) |
| tests/test_event_bus_hooks.py | 改 | 用 MinimalStubLLM 替换本地 _StubLLM |
| 13 个测试文件 | 改 | ruff --fix 清 44 error |

### 文档
| 文件 | 操作 | 关键点 |
|---|---|---|
| docs/handover-history/round_8_phase4_fb.md | 新 | 完整 R8 交接文档 |
| docs/handover-history/INDEX.md | 改 | +round_8 行 |
| docs/INDEX.md | 改 | 四期 4.7/4.8/4.9/4.10 状态 ⬜ → 🟢(本轮 4 项); 四期整段 R7 → R8 |
| docs/handover-history/round_7_phase4_core.md | 改 | 第 7 节 R8 起点全 ✅ |
| ROUND_LOG.md | 改 | 切到 Round 8(本文件) |

## 关键设计决策(摘要)
- chat_legacy 保留(双接口并存,fallback 语义有价值)
- ValidationIssue frozen=True(可哈希,可放进 EventBus payload)
- stream_chat_with_retry 用 consumed_count 状态机区分 pre/mid-stream
- EventBus 透传路径 Orchestrator → Pipeline → Steps(统一入口)
- tests/_fakes.py 抽 3 个共享,不强求合并(各 stub 用途窄)
- ruff 跨期 44 error → 0(顺手清)

## 遗留问题(五期/R8.5 起点)
- TUI 真流式 + 美化 → 后期单独 round
- Manager.batch_chat 并发 → 后期
- test_cli.py ctrim 硬编码 → 留待归档
- ValidationIssue.span UI 还没接 → 后期
- validation.issue 大量 issue 时 EventBus 刷屏 → 加节流

## 下次续做
- **五期(20 项, ~29.5h)**:周边模块(session 字段分组 / storage LRU+锁+schema / heat 衰减 / GC 后台 / classifier 滑动 / config tomllib / i18n fallback / model_fetcher / 等等)
- 或:先做"独立小 round"清遗留(#4 test_cli 归档 + 后期单独 round 处理 TUI)
- 建议:先做独立小 round(test_cli 归档 + TUI 美化,各 1-2h),再做五期
- 或直接进五期

---

> 接手者:`git checkout master` 即可;`pytest tests/ --ignore=tests/test_cli.py -q` 看到 539 passed + ruff 0 即可接五期。
