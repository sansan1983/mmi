# 工作日志 — 改进 Round 2
> Phase: 改进 | Round: 2
> 标题：搜索质量 + 截断优先级 + 动态窗口
> 开始：2026-06-04
> 状态：进行中

## 上轮交接摘要
- 改进 Round 1 完成:P0-1 + P0-3 + P2-8
- 测试 428/428 全绿,ruff 0 error
- 下轮:改进 Round 2(P0-2 jieba + P1-4 截断 + P1-5 动态窗口)

## 本轮计划子任务
- [x] P0-2:search.py 中文 jieba + BM25
- [x] P1-4:context.py compose_sections + _truncate_by_section
- [x] P1-5:_compute_recent_window 动态窗口
- [x] 删 1 个旧测试 + +2 个新测试
- [x] 全量 430/430 + ruff 0 error
- [x] 写 round_4.md

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 15:30 | 装 jieba | ✅ | 10MB |
| 15:40 | search.py BM25 重构 | ✅ | 23 个测试 |
| 16:00 | P1-4 compose_sections + _truncate_by_section | ✅ | 保留 backward compat |
| 16:30 | P1-5 _compute_recent_window | ✅ | MIN 5, MAX 20 |
| 16:45 | 删 + 加 2 测试 | ✅ | |
| 17:00 | 全量 + ruff | ✅ | 430/430 + 0 error |

## 测试结果
- 改进 Round 1 baseline:428 passed
- 改进 Round 2 final:**430 passed, 0 failed**
- 改动:1 删 + 2 加
- ruff:**0 error**

## 改动文件清单
| 文件 | 改动 |
|---|---|
| mmi/core/search.py | jieba 集成 + BM25 评分 |
| mmi/core/context.py | compose_sections + _truncate_by_section + _compute_recent_window |
| pyproject.toml | 加 [search] extras |
| tests/test_search.py | 改 tokenize 测试 + 加 2 |
| tests/test_loader.py | 删 1 + 加 1 |
| docs/HANDOVER/round_4.md | 新建 |
| docs/HANDOVER/INDEX.md | +round_4 行 |

## 关键设计决策
- jieba 精确模式,降级 2-gram
- BM25 k1=1.5, b=0.75(经典值)
- P1-4 改 sections 但 messages 仍兼容
- P1-5 动态窗口范围 [5, recent_turns*2]

## 遗留问题
- jieba 10MB 包,CI 装包慢
- 删了 1 个测试(动态窗口不直接对应 recent_turns 配置值)
- BM25 参数未调

## 下轮预告
- 改进 Round 3:P1-7 增量摘要 + P2-10 FAISS 池化 + P2-9 简化版
- 10-12h
