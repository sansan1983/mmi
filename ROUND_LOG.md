# 工作日志 — R9 R8 末遗留收口
> Phase: 收口 round(R8 末遗留)| Round: 9
> 标题:R9 — 4 子任务(test_cli 归档 / EventBus 节流 / span 测试补强 / batch_* 并发)+ 1 fix
> 开始:2026-06-06
> 状态:✅ 全部收口

---

## 上轮交接摘要(R8.5.3 末)
- 四期 R7+R8 全部完成
- R8.5.1b/2/3 三个独立小补丁收口(Provider 参数透传 / Anthropic 真 SSE / Kimi 移除)
- 测试 564 passed(`--ignore=tests/test_cli.py`),ruff 0
- R9 起点 4 项(`round_8_phase4_fb.md` §6 遗留 1-4,不含 TUI)

## 本轮完成(R9 全 5 项)
- [x] 9.1 test_cli.py ctrim 硬编码 → 归档(`6086eea`)
- [x] 9.2 EventBus 节流 — `issue_batch_threshold` + `force_individual`(`1dc9a1e`)
- [x] 9.3 ValidationIssue.span 边界测试补强(`c64c07c`)
- [x] 9.4 Manager.batch_* 并发 — ThreadPoolExecutor + `max_batch_workers`(`6494fe0`)
- [x] 9.4-fix _StubLLM.classify 签名对齐 LLMProvider 抽象(`9a82a4a`)
- [x] R9 收口文档 + 索引更新 + ROUND_LOG 切换(本 commit)

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 上午 | spec 写 + 修订 | ✅ | `2d001fe` + `fff8bc7` |
| 上午 | plan 写 | ✅ | `659bdf5` |
| 下午 | Task 1-4 派 subagent | ✅ | 4 个 commit(6086eea / 1dc9a1e / c64c07c / 6494fe0) |
| 下午 | Task 4 review fix | ✅ | `9a82a4a` |
| 下午 | 收口文档 + 索引 + ROUND_LOG | ✅ | 本 commit |

## 测试结果
- master 状态:**581 passed**(R8.5.3 末 564 baseline + 17 净增)
  - 9.1: -7 删 + -3 删(已 fail)= 净 0 影响 baseline(都不在统计内)
  - 9.2: +7
  - 9.3: +3
  - 9.4: +7
  - 9.4-fix: +0
  - **净增 = 17(564 → 581)**
- ruff:`0 error`(全程维持 0)

## 改动文件清单(R9 全 5 个功能 commit + 1 收口)
### 核心代码
| 文件 | 操作 | 关键点 |
|---|---|---|
| mmi/agent/steps.py | 改 | ValidateStep 加 issue_batch_threshold / force_individual + 改 publish if/else(超阈值发 `validation.issue_batch`) |
| mmi/core/manager.py | 改 | SessionManager 加 max_batch_workers + 类属性默认值;batch_chat / batch_touch / batch_get_meta 改 ThreadPoolExecutor(单元素快路径) |

### 测试
| 文件 | 操作 | 净增 |
|---|---|---|
| tests/test_cli.py | 删 | -7(ctrim 硬编码,3 个本就 fail 不计) |
| tests/test_event_bus_throttle.py | 新 | +7 |
| tests/test_validate.py | 改 | +3 |
| tests/test_batch_chat.py | 改 | +7 + _StubLLM.classify 签名修 |
| tests/conftest.py | 改 | +1 collect_ignore_glob 保险 |
| docs/history/ctrim-tests-deprecated.md | 新 | 归档说明 |

### 文档
| 文件 | 操作 | 关键点 |
|---|---|---|
| docs/handover-history/round_9_r8_tail.md | 新 | R9 完整交接 |
| docs/handover-history/INDEX.md | 改 | +round_9 行 |
| ROUND_LOG.md | 改 | 切到 Round 9(本文件) |

## 关键设计决策(摘要)
- 节流阈值默认 5(对照 deep analysis 经验值)
- `force_individual` 开关给调试场景
- storage 已有 portalocker,R9 不另加 RLock(spec 二修删该项)
- 顺序保证用 pre-allocated list + enumerate index
- 单元素快路径避免线程池开销
- 5 处 spec 偏差由 subagent TDD 失败循环自检修对

## 遗留问题(R9.x / R10+ 起点)
- TUI 真流式 + 美化 → R9.x 单独 round
- 五期 20 项 / 六期 16 项 → R10+
- R8.5.1b 报告 §5 B1-B4 + C1 → R8.5.x(可选)
- validation.issue_batch 大量 issue 嵌套 EventBus 仍有节流压力(本轮已比逐条好) → R10+ 视情况
- 5 处 spec 偏差(说明 plan 写时需要更细的代码片段)→ 后续 plan 改 TDD 写法

## 下次续做
- **R9.x**(可选):TUI 真流式 + 美化(本轮推后)
- **R10+**:五期 20 项 / 六期 16 项
- 建议:先做 R9.x TUI(独立 round,跟本轮同节奏),再做 R10+ 大块

---

> 接手者:`git checkout master` → `pytest tests/ -q` 看到 581 passed + ruff 0 即可接 R9.x 或 R10。
