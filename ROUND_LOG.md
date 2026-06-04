# 工作日志 — 改进 Round 1
> Phase: 改进(临时变更计划) | Round: 1
> 标题：基础修复 — P0-1 + P0-3 + P2-8
> 开始：2026-06-04
> 状态：进行中

## 上轮交接摘要
- Round 2.5 完成:5 国内商 + wizard + 双接口选择
- 测试 423/423 全绿,ruff 0 error
- 用户提改进计划(IMPROVEMENT-PLAN.md),我分析了可行性,建议先做 Round 1(P0-1 + P0-3 + P2-8)

## 本轮计划子任务
- [x] P0-1:manager.chat() 末尾加 `_schedule_memory_store`,每轮都入库
- [x] P0-3:context.estimate_tokens 优先 tiktoken,降级中英文区分
- [x] P2-8:ThreadPoolExecutor(max_workers=1) 收编 schedule_summary_update + _schedule_memory_store
- [x] +4 个新测试
- [x] 全量 428/428 + ruff 0 error
- [x] 写 round_3.md + 更新 INDEX

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 14:00 | P0-1 短会话入库 | ✅ | manager.py +5 行 |
| 14:10 | P0-3 tiktoken | ✅ | pyproject 加 [context] extras |
| 14:20 | P0-3 降级公式 | ✅ | context.py 改 estimate_tokens |
| 14:40 | P2-8 ThreadPoolExecutor | ✅ | 替换独立 daemon 线程 |
| 14:50 | _ThreadLike 包装 | ✅ | 保留 Thread API |
| 15:00 | 修 3 个旧测试 | ✅ | estimate_tokens / Thread 断言 |
| 15:10 | +4 个新测试 | ✅ | |
| 15:20 | 全量 + ruff | ✅ | 428/428 + 0 error |

## 测试结果
- Round 2.5 baseline:423 passed
- 改进 Round 1 final:**428 passed, 0 failed**
- 新增:4 net new
- ruff:**0 error**

## 改动文件清单
| 文件 | 改动 |
|---|---|
| mmi/core/manager.py | chat() 末尾调 _schedule_memory_store |
| mmi/core/context.py | estimate_tokens 优先 tiktoken + 降级公式 |
| mmi/core/summarizer.py | ThreadPoolExecutor 替换独立线程 + _ThreadLike 包装 |
| pyproject.toml | 加 [context] extras(tiktoken) |
| tests/test_loader.py | estimate_tokens 改范围断言 |
| tests/test_summarizer.py | Thread 断言改 .join/.is_alive 存在性 |
| tests/test_memory.py | +4 个新测试 |
| PLAN.md | 加临时变更计划小节 |
| docs/HANDOVER/round_3.md | 新建 |
| docs/HANDOVER/INDEX.md | +round_3 行 |

## 关键设计决策
- P0-1:直接 manager.chat 加调用,不动 summarizer 内部
- P0-3:tiktoken optional,降级公式不依赖网络
- P2-8:单 worker + 模块单例,FIFO 保证 frontmatter 不被同时改

## 遗留问题
- P0-1 高频 chat → 1000 轮对话会有 1000 次全量 FAISS 写 → Round 3 P2-10 修
- P2-8 单 worker,慢任务会阻塞 → 高频场景再优化
- tiktoken 首次需联网下载 ~1MB → CI 无网会降级但不影响功能

## 下轮预告
- 改进 Round 2:P0-2 jieba + BM25 + P1-4 截断优先级 + P1-5 动态窗口
- 8-10h,需 P0-3 完成 ✅
