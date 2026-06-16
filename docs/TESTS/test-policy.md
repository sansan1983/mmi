# 测试规范

> 版本：v1.0 | 制定时间：2026-06-16

---

## 一、测试分层

| 层级 | 范围 | 命令 |
|------|------|------|
| 单元测试 | 各模块独立逻辑 | `pytest tests/ -x` |
| 集成测试 | 跨模块协作 | `pytest tests/test_integration.py -xvs` |
| Benchmark | 性能基线 | `pytest tests/test_benchmark.py -xvs` |
| E2E (TS) | TS TUI 完整流程 | `pytest tests/tui-ts/test_e2e.py -xvs` |

---

## 二、强制门禁

| 检查项 | 标准 |
|--------|------|
| pytest | `pytest tests/ -x` 全部通过（禁止 skip） |
| ruff | `ruff check .` 0 error |
| 覆盖率 | 不低于上一阶段 |
| 新功能 | 必须有对应测试用例 |

---

## 三、测试数据规范

- Session 存储在 `~/.mmi/sessions/test/`
- 使用 `_fakes.py` 中的 FakeSessionFactory 生成假数据
- 外部 API 调用必须 mock（使用 `respx` 或 `pytest-mock`）

---

## 四、TUI 测试要求

| 测试项 | 覆盖点 |
|--------|--------|
| Markdown渲染 | 输出包含 Rich 格式标记 |
| Token计数 | 数值准确性 |
| 异常处理 | 错误时用户可见提示，无崩溃 |