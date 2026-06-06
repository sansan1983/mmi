import React from 'react'
import { Text } from 'ink'
import { useTheme } from '../state/theme.js'

const PREFIX = { doc: '› ', link: '→ ', memory: '↳ ' } as const

export function Citation({ kind, text }: { kind: keyof typeof PREFIX; text: string }) {
  const theme = useTheme()
  return <Text color={theme.citation}>{PREFIX[kind]}{text}</Text>
}
