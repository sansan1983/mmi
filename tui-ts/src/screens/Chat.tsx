import React, { useState } from 'react'
import { Box, Text } from 'ink'
import { HeaderBar } from '../components/HeaderBar.js'
import { StatusBar } from '../components/StatusBar.js'
import { Input } from '../components/Input.js'
import { MessageBlock } from '../components/MessageBlock.js'
import { useTheme } from '../state/theme.js'
import type { IpcClient } from '../ipc/client.js'

interface Turn { role: 'user' | 'agent'; content: string }

export function Chat({ client, sessionId, onExit }: {
  client: IpcClient
  sessionId: string
  onExit: () => void
}) {
  const theme = useTheme()
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)

  async function handleSubmit(text: string) {
    setBusy(true)
    setTurns((t) => [...t, { role: 'user', content: text }])
    try {
      const result = await client.request<{ content: string }>('send_message', {
        session_id: sessionId,
        content: text,
      })
      setTurns((t) => [...t, { role: 'agent', content: result.content }])
    } catch (err) {
      setTurns((t) => [...t, { role: 'agent', content: `[error] ${(err as Error).message}` }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box flexDirection="column" height="100%">
      <HeaderBar model="deepseek-chat" locale="zh-CN" />
      <Box flexDirection="column" flexGrow={1} paddingX={2}>
        {turns.map((turn, i) => (
          <MessageBlock key={i} role={turn.role} content={turn.content} />
        ))}
        {busy && <Text color={theme.hint}>…</Text>}
      </Box>
      <StatusBar time={new Date().toLocaleTimeString()} turns={turns.length} tokens={0} />
      <Input onSubmit={handleSubmit} />
    </Box>
  )
}
