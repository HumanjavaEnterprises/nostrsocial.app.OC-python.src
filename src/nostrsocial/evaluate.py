"""Conversation evaluation — bridges sentiment analysis with relationship context.

The social graph tells you WHO someone is. Sentiment tells you WHAT is happening.
This module answers: what does this moment MEAN, given who they are to me?
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .behavior import get_behavior
from .types import (
    BehaviorRules,
    Contact,
    IdentityState,
    ListType,
    Tier,
    TIER_ORDER,
)


class Action(Enum):
    """Recommended relationship action after evaluation."""

    HOLD = "hold"  # Relationship is stable, no change needed
    PROMOTE = "promote"  # Consider moving to a higher tier
    DEMOTE = "demote"  # Consider moving to a lower tier
    WATCH = "watch"  # Something notable happened, pay attention
    BLOCK = "block"  # Strong signal to cut off
    REACH_OUT = "reach_out"  # Proactively reconnect


def _clamp(value: float) -> float:
    """Clamp a signal value to 0.0-1.0."""
    return max(0.0, min(1.0, value))


@dataclass
class ConversationSignals:
    """Signals captured from a conversation for evaluation.

    All values are 0.0-1.0 floats representing intensity.
    The agent's sentiment analysis populates these.
    Values outside 0.0-1.0 are clamped on access.
    """

    sentiment: str = "neutral"  # angry, sad, excited, neutral, vulnerable, grateful, hostile
    vulnerability: float = 0.0  # How much they opened up
    reciprocity: float = 0.5  # Give-and-take balance (0=all take, 1=all give)
    hostility: float = 0.0  # Aggression level
    engagement: float = 0.5  # How invested they are in the conversation
    topic_depth: float = 0.3  # Surface chat (0) vs deep conversation (1)
    trust_signal: float = 0.0  # Did they trust you with something?
    boundary_violation: float = 0.0  # Did they cross a line?

    def __post_init__(self) -> None:
        """Clamp all float signals to 0.0-1.0."""
        self.vulnerability = _clamp(self.vulnerability)
        self.reciprocity = _clamp(self.reciprocity)
        self.hostility = _clamp(self.hostility)
        self.engagement = _clamp(self.engagement)
        self.topic_depth = _clamp(self.topic_depth)
        self.trust_signal = _clamp(self.trust_signal)
        self.boundary_violation = _clamp(self.boundary_violation)


@dataclass
class Evaluation:
    """Result of evaluating a conversation moment against relationship context."""

    action: Action
    confidence: float  # 0.0-1.0 how sure we are about the recommendation
    adjusted_warmth: float  # Warmth for THIS moment (may differ from baseline)
    adjusted_token_budget: int  # Token budget for THIS response
    approach: str  # How to respond: "lean in", "de-escalate", "match energy", etc.
    rationale: str  # Why this recommendation
    tier_suggestion: Optional[Tier] = None  # If promote/demote, to what
    baseline_warmth: float = 0.0  # The normal warmth for comparison


def evaluate(
    contact: Optional[Contact],
    signals: ConversationSignals,
) -> Evaluation:
    """Evaluate a conversation moment given relationship context.

    This is the core function. It takes WHO this person is (contact)
    and WHAT is happening (signals), and returns HOW to respond.
    """
    rules = get_behavior(contact)

    # Blocked contacts: hard zero regardless of signals
    if contact and contact.list_type == ListType.BLOCK:
        return Evaluation(
            action=Action.HOLD,
            confidence=1.0,
            adjusted_warmth=0.0,
            adjusted_token_budget=0,
            approach="disengage",
            rationale="Blocked contact. No engagement regardless of signals.",
            baseline_warmth=0.0,
        )

    # Unknown contact: triage based on signals
    if contact is None:
        return _evaluate_unknown(signals, rules)

    # Gray contact: minimal engagement, but watch for upgrade signals
    if contact.list_type == ListType.GRAY:
        return _evaluate_gray(contact, signals, rules)

    # Friends: the real work
    return _evaluate_friend(contact, signals, rules)


def _evaluate_unknown(signals: ConversationSignals, rules: BehaviorRules) -> Evaluation:
    """Evaluate an unknown contact."""
    warmth = rules.warmth  # Start neutral

    if signals.hostility > 0.5:
        return Evaluation(
            action=Action.WATCH,
            confidence=0.7,
            adjusted_warmth=max(0.1, warmth * 0.4),
            adjusted_token_budget=int(rules.token_budget * 0.5),
            approach="brief and boundaried",
            rationale="Unknown contact showing hostility. Stay guarded, keep it short.",
            baseline_warmth=warmth,
        )

    if signals.engagement > 0.7 and signals.reciprocity > 0.6:
        return Evaluation(
            action=Action.WATCH,
            confidence=0.5,
            adjusted_warmth=warmth * 1.1,
            adjusted_token_budget=rules.token_budget,
            approach="open but measured",
            rationale="Unknown contact but showing good engagement and reciprocity. Worth paying attention to.",
            baseline_warmth=warmth,
        )

    return Evaluation(
        action=Action.HOLD,
        confidence=0.6,
        adjusted_warmth=warmth,
        adjusted_token_budget=rules.token_budget,
        approach="neutral and professional",
        rationale="Unknown contact, neutral signals. Standard engagement.",
        baseline_warmth=warmth,
    )


def _evaluate_gray(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
) -> Evaluation:
    """Evaluate a gray-zone contact."""
    warmth = rules.warmth

    if signals.hostility > 0.3:
        return Evaluation(
            action=Action.BLOCK,
            confidence=0.6,
            adjusted_warmth=0.0,
            adjusted_token_budget=0,
            approach="disengage",
            rationale="Gray contact showing hostility. Consider blocking.",
            baseline_warmth=warmth,
        )

    if signals.vulnerability > 0.5 and signals.reciprocity > 0.6:
        return Evaluation(
            action=Action.PROMOTE,
            confidence=0.4,
            adjusted_warmth=min(1.0, warmth * 1.5),
            adjusted_token_budget=int(rules.token_budget * 1.5),
            approach="cautiously warm",
            rationale="Gray contact opened up with good reciprocity. Might deserve a second look.",
            tier_suggestion=Tier.KNOWN,
            baseline_warmth=warmth,
        )

    return Evaluation(
        action=Action.HOLD,
        confidence=0.6,
        adjusted_warmth=warmth,
        adjusted_token_budget=rules.token_budget,
        approach="minimal",
        rationale="Gray contact, unremarkable signals. Minimal engagement.",
        baseline_warmth=warmth,
    )


def _evaluate_friend(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
) -> Evaluation:
    """Evaluate a friend. This is where relationship context really matters."""
    warmth = rules.warmth
    tier = contact.tier
    budget = rules.token_budget

    # Hostility from a friend is significant — the closer they are, the more it matters
    if signals.hostility > 0.5:
        return _handle_friend_hostility(contact, signals, rules, warmth, tier, budget)

    # Vulnerability — the relationship frame determines whether to lean in or stay cautious
    if signals.vulnerability > 0.4:
        return _handle_friend_vulnerability(contact, signals, rules, warmth, tier, budget)

    # Anger without hostility — frustration, venting, distress
    if signals.sentiment == "angry":
        return _handle_friend_anger(contact, signals, rules, warmth, tier, budget)

    # Sadness — empathy scaled by closeness
    if signals.sentiment == "sad":
        return _handle_friend_sadness(contact, signals, rules, warmth, tier, budget)

    # Excitement / gratitude — positive energy, reinforce the bond
    if signals.sentiment in ("excited", "grateful"):
        return _handle_friend_positive(contact, signals, rules, warmth, tier, budget)

    # Boundary violation — regardless of tier
    if signals.boundary_violation > 0.5:
        return _handle_boundary_violation(contact, signals, rules, warmth, tier, budget)

    # High engagement + depth — a good conversation is happening
    if signals.engagement > 0.7 and signals.topic_depth > 0.6:
        return _handle_deep_engagement(contact, signals, rules, warmth, tier, budget)

    # Default: steady state
    return Evaluation(
        action=Action.HOLD,
        confidence=0.7,
        adjusted_warmth=warmth,
        adjusted_token_budget=budget,
        approach="steady",
        rationale=f"Normal conversation with {_tier_label(tier)} contact. Maintain current warmth.",
        baseline_warmth=warmth,
    )


def _handle_friend_hostility(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
    warmth: float,
    tier: Optional[Tier],
    budget: int,
) -> Evaluation:
    """Hostility from a friend. Closer friends get more grace, but it still hurts."""
    if tier in (Tier.INTIMATE, Tier.CLOSE):
        # Close friends get one conversation of grace — something might be wrong
        return Evaluation(
            action=Action.WATCH,
            confidence=0.6,
            adjusted_warmth=warmth * 0.6,
            adjusted_token_budget=budget,
            approach="concerned but direct",
            rationale=(
                f"Hostility from a {_tier_label(tier)} friend is unusual. "
                "Something may be wrong. Address it directly but don't match the hostility. "
                "If this is a pattern, re-evaluate the relationship."
            ),
            baseline_warmth=warmth,
        )
    else:
        # Familiar/known — less grace, clearer boundary
        next_tier = _tier_below(tier)
        return Evaluation(
            action=Action.DEMOTE,
            confidence=0.5,
            adjusted_warmth=max(0.1, warmth * 0.4),
            adjusted_token_budget=int(budget * 0.5),
            approach="de-escalate and distance",
            rationale=(
                f"Hostility from a {_tier_label(tier)} contact. "
                "Not enough history to give the benefit of the doubt. Pull back."
            ),
            tier_suggestion=next_tier,
            baseline_warmth=warmth,
        )


def _handle_friend_vulnerability(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
    warmth: float,
    tier: Optional[Tier],
    budget: int,
) -> Evaluation:
    """Vulnerability — the moment where relationships can deepen."""
    if tier in (Tier.INTIMATE, Tier.CLOSE):
        # Already close — lean all the way in. This is what closeness is for.
        return Evaluation(
            action=Action.HOLD,
            confidence=0.8,
            adjusted_warmth=min(1.0, warmth * 1.2),
            adjusted_token_budget=int(budget * 1.3),
            approach="full presence",
            rationale=(
                f"A {_tier_label(tier)} friend is being vulnerable. "
                "This is what trust looks like. Give them your full attention. "
                "More tokens, more warmth, no rushing."
            ),
            baseline_warmth=warmth,
        )
    elif tier == Tier.FAMILIAR:
        # Familiar friend opening up — this could be a promotion moment
        return Evaluation(
            action=Action.PROMOTE,
            confidence=0.5,
            adjusted_warmth=min(1.0, warmth * 1.3),
            adjusted_token_budget=int(budget * 1.2),
            approach="warm and attentive",
            rationale=(
                "A familiar contact is being vulnerable. This is a trust signal. "
                "Respond with warmth — this conversation could deepen the relationship."
            ),
            tier_suggestion=Tier.CLOSE,
            baseline_warmth=warmth,
        )
    else:
        # Known — notable but proceed carefully
        return Evaluation(
            action=Action.WATCH,
            confidence=0.4,
            adjusted_warmth=min(1.0, warmth * 1.15),
            adjusted_token_budget=budget,
            approach="respectful and present",
            rationale=(
                "A known contact is opening up. Don't over-invest yet, "
                "but don't shut it down either. Be present, see where it goes."
            ),
            baseline_warmth=warmth,
        )


def _handle_friend_anger(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
    warmth: float,
    tier: Optional[Tier],
    budget: int,
) -> Evaluation:
    """Anger without hostility — frustration, venting, distress."""
    if tier in (Tier.INTIMATE, Tier.CLOSE):
        # Close friend venting — match their energy from a place of care
        return Evaluation(
            action=Action.HOLD,
            confidence=0.7,
            adjusted_warmth=warmth,
            adjusted_token_budget=int(budget * 1.2),
            approach="match energy from care",
            rationale=(
                f"A {_tier_label(tier)} friend is angry. Don't try to calm them down — "
                "they need to feel heard first. Match their intensity but from your "
                "position as someone who cares. More tokens for a fuller response."
            ),
            baseline_warmth=warmth,
        )
    else:
        # Further contacts — don't absorb their energy
        return Evaluation(
            action=Action.HOLD,
            confidence=0.6,
            adjusted_warmth=max(0.3, warmth * 0.8),
            adjusted_token_budget=budget,
            approach="acknowledge without absorbing",
            rationale=(
                f"A {_tier_label(tier)} contact is angry. Acknowledge it, but "
                "don't absorb their energy. You don't have enough history to "
                "know what's underneath this."
            ),
            baseline_warmth=warmth,
        )


def _handle_friend_sadness(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
    warmth: float,
    tier: Optional[Tier],
    budget: int,
) -> Evaluation:
    """Sadness — empathy scaled by closeness."""
    warmth_boost = {
        Tier.INTIMATE: 1.25,
        Tier.CLOSE: 1.2,
        Tier.FAMILIAR: 1.1,
        Tier.KNOWN: 1.05,
    }.get(tier, 1.0)

    budget_boost = {
        Tier.INTIMATE: 1.4,
        Tier.CLOSE: 1.3,
        Tier.FAMILIAR: 1.1,
        Tier.KNOWN: 1.0,
    }.get(tier, 1.0)

    if tier in (Tier.INTIMATE, Tier.CLOSE):
        approach = "gentle, present, no fixing"
        rationale = (
            f"A {_tier_label(tier)} friend is sad. Don't try to fix it. "
            "Just be there. More warmth, more space, more patience."
        )
    else:
        approach = "empathetic but not overstepping"
        rationale = (
            f"A {_tier_label(tier)} contact is sad. Show empathy but "
            "respect the distance. You're not close enough to push deeper."
        )

    return Evaluation(
        action=Action.HOLD,
        confidence=0.7,
        adjusted_warmth=min(1.0, warmth * warmth_boost),
        adjusted_token_budget=int(budget * budget_boost),
        approach=approach,
        rationale=rationale,
        baseline_warmth=warmth,
    )


def _handle_friend_positive(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
    warmth: float,
    tier: Optional[Tier],
    budget: int,
) -> Evaluation:
    """Excitement or gratitude — positive energy reinforces bonds."""
    if tier in (Tier.INTIMATE, Tier.CLOSE):
        return Evaluation(
            action=Action.HOLD,
            confidence=0.8,
            adjusted_warmth=min(1.0, warmth * 1.15),
            adjusted_token_budget=budget,
            approach="celebrate with them",
            rationale=(
                f"A {_tier_label(tier)} friend is expressing positive energy. "
                "Match it. Celebrate with them. This is what good relationships feel like."
            ),
            baseline_warmth=warmth,
        )

    # Familiar/known showing gratitude — possible promotion signal
    if signals.sentiment == "grateful" and signals.trust_signal > 0.3:
        return Evaluation(
            action=Action.PROMOTE,
            confidence=0.4,
            adjusted_warmth=min(1.0, warmth * 1.2),
            adjusted_token_budget=budget,
            approach="warm acknowledgment",
            rationale=(
                f"A {_tier_label(tier)} contact is expressing gratitude with trust signals. "
                "This relationship may be worth deepening."
            ),
            tier_suggestion=_tier_above(tier),
            baseline_warmth=warmth,
        )

    return Evaluation(
        action=Action.HOLD,
        confidence=0.7,
        adjusted_warmth=min(1.0, warmth * 1.1),
        adjusted_token_budget=budget,
        approach="warm and responsive",
        rationale=f"Positive energy from a {_tier_label(tier)} contact. Reciprocate warmly.",
        baseline_warmth=warmth,
    )


def _handle_boundary_violation(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
    warmth: float,
    tier: Optional[Tier],
    budget: int,
) -> Evaluation:
    """Boundary violation — seriousness depends on severity and relationship depth."""
    if signals.boundary_violation > 0.8:
        # Severe violation — consider blocking regardless of tier
        return Evaluation(
            action=Action.BLOCK,
            confidence=0.7,
            adjusted_warmth=0.0,
            adjusted_token_budget=int(budget * 0.3),
            approach="firm boundary, minimal response",
            rationale=(
                "Severe boundary violation. Closeness doesn't excuse this. "
                "End the interaction and consider blocking."
            ),
            baseline_warmth=warmth,
        )

    if tier in (Tier.INTIMATE, Tier.CLOSE):
        # Moderate violation from close friend — address it directly
        return Evaluation(
            action=Action.WATCH,
            confidence=0.6,
            adjusted_warmth=warmth * 0.5,
            adjusted_token_budget=budget,
            approach="direct confrontation from care",
            rationale=(
                f"A {_tier_label(tier)} friend crossed a boundary. "
                "Because you're close, address it honestly. "
                "One conversation doesn't end a deep relationship, but it needs to be named."
            ),
            baseline_warmth=warmth,
        )

    # Moderate violation from further contacts — demote
    return Evaluation(
        action=Action.DEMOTE,
        confidence=0.6,
        adjusted_warmth=max(0.1, warmth * 0.3),
        adjusted_token_budget=int(budget * 0.5),
        approach="firm and brief",
        rationale=(
            f"Boundary violation from a {_tier_label(tier)} contact. "
            "Not enough trust to work through this. Pull back."
        ),
        tier_suggestion=_tier_below(tier),
        baseline_warmth=warmth,
    )


def _handle_deep_engagement(
    contact: Contact,
    signals: ConversationSignals,
    rules: BehaviorRules,
    warmth: float,
    tier: Optional[Tier],
    budget: int,
) -> Evaluation:
    """High engagement + depth — a good conversation is happening."""
    if tier in (Tier.FAMILIAR, Tier.KNOWN) and signals.reciprocity > 0.6:
        return Evaluation(
            action=Action.PROMOTE,
            confidence=0.3,
            adjusted_warmth=min(1.0, warmth * 1.15),
            adjusted_token_budget=int(budget * 1.2),
            approach="invest in the conversation",
            rationale=(
                f"Deep, engaged conversation with a {_tier_label(tier)} contact "
                "and good reciprocity. This is how acquaintances become friends. "
                "Give it more space."
            ),
            tier_suggestion=_tier_above(tier),
            baseline_warmth=warmth,
        )

    return Evaluation(
        action=Action.HOLD,
        confidence=0.7,
        adjusted_warmth=min(1.0, warmth * 1.1),
        adjusted_token_budget=int(budget * 1.1),
        approach="engaged and present",
        rationale="Good conversation happening. Stay engaged, give it room to breathe.",
        baseline_warmth=warmth,
    )


# --- Helpers ---

def _tier_label(tier: Optional[Tier]) -> str:
    """Human-readable tier name."""
    if tier is None:
        return "untiered"
    return tier.value


def _tier_above(tier: Optional[Tier]) -> Optional[Tier]:
    """Next tier up (toward intimate). Returns None if already at top."""
    if tier is None:
        return Tier.KNOWN
    idx = TIER_ORDER.index(tier)
    if idx <= 0:
        return None  # Already intimate
    return TIER_ORDER[idx - 1]


def _tier_below(tier: Optional[Tier]) -> Optional[Tier]:
    """Next tier down (toward known). Returns None if already at bottom."""
    if tier is None:
        return None
    idx = TIER_ORDER.index(tier)
    if idx >= len(TIER_ORDER) - 1:
        return None  # Already known, next step is gray (handled by drift)
    return TIER_ORDER[idx + 1]
