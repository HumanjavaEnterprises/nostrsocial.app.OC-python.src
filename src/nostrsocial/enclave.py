"""SocialEnclave — main orchestrator for the social graph."""

from __future__ import annotations

import base64
from typing import Optional

from .behavior import NEUTRAL_BEHAVIOR, compute_upgrade_hint, get_behavior
from .contacts import ContactList
from .proxy import generate_device_secret
from .storage import MemoryStorage, StorageBackend
from .types import (
    BehaviorRules,
    CapacityError,
    Contact,
    IdentityState,
    ListType,
    Tier,
)
from .verify import Challenge, create_challenge, verify_challenge


class SocialEnclave:
    """High-level social graph manager for an AI agent.

    Manages contacts across friends, block, and gray lists with
    capacity enforcement, identity verification, and behavioral rules.
    """

    def __init__(
        self,
        device_secret: bytes,
        contacts: ContactList,
        storage: StorageBackend,
    ) -> None:
        self._device_secret = device_secret
        self._contacts = contacts
        self._storage = storage

    @classmethod
    def create(cls, storage: Optional[StorageBackend] = None) -> SocialEnclave:
        """Create a new SocialEnclave with a fresh device secret."""
        if storage is None:
            storage = MemoryStorage()
        secret = generate_device_secret()
        contacts = ContactList(secret)
        return cls(secret, contacts, storage)

    @classmethod
    def load(cls, storage: StorageBackend) -> Optional[SocialEnclave]:
        """Load an existing SocialEnclave from storage. Returns None if no data."""
        data = storage.load()
        if data is None:
            return None
        secret = data["device_secret"]
        if isinstance(secret, str):
            secret = base64.b64decode(secret)
        contacts = ContactList.from_dict(data.get("contacts", []), secret)
        return cls(secret, contacts, storage)

    def add(
        self,
        identifier: str,
        channel: str,
        tier: Tier,
        display_name: Optional[str] = None,
        notes: Optional[str] = None,
        claimed_npub: Optional[str] = None,
    ) -> Contact:
        """Add a contact to the friends list."""
        return self._contacts.add(
            identifier=identifier,
            channel=channel,
            list_type=ListType.FRIENDS,
            tier=tier,
            display_name=display_name,
            notes=notes,
            claimed_npub=claimed_npub,
        )

    def block(
        self,
        identifier: str,
        channel: str,
        display_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Contact:
        """Add a contact to the block list."""
        return self._contacts.add(
            identifier=identifier,
            channel=channel,
            list_type=ListType.BLOCK,
            display_name=display_name,
            notes=notes,
        )

    def gray(
        self,
        identifier: str,
        channel: str,
        display_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Contact:
        """Add a contact to the gray list."""
        return self._contacts.add(
            identifier=identifier,
            channel=channel,
            list_type=ListType.GRAY,
            display_name=display_name,
            notes=notes,
        )

    def remove(self, identifier: str, channel: str) -> bool:
        """Remove a contact by identifier."""
        contact = self._contacts.get_by_identifier(identifier, channel)
        if contact is None:
            return False
        return self._contacts.remove(contact.proxy_npub)

    def promote(self, identifier: str, channel: str, new_tier: Tier) -> Contact:
        """Move a contact to a higher trust tier in the friends list."""
        contact = self._contacts.get_by_identifier(identifier, channel)
        if contact is None:
            raise KeyError(f"Contact not found: {identifier}")
        return self._contacts.move(contact.proxy_npub, ListType.FRIENDS, new_tier)

    def demote(self, identifier: str, channel: str, new_tier: Tier) -> Contact:
        """Move a contact to a lower trust tier in the friends list."""
        contact = self._contacts.get_by_identifier(identifier, channel)
        if contact is None:
            raise KeyError(f"Contact not found: {identifier}")
        return self._contacts.move(contact.proxy_npub, ListType.FRIENDS, new_tier)

    def get_behavior(self, identifier: str, channel: str) -> BehaviorRules:
        """Get behavioral rules for a contact. Returns NEUTRAL for unknowns."""
        contact = self._contacts.get_by_identifier(identifier, channel)
        return get_behavior(contact)

    @property
    def slots_remaining(self) -> dict[str, int]:
        """Remaining slots per list."""
        return {
            lt.value: self._contacts.slots_remaining(lt) for lt in ListType
        }

    def get_unverified_contacts(self) -> list[Contact]:
        """Get unverified contacts with upgrade hints populated."""
        contacts = self._contacts.get_unverified()
        for c in contacts:
            c.upgrade_hint = compute_upgrade_hint(c)
        return contacts

    def get_upgradeable(self) -> list[Contact]:
        """Get friends that would benefit from npub verification."""
        contacts = self._contacts.get_upgradeable()
        for c in contacts:
            c.upgrade_hint = compute_upgrade_hint(c)
        return contacts

    def create_challenge(self, claimed_npub: str, ttl_seconds: float = 300) -> Challenge:
        """Create a verification challenge for a claimed npub."""
        return create_challenge(claimed_npub, ttl_seconds)

    def verify(self, challenge: Challenge, signature: str) -> bool:
        """Verify a challenge response. Raises NotImplementedError in 0.1.0."""
        return verify_challenge(challenge, signature)

    def save(self) -> None:
        """Persist the social graph to storage."""
        data = {
            "device_secret": self._device_secret,
            "contacts": self._contacts.to_dict(),
            "version": "0.1.0",
        }
        self._storage.save(data)

    def decay(self, max_age_seconds: float = 30 * 86400) -> list[Contact]:
        """Remove stale gray-zone contacts."""
        return self._contacts.decay_gray(max_age_seconds)
