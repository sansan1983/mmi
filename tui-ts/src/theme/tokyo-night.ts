/** Tokyo Night color palette (dark variant). Mirrors docs/design/tui-visual-design.md §4.2. */
export const tokyoNight: Theme = {
  bg: undefined, // transparent
  body: '#c0caf5',
  userTag: '#7dcfff',
  agentTag: '#c0caf5',
  divider: '#414868',
  onLineText: '#7aa2f7',
  selectedBg: '#161b22',
  selectedFg: '#2ac3de',
  codeKeyword: '#9ece6a',
  codeString: '#565f89',
  treeLine: '#565f89',
  hint: '#565f89',
  statusLine: '#414868',
  citation: '#7aa2f7',
  foldBorder: '#414868',
  shortcut: '#7aa2f7',
}

export interface Theme {
  bg: string | undefined
  body: string
  userTag: string
  agentTag: string
  divider: string
  onLineText: string
  selectedBg: string
  selectedFg: string
  codeKeyword: string
  codeString: string
  treeLine: string
  hint: string
  statusLine: string
  citation: string
  foldBorder: string
  shortcut: string
}
