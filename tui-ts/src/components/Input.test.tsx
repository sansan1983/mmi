import React from 'react'
import { describe, expect, it, vi } from 'vitest'
import { render } from 'ink-testing-library'
import { ThemeProvider } from '../state/theme.js'
import { Input } from './Input.js'
import { tokyoNight } from '../theme/tokyo-night.js'

// In `ink-testing-library`, `stdin.write` is dispatched through an
// EventEmitter 'readable' event that the App subscribes to. The whole
// pipeline (emit → handleReadable → parseKeypress → React commit)
// requires a macrotask tick to settle. We must wait AFTER `render()`
// for the App's `useInput` effect to attach its listener, otherwise the
// first chunk is dropped, AND we must wait between consecutive writes.
const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 10))

async function typeAndEnter(stdin: { write: (s: string) => void }, text: string) {
  for (const ch of text) {
    stdin.write(ch)
    await tick()
  }
  stdin.write('\r')
  await tick()
}

describe('<Input />', () => {
  it('calls onSubmit with typed text on Enter', async () => {
    const onSubmit = vi.fn()
    const { stdin, unmount } = render(
      <ThemeProvider theme={tokyoNight}><Input onSubmit={onSubmit} /></ThemeProvider>
    )
    await tick() // let useInput effect attach the listener
    await typeAndEnter(stdin, 'hello')
    expect(onSubmit).toHaveBeenCalledWith('hello')
    unmount()
  })

  it('clears value after submit', async () => {
    const onSubmit = vi.fn()
    const { stdin, lastFrame, unmount } = render(
      <ThemeProvider theme={tokyoNight}><Input onSubmit={onSubmit} /></ThemeProvider>
    )
    await tick() // let useInput effect attach the listener
    await typeAndEnter(stdin, 'x')
    const frame = lastFrame() ?? ''
    expect(frame).toContain('输入消息')
    expect(onSubmit).toHaveBeenCalledWith('x')
    unmount()
  })
})
