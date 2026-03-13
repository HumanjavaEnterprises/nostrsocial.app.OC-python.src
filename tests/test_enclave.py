"""Tests for SocialEnclave orchestrator."""

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


class TestDecay:
    def test_decay(self, enclave):
        import time
        contact = enclave.gray("meh@example.com", "email")
        # Access internal to force old timestamp
        c = enclave._contacts.get_by_identifier("meh@example.com", "email")
        c.last_interaction = time.time() - 60 * 86400
        removed = enclave.decay()
        assert len(removed) == 1
