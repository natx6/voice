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
    TTSRequest, TTSResponse, TTSVariationsRequest, TTSVariationsResponse,
    PlayRequest, PlayResponse, PlayStatusResponse,
    VoiceSettingsModel, VoicesResponse, VoiceModel,
    VoiceDesignRequest, VoiceDesignResponse,
    VoiceBlendRequest, VoiceBlendResponse,
    HistoryEntryModel, HistoryListResponse,
    RefineTextRequest, RefineTextResponse,
    StatusResponse,
)
from api.voice_manager import get_manager, VoiceManager
from api.credits import get_balance, add_credits, deduct_credit, tokens_to_credits
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

def _deduct_or_raise(wallet: str, amount: int = 1):
    """Check credits and deduct if sufficient. Raises 402 if not."""
    if not wallet:
        return  # No wallet = free (demo mode)
    from api.credits import deduct_credit, get_balance
    for _ in range(amount):
        if not deduct_credit(wallet):
            bal = get_balance(wallet)
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. Balance: {bal}, needed: {amount}",
            )


@app.post("/api/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest):
    mgr = get_manager(_require_api_key())
    vs = _vs_from_model(req.voice_settings)
    _deduct_or_raise(req.wallet, 1)
    try:
        result = mgr.tts_generate(req.text, req.voice_id, vs)
        return TTSResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tts/variations", response_model=TTSVariationsResponse)
async def tts_variations(req: TTSVariationsRequest):
    """Generate multiple audio variations with different deliveries."""
    mgr = get_manager(_require_api_key())
    vs = _vs_from_model(req.voice_settings)
    count = max(2, min(req.count, 5))
    _deduct_or_raise(req.wallet, count)
    try:
        results = mgr.tts_generate_variations(req.text, req.voice_id, vs, count=count)
        return TTSVariationsResponse(status="ok", variations=results)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Text Refinement ────────────────────────────────────────────────────────

REFINEMENT_PROMPT = """You are a text refiner. Your job is two steps:
1. ANALYZE the emotional tone of the input text
2. REWRITE it using the matching emotional style below with ElevenLabs v3 audio tags

## EMOTIONAL STYLES — Match the text to the closest one

### 1. Sad / Heartbroken
Use constant ellipses (...), lowercase phrasing, heavy bracketed breath tags, fragmented sentences.
"You want slow, trembling, hesitant delivery."
"Hey... [sighs] I'm sorry to drop this on you... I just... I really don't know what to do right now. [whispers] Everything just feels so heavy today... honestly, I just kind of need a friend. Call me whenever you can, okay? Bye."

### 2. Excited / Ecstatic
Use ALL-CAPS on high-energy words, multiple exclamation marks, run-on sentences, expressive laughter tags.
"You want rapid-fire, high-pitch delivery."
"OH MY GOD [giggles] okay you are LITERALLY never going to believe what just happened!!! [laughs] I am shaking right now, like, it actually happened! [gasp] We have to celebrate tonight, seriously, call me back the SECOND you see this!"

### 3. Angry / Frustrated
Use sharp, blunt single sentences, hard periods, aggressive behavioral tags.
"You want fast, clipped, tense tone."
"[scoffs] Like... are you actually kidding me right now? [frustrated sigh] I am so completely done with this. Seriously. [groans] Do not even try to make an excuse. Just call me back immediately. I'm so over it."

### 4. Anxious / Panicked
Use rapid dashes (—) for interrupted thoughts, shallow breath tags, repetitive scattered phrasing.
"You want racing heartbeat, breathless pitch."
"Hey—so—I'm trying not to freak out but [gasp] I don't know—I think I completely messed up. [rapid breathing] What if it's too late? Oh god... [whispers nervously] I literally don't know what to do right now, my head is spinning—just—please call me as soon as you can."

### 5. Smug / Gossipy
Use trailing ellipses, casual modern slang, cynical laughter tags.
"You want low register, vocal fry, slow rhythmic cadence."
"So... [chuckles] remember how he said he was 'just working late' last night? [whispers] Yeah, well... guess who literally just walked past me at the coffee shop. [scoffs playfully] Exactly. I knew it. Oh, we have so much to talk about later."

### 6. Comforting / Empathetic
Use soft punctuation, long soothing words, gentle action tags.
"You want velvety warm, low-register, steady calming pacing."
"Hey... [soft breath] I just wanted to check in on you. I know things have been incredibly stressful lately... but you're doing so much better than you think you are. [smiling softly] Just take a deep breath, okay? I'm right here if you need anything at all."

## RULES
- First detect the emotion, then apply THAT style's formatting and tags
- Use 1-3 audio tags per paragraph placed naturally before or after text
- Contractions ALWAYS — "I am" to "I'm", "do not" to "don't"
- NEVER add non-verbal sounds like "mmhm", "ahaa", "uh", "um", "hmm"
- Keep ALL original meaning, facts, names, numbers
- Output ONLY the rewritten text with tags — no explanations, no labels"""

STYLE_VARIATIONS = [
    "Style direction: Slow and deliberate. Use [pause 1s] between thoughts and [sighs] or [thoughtful] for processing.",
    "Style direction: A bit tired and vulnerable. Use [sighs], [hesitant], and [pause 1s] for awkward pauses.",
    "Style direction: Warm and hesitant. Use [pause 1s] before important reveals and [warmly] for reassurance.",
    "Style direction: Chill and laid-back. Use [casual], [laughs], and [pause 2s] between stories.",
    "Style direction: Honest and raw. Use [sighs], [pause 1s] before the hard part, [relieved] at the end.",
    "Style direction: Storyteller mode. Use [pause 2s] between key moments and [laughs] or [gasp] for reactions.",
    "Style direction: Vulnerable and real. Use [hesitant], [pause 1s], and [whispers] for the emotional reveal.",
    "Style direction: Calm and measured. Use [thoughtful], [pause 2s] after important points, [warmly].",
    "Style direction: Slightly emotional. Use [frustrated], [sighs], [pause 1s], then [relieved] at resolution.",
    "Style direction: Late night conversation. Use [casual], [laughs], [pause 1s] while thinking, [yawns] maybe.",
    "Style direction: Soft and careful. Use [whispers], [hesitant], [pause 2s] between each thought.",
    "Style direction: Let big moments breathe. Use [pause 2s] after key lines, [sighs] before the next thought.",
    "Style direction: Processing out loud. Use [pause 1s], [thoughtful], [sighs], [hesitant] as you figure it out.",
    "Style direction: Low and deliberate. Use [pause 2s] between every thought. [serious] tone. Let each line land.",
    "Style direction: Anxious and urgent. Use [frustrated], [sighs], [impatient], short rapid sentences.",
    "Style direction: Warm and encouraging. Use [warmly], [laughs], [pause 1s] for emphasis, [excitedly] at good news.",
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

        # If user specified a style, inject it. Otherwise use random variation.
        style_override = ""
        if req.style and req.style != "auto":
            style_labels = {
                "sad": "Style to use: SAD / HEARTBROKEN. Constant ellipses, lowercase, breath tags, fragmented. Slow trembling delivery.",
                "excited": "Style to use: EXCITED / ECSTATIC. ALL-CAPS, exclamation marks, run-on sentences, laughter tags. Rapid high-pitch delivery.",
                "angry": "Style to use: ANGRY / FRUSTRATED. Sharp blunt sentences, hard periods, aggressive tags. Clipped tense tone.",
                "anxious": "Style to use: ANXIOUS / PANICKED. Rapid dashes, shallow breath tags, scattered phrasing. Breathless pitch.",
                "smug": "Style to use: SMUG / GOSSIPY. Trailing ellipses, casual slang, cynical laughter tags. Low register, vocal fry.",
                "comforting": "Style to use: COMFORTING / EMPATHETIC. Soft punctuation, long soothing words, gentle tags. Warm steady pacing.",
            }
            style_override = style_labels.get(req.style, "")

        style_prompt = ""
        if style_override:
            style_prompt = style_override
        else:
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


# ── Credits ──────────────────────────────────────────────────────────────

@app.get("/api/credits/balance")
async def credits_balance(wallet: str = ""):
    """Get credit balance for a wallet address."""
    if not wallet:
        raise HTTPException(status_code=400, detail="Wallet address required")
    balance = get_balance(wallet)
    return {"wallet": wallet, "balance": balance, "price_per_gen": 0.005, "token": "SOL"}


@app.post("/api/credits/deduct")
async def credits_deduct(wallet: str = ""):
    """Deduct one credit for a generation."""
    if not wallet:
        raise HTTPException(status_code=400, detail="Wallet address required")
    if deduct_credit(wallet):
        balance = get_balance(wallet)
        return {"status": "ok", "balance": balance}
    raise HTTPException(status_code=402, detail="Insufficient credits")


@app.post("/api/credits/add")
async def credits_add(wallet: str = "", amount: int = 0, token: str = "SOL", tx: str = ""):
    """Add credits after payment verification. In production, verify tx on-chain."""
    if not wallet or amount <= 0:
        raise HTTPException(status_code=400, detail="Wallet and positive amount required")
    credits = tokens_to_credits(token, amount) if token != "manual" else amount
    balance = add_credits(wallet, credits, source=f"{token}:{tx}" if tx else token)
    return {"status": "ok", "wallet": wallet, "credits_added": credits, "balance": balance}


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
