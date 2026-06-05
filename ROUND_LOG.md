# 工作日志 — 四期 架构加固 R7(全部收口)
> Phase: 四期 | Round: 7
> 标题:R7 核心 6 项 — 全部完成并合并
> 开始:2026-06-05
> 状态:✅ 全部收口

---

## 上轮交接摘要
- 三期 R6 完成:Agent 最小可用,3.1-3.12 全清
- 测试 466/466,ruff 44 errors(baseline)

## 本轮完成(R7 6 项全部落地)
- [x] 4.3 LLM 重试 + 4.5 ChatResult(Task 1)
- [x] 4.1 EventBus(Task 2)
- [x] 4.2 Pipeline 容器 + 6 内建 Step(Task 3)
- [x] 4.2 Orchestrator 改走 Pipeline(Task 4) — `chat()` → PipelineCtx+pipeline.run(),`chat_legacy()` 兼容
- [x] 4.4 LLM stream_chat 同步迭代器(Task 5) — 默认走 chat 拆单 chunk,OpenAI override 走 stream=True
- [x] 4.6 Manager 批量接口(Task 6) — batch_chat / batch_touch / batch_get_meta + get_session_meta
- [x] `ValidationResult.reasons` → `issues` 字段迁移(原 R8 4.10,提前到本轮减少后续改动)
- [x] `LLM = LLMProvider` 向后兼容别名
- [x] ruff 从 44 → 0(顺手清完 baseline 跨期遗留)
- [x] R7 完整收口文档 + 索引更新

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 上午 | spec + R7 plan + self-review | ✅ | 2 个 commit,落在 master |
| 中午 | worktree 建 r7/phase4-cont | ✅ | /home/ubuntu/mmi-r7c |
| 中午 | Task 1 subagent | ✅ | 1 个 fix subagent(ValidationResult 字段冲突)后通过,475 passed |
| 下午 | Task 2 subagent | ✅ | 482 passed |
| 下午 | Task 3 subagent | ✅ | 5 处 plan 偏差已审,489 passed |
| 下午 | 用户决定先合并暂停 | ✅ | ff-merge 3 commit 到 master,489 passed 在 master 验证 |
| 晚上 | Task 4/5/6 + ruff 清零 + 文档升级 | ✅ | 506/506 passed,ruff 0,本文档写完 |

## 测试结果
- master 状态:**506 passed**(466 baseline + 40 net new)
  - Task 1: +9(chat_with_retry 6 + ChatResult 3)
  - Task 2: +7(EventBus)
  - Task 3: +7(Pipeline 4 + 内建 Step 3)
  - Task 4: +9(Orchestrator 改走 Pipeline)
  - Task 5: +4(LLM stream_chat)
  - Task 6: +4(Manager batch)
- ruff:**0 error**(从 baseline 44 → 0,顺手清完)
- 全量:506 / 506(排除 1 个 ctrim 时代 test_cli.py 硬编码路径)

## 改动文件清单(R7 全 6 项总和)
### 核心代码
| 文件 | 操作 | 关键点 |
|---|---|---|
| mmi/agent/event_bus.py | 新 | `Event` 冻结 dataclass + `EventBus` 同步派发 + 异常隔离 + 单例 |
| mmi/agent/pipeline.py | 新 | `PipelineCtx` + `PipelineStep` Protocol + `Pipeline` 容器;`degrade` = 失败重试 1 次;`latency_ms` 实际测量 |
| mmi/agent/steps.py | 新 | 6 个内建 Step:Classify / Route / Instantiate / Run / Validate / Persist |
| mmi/agent/result.py | 新 | `ChatResult` dataclass + `to_dict()` |
| mmi/agent/orchestrator.py | 改 | `chat()` 改走 Pipeline,加 `chat_legacy()` 兼容 phase 3 |
| mmi/agent/registry.py | 改 | 加 `get()` 实例化方法 + `set_default_llm/skill_library()` 注入 |
| mmi/agent/validate.py | 改 | `reasons: list[str]` → `issues: tuple[ValidationIssue, ...]` |
| mmi/agent/__init__.py | 改 | 暴露新符号 |
| mmi/core/exceptions.py | 新 | `LLMRetryExhausted` + `StreamError` |
| mmi/core/llm.py | 改 | `chat_with_retry`(指数退避)+ `stream_chat` 同步迭代器 + `LLM = LLMProvider` 别名 |
| mmi/core/manager.py | 改 | `batch_chat/touch/get_meta` + `get_session_meta` |
| mmi/cli.py | 改 | `cmd_agent` 走 `chat_legacy` |
| mmi/tui/screens/chat.py | 改 | `stream_chat` 同步迭代器 + `asyncio.to_thread` 收齐 |

### 测试
| 文件 | 操作 | 净增 |
|---|---|---|
| test_chat_result.py | 新 | 3 |
| test_llm_retry.py | 新 | 6 |
| test_event_bus.py | 新 | 7 |
| test_pipeline.py | 新 | 7 |
| test_llm_stream.py | 新 | 4 |
| test_orchestrator_phase4.py | 新 | 9 |
| test_batch_chat.py | 新 | 4 |
| test_agent_phase3.py | 改 | 2 处 reasons→issues,chat→chat_legacy |
| test_llm.py | 改 | 3 个 stream 测试同步化 |
| conftest.py | 改 | `ScriptedLLM.stream_chat` 同步化 |

### 文档
| 文件 | 操作 | 关键点 |
|---|---|---|
| docs/handover-history/round_7_phase4_core.md | 升级 | 部分收口 → 全部收口(完整版) |
| docs/handover-history/INDEX.md | 改 | round_7 行扩到 4.1/4.2/4.3/4.4/4.5/4.6 |
| docs/INDEX.md | 改 | 四期状态 🟡 → ✅(506/506,ruff 0) |
| ROUND_LOG.md | 改 | 本文件 |

## 关键设计决策(摘要)
- LLM 重试自写(零依赖、可控、好测)
- `ValidationResult.reasons` → `issues` 提前到 R7(R8 4.10 不再重命名字段)
- `class LLM` → `LLMProvider` + `LLM = LLMProvider` 别名(零 blast radius)
- Pipeline `degrade` 策略语义 = 失败重试 1 次
- `ChatResult.intent` 在 `chat_with_retry` 里是 `None`,由 Pipeline.RunStep 在装配时填
- `stream_chat` 改同步生成器(放弃 async generator)— SDK 同步 + 改动面小 + 测试简单
- `Orchestrator.chat_legacy()` 兼容 phase 3 `chat() -> str` 签名,内部调 `chat(...).reply`
- `AgentRegistry.get()` 兜底:常见签名先 try,失败 catch `TypeError` → 无参 + setattr
- ruff 从 44 → 0 顺手清完 baseline 跨期遗留

## 遗留问题(R8 起点)
- Tracer 未接 EventBus(目前只 `tracer.record()`,不 publish 事件)— R8 4.7
- `ValidationResult.issues[i]` 内部只有 `message`,没 `severity/span/rule_id` — R8 4.10
- `StreamError` 抛出后无 retry 包装(stream 路径失败 = 全段重试)— R8 4.8
- `batch_chat` 顺序执行,无并发选项 — R8
- TUI `stream_chat` 收齐再渲染,不是 chunk-by-chunk 增量 — R8
- `Orchestrator.chat_legacy()` 与 `chat()` 双接口并存 — R8 视情况移除
- `_FakeLLM` / `ScriptedLLM` 跨多个测试文件,未抽公共 `tests/_fakes.py` — R8
- `tests/test_cli.py` 仍硬编码 ctrim 旧路径(三期就发现)— 留待归档

## 下次续做
R8 起点(4.7–4.10 + 跨期遗留 1-8):
- 4.7 Tracer → EventBus 全链路
- 4.8 LLM 高级重试 + 流式退避
- 4.9 验证 + 持久化拆 hook(允许外部插入审计)
- 4.10 `ValidationResult.issues[i]` 内部结构扩展(`severity` + `span` + `rule_id`)

预计 R8 净工时:~6h。

---

> 接手者:`git checkout master` 即可;`pytest tests/ --ignore=tests/test_cli.py -q` 看到 506 passed + ruff 0 即可接 R8。
