import { useCallback, useEffect, useState } from 'react'

function adminFetch(path: string, token: string, init?: RequestInit) {
  const sep = path.includes('?') ? '&' : '?'
  return fetch(`/api${path}${sep}token=${encodeURIComponent(token)}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  }).then(r => {
    if (!r.ok) throw new Error(`Request failed: ${r.status}`)
    return r.json()
  })
}

export default function AdminPage() {
  const [token, setToken] = useState(() => {
    try { return localStorage.getItem('sh-admin-token') || '' } catch { return '' }
  })
  const [tokenInput, setTokenInput] = useState('')
  const [tokenError, setTokenError] = useState('')
  const [tab, setTab] = useState<'users' | 'credits' | 'settings'>('users')
  const [users, setUsers] = useState<any[]>([])
  const [recvWallet, setRecvWallet] = useState('')
  const [solWallet, setSolWallet] = useState('')
  const [ltcWallet, setLtcWallet] = useState('')
  const [xmrWallet, setXmrWallet] = useState('')
  const [usdPerCredit, setUsdPerCredit] = useState(5.0)
  const [creditWallet, setCreditWallet] = useState('')
  const [creditAmount, setCreditAmount] = useState(5)
  const [creditMsg, setCreditMsg] = useState('')

  const loadUsers = useCallback(async () => {
    if (!token) return
    try { const d = await adminFetch('/admin/users', token); setUsers(d.users || []) } catch {}
  }, [token])

  useEffect(() => { if (token) loadUsers() }, [token, loadUsers])

  const loadSettings = useCallback(async () => {
    if (!token) return
    try {
      const d = await adminFetch('/admin/settings', token)
      const s = d.settings || {}
      setRecvWallet(s.receiving_wallet || '')
      setSolWallet(s.sol_wallet || s.receiving_wallet || '')
      setLtcWallet(s.ltc_wallet || '')
      setXmrWallet(s.xmr_wallet || '')
      setUsdPerCredit(s.usd_per_credit || 5.0)
    } catch {}
  }, [token])

  useEffect(() => { if (token) loadSettings() }, [token, loadSettings])

  const handleLogin = useCallback(async () => {
    try {
      await adminFetch('/admin/login', tokenInput.trim())
      setToken(tokenInput.trim())
      localStorage.setItem('sh-admin-token', tokenInput.trim())
      setTokenError('')
    } catch { setTokenError('Invalid admin token') }
  }, [tokenInput])

  const handleAddCredits = useCallback(async () => {
    if (!creditWallet || creditAmount <= 0 || !token) return
    setCreditMsg('')
    try {
      const d = await adminFetch(`/admin/credits?username=${encodeURIComponent(creditWallet)}&amount=${creditAmount}`, token, { method: 'POST' })
      setCreditMsg(`Added ${creditAmount} credits — Balance: ${d.user?.balance}`)
      setCreditWallet('')
      loadUsers()
    } catch (e: any) { setCreditMsg(`Error: ${e.message}`) }
  }, [creditWallet, creditAmount, token, loadUsers])

  const handleLogout = () => {
    localStorage.removeItem('sh-admin-token')
    setToken('')
    setTokenInput('')
  }

  if (!token) {
    return (
      <div className="card" style={{ maxWidth: 400, margin: '40px auto' }}>
        <div className="card-title">Admin Access</div>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 12 }}>
          Enter the admin token from the server console.
        </p>
        <div className="form-group">
          <input type="text" value={tokenInput} onChange={e => setTokenInput(e.target.value)}
            placeholder="Paste admin token" autoFocus
            onKeyDown={e => { if (e.key === 'Enter') handleLogin() }} />
        </div>
        {tokenError && <div style={{ fontSize: 12, color: 'var(--red)', marginBottom: 8 }}>{tokenError}</div>}
        <button className="btn btn-primary btn-block" onClick={handleLogin}>Access Admin</button>
      </div>
    )
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={{ display: 'flex', gap: 4, background: 'var(--surface)', borderRadius: 'var(--radius)', padding: 4 }}>
          {(['users', 'credits', 'settings'] as const).map(t => (
            <button key={t} className={`btn btn-sm${tab === t ? ' btn-primary' : ' btn-ghost'}`}
              onClick={() => setTab(t)} style={{ flex: 1 }}>
              {t === 'users' ? 'Users' : t === 'credits' ? 'Credits' : 'Settings'}
            </button>
          ))}
        </div>
        <button className="btn btn-ghost btn-sm" onClick={handleLogout}>Sign Out</button>
      </div>

      {tab === 'users' && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-dim)', marginBottom: 12, textTransform: 'uppercase' }}>
            Users ({users.length})
          </div>
          {users.map(u => (
            <div key={u.username} className="history-item">
              <div className="info">
                <div className="name">@{u.username}</div>
                <div className="meta">{u.balance} credits · {u.created?.slice(0, 10)}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === 'credits' && (
        <div className="card">
          <div className="card-title">Add Credits</div>
          <div className="form-group">
            <label>Username</label>
            <input type="text" value={creditWallet} onChange={e => setCreditWallet(e.target.value)} placeholder="Username (e.g. happy-tiger-42)" />
          </div>
          <div className="form-group">
            <label>Amount</label>
            <input type="number" value={creditAmount} onChange={e => setCreditAmount(parseInt(e.target.value) || 0)} min={1} max={1000} style={{ width: 100 }} />
          </div>
          <button className="btn btn-primary" onClick={handleAddCredits}>Add Credits</button>
          {creditMsg && <div style={{ marginTop: 12, padding: '8px 12px', background: creditMsg.startsWith('Error') ? 'var(--red-dim)' : 'var(--green-dim)', borderRadius: 6, fontSize: 13 }}>{creditMsg}</div>}
        </div>
      )}

      {tab === 'settings' && (
        <div className="card">
          <div className="card-title">Settings</div>
          <div className="form-group">
            <label>SOL Wallet</label>
            <input type="text" value={solWallet} onChange={e => setSolWallet(e.target.value)} placeholder="Solana address" />
          </div>
          <div className="form-group">
            <label>LTC Wallet</label>
            <input type="text" value={ltcWallet} onChange={e => setLtcWallet(e.target.value)} placeholder="Litecoin address (optional)" />
          </div>
          <div className="form-group">
            <label>XMR Wallet</label>
            <input type="text" value={xmrWallet} onChange={e => setXmrWallet(e.target.value)} placeholder="Monero address (optional)" />
          </div>
          <div className="form-group">
            <label>Price per Generation (USD)</label>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 16, fontWeight: 600 }}>$</span>
              <input type="number" value={usdPerCredit} onChange={e => setUsdPerCredit(parseFloat(e.target.value) || 5.0)}
                step={1} min={1} max={1000} style={{ width: 100 }} />
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
              Converts to SOL/LTC/XMR at current market rates.
            </div>
          </div>
          <button className="btn btn-primary" onClick={async () => {
            try {
              await adminFetch(`/admin/settings?sol_wallet=${encodeURIComponent(solWallet)}&ltc_wallet=${encodeURIComponent(ltcWallet)}&xmr_wallet=${encodeURIComponent(xmrWallet)}&receiving_wallet=${encodeURIComponent(recvWallet)}&usd_per_credit=${usdPerCredit}`, token, { method: 'POST' })
            } catch {}
          }}>Save</button>
        </div>
      )}
    </div>
  )
}
