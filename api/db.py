"""SQLite database for auth, invites, API keys, and settings."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path.home() / ".soundhuman" / "app.db"
SECRET_KEY = os.environ.get("SOUNDHUMAN_SECRET", secrets.token_hex(32))
_lock = threading.RLock()  # RLock so same thread can re-acquire


def _get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init():
    """Create tables if they don't exist."""
    with _lock:
        conn = _get_db()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                wallet TEXT DEFAULT '',
                role TEXT DEFAULT 'user',
                credits_granted INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                created_by INTEGER,
                used_by INTEGER,
                used_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (used_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                key TEXT UNIQUE NOT NULL,
                name TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            INSERT OR IGNORE INTO settings (key, value) VALUES ('receiving_wallet', '');
        """)
        conn.commit()

        # Create initial admin invite if no users exist
        row = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
        if row and row['c'] == 0:
            code = secrets.token_urlsafe(12)
            conn.execute("INSERT INTO invite_codes (code) VALUES (?)", (code,))
            conn.commit()
            print(f"\n  ╔═══════════════════════════════════════╗")
            print(f"  ║  FIRST RUN — Admin invite code:       ║")
            print(f"  ║                                      ║")
            print(f"  ║    {code}        ║")
            print(f"  ║                                      ║")
            print(f"  ╚═══════════════════════════════════════╝\n")
        conn.commit()


# ── Password hashing ────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
    return f"{salt}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
        computed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100_000)
        return hmac.compare_digest(computed.hex(), h)
    except Exception:
        return False


# ── Token management ───────────────────────────────────────────────────

def create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    expires = time.time() + 86400 * 7  # 7 days
    with _lock:
        conn = _get_db()
        conn.execute("INSERT INTO tokens (token, user_id, expires_at) VALUES (?, ?, ?)",
                     (token, user_id, expires))
        conn.commit()
    return token


def verify_token(token: str) -> Optional[dict]:
    with _lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT u.id, u.email, u.role, u.wallet FROM tokens t JOIN users u ON t.user_id = u.id WHERE t.token = ? AND t.expires_at > ?",
            (token, time.time())
        ).fetchone()
        if row:
            return dict(row)
    return None


def delete_token(token: str):
    with _lock:
        conn = _get_db()
        conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
        conn.commit()


# ── User management ───────────────────────────────────────────────────

def create_user(email: str, password: str, invite_code: str) -> tuple[bool, str]:
    """Create a user. Returns (success, error_message)."""
    with _lock:
        conn = _get_db()

        # Verify invite code
        invite = conn.execute(
            "SELECT id FROM invite_codes WHERE code = ? AND used_by IS NULL", (invite_code,)
        ).fetchone()
        if not invite:
            return False, "Invalid or used invite code"

        # Check email uniqueness
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return False, "Email already registered"

        # Create user — first user gets admin role
        existing_count = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()
        role = 'admin' if (not existing_count or existing_count['c'] == 0) else 'user'
        pwd_hash = hash_password(password)
        cursor = conn.execute(
            "INSERT INTO users (email, password_hash, role) VALUES (?, ?, ?)",
            (email, pwd_hash, role)
        )
        user_id = cursor.lastrowid

        # Mark invite as used
        conn.execute("UPDATE invite_codes SET used_by = ?, used_at = datetime('now') WHERE id = ?",
                     (user_id, invite['id']))
        conn.commit()
        return True, ""


def authenticate(email: str, password: str) -> tuple[bool, str, Optional[str]]:
    """Returns (success, error_message, token)."""
    with _lock:
        conn = _get_db()
        row = conn.execute("SELECT id, email, password_hash, role FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            return False, "Invalid email or password", None
        if not verify_password(password, row['password_hash']):
            return False, "Invalid email or password", None
        token = create_token(row['id'])
        return True, "", token


def get_user_by_email(email: str) -> Optional[dict]:
    with _lock:
        conn = _get_db()
        row = conn.execute("SELECT id, email, role, wallet, created_at FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            return dict(row)
    return None


def get_user(user_id: int) -> Optional[dict]:
    with _lock:
        conn = _get_db()
        row = conn.execute("SELECT id, email, role, wallet, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            return dict(row)
    return None


def get_all_users() -> list[dict]:
    with _lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, email, role, wallet, created_at FROM users ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


def update_wallet(user_id: int, wallet: str):
    with _lock:
        conn = _get_db()
        conn.execute("UPDATE users SET wallet = ? WHERE id = ?", (wallet, user_id))
        conn.commit()


# ── Invite codes ─────────────────────────────────────────────────────

def create_invite_code(created_by: int) -> str:
    code = secrets.token_urlsafe(12)
    with _lock:
        conn = _get_db()
        conn.execute("INSERT INTO invite_codes (code, created_by) VALUES (?, ?)", (code, created_by))
        conn.commit()
    return code


def get_invite_codes() -> list[dict]:
    with _lock:
        conn = _get_db()
        rows = conn.execute(
            "SELECT ic.*, u.email as used_by_email FROM invite_codes ic LEFT JOIN users u ON ic.used_by = u.id ORDER BY ic.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ── API Keys ─────────────────────────────────────────────────────────

def create_api_key(user_id: int, name: str = "") -> str:
    key = f"sh_{secrets.token_hex(24)}"
    with _lock:
        conn = _get_db()
        conn.execute("INSERT INTO api_keys (user_id, key, name) VALUES (?, ?, ?)", (user_id, key, name))
        conn.commit()
    return key


def verify_api_key(key: str) -> Optional[dict]:
    with _lock:
        conn = _get_db()
        row = conn.execute(
            "SELECT ak.*, u.email, u.role FROM api_keys ak JOIN users u ON ak.user_id = u.id WHERE ak.key = ?",
            (key,)
        ).fetchone()
        if row:
            return dict(row)
    return None


def get_api_keys(user_id: int) -> list[dict]:
    with _lock:
        conn = _get_db()
        rows = conn.execute("SELECT id, key, name, created_at FROM api_keys WHERE user_id = ? ORDER BY id", (user_id,)).fetchall()
        return [dict(r) for r in rows]


def delete_api_key(key: str, user_id: int) -> bool:
    with _lock:
        conn = _get_db()
        cur = conn.execute("DELETE FROM api_keys WHERE key = ? AND user_id = ?", (key, user_id))
        conn.commit()
        return cur.rowcount > 0


# ── Settings ──────────────────────────────────────────────────────────

def get_setting(key: str) -> str:
    with _lock:
        conn = _get_db()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row['value'] if row else ""


def set_setting(key: str, value: str):
    with _lock:
        conn = _get_db()
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def get_all_settings() -> dict:
    with _lock:
        conn = _get_db()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r['key']: r['value'] for r in rows}
