import { tokyoNight } from './tokyo-night.js'
import { light } from './light.js'
import type { Theme } from './tokyo-night.js'

/** Detect terminal background luminance via OSC 11. Falls back to dark. */
export async function detectTheme(timeoutMs = 200): Promise<Theme> {
  return new Promise<Theme>((resolve) => {
    if (!process.stdout.isTTY) {
      resolve(tokyoNight)
      return
    }
    const onData = (data: Buffer) => {
      const text = data.toString()
      const match = text.match(/rgb:([0-9a-fA-F]{2,4})\/([0-9a-fA-F]{2,4})\/([0-9a-fA-F]{2,4})/)
      if (!match) return
      cleanup()
      const [, rHex, gHex, bHex] = match
      const r = parseInt(rHex!.padEnd(4, rHex!), 16) / 65535
      const g = parseInt(gHex!.padEnd(4, gHex!), 16) / 65535
      const b = parseInt(bHex!.padEnd(4, bHex!), 16) / 65535
      const luma = 0.299 * r + 0.587 * g + 0.114 * b
      resolve(luma > 0.5 ? light : tokyoNight)
    }
    const timer = setTimeout(() => {
      cleanup()
      resolve(tokyoNight)
    }, timeoutMs)
    const cleanup = () => {
      clearTimeout(timer)
      process.stdin.off('data', onData)
    }
    process.stdin.once('data', onData)
    process.stdout.write('\x1b]11;?\x07')
  })
}
