import { useState, useCallback } from 'react'
import * as api from '../api'

interface Props {
  onAuth: () => void
}

export default function AuthPage({ onAuth }: Props) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  const handleLogin = useCallback(async () => {
    if (!email || !password) return
    setLoading(true); setError(''); setSuccess('')
    try {
      await api.login(email, password)
      setSuccess('Signed in!')
      setTimeout(() => onAuth(), 400)
    } catch (e: any) {
      setError(e.message || 'Login failed')
    } finally { setLoading(false) }
  }, [email, password, onAuth])

  const handleSignup = useCallback(async () => {
    if (!email || !password || !inviteCode) return
    setLoading(true); setError(''); setSuccess('')
    try {
      await api.signup(email, password, inviteCode)
      setSuccess('Account created!')
      setTimeout(() => onAuth(), 400)
    } catch (e: any) {
      setError(e.message || 'Signup failed')
    } finally { setLoading(false) }
  }, [email, password, inviteCode, onAuth])

  return (
    <div style={{
      maxWidth: 400, margin: '60px auto', padding: '0 16px',
    }}>
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <div style={{
          width: 48, height: 48, borderRadius: 14,
          background: 'linear-gradient(135deg, var(--accent), #a29bfe)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 22, fontWeight: 700, color: 'white', margin: '0 auto 12px',
          boxShadow: '0 0 20px var(--accent-glow)',
        }}>sh</div>
        <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 4, letterSpacing: '-0.5px' }}>
          soundhuman
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-dim)' }}>
          {mode === 'login' ? 'Welcome back' : 'Create your account'}
        </p>
      </div>

      <div className="card" style={{ padding: 24 }}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 20, background: 'var(--surface-2)', borderRadius: 8, padding: 3 }}>
          <button style={{
            flex: 1, padding: '8px 0', border: 'none', borderRadius: 6,
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
            background: mode === 'login' ? 'var(--accent)' : 'transparent',
            color: mode === 'login' ? 'white' : 'var(--text-dim)',
            transition: 'all 0.15s',
          }} onClick={() => setMode('login')}>Sign In</button>
          <button style={{
            flex: 1, padding: '8px 0', border: 'none', borderRadius: 6,
            fontSize: 13, fontWeight: 600, cursor: 'pointer',
            background: mode === 'signup' ? 'var(--accent)' : 'transparent',
            color: mode === 'signup' ? 'white' : 'var(--text-dim)',
            transition: 'all 0.15s',
          }} onClick={() => setMode('signup')}>Sign Up</button>
        </div>

        <div className="form-group">
          <label>Email</label>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com" autoFocus />
        </div>

        <div className="form-group">
          <label>Password</label>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
            placeholder="At least 6 characters" />
        </div>

        {mode === 'signup' && (
          <div className="form-group">
            <label>Invite Code</label>
            <input type="text" value={inviteCode} onChange={e => setInviteCode(e.target.value)}
              placeholder="Paste your invite code" />
          </div>
        )}

        {error && (
          <div style={{ fontSize: 12, color: 'var(--red)', marginBottom: 12, padding: '8px 12px', background: 'var(--red-dim)', borderRadius: 6 }}>
            {error}
          </div>
        )}

        {success && (
          <div style={{
            fontSize: 14, color: 'var(--green)', marginBottom: 12,
            padding: '12px', background: 'var(--green-dim)', borderRadius: 6,
            textAlign: 'center', fontWeight: 600,
          }}>
            <div style={{ marginBottom: 4 }}>
              <span style={{
                display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                background: 'var(--green)', marginRight: 8,
                animation: 'loadDot 1s ease-in-out infinite',
              }} />
              {success}
            </div>
            <div style={{ fontSize: 11, fontWeight: 400, opacity: 0.7 }}>Redirecting...</div>
          </div>
        )}

        <button
          className="btn btn-primary btn-lg btn-block"
          onClick={mode === 'login' ? handleLogin : handleSignup}
          disabled={loading || !!success}
          style={{ marginTop: 4 }}
        >
          {loading ? (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span style={{ display: 'inline-flex', gap: 3 }}>
                {[0, 1, 2].map(i => (
                  <span key={i} style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: 'white', opacity: 0.6,
                    animation: `loadDot 1.2s ease-in-out ${i * 0.2}s infinite`,
                  }} />
                ))}
              </span>
              {mode === 'login' ? 'Signing in...' : 'Creating account...'}
            </span>
          ) : success ? 'Done!' : mode === 'login' ? 'Sign In' : 'Create Account'}
        </button>
      </div>
    </div>
  )
}
