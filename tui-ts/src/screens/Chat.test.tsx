import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render } from 'ink-testing-library'
import { EventEmitter } from 'node:events'
import { ThemeProvider } from '../state/theme.js'
import { Chat } from './Chat.js'
import { tokyoNight } from '../theme/tokyo-night.js'
import type { IpcClient } from '../ipc/client.js'

const tick = (ms = 10) => new Promise<void>((resolve) => setTimeout(resolve, ms))

async function typeAndEnter(stdin: { write: (s: string) => void }, text: string) {
  for (const ch of text) {
    stdin.write(ch)
    await tick()
  }
  stdin.write('\r')
  await tick()
}

function makeClient(respondWith = 'echoed') {
  const client = new EventEmitter() as any
  client.request = vi.fn().mockImplementation(async (method: string) => {
    if (method === 'send_message') return { content: respondWith }
    return {}
  })
  return client as IpcClient
}

function makeStreamingClient(): IpcClient {
  const client = new EventEmitter() as any
  client.request = vi.fn().mockResolvedValue({ ok: true })
  return client as IpcClient
}

describe('<Chat />', () => {
  it('renders empty state', () => {
    const { lastFrame, unmount } = render(
      <ThemeProvider theme={tokyoNight}><Chat client={makeClient()} sessionId="S1" onExit={() => {}} /></ThemeProvider>
    )
    expect(lastFrame()).toContain('deepseek-chat')
    unmount()
  })

  it('sends message and shows user turn', async () => {
    const client = makeClient('hi back')
    const { stdin, lastFrame, unmount } = render(
      <ThemeProvider theme={tokyoNight}><Chat client={client} sessionId="S1" onExit={() => {}} /></ThemeProvider>
    )
    await tick() // let useInput effect attach the listener
    await typeAndEnter(stdin, 'hello')
    await tick(50) // let the request promise resolve + state update + render
    const frame = lastFrame() ?? ''
    expect(frame).toContain('hello')
    unmount()
  })
})

describe('<Chat /> streaming', () => {
  it('appends streamed tokens to the buffer', async () => {
    const client = makeStreamingClient()
    const { stdin, lastFrame, unmount } = render(
      <ThemeProvider theme={tokyoNight}><Chat client={client} sessionId="S1" onExit={() => {}} /></ThemeProvider>
    )
    await new Promise((r) => setTimeout(r, 10))
    stdin.write('hi')
    await new Promise((r) => setTimeout(r, 10))
    stdin.write('\r')
    await new Promise((r) => setTimeout(r, 20))
    client.emit('event:token', { session_id: 'S1', delta: 'hel' })
    await new Promise((r) => setTimeout(r, 10))
    client.emit('event:token', { session_id: 'S1', delta: 'lo!' })
    await new Promise((r) => setTimeout(r, 20))
    const frame = lastFrame() ?? ''
    expect(frame).toContain('hel')
    expect(frame).toContain('lo!')
    unmount()
  })
})
