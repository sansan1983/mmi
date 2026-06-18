# AGENTS.md — MMI

> MMI (Multimodal Intelligence): a Python agent framework with FAISS + SQLite
> FTS5 memory, multi-agent routing, MCP server, and a Python TUI.
>
> Read first: `CLAUDE.md` (handover table at the top + iron rules) and
> `docs/INDEX.md` (doc map). This file is the OpenCode-specific complement —
> things that are non-obvious from filenames or not covered there.

## Stack & entry points

- Python 3.11+ (CI pins 3.12). `pyproject.toml` is the only manifest; build
  backend is setuptools.
- CLI script `mmi` → `mmi.cli.main:main` (defined in `[project.scripts]`).
- `python -m mmi` → `mmi/__main__.py` (calls `cli.main:main`).
- MCP server: `python -m mmi.core.mcp_server`.
- Install: `pip install -e ".[tui,fuzzy]"` for the documented baseline.
  CI uses `pip install -e ".[all]"` (includes faiss-cpu, numpy,
  sentence-transformers, tiktoken, ruff, pytest). Optional extras:
  `[memory]`, `[context]`, `[dev]`, `[test]`.

## Package layout

```
mmi/
├── core/         # memory engine + session lifecycle — UI-agnostic, must not import UI
├── agent/        # orchestrator, router, registry, skills, tools, validator, tracer
├── cli/
│   ├── main.py   # arg parse + _dispatch() that routes to commands/<name>.py
│   └── commands/ # one cmd_<name>.py per subcommand (21 of them)
├── tui_v3.py     # the only TUI — Python, no tui-ts/ in the tree
└── tools/        # doctor, etc.
```

Hard rule from `docs/ARCHITECTURE.md`: `mmi/core/` does not import from
`mmi/cli/`, `mmi/tui_v3.py`, or `mmi/agent/builtin/` (UI/tool plugins).
Cross-layer calls go through `mmi.core.manager.SessionManager` (the facade).
Public API is re-exported from `mmi/core/__init__.py` — add new public
symbols there too.

## CLI subcommand pattern

Adding a new subcommand requires exactly three edits, all in `mmi/cli/`:

1. Register the parser in `mmi/cli/parser.py` (`build_parser()`).
2. Implement `cmd_<name>(args, mgr) -> int` in `mmi/cli/commands/<name>.py`.
3. Add a dispatch branch in `mmi/cli/main.py` `_dispatch()` (lazy import
   inside the elif — pattern is already established; do not eager-import).

Subcommands return 0 on success, non-zero on error, write errors to
`stderr` and success to `stdout`. Subcommand files call
`ensure_mmi_home()` from `mmi.cli` to default `MMI_HOME` to `~/.mmi/`.

## Data directory

- Root: `~/.mmi/` (overridable with the `MMI_HOME` env var — tests rely on
  this; see `isolated_home` fixture in `tests/conftest.py`).
- Layout (created idempotently by `mmi.core.paths.ensure_dirs()`):
  - `sessions/active/<id>.session.md` — YAML frontmatter + Markdown body
  - `sessions/trash/` — soft-deleted sessions with TTL
  - `memory.db` (SQLite FTS5) + `faiss.index` + `faiss_ids.json`
  - `skills/<id>.json`, `traces/<id>.jsonl`
  - `config.toml` — LLM provider config
- Session IDs are **ULID** (26 chars). Storage uses `portalocker` for
  cross-process exclusive locks; never read a session file directly — go
  through `mmi.core.storage` / `SessionManager`.
- Atomic writes are required: write to `<file>.tmp` in the same directory,
  then `os.replace()` to the final name. There is no single `_atomic_write`
  helper — the pattern is repeated; do not introduce one unless asked.

## Conventions (iron rules in this repo)

- **No `print()` in `mmi/core/`.** All user-visible strings go through
  `t()` from `mmi.core.i18n`. Locales live in `mmi/core/locales/{zh-CN,en-US}.json`.
  Adding a string requires adding both locale entries.
- Type annotations on every public function's parameters and return type.
  Internal subclass overrides follow the parent signature.
- No code comments unless the user asks. Existing docstrings in
  Chinese are fine — don't translate or restyle them.
- No test skips. `pytest tests/ -x` must pass with no `pytest.skip` /
  `pytest.mark.skip` left in. The whole suite should run.
- `SessionState` is a 4-state heat machine: `ACTIVE` (heat ≥ 10),
  `WARM` (≥ 5), `COLD`, `ZOMBIE` (cold > 90 days). State transitions live
  in `mmi/core/heat.py`.
- Custom LLM provider plugins: drop a Python file into
  `~/.mmi/providers/` subclassing `mmi.core.llm.LLMProvider`. Set
  `name = "<id>"` and reference it from `config.toml`'s `[llm].provider`.

## Quality gates (must pass before commit)

Run both, in this order. The CI workflow at `.github/workflows/ci.yml`
is the source of truth.

```bash
ruff check mmi/         # note: scope is mmi/, not . (the roadmap text says "." but CI and pyproject both scope to mmi/)
pytest tests/ -x        # -x stops on first failure; don't remove it
```

Optional / slower:

```bash
pytest tests/test_integration.py -xvs   # cross-module integration
pytest tests/test_benchmark.py -xvs     # perf baseline
```

## Test infrastructure

- `tests/conftest.py` provides `isolated_home` (sets `MMI_HOME` to a
  `tmp_path`), `scripted_llm_factory`, and `new_sid()`. Use `isolated_home`
  whenever a test touches the filesystem; do not set `MMI_HOME` manually.
- `tests/_fakes.py` holds shared fakes: `ScriptedLLM` (preset
  replies/stream chunks), `KeywordStubLLM`, `MinimalStubLLM`. Import from
  `tests._fakes` (or use the `scripted_llm_factory` fixture).
- `collect_ignore_glob = ["test_cli.py"]` in `conftest.py` is a deliberate
  archive guard — **do not** reintroduce `tests/test_cli.py`.
- LLM calls in tests must go through the scripted fakes. Real network is
  never required; do not add API-key-dependent tests.

## Things that will trip you up

- **No `tui-ts/` directory.** It was removed (see `CLAUDE.md` 模块 table).
  Don't recreate TypeScript TUI work — only `mmi/tui_v3.py` is supported.
- **`docs/RULES.md` does not exist.** The only `RULES.md` in the tree is
  `docs/handover-history/archive/old-plans/RULES.md` (archived). The active
  rules live in `CLAUDE.md`.
- **`WORKLOG.md` is referenced in `CLAUDE.md` but does not exist yet.**
  The convention is: at end of session, move old rows from the "近期日志"
  table in `CLAUDE.md` to `WORKLOG.md`. Create it on first use; do not
  skip the handover.
- **Untracked runtime dirs in the working tree:** `.codegraph/`,
  `.learnings/`, `.reasonix/`, `reasonix.toml`. These belong to the local
  OpenCode/Reasonix runtime, not the project. Do not commit, modify, or
  gitignore-touch them unless asked.
- **`mmi/cli/main.py` is a dispatcher, not a command implementation.**
  Don't add new subcommand logic there — put it in `commands/<name>.py`.
- **Provider registry imports are lazy** in `main.py` to avoid circular
  imports; follow the same pattern when adding new dispatch branches.
- **Branching convention:** `master` is the integration branch; work
  branches observed: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`,
  `p1a-round`. No protected-branch rules in `.github/workflows/ci.yml` —
  CI runs on push/PR to `master` and `main`.

## Key files to read before changing code

| Concern | File |
|---|---|
| Handover + rules | `CLAUDE.md` (top table + §2) |
| Roadmap | `docs/ROADMAP/DEVELOPMENT_ROADMAP.md` |
| Architecture | `docs/ARCHITECTURE.md` |
| Test policy | `docs/TESTS/test-policy.md` |
| Session lifecycle | `mmi/core/session.py`, `mmi/core/storage.py`, `mmi/core/heat.py` |
| Memory engine | `mmi/core/memory.py`, `mmi/core/search.py`, `mmi/core/summarizer.py` |
| Agent dispatch | `mmi/agent/orchestrator.py`, `mmi/agent/router.py` |
| LLM providers | `mmi/core/llm.py`, `mmi/core/provider_registry.py`, `mmi/core/provider_health.py` |
| Public facade | `mmi/core/manager.py` |
| CLI dispatch | `mmi/cli/main.py`, `mmi/cli/parser.py` |
| MCP surface | `mmi/core/mcp_server.py` |
