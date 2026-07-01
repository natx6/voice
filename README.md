# ElevenLabs Real-Time Voice Changer

Real-time **male↔female** (or any voice-to-voice) conversion on **Fedora 43**
using the ElevenLabs Speech-to-Speech streaming API.

Speak into your mic → converted voice comes out of a virtual microphone →
any app (WhatsApp, Telegram, Linphone, Zoom, Discord) picks it up as its
mic input. **End-to-end latency <400 ms.**

---

## Quick Start

```bash
# 1. Run the setup script (installs everything + creates virtual mic)
./setup_voice_changer.sh

# 2. Set your ElevenLabs API key
export ELEVENLABS_API_KEY="sk_..."

# 3. Run the converter (interactive — picks voice and devices)
python3 voice_converter.py

# 4. In your app, select "VoiceChanger" as the microphone
```

---

## Table of Contents

1. [Fedora 43 Setup](#1-fedora-43-setup)
2. [Virtual Audio Sink](#2-virtual-audio-sink)
3. [Dependencies](#3-dependencies)
4. [Usage](#4-usage)
5. [App Configuration](#5-app-configuration)
6. [VoIP.ms Registration (Linphone)](#6-voipms-registration-linphone)
7. [Voice Cloning](#7-voice-cloning)
8. [How It Works](#8-how-it-works)
9. [Troubleshooting](#9-troubleshooting)
10. [Stopping](#10-stopping)

---

## 1. Fedora 43 Setup

Run **one command:**

```bash
./setup_voice_changer.sh
```

This does **everything** automatically:

| Step | What it does |
|------|-------------|
| System packages | `python3`, `pipewire-pulseaudio`, `portaudio`, build tools |
| Python packages | `sounddevice`, `numpy`, `elevenlabs`, `requests` |
| Virtual sink | Creates `VoiceChanger` null-sink + `VoiceChanger.monitor` source |
| Persistence | Installs a `systemd --user` service so the virtual sink survives reboots |

### Manual fallback

If you prefer to do it step by step:

```bash
# System packages
sudo dnf install -y python3-pip python3-devel pipewire-pulseaudio \
    pulseaudio-utils alsa-lib-devel portaudio-devel

# Python packages
pip3 install --upgrade sounddevice numpy elevenlabs requests

# Virtual sink (creates the mic that apps will see)
pactl load-module module-null-sink \
    sink_name=VoiceChanger \
    sink_properties=device.description=VoiceChanger

# Make it permanent
mkdir -p ~/.config/systemd/user/
# (see setup_voice_changer.sh for the full systemd unit)
```

---

## 2. Virtual Audio Sink

The virtual sink is the **heart of the setup**. It's a software-only audio
device with two ports:

- **`VoiceChanger`** (sink) — where the Python script **writes** converted audio
- **`VoiceChanger.monitor`** (source) — what apps **read** as their microphone

```
Physical Mic → Python → ElevenLabs API → [VoiceChanger sink]
                                                    ↓
                                        VoiceChanger.monitor
                                                    ↓
                                        WhatsApp / Telegram / Linphone
```

### Commands to manage it

```bash
# List all sinks
pactl list-sinks short

# List all sources (the monitor appears here)
pactl list-sources short

# Remove and recreate
pactl unload-module module-null-sink
pactl load-module module-null-sink sink_name=VoiceChanger \
    sink_properties=device.description=VoiceChanger
```

---

## 3. Dependencies

| Package | Purpose |
|---------|---------|
| `sounddevice` | Audio capture from mic + playback to virtual sink |
| `numpy` | Audio buffer manipulation (RMS, reshaping) |
| `elevenlabs` | Official Python SDK for ElevenLabs API |
| `requests` | Fallback HTTP client if SDK is missing |
| `pipewire-pulseaudio` | PulseAudio compatibility layer for PipeWire |
| `portaudio-devel` | Build dependency for sounddevice |

All installed by `setup_voice_changer.sh`. To update later:

```bash
pip3 install --upgrade elevenlabs sounddevice numpy requests
```

---

## 4. Usage

### Set your API key

```bash
export ELEVENLABS_API_KEY="sk_0e4ac5645cd8aa3cadcf3cf788dc80805022474d52ea4a2f"
```

Or pass it on the command line:

```bash
python3 voice_converter.py --api-key "sk_..."
```

### Interactive mode (recommended first run)

```bash
python3 voice_converter.py
```

Prompts you to:
1. Select a voice from the ElevenLabs library (or paste a Voice ID)
2. Choose input device (microphone)
3. Choose output device (the "VoiceChanger" virtual sink)

### Command-line mode

```bash
# List available voices
python3 voice_converter.py --list-voices

# List audio devices
python3 voice_converter.py --list-devices

# Run with a specific voice
python3 voice_converter.py --voice-id JBFqnCBsd6RMkjVDRZzb

# With specific device indices
python3 voice_converter.py \
    --voice-id 21m00Tcm4TlvDq8ikWAM \
    --input-device 2 \
    --output-device 5

# Adjust VAD sensitivity (lower = more sensitive)
python3 voice_converter.py --threshold 150

# Debug logging
python3 voice_converter.py --verbose
```

### Popular preset voice IDs

| Voice | Voice ID | Gender |
|-------|----------|--------|
| Rachel | `21m00Tcm4TlvDq8ikWAM` | Female |
| Bella | `EXAVITQu4vr2l5k6U2P1` | Female |
| Sarah | `ODq5zmih8GrVes37Dizd` | Female |
| Josh | `TxGEqnHWrfWFTfGW9XjX` | Male |
| Arnold | `VR6AewLTigWG4xSOukaG` | Male |
| Adam | `pNInz6obpgDQGcFmaJgB` | Male |

Use `--list-voices` to see all voices available on your account.

---

## 5. App Configuration

### WhatsApp Desktop

```
Settings → Audio → Microphone → "VoiceChanger Monitor Source"
```

- WhatsApp may need a restart to see new audio devices
- Works with both voice calls and voice messages

### Telegram Desktop

```
Settings → Advanced → Microphone → "VoiceChanger Monitor Source"
```

- Test by recording a voice message — it should play back with the converted voice
- Also works for voice chats and calls

### Linphone (softphone)

```
Preferences → Audio → Capture device → "VoiceChanger Monitor Source"
```

Also set:
- **Playback device**: your headphones/speakers (not the virtual sink)
- **Ringer device**: your headphones/speakers

### Zoiper

```
Settings → Audio → Input device → "VoiceChanger Monitor Source"
```

### Other apps (Discord, Zoom, Google Meet, etc.)

Any app that lets you choose a microphone can select
`VoiceChanger Monitor Source`.

---

## 6. VoIP.ms Registration (Linphone)

To make and receive calls via VoIP.ms:

### In the VoIP.ms portal

1. Log in at [voip.ms](https://voip.ms)
2. **Create a DID number** (or use an existing one)
3. Note your **sip username** and **sip password** under
   `Billing → Sub Accounts` (or create a sub-account)
4. Under `Sub Accounts`, ensure:
   - **SIP/IAX**: `SIP`
   - **Caller ID Name**: anything you want
   - **Password**: set a strong password

### In Linphone

1. Open Linphone → `Preferences → SIP Accounts`
2. Click **`+`** to add an account
3. Fill in:

   | Field | Value |
   |-------|-------|
   | Username | (your VoIP.ms sub-account username) |
   | SIP Domain / Registrar | `atlanta.voip.ms` (or closest server) |
   | Password | (your VoIP.ms sub-account password) |
   | Display Name | (anything) |
   | Transport | UDP |

   **Pick the nearest SIP server** from:
   - `atlanta.voip.ms`
   - `dallas.voip.ms`
   - `denver.voip.ms`
   - `losangeles.voip.ms`
   - `montreal.voip.ms`
   - `newyork.voip.ms`
   - `toronto.voip.ms`
   - `vancouver.voip.ms`

4. Click **Save** — Linphone registers with VoIP.ms (green checkmark = success)
5. Test by calling `echo` or `1000` (VoIP.ms echo test number)

Now all calls through Linphone will use the converted voice!

### PSTN Call Flow

```
You → Physical Mic → Python → ElevenLabs → VoiceChanger sink → Linphone
                                                                    ↓
                                                                 VoIP.ms
                                                                    ↓
                                                            Phone Network
                                                                    ↓
                                                            Recipient hears
                                                            converted voice
```

---

## 7. Voice Cloning

To use your **own voice** (or a custom target voice):

1. Go to [ElevenLabs Voice Lab](https://elevenlabs.io/app/voice-lab)
2. Click **"Add Voice"** → **"Instant Voice Cloning"**
3. Upload **1–5 minutes** of clean speech:
   - No background noise
   - Clear, consistent recording
   - Single speaker
   - Good audio quality (48 kHz+ preferred)
4. Name your voice and click **"Add Voice"**
5. Once created, copy the **Voice ID** from the voice's page (looks like:
   `5QJ5DFh4Mj8Tqq1I8TlK`)
6. Use it with:

```bash
python3 voice_converter.py --voice-id "5QJ5DFh4Mj8Tqq1I8TlK"
```

**Professional voice cloning** (ElevenLab's "Professional Voice Cloning"):
Same process but costs more and gives higher quality. Available on
ElevenLabs Creator/Pro plans.

---

## 8. How It Works

```
┌─────────────────────────────────────────────────────────────────────┐
│  Your Computer                                                       │
│                                                                     │
│  ┌──────────┐   20ms blocks    ┌──────────┐   300ms segments        │
│  │ Physical  │ ──────────────→ │  Python  │ ──────────────────────→ │
│  │ Microphone│                 │ Script  │                         │
│  └──────────┘                  │          │    ElevenLabs STS API   │
│                                │ (VAD →  │    (multilingual_v2)    │
│                                │  Buffer)│ ←────────────────────── │
│                                └────┬─────┘                        │
│                                     │                              │
│                          Converted PCM audio                       │
│                                     │                              │
│                                     ↓                              │
│                             ┌──────────────┐                       │
│                             │ VoiceChanger  │  (virtual sink)      │
│                             │ Null Sink     │                      │
│                             └──────┬───────┘                       │
│                                    │                               │
│                                    ↓                               │
│                          VoiceChanger.monitor                       │
│                          (virtual microphone)                       │
│                                    │                               │
│                                    ↓                               │
│                    WhatsApp / Telegram / Linphone                   │
│                    (selected as mic input)                          │
└─────────────────────────────────────────────────────────────────────┘
                                    ↓
                           Remote caller hears
                           converted voice
```

### Latency Budget

| Stage | Time | Description |
|-------|------|-------------|
| VAD segment accumulation | ~300 ms | Buffering speech before API call |
| ElevenLabs API processing | ~60–120 ms | First-byte latency with optimize=4 |
| Playout buffer | ~20 ms | Jitter buffer (2 blocks) |
| **Total** | **~380–440 ms** | End-to-end |

### Pipeline threads

- **Capture thread**: reads mic at 20 ms blocks, runs energy-based VAD,
  assembles 300 ms speech segments
- **Process thread**: sends segments to ElevenLabs STS, reads streaming
  response, queues converted chunks
- **Playout thread**: drains the output queue, writes to virtual sink

---

## 9. Troubleshooting

### "Virtual sink not found"

```bash
# Check if it exists
pactl list-sinks short | grep VoiceChanger

# If missing, create it
pactl load-module module-null-sink \
    sink_name=VoiceChanger \
    sink_properties=device.description=VoiceChanger

# Check PipeWire status
systemctl --user status pipewire-pulse.service
```

### No audio / silent output

```bash
# Verify Python can see the devices
python3 voice_converter.py --list-devices

# Check monitor source exists
pactl list-sources short | grep VoiceChanger

# Follow the log in verbose mode
python3 voice_converter.py --verbose
```

### 401 Unauthorized from ElevenLabs

```bash
# Verify your key is set
echo "${ELEVENLABS_API_KEY:0:8}..."   # should show "sk_..."

# Test directly
curl -H "xi-api-key: $ELEVENLABS_API_KEY" \
     https://api.elevenlabs.io/v1/voices
```

### API errors or timeouts

```bash
# Check internet
ping -c2 api.elevenlabs.io

# Check ElevenLabs status
# https://status.elevenlabs.io
```

### High latency / choppy audio

- Lower the VAD threshold for faster detection: `--threshold 100`
- Use a wired microphone (no Bluetooth — adds ~100–200 ms latency)
- Close other bandwidth-intensive apps
- Run `python3 voice_converter.py --verbose` to see per-segment stats

### App doesn't see VoiceChanger

Restart the app after creating the virtual sink. Some apps scan audio
devices only at startup.

---

## 10. Stopping

Press **`Ctrl+C`** in the terminal where the converter is running.

The script handles clean shutdown — threads terminate, audio streams close.

To also remove the virtual sink (not required — it's harmless):

```bash
pactl unload-module module-null-sink
```
