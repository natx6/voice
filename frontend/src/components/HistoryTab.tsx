import { useState, useCallback, useEffect, useRef } from 'react'
import type { HistoryEntry } from '../types'
import * as api from '../api'

interface Props {
  history: HistoryEntry[]
  onRefresh: () => void
  showToast: (msg: string) => void
}

export default function HistoryTab({ history, onRefresh, showToast }: Props) {
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editingLabel, setEditingLabel] = useState('')
  const [playingEntry, setPlayingEntry] = useState<HistoryEntry | null>(null)
  const [playStatus, setPlayStatus] = useState<api.PlayStatus | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const startPolling = useCallback(() => {
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getPlayStatus()
        setPlayStatus(s)
        if (!s.playing) {
          if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
          setPlayingEntry(null)
          setPlayStatus(null)
        }
      } catch {}
    }, 200)
  }, [])

  useEffect(() => {
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [])

  const handlePreview = useCallback(async (entry: HistoryEntry) => {
    try {
      await api.previewAudio(entry.file_path)
      setPlayingEntry(entry)
      startPolling()
    } catch (e: any) {
      showToast(`Preview failed: ${e.message}`)
    }
  }, [showToast, startPolling])

  const handleCapture = useCallback(async (entry: HistoryEntry) => {
    try {
      await api.captureAudio(entry.file_path, 3)
      setPlayingEntry(entry)
      startPolling()
    } catch (e: any) {
      showToast(`Capture failed: ${e.message}`)
    }
  }, [showToast, startPolling])

  const handleStop = useCallback(async () => {
    try { await api.stopPlayback() } catch {}
    setPlayingEntry(null)
    setPlayStatus(null)
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }, [])

  const handleDelete = useCallback(async (id: number) => {
    try {
      await api.deleteHistory(id)
      showToast(`Deleted #${id}`)
      onRefresh()
    } catch (e: any) { showToast(`Delete failed: ${e.message}`) }
  }, [showToast, onRefresh])

  const handleLabel = useCallback(async (id: number) => {
    if (!editingLabel.trim()) return
    try {
      await api.labelHistory(id, editingLabel.trim())
      setEditingId(null)
      setEditingLabel('')
      onRefresh()
    } catch (e: any) { showToast(`Failed to label: ${e.message}`) }
  }, [editingLabel, showToast, onRefresh])

  if (history.length === 0) {
    return (
      <div className="card">
        <div className="empty">
          <p>No clips yet. Create your first one!</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
          History ({history.length})
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onRefresh}>Refresh</button>
      </div>

      {/* Active playback progress */}
      {playingEntry && playStatus?.playing && (
        <div className="card" style={{ padding: 14, marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>
            <span>{playStatus.mode === 'capture' ? 'Playing for Telegram...' : 'Previewing...'}</span>
            <span>{Math.round(playStatus.elapsed_secs)}s / {Math.round(playingEntry.duration_secs)}s</span>
          </div>
          <div className="vu-meter">
            <div className="fill" style={{
              width: `${Math.min(playStatus.progress_pct, 100)}%`,
              background: playStatus.mode === 'capture' ? 'linear-gradient(90deg, #e17055, #fdcb6e)' : undefined,
              transition: 'width 0.25s ease',
            }} />
          </div>
          <button className="btn btn-danger btn-sm" onClick={handleStop} style={{ marginTop: 8, width: '100%' }}>
            Stop
          </button>
        </div>
      )}

      {history.map(entry => (
        <div key={entry.id} className="history-item" style={{
          borderColor: playingEntry?.id === entry.id ? 'var(--accent)' : undefined,
        }}>
          <div className={`icon ${entry.type}`}>
            {entry.type === 'tts' ? 'T' : 'S'}
          </div>
          <div className="info">
            <div className="name">
              {entry.label || `Clip #${entry.id}`}
            </div>
            <div className="meta">
              {entry.timestamp.slice(0, 8)} · {entry.duration_secs}s
              {entry.voice_name && entry.voice_name !== entry.voice_id ? ` · ${entry.voice_name.slice(0, 25)}` : ''}
              {entry.text && ` · "${entry.text.slice(0, 30)}${entry.text.length > 30 ? '...' : ''}"`}
            </div>
          </div>
          <div className="actions">
            {playingEntry?.id === entry.id ? (
              <button className="btn btn-danger btn-sm" onClick={handleStop}>Stop</button>
            ) : (
              <>
                <button className="btn btn-ghost btn-sm" onClick={() => handlePreview(entry)} title="Preview through speakers">Play</button>
                <button className="btn btn-ghost btn-sm" onClick={() => handleCapture(entry)} title="Recapture for Telegram">Recap</button>
              </>
            )}
            <button className="btn btn-ghost btn-sm" onClick={() => { setEditingId(entry.id); setEditingLabel(entry.label) }} title="Label">Tag</button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(entry.id)} title="Delete">Del</button>
          </div>
        </div>
      ))}

      {editingId !== null && (
        <div className="card">
          <div className="label-row">
            <input type="text" value={editingLabel} onChange={e => setEditingLabel(e.target.value)}
              placeholder="Enter a label..." autoFocus
              onKeyDown={e => { if (e.key === 'Enter') handleLabel(editingId); if (e.key === 'Escape') setEditingId(null) }} />
            <button className="btn btn-primary btn-sm" onClick={() => handleLabel(editingId)}>Save</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
