# 工作日志 — Round 2.2
> Phase: 2 | Round: 2
> 标题：向量记忆(FAISS)落地
> 开始：2026-06-03
> 状态：进行中

## 上轮交接摘要
- Round 2.1 完成:SessionMeta 时间字段类型修复 + race condition 修复
- 测试 351/351 全绿
- 下轮:Round 2.2 — 二期 P1:FAISS 向量记忆

## 本轮计划子任务
- [x] 装 FAISS + sentence-transformers
- [x] 设计 memories 表 schema + 扩 paths.py
- [x] 实现 memory.py: store_memory / search_semantic / rerank / build_structured_summary / recall_memories
- [x] 嵌入器抽象: Embedder Protocol + HashEmbedder(测试) + SentenceTransformerEmbedder(生产)
- [x] context.build_context 集成: LoaderConfig.memory + system prompt 追加 recall 段
- [x] CLI: mmi memory {search|count|clear}
- [x] memory 模块测试 24 个
- [x] 修复 _load_intermediate 空 session 早退 bug(让 memory 也能跑)
- [x] 修复 rerank 早退条件(top_n >= len → top_n > len)
- [x] pyproject.toml 加 memory extras
- [x] 跑全量测试:375 passed
- [ ] 写 docs/HANDOVER/round_2_2.md(进行中)

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 21:00 | 装 faiss-cpu + sentence-transformers | ✅ | |
| 21:10 | 写 memory.py 完整实现 | ✅ | 含 Embedder 协议 + Hash 降级 + SQLite + FAISS |
| 21:30 | context 集成 | ✅ | LoaderConfig.memory + recall 段 |
| 21:40 | 写 24 个 memory 测试 | ✅ | Hash 假嵌入器避免下载模型 |
| 21:50 | 修 _load_intermediate 早退 + rerank 条件 | ✅ | |
| 22:00 | CLI: mmi memory search/count/clear | ✅ | |
| 22:10 | 全量测试 375/375 | ✅ | |

## 测试结果
- Round 2.1 baseline:351 passed
- Round 2.2 final:**375 passed, 0 failed**
- 新增:24 memory tests
- 集成:context.py / cli.py / pyproject.toml 改动无回归

## 改动文件清单
| 文件 | 改动 |
|---|---|
| mmi/core/memory.py | 新建(~430 行):完整向量记忆模块 |
| mmi/core/paths.py | 加 get_memory_db_path / get_faiss_index_path / get_faiss_ids_path |
| mmi/core/context.py | LoaderConfig.memory + _load_intermediate 集成 recall + compose_messages 注入系统段 |
| mmi/cli.py | 新增 memory 子命令(search/count/clear) + cmd_memory |
| pyproject.toml | 加 [memory] extras(faiss-cpu + numpy) |
| tests/test_memory.py | 新建:24 个单元 + 集成测试 |

## 关键设计决策
- **嵌入器可注入**:默认 sentence-transformers(本地、零 API key),失败降级 HashEmbedder;测试用 HashEmbedder 避免下载模型
- **SQLite + FAISS 双文件**:SQLite 存元数据(title/decision/conclusion/todos/raw_excerpt),FAISS 存向量,faiss_ids.json 映射位置→memory_id
- **rerank 容错**:LLM 异常/返回未知 id → 退回原顺序补齐;无 LLM → 直接按 FAISS 顺序截 top_n
- **memory.enabled 默认 True**:跨会话记忆是核心卖点,默认开;context 检索失败静默降级,不阻塞主流程
- **build_structured_summary 规则版**:Round 2.2 阶段不调 LLM(避免慢/不稳定),Round 3 (P2) 升级为 LLM 提取

## 遗留问题
- ⚠️ build_structured_summary 规则版只提 title + conclusion(从 markdown 头/尾),没真做 LLM 提取 → Round 3 升级
- ⚠️ FTS5 路径未实现(架构文档提了,本轮只做 FAISS,FTS5 留 Round 2.3)
- ⚠️ 70 个 ruff error(既有,本轮未引入新错)
- 💡 写入路径:目前是手动调 store_memory,未接到 chat 末尾的自动入库 → Round 2.3 接 summarizer

## 下轮预告
- 下一轮:Round 2.3 — 把 memory 接入 chat 末尾(自动入库)+ 升级 build_structured_summary 为 LLM 版
- 前置依赖:本轮全部完成 ✅
- 预估工作量:1d
