import { useCallback, useEffect, useState } from 'react'

export default function SettingsPage() {
  const [email, setEmail] = useState('')
  const [balance, setBalance] = useState(0)
  const [invites, setInvites] = useState<{ code: string; used: boolean }[]>([])
  const [wallets, setWallets] = useState<Record<string, string>>({})
  const [copiedWallet, setCopiedWallet] = useState('')
  const [usdPrice, setUsdPrice] = useState(5.0)
  const [solRate, setSolRate] = useState(0)
  const [buyAmount, setBuyAmount] = useState('')
  const [showAddress, setShowAddress] = useState(false)
  const [purchasesBlocked, setPurchasesBlocked] = useState(false)
  const [txHash, setTxHash] = useState('')
  const [paymentSent, setPaymentSent] = useState(false)
  const accessCode = (() => { try { return localStorage.getItem('sh-access-code') || '' } catch { return '' } })()

  const loadInvites = useCallback(async () => {
    if (!accessCode) return
    try { const r = await fetch(`/api/invites?code=${encodeURIComponent(accessCode)}`); const d = await r.json(); setInvites(d.invites || []) } catch {}
  }, [accessCode])

  useEffect(() => {
    if (!accessCode) return
    fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code: accessCode }) })
      .then(r => r.json()).then(d => { if (d.user) { setBalance(d.user.balance ?? 0); setEmail(d.user.email || '') } }).catch(() => {})
    fetch('/api/payment/wallet').then(r => r.json()).then(d => { setWallets(d || {}); setPurchasesBlocked(d.purchases_blocked || false) }).catch(() => {})
    fetch('/api/pricing').then(r => r.json()).then(d => { setUsdPrice(d.usd_per_credit || 5.0); setSolRate(d.sol_per_credit || 0.035) }).catch(() => {})
    loadInvites()
  }, [accessCode, loadInvites])

  const handleCopy = useCallback((coin: string, addr: string) => {
    navigator.clipboard.writeText(addr); setCopiedWallet(coin); setTimeout(() => setCopiedWallet(''), 2000)
  }, [])

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
          Share codes with friends. They get 2 credits on signup, you get 1 bonus credit.
        </p>
        {invites.length === 0 && <div style={{ fontSize: 12, color: 'var(--text-dim)', fontStyle: 'italic', marginBottom: 8 }}>No invite codes yet.</div>}
        {invites.filter(i => !i.used).map(inv => (
          <div key={inv.code} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, padding: '6px 10px', background: 'var(--surface-2)', borderRadius: 6 }}>
            <code style={{ flex: 1, fontSize: 12, fontFamily: 'monospace' }}>{inv.code}</code>
            <button className="btn btn-ghost btn-sm" onClick={() => navigator.clipboard.writeText(inv.code)}>Copy</button>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-title">Buy Credits</div>
        <div style={{ fontSize: 13, marginBottom: 8, lineHeight: 1.6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
            <span>1 credit</span>
            <span style={{ fontWeight: 600 }}>${usdPrice.toFixed(2)} USD</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0', fontSize: 12, color: 'var(--text-dim)' }}>
            <span>≈ {solRate ? (1 / solRate).toFixed(2) : '...'} USD worth of SOL</span>
          </div>
        </div>

        {purchasesBlocked ? (
          <div style={{ fontSize: 13, color: 'var(--text-dim)', fontStyle: 'italic', padding: '8px 0' }}>Purchases are temporarily disabled.</div>
        ) : !showAddress ? (
          <div>
            <p style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 8 }}>Enter USD amount. Minimum $10.</p>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ fontSize: 16, fontWeight: 600 }}>$</span>
              <input type="number" value={buyAmount} onChange={e => setBuyAmount(e.target.value)} placeholder="10.00" step={1} min={10} style={{ width: 120 }} />
              <span style={{ fontSize: 12, color: 'var(--text-dim)' }}>≈ {(parseFloat(buyAmount || '0') * solRate / usdPrice).toFixed(6)} SOL</span>
            </div>
            <button className="btn btn-primary btn-sm" style={{ marginTop: 8 }}
              onClick={() => setShowAddress(true)} disabled={!buyAmount || parseFloat(buyAmount) < 10}>
              Get receiving address — ${buyAmount || '0'}
            </button>
          </div>
        ) : (
          <div>
            <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 6, marginBottom: 8 }}>
              <div style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 4 }}>
                Send <strong>{(parseFloat(buyAmount) * solRate / usdPrice).toFixed(6)} SOL</strong> (${buyAmount}) for <strong>~{(parseFloat(buyAmount) / usdPrice).toFixed(0)} credits</strong>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
                <code style={{ flex: 1, fontSize: 11, fontFamily: 'monospace', wordBreak: 'break-all' }}>{wallets.sol || 'No address configured'}</code>
                {wallets.sol && <button className="btn btn-ghost btn-sm" onClick={() => handleCopy('sol', wallets.sol)}>{copiedWallet === 'sol' ? 'Copied!' : 'Copy'}</button>}
              </div>
            </div>
            <input type="text" value={txHash} onChange={e => setTxHash(e.target.value)} placeholder="Transaction signature (optional)" style={{ fontSize: 12, width: '100%', marginBottom: 6 }} />
            <button className="btn btn-primary btn-sm btn-block" onClick={async () => {
              const code = localStorage.getItem('sh-access-code') || ''
              await fetch(`/api/payment/request?code=${encodeURIComponent(code)}&amount_usd=${buyAmount}&tx_hash=${encodeURIComponent(txHash)}`, { method: 'POST' })
              setPaymentSent(true)
            }}>I have sent the payment</button>
            {paymentSent && <p style={{ fontSize: 12, color: 'var(--green)', marginTop: 6 }}>Reported. Admin will credit you after verification.</p>}
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 4 }} onClick={() => { setShowAddress(false); setBuyAmount(''); setTxHash(''); setPaymentSent(false) }}>Cancel</button>
          </div>
        )}
      </div>
    </div>
  )
}
