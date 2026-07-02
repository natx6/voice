export interface VoiceSettings {
  stability: number
  similarity_boost: number
  style_exaggeration: number
  speaker_boost: boolean
  speed: number
  character: string
}

export interface HistoryEntry {
  id: number
  type: 'sts' | 'tts'
  timestamp: string
  voice_id: string
  voice_name: string
  duration_secs: number
  file_path: string
  text: string
  label: string
  stability: number
  similarity_boost: number
  style_exaggeration: number
  speaker_boost: boolean
}

export interface VoiceInfo {
  voice_id: string
  name: string
  category: string
  labels?: Record<string, string>
}

export type TabName = 'record' | 'tts' | 'history' | 'settings'
