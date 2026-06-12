"""mmi.tui.theme_css —— TCSS 主题。"""

THEME_CSS = """
Screen { background: #13151e; color: #c0caf5; }

#term-titlebar { height: 2; background: #0d0f17; color: #c0caf5; border-bottom: solid #282a40; }
#main-content { height: 1fr; background: #13151e; }

#list-view { height: 1fr; }
#list-top { height: 2; background: #13151e; border-bottom: solid #282a40; color: #c0caf5; }
#list-header { height: 2; background: #13151e; color: #c0caf5; text-style: bold; border-bottom: solid #282a40; }
#list-items { height: 1fr; background: #13151e; }
#list-items > Static { color: #c0caf5; border-left: solid transparent; }
#list-items > Static:hover { background: #1a1c27; }
#list-items > Static.-sel { background: #22243a; border-left: solid #7aa2f7; }
#empty-state { height: 1fr; align: center middle; }
#empty-state .empty-big { color: #282a40; text-style: bold; }
#empty-state .empty-text { color: #c0caf5; }
#empty-state .empty-hint { color: #7aa2f7; }
#list-footer { height: 2; background: #0d0f17; color: #6b7394; border-top: solid #282a40; }

#chat-view { height: 1fr; }
#chat-topbar { height: 2; background: #0d0f17; color: #c0caf5; border-bottom: solid #282a40; }
#msg-area { height: 1fr; background: #13151e; }

/* 输入区：单行起步，内容多自动向上扩，最多6行 */
#input-editor { height: auto; min-height: 1; max-height: 6; background: #1e2030; color: #c0caf5; }
#input-editor:focus { background: #1a1c27; border: none; }
#chat-footer { height: 2; background: #1e2030; color: #6b7394; }

.turn-header { height: 1; background: #13151e; }
.turn-header.role-user { color: #2ac3de; text-style: bold; }
.turn-header.role-asst { color: #bb9af7; text-style: bold; }
.turn-body.-hidden { display: none; height: 0; }
.msg-content { padding: 0 0 0 2; }
"""
