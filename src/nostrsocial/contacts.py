"""Contact list management with slot enforcement."""

from __future__ import annotations

import time
from typing import Optional

from .behavior import compute_upgrade_hint
from .proxy import derive_proxy_npub
from .types import (
    CapacityError,
    Contact,
    IdentityState,
    ListType,
    Tier,
    LIST_CAPACITY,
    TIER_CAPACITY,
)


class ContactList:
    """Manages contacts across friends, block, and gray lists with capacity enforcement."""

    def __init__(self, device_secret: bytes) -> None:
        self._contacts: dict[str, Contact] = {}
        self._device_secret = device_secret

    def add(
        self,
        identifier: str,
        channel: str,
        list_type: ListType,
        tier: Optional[Tier] = None,
        display_name: Optional[str] = None,
        notes: Optional[str] = None,
        claimed_npub: Optional[str] = None,
    ) -> Contact:
        """Add a contact. Raises CapacityError if list or tier is full."""
        # Validate tier requirement for friends
        if list_type == ListType.FRIENDS and tier is None:
            raise ValueError("Friends list contacts must have a tier")
        if list_type != ListType.FRIENDS and tier is not None:
            raise ValueError("Only friends list contacts can have a tier")

        # Check list capacity
        current_list_count = sum(
            1 for c in self._contacts.values() if c.list_type == list_type
        )
        if current_list_count >= LIST_CAPACITY[list_type]:
            raise CapacityError(
                f"{list_type.value} list is at capacity ({LIST_CAPACITY[list_type]})"
            )

        # Check tier capacity for friends
        if tier is not None:
            current_tier_count = sum(
                1 for c in self._contacts.values()
                if c.list_type == ListType.FRIENDS and c.tier == tier
            )
            if current_tier_count >= TIER_CAPACITY[tier]:
                raise CapacityError(
                    f"{tier.value} tier is at capacity ({TIER_CAPACITY[tier]})"
                )

        proxy_npub = derive_proxy_npub(identifier, channel, self._device_secret)
        identity_state = IdentityState.CLAIMED if claimed_npub else IdentityState.PROXY
        now = time.time()

        contact = Contact(
            identifier=identifier,
            channel=channel,
            list_type=list_type,
            tier=tier,
            identity_state=identity_state,
            proxy_npub=proxy_npub,
            claimed_npub=claimed_npub,
            display_name=display_name,
            added_at=now,
            last_interaction=now,
            notes=notes,
        )
        contact.upgrade_hint = compute_upgrade_hint(contact)
        self._contacts[proxy_npub] = contact
        return contact

    def remove(self, proxy_npub: str) -> bool:
        """Remove a contact by proxy npub. Returns True if found."""
        return self._contacts.pop(proxy_npub, None) is not None

    def get(self, proxy_npub: str) -> Optional[Contact]:
        """Get a contact by proxy npub."""
        return self._contacts.get(proxy_npub)

    def get_by_identifier(self, identifier: str, channel: str) -> Optional[Contact]:
        """Find a contact by original identifier and channel."""
        proxy_npub = derive_proxy_npub(identifier, channel, self._device_secret)
        return self._contacts.get(proxy_npub)

    def get_by_npub(self, npub: str) -> Optional[Contact]:
        """Find a contact by claimed or proxy npub."""
        for contact in self._contacts.values():
            if contact.proxy_npub == npub or contact.claimed_npub == npub:
                return contact
        return None

    def move(
        self,
        proxy_npub: str,
        new_list: ListType,
        new_tier: Optional[Tier] = None,
    ) -> Contact:
        """Move a contact between lists. Raises CapacityError if target is full."""
        contact = self._contacts.get(proxy_npub)
        if contact is None:
            raise KeyError(f"Contact not found: {proxy_npub}")

        if new_list == ListType.FRIENDS and new_tier is None:
            raise ValueError("Friends list contacts must have a tier")

        # Check target capacity (excluding current contact if same list)
        current_list_count = sum(
            1 for k, c in self._contacts.items()
            if c.list_type == new_list and k != proxy_npub
        )
        if current_list_count >= LIST_CAPACITY[new_list]:
            raise CapacityError(
                f"{new_list.value} list is at capacity ({LIST_CAPACITY[new_list]})"
            )

        if new_tier is not None:
            current_tier_count = sum(
                1 for k, c in self._contacts.items()
                if c.list_type == ListType.FRIENDS and c.tier == new_tier and k != proxy_npub
            )
            if current_tier_count >= TIER_CAPACITY[new_tier]:
                raise CapacityError(
                    f"{new_tier.value} tier is at capacity ({TIER_CAPACITY[new_tier]})"
                )

        contact.list_type = new_list
        contact.tier = new_tier if new_list == ListType.FRIENDS else None
        contact.upgrade_hint = compute_upgrade_hint(contact)
        return contact

    def list_friends(self, tier: Optional[Tier] = None) -> list[Contact]:
        """List friends, optionally filtered by tier."""
        return [
            c for c in self._contacts.values()
            if c.list_type == ListType.FRIENDS and (tier is None or c.tier == tier)
        ]

    def list_blocked(self) -> list[Contact]:
        """List all blocked contacts."""
        return [c for c in self._contacts.values() if c.list_type == ListType.BLOCK]

    def list_gray(self) -> list[Contact]:
        """List all gray-zone contacts."""
        return [c for c in self._contacts.values() if c.list_type == ListType.GRAY]

    def slots_remaining(self, list_type: ListType) -> int:
        """How many slots remain in a list."""
        current = sum(1 for c in self._contacts.values() if c.list_type == list_type)
        return LIST_CAPACITY[list_type] - current

    def tier_slots_remaining(self, tier: Tier) -> int:
        """How many slots remain in a tier."""
        current = sum(
            1 for c in self._contacts.values()
            if c.list_type == ListType.FRIENDS and c.tier == tier
        )
        return TIER_CAPACITY[tier] - current

    def get_unverified(self) -> list[Contact]:
        """Get all contacts that are not yet verified."""
        return [
            c for c in self._contacts.values()
            if c.identity_state != IdentityState.VERIFIED
        ]

    def get_upgradeable(self) -> list[Contact]:
        """Get contacts that would benefit from npub verification."""
        return [
            c for c in self._contacts.values()
            if c.identity_state in (IdentityState.PROXY, IdentityState.CLAIMED)
            and c.list_type == ListType.FRIENDS
        ]

    def decay_gray(self, max_age_seconds: float = 30 * 86400) -> list[Contact]:
        """Remove gray contacts older than max_age. Returns removed contacts."""
        now = time.time()
        to_remove = []
        for npub, contact in self._contacts.items():
            if contact.list_type == ListType.GRAY:
                age = now - contact.last_interaction
                if age > max_age_seconds:
                    to_remove.append(npub)

        removed = []
        for npub in to_remove:
            removed.append(self._contacts.pop(npub))
        return removed

    def to_dict(self) -> list[dict]:
        """Serialize all contacts."""
        return [c.to_dict() for c in self._contacts.values()]

    @classmethod
    def from_dict(cls, data: list[dict], device_secret: bytes) -> ContactList:
        """Deserialize contacts."""
        cl = cls(device_secret)
        for item in data:
            contact = Contact.from_dict(item)
            cl._contacts[contact.proxy_npub] = contact
        return cl
