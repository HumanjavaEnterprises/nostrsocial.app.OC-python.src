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
  - `verify.py` — Challenge-response verification (stub in 0.1.0)
  - `storage.py` — MemoryStorage + FileStorage backends
- `tests/` — pytest suite
- `clawhub/` — OpenClaw skill metadata

## Conventions

- Python 3.10+, hatchling build, ruff linter (100 char line length)
- Dependency: `nostrkey>=0.1.1` only
- Capacity limits are constants in `types.py` — do not bypass them
- Proxy npubs are deterministic (HMAC-SHA256) — same input always produces same output
- `verify_challenge()` raises NotImplementedError in 0.1.0 — this is intentional
