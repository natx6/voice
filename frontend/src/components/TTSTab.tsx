import { useState, useCallback } from 'react'
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
  // Persisted state (survives tab switches)
  rawText: string
  refinedText: string | null
  lastFile: string | null
  durationSecs: number
  onRawTextChange: (text: string) => void
  onRefinedTextChange: (text: string | null) => void
  onResult: (file: string, secs: number) => void
}

export default function TTSTab({
  voiceId, voices, onSelectVoice, settings, onRefreshHistory, showToast,
  rawText, refinedText, lastFile, durationSecs,
  onRawTextChange, onRefinedTextChange, onResult,
}: Props) {
  const [refining, setRefining] = useState(false)
  const [generating, setGenerating] = useState(false)

  const handleRefine = useCallback(async () => {
    if (!rawText.trim()) {
      showToast('Enter some text first')
      return
    }
    setRefining(true)
    try {
      const result = await api.refineText(rawText)
      onRefinedTextChange(result.refined)
      showToast(`Refined by ${result.provider} — ${result.refined.length} chars`)
    } catch (e: any) {
      showToast(`Refinement failed: ${e.message}`)
    } finally {
      setRefining(false)
    }
  }, [rawText, showToast, onRefinedTextChange])

  const handleGenerate = useCallback(async () => {
    const text = refinedText ?? rawText
    if (!text.trim()) {
      showToast('Enter some text first')
      return
    }
    if (!voiceId) {
      showToast('Select a voice first')
      return
    }
    setGenerating(true)
    try {
      const result = await api.generateTTS(text, voiceId, settings)
      onResult(result.file_path, result.duration_secs)
      showToast(`Generated ${result.duration_secs}s (${result.chars} chars)`)
      onRefreshHistory()
    } catch (e: any) {
      showToast(`TTS failed: ${e.message}`)
    } finally {
      setGenerating(false)
    }
  }, [refinedText, rawText, voiceId, settings, showToast, onRefreshHistory, onResult])

  const handlePreview = useCallback(async () => {
    if (!lastFile) return
    try {
      await api.previewAudio(lastFile, settings.speed, settings.character)
    } catch (e: any) {
      showToast(`Preview failed: ${e.message}`)
    }
  }, [lastFile, settings.speed, settings.character, showToast])

  const handleCapture = useCallback(async () => {
    if (!lastFile) return
    try {
      await api.captureAudio(lastFile, 3, settings.speed, settings.character)
    } catch (e: any) {
      showToast(`Capture failed: ${e.message}`)
    }
  }, [lastFile, settings.speed, settings.character, showToast])

  const chars = (refinedText ?? rawText).length
  const estSecs = Math.round(chars / 20)

  return (
    <div>
      {/* Step 1: Raw input */}
      <div className="card">
        <div className="card-title">📝 Step 1: Write or paste your text</div>

        <div className="form-group">
          <textarea
            value={rawText}
            onChange={e => { onRawTextChange(e.target.value); onRefinedTextChange(null) }}
            placeholder="Paste your raw text here — written, formal, whatever. We'll make it conversational."
            rows={4}
            style={{ fontSize: 13, opacity: refinedText ? 0.5 : 1 }}
            disabled={refinedText !== null}
          />
        </div>

        {refinedText === null && (
          <button
            className="btn btn-primary"
            onClick={handleRefine}
            disabled={refining || !rawText.trim()}
            style={{ width: '100%' }}
          >
            {refining ? '⏳ Thinking...' : '💬 Make Conversational'}
          </button>
        )}

        {refinedText !== null && (
          <button
            className="btn btn-ghost"
            onClick={() => { onRefinedTextChange(null) }}
            style={{ width: '100%' }}
          >
            ↩ Back to raw text
          </button>
        )}

        {!rawText.trim() && refinedText === null && (
          <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 8, textAlign: 'center' }}>
            Uses DeepSeek AI (falls back to rule-based if no DEEPSEEK_API_KEY set)
          </div>
        )}
      </div>

      {/* Step 2: Refined preview (editable) */}
      {refinedText !== null && (
        <div className="card" style={{ borderColor: 'var(--accent)' }}>
          <div className="card-title">💡 Step 2: Conversational version — edit if you like</div>

          <div className="form-group">
            <textarea
              value={refinedText}
              onChange={e => onRefinedTextChange(e.target.value)}
              rows={5}
              style={{ fontSize: 13, borderColor: 'var(--accent)' }}
            />
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4, display: 'flex', justifyContent: 'space-between' }}>
              <span>✏️ You can edit this directly before generating</span>
              <span>{chars} chars · ~{estSecs}s estimated</span>
            </div>
          </div>

          <VoicePicker voices={voices} selected={voiceId} onChange={onSelectVoice} />

          <button
            className="btn btn-primary"
            onClick={handleGenerate}
            disabled={generating || !refinedText.trim()}
            style={{ width: '100%', marginTop: 8 }}
          >
            {generating ? '⏳ Generating...' : '🎯 Generate Voice from Preview'}
          </button>
        </div>
      )}

      {/* Step 3: Playback */}
      {lastFile && !generating && (
        <PlaybackProgress
          onPreview={handlePreview}
          onCapture={handleCapture}
          durationSecs={durationSecs}
        />
      )}
    </div>
  )
}
