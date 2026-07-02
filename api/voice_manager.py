"""Voice Manager — wraps existing Python modules for the API backend.

Centralises access to ElevenLabs API, PulseAudio devices, session history,
and audio file management so the FastAPI routes stay thin.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Optional

# Add parent directory so we can import the existing modules
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voice_converter import (
    ElevenLabsSTS, VoiceSettings, VIRTUAL_SINK_NAME,
    pulse_name, default_source, OUTPUT_FMT,
)
from voice_note import SessionHistory as STSHistory, HistoryEntry as STSEntry
from voice_note import record as sts_record
from voice_note import raw_to_wav
from tts_voice_note import SessionHistory as TTSHistory, HistoryEntry as TTSEntry
from tts_voice_note import raw_to_wav as tts_raw_to_wav


log = logging.getLogger("voice_manager")
TEMP_DIR = Path(tempfile.gettempdir()) / "voice_api"
OUTPUT_RATE = int(OUTPUT_FMT.replace("pcm_", "")) if OUTPUT_FMT.startswith("pcm_") else 24000


@dataclass
class PlaybackState:
    """Shared state for tracking active playback."""
    playing: bool = False
    file_path: str = ""
    total_secs: float = 0.0
    started_at: float = 0.0
    mode: str = ""  # "preview" or "capture"
    _lock: threading.Lock = threading.Lock()

    def start(self, file_path: str, total_secs: float, mode: str):
        with self._lock:
            self.playing = True
            self.file_path = file_path
            self.total_secs = total_secs
            self.started_at = time.monotonic()
            self.mode = mode

    def stop(self):
        with self._lock:
            self.playing = False
            self.file_path = ""
            self.total_secs = 0.0
            self.mode = ""

    @property
    def elapsed_secs(self) -> float:
        if not self.playing:
            return 0.0
        with self._lock:
            return time.monotonic() - self.started_at

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "playing": self.playing,
                "file_path": self.file_path,
                "total_secs": self.total_secs,
                "elapsed_secs": time.monotonic() - self.started_at if self.playing else 0.0,
                "progress_pct": round(
                    min(100, (time.monotonic() - self.started_at) / max(0.1, self.total_secs) * 100), 1
                ) if self.playing else 0.0,
                "mode": self.mode,
            }


class VoiceManager:
    """High-level manager for voice operations."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.eleven = ElevenLabsSTS(api_key)
        self.sts_history = STSHistory()
        self.tts_history = TTSHistory()

        # Current recording state
        self._recording_proc: subprocess.Popen | None = None
        self._recording_path: Path | None = None
        self._recording_start: float = 0.0
        self._recording_lock = threading.Lock()
        self._level_listeners: list[Callable[[int], None]] = []

        # Current play state (shared across preview + capture)
        self.play_state = PlaybackState()
        self._play_proc: subprocess.Popen | None = None
        self._play_lock = threading.Lock()

    # ── Device discovery ────────────────────────────────────────────────

    def list_sources(self) -> list[str]:
        try:
            raw = subprocess.check_output(
                ["pactl", "list", "sources", "short"], text=True, timeout=3
            )
            return [line.split("\t")[1] for line in raw.strip().split("\n") if line]
        except Exception:
            return []

    def list_sinks(self) -> list[str]:
        try:
            raw = subprocess.check_output(
                ["pactl", "list", "sinks", "short"], text=True, timeout=3
            )
            return [line.split("\t")[1] for line in raw.strip().split("\n") if line]
        except Exception:
            return []

    def default_source(self) -> str:
        return default_source() or ""

    def resolve_sink(self, name: str = "VoiceChanger") -> str:
        resolved = pulse_name(name, "output")
        return resolved or name

    # ── Voice listing ───────────────────────────────────────────────────

    def list_voices(self) -> list[dict]:
        return self.eleven.list_voices()

    # ── Recording ───────────────────────────────────────────────────────

    def start_recording(self, source: str = "") -> Path:
        """Start recording audio in a background process."""
        with self._recording_lock:
            if self._recording_proc is not None:
                raise RuntimeError("Already recording")

            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            self._recording_path = TEMP_DIR / f"capture_{int(time.time())}.raw"
            self._recording_path.parent.mkdir(parents=True, exist_ok=True)

            src = source or default_source() or "default"
            cmd = [
                "parec", "--raw", "--rate=16000", "--format=s16le",
                "--channels=1", f"--device={src}",
            ]
            self._recording_proc = subprocess.Popen(
                cmd, stdout=open(self._recording_path, "wb"), bufsize=2**20
            )
            self._recording_start = time.monotonic()
            return self._recording_path

    def stop_recording(self) -> dict:
        """Stop recording and return info about the captured audio."""
        with self._recording_lock:
            if self._recording_proc is None:
                raise RuntimeError("Not recording")
            self._recording_proc.terminate()
            self._recording_proc.wait()
            elapsed = time.monotonic() - self._recording_start
            path = self._recording_path
            self._recording_proc = None
            self._recording_path = None

        size = path.stat().st_size if path and path.exists() else 0
        secs = size // (16000 * 2)
        return {
            "file_path": str(path) if path else "",
            "duration_secs": secs,
            "size_bytes": size,
        }

    def is_recording(self) -> bool:
        with self._recording_lock:
            return self._recording_proc is not None

    def add_level_listener(self, listener: Callable[[int], None]):
        self._level_listeners.append(listener)

    def _notify_level(self, level: int):
        for listener in self._level_listeners:
            try:
                listener(level)
            except Exception:
                pass

    # ── Conversion (STS) ────────────────────────────────────────────────

    def convert(self, input_path: str, voice_id: str,
                voice_settings: Optional[VoiceSettings] = None) -> dict:
        """Convert a recording using ElevenLabs STS."""
        vs = voice_settings or VoiceSettings()
        in_path = Path(input_path)
        raw_data = in_path.read_bytes()

        chunks: list[bytes] = []
        for chunk in self.eleven.convert_stream(raw_data, voice_id, vs):
            chunks.append(chunk)
        data = b"".join(chunks)

        # Save output
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        raw_path = TEMP_DIR / f"converted_{ts}.raw"
        raw_path.write_bytes(data)

        # Wrap in WAV
        wav_path = raw_to_wav(raw_path, OUTPUT_RATE)

        # Copy to VoiceNotes
        notes_dir = Path.home() / "VoiceNotes"
        notes_dir.mkdir(exist_ok=True)
        final_path = notes_dir / f"converted_{ts}.wav"
        shutil.copy2(wav_path, final_path)

        secs = len(data) // (OUTPUT_RATE * 2)
        hsecs = len(data) // (OUTPUT_RATE * 2)

        # Add to history
        hid = self.sts_history.add(STSEntry(
            id=0, type="sts", timestamp=ts,
            voice_id=voice_id, voice_name=voice_id,
            duration_secs=hsecs,
            file_path=str(final_path),
            stability=vs.stability,
            similarity_boost=vs.similarity_boost,
            style_exaggeration=vs.style_exaggeration,
            speaker_boost=vs.speaker_boost,
        ))

        return {
            "status": "ok",
            "file_path": str(final_path),
            "raw_file": str(raw_path),
            "duration_secs": hsecs,
            "size_bytes": len(data),
            "history_id": hid,
        }

    # ── TTS ─────────────────────────────────────────────────────────────

    def tts_generate(self, text: str, voice_id: str,
                     voice_settings: Optional[VoiceSettings] = None) -> dict:
        """Generate TTS audio from text."""
        from tts_voice_note import tts_stream
        vs = voice_settings or VoiceSettings()

        chunks = list(tts_stream(self.api_key, voice_id, text, vs))
        data = b"".join(chunks)

        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        raw_path = TEMP_DIR / f"tts_{ts}.raw"
        raw_path.write_bytes(data)

        wav_path = tts_raw_to_wav(raw_path, OUTPUT_RATE)
        notes_dir = Path.home() / "VoiceNotes"
        notes_dir.mkdir(exist_ok=True)
        final_path = notes_dir / f"tts_{ts}.wav"
        shutil.copy2(wav_path, final_path)

        hsecs = len(data) // (OUTPUT_RATE * 2)

        hid = self.tts_history.add(TTSEntry(
            id=0, type="tts", timestamp=ts,
            voice_id=voice_id, voice_name=voice_id,
            duration_secs=hsecs,
            file_path=str(final_path),
            text=text,
            stability=vs.stability,
            similarity_boost=vs.similarity_boost,
            style_exaggeration=vs.style_exaggeration,
            speaker_boost=vs.speaker_boost,
        ))

        return {
            "status": "ok",
            "file_path": str(final_path),
            "raw_file": str(raw_path),
            "duration_secs": hsecs,
            "chars": len(text),
            "history_id": hid,
        }

    # ── Playback ────────────────────────────────────────────────────────

    # ── helpers ─────────────────────────────────────────────────────────

    def _prepare_audio(self, file_path: str, speed: float = 1.0,
                       character: str = "studio") -> tuple[Path, float]:
        """Convert WAV to raw PCM, optionally applying speed + character filters.
        Returns (raw_path, duration_secs).
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        raw_path = TEMP_DIR / "play_temp.raw"
        raw_path.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix == ".wav":
            try:
                # Build ffmpeg filter chain: character first, then speed
                from voice_converter import VoiceSettings as VS
                char_filters = VS(character=character).to_ffmpeg_filters()
                af_parts = list(char_filters)
                if speed != 1.0:
                    af_parts.append(f"atempo={speed}")
                filters = ["-af", ",".join(af_parts)] if af_parts else []
                cmd = ["ffmpeg", "-y", "-i", str(path),
                       "-acodec", "pcm_s16le", "-ar", str(OUTPUT_RATE), "-ac", "1",
                       *filters, "-f", "s16le", str(raw_path)]
                subprocess.run(cmd, check=True, capture_output=True)
            except FileNotFoundError:
                log.warning("ffmpeg not found, stripping WAV header")
                data = path.read_bytes()
                pcm_start = 44
                if len(data) > pcm_start:
                    raw_path.write_bytes(data[pcm_start:])
                else:
                    raise RuntimeError("Cannot parse WAV without ffmpeg")
            except subprocess.CalledProcessError as e:
                log.warning("ffmpeg failed: %s", e.stderr[:200] if e.stderr else "unknown")
                raw_path = path
        else:
            raw_path = path

        if not raw_path or not raw_path.exists():
            raise RuntimeError("Could not prepare audio file for playback")

        secs = raw_path.stat().st_size // (OUTPUT_RATE * 2)
        return raw_path, max(0.1, secs)

    def _spawn_paplay(self, device: str, raw_path: Path) -> subprocess.Popen:
        """Start paplay subprocess for the given device and raw PCM file."""
        return subprocess.Popen(
            ["paplay", "--raw", f"--rate={OUTPUT_RATE}", "--format=s16le",
             "--channels=1", f"--device={device}", str(raw_path)],
        )

    def _approx_duration(self, file_path: str) -> float:
        """Get approximate audio duration from file size without ffmpeg."""
        try:
            size = Path(file_path).stat().st_size
            return max(0.5, (size - 44) / (OUTPUT_RATE * 2)) if size > 44 else 1.0
        except Exception:
            return 1.0

    def _run_with_state(self, file_path: str, sink: str, mode: str,
                        countdown: int = 0, speed: float = 1.0,
                        character: str = "studio"):
        """Run paplay in a thread, tracking progress in play_state."""
        raw_path: Path | None = None
        try:
            # Set playing=true IMMEDIATELY so the frontend poll starts seeing it
            approx = self._approx_duration(file_path) / speed
            self.play_state.start(file_path, approx, mode)

            # Convert WAV → raw PCM with speed + character applied
            raw_path, secs = self._prepare_audio(file_path, speed, character)
            # Update with exact duration now that we know it
            self.play_state.start(file_path, secs, mode)

            if countdown > 0:
                log.info("Capture countdown %ds", countdown)
                time.sleep(countdown)
                if not self.play_state.playing:
                    return

            log.info("Playing %ds audio through %s (%s)", secs, sink, mode)
            proc = self._spawn_paplay(sink, raw_path)
            with self._play_lock:
                self._play_proc = proc

            proc.wait()
            log.info("Playback complete (%s)", mode)
        except Exception as exc:
            log.error("Playback error (%s): %s", mode, exc)
        finally:
            self.play_state.stop()
            with self._play_lock:
                self._play_proc = None
            if raw_path and raw_path != Path(file_path) and raw_path.exists():
                raw_path.unlink(missing_ok=True)

    # ── Public API ─────────────────────────────────────────────────────

    def preview(self, file_path: str, speed: float = 1.0, character: str = "studio"):
        """Play audio through the DEFAULT output (speakers/headphones) for preview.
        No countdown — user just wants to hear it before deciding to capture.
        """
        if self.play_state.playing:
            log.warning("Already playing, stopping previous playback")
            self.stop_playback()

        sink = self._default_sink()

        thread = threading.Thread(
            target=self._run_with_state,
            args=(file_path, sink, "preview"),
            kwargs={"speed": speed, "character": character},
            daemon=True,
        )
        thread.start()

    def capture(self, file_path: str, countdown: int = 3, speed: float = 1.0,
                character: str = "studio"):
        """Play audio through the VoiceChanger sink for Telegram capture.
        Includes a countdown so user can start recording in Telegram.
        """
        if self.play_state.playing:
            log.warning("Already playing, stopping previous playback")
            self.stop_playback()

        sink = self.resolve_sink("VoiceChanger")
        if not sink or "VoiceChanger" not in sink:
            sink = "VoiceChanger"

        thread = threading.Thread(
            target=self._run_with_state,
            args=(file_path, sink, "capture", countdown),
            kwargs={"speed": speed, "character": character},
            daemon=True,
        )
        thread.start()

    def _default_sink(self) -> str:
        try:
            raw = subprocess.check_output(
                ["pactl", "get-default-sink"], text=True, timeout=3
            ).strip()
            return raw or "@DEFAULT_SINK@"
        except Exception:
            return "@DEFAULT_SINK@"

    def stop_playback(self):
        """Stop the current playback immediately."""
        with self._play_lock:
            if self._play_proc and self._play_proc.poll() is None:
                self._play_proc.terminate()
                try:
                    self._play_proc.wait(timeout=2)
                except Exception:
                    self._play_proc.kill()
                self._play_proc = None
        self.play_state.stop()

    def play_status(self) -> dict:
        return self.play_state.to_dict()

    # ── History ─────────────────────────────────────────────────────────

    def get_history(self) -> list[dict]:
        """Merge STS and TTS history, sorted by id descending."""
        all_entries = []
        for e in self.sts_history.list():
            all_entries.append(e.to_dict())
        for e in self.tts_history.list():
            all_entries.append(e.to_dict())
        all_entries.sort(key=lambda x: x["id"], reverse=True)
        return all_entries

    def delete_history_entry(self, entry_id: int) -> bool:
        if self.sts_history.delete(entry_id):
            return True
        if self.tts_history.delete(entry_id):
            return True
        return False

    def label_history_entry(self, entry_id: int, label: str) -> bool:
        if self.sts_history.rename(entry_id, label):
            return True
        if self.tts_history.rename(entry_id, label):
            return True
        return False

    # ── Voice Design ────────────────────────────────────────────────────

    def voice_design(self, text_description: str) -> dict:
        """Use ElevenLabs Voice Design API to create a new voice from description."""
        try:
            from elevenlabs import ElevenLabs
            import time
            client = ElevenLabs(api_key=self.api_key)

            # Pad description to meet minimum length if needed
            desc = text_description.strip()
            if len(desc) < 20:
                desc = f"{desc}. Warm and natural speaking voice for conversation."

            # Step 1: Generate previews from description
            previews = client.text_to_voice.create_previews(
                voice_description=desc,
                auto_generate_text=True,
            )
            if not previews or not previews.previews:
                return {"status": "error", "error": "No voice previews generated"}

            # Step 2: Use the first preview's generated_voice_id to create the voice
            preview = previews.previews[0]
            result = client.text_to_voice.create(
                voice_name=f"designed_{int(time.time())}",
                voice_description=desc,
                generated_voice_id=preview.generated_voice_id,
            )
            return {
                "status": "ok",
                "voice_id": result.voice_id,
                "voice_name": getattr(result, "name", "Designed Voice"),
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Voice design failed: {e}",
            }

    def voice_blend(self, voice_ids: list[str],
                    weights: Optional[list[float]] = None) -> dict:
        """Blend multiple voices into one using ElevenLabs voice blending."""
        try:
            import requests as req

            if weights and len(weights) != len(voice_ids):
                return {"status": "error", "error": "weights must match voice_ids count"}

            url = "https://api.elevenlabs.io/v1/voices/add"
            headers = {"xi-api-key": self.api_key}

            voice_settings_list = [
                {"voice_id": vid, "weight": w} if w else {"voice_id": vid}
                for vid, w in zip(
                    voice_ids,
                    weights or [1.0 / len(voice_ids)] * len(voice_ids)
                )
            ]

            data = {
                "voice_name": f"blend_{int(time.time())}",
                "voice_settings_list": voice_settings_list,
            }

            resp = req.post(url, headers=headers, json=data, timeout=30)
            if resp.ok:
                result = resp.json()
                return {
                    "status": "ok",
                    "voice_id": result.get("voice_id", ""),
                    "voice_name": data["voice_name"],
                }
            else:
                return {
                    "status": "error",
                    "error": f"API error {resp.status_code}: {resp.text[:200]}",
                }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Cleanup ─────────────────────────────────────────────────────────

    def cleanup(self):
        """Clean up temp files."""
        if TEMP_DIR.exists():
            shutil.rmtree(TEMP_DIR, ignore_errors=True)


# Singleton
_manager: VoiceManager | None = None


def get_manager(api_key: str = "") -> VoiceManager:
    global _manager
    if _manager is None:
        key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        _manager = VoiceManager(key)
    return _manager
