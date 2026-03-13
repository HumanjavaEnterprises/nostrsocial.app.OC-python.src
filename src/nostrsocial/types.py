"""Data types for the nostrsocial social graph manager."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Tier(Enum):
    """Trust tier within the friends list (Dunbar-inspired)."""

    INTIMATE = "intimate"  # 5 slots
    CLOSE = "close"  # 15 slots
    FAMILIAR = "familiar"  # 50 slots
    KNOWN = "known"  # 80 slots


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


# Slot limits per tier within the friends list
TIER_CAPACITY: dict[Tier, int] = {
    Tier.INTIMATE: 5,
    Tier.CLOSE: 15,
    Tier.FAMILIAR: 50,
    Tier.KNOWN: 80,
}

# Total capacity per list
LIST_CAPACITY: dict[ListType, int] = {
    ListType.FRIENDS: 150,
    ListType.BLOCK: 50,
    ListType.GRAY: 100,
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
    notes: Optional[str] = None
    upgrade_hint: str = ""

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
            "notes": self.notes,
            "upgrade_hint": self.upgrade_hint,
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
            notes=data.get("notes"),
            upgrade_hint=data.get("upgrade_hint", ""),
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


class CapacityError(Exception):
    """Raised when a list or tier is at capacity."""

    pass
