# 工作日志 — 改进 Round 3
> Phase: 改进 | Round: 3
> 标题：性能与智能增强
> 开始：2026-06-04
> 状态：进行中

## 上轮交接摘要
- 改进 Round 2 完成:jieba + BM25 + 截断 + 动态窗口
- 测试 430/430,ruff 0 error
- 下轮:改进 Round 3(P1-7 增量摘要 + P2-10 FAISS 池化 + P2-9 简化版热度)

## 本轮计划子任务
- [x] P1-7 增量摘要 + FULL_REBUILD_EVERY=100 兜底
- [x] P2-10 FAISS 内存池 + 节流 flush(50 条阈值)
- [x] P2-9 简化版热度(加法,不是乘法)
- [x] +9 个新测试
- [x] 全量 439/439 + ruff 0 error
- [x] 写 round_5.md

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 17:30 | P1-7 增量摘要 | ✅ | 17 个 summarizer 测试 |
| 17:50 | P2-10 FAISS 池 | ✅ | 49 个 memory 测试 |
| 18:10 | P2-9 简化版热度 | ✅ | 加法(避免 0 heat 状态错乱) |
| 18:20 | 9 个新测试 | ✅ | |
| 18:30 | 全量 + ruff | ✅ | 439/439 + 0 error |

## 测试结果
- 改进 Round 2 baseline:430 passed
- 改进 Round 3 final:**439 passed, 0 failed**
- 新增:9 个 net new
- ruff:**0 error**

## 改动文件清单
| 文件 | 改动 |
|---|---|
| mmi/core/summarizer.py | FULL_REBUILD_EVERY=100 + _extract_new_turns + 增量分支 |
| mmi/core/memory.py | _INMEM 池 + _ensure_loaded/_maybe_flush/flush_faiss |
| mmi/core/heat.py | compute_heat 加 total_turns + content_bonus(加法) |
| mmi/core/manager.py | _recompute_heat 传 total_turns |
| tests/test_memory.py | +9 个测试 |
| docs/HANDOVER/round_5.md | 新建 |
| docs/HANDOVER/INDEX.md | +round_5 行 |

## 关键设计决策
- 增量阈值 100 轮兜底
- FAISS 池 50 条 flush 阈值
- 热度加法(避免乘法让 0 turn 状态错乱)

## 遗留问题
- P1-6 缓存未做(投出比存疑,推迟)
- 池化切模型会丢历史
- 增量摘要早期细节可能漏

## 下轮预告
- 三期 3.0 多 Agent 调度(PLAN.md 三期) — mmi 核心能力
- 或改进 Round 4 P1-6 缓存
