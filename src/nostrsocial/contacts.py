"""Contact list management with slot enforcement."""

from __future__ import annotations

import time
from typing import Optional

from .behavior import compute_upgrade_hint
from .proxy import derive_proxy_npub
from .types import (
    CapacityError,
    Contact,
    DriftEvent,
    IdentityState,
    ListType,
    Tier,
    TIER_ORDER,
    DEFAULT_DRIFT_THRESHOLDS,
    DEFAULT_LIST_CAPACITY,
    DEFAULT_TIER_CAPACITY,
)


class ContactList:
    """Manages contacts across friends, block, and gray lists with capacity enforcement."""

    def __init__(
        self,
        device_secret: bytes,
        tier_capacity: Optional[dict[Tier, int]] = None,
        list_capacity: Optional[dict[ListType, int]] = None,
        drift_thresholds: Optional[dict[Tier, float]] = None,
    ) -> None:
        self._contacts: dict[str, Contact] = {}
        self._device_secret = device_secret
        self._tier_capacity = tier_capacity or dict(DEFAULT_TIER_CAPACITY)
        self._list_capacity = list_capacity or dict(DEFAULT_LIST_CAPACITY)
        self._drift_thresholds = drift_thresholds or dict(DEFAULT_DRIFT_THRESHOLDS)
        # Recalculate friends capacity from tier sum if tiers were customized
        if tier_capacity is not None and list_capacity is None:
            self._list_capacity[ListType.FRIENDS] = sum(self._tier_capacity.values())

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
        if current_list_count >= self._list_capacity[list_type]:
            raise CapacityError(
                f"{list_type.value} list is at capacity ({self._list_capacity[list_type]})"
            )

        # Check tier capacity for friends
        if tier is not None:
            current_tier_count = sum(
                1 for c in self._contacts.values()
                if c.list_type == ListType.FRIENDS and c.tier == tier
            )
            if current_tier_count >= self._tier_capacity[tier]:
                raise CapacityError(
                    f"{tier.value} tier is at capacity ({self._tier_capacity[tier]})"
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
            interaction_count=0,
            notes=notes,
        )
        contact.upgrade_hint = compute_upgrade_hint(contact)
        self._contacts[proxy_npub] = contact
        return contact

    def touch(self, proxy_npub: str) -> Optional[Contact]:
        """Record an interaction with a contact. Updates timestamp and count."""
        contact = self._contacts.get(proxy_npub)
        if contact is None:
            return None
        contact.last_interaction = time.time()
        contact.interaction_count += 1
        return contact

    def touch_by_identifier(self, identifier: str, channel: str) -> Optional[Contact]:
        """Record an interaction by identifier."""
        proxy_npub = derive_proxy_npub(identifier, channel, self._device_secret)
        return self.touch(proxy_npub)

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
        if current_list_count >= self._list_capacity[new_list]:
            raise CapacityError(
                f"{new_list.value} list is at capacity ({self._list_capacity[new_list]})"
            )

        if new_tier is not None:
            current_tier_count = sum(
                1 for k, c in self._contacts.items()
                if c.list_type == ListType.FRIENDS and c.tier == new_tier and k != proxy_npub
            )
            if current_tier_count >= self._tier_capacity[new_tier]:
                raise CapacityError(
                    f"{new_tier.value} tier is at capacity ({self._tier_capacity[new_tier]})"
                )

        contact.list_type = new_list
        contact.tier = new_tier if new_list == ListType.FRIENDS else None
        contact.upgrade_hint = compute_upgrade_hint(contact)
        return contact

    def drift(self) -> list[DriftEvent]:
        """Demote friends who haven't interacted recently. Returns drift events.

        Drift is gravity — trust cools without effort.
        Intimate → Close → Familiar → Known → Gray.
        Block list never drifts. Gray decays separately.
        """
        now = time.time()
        events: list[DriftEvent] = []

        for contact in list(self._contacts.values()):
            if contact.list_type != ListType.FRIENDS or contact.tier is None:
                continue

            silence = now - contact.last_interaction
            threshold = self._drift_thresholds.get(contact.tier)
            if threshold is None or silence < threshold:
                continue

            from_tier = contact.tier
            tier_idx = TIER_ORDER.index(contact.tier)

            if tier_idx >= len(TIER_ORDER) - 1:
                # Known → Gray (falls off friends list)
                # Check gray capacity first
                gray_count = sum(
                    1 for c in self._contacts.values() if c.list_type == ListType.GRAY
                )
                if gray_count < self._list_capacity[ListType.GRAY]:
                    contact.list_type = ListType.GRAY
                    contact.tier = None
                    events.append(DriftEvent(
                        contact=contact,
                        from_tier=from_tier,
                        to_tier=None,
                        to_list=ListType.GRAY,
                        days_silent=silence / 86400,
                    ))
            else:
                # Demote one tier
                new_tier = TIER_ORDER[tier_idx + 1]
                contact.tier = new_tier
                events.append(DriftEvent(
                    contact=contact,
                    from_tier=from_tier,
                    to_tier=new_tier,
                    to_list=ListType.FRIENDS,
                    days_silent=silence / 86400,
                ))

            contact.upgrade_hint = compute_upgrade_hint(contact)

        return events

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

    def list_drifting(self, threshold_pct: float = 0.5) -> list[Contact]:
        """List friends approaching their drift threshold.

        Returns contacts who have been silent for more than threshold_pct
        of their tier's drift window. These are at risk of demotion.
        """
        now = time.time()
        at_risk = []
        for contact in self._contacts.values():
            if contact.list_type != ListType.FRIENDS or contact.tier is None:
                continue
            threshold = self._drift_thresholds.get(contact.tier, 0)
            if threshold <= 0:
                continue
            silence = now - contact.last_interaction
            if silence > threshold * threshold_pct:
                at_risk.append(contact)
        return sorted(at_risk, key=lambda c: c.last_interaction)

    def slots_remaining(self, list_type: ListType) -> int:
        """How many slots remain in a list."""
        current = sum(1 for c in self._contacts.values() if c.list_type == list_type)
        return self._list_capacity[list_type] - current

    def tier_slots_remaining(self, tier: Tier) -> int:
        """How many slots remain in a tier."""
        current = sum(
            1 for c in self._contacts.values()
            if c.list_type == ListType.FRIENDS and c.tier == tier
        )
        return self._tier_capacity[tier] - current

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

    def all_contacts(self) -> list[Contact]:
        """Return all contacts across all lists."""
        return list(self._contacts.values())

    def to_dict(self) -> list[dict]:
        """Serialize all contacts."""
        return [c.to_dict() for c in self._contacts.values()]

    def capacity_config(self) -> dict:
        """Return current capacity configuration for serialization."""
        return {
            "tier_capacity": {t.value: v for t, v in self._tier_capacity.items()},
            "list_capacity": {lt.value: v for lt, v in self._list_capacity.items()},
            "drift_thresholds": {t.value: v for t, v in self._drift_thresholds.items()},
        }

    @classmethod
    def from_dict(
        cls,
        data: list[dict],
        device_secret: bytes,
        capacity_config: Optional[dict] = None,
    ) -> ContactList:
        """Deserialize contacts."""
        tier_cap = None
        list_cap = None
        drift_thresh = None
        if capacity_config:
            if "tier_capacity" in capacity_config:
                tier_cap = {Tier(k): v for k, v in capacity_config["tier_capacity"].items()}
            if "list_capacity" in capacity_config:
                list_cap = {ListType(k): v for k, v in capacity_config["list_capacity"].items()}
            if "drift_thresholds" in capacity_config:
                drift_thresh = {Tier(k): v for k, v in capacity_config["drift_thresholds"].items()}
        cl = cls(device_secret, tier_cap, list_cap, drift_thresh)
        for item in data:
            contact = Contact.from_dict(item)
            cl._contacts[contact.proxy_npub] = contact
        return cl
