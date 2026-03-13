# nostrsocial

Social graph manager for OpenClaw AI agents. Part of the Humanjava ecosystem.

## Build & Test

```bash
pip install -e ".[dev]"
pytest -v
```

## Structure

- `src/nostrsocial/` — package source
  - `types.py` — Contact, Tier, ListType, IdentityState, BehaviorRules, CapacityError
  - `enclave.py` — SocialEnclave orchestrator (main entry point)
  - `contacts.py` — ContactList CRUD with slot enforcement
  - `behavior.py` — Tier → behavioral rules mapping
  - `proxy.py` — HMAC-based proxy npub derivation
  - `evaluate.py` — Conversation evaluation: sentiment + relationship context → adjusted behavior
  - `resonance.py` — Cross-channel recognition and identity linking (not surveillance)
  - `guardrails.py` — Content screening: banned words, topics, entities with operator overrides
  - `data/` — Bundled JSON filter lists (banned_words, banned_topics, banned_entities)
  - `verify.py` — Challenge-response verification (stub in 0.1.0)
  - `storage.py` — MemoryStorage + FileStorage backends
- `tests/` — pytest suite
- `clawhub/` — OpenClaw skill metadata

## Conventions

- Python 3.10+, hatchling build, ruff linter (100 char line length)
- Dependency: `bech32>=1.2.0` only (nostrkey removed — proxy.py implements bech32 encoding directly)
- Capacity limits are constants in `types.py` — do not bypass them
- Proxy npubs are deterministic (HMAC-SHA256) — same input always produces same output
- `verify_challenge()` raises NotImplementedError in 0.1.0 — this is intentional
- Resonance is recognition, not surveillance — only checks existing contacts, never mines external data
- Linking is always explicit — matching npubs don't auto-merge
- Guardrails: bundled defaults in `data/*.json`, operators can override via `extra_words`/`extra_topics`/`extra_entities`
- ScreenResult.matched never exposes raw input — uses category tags like `[slurs]` for PII safety
- ⚠️ Device secret is the root of all proxy npub derivation — call `export_secret()` after `create()` and store securely
- `restore(secret_b64)` rebuilds an enclave from a backed-up secret
- `displace(tier)` handles full-tier scenarios by demoting the weakest contact
- `maintain(dry_run=True)` previews maintenance without making changes
- `signal_history` on Contact tracks the last 10 interaction snapshots for temporal pattern detection
