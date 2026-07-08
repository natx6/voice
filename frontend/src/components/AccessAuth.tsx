import { useState, useCallback } from 'react'

interface Props {
  onAuth: (code: string) => void
}

export default function AccessAuth({ onAuth }: Props) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

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

  return (
    <div style={{ maxWidth: 400, margin: '80px auto', padding: '0 16px', textAlign: 'center' }}>
      <div style={{
        width: 52, height: 52, borderRadius: 14,
        background: 'linear-gradient(135deg, #0066cc, #409cff)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 24, fontWeight: 700, color: 'white', margin: '0 auto 16px',
      }}>sh</div>
      <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 4, letterSpacing: '-0.5px' }}>soundhuman</h1>
      <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 24 }}>Enter your access code</p>

      <div className="card" style={{ padding: 24, textAlign: 'left' }}>
        <input type="text" value={code} onChange={e => setCode(e.target.value)}
          placeholder="Paste your access code" autoFocus
          onKeyDown={e => { if (e.key === 'Enter') handleLogin() }}
          style={{ marginBottom: 12 }} />
        {error && <div style={{ fontSize: 12, color: 'var(--red)', marginBottom: 12 }}>{error}</div>}
        <button className="btn btn-primary btn-lg btn-block" onClick={handleLogin} disabled={loading || !code.trim()}>
          {loading ? 'Signing in...' : 'Continue'}
        </button>
      </div>
    </div>
  )
}
