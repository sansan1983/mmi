# P1A-Round 完成报告

**日期**: 2026-06-12
**分支**: p1a-round (`c99bcc0`)
**测试结果**: 576 passed, 1 pre-existing failure

## 任务完成状态

| Task | 状态 | 文件 | 说明 |
|------|------|------|------|
| P1A-1 GC 后台自动触发 | ✅ | `mmi/core/gc_daemon.py` | DaemonGC 单例，on_chat_done 计数触发，16 tests |
| P1A-2 API Key 安全存储 | ✅ | `mmi/core/config.py` | mask_api_key + resolve_api_key + env var 回退 |
| P1A-3 Manager 线程安全 | ✅ | `mmi/core/manager.py` | RLock 保护 create/_recompute_heat |
| P1A-4 Config Schema 校验 | ✅ | `tests/test_config_schema.py` | 35 tests |

## 修复的测试失败

1. **mask_api_key** — 短密钥边界条件：修复 `key_body[-visible_chars:]` 逻辑，`sk-ab`→`sk-***`，`sk-abcde`→`sk-***cde`
2. **resolve_api_key** — unknown provider env var 回退：添加 `f"{provider.upper()}_API_KEY"` 兜底
3. **_atomic_write** — Windows PermissionError：添加 `_unlink_with_retry` 指数退避重试
4. **batch_chat** — orchestrator 调用：_run 调用 `self.orchestrator.chat`，补 orchestrator MagicMock
5. **concurrent_chat** — `manager.count()` 不存在，改为 `len(list_session_ids())`
6. **test_config_schema** — 移除未使用的 `os`/`patch` 导入

## 关键代码变更

- `mmi/core/gc_daemon.py` (new) — GC daemon 实现
- `mmi/core/config.py` — mask_api_key 重写，resolve_api_key 回退逻辑
- `mmi/core/manager.py` — RLock 保护，batch_chat _run 修复
- `tests/test_config_schema.py` (new) — 35 个配置测试
- `tests/test_gc_daemon.py` (new) — 16 个 GC daemon 测试
- `tests/test_manager_thread_safety.py` (new) — 线程安全测试

## 下一步

按计划进入 **P1-Round B (TUI MVP)**：
- 从 `feat/tui-redesign` 分支合并 TUI 代码
- 流式 IPC 透传 chunk 增量渲染
- TUI 入口命令注册

## 预Existing 失败（与本阶段无关）

- `tests/tui-ts/test_e2e.py::test_bundle_renders_sessionhub_and_does_not_crash` — Windows `python3` 路径问题