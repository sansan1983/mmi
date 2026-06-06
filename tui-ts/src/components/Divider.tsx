import React from 'react'
import { Text, useStdout } from 'ink'
import stringWidth from 'string-width'

export function Divider({ width = 0.8, label }: { width?: number; label?: string }) {
  const { stdout } = useStdout()
  const cols = stdout.columns ?? 80
  const total = Math.floor(cols * width)
  const edgePad = Math.floor(total * 0.1)
  if (!label) {
    return <Text dimColor>{'─'.repeat(Math.max(0, total - edgePad * 2))}</Text>
  }
  const labelText = `  ${label}  `
  const labelLen = stringWidth(labelText)
  const middle = total - edgePad * 2 - labelLen
  const left = Math.floor(middle / 2)
  const right = middle - left
  return (
    <Text dimColor>
      {'─'.repeat(Math.max(0, left))}
      {labelText}
      {'─'.repeat(Math.max(0, right))}
    </Text>
  )
}
