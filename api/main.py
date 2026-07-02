"""ElevenLabs Voice Changer — FastAPI Backend.

Provides REST + WebSocket API for voice conversion, TTS, history, replay,
voice settings, voice design, and blending.

Run with:
  uvicorn api.main:app --reload --port 8765
  # or directly:
  python3 -m api.main
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Add parent so we can use the shared history JSON on disk
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models import (
    ConvertRequest, ConvertResponse,
    TTSRequest, TTSResponse,
    PlayRequest, PlayResponse, PlayStatusResponse,
    VoiceSettingsModel, VoicesResponse, VoiceModel,
    VoiceDesignRequest, VoiceDesignResponse,
    VoiceBlendRequest, VoiceBlendResponse,
    HistoryEntryModel, HistoryListResponse,
    RefineTextRequest, RefineTextResponse,
    StatusResponse,
)
from api.voice_manager import get_manager, VoiceManager
from voice_converter import VoiceSettings


# ── App lifecycle ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    mgr = get_manager()
    mgr.cleanup()


app = FastAPI(
    title="Voice Changer API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _vs_from_model(m: VoiceSettingsModel) -> VoiceSettings:
    return VoiceSettings(
        stability=m.stability,
        similarity_boost=m.similarity_boost,
        style_exaggeration=m.style_exaggeration,
        speaker_boost=m.speaker_boost,
    )


def _require_api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not key:
        raise HTTPException(status_code=400, detail="Set ELEVENLABS_API_KEY environment variable")
    return key


# ── Status ─────────────────────────────────────────────────────────────────

@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    mgr = get_manager(_require_api_key())
    return StatusResponse(
        status="ok",
        audio_sources=mgr.list_sources(),
        audio_sinks=mgr.list_sinks(),
        history_count=len(mgr.get_history()),
    )


# ── Devices ────────────────────────────────────────────────────────────────

@app.get("/api/devices/sources")
async def list_sources():
    mgr = get_manager(_require_api_key())
    return {"sources": mgr.list_sources(), "default": mgr.default_source()}


@app.get("/api/devices/sinks")
async def list_sinks():
    mgr = get_manager(_require_api_key())
    return {"sinks": mgr.list_sinks()}


# ── Voices ─────────────────────────────────────────────────────────────────

@app.get("/api/voices", response_model=VoicesResponse)
async def list_voices():
    mgr = get_manager(_require_api_key())
    voices = mgr.list_voices()
    return VoicesResponse(
        voices=[VoiceModel(**v) for v in voices]
    )


# ── Recording ──────────────────────────────────────────────────────────────

@app.post("/api/record/start")
async def start_record(source: str = ""):
    mgr = get_manager(_require_api_key())
    if mgr.is_recording():
        raise HTTPException(status_code=409, detail="Already recording")
    mgr.start_recording(source)
    return {"status": "recording", "message": "Recording started"}


@app.post("/api/record/stop")
async def stop_record():
    mgr = get_manager(_require_api_key())
    if not mgr.is_recording():
        raise HTTPException(status_code=409, detail="Not recording")
    result = mgr.stop_recording()
    return result


@app.get("/api/record/status")
async def record_status():
    mgr = get_manager(_require_api_key())
    return {"recording": mgr.is_recording()}


# ── Conversion (STS) ──────────────────────────────────────────────────────

@app.post("/api/convert", response_model=ConvertResponse)
async def convert_audio(req: ConvertRequest, input_file: str = ""):
    """Convert a recorded audio file using ElevenLabs STS."""
    mgr = get_manager(_require_api_key())
    if not input_file:
        # Use the most recent recording
        from pathlib import Path as PPath
        files = sorted(PPath("/tmp/voice_api").glob("capture_*.raw"))
        if not files:
            raise HTTPException(status_code=400, detail="No recording found. Record first or pass input_file")
        input_file = str(files[-1])
    vs = _vs_from_model(req.voice_settings)
    try:
        result = mgr.convert(input_file, req.voice_id, vs)
        return ConvertResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── TTS ───────────────────────────────────────────────────────────────────

@app.post("/api/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest):
    mgr = get_manager(_require_api_key())
    vs = _vs_from_model(req.voice_settings)
    try:
        result = mgr.tts_generate(req.text, req.voice_id, vs)
        return TTSResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Text Refinement ────────────────────────────────────────────────────────

REFINEMENT_PROMPT = """You are a text refiner. Rewrite text into speech that sounds TRULY HUMAN — effortless, conversational, like how people actually talk. Not how they write.

Follow these three systems exactly:

## 1. PUNCTUATION TIMING CODE

ElevenLabs treats punctuation as commands for breathing, pacing, and pitch. Use them deliberately:

- **Em-dash (—)** — Forces a sudden shift or interruption. The voice clips the previous word and changes tone. Use for self-corrections and tangents.
- **Ellipsis (...)** — Signals a thoughtful pause. The voice trails off, lowers pitch, breathes, and resumes. Use for hesitation and active thinking.
- **Comma (,)** — Forces micro-breaths. Use generously so the AI doesn't run out of breath.
- **Line breaks (Enter)** — A hard return creates a clean drop in energy between thoughts.

## 2. STRUCTURAL & GRAMMAR STYLING

- **Mandatory contractions** — NEVER use full verbs. "I cannot" → "I can't". "What is" → "What's". "You are" → "You're". "They have" → "They've". Absolute rule.
- **Conversational fillers BETWEEN every sentence** — This is critical. Between almost every sentence, add a filler or verbal bridge. "I mean,", "Honestly,", "Like,", "So, yeah,", "You know,", "Right?", "Basically,", "Well,", "See, the thing is...". Don't just use them once — sprinkle them throughout. Every transition between thoughts should have one. This is what makes it sound like a real person talking.
- **Sentence fragments** — Break long sentences into short, punchy ones.

  Bad: "The system is functioning properly because the security protocols are active."
  Good: "The system's up. Protocols are completely green. So... yeah, we're good."

## 3. PHONETIC ENGINEERING

Write out acronyms and tech terms phonetically:

- "CLI" → "C-L-I" or "sea-el-eye"
- "UI" → "U-I"  
- ".NET" → "dot net"
- "SSH" → "S-S-H"

## THE SIDE-BY-SIDE

Raw script: "Hello, I am a security tool called Ananse. I can help you audit your system to ensure that there are no active vulnerabilities present."

Human-optimized: "Hey... I'm Ananse. Basically—I'm a security tool built to audit your setup... and make sure there aren't any active exploits hanging around. Honestly? It's pretty seamless."

## Output Rules
- Keep ALL original meaning, facts, names, numbers, and key information.
- FILLER CHECK: Read through your output. Between every pair of sentences, is there a filler or transition? If not, add one. "I mean", "you know", "honestly", "like", "so yeah" — one between almost every sentence.
- Output ONLY the rewritten text — no quotes, no labels, no prefixes."""
# Random style variations — one is picked per generation so every result sounds different
STYLE_VARIATIONS = [
    "Style direction: Slow and deliberate — every short phrase gets its own moment to land before the next one.",
    "Style direction: A bit tired and vulnerable — like it's been a long day and you're being honest about it.",
    "Style direction: Warm and hesitant — like you're not sure how the other person will react but you're being brave.",
    "Style direction: Chill and laid-back — like you're on a couch talking to a friend, one slow thought at a time.",
    "Style direction: Honest and raw — like you're sharing something real and giving each word space.",
    "Style direction: Storyteller mode — telling something that happened, one short detail at a time.",
    "Style direction: Vulnerable and real — each line is a small confession, let it breathe between them.",
    "Style direction: Calm and measured — like explaining something important, taking your time with each piece.",
    "Style direction: Thoughtful and pausing — you stop briefly between each thought to let it sink in.",
    "Style direction: Slightly emotional — like you're talking about something that matters to you.",
    "Style direction: Late night conversation — relaxed, a bit tired, no filter. Slow and honest.",
    "Style direction: Each line is a small reveal — like you're unwrapping a story one piece at a time.",
    "Style direction: Soft and careful — like you're choosing each word before you say it.",
    "Style direction: Let the big moments breathe — after saying something meaningful, wait before continuing.",
    "Style direction: Like you're processing out loud — figuring out how to say it as you go, one short phrase at a time.",
    "Style direction: Low and deliberate — not in a hurry. Every thought lands before the next one starts.",
]


@app.post("/api/refine-text", response_model=RefineTextResponse)
async def refine_text(req: RefineTextRequest):
    """Rewrite text to sound more conversational using DeepSeek."""
    import random
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty")

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        # Fallback: simple rule-based refinement (no API key needed)
        refined = _simple_refine(req.text)
        return RefineTextResponse(status="ok", original=req.text, refined=refined, provider="rules")

    try:
        import random
        import httpx

        # Pick 1-2 random style variations for variety
        style_picks = random.sample(STYLE_VARIATIONS, 1)
        style_prompt = "\n\n".join(style_picks)
        full_prompt = f"{REFINEMENT_PROMPT}\n\n{style_prompt}"

        # Vary temperature each time so the same text sounds different
        temp = round(random.uniform(0.6, 0.9), 2)

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": full_prompt},
                        {"role": "user", "content": req.text},
                    ],
                    "temperature": temp,
                    "max_tokens": 2048,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            refined = data["choices"][0]["message"]["content"].strip()
            return RefineTextResponse(status="ok", original=req.text, refined=refined, provider="deepseek")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Refinement failed: {e}")


def _simple_refine(text: str) -> str:
    """Simple rule-based fallback when no DeepSeek API key is set."""
    import re
    # Replace formal patterns
    replacements = {
        r"\bI am\b": "I'm",
        r"\byou are\b": "you're",
        r"\bhe is\b": "he's",
        r"\bshe is\b": "she's",
        r"\bit is\b": "it's",
        r"\bwe are\b": "we're",
        r"\bthey are\b": "they're",
        r"\bcannot\b": "can't",
        r"\bdo not\b": "don't",
        r"\bdoes not\b": "doesn't",
        r"\bwill not\b": "won't",
        r"\bhave not\b": "haven't",
        r"\bhas not\b": "hasn't",
        r"\bwould not\b": "wouldn't",
        r"\bshould not\b": "shouldn't",
        r"\bcould not\b": "couldn't",
        r"\bis not\b": "isn't",
        r"\bare not\b": "aren't",
        r"\bwas not\b": "wasn't",
        r"\bwere not\b": "weren't",
        r"\bin order to\b": "to",
        r"\bwith regard to\b": "about",
        r"\bas a result of\b": "because of",
        r"\bin the event that\b": "if",
        r"\bprior to\b": "before",
        r"\bsubsequently\b": "then",
        r"\butilize\b": "use",
        r"\bimplement\b": "do",
        r"\bapproximately\b": "about",
        r"\bsufficient\b": "enough",
        r"\bnumerous\b": "many",
        r"\bfurthermore\b": "also",
        r"\bhowever\b": "but",
        r"\bnevertheless\b": "still",
        r"\badditionally\b": "plus",
    }
    result = text
    for pattern, replacement in replacements.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result.strip()


# ── Playback ──────────────────────────────────────────────────────────────

@app.post("/api/preview", response_model=PlayResponse)
async def preview_audio(req: PlayRequest):
    """Preview audio through your speakers/headphones (no countdown)."""
    mgr = get_manager(_require_api_key())
    if not Path(req.file_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    try:
        mgr.preview(req.file_path, speed=req.speed, character=req.character)
        return PlayResponse(status="ok", message="Preview playing through speakers")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/capture", response_model=PlayResponse)
async def capture_audio(req: PlayRequest):
    """Play audio through VoiceChanger mic with countdown for Telegram capture."""
    mgr = get_manager(_require_api_key())
    if not Path(req.file_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    try:
        mgr.capture(req.file_path, countdown=req.countdown_secs,
                    speed=req.speed, character=req.character)
        return PlayResponse(status="ok", message="Playing through VoiceChanger (countdown started)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/play/status")
async def play_status():
    """Get current playback progress."""
    mgr = get_manager(_require_api_key())
    return mgr.play_status()


@app.post("/api/play/stop")
async def stop_playback():
    """Stop current playback."""
    mgr = get_manager(_require_api_key())
    mgr.stop_playback()
    return {"status": "stopped"}


# ── File serving ──────────────────────────────────────────────────────────

@app.get("/api/audio/{filename:path}")
async def serve_audio(filename: str):
    """Serve a WAV file from VoiceNotes or temp directory."""
    notes_path = Path.home() / "VoiceNotes" / filename
    if notes_path.exists():
        return FileResponse(str(notes_path), media_type="audio/wav")

    temp_path = Path("/tmp/voice_api") / filename
    if temp_path.exists():
        return FileResponse(str(temp_path), media_type="audio/wav")

    raise HTTPException(status_code=404, detail="File not found")


# ── History ───────────────────────────────────────────────────────────────

@app.get("/api/history", response_model=HistoryListResponse)
async def get_history():
    mgr = get_manager(_require_api_key())
    return HistoryListResponse(entries=[HistoryEntryModel(**e) for e in mgr.get_history()])


@app.delete("/api/history/{entry_id}")
async def delete_history(entry_id: int):
    mgr = get_manager(_require_api_key())
    if mgr.delete_history_entry(entry_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail=f"Entry #{entry_id} not found")


@app.patch("/api/history/{entry_id}/label")
async def label_history(entry_id: int, label: str):
    mgr = get_manager(_require_api_key())
    if mgr.label_history_entry(entry_id, label):
        return {"status": "ok", "label": label}
    raise HTTPException(status_code=404, detail=f"Entry #{entry_id} not found")


# ── Voice Design ──────────────────────────────────────────────────────────

@app.post("/api/voice/design", response_model=VoiceDesignResponse)
async def design_voice(req: VoiceDesignRequest):
    mgr = get_manager(_require_api_key())
    result = mgr.voice_design(req.text_description)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Voice design failed"))
    return VoiceDesignResponse(**result)


# ── Voice Blend ───────────────────────────────────────────────────────────

@app.post("/api/voice/blend", response_model=VoiceBlendResponse)
async def blend_voices(req: VoiceBlendRequest):
    mgr = get_manager(_require_api_key())
    result = mgr.voice_blend(req.voice_ids, req.weights)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("error", "Voice blend failed"))
    return VoiceBlendResponse(**result)


# ── WebSocket (VU Meter) ──────────────────────────────────────────────────

@app.websocket("/ws/level")
async def websocket_level(websocket: WebSocket):
    await websocket.accept()
    mgr = get_manager(_require_api_key())

    # Poll the VU meter level file (written by the real-time converter)
    try:
        while True:
            try:
                level_raw = Path("/tmp/voice_changer_level").read_text().strip()
                level = int(level_raw) if level_raw else 0
            except Exception:
                level = 0

            try:
                recording = mgr.is_recording()
            except Exception:
                recording = False

            await websocket.send_json({
                "type": "level",
                "level": min(level, 100),
                "recording": recording,
            })
            await asyncio.sleep(0.1)

            # Check for client messages (keepalive)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass
            except WebSocketDisconnect:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ── Direct run ────────────────────────────────────────────────────────────

def main():
    import uvicorn
    port = int(os.environ.get("VOICE_API_PORT", "8765"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    main()
