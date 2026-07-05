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
    const el = btnRef.current
    if (el) {
      el.style.transform = 'scale(1.3)'
      el.style.opacity = '0.5'
      setTimeout(() => {
        setDark(!dark)
        setTimeout(() => {
          if (el) { el.style.transform = 'scale(1)'; el.style.opacity = '1' }
        }, 50)
      }, 100)
    } else {
      setDark(!dark)
    }
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
        transition: 'transform 0.15s, opacity 0.15s',
      }}
      title={dark ? 'Light mode' : 'Dark mode'}
    >
      {dark ? '☀' : '☾'}
    </button>
  )
}
