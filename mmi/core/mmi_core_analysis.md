# mmi/core/ 模块 Morphling 分析报告

## 一、项目类型与核心价值

**项目类型**: MMI (Memory Management Interface) - 会话式AI记忆管理系统

**核心价值**: 
- 向量语义记忆检索 (FAISS + embedding)
- 多阶段会话生命周期管理 (active/warm/cold/zombie/trash)
- LLM Provider 抽象与自动故障转移
- 上下文构建与摘要自动生成

---

## 二、文件清单与尺寸

| 文件 | 大小 | 行数 | 职责 |
|------|------|------|------|
| llm.py | 35KB | 912 | LLM Provider 协议与5个实现 |
| memory.py | 34KB | 979 | 三层记忆架构 + FAISS |
| manager.py | 25KB | 638 | 唯一对外门面 |
| storage.py | 23KB | 664 | 会话文件IO + LRU缓存 |
| context.py | 18KB | 512 | LLM上下文构建 |
| summarizer.py | 16KB | 447 | 摘要生成 + 版本管理 |
| gc.py | 13KB | 367 | 垃圾回收 |
| heat.py | 13KB | 357 | 热度计算 + 状态机 |
| config.py | 12KB | 384 | 配置读写 |
| search.py | 11KB | 336 | BM25关键词检索 |
| session.py | 10KB | 292 | 数据契约 |
| mcp_server.py | 10KB | 295 | MCP协议服务 |
| titler.py | 13KB | 370 | 标题生成 |
| gc_daemon.py | 7KB | 196 | 后台GC线程 |
| audit.py | 8KB | 278 | 双层输出审计 |
| model_fetcher.py | 8KB | 261 | 模型列表拉取 |
| classifier.py | 8KB | 223 | 杂项识别 |
| provider_health.py | 8KB | 220 | 健康监控 |
| provider_registry.py | 7KB | 222 | 插件发现 |
| providers.py | 6KB | 150 | 预置模型商catalog |
| ipc_server.py | 6KB | 154 | stdio JSON-RPC |
| paths.py | 5KB | 163 | 路径管理 |
| i18n.py | 4KB | 130 | 国际化 |
| evaluation.py | 8KB | 274 | 评估框架 |
| exceptions.py | 0.7KB | 23 | 异常定义 |
| __init__.py | 2KB | 37 | 公共API导出 |

---

## 三、组件处理方式

### 调用 (调用现有实现，不重写)

| 组件 | 理由 |
|------|------|
| **llm.py** | 协议设计清晰，5个Provider实现完整，Echo/OpenAI兼容足够稳定 |
| **memory.py** | 三层记忆架构合理，FAISS集成正确，lazy init良好 |
| **storage.py** | LRU缓存 + portalocker锁机制健壮，YAML frontmatter格式合理 |
| **context.py** | token估算( tiktoken降级) + 分层截断策略成熟 |
| **summarizer.py** | 增量摘要 + 每100轮全量重建策略有效防止漂移 |
| **heat.py** | 纯函数设计，易测试，对数衰减热度公式平滑 |
| **search.py** | BM25评分正确，jieba降级到2-gram的兼容性处理完善 |
| **session.py** | ULID时序ID + 四态字面量设计合理 |
| **classifier.py** | 规则预筛 + LLM二次确认的两阶段设计安全 |
| **gc.py** | 三层GC(trash/zombie/cold)逻辑清晰 |
| **gc_daemon.py** | 单例懒启动后台线程，异常隔离 |
| **config.py** | YAML配置 + env变量覆盖机制完善 |
| **providers.py** | 预置5个国内商catalog准确，API文档来源已验证 |
| **provider_registry.py** | 插件发现机制合理 |
| **provider_health.py** | 连续失败计数 + 自动降级机制正确 |
| **model_fetcher.py** | 5分钟TTL缓存 + provider级去重逻辑正确 |
| **audit.py** | 规则引擎 + LLM双层审计设计合理 |
| **paths.py** | 跨平台路径解析 idempotent |
| **i18n.py** | locale懒加载 + t()包裹所有用户可见字符串 |
| **exceptions.py** | 集中异常定义符合R7规范 |
| **__init__.py** | 精心挑选的公共API导出子集 |

### 重写 (需要重构)

| 组件 | 理由 | 建议 |
|------|------|------|
| **manager.py** | 638行过大，TYPE_CHECKING块为空，TYPE_CHECKING滥用但未实际使用，batch_chat等方法实现不完整(只有骨架) | 拆分为多个mixin类或子类，移除空TYPE_CHECKING块，补全batch_chat实现 |
| **ipc_server.py** | 使用anyio但未处理stderr，懒导入manager但未处理循环导入边界，缺少错误处理 | 重写为更健壮的JSON-RPC 2.0实现 |
| **mcp_server.py** | 295行，但MCP协议实现不完整(只有dataclass骨架)，缺少实际的MCP握手和tool call处理 | 补全MCP协议实现或标记为Phase 5+ |
| **titler.py** | detect_topic_drift函数存在但未导出(不在__all__中)，extract_keywords与search.py tokenize有重叠逻辑 | 合并到search模块或统一接口 |
| **context.py** | estimate_tokens使用tiktoken但HAS_TIKTOKEN变量未被__all__导出，LoadedContext.truncated_what字段类型不明确 | 导出_HAS_TIKTOKEN或统一token估算接口 |

### 舍弃 (可删除或降级为可选)

| 组件 | 理由 |
|------|------|
| **evaluation.py** | 274行完整评估框架，但没有任何测试数据集，EvalSample.actual_output等字段无人填充，整个框架是空壳。**建议**: 拆出为独立包 `mmi.eval`，主core不引入 |
| **ipc_server.py** | 仅TUI使用，如果TUI是Phase 12+功能，则ipc_server属于可选依赖 |

---

## 四、代码质量问题

### 屎山代码 (需要重构)

1. **manager.py** - 空TYPE_CHECKING块 (L26-27):
```python
if TYPE_CHECKING:
    pass  # 空的，应该删除
```

2. **context.py** - _HAS_TIKTOKEN未导出但被使用:
```python
_HAS_TIKTOKEN 在模块级定义但不在__all__中
```

3. **search.py 与 titler.py 重复**:
- search.py 的 `tokenize()` 函数
- titler.py 的 `extract_keywords()` 内部也做分词
- 两者停用词表重复定义 (_EN_STOPWORDS, _ZH_STOPWORDS)

4. **manager.py batch_chat 不完整** (L195-200):
```python
def batch_chat(self, items: list[tuple[str, str]]) -> list["ChatResult"]:
    """顺序或并发执行 chat()..."""  # 只有docstring，实现被截断
```

### 僵尸代码 (可删除)

1. **evaluation.py** 整个文件 - 无任何调用点，无测试数据
2. **context.py** L54-61: tiktoken降级注释完整但_HAS_TIKTOKEN未导出
3. **provider_health.py** L23: `from mmi.agent.event_bus import EventBus` 在TYPE_CHECKING外，如果EventBus不存在会导致import错误

### 无用代码

1. **ipc_server.py** L14: `import anyio` 在Windows下可能有问题(Windows不支持anyio的某些功能)
2. **paths.py** L53: `_ENV_HOME_OVERRIDE = "MMI_HOME"` 常量定义了但未在__all__中导出

---

## 五、优化精简建议

### 立即可做 (低成本高收益)

1. **删除空TYPE_CHECKING块** (manager.py L26-27)
2. **导出_HAS_TIKTOKEN或删除变量** (context.py)
3. **合并search/titler停用词表** - 提取到共享常量
4. **evaluation.py移出core** - 独立为 mmi.eval 包
5. **修复provider_health.py的EventBus导入** - 移入TYPE_CHECKING或提供fallback

### 中期优化 (中等成本)

1. **manager.py拆解** - 拆为 SessionManagerCore + BatchMixin + CheckpointMixin
2. **补全batch_chat实现**
3. **统一tokenize接口** - search.tokenize作为标准实现，titler复用

### 架构优化 (高成本)

1. **ipc_server.py重写** - 分离主进程和server
2. **mcp_server.py补全** - MCP协议握手和tool call处理
3. **评估框架** - 如果需要评价能力，补全数据集；否则删除

---

## 六、依赖分析

### 核心依赖 (必须)
- Python 3.12+
- ulid (session ID生成)
- portalocker (文件锁)
- yaml/PyYAML (配置和session格式)
- faiss-cpu (向量检索)
- numpy (数值计算)
- httpx (HTTP客户端)
- sentence-transformers (embedding)

### 可选依赖 (优雅降级)
- tiktoken (精确token估算) → 降级为字符估算
- jieba (中文分词) → 降级为2-gram
- keyring (API key安全存储) → 降级为明文env

### 潜在问题依赖
- anyio (ipc_server.py) - Windows兼容性待验证
- mmi.agent.event_bus (provider_health.py) - 可能不存在的循环依赖

---

## 七、可测维度

1. **通过率**: core模块有良好的__all__导出，可用pytest做单元测试
2. **性能**: storage LRU缓存命中率、context token估算精度
3. **稳定性**: provider_health的故障转移机制
4. **可维护性**: 文件过大(llm.py 912行, memory.py 979行)影响可读性

---

## 八、结论

mmi/core/ 模块整体质量**较高**：
- 文档完善(每个文件都有ARCHITECTURE.md引用)
- 设计模式正确(Protocol/Facade/Singleton)
- 优雅降级处理得当

**主要问题**:
1. manager.py过大且有残缺实现
2. evaluation.py是空壳
3. 跨模块停用词表重复
4. 少数TYPE_CHECKING使用不规范

**处理方式汇总**:
- 调用: 18个组件 (69%)
- 重写: 5个组件 (19%)
- 舍弃/移出: 3个组件 (12%)