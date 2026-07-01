#!/usr/bin/env python3
"""
ElevenLabs TTS Voice Note Generator
=====================================
Type a message → ElevenLabs TTS generates it in a female voice →
Plays through VoiceChanger → Telegram captures it.

No original voice bleed-through. 100% synthesized in the target voice.

Usage:
  export ELEVENLABS_API_KEY="sk_..."
  python3 tts_voice_note.py --voice-id EXAVITQu4vr4xnSDxMaL
"""

import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Iterator

# ---- Reuse helpers from voice_converter ----
sys.path.insert(0, str(Path(__file__).parent))
from voice_converter import pulse_name, VIRTUAL_SINK_NAME

TEMP_DIR = Path(tempfile.gettempdir()) / "tts_voice_note"
TEMP_CONV = TEMP_DIR / "tts_output.raw"
OUTPUT_RATE = 24000  # Hz
MODEL_ID = "eleven_turbo_v2_5"
OUTPUT_FMT = "pcm_24000"


# ---- ElevenLabs TTS ----
def tts_stream(api_key: str, voice_id: str, text: str) -> Iterator[bytes]:
    """Stream TTS audio from ElevenLabs. Yields raw PCM chunks."""
    from elevenlabs import ElevenLabs, VoiceSettings
    client = ElevenLabs(api_key=api_key)
    vs = VoiceSettings(stability=0.35, similarity_boost=0.95)
    return client.text_to_speech.stream(
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        output_format=OUTPUT_FMT,
        optimize_streaming_latency=4,
        voice_settings=vs,
    )


# ---- Audio helpers ----
def raw_to_wav(raw_path: Path, rate: int = OUTPUT_RATE) -> Path:
    """Wrap raw PCM in a WAV header."""
    wav_path = raw_path.with_suffix(".wav")
    raw = raw_path.read_bytes()
    n_samples = len(raw) // 2
    data_size = n_samples * 2
    with open(wav_path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(raw)
    return wav_path


def generate_and_play(api_key: str, voice_id: str, text: str, sink: str):
    """Send text to TTS, save audio, play through VoiceChanger."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_CONV.unlink(missing_ok=True)

    # Show a live spinner while generating
    spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    stop_spinner = threading.Event()

    def _spin():
        i = 0
        t0 = time.monotonic()
        while not stop_spinner.is_set():
            elapsed_s = int(time.monotonic() - t0)
            print(f"\r  ⏳  Generating... {spinner[i % len(spinner)]}  ({elapsed_s}s)", end="", flush=True)
            i += 1
            time.sleep(0.15)
        # Clear the spinner line
        print("\r" + " " * 50 + "\r", end="", flush=True)

    spinner_thread = threading.Thread(target=_spin, daemon=True)
    spinner_thread.start()

    t0 = time.monotonic()
    try:
        chunks = list(tts_stream(api_key, voice_id, text))
        elapsed = time.monotonic() - t0
    except Exception as exc:
        stop_spinner.set()
        print(f"\n  ❌  TTS error after {time.monotonic()-t0:.0f}s", flush=True)
        print(f"     {exc}", flush=True)
        return
    finally:
        stop_spinner.set()

    data = b"".join(chunks)
    TEMP_CONV.write_bytes(data)
    secs = len(data) // (OUTPUT_RATE * 2)
    print(f"   ✅  Generated {secs}s in {elapsed:.1f}s", flush=True)

    # Save as WAV
    notes_dir = Path.home() / "VoiceNotes"
    notes_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    wav_path = raw_to_wav(TEMP_CONV, OUTPUT_RATE)
    final_path = notes_dir / f"tts_{ts}.wav"
    shutil.copy2(wav_path, final_path)
    print(f"   💾  Saved: {final_path}", flush=True)

    # Play through VoiceChanger — user controls when
    spinner = "⣾⣽⣻⢿⡿⣟⣯⣷"
    print(f"", flush=True)
    print(f"  ─────────────────────────────────────", flush=True)
    print(f"  ✅  GENERATED — {secs}s of audio ready", flush=True)
    print(f"  ─────────────────────────────────────", flush=True)
    print(f"", flush=True)
    print(f"  📱  Open Telegram and start recording a voice note", flush=True)
    print(f"  ⏎  Then press ENTER here to play through VoiceChanger", flush=True)
    print(f"", flush=True)

    # Flush any leftover stdin before waiting
    import select
    while select.select([sys.stdin], [], [], 0.0)[0]:
        sys.stdin.readline()

    try:
        input(f"  ⏎  Press ENTER to play...")
    except (EOFError, KeyboardInterrupt):
        return

    print(f"\n  ▶️  Playing... (0s / {secs}s)", end="", flush=True)
    start_t = time.monotonic()
    proc = subprocess.Popen(
        ["paplay", "--raw", f"--rate={OUTPUT_RATE}", "--format=s16le",
         "--channels=1", f"--device={sink}", str(TEMP_CONV)],
    )
    # Show elapsed time while playing
    while proc.poll() is None:
        elapsed_p = time.monotonic() - start_t
        print(f"\r  ▶️  Playing... ({elapsed_p:.0f}s / {secs}s) {spinner[int(elapsed_p) % len(spinner)]}", end="", flush=True)
        time.sleep(0.5)
    print(f"\r  ✅  Playback complete ({secs}s)                      ")
    print(f"\n  📱  Now send that voice note in Telegram!\n", flush=True)


# ---- Interactive loop ----
def main():
    p = argparse.ArgumentParser(description="TTS Voice Note Generator")
    p.add_argument("--voice-id", required=True, help="ElevenLabs Voice ID")
    p.add_argument("--api-key", help="API key (or set ELEVENLABS_API_KEY)")
    p.add_argument("--sink", default="VoiceChanger",
                   help="PulseAudio sink (default: VoiceChanger)")
    args = p.parse_args()

    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("Set ELEVENLABS_API_KEY")
        sys.exit(1)

    sink = pulse_name(args.sink, "output") or args.sink
    print(f"🔊  Output: {sink}")

    print("\n╔══════════════════════════════════════════╗")
    print("║     TTS Voice Note Generator             ║")
    print("║                                          ║")
    print("║  Type a message → it speaks in the       ║")
    print("║  target voice → Telegram captures it.    ║")
    print("║                                          ║")
    print("║                                          ║")
    print("║  How to use:                             ║")
    print("║  1. Type/paste your message              ║")
    print("║  2. Type 'S' on a new line to generate     ║")
    print("║  3. Switch to Telegram, start recording  ║")
    print("║  4. Press Enter here to play → send      ║")
    print("║                                          ║")
    print("║  Commands:                               ║")
    print("║    Q + Enter  — Quit                     ║")
    print("╚══════════════════════════════════════════╝")

    while True:
        print("─── New message ───")
        print("  📝  Paste or type your message first, then 'S' to submit.\n")

        lines = []
        try:
            while True:
                prefix = "  📝  " if not lines else "     "
                raw = input(prefix)
                check = raw.strip().lower()

                # Submit
                if check in ("s", "/send", "\\send") and lines:
                    break

                # Discard current
                if check in ("q", "/q") and lines:
                    print("  ⚠️  Discarded.\n")
                    lines = []
                    break

                # Quit
                if check in ("q", "/q") and not lines:
                    print("👋  Done")
                    return

                # Guard
                if check in ("s", "/send") and not lines:
                    print("  ⚠️  Type message first, then 'S'.")
                    continue

                # Accumulate
                lines.append(raw)

        except (EOFError, KeyboardInterrupt):
            break

        if not lines:
            continue

        text = "\n".join(l.rstrip() for l in lines)
        print(f"  📝  {len(text)} chars, ~{len(text)//20}s estimated")
        print(f"  🎯  Generating...")
        generate_and_play(api_key, args.voice_id, text, sink)

    print("👋  Done")


if __name__ == "__main__":
    main()