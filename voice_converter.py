#!/usr/bin/env python3
"""
ElevenLabs Real-Time Voice Changer — Fedora 43 (PipeWire)
==========================================================
Real-time voice conversion (male→female, female→male, any voice transform)
using the ElevenLabs Speech-to-Speech streaming API.

Architecture:
  Physical Mic → VAD → Audio Segments → ElevenLabs STS API → Virtual Sink
  Apps (WhatsApp / Telegram / Linphone) select the virtual sink monitor as mic.

Usage:
  export ELEVENLABS_API_KEY="sk-..."
  ./voice_converter.py --voice-id JBFqnCBsd6RMkjVDRZzb

Latency target: <400 ms end-to-end.
"""

import argparse
import json
import logging
import os
import queue
import signal
import sys
import textwrap
import threading
import time
from dataclasses import dataclass, field
from io import BytesIO
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

# ── Audio Constants ──────────────────────────────────────────────────────────

SAMPLE_RATE       = 16000    # Hz — ElevenLabs STS native input rate
OUTPUT_RATE       = 24000    # Hz — output sample rate (matches pcm_24000)
CHANNELS          = 1        # Mono
BYTES_PER_SAMPLE  = 2        # int16
BLOCK_MS          = 20       # ms per capture block
BLOCK_SAMPLES     = int(SAMPLE_RATE * BLOCK_MS / 1000)     # 320
SEGMENT_MS        = 300      # ms — informational / logging only
VAD_THRESHOLD     = 100      # RMS threshold — high enough to avoid noise triggers
VAD_SPEECH_BLOCKS = 2        # 40ms to confirm speech
VAD_SILENCE_BLOCKS= 75       # 1500ms silence before cutting (sentence-level)
VAD_MAX_BLOCKS    = int(10 * 1000 / BLOCK_MS)  # ~500 = 10 s max segment

# Playout crossfade (smooth transitions between segments)
CROSSFADE_SAMPLES = int(0.010 * OUTPUT_RATE)  # 240 samples = 10ms at 24kHz

# ElevenLabs STS API
STS_MODEL         = "eleven_english_sts_v2"
OUTPUT_FMT        = "pcm_24000"   # 24kHz — good quality, works on all tiers
LATENCY_OPT       = 4

# ── Voice Settings ─────────────────────────────────────────────────────────────

@dataclass
class VoiceSettings:
    """Tunable ElevenLabs voice parameters — the main dials for natural/unique sound.

    stability:        0.0–1.0  — Low = expressive/varied, High = robotic/consistent
    similarity_boost: 0.0–1.0  — Low = deviates from source (more unique), High = tight clone
    style_exaggeration: 0.0–1.0 — Low = subtle, High = dramatic (character voices)
    speaker_boost:    bool     — Prefer to preserve original speaker identity
    speed:            0.5–2.0  — Playback/voice speed (1.0 = normal, 0.5 = half, 2.0 = double)
    character:       str      — Audio character: studio, warm, lo-fi, natural, vintage, phone
    """
    stability: float = 0.30
    similarity_boost: float = 0.95
    style_exaggeration: float = 0.0
    speaker_boost: bool = False
    speed: float = 1.0
    character: str = "studio"

    CHARACTER_OPTIONS = ["studio", "warm", "natural", "lo-fi", "phone", "vintage"]
    CHARACTER_LABELS = {
        "studio": "Studio (clean, clear)",
        "warm": "Warm (softer highs)",
        "natural": "Natural (slight room ambience)",
        "lo-fi": "Lo-Fi (muffled, like a recording)",
        "phone": "Phone Call (narrow band)",
        "vintage": "Vintage (analog warmth)",
    }

    def to_dict(self) -> dict:
        d: dict = {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
        }
        if self.style_exaggeration > 0:
            d["style_exaggeration"] = self.style_exaggeration
        if self.speaker_boost:
            d["speaker_boost"] = True
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_args(cls, args) -> "VoiceSettings":
        return cls(
            stability=args.stability,
            similarity_boost=args.similarity_boost,
            style_exaggeration=args.style_exaggeration,
            speaker_boost=args.speaker_boost,
            speed=args.speed,
            character=args.character,
        )

    def display(self) -> str:
        parts = [f"S={self.stability:.2f}", f"B={self.similarity_boost:.2f}"]
        if self.style_exaggeration > 0:
            parts.append(f"E={self.style_exaggeration:.2f}")
        if self.speaker_boost:
            parts.append("+Boost")
        if self.speed != 1.0:
            parts.append(f"⏩{self.speed:.2f}x")
        if self.character != "studio":
            parts.append(f"[{self.character}]")
        return "|".join(parts)

    def to_ffmpeg_filters(self) -> list[str]:
        """Return ffmpeg -af filter arguments for the chosen character."""
        if self.character == "studio":
            return []
        elif self.character == "warm":
            # Gentle low-pass at 8kHz to remove harsh highs, slight high-shelf cut
            return ["lowpass=f=8000", "equalizer=f=3000:t=q:w=1:g=-1.5"]
        elif self.character == "natural":
            # Subtle warmth, slight noise floor simulation via a gentle lowpass
            return ["lowpass=f=10000", "equalizer=f=200:t=q:w=0.5:g=-1"]
        elif self.character == "lo-fi":
            # Heavy low-pass, slight high-pass — muffled like a budget recording
            return ["lowpass=f=5500", "highpass=f=80", "equalizer=f=2000:t=q:w=1:g=-3"]
        elif self.character == "phone":
            # Narrow telephone band: 300Hz–3.4kHz
            return ["highpass=f=300", "lowpass=f=3400", "equalizer=f=1000:t=q:w=1:g=2"]
        elif self.character == "vintage":
            # Analog warmth: cut highs, slight mid boost
            return ["lowpass=f=7500", "equalizer=f=150:t=q:w=0.5:g=2",
                    "equalizer=f=5000:t=q:w=1:g=-2"]
        return []


# Popular presets for quick reference
VOICE_PRESETS = {
    "natural": VoiceSettings(stability=0.25, similarity_boost=0.60, style_exaggeration=0.0),
    "unique": VoiceSettings(stability=0.35, similarity_boost=0.40, style_exaggeration=0.1),
    "stable": VoiceSettings(stability=0.70, similarity_boost=0.85, style_exaggeration=0.0),
    "dramatic": VoiceSettings(stability=0.30, similarity_boost=0.75, style_exaggeration=0.6),
    "robotic": VoiceSettings(stability=0.90, similarity_boost=0.95, style_exaggeration=0.0),
}

# Legacy default
VOICE_SETTINGS_JSON = VoiceSettings().to_json()
API_BASE_URL      = "https://api.elevenlabs.io"

# Virtual sink (created by setup_voice_changer.sh)
VIRTUAL_SINK_NAME = "VoiceChanger"

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("vc")

# ── Helpers ──────────────────────────────────────────────────────────────────

def rms(arr: np.ndarray) -> float:
    if len(arr) == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))


def int16_bytes(arr: np.ndarray) -> bytes:
    return arr.astype(np.int16).tobytes()


def silence_bytes(samples: int) -> bytes:
    return b"\x00" * (samples * BYTES_PER_SAMPLE)


# ── Resampling ────────────────────────────────────────────────────────────────

def linear_resample(src: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """
    Linear-interpolation resampling for 1D int16 arrays.
    Simple, fast, good-enough for voice.
    """
    if src_rate == dst_rate or len(src) < 2:
        return src
    src_f = src.astype(np.float64)
    dst_len = max(1, int(round(len(src) * dst_rate / src_rate)))
    # Input indices for each output sample
    src_idx = np.linspace(0.0, len(src) - 1.0, dst_len)
    left = np.floor(src_idx).astype(np.int64)
    right = np.clip(left + 1, 0, len(src) - 1)
    frac = (src_idx - left).astype(np.float64)
    out = src_f[left] * (1.0 - frac) + src_f[right] * frac
    return out.astype(np.int16)


def device_rate(dev_idx: Optional[int], kind: str = "input") -> int:
    """Query the native default sample rate of an audio device."""
    try:
        import sounddevice as sd
        if dev_idx is not None:
            info = sd.query_devices(dev_idx)
            r = info.get("default_samplerate", 0)
            if r and r > 0:
                return int(r)
        # Fallback: try the kind default
        fallback = sd.query_devices(kind=kind)
        r = fallback.get("default_samplerate", 48000)
        return int(r) if r else 48000
    except Exception:
        return 48000


# ── Voice Activity Detection ─────────────────────────────────────────────────

class VAD:
    """
    Energy-based VAD state machine.

    States:
      SILENCE    – idle, discarding blocks
      MAYBE      – speech detected but not yet confirmed (debounce)
      SPEAKING   – confirmed speech, accumulating segment
      TAIL       – speech ended, accumulating hangover silence
    """

    SILENCE = 0
    MAYBE   = 1
    SPEAKING= 2
    TAIL    = 3

    def __init__(self, threshold: float = VAD_THRESHOLD):
        self.threshold = threshold
        self.state     = self.SILENCE
        self.buffer: List[np.ndarray] = []
        self.counter   = 0
        self.blocks    = 0   # total blocks in current segment

    def reset(self) -> None:
        self.state = self.SILENCE
        self.buffer = []
        self.counter = 0
        self.blocks = 0

    def feed(self, block: np.ndarray) -> Optional[np.ndarray]:
        """
        Feed one 20 ms block. Returns a complete speech segment (numpy array)
        when ready, otherwise None.
        """
        speech = rms(block) > self.threshold

        if self.state == self.SILENCE:
            if speech:
                self.state = self.MAYBE
                self.counter = 1
                self.buffer = [block.copy()]

        elif self.state == self.MAYBE:
            self.buffer.append(block.copy())
            self.blocks = len(self.buffer)
            if speech:
                self.counter += 1
                if self.counter >= VAD_SPEECH_BLOCKS:
                    self.state = self.SPEAKING
            else:
                # false alarm
                self.state = self.SILENCE
                self.buffer = []
                self.counter = 0

        elif self.state == self.SPEAKING:
            self.buffer.append(block.copy())
            self.blocks += 1
            if not speech:
                self.state = self.TAIL
                self.counter = 1
            elif self.blocks >= VAD_MAX_BLOCKS:
                return self._emit()

        elif self.state == self.TAIL:
            self.buffer.append(block.copy())
            self.blocks += 1
            if speech:
                self.state = self.SPEAKING
                self.counter = 0
            else:
                self.counter += 1
                if self.counter >= VAD_SILENCE_BLOCKS or self.blocks >= VAD_MAX_BLOCKS:
                    return self._emit()

        return None

    def _emit(self) -> np.ndarray:
        out = np.concatenate(self.buffer)
        self.reset()
        return out


# ── ElevenLabs STS Client ────────────────────────────────────────────────────

class ElevenLabsSTS:
    """Wrapper around the ElevenLabs Speech-to-Speech streaming endpoint."""

    def __init__(self, api_key: str, voice_settings: Optional[VoiceSettings] = None):
        self.api_key = api_key
        self.voice_settings = voice_settings or VoiceSettings()
        self._use_sdk = False
        self._sdk_client = None
        try:
            from elevenlabs import ElevenLabs  # noqa
            self._sdk_client = ElevenLabs(api_key=api_key)
            self._use_sdk = True
        except ImportError:
            pass
        self._have_requests = False
        try:
            import requests  # noqa
            self._have_requests = True
        except ImportError:
            pass

    def convert_stream(self, audio: bytes, voice_id: str,
                       voice_settings: Optional[VoiceSettings] = None) -> Iterator[bytes]:
        """
        Send PCM audio (16 kHz, 16-bit, mono) to the STS /stream endpoint.
        Yields converted PCM chunks as they arrive.
        voice_settings overrides the instance defaults if provided.
        """
        vs = voice_settings or self.voice_settings
        if self._use_sdk:
            yield from self._via_sdk(audio, voice_id, vs)
        elif self._have_requests:
            yield from self._via_requests(audio, voice_id, vs)
        else:
            raise RuntimeError(
                "Install 'elevenlabs' or 'requests':  pip install elevenlabs requests"
            )

    # --- SDK path ---
    def _via_sdk(self, audio: bytes, voice_id: str,
                 vs: VoiceSettings) -> Iterator[bytes]:
        stream = self._sdk_client.speech_to_speech.stream(
            voice_id=voice_id,
            audio=audio,
            model_id=STS_MODEL,
            output_format=OUTPUT_FMT,
            optimize_streaming_latency=LATENCY_OPT,
            file_format="pcm_s16le_16",
            voice_settings=vs.to_json(),
        )
        for chunk in stream:
            if chunk:
                yield chunk

    # --- raw requests fallback ---
    def _via_requests(self, audio: bytes, voice_id: str,
                      vs: VoiceSettings) -> Iterator[bytes]:
        import requests as req
        url = f"{API_BASE_URL}/v1/speech-to-speech/{voice_id}/stream"
        params = {"optimize_streaming_latency": str(LATENCY_OPT),
                  "output_format": OUTPUT_FMT}
        data = {"model_id": (None, STS_MODEL),
                "file_format": (None, "pcm_s16le_16"),
                "voice_settings": (None, vs.to_json())}
        files = {"audio": ("audio.raw", audio, "application/octet-stream")}
        headers = {"xi-api-key": self.api_key, "Accept": "audio/pcm"}
        resp = req.post(url, params=params, headers=headers,
                        files=files, data=data, stream=True, timeout=30)
        if not resp.ok:
            log.error("ElevenLabs error %d: %s", resp.status_code, resp.text[:200])
            resp.close()
            return
        for chunk in resp.iter_content(chunk_size=1024):
            if chunk:
                yield chunk
        resp.close()

    # --- voice listing ---
    def list_voices(self) -> List[Dict]:
        if self._use_sdk:
            resp = self._sdk_client.voices.get_all()
            result = []
            for v in resp.voices:
                labels = {}
                if hasattr(v, "labels") and v.labels:
                    if hasattr(v.labels, "model_dump"):
                        labels = v.labels.model_dump()
                    elif isinstance(v.labels, dict):
                        labels = v.labels
                result.append({
                    "voice_id": v.voice_id,
                    "name": v.name,
                    "category": getattr(v, "category", "unknown"),
                    "labels": labels,
                })
            return result
        if self._have_requests:
            import requests as req
            r = req.get(f"{API_BASE_URL}/v1/voices",
                        headers={"xi-api-key": self.api_key})
            r.raise_for_status()
            return [{"voice_id": v["voice_id"], "name": v["name"],
                     "category": v.get("category", "unknown"),
                     "labels": v.get("labels", {})}
                    for v in r.json().get("voices", [])]
        return []


# ── PulseAudio helpers ─────────────────────────────────────────────────────

PA_SOURCE_BT = "bluez_input.A4:40:3E:11:20:FE"   # Bluetooth mic
PA_SINK_VC   = "VoiceChanger"                      # Virtual sink

def pulse_name(hint: str, kind: str) -> Optional[str]:
    """
    Resolve a user-provided *hint* to a PulseAudio source or sink name.
    *hint* can be a pactl name substring ("Bluetooth", "VoiceChanger",
    "Baseus") or an empty string to auto-detect.
    """
    import subprocess
    try:
        if kind == "input":
            raw = subprocess.check_output(
                ["pactl", "list", "sources", "short"], text=True, timeout=3
            )
        else:
            raw = subprocess.check_output(
                ["pactl", "list", "sinks", "short"], text=True, timeout=3
            )
        for line in raw.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[1]
                if hint.lower() in name.lower():
                    return name
        return None
    except Exception:
        return None


def default_source() -> str:
    """
    Get the best available PulseAudio source name.
    Prefers the real default, falls back to first non-monitor source.
    """
    import subprocess
    # 1. Try pactl get-default-source
    try:
        name = subprocess.check_output(
            ["pactl", "get-default-source"], text=True, timeout=3
        ).strip()
        if name and name != "@DEFAULT_SOURCE@":
            return name
    except Exception:
        pass
    # 2. Fallback: find a real capture source (not a monitor)
    try:
        raw = subprocess.check_output(
            ["pactl", "list", "sources", "short"], text=True, timeout=3
        )
        for line in raw.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[1]
                if ".monitor" not in name.lower():
                    return name
    except Exception:
        pass
    # 3. Last fallback — let PulseAudio decide
    return "default"


# ── Audio Pipeline ───────────────────────────────────────────────────────────

@dataclass
class Stats:
    segments_sent: int        = 0
    segments_ok: int          = 0
    api_errors: int           = 0
    last_latency_ms: float    = 0.0
    total_output_samples: int = 0


class Pipeline:
    """
    Three-thread pipeline using PulseAudio CLI (parec / paplay) for audio I/O.

      capture  – mic → VAD → segment_queue
      process  – segment_queue → ElevenLabs STS → output_queue
      playback – output_queue → virtual sink

    Why PulseAudio CLI and not sounddevice / PortAudio:
      PortAudio's ALSA and JACK backends have heap-corruption bugs with
      PipeWire on Fedora 43.  parec/paplay go through PulseAudio → PipeWire
      and handle sample-rate conversion trivially.
    """

    def __init__(self, voice_id: str, api_key: str,
                 input_name: str = "",
                 output_name: str = PA_SINK_VC,
                 voice_settings: Optional[VoiceSettings] = None):
        self.voice_id      = voice_id     # ElevenLabs target voice ID
        self.voice_settings = voice_settings or VoiceSettings()
        self.input_name    = input_name   # PulseAudio source name (or "" for default)
        self.output_name   = output_name  # PulseAudio sink name
        self.stats         = Stats()
        self._eleven       = ElevenLabsSTS(api_key, voice_settings=self.voice_settings)
        self._running      = False
        self._seg_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=8)
        self._out_q: "queue.Queue[bytes]"      = queue.Queue(maxsize=128)
        self._vad          = VAD()
        self._capture_ready = threading.Event()
        self._proc_cap     = None  # parec subprocess
        self._proc_play    = None  # paplay subprocess
        self._threads: List[threading.Thread] = []

    # ── public API ───────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        targets = [("capture", self._capture_loop),
                   ("process", self._process_loop),
                   ("playout", self._playout_loop)]
        for name, fn in targets:
            t = threading.Thread(target=fn, name=name, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._running = False
        # kill subprocesses
        for proc_name in ("_proc_cap", "_proc_play"):
            p = getattr(self, proc_name, None)
            if p and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        # unblock queue gets
        try:
            self._seg_q.put_nowait(None)
        except queue.Full:
            pass
        try:
            self._out_q.put_nowait(None)
        except queue.Full:
            pass

    def wait(self, timeout: float = 3.0):
        for t in self._threads:
            t.join(timeout=timeout)

    # ── capture ──────────────────────────────────────────────────────────

    def _ensure_bt_profile(self):
        """Switch Bluetooth card to HSP/HFP if currently in A2DP mode."""
        import subprocess
        try:
            raw = subprocess.check_output(
                ["pactl", "list", "cards"], text=True, timeout=5
            )
        except Exception:
            return
        # Look for the Bluetooth card
        for block in raw.split("Name: bluez_card"):
            if not block:
                continue
            if "Active Profile: a2dp" in block:
                log.warning("   Bluetooth in A2DP (no mic) — switching to HSP/HFP...")
                try:
                    subprocess.run(
                        ["pactl", "set-card-profile", "bluez_card.A4_40_3E_11_20_FE",
                         "headset-head-unit"],
                        timeout=5, capture_output=True
                    )
                    log.info("   Profile switched. Waiting 2 s for source to settle...")
                    time.sleep(2)
                except Exception as exc:
                    log.warning("   Profile switch failed: %s", exc)

    def _capture_loop(self):
        import subprocess

        # Resolve the PulseAudio source name
        src = self.input_name
        if not src:
            src = default_source()
        if not src:
            src = PA_SOURCE_BT
        log.info("🎤  PulseAudio source:  %s", src)

        # If this is a Bluetooth source, ensure we're in HSP/HFP mode
        if "bluez" in src.lower() or "bluetooth" in src.lower():
            self._ensure_bt_profile()
            # Re-resolve source after potential profile switch
            new_src = default_source()
            if new_src and "bluez_input" in new_src:
                log.info("   Re-resolved source: %s", new_src)
                src = new_src

        # Start parec — capture raw 16-bit mono 16 kHz
        read_size = BLOCK_SAMPLES  # 320 samples = 20 ms at 16 kHz
        cmd = [
            "parec",
            "--raw",
            f"--rate={SAMPLE_RATE}",
            "--format=s16le",
            "--channels=1",
            f"--device={src}",
        ]
        log.info("   Starting: %s", " ".join(cmd))
        try:
            self._proc_cap = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, bufsize=2**16
            )
        except FileNotFoundError:
            log.error("parec not found — install pulseaudio-utils")
            self._running = False
            return

        # Calibrate VAD from ~1 s of ambient
        log.info("   Calibrating VAD (1 second)...")
        calib_frames = max(5, int(SAMPLE_RATE // read_size))
        energies = []
        for _ in range(calib_frames):
            if not self._running:
                break
            chunk = self._proc_cap.stdout.read(read_size * BYTES_PER_SAMPLE)
            if not chunk:
                log.error("parec returned no data — source '%s' not producing audio", src)
                log.error("Check:  pactl list sources short | grep bluez")
                log.error("Check:  pactl list cards | grep 'Active Profile'")
                self._running = False
                return
            frame = np.frombuffer(chunk, dtype=np.int16)
            energies.append(float(np.sqrt(np.mean(frame.astype(np.float64) ** 2))))

        if energies:
            floor = float(np.median(energies))
            if floor < 1.0:
                log.warning("⚠️  VAD: noise floor = %.2f — mic appears silent!", floor)
                log.warning("   Manual fix:")
                log.warning("     pactl set-card-profile bluez_card.A4_40_3E_11_20_FE headset-head-unit")
                log.warning("   Then run the script again")
                thr = float(VAD_THRESHOLD)
            else:
                thr = max(VAD_THRESHOLD, floor * 3.0)
            self._vad = VAD(threshold=thr)
            log.info("   VAD calibrated: noise floor=%.1f  threshold=%.1f", floor, thr)

        self._capture_ready.set()
        log.info("   Capture running — speak into your mic!")

        # Main loop: read 20 ms blocks, feed VAD, emit segments
        block_count = 0
        while self._running:
            chunk = self._proc_cap.stdout.read(read_size * BYTES_PER_SAMPLE)
            if not chunk:
                log.warning("parec stream ended")
                break
            frame = np.frombuffer(chunk, dtype=np.int16)
            block_count += 1

            if block_count % 50 == 0:
                peak = int(np.max(np.abs(frame)))
                rms_lvl = int(rms(frame))
                log.info("   Mic level: peak=%d  RMS=%d  (VAD threshold=%.0f)",
                         peak, rms_lvl, self._vad.threshold)

            # Write level to tmp file for TUI meter (fail silently)
            try:
                frame_rms = int(rms(frame))
                with open("/tmp/voice_changer_level", "w") as f:
                    f.write(str(frame_rms))
            except Exception:
                pass

            seg = self._vad.feed(frame)
            if seg is not None:
                # Send the FULL segment — ElevenLabs handles variable length.
                # Do NOT trim to SEGMENT_SAMPLES (that would cut speech mid-word).
                try:
                    self._seg_q.put(seg, timeout=0.5)
                except queue.Full:
                    log.warning("Segment queue full; dropping")

        if self._proc_cap and self._proc_cap.poll() is None:
            self._proc_cap.terminate()
        log.info("Capture stopped")

    # ── processing ───────────────────────────────────────────────────────

    def _process_loop(self):
        while self._running:
            try:
                seg = self._seg_q.get(timeout=1.0)
            except queue.Empty:
                continue
            if seg is None:
                break

            self.stats.segments_sent += 1

            # Check mute file — skip API call if muted
            try:
                muted = open("/tmp/voice_changer_muted").read().strip() == "1"
            except Exception:
                muted = False
            if muted:
                self.stats.segments_ok += 1
                continue

            raw = int16_bytes(seg)
            t0 = time.monotonic()
            try:
                for chunk in self._eleven.convert_stream(raw, self.voice_id):
                    if not self._running:
                        break
                    self._out_q.put(chunk)
                self.stats.last_latency_ms = (time.monotonic() - t0) * 1000
                self.stats.segments_ok += 1
            except Exception as exc:
                self.stats.api_errors += 1
                log.error("API error: %s", exc)
                self._out_q.put(silence_bytes(int(OUTPUT_RATE * 0.3)))  # 300ms silence
        log.info("Processing stopped")

    # ── playback ─────────────────────────────────────────────────────────

    def _playout_loop(self):
        import subprocess

        # Wait for capture calibration (so devices settle)
        if not self._capture_ready.wait(timeout=15.0):
            log.error("Timeout waiting for capture to be ready")
            self._running = False
            return

        sink = self.output_name
        log.info("🔊  PulseAudio sink:  %s", sink)

        # Start paplay — play raw 16-bit mono OUTPUT_RATE Hz
        cmd = [
            "paplay",
            "--raw",
            f"--rate={OUTPUT_RATE}",
            "--format=s16le",
            "--channels=1",
            f"--device={sink}",
        ]
        log.info("   Starting: %s", " ".join(cmd))
        try:
            self._proc_play = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, bufsize=2**16
            )
        except FileNotFoundError:
            log.error("paplay not found — install pulseaudio-utils")
            self._running = False
            return

        # Accumulation buffer + crossfade state
        buf = bytearray()
        prev_tail: Optional[np.ndarray] = None
        crossfade_len = CROSSFADE_SAMPLES

        while self._running:
            # Drain available chunks into buffer
            got = False
            while True:
                try:
                    ch = self._out_q.get_nowait()
                except queue.Empty:
                    break
                got = True
                if ch is None:
                    # Flush remaining buffer
                    if buf:
                        try:
                            self._proc_play.stdin.write(bytes(buf))
                            self._proc_play.stdin.flush()
                        except Exception:
                            pass
                    self._proc_play.stdin.close()
                    self._proc_play.terminate()
                    return
                buf.extend(ch)

            if not buf:
                time.sleep(0.005)
                continue

            # Convert buffer to numpy array (must be WRITABLE for crossfade)
            audio = np.frombuffer(bytes(buf), dtype=np.int16).copy()
            buf.clear()

            # Crossfade with previous segment's tail to remove clicks
            if prev_tail is not None and len(audio) > 0 and len(prev_tail) > 0:
                blend = min(crossfade_len, len(audio), len(prev_tail))
                if blend > 0:
                    fade_in = np.linspace(0.0, 1.0, blend)
                    fade_out = np.linspace(1.0, 0.0, blend)
                    head = audio[:blend].astype(np.float64)
                    tail = prev_tail[-blend:].astype(np.float64)
                    blended = (head * fade_in + tail * fade_out).astype(np.int16)
                    audio[:blend] = blended

            # Save tail for next crossfade
            if len(audio) > crossfade_len:
                prev_tail = audio[-crossfade_len:].copy()
            else:
                prev_tail = audio.copy()

            # Normalize peak to -3dB to prevent clipping
            peak = int(np.max(np.abs(audio)))
            if peak > 28000:  # near clipping
                scale = 28000.0 / peak
                audio = (audio.astype(np.float64) * scale).astype(np.int16)

            try:
                self._proc_play.stdin.write(audio.tobytes())
                self._proc_play.stdin.flush()
                self.stats.total_output_samples += len(audio)
            except BrokenPipeError:
                log.warning("paplay pipe broken (sink '%s' gone?)", sink)
                break
            except Exception as exc:
                log.error("paplay write error: %s", exc)
                break

        if self._proc_play and self._proc_play.poll() is None:
            self._proc_play.stdin.close()
            self._proc_play.terminate()
        log.info("Playback stopped")


# ── CLI Helpers ──────────────────────────────────────────────────────────────

BANNER = r"""
╔══════════════════════════════════════════════════════════╗
║     ElevenLabs Real-Time Voice Changer                   ║
║     Male ↔ Female · Any Voice · <400 ms Latency         ║
╚══════════════════════════════════════════════════════════╝
"""

def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="voice_converter.py",
        description="Real-time voice changer via ElevenLabs Speech-to-Speech API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s --voice-id JBFqnCBsd6RMkjVDRZzb
              %(prog)s --list-voices
              %(prog)s --list-devices
              %(prog)s --voice-id 21m00Tcm4TlvDq8ikWAM --input-device 2 --output-device 5

            Voice cloning:  https://elevenlabs.io/app/voice-lab
            Virtual sink:   ./setup_voice_changer.sh
        """),
    )
    p.add_argument("--voice-id", help="ElevenLabs Voice ID (preset or cloned)")
    p.add_argument("--api-key", help="API key (or set ELEVENLABS_API_KEY env)")
    p.add_argument("--list-voices", action="store_true", help="List voices and exit")
    p.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    p.add_argument("--input-device", type=str, default=None,
                   help="Input source name (e.g. 'bluetooth', 'bluez', 'default')")
    p.add_argument("--output-device", type=str, default=None,
                   help="Output sink name (e.g. 'VoiceChanger', 'default')")
    p.add_argument("--threshold", type=float, default=VAD_THRESHOLD,
                   help=f"VAD energy threshold (default {VAD_THRESHOLD})")
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
    p.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return p.parse_args(argv)


def list_devices():
    """Show PulseAudio sources and sinks (what you can use for in/out)."""
    import subprocess
    print("\n=== Audio Sources (input) ===\n")
    try:
        raw = subprocess.check_output(["pactl", "list", "sources", "short"],
                                       text=True, timeout=5)
        for line in raw.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                print(f"  {parts[1]}")
    except Exception as e:
        print(f"  (pactl error: {e})")

    print("\n=== Audio Sinks (output) ===\n")
    try:
        raw = subprocess.check_output(["pactl", "list", "sinks", "short"],
                                       text=True, timeout=5)
        for line in raw.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) >= 2:
                print(f"  {parts[1]}")
    except Exception as e:
        print(f"  (pactl error: {e})")

    print(f"\nTip: use --input-device \"<name-substring>\" to match by name")
    print(f"     use --output-device \"VoiceChanger\" for the virtual mic\n")


def list_voices(api_key: str):
    eleven = ElevenLabsSTS(api_key)
    print("\nFetching voices...\n")
    try:
        voices = eleven.list_voices()
    except Exception as exc:
        log.error("Cannot fetch voices: %s", exc)
        return
    if not voices:
        print("No voices found.\n")
        return
    print(f"{'#':>3s}  {'Name':<35s}  {'Voice ID':<25s}  {'Category'}")
    print("-" * 100)
    for i, v in enumerate(voices):
        print(f"  {i:2d}  {v['name']:<35s}  {v['voice_id']:<25s}  {v.get('category', '-')}")
    print(f"\n{len(voices)} total.\n")


def _pick_voice(voices: List[Dict]) -> Optional[str]:
    """Let the user pick a voice from the list or paste a Voice ID."""
    if voices:
        print(f"\nAvailable voices ({len(voices)}):\n")
        for i, v in enumerate(voices[:20]):
            cat = v.get("category", "")
            tag = f" [{cat}]" if cat else ""
            print(f"  {i:3d}. {v['name']:<30s} {v['voice_id']}{tag}")
        if len(voices) > 20:
            print(f"  ... and {len(voices) - 20} more")
        print()
        choice = input("Enter number or paste Voice ID: ").strip()
        try:
            idx = int(choice)
            if 0 <= idx < len(voices):
                return voices[idx]["voice_id"]
        except ValueError:
            return choice
    else:
        return input("Paste Voice ID: ").strip()
    return None


# ─── Signal Handling ─────────────────────────────────────────────────────────

_pipeline: Optional[Pipeline] = None

def _on_sig(signum, frame):
    log.info("Shutting down …")
    if _pipeline:
        _pipeline.stop()


# ─── Main ────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> None:
    global _pipeline
    args = parse_args(argv or sys.argv[1:])

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # --list-devices does not need an API key
    if args.list_devices:
        list_devices()
        return

    # API key
    api_key = args.api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        if args.list_voices:
            log.error("API key required; set ELEVENLABS_API_KEY")
            sys.exit(1)
        api_key = input("ElevenLabs API key: ").strip()
    if not api_key:
        log.error("No API key")
        sys.exit(1)

    if args.list_voices:
        list_voices(api_key)
        return

    # Resolve voice and PulseAudio device names
    voice_id = args.voice_id

    input_source: Optional[str] = None
    if args.input_device:
        resolved = pulse_name(args.input_device, "input")
        if resolved:
            input_source = resolved
            log.info("Input source: '%s' → '%s'", args.input_device, resolved)
        else:
            log.warning("Input '%s' not found via pactl; trying as-is", args.input_device)
            input_source = args.input_device

    output_sink: Optional[str] = None
    if args.output_device:
        resolved = pulse_name(args.output_device, "output")
        if resolved:
            output_sink = resolved
            log.info("Output sink: '%s' → '%s'", args.output_device, resolved)
        else:
            log.warning("Output '%s' not found via pactl; trying as-is", args.output_device)
            output_sink = args.output_device

    if not voice_id:
        print(BANNER)
        print("Interactive Setup\n")
        print("Fetching voices...", end=" ", flush=True)
        eleven = ElevenLabsSTS(api_key)
        try:
            voices = eleven.list_voices()
        except Exception as exc:
            log.error("Cannot fetch voices: %s", exc)
            voices = []
        print()
        voice_id = _pick_voice(voices)
        if not voice_id:
            sys.exit(1)
        # Show available PulseAudio devices
        list_devices()
        d_in = input("Input source name [auto]: ").strip()
        if d_in:
            resolved = pulse_name(d_in, "input")
            input_source = resolved if resolved else d_in
        d_out = input("Output sink name [VoiceChanger]: ").strip() or "VoiceChanger"
        resolved = pulse_name(d_out, "output")
        output_sink = resolved if resolved else d_out

    if output_sink is None:
        resolved = pulse_name(VIRTUAL_SINK_NAME, "output")
        output_sink = resolved if resolved else VIRTUAL_SINK_NAME
        log.info("Auto-detected output sink: %s", output_sink)

    # Resolve voice settings
    voice_settings: Optional[VoiceSettings] = None
    if args.voice_preset:
        voice_settings = VOICE_PRESETS[args.voice_preset]
        log.info("Voice preset: %s → %s", args.voice_preset, voice_settings.display())
    else:
        voice_settings = VoiceSettings(
            stability=args.stability,
            similarity_boost=args.similarity_boost,
            style_exaggeration=args.style_exaggeration,
            speaker_boost=args.speaker_boost,
            speed=args.speed,
            character=args.character,
        )

    print(BANNER)
    log.info("Voice ID:         %s", voice_id)
    log.info("Input source:     %s", input_source or "(default)")
    log.info("Output sink:      %s", output_sink)
    log.info("Segment:          %d ms", SEGMENT_MS)
    log.info("Voice settings:   %s", voice_settings.display())
    log.info("")
    log.info("Speak into your mic → converted voice → virtual sink\n")

    pipe = Pipeline(voice_id, api_key,
                    input_name=input_source or "",
                    output_name=output_sink or VIRTUAL_SINK_NAME,
                    voice_settings=voice_settings)
    _pipeline = pipe

    signal.signal(signal.SIGINT, _on_sig)
    signal.signal(signal.SIGTERM, _on_sig)

    try:
        pipe.start()
        while pipe._running:
            time.sleep(5)
            s = pipe.stats
            if s.segments_sent:
                log.info("Stats: %d sent | %d ok | %d err | API lat ~%.0f ms",
                         s.segments_sent, s.segments_ok, s.api_errors,
                         s.last_latency_ms)
    except KeyboardInterrupt:
        pass
    finally:
        log.info("Stopping …")
        pipe.stop()
        pipe.wait()
        log.info("Done.")


if __name__ == "__main__":
    main()