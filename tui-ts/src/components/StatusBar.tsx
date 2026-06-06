import React from 'react'
import { Box } from 'ink'
import { Divider } from './Divider.js'

export function StatusBar({ time, turns, tokens }: { time: string; turns: number; tokens: number }) {
  return (
    <Box flexDirection="column">
      <Divider label={`${time}  ·  ${turns} turns  ·  ${tokens} tokens  ·  Esc to exit`} />
    </Box>
  )
}
