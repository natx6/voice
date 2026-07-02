#!/usr/bin/env python3
"""
ElevenLabs TTS Voice Note Generator
=====================================
Type a message → ElevenLabs TTS generates it in a target voice →
Plays through VoiceChanger → Telegram captures it.

Now with: voice settings, session history, replay, and recapture.

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
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Iterator, Optional

# ---- Reuse helpers from voice_converter ----
sys.path.insert(0, str(Path(__file__).parent))
from voice_converter import pulse_name, VIRTUAL_SINK_NAME, VoiceSettings, VOICE_PRESETS

TEMP_DIR = Path(tempfile.gettempdir()) / "tts_voice_note"
TEMP_CONV = TEMP_DIR / "tts_output.raw"
OUTPUT_RATE = 24000  # Hz
MODEL_ID = "eleven_turbo_v2_5"
OUTPUT_FMT = "pcm_24000"

# ── Session History ────────────────────────────────────────────────────────
HISTORY_DIR = Path.home() / ".voice_history"
HISTORY_FILE = HISTORY_DIR / "history.json"


@dataclass
class HistoryEntry:
    id: int
    type: str  # "sts" or "tts"
    timestamp: str
    voice_id: str
    voice_name: str
    duration_secs: float
    file_path: str
    text: str = ""
    label: str = ""
    stability: float = 0.30
    similarity_boost: float = 0.95
    style_exaggeration: float = 0.0
    speaker_boost: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    def display(self) -> str:
        tag = f" [{self.label}]" if self.label else ""
        prefix = "📝" if self.type == "tts" else "🎙"
        text_preview = (self.text[:40] + "...") if self.text else ""
        return (
            f"  {self.id:3d}. {prefix}  {self.timestamp}  "
            f"{self.voice_name:<20s}  {self.duration_secs:3.0f}s  "
            f"S={self.stability:.2f}/B={self.similarity_boost:.2f}{tag}"
            f"{'  ' + text_preview if text_preview else ''}"
        )


class SessionHistory:
    def __init__(self):
        self.entries: list[HistoryEntry] = []
        self._next_id = 1
        self._load()

    def _load(self):
        if HISTORY_FILE.exists():
            try:
                data = json.loads(HISTORY_FILE.read_text())
                self.entries = [HistoryEntry.from_dict(e) for e in data.get("entries", [])]
                self._next_id = data.get("next_id", max((e.id for e in self.entries), default=0) + 1)
            except Exception:
                self.entries = []
                self._next_id = 1

    def _save(self):
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        data = {"next_id": self._next_id, "entries": [e.to_dict() for e in self.entries]}
        HISTORY_FILE.write_text(json.dumps(data, indent=2))

    def add(self, entry: HistoryEntry) -> int:
        entry.id = self._next_id
        self._next_id += 1
        self.entries.append(entry)
        self._save()
        return entry.id

    def get(self, entry_id: int) -> Optional[HistoryEntry]:
        for e in self.entries:
            if e.id == entry_id:
                return e
        return None

    def delete(self, entry_id: int) -> bool:
        for i, e in enumerate(self.entries):
            if e.id == entry_id:
                path = Path(e.file_path)
                if path.exists():
                    path.unlink()
                del self.entries[i]
                self._save()
                return True
        return False

    def list(self) -> list[HistoryEntry]:
        return list(self.entries)

    def rename(self, entry_id: int, label: str) -> bool:
        entry = self.get(entry_id)
        if entry:
            entry.label = label
            self._save()
            return True
        return False

    def last(self) -> Optional[HistoryEntry]:
        return self.entries[-1] if self.entries else None


# ---- ElevenLabs TTS ----
def tts_stream(api_key: str, voice_id: str, text: str,
               voice_settings: Optional[VoiceSettings] = None) -> Iterator[bytes]:
    """Stream TTS audio from ElevenLabs. Yields raw PCM chunks."""
    from elevenlabs import ElevenLabs, VoiceSettings as ELVoiceSettings
    client = ElevenLabs(api_key=api_key)
    vs = voice_settings or VoiceSettings()
    # ElevenLabs SDK expects a VoiceSettings object for TTS
    el_vs = ELVoiceSettings(
        stability=vs.stability,
        similarity_boost=vs.similarity_boost,
        style=vs.style_exaggeration if vs.style_exaggeration > 0 else None,
        use_speaker_boost=vs.speaker_boost if vs.speaker_boost else None,
        speed=vs.speed,
    )
    return client.text_to_speech.stream(
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        output_format=OUTPUT_FMT,
        optimize_streaming_latency=4,
        voice_settings=el_vs,
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


def replay(sink: str, path: Path, label: str = "", rate: int = OUTPUT_RATE):
    """Replay a previously saved file through the VoiceChanger sink with countdown."""
    if not path or not path.exists():
        print("   ⚠️  File not found", flush=True)
        return

    pcm_rate = rate or OUTPUT_RATE
    raw_path = path
    if path.suffix == ".wav":
        raw_path = TEMP_DIR / "replay_temp.raw"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(path),
             "-acodec", "pcm_s16le", "-ar", str(pcm_rate), "-ac", "1",
             "-f", "s16le", str(raw_path)],
            check=True, capture_output=True,
        )

    secs = raw_path.stat().st_size // (pcm_rate * 2)
    header = f"   🎯  Replaying: {label}" if label else "   🎯  Replaying"
    print(f"\n{header}")
    print(f"       Open Telegram and START RECORDING a voice note")
    print(f"       (audio plays in 3 seconds)\n", flush=True)
    for i in [3, 2, 1]:
        print(f"       {i}...", flush=True)
        time.sleep(1)

    print(f"   ▶  Playing {secs}s through {sink}...", flush=True)
    subprocess.run(
        ["paplay", "--raw", f"--rate={pcm_rate}", "--format=s16le",
         "--channels=1", f"--device={sink}", str(raw_path)],
        check=True,
    )
    print(f"   ✅  Done — check your voice note!\n", flush=True)
    TEMP_DIR.joinpath("replay_temp.raw").unlink(missing_ok=True)


def generate_and_play(api_key: str, voice_id: str, text: str, sink: str,
                       voice_settings: Optional[VoiceSettings] = None):
    """Send text to TTS, save audio, play through VoiceChanger."""
    vs = voice_settings or VoiceSettings()
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
        print("\r" + " " * 50 + "\r", end="", flush=True)

    spinner_thread = threading.Thread(target=_spin, daemon=True)
    spinner_thread.start()

    t0 = time.monotonic()
    try:
        chunks = list(tts_stream(api_key, voice_id, text, vs))
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
    print(f"   🎛  Settings: {vs.display()}", flush=True)

    # Save as WAV
    notes_dir = Path.home() / "VoiceNotes"
    notes_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    wav_path = raw_to_wav(TEMP_CONV, OUTPUT_RATE)
    final_path = notes_dir / f"tts_{ts}.wav"
    shutil.copy2(wav_path, final_path)
    print(f"   💾  Saved: {final_path}", flush=True)

    # Play through VoiceChanger — user controls when
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
    # Voice settings
    vs_group = p.add_argument_group("Voice settings")
    vs_group.add_argument("--stability", type=float, default=0.35,
                          help="Voice stability 0-1 (default: 0.35)")
    vs_group.add_argument("--similarity-boost", type=float, default=0.95,
                          help="Similarity boost 0-1 (default: 0.95)")
    vs_group.add_argument("--style-exaggeration", type=float, default=0.0,
                          help="Style exaggeration 0-1 (default: 0)")
    vs_group.add_argument("--speaker-boost", action="store_true",
                          help="Enable speaker boost")
    vs_group.add_argument("--speed", type=float, default=1.0,
                          help="Playback speed 0.5-2.0 (1.0 = normal) (default: 1.0)")
    vs_group.add_argument("--character",
                          choices=VoiceSettings.CHARACTER_OPTIONS, default="studio",
                          help="Audio character/filter (default: studio)")
    vs_group.add_argument("--voice-preset",
                          choices=list(VOICE_PRESETS.keys()),
                          help="Apply a voice settings preset")
    args = p.parse_args()

    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("Set ELEVENLABS_API_KEY")
        sys.exit(1)

    # Resolve voice settings
    if args.voice_preset:
        voice_settings = VOICE_PRESETS[args.voice_preset]
    else:
        voice_settings = VoiceSettings(
            stability=args.stability,
            similarity_boost=args.similarity_boost,
            style_exaggeration=args.style_exaggeration,
            speaker_boost=args.speaker_boost,
            speed=args.speed,
            character=args.character,
        )

    sink = pulse_name(args.sink, "output") or args.sink
    print(f"🔊  Output: {sink}")
    print(f"🎛  Voice:  {voice_settings.display()}")

    history = SessionHistory()

    print("\n╔══════════════════════════════════════════╗")
    print("║     TTS Voice Note Generator             ║")
    print("║                                          ║")
    print("║  Type a message → it speaks in the       ║")
    print("║  target voice → Telegram captures it.    ║")
    print("║                                          ║")
    print("║  Commands:                               ║")
    print("║    S          — Submit/generate TTS       ║")
    print("║    H          — History (list all)        ║")
    print("║    R#         — Replay entry #            ║")
    print("║    G#         — Regenerate entry #        ║")
    print("║    D#         — Delete entry #            ║")
    print("║    L# <label> — Label entry #             ║")
    print("║    Q          — Quit                      ║")
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

                # History command
                if check == "h":
                    entries = history.list()
                    if not entries:
                        print("   📭  No history yet")
                    else:
                        print(f"\n  ── History ({len(entries)} entries) ──")
                        for e in reversed(entries):
                            print(e.display())
                    continue

                # Replay command
                if check.startswith("r") and len(check) > 1:
                    try:
                        eid = int(check[1:])
                        entry = history.get(eid)
                        if entry:
                            replay(sink, Path(entry.file_path), label=entry.label or f"Entry #{eid}")
                        else:
                            print(f"   ⚠️  No entry #{eid}")
                    except ValueError:
                        print(f"   ⚠️  Usage: R#  (e.g. R3)")
                    continue

                # Regenerate command
                if check.startswith("g") and len(check) > 1:
                    try:
                        eid = int(check[1:])
                        entry = history.get(eid)
                        if not entry:
                            print(f"   ⚠️  No entry #{eid}")
                            continue
                        if not entry.text:
                            print(f"   ⚠️  Entry #{eid} has no saved text to regenerate from")
                            continue
                        print(f"\n   🔄  Regenerating entry #{eid} with {voice_settings.display()}")
                        generate_and_play(api_key, entry.voice_id, entry.text, sink, voice_settings)
                        # Add to history (the generated file was saved by generate_and_play)
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        wav_path = raw_to_wav(TEMP_CONV, OUTPUT_RATE)
                        final_path = Path.home() / "VoiceNotes" / f"tts_{ts}.wav"
                        shutil.copy2(wav_path, final_path)
                        history.add(HistoryEntry(
                            id=0, type="tts", timestamp=ts,
                            voice_id=entry.voice_id, voice_name=entry.voice_id,
                            duration_secs=final_path.stat().st_size // (OUTPUT_RATE * 2),
                            file_path=str(final_path),
                            text=entry.text,
                            label=f"regenerated from #{eid}",
                            stability=voice_settings.stability,
                            similarity_boost=voice_settings.similarity_boost,
                            style_exaggeration=voice_settings.style_exaggeration,
                            speaker_boost=voice_settings.speaker_boost,
                        ))
                        print(f"   ✅  Regenerated — use R{history.last().id} to replay\n")
                    except ValueError:
                        print(f"   ⚠️  Usage: G#")
                    continue

                # Delete command
                if check.startswith("d") and len(check) > 1:
                    try:
                        eid = int(check[1:])
                        if history.delete(eid):
                            print(f"   🗑  Deleted entry #{eid}")
                        else:
                            print(f"   ⚠️  No entry #{eid}")
                    except ValueError:
                        print(f"   ⚠️  Usage: D#")
                    continue

                # Label command
                if check.startswith("l") and len(check) > 1:
                    try:
                        parts = raw[1:].strip().split(" ", 1)
                        eid = int(parts[0])
                        label = parts[1] if len(parts) > 1 else ""
                        if label:
                            if history.rename(eid, label):
                                print(f"   🏷  Labeled entry #{eid}: {label}")
                            else:
                                print(f"   ⚠️  No entry #{eid}")
                        else:
                            print(f"   ⚠️  Usage: L# <label>")
                    except ValueError:
                        print(f"   ⚠️  Usage: L# <label>")
                    continue

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
        generate_and_play(api_key, args.voice_id, text, sink, voice_settings)

        # Add to history
        ts = time.strftime("%Y%m%d_%H%M%S")
        wav_path = raw_to_wav(TEMP_CONV, OUTPUT_RATE)
        final_path = Path.home() / "VoiceNotes" / f"tts_{ts}.wav"
        shutil.copy2(wav_path, final_path)
        history.add(HistoryEntry(
            id=0, type="tts", timestamp=ts,
            voice_id=args.voice_id, voice_name=args.voice_id,
            duration_secs=final_path.stat().st_size // (OUTPUT_RATE * 2),
            file_path=str(final_path),
            text=text,
            stability=voice_settings.stability,
            similarity_boost=voice_settings.similarity_boost,
            style_exaggeration=voice_settings.style_exaggeration,
            speaker_boost=voice_settings.speaker_boost,
        ))

    print("👋  Done")


if __name__ == "__main__":
    main()
