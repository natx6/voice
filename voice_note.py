#!/usr/bin/env python3
"""
ElevenLabs Voice Note Converter
=================================
Designed specifically for Telegram/WhatsApp voice notes.
Record → Convert → Play — no real-time streaming, maximum quality.

Usage:
  export ELEVENLABS_API_KEY="sk_..."

  # Record a voice note, convert it, play it back
  python3 voice_note.py --voice-id FGY2WhTYpPnrIDTdsKH5

  # Convert an existing audio file
  python3 voice_note.py --voice-id EXAVITQu4vr4xnSDxMaL --input recording.wav --output converted.wav

Controls during recording:
  R  Start/stop recording
  P  Play converted result
  Q  Quit
"""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# We reuse ElevenLabsSTS from the main converter
sys.path.insert(0, str(Path(__file__).parent))
from voice_converter import (
    ElevenLabsSTS,
    OUTPUT_FMT,
    STS_MODEL,
    LATENCY_OPT,
    VOICE_SETTINGS_JSON,
    pulse_name,
    default_source,
    VIRTUAL_SINK_NAME,
)

TEMP_DIR = Path(tempfile.gettempdir()) / "voice_note"
TEMP_RAW = TEMP_DIR / "capture.raw"
TEMP_CONV = TEMP_DIR / "converted.raw"
CAPTURE_RATE = 16000  # ElevenLabs input rate
# Derive output rate from the format string (e.g. "pcm_24000" → 24000)
OUTPUT_RATE = int(OUTPUT_FMT.replace("pcm_", "")) if OUTPUT_FMT.startswith("pcm_") else 24000


def ensure_temp():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def record(source: str, duration: float = 0) -> Path:
    """Record PCM audio from PulseAudio source.
    If duration <= 0, record until Ctrl+C or 'q' is pressed.
    """
    ensure_temp()
    TEMP_RAW.unlink(missing_ok=True)

    cmd = [
        "parec",
        "--raw",
        f"--rate={CAPTURE_RATE}",
        "--format=s16le",
        "--channels=1",
        f"--device={source}",
    ]

    print(f"\n🎙️  Recording... (press Q then Enter to stop)", flush=True)
    print(f"   Speak clearly — this will be sent as one complete segment\n", flush=True)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=2**20)
    start = time.monotonic()

    try:
        with open(TEMP_RAW, "wb") as f:
            buf = bytearray()
            while True:
                chunk = proc.stdout.read(16000)  # 1s chunks
                if not chunk:
                    break
                f.write(chunk)
                buf.extend(chunk)
                elapsed = time.monotonic() - start
                secs = len(buf) // (CAPTURE_RATE * 2)
                print(f"\r   ⏺  {secs}s recorded — {elapsed:.0f}s elapsed", end="", flush=True)
                if duration > 0 and secs >= duration:
                    break
                # Check for user input to stop
                if _check_stop():
                    break
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait()

    elapsed = time.monotonic() - start
    size = TEMP_RAW.stat().st_size if TEMP_RAW.exists() else 0
    secs = size // (CAPTURE_RATE * 2)
    print(f"\n   ✅  Recorded {secs}s ({size/1024:.0f} KB) in {elapsed:.1f}s\n")
    return TEMP_RAW


def _check_stop() -> bool:
    """Check stdin for 'q' input non-blocking."""
    import select
    if select.select([sys.stdin], [], [], 0.1)[0]:
        line = sys.stdin.readline().strip().lower()
        return line == "q"
    return False


def convert(api_key: str, voice_id: str, input_path: Path, output_path: Path) -> Path:
    """Send raw PCM to ElevenLabs STS, save converted audio."""
    print(f"🔄  Sending to ElevenLabs ({voice_id})...", flush=True)
    eleven = ElevenLabsSTS(api_key)
    raw = input_path.read_bytes()
    print(f"   Input: {len(raw)} bytes ({len(raw) // (CAPTURE_RATE * 2)}s at {CAPTURE_RATE}Hz)", flush=True)

    t0 = time.monotonic()
    try:
        chunks = []
        for chunk in eleven.convert_stream(raw, voice_id):
            chunks.append(chunk)
        elapsed = time.monotonic() - t0
        data = b"".join(chunks)
        output_path.write_bytes(data)
        out_secs = len(data) // (OUTPUT_RATE * 2)
        print(f"   ✅  Converted in {elapsed:.1f}s — {out_secs}s at {OUTPUT_RATE}Hz ({len(data)/1024:.0f} KB)", flush=True)
        return output_path
    except Exception as exc:
        print(f"   ❌  Error: {exc}", flush=True)
        raise


def raw_to_wav(raw_path: Path, rate: int = OUTPUT_RATE) -> Path:
    """Wrap raw PCM in a WAV header so it plays anywhere."""
    wav_path = raw_path.with_suffix(".wav")
    import struct
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


def play_for_telegram(sink: str, path: Path, rate: int = OUTPUT_RATE):
    """Play converted audio through VoiceChanger WITH a countdown.
    The user should start Telegram recording during the countdown.
    Also saves the WAV file to ~/VoiceNotes/ for later use.
    """
    if not path or not path.exists():
        print("   ⚠️  Nothing to play", flush=True)
        return

    pcm_rate = rate or OUTPUT_RATE
    secs = path.stat().st_size // (pcm_rate * 2)

    # Save WAV for later use (at the correct output sample rate)
    notes_dir = Path.home() / "VoiceNotes"
    notes_dir.mkdir(exist_ok=True)
    wav_path = raw_to_wav(path, pcm_rate)
    ts = time.strftime("%Y%m%d_%H%M%S")
    final_path = notes_dir / f"converted_{ts}.wav"
    import shutil
    shutil.copy2(wav_path, final_path)
    print(f"\n   💾  Saved: {final_path}", flush=True)

    # Countdown so user can start Telegram recording
    print(f"\n   🎯  Now open Telegram and START RECORDING a voice note")
    print(f"       (the converted audio will play below in 3 seconds)\n", flush=True)
    for i in [3, 2, 1]:
        print(f"       {i}...", flush=True)
        time.sleep(1)

    # Play through VoiceChanger (Telegram captures from its monitor)
    print(f"   ▶  Playing {secs}s through {sink}...", flush=True)
    subprocess.run(
        ["paplay", "--raw", f"--rate={pcm_rate}", "--format=s16le",
         "--channels=1", f"--device={sink}", str(path)],
        check=True,
    )
    print(f"   ✅  Done — check your Telegram voice note!\n", flush=True)


def file_to_raw(input_path: Path, output_path: Path) -> Path:
    """Convert any audio file to raw PCM mono using ffmpeg."""
    print(f"   Converting {input_path} to raw PCM...", flush=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path),
         "-acodec", "pcm_s16le", "-ar", str(CAPTURE_RATE), "-ac", "1",
         "-f", "s16le", str(output_path)],
        check=True, capture_output=True,
    )
    return output_path


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Voice Note Converter — record, convert, play"
    )
    p.add_argument("--voice-id", required=True, help="ElevenLabs Voice ID")
    p.add_argument("--api-key", help="API key (or set ELEVENLABS_API_KEY)")
    p.add_argument("--input", help="Input audio file (WAV/MP3/etc) to convert")
    p.add_argument("--output", help="Output file path (default: auto)")
    p.add_argument("--source", help="PulseAudio source (default: auto-detect)")
    p.add_argument("--sink", default="VoiceChanger",
                   help="PulseAudio sink for playback (default: VoiceChanger)")
    args = p.parse_args()

    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("Set ELEVENLABS_API_KEY or pass --api-key")
        sys.exit(1)

    # Resolve source
    source = args.source
    if source:
        resolved = pulse_name(source, "input")
        source = resolved or source
    else:
        source = default_source()
    print(f"🎤  Source: {source}")

    # Resolve sink
    sink = args.sink
    resolved = pulse_name(sink, "output")
    sink = resolved or sink
    print(f"🔊  Sink:   {sink}")

    eleven = ElevenLabsSTS(api_key)

    # ── File mode ──────────────────────────────────────────────────────
    if args.input:
        in_path = Path(args.input)
        if not in_path.exists():
            print(f"File not found: {in_path}")
            sys.exit(1)

        out_path = args.output
        if out_path:
            out_path = Path(out_path)
        else:
            out_path = TEMP_DIR / f"converted_{in_path.stem}.raw"

        if in_path.suffix not in (".raw", ".pcm"):
            raw_path = TEMP_DIR / "input_converted.raw"
            file_to_raw(in_path, raw_path)
        else:
            raw_path = in_path

        convert(api_key, args.voice_id, raw_path, out_path)
        wav = raw_to_wav(out_path, OUTPUT_RATE)
        import shutil
        notes_dir = Path.home() / "VoiceNotes"
        notes_dir.mkdir(exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        shutil.copy2(wav, notes_dir / f"converted_{ts}.wav")
        print(f"   💾  Saved: {notes_dir}/converted_{ts}.wav\n")
        play_for_telegram(sink, out_path, rate=OUTPUT_RATE)
        return

    # ── Interactive record mode ────────────────────────────────────────
    print("\n╔══════════════════════════════════════════╗")
    print("║     Voice Note Converter                 ║")
    print("║                                          ║")
    print("║  Commands:                               ║")
    print("║    R + Enter — Start/Stop recording      ║")
    print("║    P + Enter — Play converted result     ║")
    print("║    Q + Enter — Quit                      ║")
    print("╚══════════════════════════════════════════╝")

    current_recording: Path | None = None
    current_converted: Path | None = None

    while True:
        try:
            cmd = input("\n❯ ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if cmd == "r":
            # Toggle recording
            current_recording = record(source)
            if current_recording and current_recording.exists() and current_recording.stat().st_size > 100:
                convert(api_key, args.voice_id, current_recording, TEMP_CONV)
                current_converted = TEMP_CONV if TEMP_CONV.exists() else None
            else:
                print("   ⚠️  Recording too short, skipping conversion")

        elif cmd == "p":
            if current_converted:
                play_for_telegram(sink, current_converted, rate=OUTPUT_RATE)
            else:
                print("   ⚠️  No converted audio yet. Record first (R)")

        elif cmd == "q":
            break

    TEMP_RAW.unlink(missing_ok=True)
    TEMP_CONV.unlink(missing_ok=True)
    print("👋  Done")


if __name__ == "__main__":
    main()