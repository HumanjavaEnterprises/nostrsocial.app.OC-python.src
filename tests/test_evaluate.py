"""Tests for conversation evaluation — the bridge between sentiment and relationships."""

import pytest

from nostrsocial import (
    Action,
    Contact,
    ConversationSignals,
    Evaluation,
    IdentityState,
    ListType,
    SocialEnclave,
    Tier,
    evaluate,
)


# --- Helpers ---

def _friend(tier: Tier, **kwargs) -> Contact:
    return Contact(
        identifier="test@example.com",
        channel="email",
        list_type=ListType.FRIENDS,
        tier=tier,
        proxy_npub="npub1test",
        **kwargs,
    )


def _blocked() -> Contact:
    return Contact(
        identifier="spam@bad.com",
        channel="email",
        list_type=ListType.BLOCK,
        proxy_npub="npub1spam",
    )


def _gray() -> Contact:
    return Contact(
        identifier="meh@example.com",
        channel="email",
        list_type=ListType.GRAY,
        proxy_npub="npub1gray",
    )


def _signals(**kwargs) -> ConversationSignals:
    return ConversationSignals(**kwargs)


# --- Tests ---

class TestBlockedContact:
    def test_always_disengage(self):
        result = evaluate(_blocked(), _signals(sentiment="grateful", engagement=1.0))
        assert result.adjusted_warmth == 0.0
        assert result.adjusted_token_budget == 0
        assert result.approach == "disengage"

    def test_hostility_still_zero(self):
        result = evaluate(_blocked(), _signals(hostility=1.0))
        assert result.adjusted_warmth == 0.0


class TestUnknownContact:
    def test_neutral_signals(self):
        result = evaluate(None, _signals())
        assert result.action == Action.HOLD
        assert result.adjusted_warmth == 0.5  # NEUTRAL warmth
        assert "neutral" in result.approach.lower() or "professional" in result.approach.lower()

    def test_hostile_unknown(self):
        result = evaluate(None, _signals(hostility=0.7))
        assert result.action == Action.WATCH
        assert result.adjusted_warmth < 0.5  # Pulled back
        assert result.adjusted_token_budget < 500  # Less tokens

    def test_engaged_unknown(self):
        result = evaluate(None, _signals(engagement=0.8, reciprocity=0.7))
        assert result.action == Action.WATCH
        assert result.adjusted_warmth >= 0.5  # Slightly warmer


class TestGrayContact:
    def test_neutral_gray(self):
        result = evaluate(_gray(), _signals())
        assert result.action == Action.HOLD
        assert result.approach == "minimal"

    def test_hostile_gray_suggests_block(self):
        result = evaluate(_gray(), _signals(hostility=0.5))
        assert result.action == Action.BLOCK

    def test_vulnerable_gray_with_reciprocity(self):
        result = evaluate(_gray(), _signals(vulnerability=0.6, reciprocity=0.7))
        assert result.action == Action.PROMOTE
        assert result.tier_suggestion == Tier.KNOWN
        assert result.adjusted_warmth > 0.2  # Warmer than gray baseline


class TestIntimateContact:
    def test_steady_state(self):
        result = evaluate(_friend(Tier.INTIMATE), _signals())
        assert result.action == Action.HOLD
        assert result.adjusted_warmth == 0.95  # Full intimate warmth

    def test_anger_match_energy(self):
        result = evaluate(_friend(Tier.INTIMATE), _signals(sentiment="angry"))
        assert result.action == Action.HOLD
        assert "match" in result.approach.lower() or "care" in result.approach.lower()
        assert result.adjusted_token_budget > 2000  # More tokens to respond fully

    def test_vulnerability_full_presence(self):
        result = evaluate(_friend(Tier.INTIMATE), _signals(vulnerability=0.8))
        assert result.action == Action.HOLD
        assert result.adjusted_warmth > 0.95  # Warmer than baseline
        assert result.adjusted_token_budget > 2000
        assert "presence" in result.approach.lower()

    def test_hostility_gets_grace(self):
        result = evaluate(_friend(Tier.INTIMATE), _signals(hostility=0.7))
        assert result.action == Action.WATCH  # Grace, not demote
        assert "concern" in result.rationale.lower() or "wrong" in result.rationale.lower()

    def test_sadness_lean_in(self):
        result = evaluate(_friend(Tier.INTIMATE), _signals(sentiment="sad"))
        assert result.adjusted_warmth > 0.95
        assert result.adjusted_token_budget > 2000
        assert "fix" in result.rationale.lower()  # "don't try to fix it"

    def test_excitement_celebrate(self):
        result = evaluate(_friend(Tier.INTIMATE), _signals(sentiment="excited"))
        assert result.action == Action.HOLD
        assert "celebrate" in result.approach.lower()

    def test_severe_boundary_violation(self):
        result = evaluate(_friend(Tier.INTIMATE), _signals(boundary_violation=0.9))
        assert result.action == Action.BLOCK  # Even intimates can't do this
        assert result.adjusted_warmth == 0.0

    def test_moderate_boundary_violation(self):
        result = evaluate(_friend(Tier.INTIMATE), _signals(boundary_violation=0.6))
        assert result.action == Action.WATCH  # Grace for close friend
        assert "direct" in result.approach.lower() or "confrontation" in result.approach.lower()


class TestCloseContact:
    def test_anger_from_care(self):
        result = evaluate(_friend(Tier.CLOSE), _signals(sentiment="angry"))
        assert result.action == Action.HOLD
        assert result.adjusted_token_budget > 1500

    def test_vulnerability_lean_in(self):
        result = evaluate(_friend(Tier.CLOSE), _signals(vulnerability=0.7))
        assert result.action == Action.HOLD
        assert result.adjusted_warmth > 0.8

    def test_hostility_grace(self):
        result = evaluate(_friend(Tier.CLOSE), _signals(hostility=0.7))
        assert result.action == Action.WATCH  # Close friends get grace


class TestFamiliarContact:
    def test_vulnerability_promotion_signal(self):
        result = evaluate(_friend(Tier.FAMILIAR), _signals(vulnerability=0.6))
        assert result.action == Action.PROMOTE
        assert result.tier_suggestion == Tier.CLOSE
        assert result.adjusted_warmth > 0.6

    def test_hostility_demote(self):
        result = evaluate(_friend(Tier.FAMILIAR), _signals(hostility=0.7))
        assert result.action == Action.DEMOTE
        assert result.tier_suggestion == Tier.KNOWN

    def test_deep_engagement_promote(self):
        result = evaluate(
            _friend(Tier.FAMILIAR),
            _signals(engagement=0.8, topic_depth=0.7, reciprocity=0.7),
        )
        assert result.action == Action.PROMOTE
        assert result.tier_suggestion == Tier.CLOSE

    def test_anger_acknowledge_without_absorbing(self):
        result = evaluate(_friend(Tier.FAMILIAR), _signals(sentiment="angry"))
        assert "absorb" in result.rationale.lower() or "acknowledge" in result.approach.lower()


class TestKnownContact:
    def test_vulnerability_watched(self):
        result = evaluate(_friend(Tier.KNOWN), _signals(vulnerability=0.5))
        assert result.action == Action.WATCH
        assert result.adjusted_warmth > 0.5  # Slightly warmer

    def test_hostility_demote(self):
        result = evaluate(_friend(Tier.KNOWN), _signals(hostility=0.7))
        assert result.action == Action.DEMOTE

    def test_grateful_with_trust(self):
        result = evaluate(
            _friend(Tier.KNOWN),
            _signals(sentiment="grateful", trust_signal=0.5),
        )
        assert result.action == Action.PROMOTE
        assert result.tier_suggestion == Tier.FAMILIAR

    def test_deep_engagement(self):
        result = evaluate(
            _friend(Tier.KNOWN),
            _signals(engagement=0.8, topic_depth=0.7, reciprocity=0.7),
        )
        assert result.action == Action.PROMOTE
        assert result.tier_suggestion == Tier.FAMILIAR


class TestWarmthModulation:
    """The core value prop: same signal, different warmth based on relationship."""

    def test_anger_warmth_scales_with_closeness(self):
        intimate = evaluate(_friend(Tier.INTIMATE), _signals(sentiment="angry"))
        known = evaluate(_friend(Tier.KNOWN), _signals(sentiment="angry"))
        assert intimate.adjusted_warmth > known.adjusted_warmth

    def test_sadness_warmth_scales_with_closeness(self):
        intimate = evaluate(_friend(Tier.INTIMATE), _signals(sentiment="sad"))
        known = evaluate(_friend(Tier.KNOWN), _signals(sentiment="sad"))
        assert intimate.adjusted_warmth > known.adjusted_warmth

    def test_hostility_response_varies_by_tier(self):
        intimate = evaluate(_friend(Tier.INTIMATE), _signals(hostility=0.7))
        familiar = evaluate(_friend(Tier.FAMILIAR), _signals(hostility=0.7))
        assert intimate.action == Action.WATCH  # Grace
        assert familiar.action == Action.DEMOTE  # No grace

    def test_vulnerability_response_varies_by_tier(self):
        intimate = evaluate(_friend(Tier.INTIMATE), _signals(vulnerability=0.6))
        familiar = evaluate(_friend(Tier.FAMILIAR), _signals(vulnerability=0.6))
        known = evaluate(_friend(Tier.KNOWN), _signals(vulnerability=0.6))
        assert intimate.action == Action.HOLD  # Already close, just be there
        assert familiar.action == Action.PROMOTE  # Could deepen
        assert known.action == Action.WATCH  # Interesting but don't overinvest

    def test_baseline_warmth_always_set(self):
        result = evaluate(_friend(Tier.CLOSE), _signals(sentiment="sad"))
        assert result.baseline_warmth == 0.8  # Close tier baseline
        assert result.adjusted_warmth >= result.baseline_warmth  # Sadness warms up


class TestEnclavEvaluate:
    """Test the evaluate method on SocialEnclave."""

    def test_evaluate_known_contact(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        result = e.evaluate(
            "alice@example.com", "email",
            ConversationSignals(sentiment="sad"),
        )
        assert result.adjusted_warmth > 0.8
        assert result.action == Action.HOLD

    def test_evaluate_unknown_contact(self):
        e = SocialEnclave.create()
        result = e.evaluate(
            "stranger@example.com", "email",
            ConversationSignals(),
        )
        assert result.action == Action.HOLD
        assert result.adjusted_warmth == 0.5

    def test_evaluate_blocked_contact(self):
        e = SocialEnclave.create()
        e.block("spam@bad.com", "email")
        result = e.evaluate(
            "spam@bad.com", "email",
            ConversationSignals(sentiment="grateful"),
        )
        assert result.adjusted_warmth == 0.0
        assert result.adjusted_token_budget == 0


class TestSignalClamping:
    """Signals outside 0.0-1.0 are clamped, not passed through."""

    def test_negative_hostility_clamped(self):
        signals = ConversationSignals(hostility=-1.0)
        assert signals.hostility == 0.0

    def test_high_hostility_clamped(self):
        signals = ConversationSignals(hostility=5.0)
        assert signals.hostility == 1.0

    def test_negative_vulnerability_clamped(self):
        signals = ConversationSignals(vulnerability=-0.5)
        assert signals.vulnerability == 0.0

    def test_high_boundary_violation_clamped(self):
        signals = ConversationSignals(boundary_violation=2.0)
        assert signals.boundary_violation == 1.0

    def test_all_signals_clamp(self):
        signals = ConversationSignals(
            vulnerability=10.0, reciprocity=-1.0, hostility=5.0,
            engagement=-0.1, topic_depth=2.0, trust_signal=99.0,
            boundary_violation=-5.0,
        )
        assert signals.vulnerability == 1.0
        assert signals.reciprocity == 0.0
        assert signals.hostility == 1.0
        assert signals.engagement == 0.0
        assert signals.topic_depth == 1.0
        assert signals.trust_signal == 1.0
        assert signals.boundary_violation == 0.0

    def test_valid_signals_unchanged(self):
        signals = ConversationSignals(hostility=0.5, vulnerability=0.3)
        assert signals.hostility == 0.5
        assert signals.vulnerability == 0.3


class TestHostilityOverridesVulnerability:
    """When both hostility and vulnerability are high, hostility wins (checked first)."""

    def test_intimate_hostility_wins(self):
        result = evaluate(
            _friend(Tier.INTIMATE),
            _signals(hostility=0.8, vulnerability=0.8),
        )
        # Hostility check fires first — grace for intimate friend
        assert result.action == Action.WATCH
        assert "hostility" in result.rationale.lower() or "hostile" in result.rationale.lower()

    def test_known_hostility_wins(self):
        result = evaluate(
            _friend(Tier.KNOWN),
            _signals(hostility=0.8, vulnerability=0.8),
        )
        assert result.action == Action.DEMOTE


class TestBoundaryEdgeCases:
    def test_boundary_at_exact_threshold(self):
        """boundary_violation=0.5 does NOT trigger boundary handler (> 0.5 required)."""
        result = evaluate(
            _friend(Tier.CLOSE),
            _signals(boundary_violation=0.5),
        )
        # Falls through to default steady-state
        assert result.action == Action.HOLD

    def test_severe_boundary_blocks_even_intimate(self):
        result = evaluate(
            _friend(Tier.INTIMATE),
            _signals(boundary_violation=0.9),
        )
        assert result.action == Action.BLOCK


class TestPromoteDemoteDirection:
    """promote() and demote() enforce directionality."""

    def test_promote_wrong_direction_raises(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.INTIMATE)
        with pytest.raises(ValueError, match="higher"):
            e.promote("alice@example.com", "email", Tier.KNOWN)

    def test_demote_wrong_direction_raises(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.KNOWN)
        with pytest.raises(ValueError, match="lower"):
            e.demote("alice@example.com", "email", Tier.INTIMATE)

    def test_promote_same_tier_raises(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        with pytest.raises(ValueError):
            e.promote("alice@example.com", "email", Tier.CLOSE)

    def test_promote_valid_succeeds(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.KNOWN)
        result = e.promote("alice@example.com", "email", Tier.FAMILIAR)
        assert result.tier == Tier.FAMILIAR

    def test_demote_valid_succeeds(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.INTIMATE)
        result = e.demote("alice@example.com", "email", Tier.CLOSE)
        assert result.tier == Tier.CLOSE
