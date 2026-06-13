# MMI — Multimodal Intelligence 多模态智能体系统

> 带记忆引擎与多Agent调度的智能体系统。
> 从 [C-Trim](https://github.com/sansan1983/ctrim) 演进而来。

## 特性

- **三层架构**：接入层（CLI/TUI/MCP）→ Agent调度层 → 记忆引擎层
- **记忆引擎**：FAISS语义检索 + SQLite FTS5关键词 + LLM重排 + 内存池
- **多Agent调度**：主Agent → 意图分类 → 路由到子Agent/思维模式
- **Provider插件系统**：支持5家预置商 + 自定义Python插件（`~/.mmi/providers/`）
- **MCP Server**：暴露MMI能力为MCP Tools，支持Claude Desktop / Cursor接入
- **评估框架**：ExactMatch/Contains/Func评估器，延迟统计（p50/p95/p99）
- **TUI界面**：Textual终端UI，支持真流式输出、主题切换
- **健康检测**：Provider自动降级，连续3次失败→切换

## 架构

```
mmi/
├── core/              # 记忆引擎层（会话/上下文/摘要/检索/热度/GC/评估/MCP）
│   ├── llm.py        # LLMProvider抽象 + 5家预置实现
│   ├── provider_registry.py  # 自定义Provider插件发现
│   ├── memory.py     # MemoryEngine（FAISS + SQLite + 内存池）
│   ├── evaluation.py  # EvalRunner评估框架
│   ├── mcp_server.py # MCP Server（JSON-RPC 2.0）
│   └── ...
├── agent/            # Agent调度层（路由/思维模式/技能/Tool/追踪/EventBus）
├── cli/              # CLI命令（new/list/chat/tui/doctor/stat）
├── tui/              # 终端UI（textual）
└── tools/            # 诊断工具
```

完整架构见 `MMI统一架构设计.md`。

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/sansan1983/mmi.git
cd mmi

# 安装（推荐可编辑模式）
pip install -e ".[tui,fuzzy]"

# 安装预提交钩子（可选）
pre-commit install
```

### 配置

```bash
# 交互式配置向导
mmi config wizard

# 或手动编辑 ~/.mmi/config.toml
cat > ~/.mmi/config.toml << EOF
[llm]
provider = "deepseek"          # deepseek / glm / qwen / minimax
api_key = "sk-..."            # 或用环境变量 DEEPSEEK_API_KEY
model = "deepseek-chat"
base_url = "https://api.deepseek.com"
api_style = "openai"
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

# 启动TUI（推荐）
mmi tui

# 诊断
mmi doctor

# 统计
mmi stat
```

## 进阶功能

### 1. 自定义Provider插件

在 `~/.mmi/providers/` 下创建Python文件：

```python
# ~/.mmi/providers/my_provider.py
from mmi.core.llm import LLMProvider, LLMError, Classification

class MyProvider(LLMProvider):
    name = "my-provider"
    
    def __init__(self, api_key: str, model: str = "v1", **kwargs):
        self._key = api_key
        self._model = model
    
    def chat(self, messages, *, max_tokens=4096, temperature=0.7):
        # 实现你的LLM调用
        ...
    
    def classify(self, prompt, *, options):
        return Classification(choice=options[0], confidence=1.0)
```

然后在 `config.toml` 中配置：

```toml
[llm]
provider = "my-provider"
api_key = "your-key"
model = "v1"
```

### 2. MCP Server（接入Claude Desktop / Cursor）

在Claude Desktop配置中添加：

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

可用的MCP Tools：
- `mmi_list_sessions` — 列出所有会话
- `mmi_get_session` — 获取会话详情
- `mmi_chat` — 发送消息并获取回复
- `mmi_list_skills` — 列出已注册技能
- `mmi_search_memory` — 搜索记忆
- `mmi_get_stats` — 获取系统统计

### 3. 评估框架

```python
from mmi.core.evaluation import EvalRunner, ExactMatchEvaluator, EvalSample

runner = EvalRunner()
samples = [
    EvalSample(input_text="hello", expected_output="world", actual_output="world"),
    ...
]
report = runner.run(name="my-eval", samples=samples, evaluator=ExactMatchEvaluator())
print(report.summary())
```

### 4. 健康检测

自动启用，无需配置。当Provider连续3次失败时自动降级，成功时恢复。

手动查询：

```python
from mmi.core.provider_health import get_healthy_provider
provider = get_healthy_provider()
```

## CLI命令参考

| 命令 | 说明 |
|------|------|
| `mmi new <name>` | 创建新会话 |
| `mmi list` | 列出所有会话 |
| `mmi chat <session_id> <message>` | 发送消息 |
| `mmi tui` | 启动终端UI |
| `mmi config wizard` | 交互式配置 |
| `mmi config show` | 显示当前配置 |
| `mmi doctor` | 诊断系统状态 |
| `mmi stat` | 显示统计信息 |
| `mmi gc` | 手动触发垃圾回收 |
| `mmi export <session_id>` | 导出会话 |

## 测试

```bash
# 运行所有测试
python -m pytest tests/ -x

# 运行特定模块测试
python -m pytest tests/test_integration.py -xvs
python -m pytest tests/test_benchmark.py -xvs

# 检查代码质量
ruff check mmi/
```

## 设计文档

| 文档 | 说明 |
|------|------|
| `MMI统一架构设计.md` | 完整架构设计 |
| `MMI_PHASE_PLAN.md` | 分期开发计划 |
| `RULES.md` | 工作规范 |

## 许可证

MIT License
