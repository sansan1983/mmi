import React from 'react'
import { Box, Text } from 'ink'
import { useTheme } from '../state/theme.js'

export function MessageBlock({ role, content }: { role: 'user' | 'agent'; content: string }) {
  const theme = useTheme()
  const label = role === 'user' ? '[你]' : '[MMI]'
  const labelColor = role === 'user' ? theme.userTag : theme.agentTag
  return (
    <Box flexDirection="column" marginY={1}>
      <Text><Text color={labelColor}>{label}</Text>  <Text color={theme.body}>{content}</Text></Text>
    </Box>
  )
}
