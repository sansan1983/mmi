import React, { createContext, useContext, useEffect, useState, useRef } from 'react'
import type { IpcClient } from '../ipc/client.js'

interface StreamState {
  buffers: Record<string, string>
  append: (sessionId: string, delta: string) => void
  reset: (sessionId: string) => void
}

const StreamContext = createContext<StreamState | null>(null)

export function StreamProvider({ client, children }: { client: IpcClient; children: React.ReactNode }) {
  const [buffers, setBuffers] = useState<Record<string, string>>({})
  const buffersRef = useRef(buffers)
  buffersRef.current = buffers

  useEffect(() => {
    const onToken = (params: any) => {
      const { session_id, delta } = params
      setBuffers((prev) => ({ ...prev, [session_id]: (prev[session_id] ?? '') + delta }))
    }
    client.on('event:token', onToken)
    return () => { client.off('event:token', onToken) }
  }, [client])

  return (
    <StreamContext.Provider value={{
      buffers,
      append: (id, delta) => setBuffers((p) => ({ ...p, [id]: (p[id] ?? '') + delta })),
      reset: (id) => setBuffers((p) => { const { [id]: _, ...rest } = p; return rest }),
    }}>
      {children}
    </StreamContext.Provider>
  )
}

export function useStreamBuffer(sessionId: string): string {
  const ctx = useContext(StreamContext)
  return ctx?.buffers[sessionId] ?? ''
}
