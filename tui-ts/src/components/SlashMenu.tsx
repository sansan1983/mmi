import React from 'react'
import { Box, Text } from 'ink'
import { useTheme } from '../state/theme.js'

export interface SlashCommand {
  name: string
  description: string
}

export const DEFAULT_COMMANDS: SlashCommand[] = [
  { name: '/theme', description: 'switch theme (dark | light)' },
  { name: '/new', description: 'create new session' },
  { name: '/list', description: 'back to session hub' },
  { name: '/help', description: 'show help' },
  { name: '/quit', description: 'exit' },
]

export function SlashMenu({ query, onSelect }: { query: string; onSelect: (cmd: SlashCommand) => void }) {
  const theme = useTheme()
  const filtered = DEFAULT_COMMANDS.filter((c) => c.name.startsWith(query || '/'))
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={theme.foldBorder} paddingX={1}>
      {filtered.map((cmd, i) => (
        <Box key={cmd.name}>
          <Text color={theme.shortcut}>{cmd.name.padEnd(12)}</Text>
          <Text color={theme.hint}>{cmd.description}</Text>
          {i < filtered.length - 1 && <Text>{'\n'}</Text>}
        </Box>
      ))}
    </Box>
  )
}
