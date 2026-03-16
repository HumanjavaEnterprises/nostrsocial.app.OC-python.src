---
name: nostrsocial
description: Social graph manager — contacts, trust tiers, and identity verification over Nostr
version: 0.1.1
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

# NostrSocial -- Social Graph for AI Agents

Give your AI agent the ability to manage contacts, enforce trust tiers, evaluate conversations in relationship context, screen content through guardrails, and track identity verification -- all anchored to Nostr npub identity. Trust is modeled as capacity-limited tiers inspired by Dunbar's number (150 friends total), with drift detection, cross-channel recognition, and behavioral rules that adapt in real time to conversation signals.

## Install

```bash
pip install nostrsocial
```

Minimal dependencies: `bech32` only. No heavyweight crypto libraries required.

## Quickstart

```python
from nostrsocial import SocialEnclave, Tier

# Create an enclave and back up the device secret immediately
enclave = SocialEnclave.create()
secret = enclave.export_secret()  # Store this securely

# Add a contact and get tier-based behavior
enclave.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")
rules = enclave.get_behavior("alice@example.com", "email")
# rules.warmth=0.8, rules.token_budget=1500, rules.can_interrupt=True
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

### 3. Evaluate Conversations

Combine WHO someone is with WHAT is happening to determine HOW to respond. Pass `ConversationSignals` captured from sentiment analysis and get back an `Evaluation` with adjusted warmth, token budget, approach guidance, and a recommended action.

```python
from nostrsocial import ConversationSignals

signals = ConversationSignals(
    sentiment="vulnerable",
    vulnerability=0.7,
    reciprocity=0.8,
    engagement=0.9,
    topic_depth=0.6,
)
result = enclave.evaluate("alice@example.com", "email", signals)
# result.action = Action.HOLD
# result.approach = "full presence"
# result.adjusted_warmth = 0.96
# result.adjusted_token_budget = 1950
# result.rationale = "A close friend is being vulnerable..."
```

### 4. Screen Content (Guardrails)

Screen conversation text for banned words, topics, and patterns before or alongside `evaluate()`. Returns a `ScreenResult` with severity, category, and recommended action.

```python
result = enclave.screen("some incoming message text")
if result.flagged:
    print(result.action)     # "block", "exit", "warn", or "demote"
    print(result.severity)   # 0.0-1.0
    print(result.category)   # "slurs", "manipulation", etc.
    print(result.matched)    # "[slurs]" (never raw input)

# Screen display names for known bad-actor patterns
result = enclave.screen_entity("crypto_support_official")
```

### 5. Network Shape

Analyze the social graph and get a human-readable profile.

```python
shape = enclave.network_shape()
# shape.profile_type = "balanced", "fortress", "deep-connector", etc.
# shape.narrative = "12 friends (2 intimate, 4 close, ...)
# shape.tier_counts, shape.verified_count, shape.avg_interaction_days
```

### 6. Auto-Maintenance

Run drift detection, gray decay, and at-risk reporting in a single call. Use `dry_run=True` to preview changes without committing them.

```python
# Preview what would happen
preview = enclave.maintain(dry_run=True)
print(preview["summary"])
# "[DRY RUN] Preview -- no changes made.
#  2 contact(s) WOULD drift: Alice, Bob
#  1 gray contact(s) WOULD expire: Meh"

# Execute maintenance for real
result = enclave.maintain()
# result["drifted"], result["decayed"], result["at_risk"], result["summary"]
```

### 7. Cross-Channel Recognition and Linking

Recognize the same person across different channels. This is resonance, not surveillance -- it only checks contacts you already have a relationship with.

```python
# Check if a new contact might be someone you already know
matches = enclave.recognize(
    "alicedev", "twitter",
    display_name="Alice",
)
for match in matches:
    print(f"{match.confidence}: {match.reason}")
    # 0.3: "Same display name on different channels"

# Explicitly link two identities (never auto-linked)
result = enclave.link(
    "alice@example.com", "email",
    "alicedev", "twitter",
)
# result.primary = the surviving contact (stronger relationship wins)
# result.absorbed_identifier = "alicedev"
# result.interaction_count_gained = 5

# See all channels for a contact
channels = enclave.get_linked_channels("alice@example.com", "email")
# {"email": "alice@example.com", "twitter": "alicedev"}
```

### 8. Identity Verification

Track identity state from proxy to claimed to verified.

```python
# See who needs verification
for contact in enclave.get_upgradeable():
    print(f"{contact.display_name}: {contact.upgrade_hint}")

# Create a challenge for a claimed npub
challenge = enclave.create_challenge("npub1alice...")
```

### 9. Persistence

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

## Trust Tiers

| Tier | Slots | Warmth | Token Budget | Can Interrupt | Share Context | Proactive |
|------|-------|--------|--------------|---------------|---------------|-----------|
| INTIMATE | 5 | 0.95 | 2000 | Yes | Yes | Yes |
| CLOSE | 15 | 0.8 | 1500 | Yes | Yes | No |
| FAMILIAR | 50 | 0.6 | 1000 | No | No | No |
| KNOWN | 80 | 0.5 | 750 | No | No | No |
| BLOCK | 50 | 0.0 | 0 | No | No | No |
| GRAY | 100 | 0.2 | 200 | No | No | No |

Friends list total: 150 (Dunbar's number). Unknown contacts get neutral behavior (warmth 0.5, budget 500).

## When to Use Each Module

| Task | Module | Function |
|------|--------|----------|
| Add/remove contacts | `enclave` | `SocialEnclave.add`, `block`, `gray`, `remove` |
| Change trust tier | `enclave` | `promote`, `demote` |
| Get behavioral rules | `enclave` / `behavior` | `get_behavior` |
| Evaluate a conversation moment | `enclave` / `evaluate` | `evaluate` with `ConversationSignals` |
| Screen content for guardrails | `enclave` / `guardrails` | `screen`, `screen_entity` |
| Check remaining slots | `enclave` | `slots_remaining` |
| Find unverified contacts | `enclave` | `get_unverified_contacts`, `get_upgradeable` |
| Create verification challenge | `enclave` / `verify` | `create_challenge` |
| Derive proxy npub | `proxy` | `derive_proxy_npub` |
| Run maintenance (drift + decay) | `enclave` | `maintain`, `maintain(dry_run=True)` |
| Recognize cross-channel identity | `enclave` / `resonance` | `recognize` |
| Link two identities | `enclave` / `resonance` | `link` |
| Analyze network profile | `enclave` | `network_shape` |
| Displace weakest in tier | `enclave` | `displace` |
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
| `warmth` | `float` | 0.0--1.0 (intimate=0.95, known=0.5, block=0.0) |
| `response_priority` | `int` | 1=highest (intimate), 10=block |
| `share_context` | `bool` | Share agent context with this contact |
| `proactive_contact` | `bool` | Agent initiates contact |

### Evaluation (returned by `evaluate()`)

| Field | Type | Description |
|-------|------|-------------|
| `action` | `Action` | HOLD, PROMOTE, DEMOTE, WATCH, BLOCK, or REACH_OUT |
| `confidence` | `float` | 0.0--1.0 |
| `adjusted_warmth` | `float` | Warmth for this specific moment |
| `adjusted_token_budget` | `int` | Token budget for this response |
| `approach` | `str` | "lean in", "de-escalate", "match energy", etc. |
| `rationale` | `str` | Why this recommendation |
| `tier_suggestion` | `Tier \| None` | Suggested tier if promote/demote |

### ScreenResult (returned by `screen()`)

| Field | Type | Description |
|-------|------|-------------|
| `flagged` | `bool` | Whether content was flagged |
| `severity` | `float` | 0.0--1.0 |
| `category` | `str` | "slurs", "hate_symbols", "manipulation", etc. |
| `matched` | `str` | Category tag like `[slurs]` (never raw input -- PII safe) |
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

## Common Patterns

### Device Secret Backup

```python
enclave = SocialEnclave.create()
secret = enclave.export_secret()
# Store secret in encrypted backup, hardware vault, or NostrKeep

# Later: rebuild from backed-up secret
enclave = SocialEnclave.restore(secret)
```

### Displacement When a Tier Is Full

```python
# Check who would be displaced before adding
candidate = enclave.displacement_candidate(Tier.CLOSE)
if candidate:
    print(f"Would displace: {candidate.display_name}")

# Force a slot open by demoting the weakest contact
displaced = enclave.displace(Tier.CLOSE)
# displaced is now in FAMILIAR tier
enclave.add("newperson@example.com", "email", Tier.CLOSE)
```

### Dry-Run Maintenance

```python
preview = enclave.maintain(dry_run=True)
for contact in preview["would_drift"]:
    print(f"  {contact.display_name} would drift")
for contact in preview["would_decay"]:
    print(f"  {contact.display_name} would expire from gray")

# Only commit if the preview looks right
if input("Proceed? ") == "y":
    enclave.maintain()
```

## Security

- **The device secret is the root of all proxy npub derivation.** Call `export_secret()` after `create()` and store it securely. If you lose it, all proxy npubs become unrecoverable.
- **Never hardcode an nsec in your code.** If your agent has a Nostr identity, load it from an environment variable or encrypted file. The `nostrkey` package provides `Identity.load()` for this.
- **ScreenResult.matched never exposes raw input.** It returns category tags like `[slurs]` to prevent PII leakage in logs or downstream systems.
- **Guardrails use bundled defaults** from `data/*.json` (banned words, topics, entities). Operators can override or extend via `extra_words`, `extra_topics`, and `extra_entities` parameters on `Guardrails()`.
- Proxy npubs are deterministic (HMAC-SHA256) -- same identifier always maps to same npub.
- Challenge verification requires relay interaction -- stub only in 0.1.0.

## Configuration

### Capacity Constants

| List | Capacity |
|------|----------|
| INTIMATE | 5 |
| CLOSE | 15 |
| FAMILIAR | 50 |
| KNOWN | 80 |
| BLOCK | 50 |
| GRAY | 100 (auto-decay after 30 days) |
| Friends total | 150 (Dunbar's number) |

All capacity constants are defined in `types.py` and can be overridden via `SocialEnclave.create(tier_capacity=..., list_capacity=...)`.

### Identity States

| State | Meaning |
|-------|---------|
| `PROXY` | HMAC-derived from email/phone/handle. Default for new contacts. |
| `CLAIMED` | User provided an npub but it has not been verified. |
| `VERIFIED` | Signed challenge confirms npub ownership. Verified contacts get warmer behavior. |

### Drift Thresholds (defaults)

| Tier | Silent days before demotion |
|------|----------------------------|
| INTIMATE | 30 days |
| CLOSE | 60 days |
| FAMILIAR | 90 days |
| KNOWN | 180 days (then moves to gray) |

## Links

- **PyPI:** [nostrsocial](https://pypi.org/project/nostrsocial/)
- **GitHub:** [HumanjavaEnterprises/nostrsocial.app.OC-python.src](https://github.com/HumanjavaEnterprises/nostrsocial.app.OC-python.src)
- **ClawHub:** Part of the [OpenClaw](https://loginwithnostr.com/openclaw) skill ecosystem
- **License:** MIT
