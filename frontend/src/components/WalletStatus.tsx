import { useCallback, useEffect, useState } from 'react'
import * as api from '../api'

interface WalletStatusProps {
  /** Trigger payment/connect flow */
  onConnect?: () => void
}

export default function WalletStatus({ onConnect }: WalletStatusProps) {
  const [wallet, setWallet] = useState<string | null>(null)
  const [balance, setBalance] = useState(0)
  const [connecting, setConnecting] = useState(false)

  // Generate a simple wallet ID from localStorage (real WalletConnect later)
  const storedWallet = (() => {
    try { return localStorage.getItem('sh-wallet') } catch { return null }
  })()

  useEffect(() => {
    if (storedWallet) {
      setWallet(storedWallet)
      api.fetchJson(`/credits/balance?wallet=${encodeURIComponent(storedWallet)}`)
        .then((data: any) => setBalance(data.balance ?? 0))
        .catch(() => {})
    }
  }, [storedWallet])

  const handleConnect = useCallback(async () => {
    setConnecting(true)
    try {
      // Simplified: generate a wallet ID for demo
      // Real WalletConnect integration replaces this
      const demoWallet = `demo_${Math.random().toString(36).slice(2, 10)}`
      localStorage.setItem('sh-wallet', demoWallet)

      // Give 5 free credits on first connect
      await api.fetchJson(`/credits/add?wallet=${demoWallet}&amount=5&token=manual`, { method: 'POST' })
        .catch(() => {})

      setWallet(demoWallet)
      setBalance(5)
      if (onConnect) onConnect()
    } catch (e: any) {
      console.error('Connect failed:', e)
    } finally {
      setConnecting(false)
    }
  }, [onConnect])

  const handleDisconnect = () => {
    localStorage.removeItem('sh-wallet')
    setWallet(null)
    setBalance(0)
  }

  const refreshBalance = useCallback(async () => {
    if (!wallet) return
    try {
      const data: any = await api.fetchJson(`/credits/balance?wallet=${encodeURIComponent(wallet)}`)
      setBalance(data.balance ?? 0)
    } catch {}
  }, [wallet])

  if (!wallet) {
    return (
      <button className="btn btn-ghost btn-sm" onClick={handleConnect} disabled={connecting}
        style={{ fontSize: 12, padding: '6px 14px' }}>
        {connecting ? 'Connecting...' : 'Connect Wallet'}
      </button>
    )
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6,
        background: 'var(--surface-2)', borderRadius: 'var(--radius-xs)',
        padding: '4px 10px', fontSize: 12, fontWeight: 600, cursor: 'pointer',
      }} onClick={refreshBalance} title="Click to refresh">
        <div style={{
          width: 6, height: 6, borderRadius: '50%',
          background: balance > 0 ? 'var(--green)' : 'var(--yellow)',
        }} />
        {balance} credits
      </div>
      <button className="btn btn-ghost btn-sm" onClick={handleDisconnect}
        style={{ fontSize: 11, padding: '3px 8px' }}>
        {wallet.slice(0, 6)}
      </button>
    </div>
  )
}
