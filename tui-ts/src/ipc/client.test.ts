import { spawn } from 'node:child_process'
import { describe, expect, it, afterEach } from 'vitest'
import { IpcClient } from './client.js'
import type { ChildProcess } from 'node:child_process'

let procs: ChildProcess[] = []

function spawnPython(): ChildProcess {
  const proc = spawn(
    process.env.PYTHON ?? 'python3',
    ['-m', 'mmi.core.ipc_server'],
    { stdio: ['pipe', 'pipe', 'pipe'] }
  )
  procs.push(proc)
  return proc
}

afterEach(() => {
  for (const p of procs) {
    p.kill('SIGTERM')
  }
  procs = []
})

describe('IpcClient', () => {
  it('round-trips a hello request', async () => {
    const proc = spawnPython()
    const client = new IpcClient(proc)
    const result = await client.request<{ protocol_version: number; server: string }>(
      'hello',
      { protocol_version: 1 }
    )
    expect(result.protocol_version).toBe(1)
    expect(result.server).toBe('mmi-core')
  })

  it('rejects on unknown method', async () => {
    const proc = spawnPython()
    const client = new IpcClient(proc)
    await expect(client.request('does_not_exist', {})).rejects.toThrow(/Method not found/)
  })
})
