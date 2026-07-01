#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# ElevenLabs Voice Changer – Fedora 43 Setup Script
# ═══════════════════════════════════════════════════════════════════════════════
# This script installs all dependencies and creates the virtual audio sink.

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }
header(){ echo -e "\n${BOLD}╔═ $*${NC}"; echo; }

# ── 1. System dependencies ──────────────────────────────────────────────────

header "Step 1/5 — Installing system packages"

sudo dnf install -y \
    python3-pip python3-devel \
    pipewire-pulseaudio pulseaudio-utils \
    alsa-lib-devel portaudio-devel \
    webrtc-audio-processing-devel \
    cmake gcc-c++ make \
    git

info "System packages installed."

# ── 2. Python dependencies ───────────────────────────────────────────────────

header "Step 2/5 — Installing Python packages"

pip3 install --upgrade pip
pip3 install --upgrade \
    numpy \
    elevenlabs \
    requests

info "Python packages installed."

# ── 3. Virtual audio sink (PipeWire / PulseAudio) ───────────────────────────

header "Step 3/5 — Creating virtual audio sink"

# Unload any previous instance
pactl unload-module module-null-sink 2>/dev/null || true

# Create a null-sink named "VoiceChanger"
#
#   sink_name=VoiceChanger      → technical name used in pactl / pw-cli
#   sink_properties=             → human-readable label shown in apps
#
# The sink also creates a monitor source (VoiceChanger.monitor) that apps
# will select as their microphone.
pactl load-module module-null-sink \
    sink_name=VoiceChanger \
    sink_properties=device.description=VoiceChanger

info "Virtual sink 'VoiceChanger' created."
info "Monitor source: VoiceChanger.monitor"

# ── 4. Auto-load on login (user-level systemd service) ──────────────────────

header "Step 4/5 — Persisting virtual sink across reboots"

mkdir -p ~/.config/systemd/user/

cat > ~/.config/systemd/user/voice-changer-sink.service << 'EOF'
[Unit]
Description=ElevenLabs Voice Changer Virtual Sink
After=pipewire-pulse.service wireplumber.service
PartOf=pipewire-pulse.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=pactl load-module module-null-sink sink_name=VoiceChanger sink_properties=device.description=VoiceChanger
ExecStop=pactl unload-module module-null-sink

[Install]
WantedBy=pipewire-pulse.service
EOF

systemctl --user daemon-reload
systemctl --user enable voice-changer-sink.service
systemctl --user start voice-changer-sink.service

info "Service enabled & started."

# ── 5. Verify ───────────────────────────────────────────────────────────────

header "Step 5/5 — Verifying"

echo -n "  Checking Python... "
python3 -c "import numpy, elevenlabs; print('OK')"

echo    "  Audio devices:"
python3 -c "
import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    if 'VoiceChanger' in d['name']:
        print(f'    [{i}] {d[\"name\"]}  ✓')
" 2>/dev/null || echo "    (not found — check PipeWire status)"

pactl list-sinks 2>/dev/null | grep -q "VoiceChanger" && \
    echo "  PulseAudio sink: VoiceChanger  ✓" || \
    echo "  PulseAudio sink: VoiceChanger  ✗ (check: pactl info)"

echo ""
info "${BOLD}Setup complete!${NC}"
echo ""
echo "  ── Next steps ──"
echo "  1. Set your API key:"
echo "       export ELEVENLABS_API_KEY=\"sk-...\""
echo ""
echo "  2. If using Bluetooth earbuds, switch to headset mode:"
echo "       pactl set-card-profile bluez_card.A4_40_3E_11_20_FE headset-head-unit"
echo ""
echo "  3. Run the converter:"
echo "       python3 voice_converter.py"
echo ""
echo "  4. Select 'VoiceChanger' as your microphone in:"
echo "       • WhatsApp Desktop:  Settings → Audio → Microphone"
echo "       • Telegram Desktop:  Settings → Advanced → Microphone"
echo "       • Linphone:         Preferences → Audio → Capture device"
echo ""
echo "  Done."