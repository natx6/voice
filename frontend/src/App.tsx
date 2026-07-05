import { useState, useEffect, useCallback } from 'react'
import type { VoiceSettings, HistoryEntry, VoiceInfo } from './types'
import * as api from './api'
import TTSTab from './components/TTSTab'
import HistoryTab from './components/HistoryTab'
import SettingsPage from './components/SettingsPage'
import AdminPage from './components/AdminPage'
import AccessAuth from './components/AccessAuth'
import WalletStatus from './components/WalletStatus'
import ThemeToggle from './components/ThemeToggle'

const DEFAULT_SETTINGS: VoiceSettings = {
  stability: 0.30, similarity_boost: 0.95, style_exaggeration: 0,
  speaker_boost: false, speed: 1.0, character: 'studio',
}

export default function App() {
  // Auto-detect admin token from URL: /?token=xxx / /#token=xxx / direct
  const urlToken = new URLSearchParams(window.location.search).get('token')
  if (urlToken) {
    localStorage.setItem('sh-admin-token', urlToken)
    // Clean URL by removing the token param
    window.history.replaceState({}, '', window.location.pathname)
  }
  const [hasAdmin, setHasAdmin] = useState(() => {
    try { return !!localStorage.getItem('sh-admin-token') } catch { return false }
  })
  // If token was in URL, auto-show admin
  const [tab, setTab] = useState<string>(urlToken ? 'admin' : 'create')
  const [status, setStatus] = useState<string>('connecting')
  const [voices, setVoices] = useState<VoiceInfo[]>([])
  const [selectedVoice, setSelectedVoice] = useState<string>('')
  const [settings] = useState<VoiceSettings>(DEFAULT_SETTINGS)
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [toast, setToast] = useState<string | null>(null)
  const [accessCode, setAccessCode] = useState<string>(() => {
    try { return localStorage.getItem('sh-access-code') || '' } catch { return '' }
  })

  const showToast = useCallback((msg: string) => {
    setToast(msg); setTimeout(() => setToast(null), 3000)
  }, [])

  const handleSignOut = useCallback(() => {
    localStorage.removeItem('sh-access-code')
    localStorage.removeItem('sh-admin-token')
    setAccessCode('')
    setHasAdmin(false)
  }, [])

  // Load status + voices on mount (cached for instant display)
  useEffect(() => {
    api.getStatus().then(s => setStatus(s.status === 'ok' ? 'online' : 'error')).catch(() => setStatus('offline'))

    // Load cached voices instantly, then refresh in background
    const cached = (() => {
      try { const r = localStorage.getItem('sh-voices-cache'); return r ? JSON.parse(r) : null } catch { return null }
    })()
    if (cached && Array.isArray(cached) && cached.length > 0) {
      setVoices(cached)
    }

    api.getVoices().then(v => {
      setVoices(v)
      // Cache for next load
      try { localStorage.setItem('sh-voices-cache', JSON.stringify(v)) } catch {}
      const saved = (() => { try { return localStorage.getItem('sh-voice') || '' } catch { return '' } })()
      if (saved && v.some(vo => vo.voice_id === saved)) setSelectedVoice(saved)
      else if (v.length > 0) setSelectedVoice(v[0].voice_id)
    }).catch((e) => console.error('Voices failed to load:', e))
  }, [])

  useEffect(() => { try { localStorage.setItem('sh-voice', selectedVoice) } catch {} }, [selectedVoice])

  // Persisted tab state
  const [ttsRawText, setTtsRawText] = useState(() => { try { return localStorage.getItem('sh-tts-raw') || '' } catch { return '' } })
  const [ttsRefinedText, setTtsRefinedText] = useState<string | null>(() => { try { return localStorage.getItem('sh-tts-refined') } catch { return null } })
  const [ttsLastFile, setTtsLastFile] = useState<string | null>(null)
  const [ttsDurationSecs, setTtsDurationSecs] = useState(0)

  useEffect(() => { try { localStorage.setItem('sh-tts-raw', ttsRawText) } catch {} }, [ttsRawText])
  useEffect(() => { if (ttsRefinedText !== null) try { localStorage.setItem('sh-tts-refined', ttsRefinedText) } catch {} }, [ttsRefinedText])

  useEffect(() => { if (tab === 'history') api.getHistory().then(setHistory).catch(() => {}) }, [tab])
  const refreshHistory = useCallback(async () => { try { setHistory(await api.getHistory()) } catch {} }, [])

  if (!accessCode) {
    return <AccessAuth onAuth={(code) => setAccessCode(code)} />
  }

  return (
    <>
      <header>
        <div className="brand">
          <div className="logo">sh</div>
          <div>
            <h1>soundhuman</h1>
            <div className="subtitle">code: {accessCode.slice(0, 8)}...</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <WalletStatus />
          <ThemeToggle />
          <div className={`status-badge ${status}`}>
            <span className={`status-dot ${status}`} />
          </div>
          <button className="btn btn-ghost btn-sm" onClick={handleSignOut}
            style={{ fontSize: 11, padding: '4px 8px' }}>Sign Out</button>
        </div>
      </header>

      <div className="tab-bar">
        <button className={tab === 'create' ? 'active' : ''} onClick={() => setTab('create')}>Create</button>
        <button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}>History</button>
        <button className={tab === 'settings' ? 'active' : ''} onClick={() => setTab('settings')}>Settings</button>
        {hasAdmin && (
          <button className={tab === 'admin' ? 'active' : ''} onClick={() => setTab('admin') as any}>Admin</button>
        )}
      </div>

      {tab === 'create' && (
        <TTSTab voiceId={selectedVoice} voices={voices} onSelectVoice={setSelectedVoice}
          settings={settings} onRefreshHistory={refreshHistory} showToast={showToast}
          rawText={ttsRawText} refinedText={ttsRefinedText} lastFile={ttsLastFile} durationSecs={ttsDurationSecs}
          onRawTextChange={setTtsRawText} onRefinedTextChange={setTtsRefinedText}
          onResult={(file, secs) => { setTtsLastFile(file); setTtsDurationSecs(secs) }} />
      )}

      {tab === 'history' && <HistoryTab history={history} onRefresh={refreshHistory} showToast={showToast} />}

      {tab === 'settings' && <SettingsPage />}

      {tab === 'admin' && hasAdmin && <AdminPage onAuth={() => setHasAdmin(true)} />}

      {toast && <div className="toast">{toast}</div>}
    </>
  )
}
