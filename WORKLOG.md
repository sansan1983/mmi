# WORKLOG

> 完整历史日志。近期 3 条见 `CLAUDE.md` 顶部「近期日志」表。

| 日期 | 动作 | 产出 |
| 2026-06-18 | P7：抽 chat.py --inspect 模式为 _chat_inspect helper | chat.py -29 行（30 行内联 → 1 行 dispatch） |
| 2026-06-18 | P6：补全 cmd_*.py 公共 API 类型标注 | 18 + 8 + 2 函数加 `args: Namespace, mgr: SessionManager` |
| 2026-06-18 | P5：i18n 化 config.py wizard + show | 38 词条（wizard.* 36 + config_show.* 2） |
| 2026-06-18 | P4：i18n 化 12 个 cmd_*.py 硬编码 | 3 批 ~80 处 print → `i18n.t(...)` + 70+ 词条。跳过 config.py wizard 32 处 |
| 2026-06-18 | P3-E：拆 `tui_v3.py` 810 行 → `tui_v3/` 包 | 5 子模块（872 行）+ `__init__.py` 45 行 re-export。零 test 改动 |
| 2026-06-18 | P3-D：拆 `core/memory.py` 978 行 → `core/memory/` 包 | 9 子模块（1033 行）+ `__init__.py` 155 行（PEP 562 `__getattr__` 转发）。store.py 用 `_faiss_mod` 模块引用避免 stale binding。3 test monkeypatch 改 `memory.faiss._XXX`。顺手修 `memory_tools.py:72` 死代码 |
| 2026-06-18 | P3-C：拆 `core/llm.py` → `core/llm/` 包 | 7 子模块（881 行总和） + `__init__.py` re-export（50 行），6 test mock 路径更新 |
| 2026-06-18 | P3-B：`manager.chat`+`stream_chat` 抽 `_post_chat_pipeline` | 净 -19 行（+65/-84），顺手修复 `stream_chat` trashed 时丢 `trashed_reason` 的 bug |
| 2026-06-18 | P3-A：`cli/main.py::_dispatch` 70 行 elif 改 dict 查表 | 净 -27 行（+39/-66），`_COMMANDS` 字典 + `_load_command` 懒加载 |
| 2026-06-18 | P2 步骤 1：`require_session` helper 抽取 | 7 CLI 命令去重，-20 行；新增 `cli.unknown_session` i18n；修 `inspect.py` 宽 except |
| 2026-06-17 | 全量代码审查 + P0/P1 死代码清理（3 bug + -1413 行） | 20 文件改，+14/-1427；6 文件删：utils/audit/provider_health + 对应 test + _test_heat_bak |
| 2026-06-17 | Phase 0+1 全部完成 + 质量门禁全修复（ruff 270+ auto-fix + _INMEM_DIRTY bug + 原子写） | 7 commits (b0e3c26, 2a8c1d0, afd36cb, cc1e113, 9163869, ae63894, 871b593) |
| 2026-06-16 | 文档全盘整理 + 路线图 v2.0 | `docs/ROADMAP/DEVELOPMENT_ROADMAP.md` |
| 2026-06-16 | 项目根目录清理 | 删除 8 个无关目录/文件 |
