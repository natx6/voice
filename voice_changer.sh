#!/usr/bin/env bash
# Launch the ElevenLabs Voice Changer TUI
set -euo pipefail

API_KEY="${ELEVENLABS_API_KEY:-}"
if [ -z "$API_KEY" ]; then
    echo "Set ELEVENLABS_API_KEY or pass via --api-key"
    exit 1
fi

cd "$(dirname "$0")"
exec python3 voice_changer_tui.py "$@"