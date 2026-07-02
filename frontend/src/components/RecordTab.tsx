import { useState, useRef, useCallback } from 'react'
import type { VoiceSettings, VoiceInfo } from '../types'
import * as api from '../api'
import VUMeter from './VUMeter'
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
  lastFile: string | null
  durationSecs: number
  onResult: (file: string, secs: number) => void
}

export default function RecordTab({
  voiceId, voices, onSelectVoice, settings, onRefreshHistory, showToast,
  lastFile, durationSecs, onResult,
}: Props) {
  const [recording, setRecording] = useState(false)
  const [converting, setConverting] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [elapsed, setElapsed] = useState(0)

  const handleStartRecord = useCallback(async () => {
    try {
      await api.startRecord()
      setRecording(true)
      setElapsed(0)
      intervalRef.current = setInterval(() => setElapsed(e => e + 1), 1000)
    } catch (e: any) {
      showToast(`Failed to start recording: ${e.message}`)
    }
  }, [showToast])

  const handleStopRecord = useCallback(async () => {
    try {
      const result = await api.stopRecord()
      setRecording(false)
      if (intervalRef.current) clearInterval(intervalRef.current)
      onResult(result.file_path, result.duration_secs)
      showToast(`Recorded ${result.duration_secs}s — now convert it`)
    } catch (e: any) {
      showToast(`Failed to stop recording: ${e.message}`)
      setRecording(false)
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [showToast, onResult])

  const handleConvert = useCallback(async () => {
    if (!lastFile) return
    if (!voiceId) {
      showToast('Select a voice first')
      return
    }
    setConverting(true)
    try {
      const result = await api.convertAudio(voiceId, lastFile, settings)
      onResult(result.file_path, result.duration_secs)
      showToast(`Converted! ${result.duration_secs}s — preview or capture`)
      onRefreshHistory()
    } catch (e: any) {
      showToast(`Conversion failed: ${e.message}`)
    } finally {
      setConverting(false)
    }
  }, [lastFile, voiceId, settings, showToast, onRefreshHistory, onResult])

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

  return (
    <div>
      <div className="card">
        <div className="card-title">🎤 Record Voice Note</div>

        <VoicePicker voices={voices} selected={voiceId} onChange={onSelectVoice} />
        <VUMeter recording={recording} />

        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          {!recording ? (
            <button className="btn btn-primary" onClick={handleStartRecord}>
              🔴 Start Recording
            </button>
          ) : (
            <button className="btn btn-danger" onClick={handleStopRecord}>
              ⏹ Stop Recording ({elapsed}s)
            </button>
          )}
        </div>
      </div>

      {lastFile && !recording && (
        <div className="card">
          <div className="card-title">✅ Recorded</div>
          <p style={{ marginBottom: 12, fontSize: 14 }}>
            {durationSecs}s of audio captured
          </p>
          <button
            className="btn btn-primary"
            onClick={handleConvert}
            disabled={converting}
            style={{ width: '100%' }}
          >
            {converting ? '⏳ Converting...' : '🔄 Convert with ElevenLabs'}
          </button>
        </div>
      )}

      {lastFile && !recording && !converting && (
        <PlaybackProgress
          onPreview={handlePreview}
          onCapture={handleCapture}
          durationSecs={durationSecs}
        />
      )}
    </div>
  )
}
