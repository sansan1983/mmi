#!/usr/bin/env node
import React from 'react'
import { render, Text } from 'ink'
import { IpcClient } from './ipc/client.js'

function App() {
  return <Text>MMI TUI (placeholder — replace per screen)</Text>
}

const client = IpcClient.spawn()
client.request('hello', { protocol_version: 1 }).then(
  (res) => {
    render(<App />)
  },
  (err) => {
    console.error('IPC hello failed:', err)
    process.exit(1)
  }
)
