"""Tests for nostrsocial types."""

from nostrsocial.types import (
    BehaviorRules,
    CapacityError,
    Contact,
    IdentityState,
    ListType,
    Tier,
    LIST_CAPACITY,
    TIER_CAPACITY,
)


class TestEnums:
    def test_tier_values(self):
        assert Tier.INTIMATE.value == "intimate"
        assert Tier.CLOSE.value == "close"
        assert Tier.FAMILIAR.value == "familiar"
        assert Tier.KNOWN.value == "known"

    def test_list_type_values(self):
        assert ListType.FRIENDS.value == "friends"
        assert ListType.BLOCK.value == "block"
        assert ListType.GRAY.value == "gray"

    def test_identity_state_values(self):
        assert IdentityState.PROXY.value == "proxy"
        assert IdentityState.CLAIMED.value == "claimed"
        assert IdentityState.VERIFIED.value == "verified"


class TestCapacity:
    def test_tier_capacity_sums_to_friends(self):
        assert sum(TIER_CAPACITY.values()) == LIST_CAPACITY[ListType.FRIENDS]

    def test_tier_capacity_values(self):
        assert TIER_CAPACITY[Tier.INTIMATE] == 5
        assert TIER_CAPACITY[Tier.CLOSE] == 15
        assert TIER_CAPACITY[Tier.FAMILIAR] == 50
        assert TIER_CAPACITY[Tier.KNOWN] == 80

    def test_list_capacity_values(self):
        assert LIST_CAPACITY[ListType.FRIENDS] == 150
        assert LIST_CAPACITY[ListType.BLOCK] == 50
        assert LIST_CAPACITY[ListType.GRAY] == 100


class TestContact:
    def test_roundtrip(self):
        contact = Contact(
            identifier="alice@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            tier=Tier.CLOSE,
            identity_state=IdentityState.CLAIMED,
            proxy_npub="npub1test",
            claimed_npub="npub1alice",
            display_name="Alice",
            added_at=1000.0,
            last_interaction=2000.0,
            notes="Met at conference",
            upgrade_hint="Use create_challenge() to verify ownership",
        )
        data = contact.to_dict()
        restored = Contact.from_dict(data)

        assert restored.identifier == "alice@example.com"
        assert restored.channel == "email"
        assert restored.list_type == ListType.FRIENDS
        assert restored.tier == Tier.CLOSE
        assert restored.identity_state == IdentityState.CLAIMED
        assert restored.proxy_npub == "npub1test"
        assert restored.claimed_npub == "npub1alice"
        assert restored.display_name == "Alice"
        assert restored.added_at == 1000.0
        assert restored.last_interaction == 2000.0
        assert restored.notes == "Met at conference"

    def test_defaults(self):
        contact = Contact(
            identifier="bob@example.com",
            channel="email",
            list_type=ListType.GRAY,
        )
        assert contact.tier is None
        assert contact.identity_state == IdentityState.PROXY
        assert contact.proxy_npub == ""
        assert contact.claimed_npub is None
        assert contact.display_name is None

    def test_roundtrip_no_tier(self):
        contact = Contact(
            identifier="spammer@bad.com",
            channel="email",
            list_type=ListType.BLOCK,
        )
        data = contact.to_dict()
        restored = Contact.from_dict(data)
        assert restored.list_type == ListType.BLOCK
        assert restored.tier is None


class TestBehaviorRules:
    def test_defaults(self):
        rules = BehaviorRules()
        assert rules.token_budget == 500
        assert rules.warmth == 0.5
        assert rules.can_interrupt is False

    def test_to_dict(self):
        rules = BehaviorRules(token_budget=2000, warmth=0.95)
        data = rules.to_dict()
        assert data["token_budget"] == 2000
        assert data["warmth"] == 0.95


class TestCapacityError:
    def test_is_exception(self):
        assert issubclass(CapacityError, Exception)

    def test_message(self):
        err = CapacityError("tier full")
        assert str(err) == "tier full"
