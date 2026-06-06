import { spawn, type ChildProcess } from 'node:child_process'
import { EventEmitter } from 'node:events'
import readline from 'node:readline'
import type { Event, Request, Response } from './protocol.js'

export class IpcError extends Error {
  constructor(public code: number, message: string) {
    super(message)
  }
}

type Pending = {
  resolve: (value: any) => void
  reject: (reason: Error) => void
}

export class IpcClient extends EventEmitter {
  private nextId = 1
  private pending = new Map<number, Pending>()
  private rl?: readline.Interface
  private proc?: ChildProcess

  constructor(proc?: ChildProcess) {
    super()
    if (proc) this.attach(proc)
  }

  attach(proc: ChildProcess): void {
    this.proc = proc
    if (!proc.stdout) throw new Error('proc.stdout is required')
    this.rl = readline.createInterface({ input: proc.stdout })
    this.rl.on('line', (line) => this.handleLine(line))
    proc.on('exit', (code) => {
      const err = new Error(`ipc process exited with code ${code}`)
      for (const p of this.pending.values()) p.reject(err)
      this.pending.clear()
      this.emit('exit', code)
    })
  }

  /** Spawn the Python IPC server and attach. */
  static spawn(): IpcClient {
    const proc = spawn(
      process.env.PYTHON ?? 'python3',
      ['-m', 'mmi.core.ipc_server'],
      { stdio: ['pipe', 'pipe', 'pipe'] }
    )
    const client = new IpcClient()
    client.attach(proc)
    return client
  }

  request<T = unknown>(method: string, params: unknown = {}): Promise<T> {
    const id = this.nextId++
    const req: Request = { jsonrpc: '2.0', id, method, params }
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve, reject })
      if (!this.proc?.stdin) {
        reject(new Error('ipc stdin not writable'))
        return
      }
      this.proc.stdin.write(JSON.stringify(req) + '\n')
    })
  }

  private handleLine(line: string): void {
    if (!line) return
    const msg = JSON.parse(line) as Response | Event
    if ('id' in msg && msg.id !== null && msg.id !== undefined) {
      const p = this.pending.get(msg.id)
      if (!p) return
      this.pending.delete(msg.id)
      if (msg.error) p.reject(new IpcError(msg.error.code, msg.error.message))
      else p.resolve(msg.result)
    } else if ('method' in msg) {
      this.emit('event', msg as Event)
      this.emit(`event:${msg.method}`, (msg as Event).params)
    }
  }

  close(): void {
    this.rl?.close()
    this.proc?.kill('SIGTERM')
  }
}
