# ElevenLabs Voice Changer Suite

Real-time **voice conversion**, **voice note generation**, and **TTS** using the ElevenLabs Speech-to-Speech and Text-to-Speech APIs.

**Fedora 43 (PipeWire) • <400 ms latency • Virtual microphone for any app**

---

## Quick Start

```bash
# 1. Install everything + create virtual mic
./setup_voice_changer.sh

# 2. Set your API key
export ELEVENLABS_API_KEY="sk_..."

# 3. Pick a tool:
python3 voice_converter.py           # Real-time voice changer
python3 voice_note.py --voice-id X   # Record → convert → play
python3 tts_voice_note.py --voice-id X  # Type → TTS → play

# 4. In your app (Telegram/WhatsApp), select "VoiceChanger" as mic
```

---

## Tools

| Tool | What it does |
|------|-------------|
| `voice_converter.py` | Real-time: mic → VAD → ElevenLabs STS → virtual sink (for calls) |
| `voice_note.py` | Record a voice note → convert it → play through VC → Telegram captures it |
| `tts_voice_note.py` | Type a message → TTS generates it → play through VC → Telegram captures it |
| **API backend** | FastAPI server (`api/main.py`) — REST + WebSocket for the React frontend |
| **React frontend** | `frontend/` — Vite + React SPA for visual control |

---

## New Features

### 🎛 Voice Settings (all tools)

Tune how every voice sounds with four dials:

| Parameter | Range | Low | High | Default |
|-----------|-------|-----|------|---------|
| `--stability` | 0–1 | Expressive, varied intonation | Robotic, monotone | 0.30 |
| `--similarity-boost` | 0–1 | Deviates from source (unique) | Tight clone | 0.95 |
| `--style-exaggeration` | 0–1 | Subtle delivery | Over-the-top dramatic | 0.0 |
| `--speaker-boost` | bool | Off | Prefer speaker identity | off |

**Presets** (use `--voice-preset <name>`):
- `natural` — S=0.25/B=0.60 — warm, expressive, less clone-like
- `unique` — S=0.35/B=0.40 — drifts from source for a more original sound
- `stable` — S=0.70/B=0.85 — consistent, good for longer recordings
- `dramatic` — S=0.30/B=0.75/E=0.60 — character voices
- `robotic` — S=0.90/B=0.95 — deliberately monotone

Example:
```bash
# Make Rachel sound more natural and unique
python3 voice_note.py --voice-id 21m00Tcm4TlvDq8ikWAM --voice-preset natural

# Manual tuning
python3 tts_voice_note.py --voice-id EXAVITQu4vr4xnSDxMaL \
  --stability 0.25 --similarity-boost 0.55 --style-exaggeration 0.1
```

### 🔄 Replay & Recapture

Every generated voice note is saved to history. Commands available in both `voice_note.py` and `tts_voice_note.py`:

```
H        — Show history (all past clips)
R#       — Replay entry # through VoiceChanger (with 3s countdown)
G#       — Regenerate entry # with current voice settings
D#       — Delete entry #
L# <lbl> — Label entry # with a meaningful name
```

This lets you:
- **Recapture** a clip if the Telegram timing was off
- **Regenerate** the same input with different voice settings
- **Label** clips so you can find them later
- **Delete** clips you don't want

History is persisted in `~/.voice_history/history.json`. Audio files go to `~/VoiceNotes/`.

### ✨ Voice Design (via API/frontend)

Describe a voice in plain English and ElevenLabs creates it:

```bash
curl -X POST http://localhost:8765/api/voice/design \
  -H "Content-Type: application/json" \
  -d '{"text_description": "warm female voice, early 30s, British accent"}'
```

### 🔀 Voice Blend (via API/frontend)

Mix 2–4 existing voices into a unique hybrid:

```bash
curl -X POST http://localhost:8765/api/voice/blend \
  -H "Content-Type: application/json" \
  -d '{"voice_ids": ["id1", "id2"], "weights": [0.6, 0.4]}'
```

### 🌐 React Frontend

A visual SPA that wraps all the CLI functionality:

```bash
# Terminal 1: Start the API backend
export ELEVENLABS_API_KEY="sk_..."
python3 -m api.main

# Terminal 2: Start the frontend (separate terminal)
cd frontend && npm run dev
```

Open http://localhost:5173 in your browser.

**Features:**
- **Record tab** — Mic button, VU meter, record/convert/play flow
- **TTS tab** — Text input with character count, generate & play
- **History tab** — Scrollable list with play, label, delete
- **Settings tab** — Stability/similarity/style sliders, presets, voice design, voice blending

---

## Command Reference

### voice_converter.py (real-time)

```bash
python3 voice_converter.py --voice-id <ID> \
  [--stability 0.25] [--similarity-boost 0.60] \
  [--style-exaggeration 0.0] [--speaker-boost] \
  [--voice-preset natural] \
  [--input-device bluetooth] [--output-device VoiceChanger] \
  [--threshold 100] [--verbose]
```

### voice_note.py (record → convert → play)

```bash
python3 voice_note.py --voice-id <ID> \
  [--voice-preset natural] \
  [--input recording.wav] [--output result.wav]

# Interactive mode (no --input):
#   R  — Record & convert
#   P  — Play result
#   H  — Show history
#   R# — Replay entry #
#   G# — Regenerate entry #
#   D# — Delete entry #
#   L# — Label entry #
#   Q  — Quit
```

### tts_voice_note.py (text → TTS → play)

```bash
python3 tts_voice_note.py --voice-id <ID> \
  [--voice-preset unique]

# Interactive mode:
#   Type your message, then 'S' to submit
#   H  — History
#   R# — Replay
#   G# — Regenerate
#   D# — Delete
#   L# — Label
```

### API Server

```bash
# Start the FastAPI backend
python3 -m api.main     # defaults to port 8765
# or:
export VOICE_API_PORT=8765
uvicorn api.main:app --reload --host 0.0.0.0 --port 8765
```

API docs at http://localhost:8765/docs (OpenAPI/Swagger).

---

## Project Structure

```
voice/
├── voice_converter.py      # Core STS client, VAD, Pipeline, VoiceSettings
├── voice_note.py           # Record → STS → play, with history/replay
├── tts_voice_note.py       # TTS → play, with history/replay
├── setup_voice_changer.sh  # Install deps + create virtual sink
├── voice_changer.sh        # Launcher
├── api/
│   ├── main.py             # FastAPI app with all routes
│   ├── models.py           # Pydantic request/response models
│   └── voice_manager.py    # Wraps CLI modules for the API
├── frontend/
│   ├── src/
│   │   ├── App.tsx         # Main app with tabs
│   │   ├── api.ts          # API client
│   │   ├── types.ts        # TypeScript types
│   │   └── components/
│   │       ├── RecordTab.tsx    # Recording UI
│   │       ├── TTSTab.tsx       # TTS UI
│   │       ├── HistoryTab.tsx   # History list
│   │       ├── SettingsTab.tsx   # Voice settings + design + blend
│   │       ├── VUMeter.tsx      # Mic level WebSocket
│   │       └── VoicePicker.tsx  # Voice selector
│   └── package.json
└── README.md
```

---

## How the Voice Pipeline Works

```
Physical Mic → VAD (energy-based, 20ms blocks) → segments (~300ms)
    → ElevenLabs STS API → converted PCM → VoiceChanger virtual sink
    → VoiceChanger.monitor source → Telegram/WhatsApp sees it as mic
```

**TTS path:** Text → ElevenLabs TTS API → PCM → VoiceChanger sink → app mic

---

## Voice Cloning & Custom Voices

| Method | Tool | Cost |
|--------|------|------|
| Voice settings tuning | `--stability`, `--similarity-boost` | Free |
| Quick presets | `--voice-preset natural\|unique\|dramatic` | Free |
| Voice design | API `/api/voice/design` or ElevenLabs Voice Lab | API usage |
| Voice blending | API `/api/voice/blend` | API usage |
| Instant voice clone | [ElevenLabs Voice Lab](https://elevenlabs.io/app/voice-lab) | Subscription |
| Professional clone | ElevenLabs Pro plan | Higher tier |

To make an existing voice sound **natural and unique**, start with:
```
--stability 0.25 --similarity-boost 0.55
```
This gives the model room to be expressive while deviating from the stock voice.

---

## Troubleshooting

- **"Voice design API not available"** — SDK version may not support it yet. Use [ElevenLabs Voice Lab](https://elevenlabs.io/app/voice-lab) directly.
- **Blend fails** — Verify all voice IDs are valid and your plan supports blending.
- **No audio** — Run `python3 voice_converter.py --list-devices` to verify PulseAudio devices.
- **Virtual sink missing** — `pactl load-module module-null-sink sink_name=VoiceChanger sink_properties=device.description=VoiceChanger`
