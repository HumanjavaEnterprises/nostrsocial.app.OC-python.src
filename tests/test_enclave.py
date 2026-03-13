"""Tests for SocialEnclave orchestrator."""

import time

import pytest

from nostrsocial import (
    BehaviorRules,
    CapacityError,
    IdentityState,
    ListType,
    NEUTRAL_BEHAVIOR,
    SocialEnclave,
    Tier,
)
from nostrsocial.storage import MemoryStorage


@pytest.fixture
def enclave():
    return SocialEnclave.create()


class TestCreate:
    def test_create_default_storage(self):
        e = SocialEnclave.create()
        assert e.slots_remaining["friends"] == 150

    def test_create_with_storage(self):
        storage = MemoryStorage()
        e = SocialEnclave.create(storage)
        assert e.slots_remaining["friends"] == 150

    def test_create_custom_capacity(self):
        e = SocialEnclave.create(
            tier_capacity={
                Tier.INTIMATE: 10,
                Tier.CLOSE: 20,
                Tier.FAMILIAR: 50,
                Tier.KNOWN: 80,
            }
        )
        # 10+20+50+80 = 160
        assert e.slots_remaining["friends"] == 160

    def test_create_custom_drift(self):
        e = SocialEnclave.create(
            drift_thresholds={
                Tier.INTIMATE: 7 * 86400,
                Tier.CLOSE: 14 * 86400,
                Tier.FAMILIAR: 21 * 86400,
                Tier.KNOWN: 30 * 86400,
            }
        )
        # Should work, drift thresholds stored internally
        assert e.slots_remaining["friends"] == 150


class TestAdd:
    def test_add_friend(self, enclave):
        contact = enclave.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")
        assert contact.display_name == "Alice"
        assert contact.list_type == ListType.FRIENDS
        assert contact.tier == Tier.CLOSE

    def test_block(self, enclave):
        contact = enclave.block("spam@bad.com", "email")
        assert contact.list_type == ListType.BLOCK

    def test_gray(self, enclave):
        contact = enclave.gray("meh@example.com", "email")
        assert contact.list_type == ListType.GRAY


class TestTouch:
    def test_touch_updates(self, enclave):
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        contact = enclave.touch("alice@example.com", "email")
        assert contact is not None
        assert contact.interaction_count == 1

    def test_touch_nonexistent(self, enclave):
        assert enclave.touch("nobody@example.com", "email") is None

    def test_multiple_touches(self, enclave):
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        enclave.touch("alice@example.com", "email")
        enclave.touch("alice@example.com", "email")
        contact = enclave.touch("alice@example.com", "email")
        assert contact.interaction_count == 3


class TestRemove:
    def test_remove_existing(self, enclave):
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        assert enclave.remove("alice@example.com", "email") is True

    def test_remove_nonexistent(self, enclave):
        assert enclave.remove("nobody@example.com", "email") is False


class TestPromoteDemote:
    def test_promote(self, enclave):
        enclave.add("alice@example.com", "email", Tier.KNOWN)
        contact = enclave.promote("alice@example.com", "email", Tier.CLOSE)
        assert contact.tier == Tier.CLOSE

    def test_demote(self, enclave):
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        contact = enclave.demote("alice@example.com", "email", Tier.KNOWN)
        assert contact.tier == Tier.KNOWN

    def test_promote_nonexistent(self, enclave):
        with pytest.raises(KeyError):
            enclave.promote("nobody@example.com", "email", Tier.CLOSE)


class TestBehavior:
    def test_unknown_returns_neutral(self, enclave):
        rules = enclave.get_behavior("nobody@example.com", "email")
        assert rules == NEUTRAL_BEHAVIOR

    def test_friend_returns_tier_rules(self, enclave):
        enclave.add("alice@example.com", "email", Tier.INTIMATE)
        rules = enclave.get_behavior("alice@example.com", "email")
        assert rules.warmth >= 0.9
        assert rules.can_interrupt is True

    def test_blocked_returns_zero(self, enclave):
        enclave.block("spam@bad.com", "email")
        rules = enclave.get_behavior("spam@bad.com", "email")
        assert rules.token_budget == 0
        assert rules.warmth == 0.0


class TestDrift:
    def test_drift_demotes_inactive(self, enclave):
        enclave.add("alice@example.com", "email", Tier.INTIMATE)
        c = enclave._contacts.get_by_identifier("alice@example.com", "email")
        c.last_interaction = time.time() - 31 * 86400
        events = enclave.drift()
        assert len(events) == 1
        assert events[0].from_tier == Tier.INTIMATE
        assert events[0].to_tier == Tier.CLOSE

    def test_drift_no_change_when_active(self, enclave):
        enclave.add("alice@example.com", "email", Tier.INTIMATE)
        events = enclave.drift()
        assert len(events) == 0

    def test_get_drifting(self, enclave):
        enclave.add("alice@example.com", "email", Tier.INTIMATE)
        c = enclave._contacts.get_by_identifier("alice@example.com", "email")
        c.last_interaction = time.time() - 20 * 86400  # 67% of 30 day threshold
        at_risk = enclave.get_drifting(threshold_pct=0.5)
        assert len(at_risk) == 1

    def test_maintain(self, enclave):
        # Add friend who will drift
        enclave.add("alice@example.com", "email", Tier.INTIMATE)
        c = enclave._contacts.get_by_identifier("alice@example.com", "email")
        c.last_interaction = time.time() - 31 * 86400

        # Add gray who will decay
        enclave.gray("meh@example.com", "email")
        g = enclave._contacts.get_by_identifier("meh@example.com", "email")
        g.last_interaction = time.time() - 60 * 86400

        result = enclave.maintain()
        assert len(result["drifted"]) == 1
        assert len(result["decayed"]) == 1
        assert "summary" in result
        assert "drifted" in result["summary"].lower() or "contact" in result["summary"].lower()


class TestNetworkShape:
    def test_empty_network(self, enclave):
        shape = enclave.network_shape()
        assert shape.profile_type == "empty"
        assert shape.total_contacts == 0

    def test_deep_connector(self):
        e = SocialEnclave.create()
        for i in range(4):
            e.add(f"intimate{i}@example.com", "email", Tier.INTIMATE)
        for i in range(3):
            e.add(f"close{i}@example.com", "email", Tier.CLOSE)
        shape = e.network_shape()
        assert shape.profile_type == "deep-connector"
        assert shape.friends_count == 7
        assert "intimate" in shape.narrative.lower() or "trust" in shape.narrative.lower()

    def test_wide_networker(self):
        e = SocialEnclave.create()
        e.add("close1@example.com", "email", Tier.CLOSE)
        for i in range(10):
            e.add(f"known{i}@example.com", "email", Tier.KNOWN)
        for i in range(15):
            e.add(f"familiar{i}@example.com", "email", Tier.FAMILIAR)
        shape = e.network_shape()
        assert shape.profile_type == "wide-networker"

    def test_high_filter(self):
        e = SocialEnclave.create()
        e.add("friend1@example.com", "email", Tier.KNOWN)
        for i in range(20):
            e.block(f"spam{i}@bad.com", "email")
        shape = e.network_shape()
        assert shape.profile_type == "high-filter"

    def test_balanced(self):
        e = SocialEnclave.create()
        e.add("intimate1@example.com", "email", Tier.INTIMATE)
        e.add("close1@example.com", "email", Tier.CLOSE)
        e.add("familiar1@example.com", "email", Tier.FAMILIAR)
        for i in range(3):
            e.add(f"known{i}@example.com", "email", Tier.KNOWN)
        shape = e.network_shape()
        assert shape.profile_type == "balanced"

    def test_shape_includes_counts(self, enclave):
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        enclave.block("spam@bad.com", "email")
        shape = enclave.network_shape()
        assert shape.friends_count == 1
        assert shape.block_count == 1
        assert shape.tier_counts["close"] == 1

    def test_verified_count(self, enclave):
        c = enclave.add("alice@example.com", "email", Tier.CLOSE)
        c.identity_state = IdentityState.VERIFIED
        shape = enclave.network_shape()
        assert shape.verified_count == 1

    def test_fading_network(self):
        e = SocialEnclave.create()
        for i in range(6):
            c = e.add(f"person{i}@example.com", "email", Tier.KNOWN)
            c.last_interaction = time.time() - 45 * 86400
        shape = e.network_shape()
        assert shape.profile_type == "fading"
        assert shape.avg_interaction_days > 30

    def test_ghost_network(self):
        """Only gray contacts, no friends, no blocks → ghost."""
        e = SocialEnclave.create()
        e.gray("meh1@example.com", "email")
        e.gray("meh2@example.com", "email")
        shape = e.network_shape()
        assert shape.profile_type == "ghost"
        assert shape.friends_count == 0
        assert shape.gray_count == 2
        assert "close" in shape.narrative.lower() or "gray" in shape.narrative.lower()

    def test_fortress_network(self):
        """Only blocked contacts, no friends → fortress."""
        e = SocialEnclave.create()
        for i in range(5):
            e.block(f"spam{i}@bad.com", "email")
        shape = e.network_shape()
        assert shape.profile_type == "fortress"
        assert shape.block_count == 5
        assert shape.friends_count == 0
        assert "walls" in shape.narrative.lower() or "blocked" in shape.narrative.lower()


class TestConvenienceProperties:
    def test_friend_count(self, enclave):
        assert enclave.friend_count == 0
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        assert enclave.friend_count == 1

    def test_block_count(self, enclave):
        assert enclave.block_count == 0
        enclave.block("spam@bad.com", "email")
        assert enclave.block_count == 1

    def test_gray_count(self, enclave):
        assert enclave.gray_count == 0
        enclave.gray("meh@example.com", "email")
        assert enclave.gray_count == 1


class TestSlots:
    def test_slots_remaining(self, enclave):
        slots = enclave.slots_remaining
        assert slots["friends"] == 150
        assert slots["block"] == 50
        assert slots["gray"] == 100

    def test_slots_decrease(self, enclave):
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        assert enclave.slots_remaining["friends"] == 149


class TestVerification:
    def test_get_unverified(self, enclave):
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        unverified = enclave.get_unverified_contacts()
        assert len(unverified) == 1
        assert unverified[0].upgrade_hint != ""

    def test_get_upgradeable(self, enclave):
        enclave.add("alice@example.com", "email", Tier.CLOSE)
        enclave.block("spam@bad.com", "email")
        upgradeable = enclave.get_upgradeable()
        assert len(upgradeable) == 1

    def test_create_challenge(self, enclave):
        challenge = enclave.create_challenge("npub1alice")
        assert challenge.target_npub == "npub1alice"
        assert len(challenge.nonce) == 64

    def test_verify_not_implemented(self, enclave):
        challenge = enclave.create_challenge("npub1alice")
        with pytest.raises(NotImplementedError):
            enclave.verify(challenge, "fake_signature")


class TestSaveLoad:
    def test_roundtrip(self):
        storage = MemoryStorage()
        e1 = SocialEnclave.create(storage)
        e1.add("alice@example.com", "email", Tier.CLOSE, display_name="Alice")
        e1.block("spam@bad.com", "email")
        e1.save()

        e2 = SocialEnclave.load(storage)
        assert e2 is not None
        assert e2.slots_remaining["friends"] == 149
        assert e2.slots_remaining["block"] == 49

        rules = e2.get_behavior("alice@example.com", "email")
        assert rules.warmth > 0.5  # Close tier warmth

    def test_load_empty(self):
        storage = MemoryStorage()
        assert SocialEnclave.load(storage) is None

    def test_roundtrip_custom_capacity(self):
        storage = MemoryStorage()
        e1 = SocialEnclave.create(
            storage,
            tier_capacity={
                Tier.INTIMATE: 10,
                Tier.CLOSE: 20,
                Tier.FAMILIAR: 50,
                Tier.KNOWN: 80,
            },
        )
        e1.add("alice@example.com", "email", Tier.CLOSE)
        e1.save()

        e2 = SocialEnclave.load(storage)
        assert e2 is not None
        # Should preserve custom capacity: 10+20+50+80=160, minus 1
        assert e2.slots_remaining["friends"] == 159

    def test_roundtrip_preserves_interaction_count(self):
        storage = MemoryStorage()
        e1 = SocialEnclave.create(storage)
        e1.add("alice@example.com", "email", Tier.CLOSE)
        e1.touch("alice@example.com", "email")
        e1.touch("alice@example.com", "email")
        e1.save()

        e2 = SocialEnclave.load(storage)
        c = e2._contacts.get_by_identifier("alice@example.com", "email")
        assert c.interaction_count == 2


class TestDecay:
    def test_decay(self, enclave):
        enclave.gray("meh@example.com", "email")
        c = enclave._contacts.get_by_identifier("meh@example.com", "email")
        c.last_interaction = time.time() - 60 * 86400
        removed = enclave.decay()
        assert len(removed) == 1
