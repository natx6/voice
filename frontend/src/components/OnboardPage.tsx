import { useState, useCallback, useEffect } from 'react'
import * as api from '../api'

interface Props {
  onComplete: (username: string, phrase?: string) => void
}

export default function OnboardPage({ onComplete }: Props) {
  const [step, setStep] = useState<'name' | 'phrase'>('name')
  const [username, setUsername] = useState('')
  const [suggestion, setSuggestion] = useState('')
  const [invite, setInvite] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [recoveryPhrase, setRecoveryPhrase] = useState('')
  const [phrasesaved, setPhraseSaved] = useState(false)

  useEffect(() => {
    api.fetchJson<{ suggestion: string }>('/onboard').then(r => setSuggestion(r.suggestion)).catch(() => {})
  }, [])

  const handleSubmit = useCallback(async () => {
    const name = username.trim() || suggestion
    if (!name || !invite.trim()) { setError('Username and invite code are required'); return }
    setLoading(true); setError('')
    try {
      const res = await api.fetchJson<any>(
        `/onboard?username=${encodeURIComponent(name)}&invite=${encodeURIComponent(invite.trim())}`,
        { method: 'POST' }
      )
      if (res.recovery_phrase) {
        setRecoveryPhrase(res.recovery_phrase)
        setStep('phrase')
      } else {
        localStorage.setItem('sh-user', name)
        onComplete(name)
      }
    } catch (e: any) { setError(e.message || 'Failed') }
    finally { setLoading(false) }
  }, [username, suggestion, invite, onComplete])

  const handlePhraseSaved = () => {
    localStorage.setItem('sh-user', username.trim() || suggestion)
    onComplete(username.trim() || suggestion, recoveryPhrase)
  }

  if (step === 'phrase') {
    return (
      <div style={{ maxWidth: 420, margin: '60px auto', padding: '0 16px' }}>
        <div className="card" style={{ padding: 24 }}>
          <div className="card-title" style={{ color: 'var(--yellow)', marginBottom: 16 }}>
            Save your recovery phrase
          </div>
          <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 16 }}>
            This is the only way to recover your account if you lose your device. Write it down or copy it somewhere safe.
          </p>
          <div style={{
            padding: '14px 16px', background: 'var(--surface-2)', borderRadius: 8,
            fontSize: 14, fontFamily: 'monospace', lineHeight: 1.8, marginBottom: 16,
            border: '1px solid var(--border)',
          }}>
            {recoveryPhrase.split(' ').map((w, i) => (
              <span key={i}>{w}{i < 11 ? ' ' : ''}</span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={() => navigator.clipboard.writeText(recoveryPhrase)}>
              Copy
            </button>
            <label style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              padding: '8px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 600,
              background: phrasesaved ? 'var(--green-dim)' : 'var(--surface-2)',
              color: phrasesaved ? 'var(--green)' : 'var(--text-dim)',
            }}>
              <input type="checkbox" checked={phrasesaved} onChange={e => setPhraseSaved(e.target.checked)}
                style={{ width: 'auto' }} />
              I saved it
            </label>
          </div>
          <button className="btn btn-primary btn-lg btn-block" disabled={!phrasesaved} onClick={handlePhraseSaved}>
            Continue
          </button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 420, margin: '60px auto', padding: '0 16px' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <div style={{
          width: 48, height: 48, borderRadius: 14,
          background: 'linear-gradient(135deg, var(--accent), #a29bfe)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 20, fontWeight: 700, color: 'white', margin: '0 auto 12px',
          boxShadow: '0 0 20px var(--accent-glow)',
        }}>sh</div>
        <h1 style={{ fontSize: 22, fontWeight: 700, letterSpacing: '-0.5px' }}>soundhuman</h1>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 4 }}>Invite-only</p>
      </div>

      <div className="card" style={{ padding: 24 }}>
        <div className="form-group">
          <label>Invite Code (required)</label>
          <input type="text" value={invite} onChange={e => setInvite(e.target.value)}
            placeholder="Paste your invite code" autoFocus />
        </div>
        <div className="form-group">
          <label>Choose your username</label>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="text" value={username} onChange={e => setUsername(e.target.value)}
              placeholder={suggestion || 'Loading...'} style={{ flex: 1 }}
              onKeyDown={e => { if (e.key === 'Enter') handleSubmit() }} />
            {suggestion && (
              <button className="btn btn-ghost btn-sm" onClick={() => setUsername(suggestion)}
                style={{ padding: '10px 12px', fontSize: 12, whiteSpace: 'nowrap' }}>Random</button>
            )}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
            Letters, numbers, dashes. 4-30 chars. Cannot be changed.
          </div>
        </div>

        {error && (
          <div style={{ fontSize: 12, color: 'var(--red)', marginBottom: 12, padding: '8px 12px', background: 'var(--red-dim)', borderRadius: 6 }}>
            {error}
          </div>
        )}

        <button className="btn btn-primary btn-lg btn-block" onClick={handleSubmit} disabled={loading || !invite.trim()}>
          {loading ? 'Creating...' : 'Create Account'}
        </button>
      </div>
    </div>
  )
}
