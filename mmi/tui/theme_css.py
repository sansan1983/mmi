"""mmi.tui.theme_css —— TCSS 主题。"""

DARK_CSS = """
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

LIGHT_CSS = """
Screen { background: #f5f5f5; color: #333333; }

#term-titlebar { height: 2; background: #e0e0e0; color: #333333; border-bottom: solid #cccccc; }
#main-content { height: 1fr; background: #f5f5f5; }

#list-view { height: 1fr; }
#list-top { height: 2; background: #f5f5f5; border-bottom: solid #cccccc; color: #333333; }
#list-header { height: 2; background: #f5f5f5; color: #333333; text-style: bold; border-bottom: solid #cccccc; }
#list-items { height: 1fr; background: #f5f5f5; }
#list-items > Static { color: #333333; border-left: solid transparent; }
#list-items > Static:hover { background: #e8e8e8; }
#list-items > Static.-sel { background: #dddddd; border-left: solid #1a73e8; }
#empty-state { height: 1fr; align: center middle; }
#empty-state .empty-big { color: #cccccc; text-style: bold; }
#empty-state .empty-text { color: #333333; }
#empty-state .empty-hint { color: #1a73e8; }
#list-footer { height: 2; background: #e0e0e0; color: #666666; border-top: solid #cccccc; }

#chat-view { height: 1fr; }
#chat-topbar { height: 2; background: #e0e0e0; color: #333333; border-bottom: solid #cccccc; }
#msg-area { height: 1fr; background: #f5f5f5; }

/* 输入区：单行起步，内容多自动向上扩，最多6行 */
#input-editor { height: auto; min-height: 1; max-height: 6; background: #ffffff; color: #333333; }
#input-editor:focus { background: #f0f0f0; border: none; }
#chat-footer { height: 2; background: #ffffff; color: #666666; }

.turn-header { height: 1; background: #f5f5f5; }
.turn-header.role-user { color: #1a73e8; text-style: bold; }
.turn-header.role-asst { color: #9334e6; text-style: bold; }
.turn-body.-hidden { display: none; height: 0; }
.msg-content { padding: 0 0 0 2; }
"""
