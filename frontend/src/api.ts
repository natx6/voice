import type { VoiceSettings, HistoryEntry, VoiceInfo } from './types'

const BASE = '/api'

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  // 120s timeout for audio generation, 15s for other calls
  const isGen = url.includes('/tts') || url.includes('/refine-text') || url.includes('/voices')
  const timeoutMs = isGen ? 120000 : 15000
  const timeoutController = new AbortController()
  const timeoutId = setTimeout(() => timeoutController.abort(), timeoutMs)

  // Combine caller's signal with timeout signal
  const callSignal = init?.signal
  const combinedSignal = timeoutController.signal

  if (callSignal) {
    callSignal.addEventListener('abort', () => timeoutController.abort())
  }

  try {
    const res = await fetch(`${BASE}${url}`, {
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
      signal: combinedSignal,
    })
    clearTimeout(timeoutId)

    if (!res.ok) {
      const text = await res.text().catch(() => 'Unknown error')
      throw new Error(`${res.status}: ${text.slice(0, 200)}`)
    }
    return res.json()
  } catch (e: any) {
    clearTimeout(timeoutId)
    if (e.name === 'AbortError') {
      if (callSignal?.aborted) {
        throw e // caller's cancel, re-throw as-is
      }
      throw new Error(isGen ? 'Still loading, taking longer than expected...' : 'Connection timed out — server may be offline')
    }
    throw e
  }
}

// ── Status ──

export interface Status {
  status: string
  audio_sources: string[]
  audio_sinks: string[]
  history_count: number
}

export async function getStatus(): Promise<Status> {
  return fetchJson('/status')
}

// ── Devices ──

export async function getSources(): Promise<{ sources: string[]; default: string }> {
  return fetchJson('/devices/sources')
}

export async function getSinks(): Promise<{ sinks: string[] }> {
  return fetchJson('/devices/sinks')
}

// ── Voices ──

export async function getVoices(): Promise<VoiceInfo[]> {
  const res = await fetchJson<{ voices: VoiceInfo[] }>('/voices')
  return res.voices
}

// ── Recording ──

export async function startRecord(source?: string): Promise<void> {
  const params = source ? `?source=${encodeURIComponent(source)}` : ''
  await fetchJson(`/record/start${params}`, { method: 'POST' })
}

export async function stopRecord(): Promise<{ file_path: string; duration_secs: number; size_bytes: number }> {
  return fetchJson('/record/stop', { method: 'POST' })
}

export async function getRecordStatus(): Promise<{ recording: boolean }> {
  return fetchJson('/record/status')
}

// ── Conversion (STS) ──

export interface ConvertResult {
  status: string
  file_path: string
  duration_secs: number
  history_id: number
}

export async function convertAudio(voiceId: string, inputFile: string, settings: VoiceSettings): Promise<ConvertResult> {
  return fetchJson(`/convert?input_file=${encodeURIComponent(inputFile)}`, {
    method: 'POST',
    body: JSON.stringify({ voice_id: voiceId, voice_settings: settings }),
  })
}

// ── TTS ──

export interface TTSResult {
  status: string
  file_path: string
  duration_secs: number
  chars: number
  history_id: number
  seed?: number
}

function getWallet(): string {
  try { return localStorage.getItem('sh-wallet') || '' } catch { return '' }
}

export async function generateTTS(text: string, voiceId: string, settings: VoiceSettings, signal?: AbortSignal): Promise<TTSResult> {
  return fetchJson('/tts', {
    method: 'POST',
    body: JSON.stringify({ text, voice_id: voiceId, voice_settings: settings, wallet: getWallet() }),
    signal,
  })
}

export async function generateTTSVariations(text: string, voiceId: string, settings: VoiceSettings, count?: number): Promise<TTSResult[]> {
  const res = await fetchJson<{ status: string; variations: TTSResult[] }>('/tts/variations', {
    method: 'POST',
    body: JSON.stringify({ text, voice_id: voiceId, voice_settings: settings, count: count ?? 3, wallet: getWallet() }),
  })
  return res.variations
}

// ── Playback ──

export async function previewAudio(filePath: string, speed?: number, character?: string): Promise<void> {
  await fetchJson('/preview', {
    method: 'POST',
    body: JSON.stringify({ file_path: filePath, countdown_secs: 0, speed: speed ?? 1.0, character: character ?? 'studio' }),
  })
}

export async function captureAudio(filePath: string, countdown?: number, speed?: number, character?: string): Promise<void> {
  await fetchJson('/capture', {
    method: 'POST',
    body: JSON.stringify({ file_path: filePath, countdown_secs: countdown ?? 3, speed: speed ?? 1.0, character: character ?? 'studio' }),
  })
}

export interface PlayStatus {
  playing: boolean
  file_path: string
  total_secs: number
  elapsed_secs: number
  progress_pct: number
  mode: string
}

export async function getPlayStatus(): Promise<PlayStatus> {
  return fetchJson('/play/status')
}

export async function stopPlayback(): Promise<void> {
  await fetchJson('/play/stop', { method: 'POST' })
}

// ── History ──

export async function getHistory(): Promise<HistoryEntry[]> {
  const res = await fetchJson<{ entries: HistoryEntry[] }>('/history')
  return res.entries
}

export async function deleteHistory(id: number): Promise<void> {
  await fetchJson(`/history/${id}`, { method: 'DELETE' })
}

export async function labelHistory(id: number, label: string): Promise<void> {
  await fetchJson(`/history/${id}/label?label=${encodeURIComponent(label)}`, { method: 'PATCH' })
}

// ── Text Refinement ──

export interface RefineResult {
  status: string
  original: string
  refined: string
  provider: string
}

export async function refineText(text: string, style?: string): Promise<RefineResult> {
  return fetchJson('/refine-text', {
    method: 'POST',
    body: JSON.stringify({ text, style: style ?? 'conversational' }),
  })
}

// ── Auth ──

let _token: string | null = null

export function setToken(t: string | null) {
  _token = t
  if (t) localStorage.setItem('sh-auth-token', t)
  else localStorage.removeItem('sh-auth-token')
}

export function getToken(): string | null {
  if (!_token) _token = localStorage.getItem('sh-auth-token')
  return _token
}

function authHeaders(): Record<string, string> {
  const t = getToken()
  return t ? { 'Authorization': `Bearer ${t}` } : {}
}

export interface AuthUser {
  id: number
  email: string
  role: string
  wallet: string
  credits?: number
}

export async function signup(email: string, password: string, inviteCode: string): Promise<{ token: string; user: AuthUser }> {
  const res = await fetchJson<{ status: string; token: string; user: AuthUser }>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify({ email, password, invite_code: inviteCode }),
  })
  setToken(res.token)
  return res
}

export async function login(email: string, password: string): Promise<{ token: string; user: AuthUser }> {
  const res = await fetchJson<{ status: string; token: string; user: AuthUser }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  setToken(res.token)
  return res
}

export async function logout(): Promise<void> {
  try {
    await fetchJson('/auth/logout', { method: 'POST', headers: authHeaders() })
  } catch {}
  setToken(null)
}

export async function getMe(): Promise<AuthUser> {
  const res = await fetchJson<{ status: string; user: AuthUser }>('/auth/me', { headers: authHeaders() })
  return res.user
}

export async function updateWallet(wallet: string): Promise<void> {
  await fetchJson('/auth/wallet', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify({ wallet }),
  })
}

// ── Admin ──

export async function getAdminUsers(): Promise<AuthUser[]> {
  const res = await fetchJson<{ users: AuthUser[] }>('/admin/users', { headers: authHeaders() })
  return res.users
}

export async function createInviteCodes(count: number): Promise<string[]> {
  const res = await fetchJson<{ codes: string[] }>('/admin/invite', {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ count }),
  })
  return res.codes
}

export async function getInviteCodes(): Promise<any[]> {
  const res = await fetchJson<{ invites: any[] }>('/admin/invites', { headers: authHeaders() })
  return res.invites
}

export async function getAdminSettings(): Promise<Record<string, string>> {
  const res = await fetchJson<{ settings: Record<string, string> }>('/admin/settings', { headers: authHeaders() })
  return res.settings
}

export async function updateAdminSettings(settings: Record<string, string>): Promise<void> {
  await fetchJson('/admin/settings', {
    method: 'POST',
    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
}

export async function createUserInviteCode(): Promise<string> {
  const res = await fetchJson<{ code: string }>('/settings/invite', {
    method: 'POST',
    headers: authHeaders(),
  })
  return res.code
}

export async function createApiKey(name?: string): Promise<{ api_keys: any[]; key: string }> {
  return fetchJson(`/keys/create?name=${encodeURIComponent(name || '')}`, {
    method: 'POST',
    headers: authHeaders(),
  })
}

export async function getApiKeys(): Promise<any[]> {
  const res = await fetchJson<{ api_keys: any[] }>('/keys', { headers: authHeaders() })
  return res.api_keys
}

export async function deleteApiKey(key: string): Promise<void> {
  await fetchJson(`/keys/${encodeURIComponent(key)}`, { method: 'DELETE', headers: authHeaders() })
}

// ── Voice Design ──

export interface VoiceDesignResult {
  status: string
  voice_id: string
  voice_name: string
}

export async function designVoice(description: string): Promise<VoiceDesignResult> {
  return fetchJson('/voice/design', {
    method: 'POST',
    body: JSON.stringify({ text_description: description }),
  })
}

// ── Voice Blend ──

export interface VoiceBlendResult {
  status: string
  voice_id: string
  voice_name: string
}

export async function blendVoices(voiceIds: string[], weights?: number[]): Promise<VoiceBlendResult> {
  return fetchJson('/voice/blend', {
    method: 'POST',
    body: JSON.stringify({ voice_ids: voiceIds, weights }),
  })
}
