import { useCallback, useEffect, useState } from 'react'

export default function SettingsPage() {
  const [username, setUsername] = useState('')
  const [balance, setBalance] = useState(0)
  const [invites, setInvites] = useState<{ code: string; status: string }[]>([])
  const [wallets, setWallets] = useState<Record<string, string>>({})
  const [copiedWallet, setCopiedWallet] = useState('')
  const [solPrice, setSolPrice] = useState(0.005)
  const [usdcPrice, setUsdcPrice] = useState(0.50)

  useEffect(() => {
    const name = (() => { try { return localStorage.getItem('sh-user') || '' } catch { return '' } })()
    setUsername(name)
    if (!name) return
    fetch(`/api/user/${encodeURIComponent(name)}`)
      .then(r => r.json())
      .then(d => {
        if (d.user) {
          setBalance(d.user.balance ?? 0)
          setInvites(d.user.invite_codes || [])
        }
      })
      .catch(() => {})
    fetch('/api/payment/wallet')
      .then(r => r.json())
      .then(d => setWallets(d || {}))
      .catch(() => {})
    fetch('/api/pricing')
      .then(r => r.json())
      .then(d => {
        setSolPrice(d.sol_per_credit || 0.005)
        setUsdcPrice(d.usdc_per_credit || 0.50)
      })
      .catch(() => {})
  }, [])

  const handleCopy = useCallback((coin: string, addr: string) => {
    navigator.clipboard.writeText(addr)
    setCopiedWallet(coin)
    setTimeout(() => setCopiedWallet(''), 2000)
  }, [])

  return (
    <div>
      {/* Profile */}
      <div className="card">
        <div className="card-title">Profile</div>
        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>@{username}</div>
        <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
          {balance} credits · {invites.filter(i => i.status === 'available').length} invite codes available
        </div>
      </div>

      {/* Buy Credits */}
      <div className="card">
        <div className="card-title">Buy Credits</div>
        <div style={{ fontSize: 13, marginBottom: 12, lineHeight: 1.6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
            <span>1 credit</span><span style={{ fontWeight: 600 }}>{solPrice} SOL</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
            <span>10 credits</span><span style={{ fontWeight: 600 }}>{(solPrice * 10).toFixed(4)} SOL</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
            <span>100 credits</span><span style={{ fontWeight: 600 }}>{(solPrice * 100).toFixed(4)} SOL</span>
          </div>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 8 }}>
          1. Send to any address below
        </p>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 12 }}>
          2. Contact support with your username — credits added manually
        </p>
        {(() => {
          const coins = ['sol', 'ltc', 'xmr'].filter(c => wallets[c])
          if (coins.length === 0) return <div style={{ fontSize: 12, color: 'var(--text-dim)', fontStyle: 'italic' }}>No wallets configured yet.</div>
          return coins.map(coin => (
            <div key={coin} style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
              padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 6,
            }}>
              <span style={{ fontSize: 11, fontWeight: 700, minWidth: 30, textTransform: 'uppercase', color: 'var(--text-dim)' }}>
                {coin}
              </span>
              <code style={{ flex: 1, fontSize: 11, fontFamily: 'monospace', wordBreak: 'break-all', opacity: 0.8 }}>{wallets[coin]}</code>
              <button className="btn btn-ghost btn-sm" onClick={() => handleCopy(coin, wallets[coin])}>
                {copiedWallet === coin ? 'Copied!' : 'Copy'}
              </button>
            </div>
          ))
        })()}
      </div>

      {/* Invite Codes */}
      <div className="card">
        <div className="card-title">Invite Codes</div>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 10 }}>
          Share these with friends. They get 2 free credits, you get 1 bonus credit when they join.
        </p>
        {invites.filter(i => i.status === 'available').length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--text-dim)', fontStyle: 'italic' }}>No invite codes available</div>
        ) : (
          invites.filter(i => i.status === 'available').map(inv => (
            <div key={inv.code} style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6,
              padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 6,
            }}>
              <code style={{ flex: 1, fontSize: 12, fontFamily: 'monospace' }}>{inv.code}</code>
              <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard.writeText(inv.code)}>
                Copy
              </button>
            </div>
          ))
        )}
        {invites.filter(i => i.status === 'used').length > 0 && (
          <details style={{ marginTop: 8, fontSize: 12, color: 'var(--text-dim)' }}>
            <summary>{invites.filter(i => i.status === 'used').length} used</summary>
            {invites.filter(i => i.status === 'used').map(inv => (
              <div key={inv.code} style={{ padding: '4px 0', fontFamily: 'monospace' }}>{inv.code} — used</div>
            ))}
          </details>
        )}
      </div>
    </div>
  )
}
