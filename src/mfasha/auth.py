"""Officer sign-in with a phone number and a PIN.

PINs are never stored: only a salted PBKDF2 hash is. A successful login returns a signed token
(HMAC-SHA256, expires after a few hours) that the officer page sends on every request."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from typing import Optional

PIN_PATTERN = r"^\d{4,6}$"
_PIN_RE = re.compile(PIN_PATTERN)
_ITERATIONS = 200_000
TOKEN_HOURS = 12
MAX_FAILURES = 5          # wrong PINs allowed for one phone number ...
LOCK_SECONDS = 5 * 60     # ... before it is locked for this long


def normalize_phone(raw: str) -> Optional[str]:
    """'+250 788 123 456', '250788123456' and '0788 123 456' all become '0788123456'.
    Returns None when the number cannot be a phone number."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("250") and len(digits) == 12:
        digits = "0" + digits[3:]
    if 9 <= len(digits) <= 15:
        return digits
    return None


def valid_pin(pin: str) -> bool:
    return bool(_PIN_RE.match(pin or ""))


def hash_pin(pin: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, _ITERATIONS)
    return salt.hex(), digest.hex()


def check_pin(pin: str, salt_hex: str, hash_hex: str) -> bool:
    return hmac.compare_digest(hash_pin(pin, salt_hex)[1], hash_hex)


# a fixed fake record, so a wrong phone number takes as long to reject as a wrong PIN
_DUMMY_SALT, _DUMMY_HASH = hash_pin("000000")


def burn_time() -> None:
    check_pin("000000", _DUMMY_SALT, _DUMMY_HASH)


# ---------------------------------------------------------------- tokens
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_token(secret: str, phone: str, name: str, hours: int = TOKEN_HOURS) -> str:
    body = _b64(json.dumps({"p": phone, "n": name, "exp": int(time.time()) + hours * 3600}).encode())
    sig = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(secret: str, token: str) -> Optional[dict]:
    """Returns {'phone', 'name'} for a valid, unexpired token, otherwise None."""
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(_unb64(body))
        if data["exp"] < time.time():
            return None
        return {"phone": data["p"], "name": data["n"]}
    except Exception:
        return None


# ---------------------------------------------------------------- brute-force guard
class LoginThrottle:
    """A PIN has only 10 000 to 1 000 000 possible values, so guessing must be slowed down."""

    def __init__(self, max_failures: int = MAX_FAILURES, lock_seconds: int = LOCK_SECONDS):
        self._max, self._lock = max_failures, lock_seconds
        self._failures: dict[str, list[float]] = {}
        self._mutex = threading.Lock()

    def seconds_locked(self, phone: str) -> int:
        with self._mutex:
            recent = [t for t in self._failures.get(phone, []) if time.time() - t < self._lock]
            self._failures[phone] = recent
            if len(recent) >= self._max:
                return int(self._lock - (time.time() - recent[0])) + 1
            return 0

    def record_failure(self, phone: str) -> None:
        with self._mutex:
            self._failures.setdefault(phone, []).append(time.time())

    def reset(self, phone: str) -> None:
        with self._mutex:
            self._failures.pop(phone, None)