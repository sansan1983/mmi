import React from 'react'
import { describe, expect, it } from 'vitest'
import { render } from 'ink-testing-library'
import { ThemeProvider } from '../state/theme.js'
import { CodeBlock } from './CodeBlock.js'
import { tokyoNight } from '../theme/tokyo-night.js'

describe('<CodeBlock />', () => {
  it('renders tree-line prefix on each line', () => {
    const { lastFrame, unmount } = render(
      <ThemeProvider theme={tokyoNight}><CodeBlock content={'a\nb'} /></ThemeProvider>
    )
    const frame = lastFrame() ?? ''
    expect(frame).toContain('├── a')
    expect(frame).toContain('└── b')
    unmount()
  })
})
