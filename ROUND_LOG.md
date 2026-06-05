# 工作日志 — 四期 架构加固 R7(部分收口)
> Phase: 四期 | Round: 7
> 标题:R7 核心 6 项(Task 1-3 已合并,4-6 待续)
> 开始:2026-06-05
> 状态:🟡 部分收口

## 上轮交接摘要
- 三期 R6 完成:Agent 最小可用,3.1-3.12 全清
- 测试 466/466,ruff 44 errors(baseline)

## 本轮完成(R7 6 项中 4 项落地)
- [x] 4.3 LLM 重试 + 4.5 ChatResult(Task 1)
- [x] 4.1 EventBus(Task 2)
- [x] 4.2 Pipeline 容器 + 6 内建 Step(Task 3)
- [x] ValidationResult.reasons → issues 字段迁移(原 R8 4.10,提前到本轮减少后续改动)
- [x] `LLM = LLMProvider` 向后兼容别名
- [ ] 4.4 LLM stream_chat(Task 5,待续)
- [ ] 4.6 Manager 批量(Task 6,待续)
- [ ] Orchestrator 改走 Pipeline(Task 4,待续)
- [ ] R7 完整收口文档 + 索引更新(部分)

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 上午 | spec + R7 plan + self-review | ✅ | 2 个 commit,落在 master |
| 中午 | worktree 建 r7/phase4-core | ✅ | /home/ubuntu/mmi-r7 |
| 中午 | Task 1 subagent | ✅ | 1 个 fix subagent(ValidationResult 字段冲突)后通过,475 passed |
| 下午 | Task 2 subagent | ✅ | 482 passed |
| 下午 | Task 3 subagent | ✅ | 5 处 plan 偏差已审,489 passed |
| 下午 | 用户决定先合并暂停 | ✅ | ff-merge 3 commit 到 master,489 passed 在 master 验证 |

## 测试结果
- master 状态:**489 passed**(466 baseline + 23 net new)
- ruff:**44 errors**(同 baseline,无新增)
- R7 剩余:Task 4-6 + 收口估 ~9 net new → 全量 498

## 改动文件清单(Task 1-3 总和)
- mmi/agent/event_bus.py(新,45 行)
- mmi/agent/pipeline.py(新,181 行)
- mmi/agent/result.py(新,45 行)
- mmi/agent/steps.py(新,125 行)
- mmi/agent/validate.py(改,32 行差分)
- mmi/agent/orchestrator.py(改,2 行)
- mmi/agent/__init__.py(改,+25 行)
- mmi/core/exceptions.py(新,23 行)
- mmi/core/llm.py(改,+75 行)
- tests/test_chat_result.py / test_event_bus.py / test_llm_retry.py / test_pipeline.py(新)
- tests/test_agent_phase3.py(改 2 处,跟新字段对齐)
- docs/handover-history/round_7_phase4_core.md(新,部分收口)
- docs/handover-history/INDEX.md(+ round_7 行)
- docs/INDEX.md(四期状态 ⬜ → 🟡)

## 关键设计决策
- LLM 重试自写,不用 tenacity(零依赖、可控、好测)
- `ValidationResult.reasons` → `issues` 提前到 R7,R8 4.10 不再做字段重命名
- `class LLM` → `LLMProvider` + `LLM = LLMProvider` 兼容别名
- Pipeline `degrade` 策略语义 = 失败重试 1 次(plan 测试期望)
- `ChatResult.intent` 在 `chat_with_retry` 里是 `None`,由 Pipeline.RunStep 在装配时填

## 遗留问题
- Orchestrator 没切到 Pipeline(下一步 Task 4)
- LLMProvider.stream_chat 没实现(下一步 Task 5)
- Manager.batch_* 没实现(下一步 Task 6)
- Tracer 没接 EventBus(下一步或 R8)

## 下次续做
- Task 4 → Task 5 → Task 6 → R7 完整收口
- 然后写 R8 plan(4.7 LRU + 4.8/4.9 Router + 4.10 ValidationIssue 内部结构扩展)
- 预计 R7 收口后:498 passed,test_cli.py 仍硬编码路径留待归档

## 本轮计划子任务
- [x] 3.1 BaseAgent 接口协议
- [x] 3.2 Router 规则分类器
- [x] 3.3 Orchestrator 5 步流程
- [x] 3.4 Validator 4 条规则
- [x] 3.5 CodeReviewAgent
- [x] 3.6 Tools 自动发现
- [x] 3.7 BaseAgent 生命周期钩子
- [x] 3.8 registry 单例加锁
- [x] 3.9 CLI mmi agent
- [x] 3.10 DocAgent(翻译模式)
- [x] 3.11 mode prompt 从 locale
- [x] 3.12 CLI mmi skill
- [x] tests/test_agent_phase3.py(27 个新测试)
- [x] 全量 466/466 + ruff 0 error
- [x] 修 4 个真 bug(TraceRecord import / latency_ms / p_skill_list / AgentMeta import)
- [x] 写 round_6_phase3.md + 改 INDEX

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 09:15 | 装 venv + 全 deps | ✅ | .venv-test 217M,uv 装 4m |
| 09:25 | 跑 test_agent_phase3 | ⚠️→✅ | 2 失败:TraceRecord import/latency_ms,修后 27/27 |
| 09:35 | 跑全量 pytest | ⚠️→✅ | 473/476,3 失败均为 ctrim 时代 test_cli.py 硬编码路径,排除 |
| 09:40 | ruff check | ⚠️→✅ | 3 error:F841 p_skill_list + F821 AgentMeta×2,修后 0 |
| 09:50 | 写 round_6 + 改文档 | ✅ | |

## 测试结果
- 改进 Round 3 baseline:439 passed
- 三期 final:**466 passed, 0 failed**(排除 1 个 ctrim 时代测试文件)
- 三期专项:**27 / 27 passed**
- 新增:`tests/test_agent_phase3.py` 27 个 net new
- ruff:**0 error**

## 改动文件清单
| 文件 | 改动 |
|---|---|
| mmi/agent/__init__.py | 暴露 Agent* + Orchestrator + Router + Validator |
| mmi/agent/base.py | BaseAgent abstract + 生命周期钩子 + _chat_with_llm |
| mmi/agent/orchestrator.py | 5 步流程,5 处 TraceRecord 加 latency_ms,加 import |
| mmi/agent/router.py | 7 类 IntentType + 关键词 + 长度阈值 |
| mmi/agent/validate.py | 4 条规则 + ValidationResult |
| mmi/agent/registry.py | 单例加锁 get_instance() |
| mmi/agent/builtin/code_review.py | CodeReviewAgent |
| mmi/agent/builtin/doc.py | DocAgent(翻译模式) |
| mmi/agent/builtin/__init__.py | 移除 data.py |
| mmi/agent/builtin/data.py | 删除(未落地 stub) |
| mmi/agent/modes.py | get_mode_prompt 走 locale |
| mmi/agent/tools.py | 工具发现接口 |
| mmi/cli.py | +cmd_agent / +cmd_skill;删 p_skill_list;加 AgentMeta import |
| mmi/core/manager.py | persist_turn 暴露 |
| mmi/core/locales/{zh-CN,en-US}.json | +mode_prompts 节 |
| tests/test_agent_phase3.py | 新建(27 个 case) |
| docs/handover-history/round_6_phase3.md | 新建 |
| docs/handover-history/INDEX.md | +round_6 行 |
| docs/INDEX.md | 三期 3.1-3.12 全部 ✅ |
| ROUND_LOG.md | 切到 Round 6 |

## 关键设计决策
- Router 关键词 + 长度双策略(>500 → AUDIT),纯规则不上 LLM
- Orchestrator 5 步独立 try/except,失败不 crash
- Validator 4 条规则(危险 token / 短 / 危险短语 / 空)
- DocAgent 翻译模式临时切 prompt,跑完恢复
- _chat_with_llm 自动拼 system + user messages,mode suffix 自动追加
- Mode prompt 走 i18n,跟其他翻译一致

## 遗留问题
- tests/test_cli.py 3 个 case 跑 ctrim 旧路径(三期无关,留待归档)
- Router 关键词表写死(四期 4.9 配外部配置)
- 单 agent 调度(六期才有多 agent 协作)
- 错误信息直接暴露给用户(四期加脱敏)
- TraceRecord.latency_ms 写死 0.0(四期 EventBus 改造)
- Skill 仅 in-memory(六期 6.1 持久化)

## 下轮预告
- 四期 架构加固(10 项,~21h):EventBus + Pipeline + LLM 重试/流式 + Manager 批量 + 元数据 LRU
- 或:五期 周边模块(20 项,~29.5h)
- 或:六期 生态扩展(16 项,~35.5h)
- 建议先做四期,EventBus/Pipeline 是后续基础
