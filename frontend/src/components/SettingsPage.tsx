import { useCallback, useEffect, useState } from 'react'

export default function SettingsPage() {
  const [email, setEmail] = useState('')
  const [balance, setBalance] = useState(0)
  const [invites, setInvites] = useState<{ code: string; used: boolean }[]>([])
  const [wallets, setWallets] = useState<Record<string, string>>({})
  const [copiedWallet, setCopiedWallet] = useState('')
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [usdPrice, setUsdPrice] = useState(5.0)
  const [solRate, setSolRate] = useState(0)
  const [buyAmount, setBuyAmount] = useState('')
  const [showAddress, setShowAddress] = useState(false)
  const accessCode = (() => { try { return localStorage.getItem('sh-access-code') || '' } catch { return '' } })()

  const loadInvites = useCallback(async () => {
    if (!accessCode) return
    try {
      const r = await fetch(`/api/invites?code=${encodeURIComponent(accessCode)}`)
      const d = await r.json()
      setInvites(d.invites || [])
    } catch {}
  }, [accessCode])

  useEffect(() => {
    if (!accessCode) return
    fetch('/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: accessCode }),
    }).then(r => r.json()).then(d => {
      if (d.user) { setBalance(d.user.balance ?? 0); setEmail(d.user.email || '') }
    }).catch(() => {})
    fetch('/api/payment/wallet').then(r => r.json()).then(d => setWallets(d || {})).catch(() => {})
    fetch('/api/pricing').then(r => r.json()).then(d => {
      setUsdPrice(d.usd_per_credit || 5.0)
      setSolRate(d.sol_per_credit || 0.035)
      setPrices({ sol: d.sol_per_credit || 0.035, ltc: d.ltc_per_credit || 0.07, xmr: d.xmr_per_credit || 0.032 })
    }).catch(() => {})
    loadInvites()
  }, [accessCode, loadInvites])

  const handleCopy = useCallback((coin: string, addr: string) => {
    navigator.clipboard.writeText(addr); setCopiedWallet(coin); setTimeout(() => setCopiedWallet(''), 2000)
  }, [])

  const handleGenerateInvites = useCallback(async () => {
    if (!accessCode) return
    try {
      const r = await fetch(`/api/invites/generate?code=${encodeURIComponent(accessCode)}`, { method: 'POST' })
      const d = await r.json()
      setInvites(d.invites || [])
    } catch {}
  }, [accessCode])

  return (
    <div>
      <div className="card">
        <div className="card-title">Profile</div>
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{email || 'Signed in'}</div>
        <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>{balance} credits</div>
      </div>

      <div className="card">
        <div className="card-title">Invite Friends</div>
        <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 8 }}>
          Share invite codes with friends. They get 10 credits on signup, you get 1 bonus credit.
        </p>
        {invites.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-dim)', fontStyle: 'italic', marginBottom: 8 }}>No invite codes yet.</div>}
        <div style={{ marginBottom: 8 }}>
          {invites.filter(i => !i.used).map(inv => (
            <div key={inv.code} style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4,
              padding: '6px 10px', background: 'var(--surface-2)', borderRadius: 6,
            }}>
              <code style={{ flex: 1, fontSize: 12, fontFamily: 'monospace' }}>{inv.code}</code>
              <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard.writeText(inv.code)}>Copy</button>
            </div>
          ))}
        </div>
        <button className="btn btn-ghost btn-sm" onClick={handleGenerateInvites}>Generate 3 more invites</button>
        {invites.filter(i => i.used).length > 0 && (
          <details style={{ marginTop: 8, fontSize: 11, color: 'var(--text-dim)' }}>
            <summary>{invites.filter(i => i.used).length} used</summary>
            {invites.filter(i => i.used).map(inv => (
              <div key={inv.code} style={{ padding: '2px 0', fontFamily: 'monospace' }}>{inv.code}</div>
            ))}
          </details>
        )}
      </div>

      {/* Buy Credits — Solana only, enter amount first */}
      <div className="card">
        <div className="card-title">Buy Credits</div>
        <div style={{ fontSize: 13, marginBottom: 8, lineHeight: 1.6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
            <span>1 credit</span>
            <span style={{ fontWeight: 600 }}>{solRate} SOL</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
            <span>~$1 USD</span>
            <span style={{ fontWeight: 600 }}>{(solRate * (1 / usdPrice)).toFixed(6)} SOL</span>
          </div>
        </div>

        {!showAddress ? (
          <div>
            <p style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 8 }}>
              Enter the amount of SOL you want to send to see the receiving address.
            </p>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input type="number" value={buyAmount} onChange={e => setBuyAmount(e.target.value)}
                placeholder="0.00" step={0.001} min={0} style={{ width: 120 }} />
              <span style={{ fontSize: 13, fontWeight: 600 }}>SOL</span>
              <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                ≈ {buyAmount && solRate ? (parseFloat(buyAmount) / solRate).toFixed(0) : 0} credits
              </span>
            </div>
            <button className="btn btn-primary btn-sm" style={{ marginTop: 8 }}
              onClick={() => setShowAddress(true)} disabled={!buyAmount || parseFloat(buyAmount) <= 0}>
              Get receiving address
            </button>
          </div>
        ) : (
          <div>
            <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 6, marginBottom: 8 }}>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 4 }}>
                Send exactly <strong>{buyAmount} SOL</strong> to receive ~<strong>{(parseFloat(buyAmount || '0') / solRate).toFixed(0)} credits</strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                <code style={{ flex: 1, fontSize: 11, fontFamily: 'monospace', wordBreak: 'break-all' }}>
                  {wallets.sol || 'No address configured'}
                </code>
                {wallets.sol && (
                  <button className="btn btn-ghost btn-sm" onClick={() => handleCopy('sol', wallets.sol)}>
                    {copiedWallet === 'sol' ? 'Copied!' : 'Copy'}
                  </button>
                )}
              </div>
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-dim)' }}>
              After sending, contact support with your access code and transaction hash. Credits are added manually.
            </p>
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 4 }} onClick={() => { setShowAddress(false); setBuyAmount('') }}>
              Cancel
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
