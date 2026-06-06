import React, { useEffect, useRef } from 'react'
import { Box, Text } from 'ink'
import { MessageBlock } from './MessageBlock.js'
import { useStreamBuffer } from '../state/stream.js'

export function ChatLog({ sessionId, turns }: {
  sessionId: string
  turns: { role: 'user' | 'agent'; content: string }[]
}) {
  const liveBuffer = useStreamBuffer(sessionId)
  const ref = useRef<{ lastLen: number }>({ lastLen: 0 })
  useEffect(() => { ref.current.lastLen = liveBuffer.length }, [liveBuffer])
  return (
    <Box flexDirection="column" flexGrow={1} paddingX={2}>
      {turns.map((t, i) => (
        <MessageBlock key={i} role={t.role} content={t.content} />
      ))}
      {liveBuffer && <MessageBlock role="agent" content={liveBuffer} />}
    </Box>
  )
}
