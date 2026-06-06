import React, { useEffect, useState } from 'react'
import { Box, Text, useInput } from 'ink'
import { Divider } from '../components/Divider.js'
import { useTheme } from '../state/theme.js'
import type { IpcClient } from '../ipc/client.js'

interface Session {
  id: string
  title: string
  heat: number
}

export function SessionHub({ client, onEnter, onCreate }: {
  client: IpcClient
  onEnter: (id: string) => void
  onCreate: () => void
}) {
  const theme = useTheme()
  const [sessions, setSessions] = useState<Session[]>([])
  const [cursor, setCursor] = useState(0)
  const [searchMode, setSearchMode] = useState(false)
  const [query, setQuery] = useState('')

  useEffect(() => {
    client.request<{ sessions: Session[] }>('list_sessions', { limit: 10, sort: 'heat' })
      .then((r) => setSessions(r.sessions))
      .catch(() => setSessions([]))
  }, [client])

  useInput((input, key) => {
    if (searchMode) {
      if (key.escape) { setSearchMode(false); setQuery(''); return }
      if (key.return) { setSearchMode(false); return }
      if (key.backspace || key.delete) { setQuery((q) => q.slice(0, -1)); return }
      if (input) setQuery((q) => q + input)
      return
    }
    if (key.upArrow) setCursor((c) => Math.max(0, c - 1))
    else if (key.downArrow) setCursor((c) => Math.min(Math.max(0, sessions.length - 1), c + 1))
    else if (key.return) { const s = sessions[cursor]; if (s) onEnter(s.id) }
    else if (input === 'n') onCreate()
    else if (input === '/') setSearchMode(true)
    else if (input === 'q') process.exit(0)
  })

  return (
    <Box flexDirection="column" alignItems="center" paddingY={1}>
      <Text color={theme.body} bold>MMI</Text>
      <Text color={theme.hint}>Multimodal Intelligence</Text>
      <Box height={1} />
      <Divider label="Sessions" />
      <Box height={1} />
      {sessions.map((s, i) => (
        <Box key={s.id} width="100%" justifyContent="space-between" paddingX={2}>
          <Text color={i === cursor ? theme.selectedFg : theme.body}>{s.title}</Text>
          <Text color={theme.hint}>{s.heat.toFixed(1)}</Text>
        </Box>
      ))}
      <Box height={1} />
      <Divider label={`${sessions.length} sessions`} />
      <Box height={1} />
      <Text color={theme.shortcut}>n new  /  search  q quit</Text>
      {searchMode && <Text color={theme.hint}>/{query}</Text>}
    </Box>
  )
}
