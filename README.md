# MMI — 多模态智能体系统

> 带记忆引擎与多 Agent 调度的新一代智能体框架。

[![GitHub](https://img.shields.io/badge/GitHub-sansan1983%2Fmmi-brightgreen?style=flat-square&logo=github)](https://github.com/sansan1983/mmi)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Ruff](https://img.shields.io/badge/ruff-0%20errors-brightgreen?style=flat-square)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](LICENSE)

**[English](README_en.md)** · **[开发文档](docs/INDEX.md)** · **[开发路线图](docs/ROADMAP/DEVELOPMENT_ROADMAP.md)**

---

## 是什么

MMI（Multimodal Intelligence）是一个**带记忆引擎的多 Agent 智能体框架**。

它的核心能力是：**让 AI 在多轮对话中真正记住上下文**——不是靠每次把历史发回去，而是通过 FAISS 向量语义检索 + SQLite FTS5 关键词双路搜索 + LLM 动态重排，自动构建最优上下文。

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **三层记忆架构** | FAISS 向量检索 → SQLite FTS5 关键词 → LLM 重排，三路合并去重 |
| **动态上下文窗口** | 根据 token 余量自适应调整上下文，精确截断不丢关键信息 |
| **多 Agent 调度** | 主 Agent → 意图分类 → 路由到子 Agent / 思维模式 |
| **Provider 插件系统** | 支持 5 家预置 LLM 商 + 自定义 Python 插件 |
| **MCP Server** | 暴露为 MCP Tools，接入 Claude Desktop / Cursor |
| **评估框架** | ExactMatch / Contains / Func 评估器 + 延迟统计（p50/p95/p99） |
| **健康检测** | Provider 自动降级，连续 3 次失败自动切换 |

---

## 架构

```
接入层（CLI / TUI） → Agent 调度层（意图分类 / 路由） → 记忆引擎层
                                              ↓
                                    FAISS + SQLite FTS5 + LLM 重排
```

```
mmi/
├── core/              # 记忆引擎层（session / storage / context / memory / heat / gc / evaluation / mcp）
│   ├── llm.py        # LLMProvider 抽象 + 5 家预置实现
│   ├── provider_registry.py  # 自定义 Provider 插件发现
│   ├── memory.py     # MemoryEngine（FAISS + SQLite + 内存池）
│   ├── context.py    # 上下文构建（三源合并 + 优先级截断）
│   ├── summarizer.py # 摘要生成 + 版本链 + 后台线程
│   ├── evaluation.py # EvalRunner 评估框架
│   ├── mcp_server.py  # MCP Server（JSON-RPC 2.0）
│   └── ...
├── agent/            # Agent 调度层（路由 / 思维模式 / 技能 / Tool / 追踪）
├── cli/              # CLI 命令（new / list / chat / tui / doctor / stat）
└── tools/            # 诊断工具
```

完整架构见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---

## 快速开始

### 安装

```bash
git clone https://github.com/sansan1983/mmi.git
cd mmi
pip install -e ".[tui,fuzzy]"
```

### 配置

```bash
# 交互式配置向导（推荐）
mmi config wizard

# 或手动编辑 ~/.mmi/config.toml
cat > ~/.mmi/config.toml << 'EOF'
[llm]
provider = "deepseek"
api_key = "sk-..."
model = "deepseek-chat"
base_url = "https://api.deepseek.com/v1"
EOF
```

### 使用

```bash
# 创建会话
mmi new "我的第一个会话"

# 列出所有会话
mmi list

# 发送消息
mmi chat <session_id> "你好"

# 启动 TUI（推荐）
mmi tui

# 诊断系统状态
mmi doctor

# 查看统计
mmi stat
```

---

## 进阶功能

### 自定义 Provider 插件

在 `~/.mmi/providers/` 下创建 Python 文件：

```python
# ~/.mmi/providers/my_provider.py
from mmi.core.llm import LLMProvider, LLMError, Classification

class MyProvider(LLMProvider):
    name = "my-provider"

    def __init__(self, api_key: str, model: str = "v1", **kwargs):
        self._key = api_key
        self._model = model

    def chat(self, messages, *, max_tokens=4096, temperature=0.7):
        # 实现你的 LLM 调用
        ...

    def classify(self, prompt, *, options):
        return Classification(choice=options[0], confidence=1.0)
```

然后在 `config.toml` 中配置 `provider = "my-provider"` 即可。

### MCP Server（接入 Claude Desktop / Cursor）

在 Claude Desktop 配置中添加：

```json
{
  "mcpServers": {
    "mmi": {
      "command": "python",
      "args": ["-m", "mmi.core.mcp_server"]
    }
  }
}
```

可用的 MCP Tools：`mmi_list_sessions` · `mmi_get_session` · `mmi_chat` · `mmi_list_skills` · `mmi_search_memory` · `mmi_get_stats`

### 评估框架

```python
from mmi.core.evaluation import EvalRunner, ExactMatchEvaluator, EvalSample

runner = EvalRunner()
samples = [
    EvalSample(input_text="hello", expected_output="world", actual_output="world"),
]
report = runner.run(name="my-eval", samples=samples, evaluator=ExactMatchEvaluator())
print(report.summary())
```

---

## CLI 命令

| 命令 | 说明 |
|------|------|
| `mmi new <name>` | 创建新会话 |
| `mmi list` | 列出所有会话 |
| `mmi chat <session_id> <message>` | 发送消息 |
| `mmi tui` | 启动终端 UI（推荐） |
| `mmi config wizard` | 交互式配置 |
| `mmi config show` | 显示当前配置 |
| `mmi doctor` | 诊断系统状态 |
| `mmi stat` | 显示统计信息 |
| `mmi gc` | 手动触发垃圾回收 |
| `mmi export <session_id>` | 导出会话 |

---

## 测试

```bash
# 运行所有测试
pytest tests/ -x

# 代码质量检查
ruff check mmi/
```

---

## 开发路线图

当前阶段：**Phase 0｜止血** — Python TUI 修复 + GC 集成 + 质量门禁

完整路线图见 [docs/ROADMAP/DEVELOPMENT_ROADMAP.md](docs/ROADMAP/DEVELOPMENT_ROADMAP.md)。

---

## 文档

| 文档 | 用途 |
|------|------|
| [docs/INDEX.md](docs/INDEX.md) | 文档总入口（**先读**） |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构设计 |
| [docs/ROADMAP/DEVELOPMENT_ROADMAP.md](docs/ROADMAP/DEVELOPMENT_ROADMAP.md) | 开发路线图 |
| [CLAUDE.md](CLAUDE.md) | AI 开发规范（铁律，必读） |
| [docs/TESTS/test-policy.md](docs/TESTS/test-policy.md) | 测试规范 |