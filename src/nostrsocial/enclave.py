"""SocialEnclave — main orchestrator for the social graph."""

from __future__ import annotations

import base64
import time
from typing import Optional

from .behavior import NEUTRAL_BEHAVIOR, compute_upgrade_hint, get_behavior
from .contacts import ContactList
from .proxy import generate_device_secret
from .storage import MemoryStorage, StorageBackend
from .types import (
    BehaviorRules,
    CapacityError,
    Contact,
    DriftEvent,
    IdentityState,
    ListType,
    NetworkShape,
    Tier,
    TIER_ORDER,
)
from .evaluate import Action, ConversationSignals, Evaluation, evaluate
from .verify import Challenge, create_challenge, verify_challenge


class SocialEnclave:
    """High-level social graph manager for an AI agent.

    Manages contacts across friends, block, and gray lists with
    capacity enforcement, identity verification, drift detection,
    and behavioral rules.
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
    def create(
        cls,
        storage: Optional[StorageBackend] = None,
        tier_capacity: Optional[dict[Tier, int]] = None,
        list_capacity: Optional[dict[ListType, int]] = None,
        drift_thresholds: Optional[dict[Tier, float]] = None,
    ) -> SocialEnclave:
        """Create a new SocialEnclave with a fresh device secret.

        Capacity and drift thresholds are configurable. Pass None for defaults.
        """
        if storage is None:
            storage = MemoryStorage()
        secret = generate_device_secret()
        contacts = ContactList(secret, tier_capacity, list_capacity, drift_thresholds)
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
        cap_config = data.get("capacity_config")
        contacts = ContactList.from_dict(data.get("contacts", []), secret, cap_config)
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

    def touch(self, identifier: str, channel: str) -> Optional[Contact]:
        """Record an interaction with a contact. Call this on every message."""
        return self._contacts.touch_by_identifier(identifier, channel)

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

    def evaluate(
        self,
        identifier: str,
        channel: str,
        signals: ConversationSignals,
    ) -> Evaluation:
        """Evaluate a conversation moment against relationship context.

        Combines WHO this person is with WHAT is happening to determine
        HOW to respond. Call this when sentiment shifts mid-conversation
        or at conversation end to assess relationship impact.

        Returns an Evaluation with adjusted warmth, token budget,
        approach guidance, and a recommended action (hold/promote/demote/watch/block).
        """
        contact = self._contacts.get_by_identifier(identifier, channel)
        return evaluate(contact, signals)

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

    def get_drifting(self, threshold_pct: float = 0.5) -> list[Contact]:
        """Get friends at risk of demotion due to inactivity.

        threshold_pct=0.5 means contacts past 50% of their drift window.
        """
        return self._contacts.list_drifting(threshold_pct)

    def drift(self) -> list[DriftEvent]:
        """Run drift detection. Demotes inactive friends, returns what changed.

        Call this periodically (daily or on each interaction).
        Drift is gravity — trust cools without effort.
        """
        return self._contacts.drift()

    def decay(self, max_age_seconds: float = 30 * 86400) -> list[Contact]:
        """Remove stale gray-zone contacts."""
        return self._contacts.decay_gray(max_age_seconds)

    def maintain(self) -> dict:
        """Run all maintenance: drift friends, decay gray, return summary.

        This is the single call an agent should make periodically.
        """
        drift_events = self.drift()
        decayed = self.decay()
        drifting = self.get_drifting()
        return {
            "drifted": drift_events,
            "decayed": decayed,
            "at_risk": drifting,
            "summary": self._maintenance_summary(drift_events, decayed, drifting),
        }

    def _maintenance_summary(
        self,
        drifted: list[DriftEvent],
        decayed: list[Contact],
        at_risk: list[Contact],
    ) -> str:
        parts = []
        if drifted:
            parts.append(f"{len(drifted)} contact(s) drifted:")
            for e in drifted:
                parts.append(f"  {e.summary}")
        if decayed:
            names = [c.display_name or c.identifier for c in decayed]
            parts.append(f"{len(decayed)} gray contact(s) expired: {', '.join(names)}")
        if at_risk:
            names = [c.display_name or c.identifier for c in at_risk]
            parts.append(f"{len(at_risk)} friend(s) at risk of drifting: {', '.join(names)}")
        if not parts:
            parts.append("All clear. No drift, no decay.")
        return "\n".join(parts)

    def network_shape(self) -> NetworkShape:
        """Analyze the social network and return its profile."""
        friends = self._contacts.list_friends()
        blocked = self._contacts.list_blocked()
        gray = self._contacts.list_gray()
        total = len(friends) + len(blocked) + len(gray)

        tier_counts = {}
        for tier in Tier:
            tier_counts[tier.value] = sum(1 for f in friends if f.tier == tier)

        tier_capacities = {t.value: v for t, v in self._contacts._tier_capacity.items()}

        verified = sum(
            1 for c in (friends + gray)
            if c.identity_state == IdentityState.VERIFIED
        )

        # Average days since last interaction (friends only)
        now = time.time()
        if friends:
            avg_days = sum(
                (now - f.last_interaction) / 86400 for f in friends
            ) / len(friends)
        else:
            avg_days = 0.0

        profile_type, narrative = self._classify_network(
            total, friends, blocked, gray, tier_counts, tier_capacities, verified, avg_days
        )

        return NetworkShape(
            total_contacts=total,
            friends_count=len(friends),
            block_count=len(blocked),
            gray_count=len(gray),
            tier_counts=tier_counts,
            tier_capacities=tier_capacities,
            verified_count=verified,
            avg_interaction_days=round(avg_days, 1),
            profile_type=profile_type,
            narrative=narrative,
        )

    def _classify_network(
        self,
        total: int,
        friends: list[Contact],
        blocked: list[Contact],
        gray: list[Contact],
        tier_counts: dict[str, int],
        tier_capacities: dict[str, int],
        verified: int,
        avg_days: float,
    ) -> tuple[str, str]:
        if total == 0:
            return "empty", "No contacts yet. Your social graph is a blank page."

        friend_count = len(friends)
        block_count = len(blocked)
        intimate = tier_counts.get("intimate", 0)
        close = tier_counts.get("close", 0)
        inner_circle = intimate + close

        # Check for over-capacity in top tiers
        intimate_cap = tier_capacities.get("intimate", 5)
        close_cap = tier_capacities.get("close", 15)

        if friend_count == 0:
            if block_count > 0:
                return "fortress", (
                    f"{block_count} blocked, 0 friends. "
                    "You've built walls but no bridges."
                )
            return "ghost", "Only gray contacts. No one close."

        intimate_pct = intimate / friend_count if friend_count else 0
        block_pct = block_count / total if total else 0

        # Deep connector: heavy top tiers relative to their capacity
        if intimate >= intimate_cap * 0.8 or (inner_circle > 10 and intimate_pct > 0.15):
            return "deep-connector", (
                f"{intimate} intimate and {close} close contacts. "
                f"That's a deep-connector pattern — unusually high trust density. "
                f"You maintain {friend_count} friends total."
            )

        # Wide networker: mostly known/familiar, thin top
        known = tier_counts.get("known", 0)
        familiar = tier_counts.get("familiar", 0)
        if friend_count > 20 and (known + familiar) / friend_count > 0.8:
            return "wide-networker", (
                f"{friend_count} friends but only {inner_circle} in your inner circle. "
                f"Wide network, shallow depth. Consider who deserves promotion."
            )

        # High filter: aggressive blocker
        if block_pct > 0.3:
            return "high-filter", (
                f"{block_count} blocked out of {total} total contacts. "
                "Strong boundaries. Your agent is protecting your attention aggressively."
            )

        # Fading: high average silence
        if avg_days > 30 and friend_count > 5:
            return "fading", (
                f"Average {avg_days:.0f} days since last interaction across {friend_count} friends. "
                "Your network is going cold. Drift will start pulling people down soon."
            )

        # Balanced
        gray_count = len(gray)
        return "balanced", (
            f"{friend_count} friends ({intimate} intimate, {close} close, "
            f"{familiar} familiar, {known} known), "
            f"{block_count} blocked, {gray_count} gray. "
            f"Average {avg_days:.0f} days between interactions."
        )

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
            "capacity_config": self._contacts.capacity_config(),
            "version": "0.1.0",
        }
        self._storage.save(data)

    # --- Convenience properties ---

    @property
    def friend_count(self) -> int:
        return len(self._contacts.list_friends())

    @property
    def block_count(self) -> int:
        return len(self._contacts.list_blocked())

    @property
    def gray_count(self) -> int:
        return len(self._contacts.list_gray())
