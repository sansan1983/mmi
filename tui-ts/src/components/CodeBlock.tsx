import React from 'react'
import { Box, Text } from 'ink'
import { useTheme } from '../state/theme.js'

/** Render code with `├── ` / `└── ` / `│   ` tree-line decoration.
 *  Indentation (leading spaces) is converted into tree lines.
 */
export function CodeBlock({ content }: { content: string }) {
  const theme = useTheme()
  const lines = content.split('\n')
  return (
    <Box flexDirection="column" paddingX={2}>
      {lines.map((line, idx) => {
        const isLast = idx === lines.length - 1
        const prefix = isLast ? '└── ' : '├── '
        return (
          <Text key={idx}><Text color={theme.treeLine}>{prefix}</Text><Text color={theme.body}>{line}</Text></Text>
        )
      })}
    </Box>
  )
}
