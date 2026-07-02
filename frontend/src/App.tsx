import { useState, useEffect, useCallback, useRef } from 'react'
import type { TabName, VoiceSettings, HistoryEntry, VoiceInfo } from './types'
import * as api from './api'
import RecordTab from './components/RecordTab'
import TTSTab from './components/TTSTab'
import HistoryTab from './components/HistoryTab'
import SettingsTab from './components/SettingsTab'

const STORAGE_KEY = 'voice-studio-settings'
const VOICE_KEY = 'voice-studio-voice'
const TTS_RAW_KEY = 'voice-studio-tts-raw'
const TTS_REFINED_KEY = 'voice-studio-tts-refined'

const DEFAULT_SETTINGS: VoiceSettings = {
  stability: 0.30,
  similarity_boost: 0.95,
  style_exaggeration: 0,
  speaker_boost: false,
  speed: 1.0,
  character: 'studio',
}

function loadSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) }
  } catch {}
  return DEFAULT_SETTINGS
}

function loadVoice(): string {
  try {
    return localStorage.getItem(VOICE_KEY) || ''
  } catch { return '' }
}

export default function App() {
  const [tab, setTab] = useState<TabName>('record')
  const [status, setStatus] = useState<string>('connecting')
  const [voices, setVoices] = useState<VoiceInfo[]>([])
  const [selectedVoice, setSelectedVoice] = useState<string>(loadVoice)
  const [settings, setSettings] = useState<VoiceSettings>(loadSettings)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [toast, setToast] = useState<string | null>(null)

  // ── Persisted tab state (survives tab switches) ──
  const [ttsRawText, setTtsRawText] = useState(() => {
    try { return localStorage.getItem(TTS_RAW_KEY) || '' } catch { return '' }
  })
  const [ttsRefinedText, setTtsRefinedText] = useState<string | null>(() => {
    try { return localStorage.getItem(TTS_REFINED_KEY) } catch { return null }
  })
  const [ttsLastFile, setTtsLastFile] = useState<string | null>(null)
  const [ttsDurationSecs, setTtsDurationSecs] = useState(0)
  const [recordLastFile, setRecordLastFile] = useState<string | null>(null)
  const [recordDurationSecs, setRecordDurationSecs] = useState(0)

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }, [])

  // ── Load status + voices on mount ──

  useEffect(() => {
    api.getStatus()
      .then(s => {
        setStatus(s.status === 'ok' ? 'online' : 'error')
      })
      .catch(() => setStatus('offline'))

    api.getVoices()
      .then(v => {
        setVoices(v)
        // If saved voice exists and is in the list, keep it; else use first
        const saved = loadVoice()
        if (saved && v.some(vo => vo.voice_id === saved)) {
          setSelectedVoice(saved)
        } else if (v.length > 0) {
          setSelectedVoice(v[0].voice_id)
        }
      })
      .catch(() => {})
  }, [])

  // ── Persist settings, voice, and TTS text to localStorage ──

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(settings)) } catch {}
  }, [settings])

  useEffect(() => {
    try { localStorage.setItem(VOICE_KEY, selectedVoice) } catch {}
  }, [selectedVoice])

  useEffect(() => {
    try { localStorage.setItem(TTS_RAW_KEY, ttsRawText) } catch {}
  }, [ttsRawText])

  useEffect(() => {
    if (ttsRefinedText !== null) {
      try { localStorage.setItem(TTS_REFINED_KEY, ttsRefinedText) } catch {}
    }
  }, [ttsRefinedText])

  // ── Refresh history when tab changes ──

  useEffect(() => {
    if (tab === 'history') {
      api.getHistory()
        .then(setHistory)
        .catch(() => {})
    }
  }, [tab])

  const refreshHistory = useCallback(async () => {
    try {
      const h = await api.getHistory()
      setHistory(h)
    } catch {}
  }, [])

  return (
    <>
      <header>
        <div>
          <h1>🎙️ Voice Studio</h1>
          <div className="subtitle">ElevenLabs Voice Changer</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`status-dot ${status}`} />
          <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
            {status === 'online' ? 'Connected' : status === 'connecting' ? 'Connecting…' : 'Offline'}
          </span>
        </div>
      </header>

      <div className="tab-bar">
        {(['record', 'tts', 'history', 'settings'] as TabName[]).map(t => (
          <button
            key={t}
            className={tab === t ? 'active' : ''}
            onClick={() => setTab(t)}
          >
            {t === 'record' && '🎤 Record'}
            {t === 'tts' && '📝 TTS'}
            {t === 'history' && '📋 History'}
            {t === 'settings' && '⚙️ Settings'}
          </button>
        ))}
      </div>

      {tab === 'record' && (
        <RecordTab
          voiceId={selectedVoice}
          voices={voices}
          onSelectVoice={setSelectedVoice}
          settings={settings}
          onRefreshHistory={refreshHistory}
          showToast={showToast}
          lastFile={recordLastFile}
          durationSecs={recordDurationSecs}
          onResult={(file, secs) => { setRecordLastFile(file); setRecordDurationSecs(secs) }}
        />
      )}

      {tab === 'tts' && (
        <TTSTab
          voiceId={selectedVoice}
          voices={voices}
          onSelectVoice={setSelectedVoice}
          settings={settings}
          onRefreshHistory={refreshHistory}
          showToast={showToast}
          rawText={ttsRawText}
          refinedText={ttsRefinedText}
          lastFile={ttsLastFile}
          durationSecs={ttsDurationSecs}
          onRawTextChange={setTtsRawText}
          onRefinedTextChange={setTtsRefinedText}
          onResult={(file, secs) => { setTtsLastFile(file); setTtsDurationSecs(secs) }}
        />
      )}

      {tab === 'history' && (
        <HistoryTab
          history={history}
          onRefresh={refreshHistory}
          showToast={showToast}
        />
      )}

      {tab === 'settings' && (
        <SettingsTab
          settings={settings}
          onChange={setSettings}
          voices={voices}
          showToast={showToast}
        />
      )}

      {toast && <div className="toast">{toast}</div>}
    </>
  )
}
