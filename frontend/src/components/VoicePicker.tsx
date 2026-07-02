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

  // Detect gender from labels or name (extensive fallback list)
  const getGender = (v: VoiceInfo): Gender => {
    const labels = v.labels ?? {}
    const labelGender = (labels.gender || '').toLowerCase()
    if (labelGender === 'male' || labelGender === 'female') {
      return labelGender as Gender
    }
    const name = v.name.toLowerCase()
    const femaleWords = [
      'female', 'woman', 'girl', 'lady', 'sarah', 'emma', 'bella', 'rachel', 'jessica',
      'olivia', 'charlotte', 'amelia', 'sophia', 'ava', 'mia', 'alice', 'matilda', 'laura',
      'lily', 'clara', 'anika', 'eryn', 'hope', 'hannah', 'sophie', 'chloe', 'isabella',
      'ella', 'grace', 'luna', 'layla', 'riley', 'zoe', 'victoria', 'aria', 'scarlett',
      'penelope', 'layla', 'mila', 'avery', 'camila', 'aria', 'skylar', 'katherine',
      'naomi', 'jasmine', 'maya', 'audrey', 'brooklyn', 'hazel', 'abigail', 'ella',
      'eleanor', 'stella', 'violet', 'aubrey', 'addison', 'natalie', 'leah', 'savannah',
      'anna', 'elizabeth', 'serenity', 'madison', 'lillian', 'claire', 'samantha',
      'kylie', 'peyton', 'morgan', 'kaylee', 'paige', 'makayla', 'marissa', 'brianna',
      'alexa', 'gabriella', 'london', 'jenna', 'kate', 'shelby', 'taylor', 'alexis',
      'mackenzie', 'ashley', 'jordyn', 'sydney', 'cassidy', 'chelsy', 'mary', 'diana',
      'lisa', 'susan', 'karen', 'betty', 'helen', 'jennifer', 'linda', 'barbara',
      'patricia', 'deborah', 'sandra', 'carol', 'sharon', 'michelle', 'amanda',
      'melissa', 'stephanie', 'nicole', 'danielle', 'catherine', 'christina',
      'lauren', 'rebecca', 'tiffany', 'heather', 'whitney', 'amber', 'crystal',
      'megan', 'erica', 'rachel', 'faith', 'joy', 'prudence', 'serena', 'iris',
      'rose', 'daisy', 'lilly', 'holly', 'heather', 'fern', 'wren', 'blake',
      'quinn', 'harper', 'reese', 'jade', 'jules',
    ]
    const maleWords = [
      'male', 'man', 'boy', 'guy', 'josh', 'adam', 'arnold', 'antoni', 'patrick',
      'sam', 'daniel', 'james', 'michael', 'david', 'thomas', 'chris', 'roger',
      'charlie', 'george', 'callum', 'harry', 'liam', 'will', 'eric', 'brian',
      'bill', 'henry', 'jack', 'oliver', 'noah', 'ethan', 'levi', 'owen', 'luke',
      'wyatt', 'logan', 'carter', 'jayden', 'gabriel', 'julian', 'grayson',
      'isaac', 'joseph', 'caleb', 'ryan', 'nathan', 'jacob', 'andrew', 'aiden',
      'mason', 'matthew', 'elijah', 'aaron', 'sebastian', 'colton', 'elias',
      'ezra', 'dominick', 'max', 'maxwell', 'theo', 'theodore', 'nicholas',
      'colin', 'connor', 'ian', 'alex', 'alexander', 'brandon', 'zachary',
      'kevin', 'jason', 'justin', 'eric', 'tyler', 'kyle', 'dylan', 'nolan',
      'cameron', 'evan', 'jordan', 'jake', 'cole', 'bradley', 'shawn', 'derrick',
      'marcus', 'derek', 'brendan', 'brady', 'spencer', 'dustin', 'mitchell',
      'steve', 'steven', 'philip', 'peter', 'paul', 'mark', 'john', 'robert',
      'richard', 'joseph', 'charles', 'william', 'george', 'edward', 'frank',
      'raymond', 'walter', 'harold', 'jack', 'henry', 'arthur', 'fred', 'albert',
      'samuel', 'earl', 'carl', 'ernest', 'lawrence', 'francis', 'leonard',
      'melvin', 'lester', 'clarence', 'vincent', 'howard', 'gordon', 'jerome',
      'guy', 'allen', 'bruce', 'brent', 'keith', 'terry', 'jerry', 'larry',
      'barry', 'tom', 'hugh', 'neil', 'reggie', 'ray', 'sidney', 'wade',
      'gilbert', 'dwayne', 'russell', 'colin', 'kurt', 'louis', 'lewis',
      'finley', 'toby', 'arthur', 'archie', 'albie', 'freddie', 'harrison',
    ]
    for (const w of femaleWords) {
      if (name.includes(w)) return 'female'
    }
    for (const w of maleWords) {
      if (name.includes(w)) return 'male'
    }
    return 'all' // unknown — show in "All" but not in gender filters
  }

  const filtered = useMemo(() => {
    if (gender === 'all') return voices
    return voices.filter(v => getGender(v) === gender)
  }, [voices, gender])

  const selectedVoice = voices.find(v => v.voice_id === selected)

  return (
    <div>
      {/* Gender filter buttons */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
        {(['all', 'female', 'male'] as Gender[]).map(g => (
          <button
            key={g}
            className="btn btn-sm"
            style={{
              flex: 1,
              padding: '4px 8px',
              border: 'none',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              background: gender === g
                ? g === 'female' ? '#e84393' : g === 'male' ? '#0984e3' : 'var(--accent)'
                : 'var(--surface-2)',
              color: gender === g ? '#fff' : 'var(--text-dim)',
            }}
            onClick={() => setGender(g)}
          >
            {g === 'all' ? '👥 All' : g === 'female' ? '👩 Woman' : '👨 Man'}
          </button>
        ))}
      </div>

      {/* Voice selector */}
      <select value={selected} onChange={e => onChange(e.target.value)}>
        {filtered.length === 0 && <option value="">No voices match</option>}
        {filtered.map(v => {
          const labels = v.labels ?? {}
          const accent = labels.accent ? ` · ${labels.accent}` : ''
          const g = getGender(v)
          const tag = g !== 'all' ? ` [${g}]` : ''
          return (
            <option key={v.voice_id} value={v.voice_id}>
              {v.name}{tag}{accent}
            </option>
          )
        })}
      </select>

      {/* Selected voice info */}
      {selectedVoice && (
        <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
          {selectedVoice.voice_id.slice(0, 8)}…
          {selectedVoice.labels?.gender ? ` · ${selectedVoice.labels.gender}` : ''}
          {selectedVoice.labels?.accent ? ` · ${selectedVoice.labels.accent}` : ''}
        </div>
      )}
    </div>
  )
}
