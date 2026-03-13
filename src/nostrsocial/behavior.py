"""Tier-based behavioral rules for social graph contacts."""

from __future__ import annotations

from typing import Optional

from .types import BehaviorRules, Contact, IdentityState, Tier


# Behavioral parameters for each trust tier
TIER_BEHAVIORS: dict[Tier, BehaviorRules] = {
    Tier.INTIMATE: BehaviorRules(
        token_budget=2000,
        memory_depth=20,
        can_interrupt=True,
        warmth=0.95,
        response_priority=1,
        share_context=True,
        proactive_contact=True,
    ),
    Tier.CLOSE: BehaviorRules(
        token_budget=1500,
        memory_depth=15,
        can_interrupt=True,
        warmth=0.8,
        response_priority=2,
        share_context=True,
        proactive_contact=True,
    ),
    Tier.FAMILIAR: BehaviorRules(
        token_budget=1000,
        memory_depth=10,
        can_interrupt=False,
        warmth=0.6,
        response_priority=3,
        share_context=False,
        proactive_contact=False,
    ),
    Tier.KNOWN: BehaviorRules(
        token_budget=750,
        memory_depth=5,
        can_interrupt=False,
        warmth=0.5,
        response_priority=4,
        share_context=False,
        proactive_contact=False,
    ),
}

BLOCK_BEHAVIOR = BehaviorRules(
    token_budget=0,
    memory_depth=0,
    can_interrupt=False,
    warmth=0.0,
    response_priority=10,
    share_context=False,
    proactive_contact=False,
)

GRAY_BEHAVIOR = BehaviorRules(
    token_budget=200,
    memory_depth=1,
    can_interrupt=False,
    warmth=0.2,
    response_priority=8,
    share_context=False,
    proactive_contact=False,
)

NEUTRAL_BEHAVIOR = BehaviorRules(
    token_budget=500,
    memory_depth=3,
    can_interrupt=False,
    warmth=0.5,
    response_priority=5,
    share_context=False,
    proactive_contact=False,
)

# Verified contacts get a subtle warmth boost
_VERIFIED_WARMTH_BOOST = 0.05


def get_behavior(contact: Optional[Contact] = None) -> BehaviorRules:
    """Return behavioral rules for a contact. Returns NEUTRAL for None."""
    if contact is None:
        return NEUTRAL_BEHAVIOR

    from .types import ListType

    if contact.list_type == ListType.BLOCK:
        return BLOCK_BEHAVIOR

    if contact.list_type == ListType.GRAY:
        return GRAY_BEHAVIOR

    if contact.list_type == ListType.FRIENDS and contact.tier:
        base = TIER_BEHAVIORS[contact.tier]
        if contact.identity_state == IdentityState.VERIFIED:
            return BehaviorRules(
                token_budget=base.token_budget,
                memory_depth=base.memory_depth,
                can_interrupt=base.can_interrupt,
                warmth=min(1.0, base.warmth + _VERIFIED_WARMTH_BOOST),
                response_priority=base.response_priority,
                share_context=base.share_context,
                proactive_contact=base.proactive_contact,
            )
        return base

    return NEUTRAL_BEHAVIOR


def compute_upgrade_hint(contact: Contact) -> str:
    """Generate an ambient npub draw hint based on identity state."""
    if contact.identity_state == IdentityState.PROXY:
        return "Ask for their npub or suggest npub.bio"
    if contact.identity_state == IdentityState.CLAIMED:
        return "Use create_challenge() to verify ownership"
    return ""
