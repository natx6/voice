import { useState, useCallback } from 'react'
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

  const handlePreview = useCallback(async (entry: HistoryEntry) => {
    try {
      await api.previewAudio(entry.file_path)
      showToast(`Previewing entry #${entry.id}...`)
    } catch (e: any) {
      showToast(`Preview failed: ${e.message}`)
    }
  }, [showToast])

  const handleCapture = useCallback(async (entry: HistoryEntry) => {
    try {
      await api.captureAudio(entry.file_path, 3)
      showToast(`Capturing entry #${entry.id} through VoiceChanger...`)
    } catch (e: any) {
      showToast(`Capture failed: ${e.message}`)
    }
  }, [showToast])

  const handleDelete = useCallback(async (id: number) => {
    try {
      await api.deleteHistory(id)
      showToast(`Deleted entry #${id}`)
      onRefresh()
    } catch (e: any) {
      showToast(`Delete failed: ${e.message}`)
    }
  }, [showToast, onRefresh])

  const handleLabel = useCallback(async (id: number) => {
    if (!editingLabel.trim()) return
    try {
      await api.labelHistory(id, editingLabel.trim())
      showToast(`Labeled entry #${id}`)
      setEditingId(null)
      setEditingLabel('')
      onRefresh()
    } catch (e: any) {
      showToast(`Failed to label: ${e.message}`)
    }
  }, [editingLabel, showToast, onRefresh])

  if (history.length === 0) {
    return (
      <div className="card">
        <div className="empty">
          <div className="emoji">📭</div>
          <p>No voice notes yet. Record or generate one!</p>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div className="card-title" style={{ margin: 0 }}>
          📋 History ({history.length})
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onRefresh}>
          🔄 Refresh
        </button>
      </div>

      {history.map(entry => (
        <div key={entry.id} className="history-item">
          <div className={`icon ${entry.type}`}>
            {entry.type === 'tts' ? '📝' : '🎙'}
          </div>
          <div className="info">
            <div className="name">
              {entry.label || `Voice Note #${entry.id}`}
            </div>
            <div className="meta">
              <span className={`pill ${entry.type}`}>{entry.type}</span>
              {' · '}
              {entry.timestamp.slice(0, 8)} · {entry.duration_secs}s
              {' · '}
              S={entry.stability.toFixed(2)}/B={entry.similarity_boost.toFixed(2)}
              {entry.text && ` · "${entry.text.slice(0, 30)}${entry.text.length > 30 ? '…' : ''}"`}
            </div>
          </div>
          <div className="actions">
            <button className="btn btn-ghost btn-sm" onClick={() => handlePreview(entry)} title="Preview through speakers">
              🔊
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleCapture(entry)} title="Capture for Telegram">
              📱
            </button>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => { setEditingId(entry.id); setEditingLabel(entry.label) }}
              title="Label"
            >
              🏷
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(entry.id)} title="Delete">
              🗑
            </button>
          </div>
        </div>
      ))}

      {/* Label dialog */}
      {editingId !== null && (
        <div className="card">
          <div className="label-row">
            <input
              type="text"
              value={editingLabel}
              onChange={e => setEditingLabel(e.target.value)}
              placeholder="Enter a label..."
              autoFocus
              onKeyDown={e => { if (e.key === 'Enter') handleLabel(editingId); if (e.key === 'Escape') setEditingId(null) }}
            />
            <button className="btn btn-primary btn-sm" onClick={() => handleLabel(editingId)}>
              Save
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setEditingId(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
