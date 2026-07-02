import { useState, useEffect, useCallback } from 'react'
import type { VoiceSettings, HistoryEntry, VoiceInfo } from './types'
import * as api from './api'
import TTSTab from './components/TTSTab'
import HistoryTab from './components/HistoryTab'
import WalletStatus from './components/WalletStatus'

const STORAGE_KEY = 'sh-settings'
const VOICE_KEY = 'sh-voice'
const TTS_RAW_KEY = 'sh-tts-raw'
const TTS_REFINED_KEY = 'sh-tts-refined'

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
  const [tab, setTab] = useState<'create' | 'history'>('create')
  const [status, setStatus] = useState<string>('connecting')
  const [voices, setVoices] = useState<VoiceInfo[]>([])
  const [selectedVoice, setSelectedVoice] = useState<string>(loadVoice)
  const [settings] = useState<VoiceSettings>(loadSettings)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [toast, setToast] = useState<string | null>(null)

  const showToast = useCallback((msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(null), 3000)
  }, [])

  // ── Load status + voices on mount ──
  useEffect(() => {
    api.getStatus()
      .then(s => setStatus(s.status === 'ok' ? 'online' : 'error'))
      .catch(() => setStatus('offline'))

    api.getVoices()
      .then(v => {
        setVoices(v)
        const saved = loadVoice()
        if (saved && v.some(vo => vo.voice_id === saved)) {
          setSelectedVoice(saved)
        } else if (v.length > 0) {
          setSelectedVoice(v[0].voice_id)
        }
      })
      .catch(() => {})
  }, [])

  // ── Persist ──
  useEffect(() => { try { localStorage.setItem(VOICE_KEY, selectedVoice) } catch {} }, [selectedVoice])

  // ── Persisted tab state ──
  const [ttsRawText, setTtsRawText] = useState(() => {
    try { return localStorage.getItem(TTS_RAW_KEY) || '' } catch { return '' }
  })
  const [ttsRefinedText, setTtsRefinedText] = useState<string | null>(() => {
    try { return localStorage.getItem(TTS_REFINED_KEY) } catch { return null }
  })
  const [ttsLastFile, setTtsLastFile] = useState<string | null>(null)
  const [ttsDurationSecs, setTtsDurationSecs] = useState(0)

  useEffect(() => { try { localStorage.setItem(TTS_RAW_KEY, ttsRawText) } catch {} }, [ttsRawText])
  useEffect(() => {
    if (ttsRefinedText !== null) {
      try { localStorage.setItem(TTS_REFINED_KEY, ttsRefinedText) } catch {}
    }
  }, [ttsRefinedText])

  useEffect(() => {
    if (tab === 'history') {
      api.getHistory().then(setHistory).catch(() => {})
    }
  }, [tab])

  const refreshHistory = useCallback(async () => {
    try { setHistory(await api.getHistory()) } catch {}
  }, [])

  return (
    <>
      <header>
        <div className="brand">
          <div className="logo">sh</div>
          <div>
            <h1>soundhuman</h1>
            <div className="subtitle">Text that sounds like you.</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <WalletStatus />
          <div className={`status-badge ${status}`} style={{ padding: '4px 8px' }}>
            <span className={`status-dot ${status}`} />
          </div>
        </div>
      </header>

      <div className="tab-bar">
        <button className={tab === 'create' ? 'active' : ''} onClick={() => setTab('create')}>
          Create
        </button>
        <button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}>
          History
        </button>
      </div>

      {tab === 'create' && (
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
        <HistoryTab history={history} onRefresh={refreshHistory} showToast={showToast} />
      )}

      {toast && <div className="toast">{toast}</div>}
    </>
  )
}
