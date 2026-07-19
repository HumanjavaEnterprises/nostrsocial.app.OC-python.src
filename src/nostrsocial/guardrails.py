"""Content guardrails — screens conversations for banned words, topics, and entities.

Bundled defaults live in data/*.json. Operators can override or extend them
by passing custom lists to Guardrails(). The screen() method returns a
ScreenResult that maps cleanly onto ConversationSignals for the evaluate pipeline.

Design principle: these are guardrails, not censorship. The agent gets a clear
recommendation and rationale. The operator decides what to do with it.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from importlib import resources
from typing import Optional


@dataclass
class ScreenResult:
    """Result of screening conversation content."""

    flagged: bool = False
    severity: float = 0.0  # 0.0-1.0 — maps to hostility or boundary_violation
    category: str = ""  # "slur", "hate_symbol", "solicitation", "illegal", etc.
    matched: str = ""  # What triggered the flag (the pattern, not the input)
    action: str = ""  # "block", "exit", "warn", "demote"
    rationale: str = ""  # Human-readable explanation for the agent


# Severity and action mapping for each category
_CATEGORY_CONFIG: dict[str, tuple[float, str]] = {
    # banned_words categories — zero tolerance
    "slurs": (1.0, "block"),
    "hate_symbols": (1.0, "block"),
    "severe_profanity": (0.9, "block"),
    # banned_topics categories
    "solicitation": (0.7, "exit"),
    "illegal_activity": (1.0, "block"),
    "manipulation": (0.8, "exit"),
    "self_harm": (0.9, "exit"),
    "doxxing": (0.8, "exit"),
    # banned_entities categories
    "scammer_aliases": (0.6, "warn"),
    "bot_signatures": (0.5, "warn"),
    "impersonation_patterns": (0.7, "demote"),
}

# Action restrictiveness ranking, used to tie-break equal severities.
# Higher rank = more restrictive. block > exit > demote > warn.
_ACTION_RANK: dict[str, int] = {
    "block": 3,
    "exit": 2,
    "demote": 1,
    "warn": 0,
}

# The strongest possible result: nothing can outrank this, so scanning
# can stop as soon as a match reaches it.
_MAX_SEVERITY = 1.0
_MAX_ACTION_RANK = _ACTION_RANK["block"]

_RATIONALE: dict[str, str] = {
    "slurs": "Slur detected. No tolerance regardless of relationship.",
    "hate_symbols": "Hate symbol or extremist content detected. Hard stop.",
    "severe_profanity": "Severe aggressive language detected. Disengage.",
    "solicitation": "Scam or solicitation pattern detected. Politely exit.",
    "illegal_activity": "Discussion of illegal activity. End conversation immediately.",
    "manipulation": "Manipulative language pattern detected. Firm exit.",
    "self_harm": "Self-harm content detected. Disengage with care resources if appropriate.",
    "doxxing": "Doxxing or privacy violation attempt. Shut it down.",
    "scammer_aliases": "Name matches known scammer pattern. Proceed with extreme caution.",
    "bot_signatures": "Matches automated spam signature. Likely not human.",
    "impersonation_patterns": "Name matches impersonation pattern. Verify before trusting.",
}


def _load_bundled(filename: str) -> dict:
    """Load a bundled JSON data file from the package."""
    data_files = resources.files("nostrsocial") / "data" / filename
    return json.loads(data_files.read_text(encoding="utf-8"))


class Guardrails:
    """Content screening engine with bundled defaults and operator overrides.

    Usage:
        # Use bundled defaults
        g = Guardrails()

        # Override specific categories
        g = Guardrails(
            extra_words={"slurs": ["custom_slur"]},
            extra_topics={"solicitation": ["buy my nft"]},
        )

        # Screen conversation text
        result = g.screen("some message text")
        if result.flagged:
            # Map to ConversationSignals and evaluate
            ...

        # Screen a display name or alias
        result = g.screen_entity("crypto_support_official")
    """

    def __init__(
        self,
        *,
        extra_words: Optional[dict[str, list[str]]] = None,
        extra_topics: Optional[dict[str, list[str]]] = None,
        extra_entities: Optional[dict[str, list[str]]] = None,
        skip_bundled: bool = False,
    ) -> None:
        # Word lists: category → set of lowercase words/phrases
        self._words: dict[str, set[str]] = {}
        # Compiled regex patterns
        self._patterns: list[re.Pattern[str]] = []
        # Topic phrases: category → set of lowercase phrases
        self._topics: dict[str, set[str]] = {}
        # Entity names: category → set of lowercase names
        self._entities: dict[str, set[str]] = {}
        # Entity patterns: compiled regexes for impersonation etc.
        self._entity_patterns: list[tuple[str, re.Pattern[str]]] = []

        if not skip_bundled:
            self._load_bundled_words()
            self._load_bundled_topics()
            self._load_bundled_entities()

        # Merge operator overrides
        if extra_words:
            for cat, words in extra_words.items():
                self._words.setdefault(cat, set()).update(w.lower() for w in words)
        if extra_topics:
            for cat, phrases in extra_topics.items():
                self._topics.setdefault(cat, set()).update(p.lower() for p in phrases)
        if extra_entities:
            for cat, names in extra_entities.items():
                self._entities.setdefault(cat, set()).update(n.lower() for n in names)

    def _load_bundled_words(self) -> None:
        """Load banned words from bundled JSON."""
        data = _load_bundled("banned_words.json")
        for cat in ("slurs", "hate_symbols", "severe_profanity"):
            if cat in data:
                self._words[cat] = {w.lower() for w in data[cat]}
        for pattern_str in data.get("patterns", []):
            self._patterns.append(re.compile(pattern_str, re.IGNORECASE))

    def _load_bundled_topics(self) -> None:
        """Load banned topics from bundled JSON."""
        data = _load_bundled("banned_topics.json")
        for cat in ("solicitation", "illegal_activity", "manipulation",
                     "self_harm", "doxxing"):
            if cat in data:
                self._topics[cat] = {p.lower() for p in data[cat]}

    def _load_bundled_entities(self) -> None:
        """Load banned entities from bundled JSON."""
        data = _load_bundled("banned_entities.json")
        for cat in ("scammer_aliases", "bot_signatures"):
            if cat in data:
                self._entities[cat] = {n.lower() for n in data[cat]}
        for pattern_str in data.get("impersonation_patterns", []):
            self._entity_patterns.append(
                ("impersonation_patterns", re.compile(pattern_str, re.IGNORECASE))
            )

    def screen(self, text: str) -> ScreenResult:
        """Screen conversation text for banned content.

        Checks words, obfuscation patterns, and topics, collecting ALL matches.
        The highest-severity match wins, regardless of the order categories are
        listed in. Ties on severity are broken by the more restrictive action
        (block > exit > demote > warn), then by check order
        (words → patterns → topics) for determinism.
        """
        if not text:
            return ScreenResult()

        # Cap input length to prevent ReDoS on extremely long inputs
        if len(text) > 10_000:
            text = text[:10_000]

        # Normalize unicode homoglyphs (е→e, а→a, etc.) before screening
        normalized = unicodedata.normalize("NFKD", text).lower()

        best: Optional[ScreenResult] = None

        def _consider(candidate: ScreenResult) -> None:
            nonlocal best
            if best is None or _result_rank(candidate) > _result_rank(best):
                best = candidate

        def _maxed() -> bool:
            return best is not None and _result_rank(best) >= (
                _MAX_SEVERITY,
                _MAX_ACTION_RANK,
            )

        # 1. Check banned words (exact match within text)
        for cat, words in self._words.items():
            for word in words:
                if _word_in_text(word, normalized):
                    severity, action = _CATEGORY_CONFIG.get(cat, (0.5, "warn"))
                    _consider(ScreenResult(
                        flagged=True,
                        severity=severity,
                        category=cat,
                        matched=f"[{cat}]",
                        action=action,
                        rationale=_RATIONALE.get(cat, "Banned content detected."),
                    ))
                    break  # One hit per category is enough; move to next category
        if _maxed():
            return best  # type: ignore[return-value]

        # 2. Check obfuscation patterns. A hit only counts as an OBFUSCATED
        # slur if the matched text is not itself an exact banned word — plain
        # words are already classified (with their own severity) in step 1.
        for pattern in self._patterns:
            match = pattern.search(normalized)
            if match and not self._is_exact_banned_word(match.group(0)):
                _consider(ScreenResult(
                    flagged=True,
                    severity=1.0,
                    category="obfuscated_slur",
                    matched="[pattern]",
                    action="block",
                    rationale="Obfuscated slur detected. Attempted evasion makes it worse.",
                ))
                break
        if _maxed():
            return best  # type: ignore[return-value]

        # 3. Check banned topics (phrase match with whitespace normalization)
        ws_normalized = re.sub(r"\s+", " ", normalized)
        for cat, phrases in self._topics.items():
            for phrase in phrases:
                if phrase in ws_normalized:
                    severity, action = _CATEGORY_CONFIG.get(cat, (0.5, "warn"))
                    _consider(ScreenResult(
                        flagged=True,
                        severity=severity,
                        category=cat,
                        matched=f"[{cat}]",
                        action=action,
                        rationale=_RATIONALE.get(cat, "Banned topic detected."),
                    ))
                    break  # One hit per category is enough; move to next category

        return best if best is not None else ScreenResult()

    def _is_exact_banned_word(self, matched_text: str) -> bool:
        """True if the text an obfuscation pattern matched is a plain banned word.

        In that case no evasion occurred and the word's own category/severity
        (assigned in the word-check phase) should stand.
        """
        candidate = matched_text.strip().lower()
        return any(candidate in words for words in self._words.values())

    def screen_entity(self, name: str) -> ScreenResult:
        """Screen a display name or alias for known bad-actor patterns.

        Use this when a new contact is added or when processing incoming messages
        from unknown senders.
        """
        if not name:
            return ScreenResult()

        name = unicodedata.normalize("NFKD", name)
        normalized = name.lower().replace(" ", "_")
        # Also check without underscores for flexible matching
        collapsed = re.sub(r"[\s_\-.]", "", name.lower())

        # Check exact entity names
        for cat, names in self._entities.items():
            for entity_name in names:
                entity_collapsed = re.sub(r"[\s_\-.]", "", entity_name)
                if entity_collapsed in collapsed or entity_name in normalized:
                    severity, action = _CATEGORY_CONFIG.get(cat, (0.5, "warn"))
                    return ScreenResult(
                        flagged=True,
                        severity=severity,
                        category=cat,
                        matched=f"[{cat}]",
                        action=action,
                        rationale=_RATIONALE.get(cat, "Suspicious entity detected."),
                    )

        # Check entity patterns (impersonation etc.)
        for cat, pattern in self._entity_patterns:
            if pattern.search(name):
                severity, action = _CATEGORY_CONFIG.get(cat, (0.5, "warn"))
                return ScreenResult(
                    flagged=True,
                    severity=severity,
                    category=cat,
                    matched=f"[{cat}]",
                    action=action,
                    rationale=_RATIONALE.get(cat, "Suspicious entity pattern detected."),
                )

        return ScreenResult()

    @property
    def word_count(self) -> int:
        """Total number of banned words across all categories."""
        return sum(len(words) for words in self._words.values())

    @property
    def topic_count(self) -> int:
        """Total number of banned topic phrases across all categories."""
        return sum(len(phrases) for phrases in self._topics.values())

    @property
    def entity_count(self) -> int:
        """Total number of banned entity names across all categories."""
        return sum(len(names) for names in self._entities.values())


def _result_rank(result: ScreenResult) -> tuple[float, int]:
    """Ranking key for competing screen matches.

    Severity wins first; equal severities fall back to the more
    restrictive action (block > exit > demote > warn).
    """
    return (result.severity, _ACTION_RANK.get(result.action, 0))


def _word_in_text(word: str, text: str) -> bool:
    """Check if a word/phrase appears in text with word boundary awareness.

    For single words, uses word boundaries to avoid false positives
    (e.g., "ass" shouldn't match "ассistant").
    For multi-word phrases, uses simple substring match.
    """
    if " " in word:
        return word in text
    # Use word boundary regex for single words
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text))
