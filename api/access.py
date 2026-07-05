"""Access code system. User signs up with email + invite, gets access code, logs in with code only."""

from __future__ import annotations

import json
import secrets
import threading
import hashlib
from pathlib import Path

DATA_DIR = Path.home() / ".soundhuman"
_lock = threading.Lock()


def _p(name: str) -> Path:
    return DATA_DIR / name


def _load(name: str) -> dict:
    p = _p(name)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return {}
    return {}


def _save(name: str, data: dict):
    p = _p(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.rename(p)


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def generate_access_code() -> str:
    """Generate a 20-char alphanumeric access code."""
    return secrets.token_hex(10)


def signup(email: str, invite_code: str) -> tuple[bool, str, str]:
    """Sign up with email + invite code. Returns (success, msg, access_code)."""
    with _lock:
        if not email or "@" not in email:
            return False, "Valid email required", ""
        if not invite_code:
            return False, "Invite code required", ""

        # Check invite validity
        invites = _load("invites.json")
        if invite_code not in invites or invites[invite_code].get("used_by"):
            return False, "Invalid or used invite code", ""

        # Generate access code
        code = generate_access_code()
        email_hash = _hash_email(email)

        codes = _load("access_codes.json")
        codes[code] = {
            "email": email,
            "email_hash": email_hash,
            "invite_code": invite_code,
            "credits_granted": 2,
            "credits_used": 0,
            "device_id": "",
            "active": True,
            "created": str(__import__("datetime").datetime.now())[:19],
        }
        _save("access_codes.json", codes)

        # Mark invite used
        inviter = None
        if invite_code in invites:
            inviter = invites[invite_code].get("created_by")
            invites[invite_code]["used_by"] = email_hash
            _save("invites.json", invites)

        # Grant 2 free credits
        from api.credits import add_credits as add_c
        add_c(code, 2, f"signup:{email_hash}")

        # Give inviter 1 bonus credit and generate 5 invite codes for new user
        if inviter:
            add_c(inviter, 1, f"invite_bonus:{email_hash}")
            # Generate 2 invite codes for the new user
            user_codes = []
            for _ in range(2):
                ic = secrets.token_urlsafe(10)
                invites[ic] = {"created_by": code, "used_by": None}
                user_codes.append(ic)
            _save("invites.json", invites)
            codes[code]["invite_codes"] = user_codes
            _save("access_codes.json", codes)

        return True, "", code


def login(code: str, device_id: str = "") -> tuple[bool, str, dict]:
    """Login with access code. Returns (success, msg, data)."""
    with _lock:
        codes = _load("access_codes.json")
        if code not in codes:
            return False, "Invalid access code", {}
        entry = codes[code]
        if not entry.get("active", True):
            return False, "Access code has been revoked", {}

        # Register device on first use
        if not entry.get("device_id") and device_id:
            entry["device_id"] = device_id
        elif device_id and entry.get("device_id") and entry["device_id"] != device_id:
            # Different device — still allow but flag it
            entry["device_id"] = f"{entry.get('device_id')},{device_id}"

        codes[code] = entry
        _save("access_codes.json", codes)

        from api.credits import get_balance
        balance = get_balance(code)

        return True, "", {
            "code": code[:8] + "...",
            "email": entry.get("email", ""),
            "balance": balance,
            "credits_granted": entry.get("credits_granted", 0),
            "device_id": entry.get("device_id", ""),
            "created": entry.get("created", ""),
        }


def admin_generate_codes(count: int, credits: int = 2) -> list[dict]:
    """Admin generates access codes pre-loaded with credits."""
    with _lock:
        codes = _load("access_codes.json")
        from api.credits import add_credits as add_c
        result = []
        for _ in range(count):
            code = generate_access_code()
            codes[code] = {
                "email": "",
                "email_hash": "",
                "invite_code": "admin",
                "credits_granted": credits,
                "credits_used": 0,
                "device_id": "",
                "active": True,
                "created": str(__import__("datetime").datetime.now())[:19],
            }
            add_c(code, credits, f"admin_generated:{code}")
            result.append({"code": code, "credits": credits})
        _save("access_codes.json", codes)
        return result


def admin_revoke(code: str) -> bool:
    with _lock:
        codes = _load("access_codes.json")
        if code not in codes:
            return False
        codes[code]["active"] = False
        _save("access_codes.json", codes)
        return True


def get_user_invites(code: str) -> list[dict]:
    """Get invite codes belonging to an access code."""
    codes_data = _load("access_codes.json")
    if code not in codes_data:
        return []
    user_codes = codes_data[code].get("invite_codes", [])
    invites = _load("invites.json")
    result = []
    for ic in user_codes:
        if ic in invites:
            used = invites[ic].get("used_by")
            result.append({"code": ic, "used": bool(used)})
    return result


def ensure_bootstrap_invite() -> str:
    """On first run, generate a bootstrap invite code and print it."""
    with _lock:
        invites = _load("invites.json")
        # If there are any unused invites, don't create one
        for ic, data in invites.items():
            if not data.get("used_by"):
                return ""
        # No available invites — create one
        code = secrets.token_urlsafe(10)
        invites[code] = {"created_by": "bootstrap", "used_by": None}
        _save("invites.json", invites)
        print(f"\n  ╔═══════════════════════════════════════════╗")
        print(f"  ║  BOOTSTRAP INVITE CODE                    ║")
        print(f"  ║                                          ║")
        print(f"  ║    {code}          ║")
        print(f"  ║                                          ║")
        print(f"  ║  Use this to sign up as the first user.  ║")
        print(f"  ╚═══════════════════════════════════════════╝\n")
        return code


def generate_more_invites(code: str, count: int = 3) -> list[str]:
    """Generate additional invite codes for an existing user."""
    with _lock:
        codes_data = _load("access_codes.json")
        if code not in codes_data:
            return []
        invites = _load("invites.json")
        existing = codes_data[code].get("invite_codes", [])
        new_codes = []
        for _ in range(count):
            ic = secrets.token_urlsafe(10)
            invites[ic] = {"created_by": code, "used_by": None}
            new_codes.append(ic)
        existing.extend(new_codes)
        codes_data[code]["invite_codes"] = existing
        _save("access_codes.json", codes_data)
        _save("invites.json", invites)
        return new_codes


def admin_generate_codes(count: int, credits: int = 2) -> list[dict]:
    codes = _load("access_codes.json")
    result = []
    for code, data in codes.items():
        from api.credits import get_balance
        result.append({
            "code": code[:12] + "...",
            "email": data.get("email", ""),
            "active": data.get("active", True),
            "balance": get_balance(code),
            "credits_granted": data.get("credits_granted", 0),
            "device": bool(data.get("device_id")),
            "created": data.get("created", ""),
        })
    return sorted(result, key=lambda x: x["created"], reverse=True)
