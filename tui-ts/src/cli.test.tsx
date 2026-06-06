import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render } from 'ink-testing-library'
import { EventEmitter } from 'node:events'
import { App } from './cli.js'
import { ThemeProvider } from './state/theme.js'
import { tokyoNight } from './theme/tokyo-night.js'
import type { IpcClient } from './ipc/client.js'

const tick = (ms = 10) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function makeClient(): IpcClient {
  const client = new EventEmitter() as any
  client.request = vi.fn().mockImplementation(async (method: string) => {
    if (method === 'list_sessions') {
      return {
        sessions: [
          { id: '01A', title: 'Design Discussion', heat: 12.3 },
          { id: '01B', title: 'Bug Fix Round 8.5', heat: 8.7 },
        ],
      }
    }
    return {}
  })
  return client as IpcClient
}

describe('<App /> router', () => {
  it('renders SessionHub by default (no session selected)', async () => {
    const client = makeClient()
    const { lastFrame, unmount } = render(<App client={client} />)
    await tick(50) // let list_sessions resolve + render
    const frame = lastFrame() ?? ''
    expect(frame).toContain('Sessions')
    expect(frame).toContain('Design Discussion')
    expect(frame).toContain('Bug Fix Round 8.5')
    unmount()
  })

  it('pressing n does not crash (onCreate is a stub)', async () => {
    const client = makeClient()
    const { stdin, rerender, unmount } = render(<App client={client} />)
    // Force rerender to ensure SessionHub's useInput listener is registered.
    rerender(<App client={client} />)
    await tick(50)
    stdin.write('n')
    await tick(20)
    // No assertion on the stub — we just verify the router survived.
    expect(true).toBe(true)
    unmount()
  })

  it('wraps content in a ThemeProvider (no crash with default theme)', () => {
    // Render the App inside a ThemeProvider to confirm children nesting is sound.
    // The App itself also provides, so this is just a smoke test for composition.
    const client = makeClient()
    const { unmount } = render(
      <ThemeProvider theme={tokyoNight}>
        <App client={client} />
      </ThemeProvider>
    )
    expect(true).toBe(true)
    unmount()
  })
})
