import { useState } from 'react'
import type { VoiceSettings, VoiceInfo } from '../types'
import * as api from '../api'

interface Props {
  settings: VoiceSettings
  onChange: (s: VoiceSettings) => void
  voices: VoiceInfo[]
  showToast: (msg: string) => void
}

export default function SettingsTab({ settings, onChange, voices, showToast }: Props) {
  const [designDesc, setDesignDesc] = useState('')
  const [designing, setDesigning] = useState(false)

  const [blendIds, setBlendIds] = useState<string[]>(['', ''])
  const [blending, setBlending] = useState(false)

  // ── Presets ──

  const presets: { name: string; s: VoiceSettings }[] = [
    { name: 'Natural', s: { stability: 0.25, similarity_boost: 0.60, style_exaggeration: 0, speaker_boost: false, speed: 1.0, character: 'natural' } },
    { name: 'Unique', s: { stability: 0.35, similarity_boost: 0.40, style_exaggeration: 0.1, speaker_boost: false, speed: 1.0, character: 'studio' } },
    { name: 'Stable', s: { stability: 0.70, similarity_boost: 0.85, style_exaggeration: 0, speaker_boost: false, speed: 1.0, character: 'studio' } },
    { name: 'Dramatic', s: { stability: 0.30, similarity_boost: 0.75, style_exaggeration: 0.6, speaker_boost: false, speed: 1.0, character: 'studio' } },
    { name: 'Robotic', s: { stability: 0.90, similarity_boost: 0.95, style_exaggeration: 0, speaker_boost: false, speed: 1.0, character: 'studio' } },
    { name: 'Phone Call', s: { stability: 0.30, similarity_boost: 0.75, style_exaggeration: 0, speaker_boost: false, speed: 1.0, character: 'phone' } },
    { name: 'Lo-Fi', s: { stability: 0.35, similarity_boost: 0.70, style_exaggeration: 0, speaker_boost: false, speed: 1.0, character: 'lo-fi' } },
    { name: 'Warm', s: { stability: 0.30, similarity_boost: 0.75, style_exaggeration: 0, speaker_boost: false, speed: 1.0, character: 'warm' } },
    { name: 'Vintage', s: { stability: 0.30, similarity_boost: 0.75, style_exaggeration: 0, speaker_boost: false, speed: 1.0, character: 'vintage' } },
    { name: 'Fast Talker', s: { stability: 0.30, similarity_boost: 0.75, style_exaggeration: 0, speaker_boost: false, speed: 1.5, character: 'studio' } },
    { name: 'Slow & Clear', s: { stability: 0.40, similarity_boost: 0.80, style_exaggeration: 0, speaker_boost: false, speed: 0.7, character: 'studio' } },
  ]

  // ── Voice Design ──

  const handleDesign = async () => {
    if (!designDesc.trim()) return
    setDesigning(true)
    try {
      const result = await api.designVoice(designDesc)
      if (result.status === 'ok') {
        showToast(`✨ New voice created: ${result.voice_name} (${result.voice_id.slice(0, 8)}...)`)
        setDesignDesc('')
      } else {
        showToast('Voice design failed — check the API key and plan')
      }
    } catch (e: any) {
      showToast(`Voice design error: ${e.message}`)
    } finally {
      setDesigning(false)
    }
  }

  // ── Voice Blend ──

  const handleBlend = async () => {
    const valid = blendIds.filter(id => id.trim())
    if (valid.length < 2) return
    setBlending(true)
    try {
      const result = await api.blendVoices(valid)
      if (result.status === 'ok') {
        showToast(`🔀 Blend created: ${result.voice_name}`)
      } else {
        showToast('Blend failed — check voice IDs')
      }
    } catch (e: any) {
      showToast(`Blend error: ${e.message}`)
    } finally {
      setBlending(false)
    }
  }

  const addBlendSlot = () => {
    if (blendIds.length < 4) setBlendIds([...blendIds, ''])
  }

  const setBlendSlot = (i: number, val: string) => {
    const next = [...blendIds]
    next[i] = val
    setBlendIds(next)
  }

  return (
    <div>
      {/* ── Voice Settings ── */}
      <div className="card">
        <div className="card-title">🎛 Voice Settings</div>
        <p style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 16 }}>
          These affect how natural, unique, or dramatic the voice sounds.
        </p>

        <div className="form-group">
          <label>Stability — {settings.stability.toFixed(2)}</label>
          <div className="slider-group">
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Expressive</span>
            <input
              type="range" min={0} max={1} step={0.05}
              value={settings.stability}
              onChange={e => onChange({ ...settings, stability: parseFloat(e.target.value) })}
            />
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Robotic</span>
            <span className="slider-value">{settings.stability.toFixed(2)}</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--green)', marginTop: 4 }}>
            💡 Pro tip: 0.35–0.45 is the sweet spot for natural conversational speech
          </div>
        </div>

        <div className="form-group">
          <label>Similarity Boost — {settings.similarity_boost.toFixed(2)}</label>
          <div className="slider-group">
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Unique</span>
            <input
              type="range" min={0} max={1} step={0.05}
              value={settings.similarity_boost}
              onChange={e => onChange({ ...settings, similarity_boost: parseFloat(e.target.value) })}
            />
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Clone</span>
            <span className="slider-value">{settings.similarity_boost.toFixed(2)}</span>
          </div>
        </div>

        <div className="form-group">
          <label>Style Exaggeration — {settings.style_exaggeration.toFixed(2)}</label>
          <div className="slider-group">
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Subtle</span>
            <input
              type="range" min={0} max={1} step={0.05}
              value={settings.style_exaggeration}
              onChange={e => onChange({ ...settings, style_exaggeration: parseFloat(e.target.value) })}
            />
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Dramatic</span>
            <span className="slider-value">{settings.style_exaggeration.toFixed(2)}</span>
          </div>
        </div>

        <div className="form-group">
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={settings.speaker_boost}
              onChange={e => onChange({ ...settings, speaker_boost: e.target.checked })}
              style={{ width: 'auto' }}
            />
            Speaker Boost (prefer original speaker identity)
          </label>
        </div>

        <div className="form-group">
          <label>Speed — {settings.speed.toFixed(2)}x</label>
          <div className="slider-group">
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Slow</span>
            <input
              type="range" min={0.5} max={2.0} step={0.05}
              value={settings.speed}
              onChange={e => onChange({ ...settings, speed: parseFloat(e.target.value) })}
            />
            <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>Fast</span>
            <span className="slider-value">{settings.speed.toFixed(2)}x</span>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
            Applied during playback and TTS generation. 0.5x = half speed, 2.0x = double.
          </div>
        </div>

        <div className="form-group">
          <label>Character</label>
          <select
            value={settings.character}
            onChange={e => onChange({ ...settings, character: e.target.value })}
          >
            <option value="studio">Studio (clean, clear)</option>
            <option value="warm">Warm (softer highs)</option>
            <option value="natural">Natural (slight room ambience)</option>
            <option value="lo-fi">Lo-Fi (muffled, like a recording)</option>
            <option value="phone">Phone Call (narrow band)</option>
            <option value="vintage">Vintage (analog warmth)</option>
          </select>
          <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 4 }}>
            Post-processing filter applied during preview/capture. "Studio" = no processing.
          </div>
        </div>
      </div>

      {/* ── Presets ── */}
      <div className="card">
        <div className="card-title">⭐ Quick Presets</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {presets.map(p => (
            <button
              key={p.name}
              className="btn btn-ghost btn-sm"
              onClick={() => onChange(p.s)}
            >
              {p.name}
            </button>
          ))}
        </div>
      </div>

      {/* ── Voice Design ── */}
      <div className="card">
        <div className="card-title">✨ Design a New Voice</div>
        <p style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 12 }}>
          Describe the voice you want and ElevenLabs will create it.
        </p>
        <div className="form-group">
          <input
            type="text"
            value={designDesc}
            onChange={e => setDesignDesc(e.target.value)}
            placeholder='e.g. "warm female voice, early 30s, British accent, natural"'
            onKeyDown={e => { if (e.key === 'Enter') handleDesign() }}
          />
        </div>
        <button className="btn btn-primary" onClick={handleDesign} disabled={designing || !designDesc.trim()}>
          {designing ? '⏳ Designing...' : '✨ Create Voice'}
        </button>
      </div>

      {/* ── Voice Blend ── */}
      <div className="card">
        <div className="card-title">🔀 Blend Voices</div>
        <p style={{ fontSize: 12, color: 'var(--text-dim)', marginBottom: 12 }}>
          Mix 2–4 existing voices to create a unique hybrid.
        </p>

        {blendIds.map((val, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8, alignItems: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--text-dim)', minWidth: 60 }}>
              Voice {i + 1}
            </span>
            <select
              value={val}
              onChange={e => setBlendSlot(i, e.target.value)}
              style={{ flex: 1 }}
            >
              <option value="">Select a voice</option>
              {voices.map(v => (
                <option key={v.voice_id} value={v.voice_id}>
                  {v.name}
                </option>
              ))}
            </select>
            {blendIds.length > 2 && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setBlendIds(blendIds.filter((_, j) => j !== i))}
              >
                ✕
              </button>
            )}
          </div>
        ))}

        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          {blendIds.length < 4 && (
            <button className="btn btn-ghost btn-sm" onClick={addBlendSlot}>
              + Add Voice
            </button>
          )}
          <button
            className="btn btn-primary btn-sm"
            onClick={handleBlend}
            disabled={blending || blendIds.filter(b => b.trim()).length < 2}
          >
            {blending ? '⏳ Blending...' : '🔀 Create Blend'}
          </button>
        </div>
      </div>
    </div>
  )
}
