#!/usr/bin/env node
import React, { useEffect, useState } from 'react'
import { render } from 'ink'
import { pathToFileURL } from 'node:url'
import { IpcClient } from './ipc/client.js'
import { ThemeProvider } from './state/theme.js'
import { tokyoNight } from './theme/tokyo-night.js'
import { SessionHub } from './screens/SessionHub.js'
import { Chat } from './screens/Chat.js'

export function App({ client }: { client: IpcClient }) {
  const [sessionId, setSessionId] = useState<string | null>(null)

  useEffect(() => {
    client.on('exit', (code: number | null) => {
      process.exit(code ?? 0)
    })
  }, [client])

  if (sessionId) {
    return (
      <ThemeProvider theme={tokyoNight}>
        <Chat
          client={client}
          sessionId={sessionId}
          onExit={() => setSessionId(null)}
        />
      </ThemeProvider>
    )
  }

  return (
    <ThemeProvider theme={tokyoNight}>
      <SessionHub
        client={client}
        onEnter={(id) => setSessionId(id)}
        onCreate={() => {
          // TODO: call client.request('create_session', ...) and setSessionId(newId)
          // once the create_session IPC method lands. For now, just log a hint.
          process.stderr.write('[mmi] create_session IPC not yet implemented\n')
        }}
      />
    </ThemeProvider>
  )
}

// Only run entry-point side effects when this file is the launched CLI.
// When imported by tests (e.g. cli.test.tsx) we expose <App/> without spawning
// the IPC server or calling process.exit.
const isEntry = (() => {
  const argv1 = process.argv[1]
  if (!argv1) return false
  try {
    return pathToFileURL(argv1).href === import.meta.url
  } catch {
    return false
  }
})()

if (isEntry) {
  const client = IpcClient.spawn()
  client.request('hello', { protocol_version: 1 }).then(
    () => {
      render(<App client={client} />)
    },
    (err) => {
      console.error('IPC hello failed:', err)
      process.exit(1)
    }
  )
}
