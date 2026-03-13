"""Tests for behavioral rules mapping."""

from nostrsocial.behavior import (
    BLOCK_BEHAVIOR,
    GRAY_BEHAVIOR,
    NEUTRAL_BEHAVIOR,
    TIER_BEHAVIORS,
    compute_upgrade_hint,
    get_behavior,
)
from nostrsocial.types import (
    BehaviorRules,
    Contact,
    IdentityState,
    ListType,
    Tier,
)


class TestTierBehaviors:
    def test_all_tiers_mapped(self):
        for tier in Tier:
            assert tier in TIER_BEHAVIORS

    def test_intimate_highest_warmth(self):
        assert TIER_BEHAVIORS[Tier.INTIMATE].warmth > TIER_BEHAVIORS[Tier.CLOSE].warmth

    def test_intimate_can_interrupt(self):
        assert TIER_BEHAVIORS[Tier.INTIMATE].can_interrupt is True
        assert TIER_BEHAVIORS[Tier.CLOSE].can_interrupt is True
        assert TIER_BEHAVIORS[Tier.FAMILIAR].can_interrupt is False
        assert TIER_BEHAVIORS[Tier.KNOWN].can_interrupt is False

    def test_priority_ordering(self):
        priorities = [TIER_BEHAVIORS[t].response_priority for t in Tier]
        assert priorities == sorted(priorities)

    def test_token_budget_decreases(self):
        budgets = [TIER_BEHAVIORS[t].token_budget for t in Tier]
        assert budgets == sorted(budgets, reverse=True)


class TestSpecialBehaviors:
    def test_block_zero_engagement(self):
        assert BLOCK_BEHAVIOR.token_budget == 0
        assert BLOCK_BEHAVIOR.warmth == 0.0
        assert BLOCK_BEHAVIOR.memory_depth == 0

    def test_gray_minimal(self):
        assert GRAY_BEHAVIOR.token_budget == 200
        assert GRAY_BEHAVIOR.warmth == 0.2

    def test_neutral_default(self):
        assert NEUTRAL_BEHAVIOR.token_budget == 500
        assert NEUTRAL_BEHAVIOR.warmth == 0.5


class TestGetBehavior:
    def test_none_returns_neutral(self):
        assert get_behavior(None) == NEUTRAL_BEHAVIOR

    def test_blocked_contact(self):
        contact = Contact(
            identifier="spam@bad.com",
            channel="email",
            list_type=ListType.BLOCK,
        )
        assert get_behavior(contact) == BLOCK_BEHAVIOR

    def test_gray_contact(self):
        contact = Contact(
            identifier="meh@example.com",
            channel="email",
            list_type=ListType.GRAY,
        )
        assert get_behavior(contact) == GRAY_BEHAVIOR

    def test_friend_tier(self):
        contact = Contact(
            identifier="alice@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            tier=Tier.CLOSE,
        )
        rules = get_behavior(contact)
        assert rules.warmth == TIER_BEHAVIORS[Tier.CLOSE].warmth

    def test_verified_warmth_boost(self):
        contact = Contact(
            identifier="alice@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            tier=Tier.CLOSE,
            identity_state=IdentityState.VERIFIED,
        )
        rules = get_behavior(contact)
        base = TIER_BEHAVIORS[Tier.CLOSE]
        assert rules.warmth == base.warmth + 0.05

    def test_verified_boost_capped_at_one(self):
        contact = Contact(
            identifier="best@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            tier=Tier.INTIMATE,
            identity_state=IdentityState.VERIFIED,
        )
        rules = get_behavior(contact)
        assert rules.warmth <= 1.0


class TestUpgradeHint:
    def test_proxy_hint(self):
        contact = Contact(
            identifier="alice@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            identity_state=IdentityState.PROXY,
        )
        hint = compute_upgrade_hint(contact)
        assert "npub" in hint.lower() or "npub.bio" in hint

    def test_claimed_hint(self):
        contact = Contact(
            identifier="alice@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            identity_state=IdentityState.CLAIMED,
        )
        hint = compute_upgrade_hint(contact)
        assert "create_challenge" in hint

    def test_verified_no_hint(self):
        contact = Contact(
            identifier="alice@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            identity_state=IdentityState.VERIFIED,
        )
        hint = compute_upgrade_hint(contact)
        assert hint == ""
