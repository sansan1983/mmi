# MMI 四期 架构加固 — 设计规格

> 日期:2026-06-05
> 范围:docs/INDEX.md 四期 10 项(4.1–4.10),分两轮 R7+R8
> 依据:`docs/INDEX.md` 路线图 + `~/GA work/2026-06-04/documents/mmi_modules_deep_analysis.md` + `~/GA work/2026-06-04/documents/IMPROVEMENT-PLAN.md` + 三期交接 `docs/handover-history/round_6_phase3.md`
> 状态:草稿,等用户审

---

## 0. 背景与目标

### 0.1 痛点总览(摘自 deep analysis)

| 来源 | 痛点 | 严重度 |
|---|---|---|
| 1.11 F1 + 2.1 F2 + P1 | `Manager.chat()` 单体上帝对象,所有环节串行硬编码,任何失败全崩,无法插拔 | 严重 |
| 1.11 F3 + P3 | 模块耦合靠硬编码调用,无 EventBus/钩子系统,扩展要改所有调用方 | 高 |
| 1.9 F1 | `LLM.stream_chat()` 默认 `NotImplementedError`,无法打字机输出 | 高 |
| 1.9 F2 | LLM 失败无重试,调用方自己实现 | 高 |
| 1.9 F3 | 无 `tokens_used / latency_ms` 返回,无法计费统计 | 中 |
| 1.11 F2 | `list_sessions` 每次遍历磁盘,高频场景(TUI 滚动)延迟明显 | 高 |
| 1.11 F5 | 有 `touch()` 但无批量接口,UI 批量选中效率低 | 中 |
| 2.2 F2 | Router mapping 硬编码,无法动态扩展 | 中 |
| 2.2 F3 | Router 只能返单个 IntentType | 中 |
| 2.8 F3 | Validator 返 bool 但不告诉哪条规则触发 | 中 |

### 0.2 三期已落地(衔接点,不动)

- `mmi/agent/orchestrator.py` — 5 步串行(classify/route/instantiate/run/validate/persist),每步独立 try/except
- `mmi/agent/router.py` — 7 类 IntentType,关键词 + 长度双策略,纯规则不上 LLM
- `mmi/agent/validate.py` — 4 条规则 + `ValidationResult(passed, reasons)`
- `mmi/agent/trace.py` — in-memory Tracer + TraceRecord(latency_ms 当前写死 0.0)
- `mmi/agent/registry.py` — 单例加锁 `get_instance()`
- `mmi/core/llm.py` — `LLM.chat(messages)`,无重试无流式

四期不破坏外部 API:`Orchestrator.chat()` 继续存在(新增 `chat_legacy()` 兼容路径,`chat()` 改返 `ChatResult`)。

### 0.3 拆分

| 轮 | 项 | 工时 | 备注 |
|---|---|---|---|
| **R7** | 4.3 + 4.5 + 4.1 + 4.2 + 4.4 + 4.6 | ~14h | 核心,Pipeline 是核心 |
| **R8** | 4.7 + 4.8/4.9 + 4.10 | ~7h | 周边,互不依赖可任意顺序 |

---

## 1. 4.3 LLM 重试(R7)

### 痛点
1.9 F2:`LLM.chat()` 失败直接抛,调用方各自实现重试,行为不一致。

### 方案
在 `mmi/core/llm.py` 加 `LLM.chat_with_retry(messages, *, max_attempts=3, base_delay=0.5) -> ChatResult`,**自写退避,不用 tenacity**:

- 可重试错误:`httpx.TimeoutException` / `httpx.ConnectError` / `httpx.HTTPStatusError`(5xx 且 429) / `ConnectionError`
- 不可重试:其它 `HTTPStatusError`(4xx 客户端错)、`ValueError`(参数问题)
- 退避序列:`base_delay * 2^(attempt-1)`,实际等待 0.5s / 1s / 2s,最多 3 次
- 成功 → `ChatResult(reply=text, attempts=n, ...)`
- 失败(3 次都试过)→ 抛 `LLMRetryExhausted`,由 Pipeline 走 degrade 策略(见 4.2)

`chat_with_retry` 不破现有 `chat()` API;Orchestrator 三期是用 `self.llm.chat(messages)`,四期改成 `self.llm.chat_with_retry(messages)`。

**拒绝 tenacity 的理由**:依赖多(它把 `wrapt` 也拖进来)、行为细节黑箱(decorator 套太多层调 stack 时容易卡)、15 行自写完事。

### 测试
- 5xx 错误 mock 后重试成功 → `attempts==2`
- 4xx 错误不重试,直接抛
- 超时 3 次仍失败 → 抛 `LLMRetryExhausted`
- 退避时序可控:注入假 `time.sleep` 计数器验证(避免真睡)

---

## 2. 4.5 ChatResult 结构化(R7)

### 痛点
1.9 F3 + 三期遗留:Orchestrator 当前返 `str`,丢失了 intent / agent_id / 校验结果 / 尝试次数 / 时延 / 错误。

### 方案
新建 `mmi/agent/result.py`:

```python
@dataclass
class ChatResult:
    reply: str
    intent: IntentType
    agent_id: str
    validation: ValidationResult | None
    trace_ids: list[str]
    attempts: int = 1
    latency_ms: float = 0.0
    error: str | None = None
```

`Orchestrator` 公开 API 调整:

| 旧 | 新 | 行为 |
|---|---|---|
| `chat(sid, msg, mode=None) -> str` | 保留,标记 deprecated,改调 `chat_legacy` | 走同一 Pipeline,只返 `result.reply` |
| — | `chat(sid, msg, mode=None) -> ChatResult` | 主路径 |
| — | `chat_legacy(sid, msg, mode=None) -> str` | 兼容 |

TUI 端先切到 `chat_legacy`(不破),CLI 切到 `chat()`(新行为)。六期稳定后删 `chat_legacy`。

### 测试
- `ChatResult` 字段完整
- `chat_legacy` 与旧 `chat` 行为一致(同 input,reply 字符串相同)
- `to_dict()` 序列化

---

## 3. 4.1 EventBus(R7)

### 痛点
1.11 F3 + P3:模块耦合靠硬编码调用,新增功能(如 titler 完成通知)要改 manager。

### 方案
新建 `mmi/agent/event_bus.py`:

```python
@dataclass(frozen=True)
class Event:
    name: str
    timestamp: float
    payload: dict[str, Any] = field(default_factory=dict)

class EventBus:
    def subscribe(self, event_name: str, handler: Callable[[Event], None]) -> None: ...
    def unsubscribe(self, event_name: str, handler: Callable[[Event], None]) -> None: ...
    def publish(self, event: Event) -> None: ...
    def reset(self) -> None: ...  # 测试用

# 全局单例(可被依赖注入覆盖)
bus: EventBus = EventBus()
```

约定事件名(4.2 Pipeline 实际 publish):

| name | 何时 | payload |
|---|---|---|
| `pipeline.start` | Pipeline 入口 | `{session_id, user_message}` |
| `step.start` | 每步开始 | `{step: str}` |
| `step.end` | 每步结束 | `{step, duration_ms}` |
| `step.error` | 每步抛错 | `{step, error, policy}` |
| `llm.call` | 调 LLM 前 | `{agent_id, messages_count}` |
| `llm.retry` | 每次重试 | `{attempt, error, sleep_s}` |
| `llm.end` | LLM 返 | `{attempts, latency_ms, tokens?}` |
| `validation` | validate 完 | `{passed, issues}` |
| `persist.end` | 写盘完 | `{bytes_written}` |
| `chat.end` | 整轮结束 | `{session_id, agent_id, latency_ms, attempts}` |

派发策略:**同步派发,handler 异常 try/except 隔离,只 log 不抛出 publish 调用方**。

已知订阅者:
- `Tracer`(改造,接收 Event 写 TraceRecord;`latency_ms` 从 `step.end.duration_ms` 拿,不再写死 0.0)
- `HeatObserver`(可选,R7 不接,接口预留)

### 测试
- subscribe/unsubscribe 增删
- 多个订阅同一事件,全部触发
- handler 抛错不影响其它 handler
- `reset()` 清空订阅

---

## 4. 4.2 Manager Pipeline(R7)

### 痛点
1.11 F1(严重) + 2.1 F2(高) + P1(严重):`Orchestrator.chat()` 串行 5 步,无插拔无中间件,任何失败全崩。

### 方案
新建 `mmi/agent/pipeline.py`,把 5 步拆成可插拔 Step + 容器:

```python
@dataclass
class PipelineCtx:
    session_id: str
    user_message: str
    mode: ThinkingMode | None = None
    intent: IntentType | None = None
    agent_id: str | None = None
    agent: BaseAgent | None = None
    reply: str | None = None
    validation: ValidationResult | None = None
    trace: list[TraceRecord] = field(default_factory=list)
    errors: list[StepError] = field(default_factory=list)
    chat_result: ChatResult | None = None

class StepError(Exception):
    def __init__(self, step: str, cause: Exception, policy: str): ...

class PipelineStep(Protocol):
    name: str
    on_error: str            # "fail" | "degrade" | "skip"
    def run(self, ctx: PipelineCtx) -> PipelineCtx: ...

class Pipeline:
    def __init__(self, steps: list[PipelineStep]): ...
    def run(self, ctx: PipelineCtx) -> ChatResult: ...
```

6 个内建 Step(沿袭三期的 5 步,补一个 EventEmitter):

| Step | name | on_error | 行为 |
|---|---|---|---|
| `ClassifyStep` | classify | fail | `router.classify(text)` → `ctx.intent` |
| `RouteStep` | route | fail | `router.route(intent)[0]` → `ctx.agent_id` |
| `InstantiateStep` | instantiate | fail | `registry.get(agent_id)` → `ctx.agent` |
| `RunStep` | run | degrade | `agent.run(user, mode)` → `ctx.reply`;失败 → 脱敏占位 `[LLM 暂时不可用]` + `ctx.errors += StepError` |
| `ValidateStep` | validate | degrade | `validator.check(reply, intent)` → `ctx.validation`;不通过也继续 |
| `PersistStep` | persist | degrade | `manager.persist_turn(sid, msg, reply)`;失败 log.error,不阻塞 |

每步前后 publish `step.start` / `step.end`(见 4.1 事件表)。

`Orchestrator` 退化为:

```python
class Orchestrator:
    def __init__(self, ..., pipeline: Pipeline | None = None): ...
    def chat(self, sid, msg, *, mode=None) -> ChatResult:           # 主路径
        return self.pipeline.run(PipelineCtx(...))
    def chat_legacy(self, sid, msg, *, mode=None) -> str:           # 兼容
        return self.chat(sid, msg, mode=mode).reply
```

六期多 agent 协作(plan 6.4)直接受益:加新 Step 不改 Orchestrator,只换 `pipeline` 装配。

### 错误策略

| 失败点 | on_error | 用户感知 | 持久化 |
|---|---|---|---|
| classify / route / instantiate | fail(后续毫无意义) | `ChatResult.reply = "[Orchestrator error] {step}: {e}"` | 不写 |
| agent.run | degrade(脱敏占位) | `[Agent X 暂时不可用]` 之类固定文案,异常细节只走 log | 写(用户能看到错) |
| llm 重试 3 次仍失败 | degrade(同 run) | `[LLM 暂时不可用,稍后重试]` | 写 |
| validate 不通过 | degrade | 不变(继续写) | 写(issues 进 trace) |
| persist | degrade + `log.error` | 正常返 | 不写(已 log) |

**脱敏原则**:4xx 错误不暴露 API key/endpoint;5xx/网络统一文案"LLM 暂时不可用";内部 exception 详情只走 log。

### 测试
- 6 步走通的 happy path
- 每步抛错时,验证 `on_error` 策略生效
- 注入 fake Step 替换内建,验证 Pipeline 容器独立
- `chat()` 返 ChatResult,`chat_legacy()` 返 reply 字符串

---

## 5. 4.4 LLM stream_chat(R7)

### 痛点
1.9 F1:`stream_chat()` 默认 `NotImplementedError`,无法流式输出。

### 方案
在 `mmi/core/llm.py` 加 `LLM.stream_chat(messages) -> Iterator[str]`:

- **同步迭代器起步**(不抽 `async def`);原因是本仓 SDK 同步(httpx + OpenAI 兼容),强行 async 收益小、改动面大
- chunk 与 LLM Provider 实际返回对齐(逐 token 字符串)
- 断网/超时行为:`StreamError` 抛出,允许调用方走与 4.3 重试一致的逻辑
- TUI 端接 `stream_chat` 在五期后段(本轮不接,只把 LLM 层做好)

### 测试
- mock Provider 返多 chunk,迭代后拼出完整文本
- 中途 chunk 抛错 → 抛 `StreamError`
- `stream_chat` 不影响 `chat` 路径

---

## 6. 4.6 Manager 批量(R7)

### 痛点
1.11 F5:有 `touch()` 无 `batch_touch`,UI 批量选中时低效。

### 方案
在 `mmi/core/manager.py` 加:

```python
def batch_chat(self, items: list[tuple[str, str]]) -> list[ChatResult]:
    """items: [(session_id, user_message), ...]"""
    return [self.orchestrator.chat(sid, msg) for sid, msg in items]

def batch_touch(self, session_ids: list[str]) -> None:
    """批量更新 last_access"""
    for sid in session_ids:
        try: self.touch(sid)
        except Exception: log.exception("batch_touch failed for %s", sid)

def batch_get_meta(self, session_ids: list[str]) -> dict[str, SessionMeta]:
    """批量拉 meta,接 R8 LRU 缓存"""
    return {sid: self.get_session_meta(sid) for sid in session_ids}
```

顺序执行,逐项 try/except 隔离(不并发,避免 R7 引入新的并发复杂度)。

### 测试
- 3 条正常 + 1 条异常 → 3 条正常返 ChatResult,1 条异常隔离(可考虑返 `ChatResult(reply="", error=...)`)
- `batch_touch` 单条失败不阻塞其它
- `batch_get_meta` 不存在的 sid 抛 KeyError 或跳过得约定

---

## 7. 4.7 元数据 LRU(R8)

### 痛点
1.11 F2(高):`list_sessions` 每次遍历磁盘;1.2 F1(高):storage 每次 open/close。深度分析推"LRU 缓存 + 写穿 index.json"。

### 拆分(R8 内再细分)

| 段 | 内容 | 工时 |
|---|---|---|
| R8-A | `mmi/core/lru.py`:`LRU[K, V]` 泛型类 + 单元测试 | 1.5h |
| R8-B | 接入 `Manager.get_session_meta()`,写时 invalidate | 1.5h |
| R8-C(可选) | storage LRU 句柄缓存(1.2 F1)— 暂缓,五期 storage LRU 那块做 | — |

**R8 范围固定 R8-A + R8-B**。R8-C 不在四期。

### 方案

```python
class LRU(Generic[K, V]):
    def __init__(self, maxsize: int = 128): ...
    def get(self, key: K, loader: Callable[[], V]) -> V: ...
    def invalidate(self, key: K) -> None: ...
    def clear(self) -> None: ...
    def __len__(self) -> int: ...
```

- 接入点:`Manager.get_session_meta(sid)` 走 `LRU.get(sid, lambda: storage.read_session(sid).meta)`
- 写入点:`persist_turn` 后 `lru.invalidate(sid)`(避免读旧 meta)
- 默认 `maxsize=128`(估计够 ~1.2 万会话,具体等真瓶颈再调)
- **不接 list_sessions**(它要走全表,LRU 帮不上;倒排索引是五期 1.2 F3 的事)

### 测试
- 插入 N+1 → 第一个被淘汰
- 重复 get 同一 key → loader 只调一次
- invalidate 后再 get → 重新调 loader
- 线程安全(R8 暂不要求,加 `threading.Lock` 留作 1 行可选)

---

## 8. 4.8/4.9 Router 多意图 + 可配置(R8)

### 痛点
2.2 F2(中):route mapping 硬编码;2.2 F3(中):只能返单 IntentType。

### 方案

**classify 改返 list[IntentType, confidence]**:

```python
def classify(self, text: str) -> list[tuple[IntentType, float]]:
    s = text.strip().lower()
    if not s: return [(IntentType.UNKNOWN, 0.0)]
    if len(s) > 500: return [(IntentType.AUDIT, 1.0)]
    hits: list[tuple[IntentType, float]] = []
    for intent, kws in self.keywords.items():
        n = sum(1 for k in kws if k in s)
        if n: hits.append((intent, min(1.0, n * 0.4)))
    if not hits: hits.append((IntentType.QA, 0.3))
    return sorted(hits, key=lambda x: -x[1])
```

**route 接 list**:

```python
def route(self, intents: list[tuple[IntentType, float]]) -> list[str]:
    """返 agent_ids,主 agent 在前"""
    if not intents: return ["qa"]
    return [self.mapping[i[0]] for i in intents if i[0] in self.mapping]
```

**可配置**:顶部抽 `DEFAULT_KEYWORDS` + `DEFAULT_MAPPING`,加 `Router.from_config(path: Path | None = None)` 读 `~/.mmi/router.toml`:

```toml
[keywords.code_review]
zh = ["审查", "审计代码", "review"]
en = ["review", "code review", "audit"]

[mapping]
code_review = "code_review"
data_analysis = "data_analysis"
```

`path` 缺省或文件不存在/缺 key → 走默认;不抛错。

六期(plan 6.4)直接用多意图:第一个是主 agent,其余是协作 agent。

### 测试
- 单关键词命中 → 1 个 intent
- 多关键词命中多 intent → 按置信度排序
- 配置文件覆盖默认值
- 配置文件缺 key → 兜底默认
- 长度 > 500 → 强制 AUDIT 置信度 1.0

---

## 9. 4.10 ValidationResult 结构化(R8)

### 痛点
2.8 F3(中):`validate()` 返 bool 不告诉哪条规则触发;F2 默认规则过少(顺手补 2 条)。

### 方案

```python
@dataclass(frozen=True)
class ValidationIssue:
    rule: str                              # "dangerous_token" / "too_short" / "dangerous_phrase" / "empty" / "no_pii" / "max_length"
    severity: int                          # 0=info / 1=warn / 2=error
    message: str
    span: tuple[int, int] | None = None    # reply 中的字符区间

    def to_dict(self) -> dict: ...

@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def reasons(self) -> list[str]:        # 兼容三期 API
        return [i.message for i in self.issues if i.severity >= 1]
```

字段迁移:`ValidationResult(passed, reasons)` → `ValidationResult(passed, issues)`;`reasons` 留 `property` 兼容(标记 deprecated)。

**顺手补 2 条规则**(deep analysis 2.8 F2 提的):
- `no_pii`:检测 reply 是否包含邮箱/手机号/身份证(简单正则)
- `max_length`:reply > 10000 字符 → warn(避免撑爆 LLM 上文)

`no_pii` 规则:简单到不调 LLM,正则匹配 `[\w.-]+@[\w.-]+` / `1[3-9]\d{9}` / `\d{17}[\dXx]`。命中率低但成本几乎为 0。

### 测试
- 既有 4 条规则仍工作(reasons 兼容)
- 新增 `no_pii` / `max_length` 触发
- `to_dict()` 序列化
- `passed=False` 时 issues 至少 1 个 severity>=1

---

## 10. 不在四期(明确划出去)

| 项 | 出处 | 后续归 |
|---|---|---|
| heat 指数衰减(1.3) | deep analysis 1.3 F1 | 五期 |
| storage LRU 句柄(1.2 F1)+ 读写锁(1.2 F2) | deep analysis 1.2 | 五期 |
| storage 倒排索引(1.2 F3) | deep analysis 1.2 F3 | 五期 |
| heat 指数衰减 + 连续函数 | IMPROVEMENT-PLAN P2-9 + deep analysis 1.3 F1/F2 | 五期 |
| LLM deep audit(2.8 F1) | deep analysis 2.8 | 五期后段 |
| Skill 持久化 + embedding 匹配 | deep analysis 2.7 | 六期 6.1/6.2 |
| Trace 持久化 | deep analysis 2.9 | 六期 6.3 |
| 多 Agent 协作 | deep analysis 2.1/3.1 | 六期 6.4 |
| TUI 端接 stream_chat UI | — | 五期后段 |
| Pydantic 替代 dataclass | deep analysis 1.1 结构性 | 暂缓,等真痛点 |
| Provider 健康检测 | deep analysis 1.12 F3 | 六期 |
| `chat_legacy` 移除 | 三期→四期 兼容 | 六期稳定后 |

---

## 11. 测试策略与质量门禁

### 测试文件清单

| 文件 | 覆盖 | 轮 |
|---|---|---|
| `tests/test_llm_retry.py`(新) | 重试/不退/退避时序/耗尽 | R7 |
| `tests/test_chat_result.py`(新) | 字段/`chat_legacy` 兼容/序列化 | R7 |
| `tests/test_event_bus.py`(新) | 订阅/派发/handler 异常隔离/reset | R7 |
| `tests/test_pipeline.py`(新) | 6 步走通/`on_error` 策略/注入 fake step | R7 |
| `tests/test_llm_stream.py`(新) | chunk 迭代/中段错/不破 chat | R7 |
| `tests/test_batch_chat.py`(新) | 顺序/单条失败隔离 | R7 |
| `tests/test_lru.py`(新) | 插入/淘汰/invalidate/clear | R8 |
| `tests/test_router_multi.py`(新) | 多意图排序/配置覆盖/缺 key 兜底 | R8 |
| `tests/test_validation_struct.py`(新) | issues 字段/reasons 兼容/to_dict | R8 |

预计 R7 净增 ≥18,R8 净增 ≥12。

### 门禁
- `pytest tests/ -x` 全过
- `ruff check mmi/` 0 error
- 三期 27 个 net new 测试不退化
- R7 收口总数 ≥ 484,R8 收口 ≥ 496

---

## 12. 关键文件改动清单(R7 + R8 总览)

### R7 新建
- `mmi/agent/event_bus.py`
- `mmi/agent/pipeline.py`
- `mmi/agent/result.py`
- `mmi/agent/steps.py`(6 个内建 Step 类)

### R7 修改
- `mmi/core/llm.py` — `+chat_with_retry` / `+stream_chat` / `+LLMRetryExhausted` / `+StreamError`
- `mmi/agent/orchestrator.py` — 改造,内部走 Pipeline;`chat()` 改返 `ChatResult`;`+chat_legacy()`
- `mmi/agent/trace.py` — 接收 EventBus Event
- `mmi/core/manager.py` — `+batch_chat` / `+batch_touch` / `+batch_get_meta`
- `mmi/cli.py` — 切到 `ChatResult` 处理(如有需要)

### R8 新建
- `mmi/core/lru.py`
- `mmi/agent/router_config.py`(`Router.from_config`)

### R8 修改
- `mmi/agent/router.py` — `classify` 返 list;`+from_config`
- `mmi/agent/validate.py` — `ValidationResult.issues` 字段;`+no_pii` / `+max_length` 规则
- `mmi/core/manager.py` — `get_session_meta` 接 LRU;`persist_turn` 加 invalidate

### 文档
- `docs/handover-history/round_7_phase4_core.md`(R7 收)
- `docs/handover-history/round_8_phase4_tail.md`(R8 收)
- `docs/handover-history/INDEX.md` + 行
- `docs/INDEX.md` — 四期 4.1–4.10 状态更新
- `ROUND_LOG.md` — 切轮
