import React from 'react'
import { Text } from 'ink'
import { useTheme } from '../state/theme.js'

export function Pill({ children }: { children: React.ReactNode }) {
  const theme = useTheme()
  return (
    <Text backgroundColor={theme.selectedBg} color={theme.selectedFg}>
      {' '}{children}{' '}
    </Text>
  )
}
