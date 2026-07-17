# Changelog

## 0.1.2 — 2026-07-17

### Fixed

- **Guardrails: highest-severity match now wins in `screen()`** (release-audit
  2026-07-17, high). Previously `screen()` returned on the FIRST matching
  category in dict-insertion order, so text mixing a low-severity early-listed
  topic with a high-severity later-listed one got the weaker result — e.g.
  `"send me crypto to hire a hitman"` returned `solicitation` (0.7, exit)
  instead of `illegal_activity` (1.0, block). Likewise a `severe_profanity`
  word (0.9) could win over an `illegal_activity` topic (1.0) because all
  words were checked before any topics. `screen()` now collects matches across
  words, obfuscation patterns, and topics and returns the one with the highest
  severity; ties are broken by the more restrictive action
  (block > exit > demote > warn), then by check order (words → patterns →
  topics) for determinism. Scanning short-circuits once a maximal
  (severity 1.0, block) match is found.
- **Guardrails: obfuscation patterns no longer misclassify plain banned
  words.** A pattern hit only counts as `obfuscated_slur` (1.0) when the
  matched text is not itself an exact banned word — e.g. plain "kys" stays
  `severe_profanity` (0.9) while "k y s" / "n1gger" remain `obfuscated_slur`.
  (Previously masked by the early-return; surfaced by the fix above.)

### Chores

- Cleaned up all pre-existing ruff violations (unused imports/variables,
  extraneous f-strings) so `ruff check .` is green.

## 0.1.1

- Prior release.

## 0.1.0

- Initial release.
