import React, { useState } from 'react'
import { Box, useInput } from 'ink'
import { HeaderBar } from '../components/HeaderBar.js'
import { StatusBar } from '../components/StatusBar.js'
import { Input } from '../components/Input.js'
import { ChatLog } from '../components/ChatLog.js'
import { StreamProvider } from '../state/stream.js'
import type { IpcClient } from '../ipc/client.js'

interface Turn { role: 'user' | 'agent'; content: string }

export function Chat({ client, sessionId, onExit }: {
  client: IpcClient
  sessionId: string
  onExit: () => void
}) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [busy, setBusy] = useState(false)

  useInput((_input, key) => {
    if (key.escape) onExit()
  })

  async function handleSubmit(text: string) {
    setBusy(true)
    setTurns((t) => [...t, { role: 'user', content: text }])
    try {
      await client.request('send_message', { session_id: sessionId, content: text })
    } finally {
      setBusy(false)
    }
  }

  return (
    <StreamProvider client={client}>
      <Box flexDirection="column" height="100%">
        <HeaderBar model="deepseek-chat" locale="zh-CN" />
        <ChatLog sessionId={sessionId} turns={turns} />
        <StatusBar time={new Date().toLocaleTimeString()} turns={turns.length} tokens={0} />
        <Input onSubmit={handleSubmit} />
      </Box>
    </StreamProvider>
  )
}
