import { useEffect, useRef, useState } from 'react'

export default function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    const saved = (() => { try { return localStorage.getItem('sh-theme') } catch { return null } })()
    if (saved) return saved === 'dark'
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
  })
  const btnRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    try { localStorage.setItem('sh-theme', dark ? 'dark' : 'light') } catch {}
  }, [dark])

  const handleClick = () => {
    const btn = btnRef.current
    if (!btn) { setDark(!dark); return }

    // Subtle zoom + pop on the button itself
    btn.style.transform = 'scale(1.25)'
    btn.style.transition = 'transform 0.2s ease'

    setTimeout(() => {
      setDark(!dark)
      btn.style.transform = 'scale(1)'
    }, 120)
  }

  return (
    <button
      ref={btnRef}
      onClick={handleClick}
      style={{
        width: 28, height: 28, borderRadius: 6, border: '1px solid var(--border)',
        background: 'var(--surface-2)', cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 13, color: 'var(--text-dim)',
      }}
      title={dark ? 'Light mode' : 'Dark mode'}
    >
      {dark ? '☀' : '☾'}
    </button>
  )
}
