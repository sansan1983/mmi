# MMI 架构设计说明书

> 版本：v0.1.0 | 2026-06-03 | 基于 ctrim v0.5.0a5 迁移

---

## 1. 产品定位

**MMI = Multimodal Intelligence（多模态智能体）**

带记忆引擎与多Agent调度的智能体系统。从 C-Trim（Context Trim）演进而来，在会话记忆、上下文修剪、生命周期管理之上新增多Agent调度、技能管理、输出校验能力。

### 1.1 核心原则

| 原则 | 说明 |
|---|---|
| UI ≠ 推理 | 界面只负责显示，不参与推理 |
| 显示 ≠ 发送 | LLM上下文是修剪过的视图，用户看到的原文完整保留 |
| 不压缩原文 | 原文完整保存，只修剪 LLM 视图 |
| 核心可独立运行 | `mmi/core/` 不依赖 UI（CLI/TUI/GUI 只是 core 之上的薄层） |
| 轻量优先 | 主板只定义接口协议，不实现具体扩展 |

---

## 2. 系统架构

```
┌─────────────────────────────────────────────────────┐
│              接入层                                  │
│  Web GUI (Vue3)  │  CLI (typer)  │  TUI (textual)    │
├─────────────────────────────────────────────────────┤
│            Agent 调度层 (mmi/agent/)                  │
│  Orchestrator → Router → Agent Registry              │
│  Thinking Modes  │  Validator  │  Skill Library       │
│  Tool Registry   │  Tracer                           │
├─────────────────────────────────────────────────────┤
│          记忆引擎层 (mmi/core/)                        │
│  Session  │  Storage  │  Heat  │  Context            │
│  Summarizer  │  Memory  │  Search  │  GC             │
│  Titler  │  Classifier  │  LLM  │  i18n  │  Config   │
├─────────────────────────────────────────────────────┤
│              LLM 底座                                 │
│        Qwen / DeepSeek / GLM / GPT                   │
└─────────────────────────────────────────────────────┘
```

---

## 3. 目录结构

```
mmi/
├── core/            # 记忆引擎层（核心，UI无关）
│   ├── session.py   # Session / SessionMeta 数据契约, ULID
│   ├── storage.py   # .session.md 文件IO, 原子写, 文件锁
│   ├── heat.py      # 热度公式, 四态状态机
│   ├── context.py   # 上下文构建（三源合并 + 优先级截断）
│   ├── summarizer.py # 摘要生成, 版本链, 后台线程
│   ├── memory.py    # 向量语义记忆（FAISS + FTS5双路检索）
│   ├── search.py    # 关键词检索（TF + fuzzy）
│   ├── gc.py        # 垃圾回收（trash TTL, zombie清理）
│   ├── titler.py    # 会话标题生成
│   ├── classifier.py # 杂项识别（规则 + LLM混合）
│   ├── llm.py       # LLM Provider 抽象
│   ├── config.py    # ~/.mmi/config.toml 统一配置
│   ├── i18n.py      # 双语 t() 函数
│   ├── paths.py     # ~/.mmi/ 路径解析
│   ├── manager.py   # SessionManager 对外门面
│   └── locales/     # zh-CN.json / en-US.json
│
├── agent/           # Agent调度层（新建）
│   ├── orchestrator.py  # 主Agent调度中枢
│   ├── router.py        # 意图分类 + 路由分发
│   ├── registry.py      # 子Agent注册表
│   ├── base.py          # BaseAgent 抽象类
│   ├── builtin/         # 内置Agent
│   ├── modes.py         # 思维模式切换
│   ├── validate.py      # 输出校验层
│   ├── skill.py         # 技能库管理
│   ├── tools.py         # Tool注册中心
│   └── trace.py         # 调用追踪
│
├── cli.py           # 统一CLI（mmi 命令入口）
├── tui/             # TUI 终端界面（textual）
│   ├── app.py       # 应用入口
│   ├── commands.py  # 斜杠命令
│   ├── screens/     # list / chat / search
│   └── widgets/     # chat_log / header_bar / status_bar / ...
├── tools/           # 诊断维护
│   └── doctor.py    # mmi doctor
└── skills/          # 内置技能库
```

---

## 4. 核心模块设计

### 4.1 会话数据契约 (session.py)

```python
class SessionState(str, Enum):
    ACTIVE = "active"
    WARM   = "warm"
    COLD   = "cold"
    ZOMBIE = "zombie"

@dataclass
class SessionMeta:
    version: int
    type: str
    session_id: str            # ULID, 26字符
    agent_id: str
    title: str
    summary: str
    summary_version: int
    summary_history: list
    keywords: list[str]
    created_at: datetime
    updated_at: datetime
    last_access: datetime
    access_count: int
    heat: float
    state: SessionState
    trashed_at: datetime | None
    cold_since: datetime | None

@dataclass  
class Session:
    meta: SessionMeta
    body: str                  # Markdown 对话正文
```

### 4.2 存储 (storage.py)

```
存储位置: ~/.mmi/sessions/{active,trash}/
文件格式: {session_id}.session.md
  → YAML frontmatter（SessionMeta序列化）
  → Markdown body

原子写: 写 .tmp → os.replace() 覆盖
并发锁: portalocker 排他锁, timeout 10s
追加: append_turn() 始终追加, 不重写历史
```

### 4.3 热度系统 (heat.py)

```
heat = access_count × 1.0 + recency_bonus - age_penalty

recency_bonus: 1天内+10, 7天+5, 30天+1
age_penalty: 每30天-1

状态推导:
  heat ≥ 10    → active
  heat ≥ 5     → warm
  其他         → cold
  cold 持续90天 → zombie
```

### 4.4 上下文构建 (context.py)

```
三源合并:
  ① summary（摘要, 不可丢弃）
  ② hit_paragraphs（关键词命中段）
  ③ recent_turns（最近N轮, 默认10）

截断优先级（token超出上限时从低到高丢弃）:
  最近轮 > 命中段 > 摘要（永不丢弃）

Token估算: 1 token ≈ 2字符, 硬上限 4000（可配置）
```

### 4.5 记忆系统 (memory.py)

```
三层架构:
  L1 向量语义记忆  → embedding → FAISS 语义检索 top-20
  L2 结构化摘要    → LLM生成的 {主题, 决策, 结论, 待办}
  L3 完整原文      → .session.md 按 memory_id 加载

检索流程:
  embedding → FAISS top-20 → 加载L2摘要 → LLM动态重排 → top-3注入
```

### 4.6 摘要 (summarizer.py)

```
触发条件（三选一）:
  - ≥20轮 或 ≥5000字符 或 >24h且有≥5轮

版本链: summary_history 保留所有历史摘要
执行: 后台线程, 不阻塞 chat
```

### 4.7 垃圾回收 (gc.py)

```
trash TTL: 7天自动清理
zombie: 直接删除
cold超期: 移入trash

分层命令: gc --gc-only cold|zombie|trash
预览模式: gc --dry-run
```

---

## 5. Agent调度层设计

### 5.1 Orchestrator 主流程

```
用户输入 → 构建上下文 → 意图分类 → 路由分发
  → 简单问答: 主Agent直接回复
  → 创意生成: 切换发散思维模式
  → 执行类: 路由到子Agent
  → 工具调用: Tool注册中心
→ 输出校验（规则引擎 + 按需LLM审核）
→ 持久化 + 热度更新 + 摘要调度
→ 返回用户
```

### 5.2 思维模式

| 模式 | 特征 | 触发 |
|---|---|---|
| STANDARD | 客观、准确、简洁 | 默认 |
| BRAINSTORM | 发散、量大优先 | 创意生成 |
| AUDIT | 逐条审查、质疑假设 | 高风险输出二次检查 |

### 5.3 输出校验层

```
第一层: 规则引擎（零延迟）
  - 敏感词拦截
  - 空输出/过短标记
  - 格式校验 + 自动修复

第二层: LLM深度审核（仅高风险触发, <20%概率）
  - AUDIT模式重新审查
  - 对比输入需求 vs 输出完整性
```

### 5.4 技能库

```
Skill = { id, name, version, type, content (prompt模板),
          trigger_keywords, bound_tools, bound_agents,
          status, usage_count, positive_rate }

生命周期: 人工创建 → 发布 → 使用统计 → 人工迭代 → 新版本
永久红线: 不做全自动入库
```

### 5.5 Tool注册中心

```python
@tool
def read_file(path: str) -> str:
    """读取指定路径的文件内容"""
    ...

# 自动发现: 启动时扫描 tools/ 目录, 注册所有 @tool 函数
```

---

## 6. 数据流（一次完整对话）

```
用户: "帮我审查 app.py 的安全性"
  → 1. context.build(): 构建上下文（摘要+记忆+最近轮）
  → 2. router.classify(): → Intent(EXECUTE, "code_review")
  → 3. registry.match(): → CodeReviewAgent
  → 4. agent.run(): LLM调用 + Tool调用
  → 5. validator.check(): 规则引擎 → 通过
  → 6. storage.append_turn(): 原子写
  → 7. heat.compute(): 更新热度
  → 8. summarizer.schedule(): 后台检查摘要触发
  → 9. tracer.record(): 记录调用链
  → 10. 返回结果给用户
```

---

## 7. 配置 (~/.mmi/config.toml)

```toml
[llm]
model = "deepseek-chat"
base_url = "https://api.deepseek.com/v1"

[context]
max_tokens = 4000
recent_turns = 10

[memory]
embedding_model = "text-embedding-3-small"
vector_db = "faiss"
rerank_top = 3

[agent]
default_mode = "standard"
auto_audit_threshold = 0.7

[gc]
trash_ttl_days = 7
cold_ttl_days = 30
zombie_days = 90
```

---

## 8. 关键决策记录

| 决策 | 结论 | 理由 |
|---|---|---|
| 存储格式 | .session.md (YAML+Markdown) | 人类可读, 可git备份, 零运维 |
| 向量数据库 | FAISS (v1) | 零运维, 规模上去后迁Milvus |
| Agent路由 | prompt分类 | 减少依赖, 降低延迟 |
| 输出校验 | 规则引擎+按需LLM | 规则处理80%场景, LLM只在20%高风险介入 |
| 技能管理 | 人工管理, 永不全自动 | 全自动不可靠, 污染技能库 |
| 包名/命令 | mmi | 统一品牌, 从ctrim演进 |
| Python版本 | ≥3.11 | 类型系统现代化 |
| CLI框架 | typer | 与ctrim一致 |
| TUI框架 | textual | 与ctrim一致 |

---

> 完整设计文档见 MMI Agent 目录下 `MMI统一架构设计.md`
