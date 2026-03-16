---
name: nostrsocial
description: Social graph manager — contacts, trust tiers, and identity verification over Nostr
version: 0.1.0
metadata:
  openclaw:
    requires:
      bins:
        - pip
    install:
      - kind: uv
        package: nostrsocial
        bins: []
    homepage: https://github.com/HumanjavaEnterprises/nostrsocial.app.OC-python.src
---

# NostrSocial — Social Graph for AI Agents

Give your AI agent the ability to manage contacts, enforce trust tiers, and track identity verification — all anchored to Nostr npub identity.

## Install

```bash
pip install nostrsocial
```

## Core Capabilities

### 1. Manage Contacts

Add contacts to friends, block, or gray lists with capacity enforcement.

```python
from nostrsocial import SocialEnclave, Tier

enclave = SocialEnclave.create()
enclave.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")
enclave.block("spam@bad.com", "email")
enclave.gray("meh@example.com", "email")
```

### 2. Query Behavioral Rules

Get tier-based behavioral parameters for any contact.

```python
rules = enclave.get_behavior("alice@example.com", "email")
# rules.token_budget, rules.warmth, rules.can_interrupt, etc.

# Unknown contacts get neutral behavior
rules = enclave.get_behavior("stranger@example.com", "email")
# warmth=0.5, token_budget=500
```

### 3. Identity Verification

Track identity state from proxy to claimed to verified.

```python
# See who needs verification
for contact in enclave.get_upgradeable():
    print(f"{contact.display_name}: {contact.upgrade_hint}")

# Create a challenge for a claimed npub
challenge = enclave.create_challenge("npub1alice...")
```

### 4. Persistence

Save and load the social graph.

```python
from nostrsocial import FileStorage

storage = FileStorage("~/.agent/social.json")
enclave = SocialEnclave.create(storage)
enclave.add("alice@example.com", "email", Tier.CLOSE)
enclave.save()

# Later
enclave = SocialEnclave.load(storage)
```

## When to Use Each Module

| Task | Module | Function |
|------|--------|----------|
| Add/remove contacts | `enclave` | `SocialEnclave.add`, `block`, `gray`, `remove` |
| Change trust tier | `enclave` | `promote`, `demote` |
| Get behavioral rules | `enclave` / `behavior` | `get_behavior` |
| Check remaining slots | `enclave` | `slots_remaining` |
| Find unverified contacts | `enclave` | `get_unverified_contacts`, `get_upgradeable` |
| Create verification challenge | `enclave` / `verify` | `create_challenge` |
| Derive proxy npub | `proxy` | `derive_proxy_npub` |
| Decay stale contacts | `enclave` | `decay` |
| Persist social graph | `enclave` | `save` / `load` |

## Response Format

### Contact (returned by `add()`, `promote()`, `demote()`)

| Field | Type | Description |
|-------|------|-------------|
| `identifier` | `str` | Email, phone, npub, etc. |
| `channel` | `str` | "email", "phone", "npub", "twitter" |
| `list_type` | `ListType` | FRIENDS, BLOCK, or GRAY |
| `tier` | `Tier \| None` | INTIMATE, CLOSE, FAMILIAR, or KNOWN (friends only) |
| `identity_state` | `IdentityState` | PROXY, CLAIMED, or VERIFIED |
| `proxy_npub` | `str` | HMAC-derived npub for non-npub contacts |
| `display_name` | `str \| None` | Human-readable name |
| `interaction_count` | `int` | Total interactions recorded |
| `upgrade_hint` | `str` | Hint for identity verification |

### BehaviorRules (returned by `get_behavior()`)

| Field | Type | Description |
|-------|------|-------------|
| `token_budget` | `int` | Token allowance (intimate=2000, known=750, block=0) |
| `memory_depth` | `int` | Past interactions to consider |
| `can_interrupt` | `bool` | Can interrupt ongoing tasks |
| `warmth` | `float` | 0.0–1.0 (intimate=0.95, known=0.5, block=0.0) |
| `response_priority` | `int` | 1=highest (intimate), 10=block |
| `share_context` | `bool` | Share agent context with this contact |
| `proactive_contact` | `bool` | Agent initiates contact |

### Evaluation (returned by `evaluate()`)

| Field | Type | Description |
|-------|------|-------------|
| `action` | `Action` | HOLD, PROMOTE, DEMOTE, WATCH, BLOCK, or REACH_OUT |
| `confidence` | `float` | 0.0–1.0 |
| `adjusted_warmth` | `float` | Warmth for this specific moment |
| `adjusted_token_budget` | `int` | Token budget for this response |
| `approach` | `str` | "lean in", "de-escalate", "match energy", etc. |
| `rationale` | `str` | Why this recommendation |
| `tier_suggestion` | `Tier \| None` | Suggested tier if promote/demote |

### ScreenResult (returned by `screen()`)

| Field | Type | Description |
|-------|------|-------------|
| `flagged` | `bool` | Whether content was flagged |
| `severity` | `float` | 0.0–1.0 |
| `category` | `str` | "slurs", "hate_symbols", "manipulation", etc. |
| `matched` | `str` | Category tag like `[slurs]` (never raw input — PII safe) |
| `action` | `str` | "block", "exit", "warn", or "demote" |
| `rationale` | `str` | Human-readable explanation |

### NetworkShape (returned by `network_shape()`)

| Field | Type | Description |
|-------|------|-------------|
| `total_contacts` | `int` | Total across all lists |
| `tier_counts` | `dict[str, int]` | Per-tier counts |
| `verified_count` | `int` | Verified identities |
| `profile_type` | `str` | "balanced", "fortress", "deep-connector", etc. |
| `narrative` | `str` | Human-readable network description |

## Important Notes

- **The device secret is the root of all proxy npub derivation.** Call `export_secret()` after `create()` and store it securely. If you lose it, all proxy npubs become unrecoverable.
- **Never hardcode an nsec in your code.** If your agent has a Nostr identity, load it from an environment variable or encrypted file. The `nostrkey` package provides `Identity.load()` for this.
- Friends list is capped at 150 (Dunbar's number): 5 intimate + 15 close + 50 familiar + 80 known
- Block list holds 50. Gray list holds 100 with auto-decay.
- Proxy npubs are deterministic — same identifier always maps to same npub
- Identity state: proxy → claimed → verified. Verified contacts get warmer behavior.
- Challenge verification requires relay interaction — stub only in 0.1.0
- Depends on `nostrkey` for npub derivation
