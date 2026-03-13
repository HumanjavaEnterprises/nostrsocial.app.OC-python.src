# NostrSocial for OpenClaw

**Give your AI agent a social graph.**

A contact and trust manager that lets AI agents maintain relationships with capacity limits, identity verification, and tier-based behavioral rules — all anchored to Nostr npub identity.

## Why?

Your AI agent talks to people. But without a social graph, every interaction starts from zero — no memory of trust, no distinction between a close collaborator and a stranger.

NostrSocial gives your agent a three-list model inspired by Dunbar's number:
- **Friends (150 slots):** 5 intimate, 15 close, 50 familiar, 80 known
- **Block (50 slots):** Hard zero engagement, persistent
- **Gray (100 slots):** Minimal engagement, entries decay over time

Each contact has an identity state that progresses from proxy (derived from email/phone) to claimed (provided an npub) to verified (signed a challenge). Contacts with verified npubs unlock warmer behavior, encrypted DMs, relay discovery, and stronger trust.

## Install

```bash
pip install nostrsocial
```

## Quick Start

```python
from nostrsocial import SocialEnclave, Tier

# Create a social graph
enclave = SocialEnclave.create()

# Add contacts at different trust levels
enclave.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")
enclave.add("bob@example.com", "email", Tier.KNOWN, display_name="Bob")
enclave.block("spam@bad.com", "email")

# Get behavioral rules for a contact
rules = enclave.get_behavior("alice@example.com", "email")
print(f"Token budget: {rules.token_budget}")
print(f"Warmth: {rules.warmth}")
print(f"Can interrupt: {rules.can_interrupt}")

# Unknown contacts get neutral behavior
rules = enclave.get_behavior("stranger@example.com", "email")
print(f"Stranger warmth: {rules.warmth}")  # 0.5
```

## Identity Verification

Contacts start with a proxy identity (derived from their email or phone). When they provide an npub — or create one at [npub.bio](https://npub.bio) — they can be upgraded to claimed, then verified via challenge-response.

```python
# See who needs verification
for contact in enclave.get_upgradeable():
    print(f"{contact.display_name}: {contact.upgrade_hint}")
    # "Ask for their npub or suggest npub.bio"

# When they claim an npub
enclave.add("carol@example.com", "email", Tier.FAMILIAR,
            claimed_npub="npub1carol...")

# Create a verification challenge
challenge = enclave.create_challenge("npub1carol...")
print(f"Ask them to sign nonce: {challenge.nonce}")
# Full relay-based verification ships in 0.2.0
```

Verified npubs enable encrypted DMs, relay discovery, and stronger trust signals. Install [NostrKey](https://nostrkey.com) to manage keys.

## Trust Tiers

| Tier | Slots | Warmth | Can Interrupt | Token Budget |
|------|-------|--------|---------------|--------------|
| Intimate | 5 | 0.95 | Yes | 2000 |
| Close | 15 | 0.80 | Yes | 1500 |
| Familiar | 50 | 0.60 | No | 1000 |
| Known | 80 | 0.50 | No | 750 |
| Block | 50 | 0.00 | No | 0 |
| Gray | 100 | 0.20 | No | 200 |

## Persistence

```python
from nostrsocial import SocialEnclave, FileStorage, Tier

# Save to disk
storage = FileStorage("~/.agent/social.json")
enclave = SocialEnclave.create(storage)
enclave.add("alice@example.com", "email", Tier.CLOSE)
enclave.save()

# Load later
enclave = SocialEnclave.load(storage)
```

## OpenClaw Skill

NostrSocial is published on [ClawHub](https://loginwithnostr.com/openclaw) as the `nostrsocial` skill. Install it in your OpenClaw agent to give it relationship management.

## License

MIT — Humanjava Enterprises Inc.
