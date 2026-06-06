/** JSON-RPC 2.0 protocol types for MMI core <-> TUI communication. */

export const PROTOCOL_VERSION = 1

export interface Request<TParams = unknown> {
  jsonrpc: '2.0'
  id: number
  method: string
  params: TParams
}

export interface Response<TResult = unknown> {
  jsonrpc: '2.0'
  id: number | null
  result?: TResult
  error?: { code: number; message: string }
}

export interface Event<TParams = unknown> {
  jsonrpc: '2.0'
  method: string
  params: TParams
}

export interface HelloResult {
  protocol_version: number
  server: string
}
