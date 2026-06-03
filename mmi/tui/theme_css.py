"""mmi.tui.theme_css —— CSS 字符串（嵌入 app.py 避免 .tcss 路径问题）。

ARCHITECTURE Phase 5：OMP Tokyo Night 原色（暗色）。
textual 的 CSS 加载支持字符串内联（CSS 类属性），不依赖外部 .tcss 文件。
"""

__all__ = ["THEME_CSS"]


THEME_CSS = """
/* 整体单一深色背景（#1a1b26），所有区域共享 */
Screen {
    background: #1a1b26;
    color: #c0caf5;
}

/* 默认文字色 */
Static {
    color: #c0caf5;
}

/* 输入框：无方框，仅顶部分割线 */
Input {
    background: #1a1b26;
    color: #c0caf5;
    border: none;
    border-top: solid #414868;
    height: 1;
}
Input:focus {
    border-top: solid #7aa2f7;
}
Input.-bash {
    border-top: solid #f7768e;
}
Input.-bash:focus {
    border-top: solid #f7768e;
}
Input.-python {
    border-top: solid #e0af68;
}
Input.-python:focus {
    border-top: solid #e0af68;
}

/* 多行编辑器（Phase 6 P0 #4）：Input 升级为 TextArea */
TextArea {
    background: #1a1b26;
    color: #c0caf5;
    border: none;
    border-top: solid #414868;
    height: 5;
    padding: 0 1;
}
TextArea:focus {
    border-top: solid #7aa2f7;
}
TextArea.-bash {
    border-top: solid #f7768e;
}
TextArea.-bash:focus {
    border-top: solid #f7768e;
}
TextArea.-python {
    border-top: solid #e0af68;
}
TextArea.-python:focus {
    border-top: solid #e0af68;
}

/* 底部分割线统一（提示栏、输入框上方） */
Footer {
    background: #1a1b26;
    color: #565f89;
    border-top: solid #414868;
    height: 1;
}

/* Textual 默认 Header（暂留，ListScreen 还在用） */
Header {
    background: #1a1b26;
    color: #bb9af7;
    text-style: bold;
    border-bottom: solid #414868;
}

/* List/Search 屏用 */
ListView {
    background: #1a1b26;
    color: #c0caf5;
}
ListView > ListItem {
    padding: 0 1;
}
ListView > ListItem.--highlight {
    background: #2ac3de;
    color: #1a1b26;
}

/* 消息区：单背景 + 上下细线；user/agent 上细线分隔交给 ChatLog 内部 widget */
RichLog {
    background: #1a1b26;
    color: #c0caf5;
}
"""
