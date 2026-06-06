import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render } from 'ink-testing-library'
import { ThemeProvider } from '../state/theme.js'
import { SessionHub } from './SessionHub.js'
import { tokyoNight } from '../theme/tokyo-night.js'
import type { IpcClient } from '../ipc/client.js'

function makeClient() {
  return {
    request: vi.fn().mockResolvedValue({
      sessions: [
        { id: '01A', title: 'Design Discussion', heat: 12.3 },
        { id: '01B', title: 'Bug Fix Round 8.5', heat: 8.7 },
      ],
    }),
  } as unknown as IpcClient
}

describe('<SessionHub />', () => {
  it('renders sessions from client', async () => {
    const client = makeClient()
    const { lastFrame, unmount } = render(
      <ThemeProvider theme={tokyoNight}>
        <SessionHub client={client} onEnter={() => {}} onCreate={() => {}} />
      </ThemeProvider>
    )
    await new Promise((r) => setTimeout(r, 50))
    const frame = lastFrame() ?? ''
    expect(frame).toContain('Design Discussion')
    expect(frame).toContain('Bug Fix Round 8.5')
    expect(frame).toContain('12.3')
    unmount()
  })

  it('calls onCreate when n is pressed', async () => {
    const client = makeClient()
    const onCreate = vi.fn()
    const { stdin, rerender, unmount } = render(
      <ThemeProvider theme={tokyoNight}>
        <SessionHub client={client} onEnter={() => {}} onCreate={onCreate} />
      </ThemeProvider>
    )
    // Force a rerender to ensure useInput listeners are registered.
    rerender(
      <ThemeProvider theme={tokyoNight}>
        <SessionHub client={client} onEnter={() => {}} onCreate={onCreate} />
      </ThemeProvider>
    )
    await new Promise((r) => setTimeout(r, 50))
    stdin.write('n')
    await new Promise((r) => setTimeout(r, 50))
    expect(onCreate).toHaveBeenCalled()
    unmount()
  })
})
