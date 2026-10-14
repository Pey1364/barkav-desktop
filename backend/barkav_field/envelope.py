"""FD-01: encrypted envelope for field entries (FIELD_ENVELOPE_V1).

A passphrase is stretched with scrypt into a 32-byte key. The payload is sealed with
AES-256-GCM. Each envelope has its own random salt and nonce. The passphrase is never
stored or logged by this module.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

ENVELOPE_VERSION = 1
AAD = b"barkav-field-envelope-v1"
SCRYPT_N = 32768
SCRYPT_R = 8
SCRYPT_P = 1


class EnvelopeError(ValueError):
    """The envelope is malformed, the passphrase is wrong, or the data was changed."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.b64decode(text.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise EnvelopeError("bad base64") from exc


def _derive_key(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    if not passphrase:
        raise EnvelopeError("passphrase is empty")
    kdf = Scrypt(salt=salt, length=32, n=n, r=r, p=p)
    return kdf.derive(passphrase.encode("utf-8"))


def seal(payload: dict[str, Any], passphrase: str) -> bytes:
    """Return the envelope bytes (UTF-8 JSON) for a JSON-serialisable payload."""
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(passphrase, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    plain = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ct = AESGCM(key).encrypt(nonce, plain, AAD)
    envelope = {
        "v": ENVELOPE_VERSION,
        "kdf": "scrypt",
        "n": SCRYPT_N,
        "r": SCRYPT_R,
        "p": SCRYPT_P,
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "ct": _b64(ct),
    }
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def open_(data: bytes, passphrase: str) -> dict[str, Any]:
    """Decrypt an envelope and return the payload. Raises EnvelopeError on any failure."""
    try:
        envelope = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnvelopeError("not a JSON envelope") from exc
    if not isinstance(envelope, dict) or envelope.get("v") != ENVELOPE_VERSION:
        raise EnvelopeError("unsupported envelope version")
    if envelope.get("kdf") != "scrypt":
        raise EnvelopeError("unsupported key derivation")
    try:
        n, r, p = int(envelope["n"]), int(envelope["r"]), int(envelope["p"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EnvelopeError("missing scrypt parameters") from exc
    if n < 2 or n & (n - 1) or n > 2**20 or r < 1 or r > 32 or p < 1 or p > 4:
        raise EnvelopeError("scrypt parameters out of range")
    salt = _unb64(str(envelope.get("salt", "")))
    nonce = _unb64(str(envelope.get("nonce", "")))
    ct = _unb64(str(envelope.get("ct", "")))
    if len(salt) != 16 or len(nonce) != 12 or len(ct) < 16:
        raise EnvelopeError("bad envelope fields")

    key = _derive_key(passphrase, salt, n, r, p)
    try:
        plain = AESGCM(key).decrypt(nonce, ct, AAD)
    except InvalidTag as exc:
        raise EnvelopeError("wrong passphrase or changed data") from exc
    try:
        payload = json.loads(plain.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnvelopeError("payload is not JSON") from exc
    if not isinstance(payload, dict):
        raise EnvelopeError("payload is not an object")
    return payload
