"""Data types for the nostrsocial social graph manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Tier(Enum):
    """Trust tier within the friends list (Dunbar-inspired)."""

    INTIMATE = "intimate"
    CLOSE = "close"
    FAMILIAR = "familiar"
    KNOWN = "known"


# Ordered list for drift: intimate → close → familiar → known
TIER_ORDER: list[Tier] = [Tier.INTIMATE, Tier.CLOSE, Tier.FAMILIAR, Tier.KNOWN]


class ListType(Enum):
    """Which list a contact belongs to."""

    FRIENDS = "friends"
    BLOCK = "block"
    GRAY = "gray"


class IdentityState(Enum):
    """Identity verification state for a contact."""

    PROXY = "proxy"  # HMAC-derived from email/phone
    CLAIMED = "claimed"  # User provided an npub but unverified
    VERIFIED = "verified"  # Signed challenge confirms ownership


# Default slot limits per tier within the friends list
DEFAULT_TIER_CAPACITY: dict[Tier, int] = {
    Tier.INTIMATE: 5,
    Tier.CLOSE: 15,
    Tier.FAMILIAR: 50,
    Tier.KNOWN: 80,
}

# Default total capacity per list
DEFAULT_LIST_CAPACITY: dict[ListType, int] = {
    ListType.FRIENDS: 150,
    ListType.BLOCK: 50,
    ListType.GRAY: 100,
}

# Backwards compat aliases
TIER_CAPACITY = DEFAULT_TIER_CAPACITY
LIST_CAPACITY = DEFAULT_LIST_CAPACITY

# Default drift thresholds: seconds of silence before demotion
# Pass these in SECONDS (not days) when customizing via SocialEnclave.create()
DEFAULT_DRIFT_THRESHOLDS: dict[Tier, float] = {
    Tier.INTIMATE: 30 * 86400,   # 30 days → demote to close
    Tier.CLOSE: 60 * 86400,      # 60 days → demote to familiar
    Tier.FAMILIAR: 90 * 86400,   # 90 days → demote to known
    Tier.KNOWN: 180 * 86400,     # 180 days → move to gray
}


@dataclass
class Contact:
    """A contact in the social graph."""

    identifier: str
    channel: str  # "email", "phone", "npub", "twitter", etc.
    list_type: ListType
    tier: Optional[Tier] = None  # Only for FRIENDS list
    identity_state: IdentityState = IdentityState.PROXY
    proxy_npub: str = ""
    claimed_npub: Optional[str] = None
    display_name: Optional[str] = None
    added_at: float = 0.0
    last_interaction: float = 0.0
    interaction_count: int = 0
    notes: Optional[str] = None
    upgrade_hint: str = ""
    linked_channels: dict[str, str] = field(default_factory=dict)  # channel → identifier

    def __repr__(self) -> str:
        """Safe repr that doesn't expose PII (identifiers, notes, npubs)."""
        tier_label = self.tier.value if self.tier else "none"
        return (
            f"Contact(channel={self.channel!r}, list={self.list_type.value}, "
            f"tier={tier_label}, state={self.identity_state.value}, "
            f"interactions={self.interaction_count})"
        )

    @property
    def days_since_interaction(self) -> float:
        """Days since last interaction. Returns 0 if never interacted."""
        import time
        if self.last_interaction <= 0:
            return 0.0
        return (time.time() - self.last_interaction) / 86400

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        return {
            "identifier": self.identifier,
            "channel": self.channel,
            "list_type": self.list_type.value,
            "tier": self.tier.value if self.tier else None,
            "identity_state": self.identity_state.value,
            "proxy_npub": self.proxy_npub,
            "claimed_npub": self.claimed_npub,
            "display_name": self.display_name,
            "added_at": self.added_at,
            "last_interaction": self.last_interaction,
            "interaction_count": self.interaction_count,
            "notes": self.notes,
            "upgrade_hint": self.upgrade_hint,
            "linked_channels": self.linked_channels,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Contact:
        """Deserialize from a plain dict."""
        return cls(
            identifier=data["identifier"],
            channel=data["channel"],
            list_type=ListType(data["list_type"]),
            tier=Tier(data["tier"]) if data.get("tier") else None,
            identity_state=IdentityState(data.get("identity_state", "proxy")),
            proxy_npub=data.get("proxy_npub", ""),
            claimed_npub=data.get("claimed_npub"),
            display_name=data.get("display_name"),
            added_at=data.get("added_at", 0.0),
            last_interaction=data.get("last_interaction", 0.0),
            interaction_count=data.get("interaction_count", 0),
            notes=data.get("notes"),
            upgrade_hint=data.get("upgrade_hint", ""),
            linked_channels=data.get("linked_channels", {}),
        )


@dataclass
class BehaviorRules:
    """Behavioral parameters derived from a contact's trust tier."""

    token_budget: int = 500
    memory_depth: int = 3
    can_interrupt: bool = False
    warmth: float = 0.5
    response_priority: int = 5
    share_context: bool = False
    proactive_contact: bool = False

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        return {
            "token_budget": self.token_budget,
            "memory_depth": self.memory_depth,
            "can_interrupt": self.can_interrupt,
            "warmth": self.warmth,
            "response_priority": self.response_priority,
            "share_context": self.share_context,
            "proactive_contact": self.proactive_contact,
        }


@dataclass
class DriftEvent:
    """Record of a contact drifting to a lower tier."""

    contact: Contact
    from_tier: Optional[Tier]
    to_tier: Optional[Tier]
    to_list: ListType
    days_silent: float

    @property
    def summary(self) -> str:
        from_label = self.from_tier.value if self.from_tier else "friends"
        if self.to_list == ListType.GRAY:
            to_label = "gray"
        else:
            to_label = self.to_tier.value if self.to_tier else "unknown"
        name = self.contact.display_name or f"[{self.contact.channel}]"
        return f"{name}: {from_label} → {to_label} ({int(self.days_silent)}d silent)"


@dataclass
class NetworkShape:
    """Profile of an agent's social network."""

    total_contacts: int
    friends_count: int
    block_count: int
    gray_count: int
    tier_counts: dict[str, int]
    tier_capacities: dict[str, int]
    verified_count: int
    avg_interaction_days: float
    profile_type: str
    narrative: str


class CapacityError(Exception):
    """Raised when a list or tier is at capacity."""

    pass
