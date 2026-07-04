import { useCallback, useEffect, useState } from 'react'

export default function WalletStatus() {
  const [balance, setBalance] = useState(0)

  const loadBalance = useCallback(async () => {
    const name = (() => { try { return localStorage.getItem('sh-user') } catch { return null } })()
    if (!name) return
    try {
      const r = await fetch(`/api/user/${encodeURIComponent(name)}`)
      const data = await r.json()
      setBalance(data.user?.balance ?? 0)
    } catch {}
  }, [])

  useEffect(() => { loadBalance() }, [loadBalance])

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5,
      background: 'var(--surface-2)', borderRadius: 6, padding: '3px 10px',
      fontSize: 11, fontWeight: 600, cursor: 'default'
    }} onClick={loadBalance} title="Click to refresh">
      <div style={{
        width: 5, height: 5, borderRadius: '50%',
        background: balance > 0 ? 'var(--green)' : 'var(--yellow)',
      }} />
      {balance} credits
    </div>
  )
}
