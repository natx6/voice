import { useEffect, useRef, useState } from 'react'
import * as api from '../api'

interface PlaybackProgressProps {
  onPreview: () => Promise<void>
  onCapture: () => Promise<void>
  durationSecs: number
  disabled?: boolean
}

export default function PlaybackProgress({
  onPreview, onCapture, durationSecs, disabled,
}: PlaybackProgressProps) {
  const [status, setStatus] = useState<api.PlayStatus | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const wasPlayingRef = useRef(false)

  // Start polling — only called AFTER the API call succeeds
  const startPolling = () => {
    if (pollRef.current) return
    wasPlayingRef.current = false
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getPlayStatus()
        setStatus(s)

        // Detect transition: was playing → now stopped → stop polling
        if (wasPlayingRef.current && !s.playing) {
          if (pollRef.current) {
            clearInterval(pollRef.current)
            pollRef.current = null
          }
        }
        wasPlayingRef.current = s.playing
      } catch {
        // Ignore transient errors
      }
    }, 200)
  }

  const handlePreview = async () => {
    try {
      await onPreview()       // wait for the API call to actually complete
      startPolling()           // THEN start polling the backend
    } catch {}
  }

  const handleCapture = async () => {
    try {
      await onCapture()        // same: wait for the thread to be spawned
      startPolling()
    } catch {}
  }

  const handleStop = async () => {
    try {
      await api.stopPlayback()
      setStatus(null)
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    } catch {}
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [])

  const pct = status?.progress_pct ?? 0
  const elapsed = status?.elapsed_secs ?? 0
  const isPlaying = status?.playing ?? false
  const mode = status?.mode ?? ''
  const isPreview = isPlaying && mode === 'preview'
  const isCapturing = isPlaying && mode === 'capture'

  return (
    <div className="card" style={{ padding: 16 }}>
      {/* Progress bar */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>
          <span>
            {isPlaying
              ? (isPreview ? '🔊 Previewing...' : isCapturing ? '📱 Playing for Telegram...' : '▶️ Playing...')
              : 'Ready to play'
            }
          </span>
          <span>
            {isPlaying
              ? `${Math.round(elapsed)}s / ${Math.round(durationSecs)}s`
              : `${Math.round(durationSecs)}s`
            }
          </span>
        </div>
        <div className="vu-meter">
          <div
            className="fill"
            style={{
              width: `${isPlaying ? Math.min(pct, 100) : 0}%`,
              background: isCapturing
                ? 'linear-gradient(90deg, #e17055, #fdcb6e)'
                : undefined,
              transition: 'width 0.25s ease',
            }}
          />
        </div>
      </div>

      {/* Buttons */}
      <div style={{ display: 'flex', gap: 8 }}>
        {isPlaying ? (
          <button className="btn btn-danger btn-sm" onClick={handleStop} style={{ flex: 1 }}>
            ⏹ Stop
          </button>
        ) : (
          <>
            <button
              className="btn btn-ghost btn-sm"
              onClick={handlePreview}
              disabled={disabled}
              style={{ flex: 1 }}
            >
              🔊 Preview
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={handleCapture}
              disabled={disabled}
              style={{ flex: 1 }}
            >
              📱 Capture for Telegram
            </button>
          </>
        )}
      </div>
    </div>
  )
}
