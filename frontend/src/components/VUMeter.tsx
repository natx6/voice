import { useEffect, useRef, useState } from 'react'

interface VUMeterProps {
  recording: boolean
}

export default function VUMeter({ recording }: VUMeterProps) {
  const [level, setLevel] = useState(0)
  const wsRef = useRef<WebSocket | null>(null)
  const mountedRef = useRef(false)

  useEffect(() => {
    // Prevent double-connect from StrictMode
    if (mountedRef.current) return
    mountedRef.current = true

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${proto}//${host}/ws/level`

    let ws: WebSocket
    let reconnectTimer: ReturnType<typeof setTimeout>
    let closed = false

    function connect() {
      if (closed) return
      ws = new WebSocket(url)
      wsRef.current = ws

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'level') {
            setLevel(data.level ?? 0)
          }
        } catch {}
      }

      ws.onclose = () => {
        wsRef.current = null
        if (!closed) {
          reconnectTimer = setTimeout(connect, 3000)
        }
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    connect()

    return () => {
      closed = true
      clearTimeout(reconnectTimer)
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      mountedRef.current = false
    }
  }, [])

  const pct = Math.min(level * 2, 100)

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>
        <span>Mic level</span>
        <span>{recording ? '🔴 REC' : ''}</span>
      </div>
      <div className="vu-meter">
        <div className="fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
