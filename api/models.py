"""Pydantic models for the Voice Changer API."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ── Voice Settings ─────────────────────────────────────────────────────────

class VoiceSettingsModel(BaseModel):
    stability: float = Field(default=0.30, ge=0.0, le=1.0, description="0=expressive, 1=robotic")
    similarity_boost: float = Field(default=0.95, ge=0.0, le=1.0, description="0=unique, 1=tight clone")
    style_exaggeration: float = Field(default=0.0, ge=0.0, le=1.0, description="0=subtle, 1=dramatic")
    speaker_boost: bool = Field(default=False)


# ── History ─────────────────────────────────────────────────────────────────

class HistoryEntryModel(BaseModel):
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


class HistoryListResponse(BaseModel):
    entries: list[HistoryEntryModel]


# ── Recording ───────────────────────────────────────────────────────────────

class StartRecordResponse(BaseModel):
    status: str
    message: str


class StopRecordResponse(BaseModel):
    status: str
    file_path: str
    duration_secs: float
    size_bytes: int


# ── Conversion / TTS ────────────────────────────────────────────────────────

class ConvertRequest(BaseModel):
    voice_id: str
    voice_settings: VoiceSettingsModel = VoiceSettingsModel()


class ConvertResponse(BaseModel):
    status: str
    file_path: str
    duration_secs: float
    history_id: int


class TTSRequest(BaseModel):
    text: str
    voice_id: str
    voice_settings: VoiceSettingsModel = VoiceSettingsModel()
    wallet: str = ""


class TTSResponse(BaseModel):
    status: str
    file_path: str
    duration_secs: float
    chars: int
    history_id: int


class TTSVariationsRequest(BaseModel):
    text: str
    voice_id: str
    count: int = 3
    voice_settings: VoiceSettingsModel = VoiceSettingsModel()
    wallet: str = ""


class TTSVariationsResponse(BaseModel):
    status: str
    variations: list[dict]


# ── Playback ────────────────────────────────────────────────────────────────

class PlayRequest(BaseModel):
    file_path: str
    countdown_secs: int = 3
    speed: float = 1.0
    character: str = "studio"


class PlayResponse(BaseModel):
    status: str
    message: str


class PlayStatusResponse(BaseModel):
    playing: bool = False
    file_path: str = ""
    total_secs: float = 0.0
    elapsed_secs: float = 0.0
    progress_pct: float = 0.0
    mode: str = ""


# ── Voices ──────────────────────────────────────────────────────────────────

class VoiceModel(BaseModel):
    voice_id: str
    name: str
    category: str = "unknown"
    labels: dict = {}


class VoicesResponse(BaseModel):
    voices: list[VoiceModel]


# ── Voice Design / Blend ────────────────────────────────────────────────────

class VoiceDesignRequest(BaseModel):
    text_description: str
    gender: str = "female"  # male, female
    age: str = "middle_aged"  # young, middle_aged, old
    accent: str = "american"  # british, american, australian, etc.


class VoiceDesignResponse(BaseModel):
    status: str
    voice_id: str
    voice_name: str


class VoiceBlendRequest(BaseModel):
    voice_ids: list[str] = Field(..., min_length=2, max_length=4)
    weights: Optional[list[float]] = None  # must sum to 1


class VoiceBlendResponse(BaseModel):
    status: str
    voice_id: str
    voice_name: str


# ── Text Refinement ────────────────────────────────────────────────────────

class RefineTextRequest(BaseModel):
    text: str
    style: str = "conversational"


class RefineTextResponse(BaseModel):
    status: str
    original: str
    refined: str
    provider: str = "deepseek"


# ── Status ──────────────────────────────────────────────────────────────────

class StatusResponse(BaseModel):
    status: str
    audio_sources: list[str]
    audio_sinks: list[str]
    history_count: int
    version: str = "1.0.0"
