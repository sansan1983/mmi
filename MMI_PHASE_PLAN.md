# MMI 阶段修复与完善计划书

> 制定时间：2026-06-12 | 版本：v1.0 | 基准：63ea94c（master）
> 维护原则：**每阶段完成后写交接文档（`docs/handover-history/round_X.md`），更新本文档状态**

---

## 一、优先级总览

| 优先级 | 标识 | 含义 |
|--------|------|------|
| P0 | 🔴 | 立即处理，严重阻碍开发或存在安全/功能风险 |
| P1 | 🟡 | 下一 round 处理，有改善效果 |
| P2 | 🟢 | 低优先级，有余力再做 |

---

## 二、阶段划分总表

| 阶段 | 名称 | 核心任务 | 预估工时 | 优先级 |
|------|------|----------|----------|--------|
| **P0-Round** | **技术债务清除** | cli.py 重构 + 依赖修复 + ruff 安装 | ~4h | 🔴 |
| **P1-Round A** | **五期核心项** | GC后台触发 + 依赖补全 + API Key安全 + Manager线程安全 | ~8h | 🟡 |
| **P1-Round B** | **TUI MVP** | 完成 TUI 消息展示/会话列表/主题切换 + 真流式 | ~10h | 🟡 |
| **P2-Round** | **五期剩余项** | classifier滑动窗口 + heat指数衰减 + config校验 + titler话题偏移等 | ~15h | 🟢 |
| **P3-Round** | **六期生态扩展** | Skill持久化 + Trace持久化 + Provider健康检测 + LLM Deep Audit | ~20h | 🟢 |
| **P4-Round** | **六期进阶** | Web GUI + MCP + 评估框架 + 性能压测 | ~15h | 🟢 |

---

## 三、详细阶段计划

---

### 🔴 P0-Round：技术债务清除

**目标**：消除阻碍开发的严重技术债务，建立质量门禁基线

**预估工时**：~4h

**质量门禁**：`pytest tests/ -x` 全部通过 + `ruff check mmi/` 0 error

---

#### P0-1｜cli.py 重构（拆分 command 文件）

```
目标：消除 ~50% 死代码，建立可维护的 CLI 结构

文件结构改造：
  mmi/cli/
  ├── __init__.py
  ├── main.py          ← 精简后的 main()，只做参数解析 + 命令分发
  ├── parser.py        ← build_parser()，子命令注册
  └── commands/
      ├── __init__.py
      ├── new.py       ← cmd_new
      ├── list.py      ← cmd_list
      ├── chat.py      ← cmd_chat
      ├── archive.py   ← cmd_archive
      ├── delete.py    ← cmd_delete
      ├── gc.py        ← cmd_gc
      ├── tui.py       ← cmd_tui
      ├── doctor.py    ← cmd_doctor
      ├── stat.py      ← cmd_stat
      ├── export.py    ← cmd_export
      ├── rename.py    ← cmd_rename
      ├── info.py      ← cmd_info
      ├── inspect.py   ← cmd_inspect
      ├── update.py    ← cmd_update
      ├── memory.py    ← cmd_memory（子命令）
      ├── config.py     ← cmd_config（子命令）
      ├── agent.py     ← cmd_agent（子命令）
      └── skill.py     ← cmd_skill（子命令）
```

**执行步骤**：
1. 新建 `mmi/cli/` + `mmi/cli/commands/` 目录结构
2. 将 `mmi/cli.py` 逐个 `cmd_*` 函数迁移到对应 `commands/*.py`
3. 每个 `cmd_*` 独立文件后，在原位置调用 `from mmi.cli.commands import cmd_new; ...`
4. 删除所有 `return 0` 之后的死代码块
5. 运行 `pytest tests/ -x` 验证无退化
6. ruff check 0 error
7. commit: `refactor(cli): split 1200-line cli.py into command modules`

**验收标准**：
- `mmi --help` 输出与之前完全一致
- 所有子命令 `mmi new / list / chat / archive / delete / gc / tui / doctor / stat / export / rename / info / inspect / update / memory / config / agent / skill` 均正常工作
- `pytest tests/ -x` 全部通过
- ruff check mmi/ 0 error
- `mmi/cli.py` 删除（替换为 `mmi/cli/main.py` + `commands/`）
- 无任何死代码残留

**关键风险**：迁移过程中可能破坏现有命令行为 → **必须逐个迁移、逐个测试**

---

#### P0-2｜安装 ruff 并验证质量门禁

```
目标：在开发环境中安装 ruff，确保 CI/CD 质量门禁可执行
```

**执行步骤**：
1. `pip install ruff`（或 `pip install -e ".[dev]"` 如果加了 dependency-group）
2. `ruff check mmi/`
3. 如果有 error，逐个修复（当前项目声称"0 error"，验证是否真的为 0）
4. 记录 `.ruff.toml` 或 `pyproject.toml [tool.ruff]` 配置（如果需要）

**验收标准**：`ruff check mmi/` 输出 0 error

---

#### P0-3｜sentence-transformers 依赖声明补全

```
目标：用户安装 pip install -e ".[memory]" 时不会缺包
```

**执行步骤**：
1. 编辑 `pyproject.toml`
2. 将 `sentence-transformers>=2.0` 加入 `[project.optional-dependencies]` 的 `memory` 组
3. 验证：`pip install -e ".[memory]"` 成功

**验收标准**：`pip install -e ".[memory]"` 无 ImportError（memory 模块导入成功）

---

### 🟡 P1-Round A：五期核心项

**目标**：解决 P1 级功能缺陷和安全问题

**预估工时**：~8h

**前置条件**：P0-Round 完成

**质量门禁**：pytest 全通过 + ruff 0 error

---

#### P1A-1｜GC 后台自动触发

```
目标：用户不再需要手动运行 mmi gc，系统自动在后台清理

设计：
  - 首次 chat 时启动单例后台线程（daemon）
  - 每次 chat 后检查是否到达 GC 检查间隔（如每 10 次 chat 触发一次）
  - 或定时触发（如每小时一次）
  - 与手动 mmi gc 完全兼容（daemon 只清理 trash/zombie，手动 gc 可清理 cold）
  - 后台异常不阻塞主流程（try-except 包裹）
```

**验收标准**：
- `mmi gc --dry-run` 在新会话运行 24h 后自动触发（不需要用户手动运行）
- 后台异常不影响 `mmi chat` 正常功能
- pytest 有新增测试覆盖后台 GC 逻辑

---

#### P1A-2｜API Key 安全存储

```
目标：消除明文存储风险，支持环境变量引用

实现路径（两种模式）：
  模式1（推荐）：环境变量引用语法
    config.toml: api_key = "${DEEPSEEK_API_KEY}"
    config.py: 读取时检查 "${...}" 格式，从 os.environ 取值

  模式2：keyring 库
    pip install keyring
    存：keyring.set_password("mmi", "api_key", "sk-...")
    取：keyring.get_password("mmi", "api_key")

迁移策略：
  - 向后兼容：旧配置（明文 api_key）继续工作
  - 新增 `api_key_source` 字段："env" | "keyring" | "plain"
  - wizard 引导用户选择存储方式
```

**验收标准**：
- `mmi config show` 不显示完整 api_key（遮蔽为 `sk-***XXXX`）
- `${ENV_VAR}` 语法从 `os.environ` 正确读取
- keyring 模式可存可取
- 旧配置迁移后正常工作

---

#### P1A-3｜Manager 线程安全

```
目标：明确 SessionManager 的线程安全边界，防止用户误用
```

**实现**（二选一）：

**方案 A（文档方案）**：在 `docs/ARCHITECTURE.md` + `SessionManager` docstring 中明确说明"非线程安全，需在调用方加锁"

**方案 B（代码方案）**：`SessionManager` 实例加 `threading.RLock`，在所有 IO 操作前 `with self._lock:`；`batch_*` 接口内部已用 ThreadPoolExecutor 串行化，保证自身安全

**推荐方案 B**（工时相当，长期价值更高）

**验收标准**：
- 并发场景（多线程同时 `manager.chat()`）不出现数据竞争
- docstring 明确线程安全说明
- 新增 `test_manager_thread_safety.py` 覆盖并发场景

---

#### P1A-4｜config Schema 校验

```
目标：防止用户手动编辑 config.toml 写入非法值导致静默错误

实现：
  - 使用 TOML 解析（Python 3.11+ 内置 tomllib，3.11 之前用 tomli）
  - 定义 config schema（如使用 dataclasses + pydantic 或手动校验）
  - 读取时校验每个字段类型/范围
  - 非法配置给出友好错误提示（指出哪个字段、期望值）
```

**验收标准**：
- 写入非法 config 后 `mmi chat` 给出明确错误提示（不静默失败）
- 新增 `test_config_schema.py` 覆盖非法配置场景

---

### 🟡 P1-Round B：TUI MVP

**目标**：将 TypeScript TUI 从当前 MVP 推进到可用状态

**预估工时**：~10h

**前置条件**：P0-Round 完成

**质量门禁**：pytest 全通过 + `cd tui-ts && npm test` 通过

---

#### P1B-1｜合并 feat/tui-redesign 分支

```
目标：将 GitHub 上的 feat/tui-redesign 分支（1a83bf5）合并到 master
```

**执行步骤**：
1. 在本地 checkout feat/tui-redesign
2. 仔细 review 代码差异（该分支有 mockup 重写）
3. 解决可能的合并冲突（可能涉及 tui-ts/src/ 目录）
4. 运行 `npm install && npm run build` 确认构建成功
5. `mmi tui` 启动测试基本交互
6. 合并到 master

**验收标准**：
- merge commit 干净，无冲突未解决
- `mmi tui` 可正常启动并显示界面
- ruff check mmi/ 0 error

---

#### P1B-2｜TUI 真流式输出

```
目标：LLM 返回内容逐 token 流式渲染到 TUI（而非等完整回复后一次性显示）
```

**技术路径**（参考 ARCHITECTURE.md §8.5 / R9.x 计划）：
1. LLM stream_chat() 已在 core/llm.py 实现（Phase 4 成果）
2. IPC 层透传流式数据：Python → Node.js → Ink 组件
3. TUI 端增量渲染（每收到一个 chunk 就更新显示）
4. 流式期间显示加载指示器（spinner / "thinking..."）

**验收标准**：
- 在 TUI 中发起 `mmi chat <session>`，回复内容逐字/逐 token 显示
- 流式过程中可取消（Ctrl+C / /cancel 命令）
- 网络错误时流式中断并显示错误提示

---

#### P1B-3｜TUI 会话列表 + 主题切换

```
目标：TUI 内可直接切换会话、切换明/暗主题
```

**验收标准**：
- `/list` 命令显示所有 active 会话（可上下键选择）
- `/theme` 命令切换明/暗主题，主题持久化到 `~/.mmi/config.toml`
- IPC 通信正常（Python ↔ Node.js ↔ Ink）

---

### 🟢 P2-Round：五期剩余项

**目标**：完成五期剩余改进，提升系统健壮性

**预估工时**：~15h

**前置条件**：P1-Round A + B 完成

**质量门禁**：pytest 全通过 + ruff 0 error

---

#### P2-1｜storage LRU 句柄 + 读写锁

```
目标：减少高频 chat 场景下的重复文件打开/关闭 IO 开销
```

**实现**：
- 在 `storage.py` 维护 LRU 缓存（最近访问的 N 个 session 文件句柄）
- 读写分离：同一文件可并发读，加写锁时阻塞所有读
- 缓存淘汰策略：LRU + 文件大小感知（防止缓存膨胀）

---

#### P2-2｜heat 指数衰减

```
目标：当前线性公式不够精确，改用指数衰减

当前：heat = access_count×1 + recency_bonus - age_penalty（每30天-1）
改进：heat = access_count×1 + Σ(recency_decay) + 衰减因子

状态推导：
  active  → heat >= 10
  warm    → heat >= 5
  cold    → 其他
  zombie  → cold 持续 90 天
```

---

#### P2-3｜classifier 滑动窗口

```
目标：减少 Router 误分类率

实现：
  - 滑动窗口：最近 N 条用户消息作为分类上下文
  - 行为模式识别：同类型问题连续出现 → 路由置信度提升
  - UNKNOWN 分类阈值警告：连续 3 次 UNKNOWN → EventBus 发警告事件
```

---

#### P2-4｜titler 话题偏移检测

```
目标：会话跨度大时（如多天后继续讨论新话题），标题应反映最新主题
```

**触发条件**（待定）：
- 距上次 titler 运行 > 7 天
- 最近 5 轮内容与原 summary 语义相似度 < 阈值 → 触发重新生成标题

---

#### P2-5｜model_fetcher 本地缓存

```
目标：避免每次 mmi config wizard 都拉 API 模型列表

实现：
  - 首次拉取后缓存到 ~/.mmi/model_cache.json
  - 缓存 TTL 可配置（如 7 天）
  - --no-fetch 参数强制使用缓存
```

---

### 🟢 P3-Round：六期生态扩展（上）

**预估工时**：~20h

---

#### P3-1｜Skill 持久化（🔴 最高优先）

```
目标：Skill 数据当前存内存，重启后丢失，需持久化到磁盘
```

**实现**：
- `~/.mmi/skills/` 目录（JSON 文件存储）
- Skill 结构化存储（与 session.md 格式统一）
- CRUD 接口：`mmi skill create / list / search / update / delete`
- Skill 注册/注销事件通过 EventBus 广播

---

#### P3-2｜Trace 持久化（🔴 最高优先）

```
目标：调用链数据无持久化，无法事后审计
```

**实现**：
- `~/.mmi/traces/` 目录（SQLite 或 JSON Lines）
- 存储内容：session_id / agent_id / intent / latency_ms / errors / timestamp
- 查询接口：`mmi trace list <session_id>` 或 `mmi trace stats`
- 隐私合规：不含用户消息内容（仅记录元数据）

---

#### P3-3｜Provider 健康检测 + 自动降级

```
目标：API 故障时无自动降级，当前需要用户手动切换
```

**实现**：
- 首次请求失败后，在后台 ping Provider 端点健康状态
- 连续 N 次失败 → 标记 Provider 为 degraded，自动切换到备选 Provider
- EventBus 发 `provider.degraded` / `provider.switched` 事件

---

#### P3-4｜LLM Deep Audit

```
目标：高风险输出（如代码执行/文件删除/敏感信息）二次审查
```

**实现**（已在 ARCHITECTURE.md §5.3 设计）：
- 第一层：规则引擎（零延迟）
- 第二层：仅在 `auto_audit_threshold`（如 0.7）以上触发 LLM AUDIT 模式审查
- AUDIT 结果通过 EventBus 广播，可由 TUI 展示

---

### 🟢 P4-Round：六期进阶

**预估工时**：~15h

---

#### P4-1｜自定义 Provider 插件注册

```
目标：用户可注册自己的 Provider（不限于预置 5 家）
```

**实现**：
- Provider 抽象层 + 插件发现机制（扫描 `~/.mmi/providers/` 目录）
- 注册协议：实现 `LLMProvider` 抽象类 + 导出 `entry_point`
- `mmi config wizard` 显示自定义 Provider

---

#### P4-2｜Web GUI（Vue3）

```
目标：非命令行用户提供图形界面

路径（参考 ARCHITECTURE.md §6.12）：
- 前端：Vue3 + Vite（与 TUI 分离，独立项目）
- 通信：REST API（FastAPI / Flask）或 WebSocket
- 核心功能与会话管理同 CLI

注意：等核心能力稳定后再做（P3 完成后再启动）
```

---

#### P4-3｜MCP (Model Context Protocol) 集成

```
目标：让 MMI 作为 MCP Server，为 Cursor / Claude Desktop 等工具提供工具调用能力
```

**实现**：
- 实现 MCP Server 协议（参考官方规范）
- 暴露 mmi session/memory/agent 等能力为 MCP Tools
- 注册到 Claude Desktop / Cursor 等 MCP Clients

---

#### P4-4｜评估框架 + 性能压测

```
目标：建立可量化的质量评估体系

评估维度：
  - Router 分类准确率（EventBus 埋点 + ground truth 数据集）
  - Context 截断质量（对比原始上下文 vs 截断后上下文的 LLM 回答质量）
  - Memory 召回准确率（recall@k 指标）
  - Pipeline 端到端延迟（p50 / p95 / p99）

压测：
  - 100 / 500 / 1000 并发 session 场景
  - 长对话（1000+ 轮）稳定性
  - FAISS 索引 10k 条记忆检索延迟
```

---

## 四、质量门禁规范（每阶段必须通过）

| 门禁项 | 命令 | 标准 |
|--------|------|------|
| 测试全量 | `pytest tests/ -x` | 全部 passed |
| 代码检查 | `ruff check mmi/` | 0 error |
| 类型检查 | `mypy mmi/ --ignore-missing-imports`（如果项目配置了 mypy） | 0 error |
| TUI 构建 | `cd tui-ts && npm run build` | 构建成功，产物存在 |
| 冒烟测试 | `mmi doctor` | 全部诊断项通过 |

---

## 五、每轮工作规范

```
每轮开始前：
  1. 从 master 新建分支：git checkout -b round_X_name
  2. 阅读上轮交接文档 docs/handover-history/round_X-1.md
  3. 确认本轮任务清单（本计划书对应行）

每轮进行中：
  1. 任务按 P0 → P1 → P2 顺序处理
  2. 每完成一个任务写 commit（格式：type(scope): description）
  3. pytest 全通过后再做下一个任务（避免问题积累）
  4. 记录 ROUND_LOG.md 实时日志

每轮结束后：
  1. 运行全量测试 + ruff check
  2. 写 docs/handover-history/round_X.md（交接文档）
  3. 更新 docs/handover-history/INDEX.md
  4. 更新本计划书状态列
  5. PR 到 master（或直接 merge）
  6. 更新 ROUND_LOG.md
```

---

## 六、状态追踪

| 阶段 | 状态 | 完成时间 | 备注 |
|------|------|---------|------|
| P0-Round 技术债务清除 | ⬜ 待开始 | - | |
| ↳ P0-1 cli.py 重构 | ⬜ | - | |
| ↳ P0-2 ruff 安装验证 | ⬜ | - | |
| ↳ P0-3 sentence-transformers 依赖 | ⬜ | - | |
| P1-Round A 五期核心项 | ⬜ 待开始 | - | |
| ↳ P1A-1 GC 后台触发 | ⬜ | - | |
| ↳ P1A-2 API Key 安全存储 | ⬜ | - | |
| ↳ P1A-3 Manager 线程安全 | ⬜ | - | |
| ↳ P1A-4 config Schema 校验 | ⬜ | - | |
| P1-Round B TUI MVP | ⬜ 待开始 | - | |
| ↳ P1B-1 合并 tui-redesign | ⬜ | - | |
| ↳ P1B-2 TUI 真流式输出 | ⬜ | - | |
| ↳ P1B-3 会话列表 + 主题切换 | ⬜ | - | |
| P2-Round 五期剩余项 | ⬜ 待开始 | - | |
| P3-Round 六期生态扩展 | ⬜ 待开始 | - | |
| ↳ P3-1 Skill 持久化 | ⬜ | - | |
| ↳ P3-2 Trace 持久化 | ⬜ | - | |
| ↳ P3-3 Provider 健康检测 | ⬜ | - | |
| ↳ P3-4 LLM Deep Audit | ⬜ | - | |
| P4-Round 六期进阶 | ⬜ 待开始 | - | |
| ↳ P4-2 Web GUI | ⬜ | - | |
| ↳ P4-3 MCP 集成 | ⬜ | - | |
| ↳ P4-4 评估框架 | ⬜ | - | |

---

## 七、推荐启动顺序

```
下一步（今天/明天）：
  → 开始 P0-Round
    1. 先做 P0-2（ruff 安装），验证当前项目 ruff 0 error 基线
    2. 再做 P0-3（sentence-transformers 依赖补全）
    3. 最后做 P0-1（cli.py 重构，最费时但最重要）

下一 round：
  → P1-Round A（五期核心）
    1. P1A-1 GC 后台触发（用户最痛点）
    2. P1A-2 API Key 安全存储
    3. P1A-3 Manager 线程安全
    4. P1A-4 config Schema 校验

再下一 round：
  → P1-Round B（TUI）
    1. P1B-1 合并 tui-redesign
    2. P1B-2 + P1B-3

再再下一 round：
  → P2-Round + P3-Round Skill/Trace 持久化
```

---

> 接手者：**先做 P0-Round** → pytest 全通过 + ruff 0 error 后 → 接 P1-Round A