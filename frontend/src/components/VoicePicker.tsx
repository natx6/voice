import { useMemo, useState, useRef, useEffect } from 'react'
import type { VoiceInfo } from '../types'

interface VoicePickerProps {
  voices: VoiceInfo[]
  selected: string
  onChange: (id: string) => void
}

type Gender = 'all' | 'male' | 'female'

export default function VoicePicker({ voices, selected, onChange }: VoicePickerProps) {
  const [gender, setGender] = useState<Gender>('all')
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close on click outside
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const getGender = (v: VoiceInfo | undefined): Gender => {
    if (!v) return 'all'
    const labels = v.labels ?? {}
    const labelGender = (labels.gender || '').toLowerCase()
    if (labelGender === 'male' || labelGender === 'female') return labelGender as Gender
    const name = v.name.toLowerCase()
    const fw = ['female','woman','sarah','emma','bella','rachel','jessica','olivia','alice','matilda','laura','lily','clara','anika','eryn','hope','hannah','sophie','mia','ella','grace','luna','zoe','aria','victoria','naomi','jasmine','maya','audrey','hazel','abigail','eleanor','stella','violet','samantha','kylie','morgan','brianna','ashley','jennifer','michelle','amanda','melissa','nicole','lauren','rebecca','heather','megan','erica','faith','serena','iris','rose','daisy','holly','jade','jules','quinn','harper','reese','blake']
    const mw = ['male','man','boy','josh','adam','arnold','patrick','sam','daniel','james','michael','david','thomas','chris','roger','charlie','george','callum','harry','liam','will','eric','brian','bill','henry','jack','oliver','noah','ethan','owen','luke','logan','carter','gabriel','julian','isaac','joseph','caleb','ryan','nathan','jacob','andrew','aiden','mason','matthew','elijah','aaron','sebastian','nicholas','connor','ian','alex','alexander','brandon','kevin','jason','tyler','kyle','dylan','cameron','evan','jordan','jake','marcus','steve','peter','paul','mark','john','robert','richard','william','edward','frank','samuel','tom','harrison']
    for (const w of fw) { if (name.includes(w)) return 'female' }
    for (const w of mw) { if (name.includes(w)) return 'male' }
    return 'all'
  }

  const filtered = useMemo(() => {
    const valid = voices.filter((v): v is VoiceInfo => v != null)
    if (gender === 'all') return valid
    return valid.filter(v => getGender(v) === gender)
  }, [voices, gender])

  const selectedVoice = voices.find(v => v && v.voice_id === selected)

  const colors = {
    bg: 'var(--surface)',
    bgHover: 'var(--surface-2)',
    border: 'var(--border)',
    borderLight: 'var(--border-light)',
    text: 'var(--text)',
    textDim: 'var(--text-dim)',
    accent: 'var(--accent)',
    pink: '#e84393',
    blue: '#0984e3',
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <label style={{ marginBottom: 6 }}>Voice</label>

      {/* Trigger */}
      <div
        onClick={() => { if (voices.length > 0) setOpen(!open) }}
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '10px 14px', cursor: 'pointer', userSelect: 'none',
          background: colors.bg,
          border: `1px solid ${open ? colors.accent : colors.border}`,
          borderRadius: 10,
          transition: 'border-color 0.15s',
        }}
      >
        {/* Avatar */}
        <div style={{
          width: 30, height: 30, borderRadius: 8, flexShrink: 0,
          background: selectedVoice
            ? getGender(selectedVoice) === 'female' ? colors.pink : colors.blue
            : colors.border,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 13, fontWeight: 700, color: 'white',
        }}>
          {selectedVoice ? selectedVoice.name.charAt(0).toUpperCase() : '?'}
        </div>

        {/* Name + accent */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 14, fontWeight: 600,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            color: selectedVoice ? colors.text : colors.textDim,
          }}>
            {selectedVoice ? selectedVoice.name : 'Select a voice'}
          </div>
          {selectedVoice?.labels?.accent && (
            <div style={{ fontSize: 11, color: colors.textDim, marginTop: 1 }}>
              {selectedVoice.labels.accent} · {voices.length} voices
            </div>
          )}
          {!selectedVoice && voices.length > 0 && (
            <div style={{ fontSize: 11, color: colors.textDim, marginTop: 1 }}>
              {voices.length} voices available
            </div>
          )}
        </div>

        {/* Gender tag + arrow */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {selectedVoice && getGender(selectedVoice) !== 'all' && (
            <span style={{
              fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
              padding: '2px 6px', borderRadius: 4,
              color: getGender(selectedVoice) === 'female' ? colors.pink : colors.blue,
              background: getGender(selectedVoice) === 'female' ? `${colors.pink}18` : `${colors.blue}18`,
            }}>
              {getGender(selectedVoice)}
            </span>
          )}
          <svg width="12" height="12" viewBox="0 0 12 12" style={{
            transform: open ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.2s', opacity: 0.5,
          }}>
            <path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
      </div>

      {/* Dropdown */}
      {open && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
          marginTop: 4,
          background: colors.bg,
          border: `1px solid ${colors.borderLight}`,
          borderRadius: 10,
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          overflow: 'hidden',
          display: 'flex', flexDirection: 'column',
          maxHeight: 380,
        }}>
          {/* Gender filter */}
          <div style={{
            display: 'flex', gap: 4, padding: '10px 10px 6px',
            borderBottom: '1px solid var(--border)',
          }}>
            {(['all', 'female', 'male'] as Gender[]).map(g => (
              <button
                key={g}
                onClick={() => setGender(g)}
                style={{
                  flex: 1, padding: '6px 0', border: 'none', borderRadius: 6,
                  fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  background: gender === g
                    ? g === 'female' ? colors.pink : g === 'male' ? colors.blue : colors.accent
                    : colors.bgHover,
                  color: gender === g ? 'white' : colors.textDim,
                  transition: 'all 0.1s',
                }}
              >
                {g === 'all' ? 'All' : g === 'female' ? 'Female' : 'Male'}
              </button>
            ))}
          </div>

          {/* Voice list */}
          <div style={{ overflowY: 'auto', flex: 1, padding: '4px 0' }}>
            {filtered.map(v => {
              const g = getGender(v)
              const isSel = v.voice_id === selected
              return (
                <div
                  key={v.voice_id}
                  onClick={() => { onChange(v.voice_id); setOpen(false) }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 12px', cursor: 'pointer', userSelect: 'none',
                    background: isSel ? `${colors.accent}12` : 'transparent',
                    borderLeft: `3px solid ${isSel ? colors.accent : 'transparent'}`,
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => { if (!isSel) e.currentTarget.style.background = colors.bgHover }}
                  onMouseLeave={e => { if (!isSel) e.currentTarget.style.background = 'transparent' }}
                >
                  {/* Gender dot */}
                  <div style={{
                    width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                    background: g === 'female' ? colors.pink : g === 'male' ? colors.blue : colors.border,
                  }} />

                  {/* Name + accent */}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: colors.text }}>
                      {v.name}
                    </div>
                    {v.labels?.accent && (
                      <div style={{ fontSize: 11, color: colors.textDim, marginTop: 1 }}>
                        {v.labels.accent}
                      </div>
                    )}
                  </div>

                  {/* Checkmark */}
                  {isSel && (
                    <svg width="16" height="16" viewBox="0 0 16 16" style={{ flexShrink: 0 }}>
                      <path d="M3 8l3 3 7-7" fill="none" stroke={colors.accent} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                </div>
              )
            })}
            {filtered.length === 0 && (
              <div style={{ padding: 24, textAlign: 'center', color: colors.textDim, fontSize: 13 }}>
                {voices.length === 0 ? 'No voices loaded' : 'No voices match this filter'}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
