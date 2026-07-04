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
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

# We reuse ElevenLabsSTS from the main converter
sys.path.insert(0, str(Path(__file__).parent))
from voice_converter import (
    ElevenLabsSTS,
    VoiceSettings,
    VOICE_PRESETS,
    OUTPUT_FMT,
    STS_MODEL,
    LATENCY_OPT,
    pulse_name,
    default_source,
    VIRTUAL_SINK_NAME,
)

TEMP_DIR = Path(tempfile.gettempdir()) / "voice_note"
TEMP_RAW = TEMP_DIR / "capture.raw"
TEMP_CONV = TEMP_DIR / "converted.raw"
CAPTURE_RATE = 16000  # ElevenLabs input rate
OUTPUT_RATE = int(OUTPUT_FMT.replace("pcm_", "")) if OUTPUT_FMT.startswith("pcm_") else 24000

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
    text: str = ""  # For TTS entries, the input text
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
    """Persistent history of generated voice notes — supports replay and regenerate."""

    def __init__(self, file_path: Optional[Path] = None):
        self._file_path = file_path or HISTORY_FILE
        self.entries: list[HistoryEntry] = []
        self._next_id = 1
        self._load()

    def _load(self):
        fp = self._file_path
        if fp.exists():
            try:
                data = json.loads(fp.read_text())
                self.entries = [HistoryEntry.from_dict(e) for e in data.get("entries", [])]
                self._next_id = data.get("next_id", max((e.id for e in self.entries), default=0) + 1)
            except Exception:
                self.entries = []
                self._next_id = 1

    def _save(self):
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"next_id": self._next_id, "entries": [e.to_dict() for e in self.entries]}
        self._file_path.write_text(json.dumps(data, indent=2))

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


def convert(api_key: str, voice_id: str, input_path: Path, output_path: Path,
            voice_settings: Optional[VoiceSettings] = None) -> Path:
    """Send raw PCM to ElevenLabs STS, save converted audio."""
    print(f"🔄  Sending to ElevenLabs ({voice_id})...", flush=True)
    if voice_settings:
        print(f"     Settings: {voice_settings.display()}", flush=True)
    eleven = ElevenLabsSTS(api_key, voice_settings=voice_settings)
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


def replay(sink: str, path: Path, label: str = "", rate: int = OUTPUT_RATE):
    """Replay a previously saved WAV file through the VoiceChanger sink with countdown."""
    if not path or not path.exists():
        print("   ⚠️  File not found", flush=True)
        return

    pcm_rate = rate or OUTPUT_RATE
    raw_path = path
    if path.suffix == ".wav":
        # Convert WAV to raw PCM
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
        description="Voice Note Converter — record, convert, play, replay, recapture"
    )
    p.add_argument("--voice-id", required=True, help="ElevenLabs Voice ID")
    p.add_argument("--api-key", help="API key (or set ELEVENLABS_API_KEY)")
    p.add_argument("--input", help="Input audio file (WAV/MP3/etc) to convert")
    p.add_argument("--output", help="Output file path (default: auto)")
    p.add_argument("--source", help="PulseAudio source (default: auto-detect)")
    p.add_argument("--sink", default="VoiceChanger",
                   help="PulseAudio sink for playback (default: VoiceChanger)")
    # Voice settings
    vs_group = p.add_argument_group("Voice settings")
    vs_group.add_argument("--stability", type=float, default=0.30,
                          help="Voice stability 0-1 (0=expressive, 1=robotic) (default: 0.3)")
    vs_group.add_argument("--similarity-boost", type=float, default=0.95,
                          help="Similarity boost 0-1 (0=unique, 1=tight clone) (default: 0.95)")
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
                          help="Apply a voice settings preset (overrides individual settings)")
    args = p.parse_args()

    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("Set ELEVENLABS_API_KEY or pass --api-key")
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
    print(f"🎛  Voice:  {voice_settings.display()}")

    eleven = ElevenLabsSTS(api_key, voice_settings=voice_settings)
    history = SessionHistory()

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

        convert(api_key, args.voice_id, raw_path, out_path, voice_settings)
        wav = raw_to_wav(out_path, OUTPUT_RATE)
        notes_dir = Path.home() / "VoiceNotes"
        notes_dir.mkdir(exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        final_path = notes_dir / f"converted_{ts}.wav"
        import shutil
        shutil.copy2(wav, final_path)
        print(f"   💾  Saved: {final_path}\n")

        # Add to history
        history.add(HistoryEntry(
            id=0, type="sts", timestamp=ts,
            voice_id=args.voice_id, voice_name=args.voice_id,
            duration_secs=wav.stat().st_size // (OUTPUT_RATE * 2),
            file_path=str(final_path),
            stability=voice_settings.stability,
            similarity_boost=voice_settings.similarity_boost,
            style_exaggeration=voice_settings.style_exaggeration,
            speaker_boost=voice_settings.speaker_boost,
        ))

        play_for_telegram(sink, out_path, rate=OUTPUT_RATE)
        return

    # ── Interactive record mode ────────────────────────────────────────
    print("\n╔══════════════════════════════════════════╗")
    print("║     Voice Note Converter                 ║")
    print("║                                          ║")
    print("║  Commands:                               ║")
    print("║    R        — Record & Convert           ║")
    print("║    P        — Play converted result      ║")
    print("║    H        — History (list all)         ║")
    print("║    R#       — Replay entry #             ║")
    print("║    G#       — Regenerate entry #         ║")
    print("║    D#       — Delete entry #             ║")
    print("║    L# <lbl> — Label entry #              ║")
    print("║    Q        — Quit                       ║")
    print("╚══════════════════════════════════════════╝")

    current_recording: Path | None = None
    current_converted: Path | None = None

    while True:
        try:
            cmd = input("\n❯ ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        lower = cmd.lower()

        # ── Record ──
        if lower == "r":
            current_recording = record(source)
            if current_recording and current_recording.exists() and current_recording.stat().st_size > 100:
                convert(api_key, args.voice_id, current_recording, TEMP_CONV, voice_settings)
                current_converted = TEMP_CONV if TEMP_CONV.exists() else None

                # Save WAV and add to history
                if current_converted:
                    wav = raw_to_wav(current_converted, OUTPUT_RATE)
                    notes_dir = Path.home() / "VoiceNotes"
                    notes_dir.mkdir(exist_ok=True)
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    final_path = notes_dir / f"converted_{ts}.wav"
                    import shutil
                    shutil.copy2(wav, final_path)
                    history.add(HistoryEntry(
                        id=0, type="sts", timestamp=ts,
                        voice_id=args.voice_id, voice_name=args.voice_id,
                        duration_secs=final_path.stat().st_size // (OUTPUT_RATE * 2),
                        file_path=str(final_path),
                        stability=voice_settings.stability,
                        similarity_boost=voice_settings.similarity_boost,
                        style_exaggeration=voice_settings.style_exaggeration,
                        speaker_boost=voice_settings.speaker_boost,
                    ))
            else:
                print("   ⚠️  Recording too short, skipping conversion")

        # ── Play last ──
        elif lower == "p":
            if current_converted:
                play_for_telegram(sink, current_converted, rate=OUTPUT_RATE)
            else:
                print("   ⚠️  No converted audio yet. Record first (R)")

        # ── History ──
        elif lower == "h":
            entries = history.list()
            if not entries:
                print("   📭  No history yet")
            else:
                print(f"\n  ── History ({len(entries)} entries) ──")
                for e in reversed(entries):
                    print(e.display())

        # ── Replay ──
        elif lower.startswith("r") and len(lower) > 1:
            try:
                eid = int(lower[1:])
                entry = history.get(eid)
                if entry:
                    replay(sink, Path(entry.file_path), label=entry.label or f"Entry #{eid}")
                else:
                    print(f"   ⚠️  No entry #{eid}")
            except ValueError:
                print(f"   ⚠️  Usage: R#  (e.g. R3 to replay entry 3)")

        # ── Regenerate ──
        elif lower.startswith("g") and len(lower) > 1:
            try:
                eid = int(lower[1:])
                entry = history.get(eid)
                if not entry:
                    print(f"   ⚠️  No entry #{eid}")
                    continue
                if entry.type != "sts":
                    print(f"   ⚠️  Entry #{eid} is a TTS entry, use from tts_voice_note.py")
                    continue
                # Re-record and convert with current settings
                print(f"\n   🔄  Regenerating entry #{eid} with {voice_settings.display()}")
                new_rec = record(source)
                if new_rec and new_rec.exists() and new_rec.stat().st_size > 100:
                    new_conv = TEMP_DIR / f"regenerated_{eid}.raw"
                    convert(api_key, entry.voice_id, new_rec, new_conv, voice_settings)
                    wav = raw_to_wav(new_conv, OUTPUT_RATE)
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    final_path = Path.home() / "VoiceNotes" / f"regenerated_{eid}_{ts}.wav"
                    import shutil
                    shutil.copy2(wav, final_path)
                    history.add(HistoryEntry(
                        id=0, type="sts", timestamp=ts,
                        voice_id=entry.voice_id, voice_name=entry.voice_id,
                        duration_secs=final_path.stat().st_size // (OUTPUT_RATE * 2),
                        file_path=str(final_path),
                        label=f"regenerated from #{eid}",
                        stability=voice_settings.stability,
                        similarity_boost=voice_settings.similarity_boost,
                        style_exaggeration=voice_settings.style_exaggeration,
                        speaker_boost=voice_settings.speaker_boost,
                    ))
                    print(f"   ✅  Regenerated — use R{history.last().id} to replay\n")
            except ValueError:
                print(f"   ⚠️  Usage: G#  (e.g. G3 to regenerate entry 3)")

        # ── Delete ──
        elif lower.startswith("d") and len(lower) > 1:
            try:
                eid = int(lower[1:])
                if history.delete(eid):
                    print(f"   🗑  Deleted entry #{eid}")
                else:
                    print(f"   ⚠️  No entry #{eid}")
            except ValueError:
                print(f"   ⚠️  Usage: D#  (e.g. D3 to delete entry 3)")

        # ── Label ──
        elif lower.startswith("l") and len(lower) > 1:
            try:
                parts = cmd[1:].strip().split(" ", 1)
                eid = int(parts[0])
                label = parts[1] if len(parts) > 1 else ""
                if label:
                    if history.rename(eid, label):
                        print(f"   🏷  Labeled entry #{eid}: {label}")
                    else:
                        print(f"   ⚠️  No entry #{eid}")
                else:
                    print(f"   ⚠️  Usage: L# <label>  (e.g. L3 my greeting)")
            except ValueError:
                print(f"   ⚠️  Usage: L# <label>")

        elif lower == "q":
            break

    TEMP_RAW.unlink(missing_ok=True)
    TEMP_CONV.unlink(missing_ok=True)
    print("👋  Done")


if __name__ == "__main__":
    main()