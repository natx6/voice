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

    const rect = btn.getBoundingClientRect()
    const cx = rect.left + rect.width / 2
    const cy = rect.top + rect.height / 2
    const maxRadius = Math.hypot(
      Math.max(cx, window.innerWidth - cx),
      Math.max(cy, window.innerHeight - cy)
    )

    // Create the circle overlay
    const overlay = document.createElement('div')
    overlay.style.cssText = `
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      z-index: 9999; pointer-events: none;
      clip-path: circle(0px at ${cx}px ${cy}px);
      transition: clip-path 0.4s ease;
      background: ${dark ? '#f5f5f7' : '#1c1c1e'};
    `
    document.body.appendChild(overlay)

    // Force reflow then expand
    requestAnimationFrame(() => {
      overlay.style.clipPath = `circle(${maxRadius}px at ${cx}px ${cy}px)`
    })

    // Switch theme mid-animation
    setTimeout(() => {
      setDark(!dark)
    }, 200)

    // Clean up overlay after animation
    setTimeout(() => {
      overlay.remove()
    }, 500)
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
        transition: 'transform 0.15s',
      }}
      title={dark ? 'Light mode' : 'Dark mode'}
    >
      {dark ? '☀' : '☾'}
    </button>
  )
}
