import React, { useState } from 'react'
import { Box, Text, useInput } from 'ink'
import { useTheme } from '../state/theme.js'

export function FoldBlock({ kind, summary, children }: {
  kind: 'thinking' | 'tool'
  summary: string
  children: React.ReactNode
}) {
  const theme = useTheme()
  const [open, setOpen] = useState(false)
  useInput((_input, key) => {
    if (key.return) setOpen((o) => !o)
  })
  const barColor = kind === 'thinking' ? '#bb9af7' : '#9ece6a'
  const symbol = open ? '▼' : '▶'
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={theme.foldBorder} paddingX={1} marginY={1}>
      <Box>
        <Text color={barColor}>│ </Text>
        <Text color={theme.body}>{symbol} [{kind}] {summary}</Text>
      </Box>
      {open && <Box paddingLeft={2}><Text color={theme.body}>{children}</Text></Box>}
    </Box>
  )
}
