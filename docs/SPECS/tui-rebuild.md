# SPEC: Python TUI 修复

> Phase: 0 | 优先级：🔴 | 制定时间：2026-06-16

---

## 背景

Python TUI 是用户使用 MMI 的唯一入口，当前存在三个严重问题：
1. Markdown 无法正常渲染
2. Token 计数显示乱码
3. 14 处静默吞异常

---

## 任务 0.1 — Markdown 渲染修复

### 问题
`mmi/tui_v3.py` 中使用了 `rich.console.Console().print()` 或直接 `print()` 输出文本，无法正确渲染 Markdown 格式。

### 验收标准
- [ ] 启动 `mmi tui` 后，助手回复以彩色 Markdown 格式显示
- [ ] 标题、代码块、链接等均有正确样式
- [ ] 代码块有语法高亮

### 实现提示
```python
from rich.markdown import Markdown
console = Console()
console.print(Markdown(response_text))
```

---

## 任务 0.2 — Token 计数修复

### 问题
TUI 中 token 计数使用 `len(text.encode())` 或类似逻辑，在非 ASCII 字符下会出错。

### 验收标准
- [ ] 显示格式：`Tokens: 123 | Chars: 456`
- [ ] Token 数与 LLM API 返回值误差 < 5%
- [ ] 中文字符计数正确

### 实现提示
使用 `tiktoken` 或 `transformers` 的 tokenizer，或使用 LLM 返回的 `usage` 字段。

---

## 任务 0.3 — 异常处理修复

### 问题
14 处 `except Exception: pass` 静默吞掉异常，用户完全不知道出错。

### 验收标准
- [ ] 所有静默 except 改为有日志记录
- [ ] 用户可见错误信息（友好提示 + 日志路径）
- [ ] 错误不导致程序崩溃

### 实现提示
```python
import logging
logger = logging.getLogger("mmi.tui")
try:
    ...
except SomeSpecificError as e:
    logger.error(f"操作失败: {e}", exc_info=True)
    console.print("[red]操作失败，请重试[/red]")
```

---

## 任务 0.4 — GC Daemon 集成

### 问题
GC Daemon 有框架代码但未与 Manager 集成，垃圾回收从未实际触发。

### 验收标准
- [ ] Session 激活时自动激活 GC Daemon
- [ ] Session 退出时自动取消 GC Daemon
- [ ] `pytest tests/test_gc_daemon.py -x` 全部通过

---

## 任务 0.5 — ruff 集成 CI

### 问题
CI 有框架但 `ruff check` 未实际运行。

### 验收标准
- [ ] `.github/workflows/ci.yml` 中 `ruff check .` 存在且通过
- [ ] PR 触发 CI 检查