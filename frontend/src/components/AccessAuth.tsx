import { useState, useCallback, useEffect } from 'react'

interface Props {
  onAuth: (code: string) => void
}

export default function AccessAuth({ onAuth }: Props) {
  const [mode, setMode] = useState<'login' | 'signup' | 'showcode'>('login')
  const [code, setCode] = useState('')
  const [email, setEmail] = useState('')
  const [invite, setInvite] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [accessCode, setAccessCode] = useState('')

  const handleLogin = useCallback(async () => {
    if (!code.trim()) return
    setLoading(true); setError('')
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code.trim() }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Invalid code')
      localStorage.setItem('sh-access-code', code.trim())
      onAuth(code.trim())
    } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }, [code, onAuth])

  const handleSignup = useCallback(async () => {
    if (!email || !invite) return
    setLoading(true); setError('')
    try {
      const r = await fetch(`/api/auth/signup?email=${encodeURIComponent(email)}&invite=${encodeURIComponent(invite)}`, { method: 'POST' })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Signup failed')
      setAccessCode(d.access_code)
      setMode('showcode')
    } catch (e: any) { setError(e.message) }
    finally { setLoading(false) }
  }, [email, invite])

  const handleGotIt = () => {
    localStorage.setItem('sh-access-code', accessCode)
    setCode(accessCode)
    setMode('login')
  }

  if (mode === 'showcode') {
    return (
      <div style={{ maxWidth: 420, margin: '60px auto', padding: '0 16px' }}>
        <div className="card" style={{ padding: 24 }}>
          <div className="card-title" style={{ color: 'var(--yellow)', marginBottom: 12 }}>Your Access Code</div>
          <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 16 }}>
            Save this code. You'll use it to log in. If you lose it, you lose access to your account.
          </p>
          <div style={{
            padding: '14px 16px', background: 'var(--surface-2)', borderRadius: 8,
            fontSize: 18, fontFamily: 'monospace', textAlign: 'center', letterSpacing: 2,
            border: '1px solid var(--border)', marginBottom: 16,
          }}>
            {accessCode}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary btn-sm" style={{ flex: 1 }}
              onClick={() => navigator.clipboard.writeText(accessCode)}>Copy</button>
            <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={handleGotIt}>
              I saved it — Log in
            </button>
          </div>
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
      </div>

      {mode === 'login' ? (
        <div className="card" style={{ padding: 24 }}>
          <div className="form-group">
            <label>Access Code</label>
            <input type="text" value={code} onChange={e => setCode(e.target.value)}
              placeholder="Paste your access code" autoFocus
              onKeyDown={e => { if (e.key === 'Enter') handleLogin() }} />
          </div>
          {error && <div style={{ fontSize: 12, color: 'var(--red)', marginBottom: 12, padding: '8px 12px', background: 'var(--red-dim)', borderRadius: 6 }}>{error}</div>}
          <button className="btn btn-primary btn-lg btn-block" onClick={handleLogin} disabled={loading || !code.trim()}>
            {loading ? 'Checking...' : 'Access Granted'}
          </button>
          <div style={{ marginTop: 12, textAlign: 'center', fontSize: 13, color: 'var(--text-dim)' }}>
            No code? <button className="btn btn-ghost btn-sm" onClick={() => setMode('signup')}
              style={{ fontSize: 13, padding: '4px 8px', textDecoration: 'underline', background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer' }}>
              Sign up with invite
            </button>
          </div>
        </div>
      ) : (
        <div className="card" style={{ padding: 24 }}>
          <div className="form-group">
            <label>Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" autoFocus />
          </div>
          <div className="form-group">
            <label>Invite Code</label>
            <input type="text" value={invite} onChange={e => setInvite(e.target.value)} placeholder="Paste your invite code" />
          </div>
          {error && <div style={{ fontSize: 12, color: 'var(--red)', marginBottom: 12, padding: '8px 12px', background: 'var(--red-dim)', borderRadius: 6 }}>{error}</div>}
          <button className="btn btn-primary btn-lg btn-block" onClick={handleSignup} disabled={loading || !email || !invite}>
            {loading ? 'Signing up...' : 'Get Access Code'}
          </button>
          <div style={{ marginTop: 12, textAlign: 'center', fontSize: 13, color: 'var(--text-dim)' }}>
            Already have a code? <button className="btn btn-ghost btn-sm" onClick={() => setMode('login')}
              style={{ fontSize: 13, padding: '4px 8px', textDecoration: 'underline', background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer' }}>
              Log in
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
