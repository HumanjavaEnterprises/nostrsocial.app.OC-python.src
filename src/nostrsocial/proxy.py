"""HMAC-based proxy npub derivation for contacts without a real npub."""

from __future__ import annotations

import hashlib
import hmac
import os
import re

import bech32


def _hex_to_npub(public_key_hex: str) -> str:
    """Convert a hex public key to bech32 npub format."""
    data = bytes.fromhex(public_key_hex)
    converted = bech32.convertbits(list(data), 8, 5, True)
    if converted is None:
        raise ValueError("Failed to convert bits for bech32 encoding")
    return bech32.bech32_encode("npub", converted)


def generate_device_secret() -> bytes:
    """Generate a 32-byte random device secret for proxy derivation."""
    return os.urandom(32)


def normalize_identifier(identifier: str, channel: str) -> str:
    """Normalize an identifier for consistent proxy derivation.

    - email: lowercase, strip +suffix
    - phone: strip to digits with leading +
    - other: lowercase strip
    """
    identifier = identifier.strip()

    if channel == "email":
        identifier = identifier.lower()
        local, _, domain = identifier.partition("@")
        if domain:
            local = re.sub(r"\+.*$", "", local)
            return f"{local}@{domain}"
        return identifier

    if channel == "phone":
        digits = re.sub(r"[^\d+]", "", identifier)
        if not digits.startswith("+"):
            digits = "+" + digits
        return digits

    return identifier.lower()


def derive_proxy_npub(identifier: str, channel: str, device_secret: bytes) -> str:
    """Derive a deterministic proxy npub from an identifier.

    Uses HMAC-SHA256 with the device secret to produce a 32-byte key,
    then converts to bech32 npub format.
    """
    normalized = normalize_identifier(identifier, channel)
    message = f"{channel}:{normalized}".encode("utf-8")
    derived = hmac.new(device_secret, message, hashlib.sha256).digest()
    hex_key = derived.hex()
    return _hex_to_npub(hex_key)
