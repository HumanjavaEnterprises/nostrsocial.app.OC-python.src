"""Tests for nostrsocial types."""

from nostrsocial.types import (
    BehaviorRules,
    CapacityError,
    Contact,
    DriftEvent,
    IdentityState,
    ListType,
    NetworkShape,
    Tier,
    TIER_ORDER,
    DEFAULT_DRIFT_THRESHOLDS,
    DEFAULT_LIST_CAPACITY,
    DEFAULT_TIER_CAPACITY,
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

    def test_tier_order(self):
        assert TIER_ORDER == [Tier.INTIMATE, Tier.CLOSE, Tier.FAMILIAR, Tier.KNOWN]


class TestCapacity:
    def test_tier_capacity_sums_to_friends(self):
        assert sum(DEFAULT_TIER_CAPACITY.values()) == DEFAULT_LIST_CAPACITY[ListType.FRIENDS]

    def test_tier_capacity_values(self):
        assert DEFAULT_TIER_CAPACITY[Tier.INTIMATE] == 5
        assert DEFAULT_TIER_CAPACITY[Tier.CLOSE] == 15
        assert DEFAULT_TIER_CAPACITY[Tier.FAMILIAR] == 50
        assert DEFAULT_TIER_CAPACITY[Tier.KNOWN] == 80

    def test_list_capacity_values(self):
        assert DEFAULT_LIST_CAPACITY[ListType.FRIENDS] == 150
        assert DEFAULT_LIST_CAPACITY[ListType.BLOCK] == 50
        assert DEFAULT_LIST_CAPACITY[ListType.GRAY] == 100


class TestDriftThresholds:
    def test_all_tiers_have_thresholds(self):
        for tier in Tier:
            assert tier in DEFAULT_DRIFT_THRESHOLDS

    def test_thresholds_increase_with_distance(self):
        vals = [DEFAULT_DRIFT_THRESHOLDS[t] for t in TIER_ORDER]
        assert vals == sorted(vals)


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
            interaction_count=42,
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
        assert restored.interaction_count == 42
        assert restored.notes == "Met at conference"

    def test_linked_channels_roundtrip(self):
        contact = Contact(
            identifier="alice@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            tier=Tier.CLOSE,
            proxy_npub="npub1test",
            linked_channels={"twitter": "@alice", "phone": "+15551234567"},
        )
        data = contact.to_dict()
        restored = Contact.from_dict(data)
        assert restored.linked_channels == {"twitter": "@alice", "phone": "+15551234567"}

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
        assert contact.interaction_count == 0

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

    def test_days_since_interaction(self):
        import time
        contact = Contact(
            identifier="test@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            last_interaction=time.time() - 86400,  # 1 day ago
        )
        days = contact.days_since_interaction
        assert 0.9 < days < 1.1

    def test_interaction_count_roundtrip(self):
        contact = Contact(
            identifier="test@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            interaction_count=99,
        )
        data = contact.to_dict()
        assert data["interaction_count"] == 99
        restored = Contact.from_dict(data)
        assert restored.interaction_count == 99


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


class TestDriftEvent:
    def test_summary(self):
        contact = Contact(
            identifier="alice@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            display_name="Alice",
        )
        event = DriftEvent(
            contact=contact,
            from_tier=Tier.CLOSE,
            to_tier=Tier.FAMILIAR,
            to_list=ListType.FRIENDS,
            days_silent=45.3,
        )
        assert "Alice" in event.summary
        assert "close" in event.summary
        assert "familiar" in event.summary
        assert "45d" in event.summary

    def test_summary_to_gray(self):
        contact = Contact(
            identifier="bob@example.com",
            channel="email",
            list_type=ListType.GRAY,
            display_name="Bob",
        )
        event = DriftEvent(
            contact=contact,
            from_tier=Tier.KNOWN,
            to_tier=None,
            to_list=ListType.GRAY,
            days_silent=200.0,
        )
        assert "gray" in event.summary


class TestNetworkShape:
    def test_dataclass(self):
        shape = NetworkShape(
            total_contacts=10,
            friends_count=7,
            block_count=2,
            gray_count=1,
            tier_counts={"intimate": 2, "close": 3, "familiar": 1, "known": 1},
            tier_capacities={"intimate": 5, "close": 15, "familiar": 50, "known": 80},
            verified_count=3,
            avg_interaction_days=5.2,
            profile_type="deep-connector",
            narrative="test",
        )
        assert shape.profile_type == "deep-connector"
        assert shape.total_contacts == 10


class TestCapacityError:
    def test_is_exception(self):
        assert issubclass(CapacityError, Exception)

    def test_message(self):
        err = CapacityError("tier full")
        assert str(err) == "tier full"
