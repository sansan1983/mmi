C-CLI 会话记忆系统 — 初步开发计划
一句话定位​
一个不靠上下文压缩、不靠用户记 ID、自清理、自组织的 CLI / TUI / GUI 通用会话系统。
一、要解决的核心痛点
编号
	
痛点
	
现状


P1
	
CLI 关掉就断
	
记不住 session


P2
	
历史越长越慢
	
全量上下文重发


P3
	
Token 无限涨
	
没有淘汰机制


P4
	
AI 开始忘事
	
上下文被稀释


P5
	
GUI 也救不了
	
UI 和推理耦合


P6
	
垃圾对话堆积
	
没有过滤机制
二、产品目标（做到什么程度）
✅ CLI：简单入口
✅ TUI：会话选择 + 搜索
✅ GUI：历史可视，不背上下文锅
✅ 不压缩历史
✅ 不爆 token
✅ 不依赖用户记忆
三、核心设计思想（不再改变）
UI ≠ 推理​
显示 ≠ 发送​
聊天记录 ≠ LLM 上下文
四、总体架构（文字版框架图）
┌──────────────┐
│   CLI / TUI  │
│   (选择/新建) │
└──────┬───────┘
       ↓
┌────────────────────┐
│   Session Router   │  ← 热/温/冷/僵尸
└──────┬─────────────┘
       ↓
┌────────────────────────────┐
│   Session Index (标题+摘要) │  ← 只扫这里
└──────┬─────────────────────┘
       ↓
┌────────────────────────────┐
│   Session Loader           │
│   - 摘要                   │
│   - 最近 N 轮              │
│   - 按需扫描正文           │
└──────┬─────────────────────┘
       ↓
┌──────────────┐
│   LLM Call   │
└──────────────┘
五、会话文件格式（Skill 风格）
---
version: 1
type: session
agent_id: ccli
title: postgres-sharding-design
summary: 讨论 PG 分库分表，已确定 hash shard，未决定扩容方案
keywords: [postgres, sharding, connection-pool]
created_at: 2026-05-28
heat: 12
last_access: 2026-05-30
---

### 2026-05-28
User: ...
Assistant: ...

### 2026-05-29
User: ...
Assistant: ...
六、开发节点（严格按顺序）
✅ Phase 1：CLI 最小闭环（必须最先）
目标
能存
能选
能继续
交付
会话 JSONL 存储
最近 10 条列表
新建 / 恢复会话
不涉及
不压缩
不摘要
不 GUI
✅ Phase 2：会话命名与分类
目标
不再用 ID
自动区分“正经会话 / 杂项”
规则
前 20 条 → 尝试生成标题
失败 → 归类为杂项
杂项 → ~/.ccli/trash/
交付
LLM 生成标题 prompt
杂项目录自动清理（TTL）
✅ Phase 3：摘要 + 滚动窗口
目标
解决慢
解决 token 暴涨
规则
LLM 永远只收到：
摘要
最近 N 轮
正文只存，不发
交付
摘要生成逻辑
Session Loader
不加载全文
✅ Phase 4：热度排序与生命周期
目标
存储不无限增长
规则
会话状态
	
行为


热
	
前 10 条


温
	
折叠显示


冷
	
归档


僵尸
	
删除
交付
heat 计算逻辑
自动归档
自动删除
✅ Phase 5：TUI 交互
目标
不用记
不用想
界面
1) postgres-sharding
...
10) older-session
s) 搜索
n) 新建
>

---

## ✅ Phase 6：TUI 完善（2026-06-03 重新规划）

> **2026-06-03 决策**：**GUI 暂缓不做**。原 Phase 6（GUI 外壳）按用户要求无限期搁置。新的 Phase 6 目标是**让 TUI 从"能跑"升级到"可用"**，对照 `OMP-TUI-Spec.md` 倒推补全。

### 6.1 P0 核心交互（4.5d）

| # | 任务 | 现状 | 工作量 |
|---|---|---|---|
| 1 | `!` bash 模式 + `$` python 模式（输入框边框按前缀变色）| ❌ | 1d |
| 2 | `Ctrl+D` / `Ctrl+Z` 键绑定（spec §3.2）| ❌ | 0.5d |
| 3 | ToolCallBlock 状态机（pending → running → success/error）| ❌ | 1.5d |
| 4 | 多行 Editor（Input → TextArea）| ❌ | 1d |
| 5 | 思考过程整行高亮（OMP 风格，颜色/边框）| ⚠️ v2 部分 | 0.5d |

### 6.2 P1 视觉/UX 打磨（3-4d）

| # | 任务 | 工作量 |
|---|---|---|
| 6 | CJK 宽度处理（`visibleWidth` 替代 `len`） | 0.5d |
| 7 | 状态栏补字段（cwd / git / context% / cost）| 1d |
| 8 | 暗/亮主题切换 | 0.5d |
| 9 | Tab 键自动补全 | 0.5d |
| 10 | Escape 全局绑定 | 0.5d |
| 11 | TUI 排版细化（比例 / 颜色 / 字距，用户主动要求"先放一放"）| 2-3d |

### 6.3 P2 基础设施（2.5d）

| # | 任务 | 工作量 |
|---|---|---|
| 12 | `rapidfuzz` 下沉到 `core/search.py` | 0.5d |
| 13 | `/archive` / `/model` 端到端测试 | 0.5d |
| 14 | ARCHITECTURE.md 增补（TUI 折叠协议 / `stream_chat` / `config.toml` schema）| 1d |
| 15 | tag 命名统一（PEP 440 vs phase 跨 phase 决策）| 0.5d |
| 16 | BUG-2 视觉验证（明早做）| 0d |

### 6.4 范围

- **最小 Phase 6**：只做 6.1（P0 五项，4.5d）
- **完整 Phase 6**：6.1 + 6.2 + 6.3 = 10d

### 6.5 明确不做

- ❌ **GUI 外壳**（Electron / Tauri），无限期搁置
- ❌ voice / 飞书 集成（phase 7+ 再说）
- ❌ 真正的 LLM 流式（当前 ScriptedLLM 是 mock；接入真 OpenAI 留给独立 PR）

---

## ✅ Phase 7+：GUI 外壳（远期）

> GUI 只显示，不决定上下文。
> 交付：会话列表、聊天记录、搜索框。
> **不在 Phase 6 范围。** 用户 2026-06-03 明确"GUI 暂缓不做"。

七、需要的条件
类别
	
要求


语言
	
Python


LLM
	
任意 OpenAI 兼容


存储
	
本地文件系统


依赖
	
极少


UI
	
textual / ratatui / electron
八、明确不做的事（边界）
❌ 不实时压缩上下文
❌ 不把所有历史塞给 LLM
❌ 不依赖用户记 ID
❌ 不做复杂知识图谱
❌ 不做多用户
九、第一阶段即可验证的价值
✅ 关掉窗口能回来
✅ 不用记 session
✅ 不怕历史长
✅ token 可控
✅ 不丢重要信息