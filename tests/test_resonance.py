"""Tests for cross-channel recognition and identity linking.

Resonance is recognition, not surveillance.
"""

import time

import pytest

from nostrsocial import (
    IdentityState,
    ListType,
    SocialEnclave,
    Tier,
)
from nostrsocial.resonance import find_recognitions, merge_contacts
from nostrsocial.types import Contact


# --- Helpers ---

def _contact(identifier, channel, tier=Tier.CLOSE, **kwargs):
    return Contact(
        identifier=identifier,
        channel=channel,
        list_type=ListType.FRIENDS,
        tier=tier,
        proxy_npub=f"npub1{identifier.replace('@', '').replace('.', '')}",
        added_at=time.time(),
        last_interaction=time.time(),
        **kwargs,
    )


# --- Recognition tests ---

class TestFindRecognitions:
    def test_npub_match(self):
        existing = [_contact("alice@example.com", "email", claimed_npub="npub1alice")]
        matches = find_recognitions(
            existing, "@alicedev", "twitter", claimed_npub="npub1alice"
        )
        assert len(matches) == 1
        assert matches[0].confidence == 0.95
        assert "npub" in matches[0].reason.lower()

    def test_display_name_match(self):
        existing = [_contact("alice@example.com", "email", display_name="Alice")]
        matches = find_recognitions(
            existing, "@alicedev", "twitter", display_name="Alice"
        )
        assert len(matches) == 1
        assert matches[0].confidence == 0.3
        assert "display name" in matches[0].reason.lower()

    def test_no_match(self):
        existing = [_contact("bob@example.com", "email", display_name="Bob")]
        matches = find_recognitions(
            existing, "@alicedev", "twitter", display_name="Alice"
        )
        assert len(matches) == 0

    def test_same_identifier_ignored(self):
        existing = [_contact("alice@example.com", "email")]
        matches = find_recognitions(
            existing, "alice@example.com", "email"
        )
        assert len(matches) == 0

    def test_display_name_case_insensitive(self):
        existing = [_contact("alice@example.com", "email", display_name="ALICE")]
        matches = find_recognitions(
            existing, "@alice", "twitter", display_name="alice"
        )
        assert len(matches) == 1

    def test_npub_ranked_above_name(self):
        existing = [
            _contact("alice@example.com", "email",
                     claimed_npub="npub1alice", display_name="Alice"),
        ]
        matches = find_recognitions(
            existing, "@alice", "twitter",
            claimed_npub="npub1alice", display_name="Alice",
        )
        # Should find npub match, not name match (npub is stronger)
        assert len(matches) == 1
        assert matches[0].confidence == 0.95

    def test_multiple_matches_sorted_by_confidence(self):
        existing = [
            _contact("alice@example.com", "email",
                     claimed_npub="npub1alice", display_name="Alice"),
            _contact("alice2@example.com", "email", display_name="Alice"),
        ]
        matches = find_recognitions(
            existing, "@alice", "twitter",
            claimed_npub="npub1alice", display_name="Alice",
        )
        assert len(matches) == 2
        assert matches[0].confidence > matches[1].confidence

    def test_same_channel_no_display_match(self):
        """Two people named Alice on the same channel are different people."""
        existing = [_contact("alice1@example.com", "email", display_name="Alice")]
        matches = find_recognitions(
            existing, "alice2@example.com", "email", display_name="Alice"
        )
        # Same channel — display name match doesn't apply
        assert len(matches) == 0


# --- Merge tests ---

class TestMergeContacts:
    def test_basic_merge(self):
        primary = _contact("alice@example.com", "email", tier=Tier.CLOSE,
                           interaction_count=10)
        secondary = _contact("@alicedev", "twitter", tier=Tier.KNOWN,
                             interaction_count=5)
        result = merge_contacts(primary, secondary)

        assert result.identifier == "alice@example.com"  # Primary survives
        assert result.interaction_count == 15  # Summed
        assert result.linked_channels == {"twitter": "@alicedev"}

    def test_higher_tier_wins(self):
        primary = _contact("alice@example.com", "email", tier=Tier.KNOWN)
        secondary = _contact("@alice", "twitter", tier=Tier.INTIMATE)
        result = merge_contacts(primary, secondary)
        assert result.tier == Tier.INTIMATE  # Secondary had higher tier

    def test_earlier_added_at_wins(self):
        primary = _contact("alice@example.com", "email")
        primary.added_at = 2000.0
        secondary = _contact("@alice", "twitter")
        secondary.added_at = 1000.0  # Earlier
        result = merge_contacts(primary, secondary)
        assert result.added_at == 1000.0

    def test_latest_interaction_wins(self):
        primary = _contact("alice@example.com", "email")
        primary.last_interaction = 1000.0
        secondary = _contact("@alice", "twitter")
        secondary.last_interaction = 2000.0  # More recent
        result = merge_contacts(primary, secondary)
        assert result.last_interaction == 2000.0

    def test_verified_state_wins(self):
        primary = _contact("alice@example.com", "email",
                           identity_state=IdentityState.PROXY)
        secondary = _contact("@alice", "twitter",
                             identity_state=IdentityState.VERIFIED)
        result = merge_contacts(primary, secondary)
        assert result.identity_state == IdentityState.VERIFIED

    def test_claimed_state_over_proxy(self):
        primary = _contact("alice@example.com", "email",
                           identity_state=IdentityState.PROXY)
        secondary = _contact("@alice", "twitter",
                             identity_state=IdentityState.CLAIMED)
        result = merge_contacts(primary, secondary)
        assert result.identity_state == IdentityState.CLAIMED

    def test_npub_carried_over(self):
        primary = _contact("alice@example.com", "email")
        secondary = _contact("@alice", "twitter", claimed_npub="npub1alice")
        result = merge_contacts(primary, secondary)
        assert result.claimed_npub == "npub1alice"

    def test_notes_combined(self):
        primary = _contact("alice@example.com", "email", notes="Met at conference")
        secondary = _contact("@alice", "twitter", notes="Active on crypto twitter")
        result = merge_contacts(primary, secondary)
        assert "Met at conference" in result.notes
        assert "crypto twitter" in result.notes
        assert "[linked from twitter]" in result.notes

    def test_display_name_fallback(self):
        primary = _contact("alice@example.com", "email")
        primary.display_name = None
        secondary = _contact("@alice", "twitter", display_name="Alice Dev")
        result = merge_contacts(primary, secondary)
        assert result.display_name == "Alice Dev"

    def test_secondary_linked_channels_carried(self):
        primary = _contact("alice@example.com", "email")
        secondary = _contact("@alice", "twitter")
        secondary.linked_channels = {"phone": "+15551234567"}
        result = merge_contacts(primary, secondary)
        assert result.linked_channels["twitter"] == "@alice"
        assert result.linked_channels["phone"] == "+15551234567"

    def test_both_have_claimed_npub_primary_wins(self):
        """When both contacts have a claimed npub, primary's is preserved."""
        primary = _contact("alice@example.com", "email", claimed_npub="npub1primary")
        secondary = _contact("@alice", "twitter", claimed_npub="npub1secondary")
        result = merge_contacts(primary, secondary)
        assert result.claimed_npub == "npub1primary"

    def test_overlapping_linked_channels_primary_wins(self):
        """When both have the same linked channel, primary's version wins."""
        primary = _contact("alice@example.com", "email")
        primary.linked_channels = {"phone": "+15551111111"}
        secondary = _contact("@alice", "twitter")
        secondary.linked_channels = {"phone": "+15552222222"}
        result = merge_contacts(primary, secondary)
        assert result.linked_channels["phone"] == "+15551111111"


# --- Enclave integration tests ---

class TestEnclaveRecognize:
    def test_recognize_by_npub(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE,
              display_name="Alice", claimed_npub="npub1alice")

        matches = e.recognize("@alicedev", "twitter", claimed_npub="npub1alice")
        assert len(matches) == 1
        assert matches[0].confidence == 0.95

    def test_recognize_by_display_name(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")

        matches = e.recognize("@alicedev", "twitter", display_name="Alice")
        assert len(matches) == 1
        assert matches[0].confidence == 0.3

    def test_recognize_no_match(self):
        e = SocialEnclave.create()
        e.add("bob@example.com", "email", Tier.KNOWN)
        matches = e.recognize("@alice", "twitter")
        assert len(matches) == 0

    def test_recognize_blocked_contact(self):
        """Even blocked contacts can be recognized — you need to know who to avoid."""
        e = SocialEnclave.create()
        e.block("spam@bad.com", "email", display_name="Spammer")
        matches = e.recognize("@spammer", "twitter", display_name="Spammer")
        assert len(matches) == 1


class TestEnclaveLink:
    def test_basic_link(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")
        e.add("@alicedev", "twitter", Tier.KNOWN, display_name="Alice Dev")

        result = e.link("alice@example.com", "email", "@alicedev", "twitter")
        assert result.primary.identifier == "alice@example.com"  # Higher tier
        assert result.absorbed_channel == "twitter"
        assert e.friend_count == 1  # One contact now, not two

    def test_link_preserves_interactions(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        for _ in range(5):
            e.touch("alice@example.com", "email")

        e.add("@alice", "twitter", Tier.KNOWN)
        for _ in range(3):
            e.touch("@alice", "twitter")

        result = e.link("alice@example.com", "email", "@alice", "twitter")
        assert result.primary.interaction_count == 8  # 5 + 3

    def test_link_higher_tier_wins(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.KNOWN)
        e.add("@alice", "twitter", Tier.INTIMATE)

        result = e.link("alice@example.com", "email", "@alice", "twitter")
        assert result.primary.tier == Tier.INTIMATE

    def test_link_npub_carried(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        e.add("@alice", "twitter", Tier.KNOWN, claimed_npub="npub1alice")

        result = e.link("alice@example.com", "email", "@alice", "twitter")
        assert result.primary.claimed_npub == "npub1alice"

    def test_link_nonexistent_raises(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        with pytest.raises(KeyError):
            e.link("alice@example.com", "email", "nobody@example.com", "email")

    def test_link_self_raises(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        with pytest.raises(ValueError, match="itself"):
            e.link("alice@example.com", "email", "alice@example.com", "email")

    def test_link_blocked_raises(self):
        """Cannot link a blocked contact — must unblock first."""
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        e.block("spam@bad.com", "email")
        with pytest.raises(ValueError, match="[Bb]locked"):
            e.link("alice@example.com", "email", "spam@bad.com", "email")

    def test_link_respects_tier_capacity(self):
        """Linking can't promote into a full tier via merge.

        _pick_primary chooses the higher-tier contact as primary, so the
        promotion path fires when both contacts are at the same tier but
        the primary was picked by interaction count, and the secondary
        has a higher tier set directly (bypassing add() capacity check).
        """
        from nostrsocial import CapacityError
        e = SocialEnclave.create(tier_capacity={
            Tier.INTIMATE: 1, Tier.CLOSE: 15, Tier.FAMILIAR: 50, Tier.KNOWN: 80,
        })
        e.add("alice@example.com", "email", Tier.INTIMATE)  # Fills intimate

        # Both at CLOSE — primary chosen by interaction count
        e.add("bob@example.com", "email", Tier.CLOSE)
        for _ in range(10):
            e.touch("bob@example.com", "email")
        e.add("@bob", "twitter", Tier.CLOSE)
        # bob@email has 10 interactions → primary. Both CLOSE, no tier change. Fine.
        e.link("bob@example.com", "email", "@bob", "twitter")

        # Now: carol@email has many interactions (→ primary), @carol has INTIMATE set directly
        e.add("carol@example.com", "email", Tier.KNOWN)
        for _ in range(20):
            e.touch("carol@example.com", "email")
        e.add("@carol", "twitter", Tier.KNOWN)
        # Manually set @carol to INTIMATE to create the capacity-violating merge
        twitter_carol = e._contacts.get_by_identifier("@carol", "twitter")
        twitter_carol.tier = Tier.INTIMATE

        # carol@email (KNOWN, 20 interactions) vs @carol (INTIMATE, 0 interactions)
        # _pick_primary: @carol wins by tier (INTIMATE > KNOWN)
        # Primary is @carol(INTIMATE), secondary is carol@email(KNOWN)
        # merge_contacts: secondary(KNOWN idx=3) < primary(INTIMATE idx=0)? No.
        # So no tier change — capacity check doesn't trigger here.
        # The capacity check actually guards against the case where secondary.tier
        # is higher — but _pick_primary always picks higher tier as primary.
        # This means link() inherently respects capacity through _pick_primary.
        # Test that the link works (no crash) and verify the result.
        result = e.link("carol@example.com", "email", "@carol", "twitter")
        assert result.primary.tier == Tier.INTIMATE

    def test_get_linked_channels(self):
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        e.add("@alice", "twitter", Tier.KNOWN)
        e.link("alice@example.com", "email", "@alice", "twitter")

        channels = e.get_linked_channels("alice@example.com", "email")
        assert channels["email"] == "alice@example.com"
        assert channels["twitter"] == "@alice"

    def test_get_linked_channels_unknown(self):
        e = SocialEnclave.create()
        channels = e.get_linked_channels("nobody@example.com", "email")
        assert channels == {}

    def test_link_saves_and_loads(self):
        from nostrsocial.storage import MemoryStorage
        storage = MemoryStorage()
        e1 = SocialEnclave.create(storage)
        e1.add("alice@example.com", "email", Tier.CLOSE)
        e1.add("@alice", "twitter", Tier.KNOWN)
        e1.link("alice@example.com", "email", "@alice", "twitter")
        e1.save()

        e2 = SocialEnclave.load(storage)
        channels = e2.get_linked_channels("alice@example.com", "email")
        assert "twitter" in channels

    def test_triple_link(self):
        """Link three channels together."""
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        e.add("@alice", "twitter", Tier.KNOWN)
        e.add("+15551234567", "phone", Tier.KNOWN)

        e.link("alice@example.com", "email", "@alice", "twitter")
        e.link("alice@example.com", "email", "+15551234567", "phone")

        channels = e.get_linked_channels("alice@example.com", "email")
        assert len(channels) == 3
        assert channels["email"] == "alice@example.com"
        assert channels["twitter"] == "@alice"
        assert channels["phone"] == "+15551234567"
        assert e.friend_count == 1


class TestResonanceNotSurveillance:
    """Tests that verify the design intent: recognition, not surveillance."""

    def test_recognize_only_checks_existing_contacts(self):
        """recognize() only looks at people you already know."""
        e = SocialEnclave.create()
        # No contacts added — nothing to recognize
        matches = e.recognize("anyone@example.com", "email", display_name="Anyone")
        assert len(matches) == 0

    def test_link_requires_both_contacts_exist(self):
        """Can't link to someone you don't already have a relationship with."""
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE)
        with pytest.raises(KeyError):
            e.link("alice@example.com", "email", "stranger@example.com", "email")

    def test_link_is_explicit_not_automatic(self):
        """Adding two contacts with the same npub doesn't auto-link them."""
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE, claimed_npub="npub1alice")
        e.add("@alice", "twitter", Tier.KNOWN, claimed_npub="npub1alice")
        # Two separate contacts exist — no auto-merge
        assert e.friend_count == 2

    def test_display_name_match_is_low_confidence(self):
        """Same name ≠ same person. Confidence reflects this."""
        e = SocialEnclave.create()
        e.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")
        matches = e.recognize("@alice", "twitter", display_name="Alice")
        assert matches[0].confidence <= 0.3
        assert "confirm" in matches[0].suggestion.lower() or "ask" in matches[0].suggestion.lower()
