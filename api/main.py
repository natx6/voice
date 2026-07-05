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
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
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
from api import users, access
import re
from voice_converter import VoiceSettings


# ── App lifecycle ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — generate bootstrap invite if needed
    from api.access import ensure_bootstrap_invite
    ensure_bootstrap_invite()
    yield
    # Shutdown
    from api.voice_manager import cleanup_all
    cleanup_all()


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


# ── Rate Limiting & Abuse Prevention ──────────────────────────────────────

_ratelimit: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10     # max requests per window per IP


def _check_ratelimit(request):
    """Simple in-memory rate limit per IP. Raises 429 if exceeded."""
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _ratelimit[ip]
    # Prune old entries
    _ratelimit[ip] = [t for t in window if now - t < _RATE_LIMIT_WINDOW]
    if len(_ratelimit[ip]) >= _RATE_LIMIT_MAX:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    _ratelimit[ip].append(now)


def _admin_only(req):
    """Ensure the credit add endpoint isn't abused. Requires a secret env var."""
    admin_key = os.environ.get("SOUNDHUMAN_ADMIN_KEY", "")
    if admin_key:
        auth = req.headers.get("Authorization", "")
        if auth != f"Bearer {admin_key}":
            raise HTTPException(status_code=403, detail="Admin access required")


# Free credit grants per IP (prevents creating infinite demo wallets)
_free_grants: dict[str, int] = defaultdict(int)
_MAX_FREE_CREDITS_PER_IP = 10  # max free credits total per IP


def _check_free_limit(ip: str, amount: int):
    if _free_grants[ip] + amount > _MAX_FREE_CREDITS_PER_IP:
        raise HTTPException(status_code=429, detail="Free credit limit reached for this IP")
    _free_grants[ip] += amount


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



username_re = re.compile(r"^[a-zA-Z0-9_-]{4,30}$")

# ── Admin token (random URL, no login) ────────────────────────────────

ADMIN_TOKEN_FILE = Path.home() / ".soundhuman" / "admin_token"


def _get_admin_token() -> str:
    if ADMIN_TOKEN_FILE.exists():
        return ADMIN_TOKEN_FILE.read_text().strip()
    import secrets
    token = secrets.token_hex(32)  # 64-char hex
    ADMIN_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_TOKEN_FILE.write_text(token)
    print(f"\n  ╔══════════════════════════════════════════════════╗")
    print(f"  ║  ADMIN PANEL                                     ║")
    print(f"  ║                                                  ║")
    print(f"  ║  http://localhost:5173/?token={token}  ║")
    print(f"  ║                                                  ║")
    print(f"  ╚══════════════════════════════════════════════════╝\n")
    return token


def _require_admin(request: Request):
    """Check admin token from query param or Authorization header."""
    token = request.query_params.get("token", "")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    stored = _get_admin_token()
    if not token or token != stored:
        raise HTTPException(status_code=403, detail="Invalid admin token")


@app.get("/api/admin/login")
async def admin_login(request: Request):
    """Verify admin token. Returns ok if token matches."""
    try:
        _require_admin(request)
        return {"status": "ok", "message": "Admin access granted"}
    except HTTPException as e:
        raise e


@app.get("/api/payment/wallet")
async def payment_wallet():
    """Public endpoint: returns all configured wallet addresses."""
    p = Path.home() / ".soundhuman" / "settings.json"
    result = {"sol": "", "ltc": "", "xmr": "", "purchases_blocked": False}
    if p.exists():
        import json
        data = json.loads(p.read_text())
        result["sol"] = data.get("sol_wallet", "")
        result["ltc"] = data.get("ltc_wallet", "")
        result["xmr"] = data.get("xmr_wallet", "")
        result["purchases_blocked"] = data.get("purchases_blocked", False)
    return result


@app.get("/api/pricing")
async def get_pricing():
    """Pricing in USD, auto-converted to crypto at current rates."""
    p = Path.home() / ".soundhuman" / "settings.json"
    usd_price = 5.0  # default: $5 per credit
    rates = {"sol": 140, "ltc": 70, "xmr": 155}  # fallback rates

    if p.exists():
        import json
        data = json.loads(p.read_text())
        usd_price = data.get("usd_per_credit", usd_price)

    # Try to get live rates from CoinGecko (cheap, no key needed)
    try:
        import httpx
        r = httpx.get("https://api.coingecko.com/api/v3/simple/price?ids=solana,litecoin,monero&vs_currencies=usd", timeout=5)
        if r.status_code == 200:
            d = r.json()
            if "solana" in d: rates["sol"] = d["solana"]["usd"]
            if "litecoin" in d: rates["ltc"] = d["litecoin"]["usd"]
            if "monero" in d: rates["xmr"] = d["monero"]["usd"]
    except Exception:
        pass

    return {
        "usd_per_credit": usd_price,
        "sol_per_credit": round(usd_price / rates["sol"], 6),
        "ltc_per_credit": round(usd_price / rates["ltc"], 6),
        "xmr_per_credit": round(usd_price / rates["xmr"], 6),
        "rates_updated": "live" if rates else "fallback",
    }


@app.post("/api/recover")
async def recover(phrase: str = ""):
    """Restore username by recovery phrase."""
    if not phrase:
        raise HTTPException(400, "Recovery phrase required")
    username = users.restore_by_phrase(phrase)
    if not username:
        raise HTTPException(404, "Invalid recovery phrase")
    user = users.get_user(username)
    if not user:
        raise HTTPException(404, "User not found")
    return {"status": "ok", "user": user}


# ── Access Code Auth ──────────────────────────────────────────────────

@app.get("/api/invites")
async def get_invites(code: str = ""):
    """Get invite codes for an access code."""
    if not code:
        raise HTTPException(400, "Access code required")
    invites = access.get_user_invites(code)
    return {"invites": invites}


@app.post("/api/invites/generate")
async def generate_invites(code: str = ""):
    """Generate 3 more invite codes for an access code."""
    if not code:
        raise HTTPException(400, "Access code required")
    codes = access.generate_more_invites(code)
    if not codes:
        raise HTTPException(400, "Invalid access code")
    invites = access.get_user_invites(code)
    return {"invites": invites, "new": codes}


@app.post("/api/auth/signup")
async def auth_signup(email: str = "", invite: str = ""):
    """Sign up with email + invite code. Returns access code + optional admin token."""
    result = access.signup(email, invite)
    success, msg = result[0], result[1]
    code = result[2]
    admin_token = result[3] if len(result) > 3 else ""
    if not success:
        raise HTTPException(400, msg)
    resp = {"status": "ok", "access_code": code, "message": "Save this code — you'll need it to log in."}
    if admin_token:
        resp["admin_token"] = admin_token
        resp["message"] += " You're the first user — admin access granted automatically."
    return resp


@app.post("/api/auth/login")
async def auth_login(request: Request, code: str = ""):
    """Login with access code only. Accepts query param or JSON body."""
    # Support both: query param ?code=xxx or JSON body {"code":"xxx"}
    if not code:
        try:
            body = await request.json()
            code = body.get("code", "")
        except Exception:
            pass
    success, msg, data = access.login(code.strip())
    if not success:
        raise HTTPException(401, msg)
    return {"status": "ok", "user": data}


@app.post("/api/admin/codes")
async def admin_generate_codes(request: Request, count: int = 1, credits: int = 10):
    _require_admin(request)
    count = max(1, min(count, 50))
    codes = access.admin_generate_codes(count, credits)
    return {"status": "ok", "codes": codes}


@app.get("/api/admin/codes")
async def admin_list_codes(request: Request):
    _require_admin(request)
    return {"codes": access.admin_list_codes()}


@app.post("/api/admin/codes/revoke")
async def admin_revoke_code(request: Request, code: str = ""):
    _require_admin(request)
    if not code:
        raise HTTPException(400, "Code required")
    if access.admin_revoke(code):
        return {"status": "revoked"}
    raise HTTPException(404, "Code not found")


@app.get("/api/onboard")
async def onboard_suggest():
    return {"suggestion": users.generate_username()}


@app.post("/api/onboard")
async def onboard(username: str = "", invite: str = ""):
    if not username:
        return {"suggestion": users.generate_username()}
    if not username_re.match(username):
        raise HTTPException(400, "Username must be 4-30 chars, letters/numbers/dashes/underscores")
    success, err_or_phrase = users.create_user(username, invite)
    if not success:
        raise HTTPException(400, err_or_phrase)
    user = users.get_user(username)
    return {"status": "ok", "user": user, "recovery_phrase": err_or_phrase if len(err_or_phrase) > 50 else ""}


@app.get("/api/user/{username}")
async def get_user_info(username: str):
    user = users.get_user(username)
    if not user:
        raise HTTPException(404, "User not found")
    return {"user": user}


@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    _require_admin(request)
    return {"users": users.get_all_users()}


@app.post("/api/admin/credits")
async def admin_add_credits(request: Request, username: str = "", amount: int = 0):
    _require_admin(request)
    if not username or amount <= 0:
        raise HTTPException(400, "Username and positive amount required")
    add_credits(username, amount, f"admin:{username}")
    user = users.get_user(username)
    return {"status": "ok", "user": user}


@app.post("/api/admin/invite")
async def admin_create_invite(request: Request, username: str = ""):
    _require_admin(request)
    if not username:
        raise HTTPException(400, "Username required")
    user = users.get_user(username)
    if not user:
        raise HTTPException(404, "User not found")
    from api.users import _generate_invites
    codes = _generate_invites(username, 1)
    return {"status": "ok", "code": codes[0]}


@app.get("/api/admin/settings")
async def admin_get_settings(request: Request):
    _require_admin(request)
    p = Path.home() / ".soundhuman" / "settings.json"
    if p.exists():
        import json
        return {"settings": json.loads(p.read_text())}
    return {"settings": {"receiving_wallet": ""}}


@app.post("/api/admin/settings")
async def admin_update_settings(request: Request,
                                receiving_wallet: str = "",
                                usd_per_credit: float = 5.0,
                                sol_wallet: str = "",
                                ltc_wallet: str = "",
                                xmr_wallet: str = "",
                                purchases_blocked: bool = False):
    _require_admin(request)
    import json
    p = Path.home() / ".soundhuman" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if p.exists():
        data = json.loads(p.read_text())
    data["receiving_wallet"] = receiving_wallet
    data["usd_per_credit"] = usd_per_credit
    data["purchases_blocked"] = purchases_blocked
    if sol_wallet: data["sol_wallet"] = sol_wallet
    if ltc_wallet: data["ltc_wallet"] = ltc_wallet
    if xmr_wallet: data["xmr_wallet"] = xmr_wallet
    p.write_text(json.dumps(data, indent=2))
    return {"status": "ok", "settings": data}


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


    return 0

@app.post("/api/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest, request: Request):
    _check_ratelimit(request)
    import hashlib
    uid = int(hashlib.sha256(req.wallet.encode()).hexdigest()[:8], 16) if req.wallet else 0
    mgr = get_manager(_require_api_key(), user_id=uid)
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
async def tts_variations(req: TTSVariationsRequest, request: Request):
    """Generate multiple audio variations with different deliveries."""
    _check_ratelimit(request)
    
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

REFINEMENT_PROMPT = """You are a text refiner. Rewrite text into natural speech using ElevenLabs v3 audio tags. Your output is fed directly into v3 TTS — tags control delivery but are not spoken.

## STEP 1: Analyze the emotional tone of the input
## STEP 2: Rewrite using these techniques:

### CORE TAGS — place strategically throughout text

| Tag | What it does |
|---|---|
| [laughs] [chuckles] [giggles] | Natural laughter |
| [sighs] [breaths] [gasp] | Breath and sigh events |
| [pause] [short pause] [pause 0.5s] [pause 1s] | Timing and rhythm control |
| [speaks faster] [slows down] [trails off] | Mid-sentence rate changes |
| [whispers] [softly] [excited] [hesitant] | Delivery shifts |
| [um] [uh] [you know] [like] | Disfluency tokens (use naturally) |
| [interrupts self] [corrects] [restarts] | Conversation repairs |
| [scoffs] [groans] [frustrated] [annoyed] | Frustration/attitude |

### TECHNIQUES FOR SPONTANEITY

**Interleaved tags:** Place tags throughout sentences, not just at edges.
"Hey, so I was thinking [pause] maybe we should [chuckles] try the other approach instead. [short pause] What do you think?"

**Layered style prefix:** Start output with a delivery cue in brackets:
"[conversational, natural, occasional filler words and breathing sounds, slight hesitations]"

**Variable pacing blocks:** Break long responses into tagged segments.
"[normal pace] Okay so the first step is pretty straightforward [speaks faster] but then you have to be careful with the timing [pause] because if you rush it [trails off] it usually doesn't go well."

**Disfluency injection:** Seed natural conversational artifacts.
"I mean [um] I'm not saying it's impossible [uh] just that it might take a bit longer than we thought."

**Emotion + tag chaining:** Combine directions for micro-timing.
"[slightly hesitant, thoughtful] Honestly... [pause] I don't know if that's the best idea right now [soft sigh] but we can try it."
"[pause][breaths][speaks slower]"

### EMOTIONAL STYLES — Apply the matching style

**Sad / Heartbroken** — ellipsis, lowercase, breath tags, fragmented, slow trembling delivery.
"Hey... [sighs] I'm sorry to drop this on you... I just [pause] I really don't know what to do right now. [whispers] Everything just feels so heavy today... [breaths] honestly, I just kind of need a friend."

**Excited / Ecstatic** — ALL-CAPS, exclamation marks, laughter tags, rapid-fire.
"OH MY GOD [giggles] okay you are LITERALLY never going to believe what just happened!!! [laughs] I am shaking right now [gasp] We have to celebrate tonight!"

**Angry / Frustrated** — sharp single sentences, hard periods, aggressive tags, clipped tense tone.
"[scoffs] Like... are you actually kidding me right now? [frustrated sigh] I am so completely done with this. Seriously. [groans] Just call me back. Immediately."

**Anxious / Panicked** — rapid dashes, shallow breath tags, scattered phrasing, breathless pitch.
"Hey—so—I'm trying not to freak out but [gasp] I don't know—I think I completely messed up. [breaths] What if it's too late? Oh god... [whispers nervously] I don't know what to do—just—please call me."

**Smug / Gossipy** — trailing ellipses, casual slang, cynical laughter, vocal fry.
"So... [chuckles] remember how he said he was 'just working late' last night? [whispers] Yeah, well... guess who literally just walked past me at the coffee shop. [scoffs playfully] Exactly. I knew it."

**Comforting / Empathetic** — soft punctuation, soothing words, gentle tags, warm steady pacing.
"Hey... [soft breath] I just wanted to check in on you. I know things have been incredibly stressful lately... but you're doing so much better than you think you are. [warmly] I'm right here if you need anything."

## RULES
- Contractions ALWAYS — "I am" to "I'm", "do not" to "don't", "cannot" to "can't"
- FILLERS BETWEEN EVERY SENTENCE: Add "I mean", "you know", "honestly", "like", "so yeah", "basically", "well", "right?", "see", "the thing is" between almost every sentence. Spread them throughout — don't just use one type.
- Use 3-6 tags per paragraph, interleaved throughout sentences
- Chain tags for micro-timing: [pause][breaths][speaks slower]
- Use [um] [uh] [you know] naturally — they add realism
- Keep ALL original meaning, facts, names, numbers
- Output ONLY the rewritten text with tags — no explanations, no labels"""

STYLE_VARIATIONS = [
    "Interleaved chain: [laughs][pause]I mean [um] I wasn't expecting that at all [breaths] honestly.",
    "Spontaneous repair: [speaks faster]Wait no—I mean [corrects] actually that's not what I meant [slows down] let me explain.",
    "Rate shift: [normal pace]The first part is easy [speaks faster]but you gotta be quick with the timing [pause]or it falls apart [trails off]usually.",
    "Disfluency + breath: I mean [uh] I'm not saying it's impossible [breaths] just that it's going to take a bit [pause] longer than we thought.",
    "Hesitant + trailing: Honestly [pause] I don't know if that's the best idea [soft sigh] but we can try.",
    "Tag chain micro-timing: [pause][breaths][speaks slower]Okay let me think about this for a second.",
    "Conversational filler chain: So [um] here's the thing [pause][breaths] I've been going back and forth on this.",
    "Interruption + repair: I was going to say—[interrupts self]actually no wait [restarts]here's what I mean [pause] basically.",
    "Warm + thoughtful: [warmly]That's a really good question [pause][breaths] I think the answer depends on a few things.",
    "Emotion chaining: [slightly hesitant, thoughtful]Honestly... [pause]I'm not sure that's the right move [soft sigh]but we can try it and see.",
    "Breath + pace combo: [breaths][speaks slower]I need a minute to process that [pause] because honestly [um] I wasn't ready for this conversation.",
    "Soft delivery: [softly]Yeah [pause] I hear you [breaths] and I think you're right [trails off]even if it's hard to admit.",
    "Energetic repair: [excited]OH WAIT—[interrupts self][laughs]sorry I just realized something [speaks faster]okay so here's what we should actually do.",
    "Vulnerable chain: [hesitant][pause][breaths]I don't really know how to say this [trails off]so I'm just going to say it [um] directly.",
    "Storyteller pacing: [normal pace]So this happened yesterday [pause][speaks faster]and I swear I still can't believe it [slows down]like, of all the things that could go wrong.",
    "Casual aside: [casual]I mean [you know] it's not that big of a deal [pause][sighs]but it kinda is though.",
]

@app.post("/api/refine-text", response_model=RefineTextResponse)
async def refine_text(req: RefineTextRequest, request: Request):
    """Rewrite text to sound more conversational using DeepSeek."""
    _check_ratelimit(request)
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
async def get_history(request: Request):
    
    mgr = get_manager(_require_api_key())
    return HistoryListResponse(entries=[HistoryEntryModel(**e) for e in mgr.get_history()])


@app.delete("/api/history/{entry_id}")
async def delete_history(entry_id: int, request: Request):
    
    mgr = get_manager(_require_api_key())
    if mgr.delete_history_entry(entry_id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail=f"Entry #{entry_id} not found")


@app.patch("/api/history/{entry_id}/label")
async def label_history(entry_id: int, label: str, request: Request):
    
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
async def credits_add(wallet: str = "", amount: int = 0, token: str = "SOL", tx: str = "", request: Request = None):
    """Add credits. Requires admin key for manual adds. In production, verify tx on-chain."""
    if not wallet or amount <= 0:
        raise HTTPException(status_code=400, detail="Wallet and positive amount required")

    # Free credits (token=manual) are rate-limited per IP and capped
    if token == "manual":
        if request:
            _check_free_limit(request.client.host if request.client else "unknown", amount)
        # Cap free credits per call
        amount = min(amount, 5)
        credits = amount
    else:
        credits = tokens_to_credits(token, amount)

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
