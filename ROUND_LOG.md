# 工作日志 — Round 2.5
> Phase: 二期 + 用户临时 | Round: 5
> 标题：交互式 LLM 配置 wizard
> 开始：2026-06-04
> 状态：进行中

## 上轮交接摘要
- Round 2.4 完成:memory 收尾(独立线程 + hash 去重 + ruff 0 error)
- 测试 395/395 全绿
- 用户临时加项目:`mmi config` 交互式配置 LLM

## 本轮计划子任务
- [x] 5 国内 + 1 自定义 catalog(deepseek / minimax / glm / moonshot / qwen + custom)
- [x] Anthropic 优先(DeepSeek + MiniMax),fetcher 失败回退 OpenAI
- [x] mmi/core/providers.py + model_fetcher.py
- [x] mmi/core/config.py 扩 LLM section(get_llm_config / set_llm_config / resolve_api_key)
- [x] mmi/cli.py cmd_config(show + wizard)
- [x] +28 providers 测试 + +11 config 测试
- [x] ruff 0 error
- [x] 全量 423/423
- [x] 写 docs/HANDOVER/round_2_5.md

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 15:00 | catalog + fetcher 实现 | ✅ | 5 国内 + custom |
| 15:30 | config 持久化 | ✅ | linter 已加 get_llm_config 等 |
| 16:00 | cmd_config wizard | ✅ | 选 provider / 填 key / 拉模型 / 选 model |
| 16:30 | 28 + 11 测试 | ✅ | 0 error 起步,roundtrip 全通 |
| 17:00 | 全量 + ruff | ✅ | 423/423 + ruff 0 |

## 测试结果
- Round 2.4 baseline:395 passed
- Round 2.5 final:**423 passed, 0 failed**
- 新增:28 providers + 11 config = 39 net new(去掉 7 个旧 + 其他)
- ruff:**0 error**

## 改动文件清单
| 文件 | 改动 |
|---|---|
| mmi/core/providers.py | 新建(5 国内 catalog + custom 工厂) |
| mmi/core/model_fetcher.py | 新建(双风格 + 回退) |
| mmi/core/config.py | 扩 LLM section 持久化 |
| mmi/cli.py | cmd_config + wizard |
| tests/test_providers.py | 新建 28 个 |
| tests/test_config.py | 新建 11 个 |
| docs/HANDOVER/round_2_5.md | 新建 |
| docs/HANDOVER/INDEX.md | 加 2.5 行 |
| ROUND_LOG.md | 更新本轮 |

## 关键设计决策
- Anthropic 优先:DeepSeek + MiniMax 走 Anthropic 端点,失败回退 OpenAI
- key 持久化在 config.toml,env 兼容兜底
- Anthropic 不引 SDK(llm.py 早就 httpx 直连)
- 5 国内:deepseek / minimax / glm / moonshot / qwen,海外商后续扩

## 遗留 / 下轮候选
- 后续要加海外商:在 `PROVIDERS` tuple 加一条
- helper model(embedding / summary)用同一配置
- 可选:加 `mmi config set <key> <value>`(目前只支持 wizard)
- 三期 3.1-3.13 多 Agent 调度 仍待开始

## 下轮预告
- 三期 3.0 多 Agent 调度(PLAN.md 三期),或
- 继续打磨 Round 2.5 后续(海外商 / helper model)
- 预估:2-3d

## 上轮交接摘要
- Round 2.3 完成:FTS5 双路召回 + LLM 摘要 + summarizer 自动入库
- 测试 387/387 全绿
- 下轮:Round 2.4 — memory 写入优化 + 清 ruff

## 本轮计划子任务
- [x] summarizer.store_memory 拆出独立后台线程(`_schedule_memory_store`)
- [x] 加 content_hash 字段 + 去重逻辑(同 body 重复入库跳过)
- [x] 清 35 个 ruff error(全部修复:24 自动 + 11 手动)
- [x] 加 8 个新测试(去重 6 + 独立线程 2)
- [x] 全量测试 395 passed
- [ ] 写 docs/HANDOVER/round_2_4.md(进行中)

## 执行记录
| 时间 | 任务 | 结果 | 备注 |
|---|---|---|---|
| 11:30 | _schedule_memory_store 拆独立线程 | ✅ | 与 update_summary 解耦 |
| 11:40 | content_hash + 去重 | ✅ | sha256[:16],同 body 返旧 record |
| 11:50 | ruff --fix 自动修 24 个 | ✅ | F401/F541 等 |
| 12:00 | 手动修 11 个 ruff | ✅ | E402 noqa / F841 / E741 / 显式 re-export |
| 12:10 | 8 个新测试 | ✅ | |
| 12:20 | 全量 395/395 | ✅ | |

## 测试结果
- Round 2.3 baseline:387 passed
- Round 2.4 final:**395 passed, 0 failed**
- 新增:8 memory tests(6 dedup + 2 thread)
- ruff:`All checks passed!`(0 error)

## 改动文件清单
| 文件 | 改动 |
|---|---|
| mmi/core/summarizer.py | `_run` 只跑 update_summary,成功后调 `_schedule_memory_store` 起独立线程入库;移除冗余 `current_turns` 变量 |
| mmi/core/memory.py | schema 加 `content_hash` 列 + 索引;`store_memory` 加 hash 去重逻辑 + `_get_by_hash` 辅助;FAISS `I` 变量名改 `idx_indices`(消 E741) |
| mmi/__init__.py | `SessionState as SessionState` 显式 re-export |
| mmi/cli.py | 移除未用 `p_tui` / `p_doctor` / `p_stat` / `title` 局部变量 |
| mmi/tools/doctor.py | 4 个 import 加 `noqa: E402` |
| tests/test_memory.py | +8 个 Round 2.4 测试 |

## 关键设计决策
- **入库独立线程**:`_schedule_memory_store` 单独 daemon 线程,失败静默。update_summary 跑完即释放线程,避免入库 IO 拖慢摘要线程
- **content_hash 去重**:用 `sha256(body)[:16]` 作为 16 字符短 hash,既稳定(同 body 同 hash)又轻量(不占空间)。同 hash 命中 → 直接返旧 record,不重算 embedding
- **FTS5 + content_hash 索引**:`idx_memories_hash` 让去重查询走索引(实际单 session 量小,扫表也无所谓,索引为后续规模留口)
- **ruff 0 error**:自动修 24 个 + 手动修 11 个(已显式 re-export / noqa / 重命名)

## 遗留问题
- ⚠️ Round 3.0 多 Agent 调度 还没开始(原本在 2.3 交接里建议,2.4 没碰)
- 💡 LLM summary prompt 仍可调优(实测数据)
- 💡 FTS5 query sanitizer 简化版(同 2.3 遗留)

## 下轮预告
- Round 3.0 — 多 Agent 调度(Orchestrator / Router / Registry / 3 个内置 Agent 骨架)
- 或:继续 memory 调优(批量入库 / 索引合并)
- 预估:2-3d
