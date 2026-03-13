"""Challenge-response identity verification (stub for 0.1.0)."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass


@dataclass
class Challenge:
    """A verification challenge for proving npub ownership."""

    nonce: str
    target_npub: str
    created_at: float
    expires_at: float


def create_challenge(claimed_npub: str, ttl_seconds: float = 300) -> Challenge:
    """Create a challenge for a claimed npub to prove ownership.

    The contact must sign this nonce with their nsec to complete verification.
    """
    nonce = os.urandom(32).hex()
    now = time.time()
    return Challenge(
        nonce=nonce,
        target_npub=claimed_npub,
        created_at=now,
        expires_at=now + ttl_seconds,
    )


def verify_challenge(challenge: Challenge, signature: str) -> bool:
    """Verify a signed challenge response.

    Not implemented in 0.1.0 — requires relay-based message exchange.
    Full verification will ship in 0.2.0 using NIP-46 bunker flow.

    Raises:
        NotImplementedError: Always, in 0.1.0.
    """
    raise NotImplementedError(
        "Challenge verification requires relay interaction. "
        "Shipping in 0.2.0 with NIP-46 bunker flow. "
        "Use create_challenge() to generate nonces now."
    )
