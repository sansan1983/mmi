/** Minimal markdown -> AST. No external deps. */

export type MdNode =
  | { type: 'code'; lang: string; content: string }
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'list'; ordered: boolean; items: string[] }
  | { type: 'blockquote'; text: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool'; content: string }

export function parseMarkdown(input: string): MdNode[] {
  const lines = input.split('\n')
  const nodes: MdNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i] ?? ''
    // Fenced code
    if (line.startsWith('```')) {
      const lang = line.slice(3).trim()
      const buf: string[] = []
      i++
      while (i < lines.length && !(lines[i] ?? '').startsWith('```')) {
        buf.push(lines[i] ?? '')
        i++
      }
      i++
      nodes.push({ type: 'code', lang, content: buf.join('\n') })
      continue
    }
    // :::thinking / :::tool fold blocks
    if (line.startsWith(':::thinking')) {
      const buf: string[] = []
      i++
      while (i < lines.length && !(lines[i] ?? '').startsWith(':::')) {
        buf.push(lines[i] ?? '')
        i++
      }
      i++
      nodes.push({ type: 'thinking', content: buf.join('\n') })
      continue
    }
    if (line.startsWith(':::tool')) {
      const buf: string[] = []
      i++
      while (i < lines.length && !(lines[i] ?? '').startsWith(':::')) {
        buf.push(lines[i] ?? '')
        i++
      }
      i++
      nodes.push({ type: 'tool', content: buf.join('\n') })
      continue
    }
    // Heading
    const headingMatch = /^(#{1,6})\s+(.+)$/.exec(line)
    if (headingMatch) {
      nodes.push({ type: 'heading', level: headingMatch[1]!.length, text: headingMatch[2]! })
      i++
      continue
    }
    // Blockquote
    if (line.startsWith('> ')) {
      nodes.push({ type: 'blockquote', text: line.slice(2) })
      i++
      continue
    }
    // Lists
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^[-*]\s+/.test(lines[i] ?? '')) {
        items.push((lines[i] ?? '').replace(/^[-*]\s+/, ''))
        i++
      }
      nodes.push({ type: 'list', ordered: false, items })
      continue
    }
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i] ?? '')) {
        items.push((lines[i] ?? '').replace(/^\d+\.\s+/, ''))
        i++
      }
      nodes.push({ type: 'list', ordered: true, items })
      continue
    }
    // Paragraph (collect until blank line)
    if (line.trim()) {
      const buf: string[] = [line]
      i++
      while (i < lines.length && (lines[i] ?? '').trim() && !/^(#{1,6}\s|[-*]\s|\d+\.\s|>|```|:::)/.test(lines[i] ?? '')) {
        buf.push(lines[i] ?? '')
        i++
      }
      nodes.push({ type: 'paragraph', text: buf.join('\n') })
      continue
    }
    i++
  }
  return nodes
}
