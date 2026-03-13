"""Tests for contact list management."""

import time

import pytest

from nostrsocial.contacts import ContactList
from nostrsocial.types import (
    CapacityError,
    IdentityState,
    ListType,
    Tier,
    TIER_CAPACITY,
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


class TestCapacityEnforcement:
    def test_tier_capacity(self, cl):
        for i in range(TIER_CAPACITY[Tier.INTIMATE]):
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


class TestSerialization:
    def test_roundtrip(self, cl, secret):
        cl.add("alice@example.com", "email", ListType.FRIENDS, Tier.CLOSE)
        cl.add("bob@example.com", "email", ListType.BLOCK)
        cl.add("meh@example.com", "email", ListType.GRAY)

        data = cl.to_dict()
        restored = ContactList.from_dict(data, secret)

        assert len(restored.list_friends()) == 1
        assert len(restored.list_blocked()) == 1
        assert len(restored.list_gray()) == 1
