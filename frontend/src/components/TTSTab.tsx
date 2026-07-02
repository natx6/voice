import React, { useState, useCallback, useRef } from 'react'
import type { VoiceSettings, VoiceInfo } from '../types'
import * as api from '../api'
import VoicePicker from './VoicePicker'
import PlaybackProgress from './PlaybackProgress'

interface Props {
  voiceId: string
  voices: VoiceInfo[]
  onSelectVoice: (id: string) => void
  settings: VoiceSettings
  onRefreshHistory: () => void
  showToast: (msg: string) => void
  rawText: string
  refinedText: string | null
  lastFile: string | null
  durationSecs: number
  onRawTextChange: (text: string) => void
  onRefinedTextChange: (text: string | null) => void
  onResult: (file: string, secs: number) => void
}

const FLAIRS = [
  { id: 'auto', label: 'Auto', color: '#6c5ce7' },
  { id: 'sad', label: 'Sad', color: '#74b9ff' },
  { id: 'excited', label: 'Excited', color: '#fdcb6e' },
  { id: 'angry', label: 'Angry', color: '#e17055' },
  { id: 'anxious', label: 'Anxious', color: '#fd79a8' },
  { id: 'smug', label: 'Smug', color: '#a29bfe' },
  { id: 'comforting', label: 'Kind', color: '#00cec9' },
]

function LoadingDots({ label, pct }: { label: string; pct?: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
      <span style={{ display: 'inline-flex', gap: 3 }}>
        {[0, 1, 2].map(i => (
          <span key={i} style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'currentColor', opacity: 0.6,
            animation: `loadDot 1.2s ease-in-out ${i * 0.2}s infinite`,
          }} />
        ))}
      </span>
      {label}
      {pct !== undefined && (
        <span style={{ fontSize: 12, opacity: 0.7, fontVariantNumeric: 'tabular-nums' }}>
          {Math.round(pct)}%
        </span>
      )}
    </span>
  )
}

function highlightTags(text: string): any {
  const tagRegex = /(\[[^\]]+\])/g
  const parts = text.split(tagRegex)
  return parts.map((part, i) => {
    if (!part.startsWith('[') || !part.endsWith(']')) return part
    const inner = part.slice(1, -1).toLowerCase()
    let color = '#6c5ce7'
    if (inner.startsWith('pause')) color = '#0984e3'
    else if (['gasp', 'sigh', 'clears throat', 'yawns', 'groans', 'sniffling', 'rapid breathing', 'heavy breath', 'soft breath'].some(t => inner.includes(t)))
      color = '#00b894'
    else if (['whispers', 'whisper', 'muttering', 'vocal fry'].some(t => inner.includes(t)))
      color = '#fd79a8'
    else if (['laughs', 'laugh', 'giggling', 'giggles', 'chuckles'].some(t => inner.includes(t)))
      color = '#fdcb6e'
    else if (['scoffs', 'frustrated', 'annoyed', 'impatient', 'groans'].some(t => inner.includes(t)))
      color = '#e17055'
    return (
      <span key={i} style={{ color, fontWeight: 600, fontSize: 13, background: `${color}15`, borderRadius: 4, padding: '1px 4px' }}>
        {part}
      </span>
    )
  })
}

export default function TTSTab({
  voiceId, voices, onSelectVoice, settings, onRefreshHistory, showToast,
  rawText, refinedText, lastFile, durationSecs,
  onRawTextChange, onRefinedTextChange, onResult,
}: Props) {
  const [refining, setRefining] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genPct, setGenPct] = useState(0)
  const [flair, setFlair] = useState('auto')
  const [stage, setStage] = useState<'input' | 'edit' | 'variations' | 'done'>(() => refinedText ? 'edit' : 'input')
  const [variations, setVariations] = useState<api.TTSResult[]>([])
  const [selectedVar, setSelectedVar] = useState<api.TTSResult | null>(null)
  const [genVariations, setGenVariations] = useState(() => {
    try { return localStorage.getItem('sh-variations') === 'true' } catch { return true }
  })
  const abortRef = useRef<AbortController | null>(null)
  const genTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const handleRefine = useCallback(async () => {
    if (!rawText.trim()) { showToast('Enter some text first'); return }
    setRefining(true)
    try {
      const result = await api.refineText(rawText, flair === 'auto' ? undefined : flair)
      onRefinedTextChange(result.refined)
      setStage('edit')
    } catch (e: any) { showToast(`Refinement failed: ${e.message}`) }
    finally { setRefining(false) }
  }, [rawText, flair, showToast, onRefinedTextChange])

  const handleGenerateVariations = useCallback(async () => {
    const text = refinedText ?? rawText
    if (!text.trim() || !voiceId) return
    setGenerating(true)
    setGenPct(0)
    setVariations([])
    setSelectedVar(null)

    const count = genVariations ? 3 : 1
    const estTotalSecs = Math.max(3, Math.round(text.length / 20) * count)
    const timerStart = Date.now()
    genTimerRef.current = setInterval(() => {
      const elapsed = (Date.now() - timerStart) / 1000
      setGenPct(Math.min(95, (elapsed / estTotalSecs) * 100))
    }, 200)

    try {
      if (genVariations) {
        const results = await api.generateTTSVariations(text, voiceId, settings, 3)
        setVariations(results)
        setStage('variations')
      } else {
        const result = await api.generateTTS(text, voiceId, settings)
        setSelectedVar(result)
        onResult(result.file_path, result.duration_secs)
        setStage('done')
        showToast(`Generated ${result.duration_secs}s`)
        onRefreshHistory()
      }
    } catch (e: any) {
      showToast(`Generation failed: ${e.message}`)
    } finally {
      setGenerating(false)
      setGenPct(0)
      if (genTimerRef.current) { clearInterval(genTimerRef.current); genTimerRef.current = null }
    }
  }, [refinedText, rawText, voiceId, settings, genVariations, showToast, onResult, onRefreshHistory])

  const handlePickVariation = useCallback((v: api.TTSResult) => {
    setSelectedVar(v)
    onResult(v.file_path, v.duration_secs)
    setStage('done')
  }, [onResult])

  const handlePreview = useCallback(async () => {
    if (!selectedVar?.file_path) return
    try { await api.previewAudio(selectedVar.file_path, settings.speed, settings.character) }
    catch (e: any) { showToast(`Preview failed: ${e.message}`) }
  }, [selectedVar, settings.speed, settings.character, showToast])

  const handleCapture = useCallback(async () => {
    if (!selectedVar?.file_path) return
    try { await api.captureAudio(selectedVar.file_path, 3, settings.speed, settings.character) }
    catch (e: any) { showToast(`Capture failed: ${e.message}`) }
  }, [selectedVar, settings.speed, settings.character, showToast])

  const handleReset = () => {
    onRawTextChange(''); onRefinedTextChange(null); setVariations([]); setSelectedVar(null); setStage('input')
  }

  // Play a variation to preview it
  const [previewingId, setPreviewingId] = useState<number | null>(null)
  const handlePreviewVar = useCallback(async (v: api.TTSResult) => {
    setPreviewingId(v.seed ?? v.history_id)
    try { await api.previewAudio(v.file_path) }
    catch {}
    setPreviewingId(null)
  }, [])

  return (
    <div>
      {/* Input */}
      {stage === 'input' && (
        <div className="card">
          <div style={{ display: 'flex', gap: 4, marginBottom: 12, flexWrap: 'wrap' }}>
            {FLAIRS.map(f => (
              <button key={f.id} onClick={() => setFlair(f.id)} style={{
                padding: '5px 12px', borderRadius: 20, border: 'none',
                fontSize: 12, fontWeight: 600, cursor: 'pointer',
                background: flair === f.id ? f.color : 'var(--surface-2)',
                color: flair === f.id ? 'white' : 'var(--text-dim)',
                transition: 'all 0.15s',
              }}>{f.label}</button>
            ))}
          </div>
          <div className="form-group" style={{ marginBottom: 0 }}>
            <textarea value={rawText} onChange={e => onRawTextChange(e.target.value)}
              placeholder="Paste what you want to say..." rows={6}
              style={{ fontSize: 15, lineHeight: 1.6, minHeight: 160 }} autoFocus />
          </div>
          {rawText.trim().length > 0 && (
            <div style={{ marginTop: 12 }}>
              {refining ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                  padding: 14, borderRadius: 'var(--radius-sm)',
                  background: 'var(--surface-2)', color: 'var(--text-dim)', fontSize: 14, fontWeight: 500 }}>
                  <LoadingDots label="Refining..." />
                </div>
              ) : (
                <button className="btn btn-primary btn-lg btn-block" onClick={handleRefine}>Make it sound human</button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Edit refined text */}
      {stage === 'edit' && refinedText !== null && (
        <>
          <div className="card" style={{ borderColor: 'var(--accent)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12,
              fontSize: 12, fontWeight: 600, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', boxShadow: '0 0 6px var(--accent-glow)' }} />
              Edited for speech
            </div>
            <div style={{ fontSize: 15, lineHeight: 1.8, padding: '12px 14px',
              background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)', marginBottom: 8, minHeight: 80,
              border: '1px solid var(--border)' }}>
              {highlightTags(refinedText)}
            </div>
            <div className="form-group" style={{ marginBottom: 12 }}>
              <textarea value={refinedText} onChange={e => onRefinedTextChange(e.target.value)}
                rows={4} style={{ fontSize: 14, lineHeight: 1.6, minHeight: 100, borderColor: 'var(--accent)' }} />
              <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 6, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <span><span style={{ color: '#6c5ce7', fontWeight: 700 }}>■</span> Emotion</span>
                <span><span style={{ color: '#0984e3', fontWeight: 700 }}>■</span> Pause</span>
                <span><span style={{ color: '#00b894', fontWeight: 700 }}>■</span> Breath</span>
                <span><span style={{ color: '#fd79a8', fontWeight: 700 }}>■</span> Voice</span>
                <span><span style={{ color: '#fdcb6e', fontWeight: 700 }}>■</span> Laugh</span>
                <span><span style={{ color: '#e17055', fontWeight: 700 }}>■</span> Frustration</span>
              </div>
            </div>

            <div style={{ marginTop: 16 }}>
              {generating ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    padding: 14, borderRadius: 'var(--radius-sm)', background: 'var(--accent-subtle)', color: 'var(--accent)',
                    fontSize: 14, fontWeight: 500 }}>
                    <LoadingDots label={genVariations ? 'Generating 3 variations...' : 'Generating...'} pct={genPct} />
                  </div>
                </div>
              ) : (
                <>
                  {/* Variations toggle */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 12 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>Variations</span>
                    <button
                      onClick={() => {
                        const next = !genVariations
                        setGenVariations(next)
                        try { localStorage.setItem('sh-variations', String(next)) } catch {}
                      }}
                      style={{
                        width: 36, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer',
                        background: genVariations ? 'var(--accent)' : 'var(--border)',
                        position: 'relative', transition: 'background 0.15s',
                      }}
                    >
                      <div style={{
                        width: 16, height: 16, borderRadius: '50%', background: 'white',
                        position: 'absolute', top: 2,
                        left: genVariations ? 18 : 2,
                        transition: 'left 0.15s',
                      }} />
                    </button>
                  </div>
                  <button className="btn btn-primary btn-lg btn-block" onClick={handleGenerateVariations}>
                    {genVariations ? 'Generate 3 variations' : 'Generate audio'}
                  </button>
                </>
              )}
            </div>
            <div style={{ marginTop: 8 }}>
              <button className="btn btn-ghost btn-sm btn-block" onClick={handleReset}>Start over</button>
            </div>
          </div>

          <div className="card" style={{ padding: 14 }}>
            <VoicePicker voices={voices} selected={voiceId} onChange={onSelectVoice} />
          </div>
        </>
      )}

      {/* Pick a variation */}
      {stage === 'variations' && variations.length > 0 && (
        <>
          <div style={{ marginBottom: 12, fontSize: 12, fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Pick the best one
          </div>
          {variations.map((v, i) => {
            const isPlaying = previewingId === (v.seed ?? v.history_id)
            return (
              <div key={v.history_id} className="history-item" style={{ cursor: 'pointer', borderColor: selectedVar?.history_id === v.history_id ? 'var(--accent)' : undefined }}
                onClick={() => handlePickVariation(v)}>
                <div style={{ width: 28, height: 28, borderRadius: 8, background: 'var(--accent)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, color: 'white', flexShrink: 0 }}>
                  {i + 1}
                </div>
                <div className="info">
                  <div className="name">Variation {i + 1}</div>
                  <div className="meta">{v.duration_secs}s · seed {v.seed ?? '?'}</div>
                </div>
                <div className="actions">
                  <button className="btn btn-ghost btn-sm" onClick={e => { e.stopPropagation(); handlePreviewVar(v) }} disabled={isPlaying}>
                    {isPlaying ? 'Playing...' : 'Preview'}
                  </button>
                  <button className="btn btn-primary btn-sm" onClick={() => handlePickVariation(v)}>Select</button>
                </div>
              </div>
            )
          })}
        </>
      )}

      {/* Done — selected variation */}
      {stage === 'done' && selectedVar && (
        <>
          <div className="card" style={{ padding: 14, marginBottom: 12, borderColor: 'var(--green)' }}>
            <div style={{ fontSize: 11, color: 'var(--green)', fontWeight: 600, marginBottom: 4 }}>
              Selected — Variation {variations.findIndex(v => v.history_id === selectedVar?.history_id) + 1}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
              {selectedVar.duration_secs}s
            </div>
          </div>
          <PlaybackProgress onPreview={handlePreview} onCapture={handleCapture} durationSecs={selectedVar.duration_secs} />
          <div className="card" style={{ padding: 14 }}>
            <VoicePicker voices={voices} selected={voiceId} onChange={onSelectVoice} />
          </div>
          <button className="btn btn-ghost btn-sm btn-block" onClick={handleReset} style={{ marginTop: 8 }}>
            Create another
          </button>
        </>
      )}
    </div>
  )
}
