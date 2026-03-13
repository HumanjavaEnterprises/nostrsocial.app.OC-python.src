"""Tests for contact list management."""

import time

import pytest

from nostrsocial.contacts import ContactList
from nostrsocial.types import (
    CapacityError,
    IdentityState,
    ListType,
    Tier,
    DEFAULT_TIER_CAPACITY,
)


@pytest.fixture
def secret():
    return b"\x00" * 32


@pytest.fixture
def cl(secret):
    return ContactList(secret)


class TestAdd:
    def test_add_friend(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        assert contact.identifier == "alice@example.com"
        assert contact.list_type == ListType.FRIENDS
        assert contact.tier == Tier.CLOSE
        assert contact.identity_state == IdentityState.PROXY
        assert contact.proxy_npub.startswith("npub1")

    def test_add_with_claimed_npub(self, cl):
        contact = cl.add(
            "alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE,
            claimed_npub="npub1alice",
        )
        assert contact.identity_state == IdentityState.CLAIMED
        assert contact.claimed_npub == "npub1alice"

    def test_add_blocked(self, cl):
        contact = cl.add("spam@bad.com", "email", ListType.BLOCK)
        assert contact.list_type == ListType.BLOCK
        assert contact.tier is None

    def test_add_gray(self, cl):
        contact = cl.add("meh@example.com", "email", ListType.GRAY)
        assert contact.list_type == ListType.GRAY

    def test_friend_requires_tier(self, cl):
        with pytest.raises(ValueError, match="must have a tier"):
            cl.add("alice@example.com", "email", ListType.FRIENDS)

    def test_block_rejects_tier(self, cl):
        with pytest.raises(ValueError, match="Only friends"):
            cl.add("spam@bad.com", "email", ListType.BLOCK, Tier.CLOSE)

    def test_upgrade_hint_populated(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        assert contact.upgrade_hint != ""

    def test_interaction_count_starts_zero(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        assert contact.interaction_count == 0


class TestTouch:
    def test_touch_updates_timestamp(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        old_time = contact.last_interaction
        time.sleep(0.01)
        cl.touch(contact.proxy_npub)
        assert contact.last_interaction > old_time

    def test_touch_increments_count(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        assert contact.interaction_count == 0
        cl.touch(contact.proxy_npub)
        assert contact.interaction_count == 1
        cl.touch(contact.proxy_npub)
        assert contact.interaction_count == 2

    def test_touch_by_identifier(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        result = cl.touch_by_identifier("alice@example.com", "email")
        assert result is not None
        assert result.interaction_count == 1

    def test_touch_nonexistent(self, cl):
        assert cl.touch("npub1nonexistent") is None

    def test_touch_by_identifier_nonexistent(self, cl):
        assert cl.touch_by_identifier("nobody@example.com", "email") is None


class TestCapacityEnforcement:
    def test_tier_capacity(self, cl):
        for i in range(DEFAULT_TIER_CAPACITY[Tier.INTIMATE]):
            cl.add(f"person{i}@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)

        with pytest.raises(CapacityError, match="intimate"):
            cl.add("overflow@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)

    def test_block_capacity(self, cl):
        for i in range(50):
            cl.add(f"spam{i}@bad.com", "email", ListType.BLOCK)

        with pytest.raises(CapacityError, match="block"):
            cl.add("overflow@bad.com", "email", ListType.BLOCK)

    def test_gray_capacity(self, cl):
        for i in range(100):
            cl.add(f"gray{i}@example.com", "email", ListType.GRAY)

        with pytest.raises(CapacityError, match="gray"):
            cl.add("overflow@example.com", "email", ListType.GRAY)

    def test_custom_tier_capacity(self, secret):
        custom_cl = ContactList(secret, tier_capacity={
            Tier.INTIMATE: 10,
            Tier.CLOSE: 20,
            Tier.FAMILIAR: 50,
            Tier.KNOWN: 80,
        })
        # Should allow 10 intimate contacts now
        for i in range(10):
            custom_cl.add(f"person{i}@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        with pytest.raises(CapacityError):
            custom_cl.add("overflow@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)

    def test_custom_tier_recalculates_friends(self, secret):
        custom_cl = ContactList(secret, tier_capacity={
            Tier.INTIMATE: 10,
            Tier.CLOSE: 20,
            Tier.FAMILIAR: 50,
            Tier.KNOWN: 80,
        })
        # Friends capacity should be sum: 10+20+50+80 = 160
        assert custom_cl.slots_remaining(ListType.FRIENDS) == 160

    def test_custom_list_capacity(self, secret):
        custom_cl = ContactList(secret, list_capacity={
            ListType.FRIENDS: 200,
            ListType.BLOCK: 100,
            ListType.GRAY: 50,
        })
        assert custom_cl.slots_remaining(ListType.BLOCK) == 100
        assert custom_cl.slots_remaining(ListType.GRAY) == 50


class TestRemoveAndGet:
    def test_remove(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        assert cl.remove(contact.proxy_npub) is True
        assert cl.get(contact.proxy_npub) is None

    def test_remove_nonexistent(self, cl):
        assert cl.remove("npub1nonexistent") is False

    def test_get_by_identifier(self, cl):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        contact = cl.get_by_identifier("alice@example.com", "email")
        assert contact is not None
        assert contact.identifier == "alice@example.com"

    def test_get_by_npub(self, cl):
        original = cl.add(
            "alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE,
            claimed_npub="npub1alice",
        )
        found = cl.get_by_npub("npub1alice")
        assert found is not None
        assert found.identifier == original.identifier


class TestMove:
    def test_move_to_block(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        moved = cl.move(contact.proxy_npub, ListType.BLOCK)
        assert moved.list_type == ListType.BLOCK
        assert moved.tier is None

    def test_move_to_friends_requires_tier(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.GRAY)
        with pytest.raises(ValueError, match="must have a tier"):
            cl.move(contact.proxy_npub, ListType.FRIENDS)

    def test_move_nonexistent(self, cl):
        with pytest.raises(KeyError):
            cl.move("npub1nonexistent", ListType.BLOCK)

    def test_move_respects_capacity(self, cl):
        for i in range(50):
            cl.add(f"spam{i}@bad.com", "email", ListType.BLOCK)

        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        with pytest.raises(CapacityError, match="block"):
            cl.move(contact.proxy_npub, ListType.BLOCK)


class TestDrift:
    def test_no_drift_when_active(self, cl):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        events = cl.drift()
        assert len(events) == 0

    def test_intimate_drifts_to_close(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        contact.last_interaction = time.time() - 31 * 86400  # 31 days silent
        events = cl.drift()
        assert len(events) == 1
        assert events[0].from_tier == Tier.INTIMATE
        assert events[0].to_tier == Tier.CLOSE
        assert contact.tier == Tier.CLOSE

    def test_close_drifts_to_familiar(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        contact.last_interaction = time.time() - 61 * 86400
        events = cl.drift()
        assert len(events) == 1
        assert events[0].from_tier == Tier.CLOSE
        assert events[0].to_tier == Tier.FAMILIAR

    def test_familiar_drifts_to_known(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.FAMILIAR)
        contact.last_interaction = time.time() - 91 * 86400
        events = cl.drift()
        assert len(events) == 1
        assert events[0].to_tier == Tier.KNOWN

    def test_known_drifts_to_gray(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.KNOWN)
        contact.last_interaction = time.time() - 181 * 86400
        events = cl.drift()
        assert len(events) == 1
        assert events[0].to_tier is None
        assert events[0].to_list == ListType.GRAY
        assert contact.list_type == ListType.GRAY

    def test_drift_only_demotes_one_step(self, cl):
        """Even if silent for a year, drift only moves one tier at a time."""
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        contact.last_interaction = time.time() - 365 * 86400
        events = cl.drift()
        assert len(events) == 1
        assert events[0].to_tier == Tier.CLOSE  # Only one step
        # Second drift call would demote further
        events2 = cl.drift()
        assert len(events2) == 1
        assert events2[0].to_tier == Tier.FAMILIAR

    def test_drift_doesnt_touch_block(self, cl):
        contact = cl.add("spam@bad.com", "email", ListType.BLOCK)
        contact.last_interaction = time.time() - 365 * 86400
        events = cl.drift()
        assert len(events) == 0

    def test_drift_doesnt_touch_gray(self, cl):
        contact = cl.add("meh@example.com", "email", ListType.GRAY)
        contact.last_interaction = time.time() - 365 * 86400
        events = cl.drift()
        assert len(events) == 0

    def test_touch_prevents_drift(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        contact.last_interaction = time.time() - 29 * 86400  # Just under threshold
        events = cl.drift()
        assert len(events) == 0

    def test_custom_drift_thresholds(self, secret):
        fast_cl = ContactList(secret, drift_thresholds={
            Tier.INTIMATE: 7 * 86400,   # 7 days
            Tier.CLOSE: 14 * 86400,
            Tier.FAMILIAR: 21 * 86400,
            Tier.KNOWN: 30 * 86400,
        })
        contact = fast_cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        contact.last_interaction = time.time() - 8 * 86400
        events = fast_cl.drift()
        assert len(events) == 1

    def test_multiple_contacts_drift(self, cl):
        c1 = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        c2 = cl.add("bob@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        c1.last_interaction = time.time() - 31 * 86400
        c2.last_interaction = time.time() - 61 * 86400
        events = cl.drift()
        assert len(events) == 2


class TestListDrifting:
    def test_at_risk_contacts(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        # 50% of 30 days = 15 days
        contact.last_interaction = time.time() - 16 * 86400
        at_risk = cl.list_drifting(threshold_pct=0.5)
        assert len(at_risk) == 1

    def test_not_at_risk(self, cl):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        at_risk = cl.list_drifting(threshold_pct=0.5)
        assert len(at_risk) == 0

    def test_sorted_by_staleness(self, cl):
        c1 = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        c2 = cl.add("bob@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        c1.last_interaction = time.time() - 20 * 86400  # More stale
        c2.last_interaction = time.time() - 16 * 86400  # Less stale
        at_risk = cl.list_drifting(threshold_pct=0.5)
        assert at_risk[0].identifier == "alice@example.com"


class TestListing:
    def test_list_friends(self, cl):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        cl.add("bob@example.com", "email", ListType.FRIENDS, Tier.KNOWN)
        cl.add("spam@bad.com", "email", ListType.BLOCK)

        friends = cl.list_friends()
        assert len(friends) == 2

    def test_list_friends_by_tier(self, cl):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        cl.add("bob@example.com", "email", ListType.FRIENDS, Tier.KNOWN)

        close = cl.list_friends(Tier.CLOSE)
        assert len(close) == 1
        assert close[0].identifier == "alice@example.com"

    def test_list_blocked(self, cl):
        cl.add("spam@bad.com", "email", ListType.BLOCK)
        assert len(cl.list_blocked()) == 1

    def test_list_gray(self, cl):
        cl.add("meh@example.com", "email", ListType.GRAY)
        assert len(cl.list_gray()) == 1


class TestSlots:
    def test_slots_remaining(self, cl):
        assert cl.slots_remaining(ListType.FRIENDS) == 150
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        assert cl.slots_remaining(ListType.FRIENDS) == 149

    def test_tier_slots_remaining(self, cl):
        assert cl.tier_slots_remaining(Tier.INTIMATE) == 5
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.INTIMATE)
        assert cl.tier_slots_remaining(Tier.INTIMATE) == 4


class TestUnverified:
    def test_get_unverified(self, cl):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        cl.add("bob@example.com", "email", ListType.FRIENDS, Tier.KNOWN)
        assert len(cl.get_unverified()) == 2

    def test_get_upgradeable(self, cl):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        cl.add("spam@bad.com", "email", ListType.BLOCK)
        upgradeable = cl.get_upgradeable()
        assert len(upgradeable) == 1
        assert upgradeable[0].identifier == "alice@example.com"


class TestDecay:
    def test_decay_gray(self, cl):
        contact = cl.add("meh@example.com", "email", ListType.GRAY)
        # Force old timestamp
        contact.last_interaction = time.time() - 60 * 86400
        removed = cl.decay_gray(max_age_seconds=30 * 86400)
        assert len(removed) == 1
        assert cl.list_gray() == []

    def test_decay_keeps_recent(self, cl):
        cl.add("recent@example.com", "email", ListType.GRAY)
        removed = cl.decay_gray(max_age_seconds=30 * 86400)
        assert len(removed) == 0
        assert len(cl.list_gray()) == 1

    def test_decay_ignores_friends(self, cl):
        contact = cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        contact.last_interaction = time.time() - 60 * 86400
        removed = cl.decay_gray()
        assert len(removed) == 0


class TestCapacityConfig:
    def test_config_roundtrip(self, secret):
        custom = ContactList(secret, tier_capacity={
            Tier.INTIMATE: 10, Tier.CLOSE: 20, Tier.FAMILIAR: 50, Tier.KNOWN: 80,
        })
        config = custom.capacity_config()
        assert config["tier_capacity"]["intimate"] == 10

        restored = ContactList.from_dict([], secret, config)
        assert restored._tier_capacity[Tier.INTIMATE] == 10

    def test_default_config(self, cl):
        config = cl.capacity_config()
        assert config["tier_capacity"]["intimate"] == 5


class TestSerialization:
    def test_roundtrip(self, cl, secret):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        cl.add("bob@example.com", "email", ListType.BLOCK)
        cl.add("meh@example.com", "email", ListType.GRAY)

        data = cl.to_dict()
        config = cl.capacity_config()
        restored = ContactList.from_dict(data, secret, config)

        assert len(restored.list_friends()) == 1
        assert len(restored.list_blocked()) == 1
        assert len(restored.list_gray()) == 1
