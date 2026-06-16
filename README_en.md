# MMI — Multimodal Intelligence Agent System

> A next-generation agent framework with memory engine and multi-Agent scheduling.

[![GitHub](https://img.shields.io/badge/GitHub-sansan1983%2Fmmi-brightgreen?style=flat-square&logo=github)](https://github.com/sansan1983/mmi)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Ruff](https://img.shields.io/badge/ruff-0%20errors-brightgreen?style=flat-square)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow?style=flat-square)](LICENSE)

**[中文](README.md)** · **[开发文档](docs/INDEX.md)** · **[Development Roadmap](docs/ROADMAP/DEVELOPMENT_ROADMAP.md)**

---

## What Is It

MMI (Multimodal Intelligence) is a **multi-Agent intelligent agent framework with a memory engine**.

Its core capability: **enabling AI to truly remember context across multi-turn conversations** — not by sending the full history every time, but through FAISS semantic retrieval + SQLite FTS5 keyword search + LLM dynamic re-ranking, automatically constructing the optimal context.

---

## Key Features

| Feature | Description |
|---------|-------------|
| **Three-Layer Memory Architecture** | FAISS vector search → SQLite FTS5 keyword → LLM re-ranking, three-way merge with deduplication |
| **Dynamic Context Window** | Adaptive context size based on token budget, precise truncation preserving critical info |
| **Multi-Agent Scheduling** | Main Agent → Intent Classification → Route to sub-Agents / thinking modes |
| **Provider Plugin System** | 5 built-in LLM providers + custom Python plugins |
| **MCP Server** | Exposed as MCP Tools, works with Claude Desktop / Cursor |
| **Evaluation Framework** | ExactMatch / Contains / Func evaluators + latency stats (p50/p95/p99) |
| **Health Detection** | Provider auto-fallback, auto-switch after 3 consecutive failures |

---

## Architecture

```
Access Layer (CLI / TUI) → Agent Scheduling Layer (intent classification / routing) → Memory Engine Layer
                                              ↓
                                    FAISS + SQLite FTS5 + LLM Re-ranking
```

```
mmi/
├── core/              # Memory engine layer (session / storage / context / memory / heat / gc / evaluation / mcp)
│   ├── llm.py        # LLMProvider abstract + 5 built-in implementations
│   ├── provider_registry.py  # Custom Provider plugin discovery
│   ├── memory.py     # MemoryEngine (FAISS + SQLite + memory pool)
│   ├── context.py    # Context construction (three-source merge + priority truncation)
│   ├── summarizer.py # Summarization + version chain + background thread
│   ├── evaluation.py # EvalRunner evaluation framework
│   ├── mcp_server.py  # MCP Server (JSON-RPC 2.0)
│   └── ...
├── agent/            # Agent scheduling layer (routing / thinking modes / skills / tools / tracing)
├── cli/              # CLI commands (new / list / chat / tui / doctor / stat)
└── tools/            # Diagnostic tools
```

Full architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Quick Start

### Install

```bash
git clone https://github.com/sansan1983/mmi.git
cd mmi
pip install -e ".[tui,fuzzy]"
```

### Configure

```bash
# Interactive config wizard (recommended)
mmi config wizard

# Or manually edit ~/.mmi/config.toml
cat > ~/.mmi/config.toml << 'EOF'
[llm]
provider = "deepseek"
api_key = "sk-..."
model = "deepseek-chat"
base_url = "https://api.deepseek.com/v1"
EOF
```

### Usage

```bash
# Create a new session
mmi new "My first session"

# List all sessions
mmi list

# Send a message
mmi chat <session_id> "Hello"

# Start TUI (recommended)
mmi tui

# Diagnose system status
mmi doctor

# View statistics
mmi stat
```

---

## Advanced Features

### Custom Provider Plugins

Create a Python file in `~/.mmi/providers/`:

```python
# ~/.mmi/providers/my_provider.py
from mmi.core.llm import LLMProvider, LLMError, Classification

class MyProvider(LLMProvider):
    name = "my-provider"

    def __init__(self, api_key: str, model: str = "v1", **kwargs):
        self._key = api_key
        self._model = model

    def chat(self, messages, *, max_tokens=4096, temperature=0.7):
        # Implement your LLM call here
        ...

    def classify(self, prompt, *, options):
        return Classification(choice=options[0], confidence=1.0)
```

Then set `provider = "my-provider"` in `config.toml`.

### MCP Server (Claude Desktop / Cursor)

Add to Claude Desktop config:

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

Available MCP Tools: `mmi_list_sessions` · `mmi_get_session` · `mmi_chat` · `mmi_list_skills` · `mmi_search_memory` · `mmi_get_stats`

### Evaluation Framework

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

## CLI Commands

| Command | Description |
|---------|-------------|
| `mmi new <name>` | Create a new session |
| `mmi list` | List all sessions |
| `mmi chat <session_id> <message>` | Send a message |
| `mmi tui` | Start terminal UI (recommended) |
| `mmi config wizard` | Interactive configuration |
| `mmi config show` | Show current config |
| `mmi doctor` | Diagnose system status |
| `mmi stat` | Show statistics |
| `mmi gc` | Manually trigger garbage collection |
| `mmi export <session_id>` | Export a session |

---

## Testing

```bash
# Run all tests
pytest tests/ -x

# Code quality check
ruff check mmi/
```

---

## Development Roadmap

Current stage: **Phase 0｜止血 (Stabilization)** — Python TUI fixes + GC integration + quality gates

Full roadmap: [docs/ROADMAP/DEVELOPMENT_ROADMAP.md](docs/ROADMAP/DEVELOPMENT_ROADMAP.md).

---

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/INDEX.md](docs/INDEX.md) | Documentation index (**start here**) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture design |
| [docs/ROADMAP/DEVELOPMENT_ROADMAP.md](docs/ROADMAP/DEVELOPMENT_ROADMAP.md) | Development roadmap |
| [CLAUDE.md](CLAUDE.md) | AI development rules (iron laws, required reading) |
| [docs/TESTS/test-policy.md](docs/TESTS/test-policy.md) | Testing standards |