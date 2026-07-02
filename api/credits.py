"""Simple credit system keyed by wallet address.

Stores balances in a JSON file. No database needed.
Supports SOL, USDC, ETH — all converted to a unified credit.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Optional

CREDITS_FILE = Path.home() / ".soundhuman" / "credits.json"
_lock = threading.Lock()

# Price config (credits per generation)
CREDITS_PER_GEN = 1

# Token conversion (what 1 unit of token buys in credits)
# These are approximate and should be updated with real price feeds
TOKEN_RATES = {
    "SOL": 100,    # 1 SOL = 100 credits
    "USDC": 0.2,   # 1 USDC = 0.2 credits (soon 1 USDC = 5 gens)
    "ETH": 250,    # 1 ETH = 250 credits
}


def _load() -> dict:
    if CREDITS_FILE.exists():
        try:
            return json.loads(CREDITS_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save(data: dict):
    CREDITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write
    tmp = CREDITS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    shutil.move(str(tmp), str(CREDITS_FILE))


def get_balance(wallet: str) -> int:
    """Get credit balance for a wallet address."""
    with _lock:
        data = _load()
        return data.get(wallet.lower(), {}).get("balance", 0)


def add_credits(wallet: str, amount: int, source: str = "manual"):
    """Add credits to a wallet. Source tracks where they came from."""
    with _lock:
        data = _load()
        key = wallet.lower()
        if key not in data:
            data[key] = {"balance": 0, "total_added": 0, "transactions": []}
        data[key]["balance"] += amount
        data[key]["total_added"] += amount
        data[key]["transactions"].append({
            "type": "credit",
            "amount": amount,
            "source": source,
            "balance_after": data[key]["balance"],
        })
        _save(data)
        return data[key]["balance"]


def deduct_credit(wallet: str) -> bool:
    """Deduct one credit for a generation. Returns False if insufficient."""
    with _lock:
        data = _load()
        key = wallet.lower()
        if key not in data or data[key]["balance"] < CREDITS_PER_GEN:
            return False
        data[key]["balance"] -= CREDITS_PER_GEN
        data[key]["transactions"].append({
            "type": "deduct",
            "amount": CREDITS_PER_GEN,
            "source": "generation",
            "balance_after": data[key]["balance"],
        })
        _save(data)
        return True


def get_history(wallet: str) -> list:
    """Get transaction history for a wallet."""
    with _lock:
        data = _load()
        key = wallet.lower()
        if key not in data:
            return []
        return data[key].get("transactions", [])[-20:]  # last 20


def tokens_to_credits(token: str, amount: float) -> int:
    """Convert token amount to credits using current rates."""
    rate = TOKEN_RATES.get(token.upper(), 0)
    return int(amount * rate)
