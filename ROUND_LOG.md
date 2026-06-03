# 工作日志 — Round 2.3
> Phase: 2 | Round: 3
> 标题：memory 接通 chat + LLM 摘要升级 + FTS5 双路
> 开始：2026-06-04
> 状态：进行中

## 上轮交接摘要
- Round 2.2 完成:FAISS + SQLite 记忆模块
- 测试 375/375 全绿
- 下轮:Round 2.3 — 自动入库 + LLM 摘要 + FTS5

## 本轮计划子任务
- [x] summarizer.schedule_summary_update 完成后自动调 memory.store_memory
- [x] build_structured_summary 升级 LLM 提取版({title, decision, conclusion, todos})
- [x] FTS5 虚拟表 + 触发器 + search_semantic 双路召回
- [x] 清 cli.py 重复的 if info/rename
- [x] 补 12 个新测试(LLM summary 4 + FTS5 7 + auto-store 1)
- [x] 全量测试 387 passed
- [ ] 写 docs/HANDOVER/round_2_3.md(进行中)

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 10:00 | summarizer 自动入库 | ✅ | 失败静默,不阻塞摘要 |
| 10:10 | LLM 版 build_structured_summary | ✅ | 失败降级规则版,容错 |
| 10:20 | FTS5 schema + 触发器 | ✅ | external content + AI/AU/AD triggers |
| 10:30 | 修"database disk image is malformed" | ✅ | 改用 triggers,移除手工 DELETE/INSERT |
| 10:40 | search_semantic 双路召回(FAISS + FTS5) | ✅ | 去重,FAISS 优先 |
| 10:50 | cli.py 重复 if | ✅ | info/rename 各去掉一个 |
| 11:00 | 写 12 个新测试 | ✅ | 全绿 |
| 11:10 | 全量 387/387 | ✅ | |

## 测试结果
- Round 2.2 baseline:375 passed
- Round 2.3 final:**387 passed, 0 failed**
- 新增:12 memory tests(LLM summary 4 + FTS5 7 + auto-store 1)

## 改动文件清单
| 文件 | 改动 |
|---|---|
| mmi/core/summarizer.py | schedule_summary_update 后台线程成功后自动调 store_memory;加 _read_body_for_memory 辅助 |
| mmi/core/memory.py | build_structured_summary 升级 LLM 版(失败降级);FTS5 schema + 触发器;_search_fts / _sanitize_fts_query;search_semantic 双路召回 + 去重 |
| mmi/cli.py | 去掉重复的 if info / if rename |
| tests/test_memory.py | +12 个测试 |

## 关键设计决策
- **FTS5 触发器同步**:用 AFTER INSERT/UPDATE/DELETE triggers 自动维护 memories_fts,避免手工 DELETE/INSERT 撞 "external content" 模式的"database disk image is malformed" 错误
- **双路召回 + FAISS 优先**:FAISS 命中(语义近邻)排前,FTS5 命中(关键词)补后;按 memory_id 去重;任一路失败静默降级
- **LLM summary 降级**:JSON 解析失败 / LLM 抛异常 → 用原 body 走规则版;LLM 输出的乱码不会被当 title
- **summarizer 后台自动入库**:与摘要写在同一后台线程,摘要写入失败 → 不入库;入库失败 → 不抛;主流程零感知

## 遗留问题
- ⚠️ 70 个 ruff error(既有,本轮未引入新错)
- ⚠️ FTS5 query sanitizer 是简化版,复杂 query 表达(如 NEAR / 列查询)未支持
- 💡 build_structured_summary 的 LLM 提取 prompt 还可以更精细(待实际数据调优)
- 💡 自动入库触发器与 summarizer 串行;高频 chat 场景下入库会成瓶颈(下轮评估)

## 下轮预告
- Round 3.0:多 Agent 调度(Orchestrator + Router + Registry)骨架落地
- 或:Round 2.4 — memory 写入端优化(批量 + 防抖) + 入库触发器独立
