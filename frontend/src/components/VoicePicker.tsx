import { useMemo, useState } from 'react'
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

  const getGender = (v: VoiceInfo | undefined): Gender => {
    if (!v) return 'all'
    const labels = v.labels ?? {}
    const labelGender = (labels.gender || '').toLowerCase()
    if (labelGender === 'male' || labelGender === 'female') return labelGender as Gender
    const name = v.name.toLowerCase()
    const femaleWords = ['female', 'woman', 'girl', 'sarah', 'emma', 'bella', 'rachel', 'jessica',
      'olivia', 'alice', 'matilda', 'laura', 'lily', 'clara', 'anika', 'eryn', 'hope', 'hannah',
      'sophie', 'chloe', 'mia', 'ella', 'grace', 'luna', 'layla', 'riley', 'zoe', 'aria', 'victoria',
      'scarlett', 'penelope', 'mila', 'avery', 'camila', 'naomi', 'jasmine', 'maya', 'audrey',
      'brooklyn', 'hazel', 'abigail', 'eleanor', 'stella', 'violet', 'aubrey', 'addison',
      'samantha', 'kylie', 'morgan', 'brianna', 'alexis', 'mackenzie', 'ashley', 'jennifer',
      'michelle', 'amanda', 'melissa', 'stephanie', 'nicole', 'danielle', 'catherine', 'lauren',
      'rebecca', 'heather', 'megan', 'erica', 'faith', 'serena', 'iris', 'rose', 'daisy',
      'holly', 'jade', 'jules', 'quinn', 'harper', 'reese', 'blake']
    const maleWords = ['male', 'man', 'boy', 'guy', 'josh', 'adam', 'arnold', 'antoni', 'patrick',
      'sam', 'daniel', 'james', 'michael', 'david', 'thomas', 'chris', 'roger', 'charlie',
      'george', 'callum', 'harry', 'liam', 'will', 'eric', 'brian', 'bill', 'henry', 'jack',
      'oliver', 'noah', 'ethan', 'levi', 'owen', 'luke', 'logan', 'carter', 'jayden', 'gabriel',
      'julian', 'isaac', 'joseph', 'caleb', 'ryan', 'nathan', 'jacob', 'andrew', 'aiden',
      'mason', 'matthew', 'elijah', 'aaron', 'sebastian', 'nicholas', 'connor', 'ian', 'alex',
      'alexander', 'brandon', 'zachary', 'kevin', 'jason', 'justin', 'tyler', 'kyle', 'dylan',
      'cameron', 'evan', 'jordan', 'jake', 'marcus', 'steve', 'peter', 'paul', 'mark', 'john',
      'robert', 'richard', 'william', 'edward', 'frank', 'samuel', 'tom', 'harrison']
    for (const w of femaleWords) { if (name.includes(w)) return 'female' }
    for (const w of maleWords) { if (name.includes(w)) return 'male' }
    return 'all'
  }

  const filtered = useMemo(() => {
    const valid = voices.filter(Boolean)
    if (gender === 'all') return valid
    return valid.filter(v => getGender(v) === gender)
  }, [voices, gender])

  const selectedVoice = voices.find(v => v && v.voice_id === selected)

  return (
    <div>
      {/* Voice selector button */}
      <label style={{ marginBottom: 8 }}>Voice</label>
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '10px 14px',
          background: 'var(--surface-2)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
          transition: 'border-color 0.15s',
        }}
        className="voice-selector-trigger"
      >
        <div style={{
          width: 28, height: 28, borderRadius: 8,
          background: selectedVoice
            ? getGender(selectedVoice) === 'female' ? 'var(--pink)' : '#0984e3'
            : 'var(--border)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 12, fontWeight: 700, color: 'white', flexShrink: 0,
        }}>
          {selectedVoice ? selectedVoice.name.charAt(0).toUpperCase() : '?'}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {selectedVoice ? selectedVoice.name : 'Select a voice'}
          </div>
          {selectedVoice?.labels?.accent && (
            <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 1 }}>
              {selectedVoice.labels.accent}
            </div>
          )}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-dim)', textAlign: 'right' }}>
          {selectedVoice && getGender(selectedVoice) !== 'all' ? getGender(selectedVoice) : ''}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-dim)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}>
          ▼
        </div>
      </div>

      {/* Dropdown */}
      {open && (
        <div style={{
          marginTop: 4,
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          maxHeight: 320,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}>
          {/* Gender filter */}
          <div style={{ display: 'flex', gap: 4, padding: '8px 8px 4px', borderBottom: '1px solid var(--border)' }}>
            {(['all', 'female', 'male'] as Gender[]).map(g => (
              <button
                key={g}
                className={`gender-btn${gender === g ? ' active' : ''}`}
                style={gender === g ? {
                  background: g === 'female' ? 'var(--pink)' : g === 'male' ? '#0984e3' : 'var(--accent)',
                  borderColor: g === 'female' ? 'var(--pink)' : g === 'male' ? '#0984e3' : 'var(--accent)',
                  color: 'white',
                } : {}}
                onClick={() => setGender(g)}
              >
                {g === 'all' ? 'All' : g === 'female' ? 'F' : 'M'}
              </button>
            ))}
          </div>

          {/* Voice list */}
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {filtered.filter(Boolean).map(v => {
              const g = getGender(v)
              const isSelected = v.voice_id === selected
              return (
                <div
                  key={v.voice_id}
                  onClick={() => { onChange(v.voice_id); setOpen(false) }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 12px', cursor: 'pointer',
                    background: isSelected ? 'var(--accent-subtle)' : 'transparent',
                    borderLeft: isSelected ? '2px solid var(--accent)' : '2px solid transparent',
                    transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = 'var(--surface-2)' }}
                  onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent' }}
                >
                  <div style={{
                    width: 24, height: 24, borderRadius: 6,
                    background: g === 'female' ? 'var(--pink)' : g === 'male' ? '#0984e3' : 'var(--border)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 10, fontWeight: 700, color: 'white', flexShrink: 0,
                  }}>
                    {g === 'female' ? 'F' : g === 'male' ? 'M' : '?'}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {v.name}
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 1 }}>
                      {v.labels?.accent ?? ''}
                    </div>
                  </div>
                  {isSelected && <div style={{ color: 'var(--accent)', fontSize: 14 }}>✓</div>}
                </div>
              )
            })}
            {filtered.length === 0 && (
              <div style={{ padding: 20, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13 }}>
                No voices match
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
