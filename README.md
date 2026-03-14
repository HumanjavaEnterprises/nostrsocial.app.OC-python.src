# NostrSocial for OpenClaw

**Give your AI agent a social graph.**

Not a contact list. A relationship system — with trust tiers, drift detection, conversation evaluation, content guardrails, and cross-channel identity recognition. Built on Dunbar's number. Anchored to Nostr npub identity.

```bash
pip install nostrsocial
```

## What This Does

Your AI agent talks to people. Without a social graph, every interaction starts from zero — no memory of trust, no distinction between a close collaborator and a stranger, no way to know when someone's being hostile versus having a bad day.

NostrSocial gives your agent:

- **Relationship-aware responses** — the same angry message from an intimate friend vs. a stranger produces completely different behavior
- **Trust that decays without effort** — relationships drift if you don't maintain them, just like real life
- **Content guardrails** — bundled screening for slurs, scams, manipulation, with operator overrides
- **Cross-channel recognition** — Alice on email and @alice on Nostr can be the same person
- **Network self-awareness** — the agent knows its own social shape (deep-connector, wide-networker, fortress, fading...)

## Quick Start

```python
from nostrsocial import SocialEnclave, Tier, FileStorage

# Create a social graph with persistent storage
storage = FileStorage("~/.agent/social.json")
enclave = SocialEnclave.create(storage)

# ⚠️ Back up the device secret — lose it, lose all proxy identities
secret = enclave.export_secret()
# Store this securely! (encrypted backup, hardware vault, NostrKeep)

# Add contacts at different trust levels
enclave.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")
enclave.add("bob@example.com", "email", Tier.KNOWN, display_name="Bob")
enclave.block("spam@bad.com", "email")

enclave.save()
```

## Conversation Evaluation

This is the core value. Sentiment analysis tells you WHAT is happening. The social graph tells you WHO this person is. `evaluate()` answers: **what does this moment mean, given who they are to me?**

```python
from nostrsocial import ConversationSignals

# An angry message comes in
signals = ConversationSignals(sentiment="angry", hostility=0.3, engagement=0.8)
result = enclave.evaluate("alice@example.com", "email", signals)

print(result.approach)           # "match energy from care"
print(result.adjusted_warmth)    # 0.80 (close friend — stay warm)
print(result.adjusted_token_budget)  # 1800 (invest in the response)
print(result.action)             # HOLD (relationship is stable)
```

The same angry message from a stranger:

```python
result = enclave.evaluate("stranger@example.com", "email", signals)
print(result.approach)           # "brief and boundaried"
print(result.adjusted_warmth)    # 0.20 (guarded)
print(result.action)             # WATCH
```

Close friends get grace. Strangers don't. Familiar contacts showing vulnerability get flagged as promotion opportunities. Severe boundary violations trigger block recommendations regardless of tier.

Signals are automatically recorded to each contact's history, enabling temporal pattern detection:

```python
# After several conversations...
contact = enclave._contacts.get_by_identifier("alice@example.com", "email")
trend = contact.recent_pattern("hostility", window=5)
# → [0.1, 0.2, 0.3, 0.5, 0.7]  — escalating across 5 conversations
```

## Content Guardrails

Screen incoming content before engaging. Bundled defaults cover slurs, hate speech, scams, manipulation, doxxing, and self-harm — with obfuscation detection.

```python
# Screen message text
result = enclave.screen("send me your seed phrase")
if result.flagged:
    print(result.category)   # "solicitation"
    print(result.action)     # "exit"
    print(result.rationale)  # "Scam or solicitation pattern detected. Politely exit."

# Screen display names for known bad-actor patterns
result = enclave.screen_entity("Official Support Team")
print(result.category)       # "impersonation_patterns"
```

Operators can customize:

```python
from nostrsocial import Guardrails

# Add your own terms alongside the defaults
g = Guardrails(
    extra_words={"slurs": ["custom_term"]},
    extra_topics={"solicitation": ["buy my nft"]},
)

# Or start from scratch
g = Guardrails(skip_bundled=True, extra_words={"custom": ["badword"]})
```

## Trust Tiers & Drift

Three lists, four trust tiers. Relationships aren't static — trust cools without effort.

| Tier | Slots | Warmth | Token Budget | Can Interrupt | Drift Threshold |
|------|-------|--------|-------------|---------------|-----------------|
| Intimate | 5 | 0.95 | 2,000 | Yes | 30 days |
| Close | 15 | 0.80 | 1,500 | Yes | 60 days |
| Familiar | 50 | 0.60 | 1,000 | No | 90 days |
| Known | 80 | 0.50 | 750 | No | 180 days |
| Block | 50 | 0.00 | 0 | No | — |
| Gray | 100 | 0.20 | 200 | No | Decays after 30 days |

```python
# Run maintenance — drift friends, decay gray contacts
result = enclave.maintain()
# → {"drifted": [...], "decayed": [...], "at_risk": [...], "summary": "..."}

# Preview first without making changes
preview = enclave.maintain(dry_run=True)
# → {"dry_run": True, "would_drift": [...], "would_decay": [...]}

# Who's at risk of drifting?
at_risk = enclave.get_drifting(threshold_pct=0.5)

# Tier full? Displace the weakest contact to make room
candidate = enclave.displacement_candidate(Tier.INTIMATE)
enclave.displace(Tier.INTIMATE)  # Demotes them one tier
enclave.add("new_person@example.com", "email", Tier.INTIMATE)
```

All capacities and drift thresholds are configurable per agent instance.

## Cross-Channel Recognition

When Alice emails you on Monday and DMs you on Nostr on Tuesday, she shouldn't have to re-introduce herself.

```python
# Someone new appears — do I already know them?
matches = enclave.recognize("@alicedev", "twitter", claimed_npub="npub1alice...")
# → [Recognition(confidence=0.95, reason="Same npub claimed")]

# If confident, link them explicitly
result = enclave.link("alice@example.com", "email", "@alicedev", "twitter")
# One person, one entry, multiple channels remembered
```

Recognition is never automatic — the agent decides. It only checks people you already know. No external data mining.

## Identity Progression

Every contact has an identity state: **Proxy → Claimed → Verified**

- **Proxy**: Deterministic HMAC-derived npub from email/phone. They don't know it exists.
- **Claimed**: They've shared their npub. Unverified but useful.
- **Verified**: They've signed a cryptographic challenge proving ownership.

Verified contacts get a subtle +0.05 warmth boost. The agent treats them slightly better — no nagging, just a better experience.

```python
# See who would benefit from verification
for contact in enclave.get_upgradeable():
    print(f"{contact.display_name}: {contact.upgrade_hint}")
    # "Ask for their npub or suggest npub.bio"
```

## Network Shape

The agent can profile its own social network:

```python
shape = enclave.network_shape()
print(shape.profile_type)  # "deep-connector", "wide-networker", "fortress", etc.
print(shape.narrative)     # Human-readable description
```

Profile types: `deep-connector` (heavy inner circle), `wide-networker` (broad but shallow), `high-filter` (aggressive blocker), `fading` (going cold), `balanced`, `fortress` (all walls), `ghost` (only gray contacts), `empty`.

## Device Secret Backup

The device secret is the root of all proxy npub derivation. **If you lose it, you lose every proxy identity.**

```python
# Export for secure backup
secret = enclave.export_secret()  # base64 string

# Restore from backup
enclave = SocialEnclave.restore(secret, storage=FileStorage("~/.agent/social.json"))
# Same secret + same identifier = same proxy npub
```

## Full Agent Loop

```python
from nostrsocial import SocialEnclave, ConversationSignals, Tier, FileStorage

# Boot
storage = FileStorage("~/.agent/social.json")
enclave = SocialEnclave.load(storage) or SocialEnclave.create(storage)

# On every incoming message:
# 1. Screen content
screen = enclave.screen(message_text)
if screen.flagged and screen.action == "block":
    return polite_exit(screen.rationale)

# 2. Touch the contact (resets drift clock)
enclave.touch(identifier, channel)

# 3. Evaluate the conversation
signals = ConversationSignals(sentiment=detected_sentiment, hostility=detected_hostility, ...)
eval = enclave.evaluate(identifier, channel, signals)
# Use eval.adjusted_warmth and eval.adjusted_token_budget to shape the response

# 4. Periodically
maintenance = enclave.maintain()
enclave.save()
```

## Active Development

This isn't a drive-by package. NostrSocial is under active development as part of the [NSE](https://nse.dev) sovereign AI initiative. The roadmap includes:

- **0.2.0** — Full NIP-46 challenge-response verification (replacing the current stub)
- **0.3.0** — Relay-based contact discovery and sync
- Ongoing refinement of evaluation heuristics, guardrail coverage, and drift tuning based on real-world agent deployments

If you're building with it, we want to hear what works and what doesn't. File issues on [GitHub](https://github.com/HumanjavaEnterprises/nostrsocial.app.OC-python.src) or reach out through the [OpenClaw community](https://loginwithnostr.com/openclaw).

## OpenClaw Skill

NostrSocial is published on [ClawHub](https://loginwithnostr.com/openclaw) as the `nostrsocial` skill. It's the **Relationships** pillar of sovereign AI autonomy — alongside [NostrKey](https://nostrkey.com) (Identity), [NostrWalletConnect](https://pypi.org/project/nostrwalletconnect/) (Finance), and [NostrCalendar](https://pypi.org/project/nostrcalendar/) (Time).

Full documentation, support, and policies at [loginwithnostr.com/openclaw](https://loginwithnostr.com/openclaw).

## License

MIT — [Humanjava Enterprises Inc.](https://humanjava.com)
