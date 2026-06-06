import { describe, expect, it } from 'vitest'
import { parseMarkdown } from './markdown.js'

describe('parseMarkdown', () => {
  it('parses headings', () => {
    const nodes = parseMarkdown('# Hello\n## World')
    expect(nodes).toEqual([
      { type: 'heading', level: 1, text: 'Hello' },
      { type: 'heading', level: 2, text: 'World' },
    ])
  })

  it('parses fenced code blocks', () => {
    const nodes = parseMarkdown('```python\nprint(1)\n```')
    expect(nodes).toEqual([{ type: 'code', lang: 'python', content: 'print(1)' }])
  })

  it('parses :::thinking fold blocks', () => {
    const nodes = parseMarkdown(':::thinking\nreasoning here\n:::')
    expect(nodes).toEqual([{ type: 'thinking', content: 'reasoning here' }])
  })

  it('parses unordered lists', () => {
    const nodes = parseMarkdown('- a\n- b')
    expect(nodes).toEqual([{ type: 'list', ordered: false, items: ['a', 'b'] }])
  })

  it('parses blockquotes', () => {
    const nodes = parseMarkdown('> quoted')
    expect(nodes).toEqual([{ type: 'blockquote', text: 'quoted' }])
  })
})
