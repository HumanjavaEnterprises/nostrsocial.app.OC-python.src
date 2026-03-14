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
from .guardrails import Guardrails, ScreenResult
from .resonance import LinkResult, Recognition, find_recognitions, merge_contacts
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
        guardrails: Optional[Guardrails] = None,
    ) -> None:
        self._device_secret = device_secret
        self._contacts = contacts
        self._storage = storage
        self._guardrails = guardrails or Guardrails()

    @classmethod
    def create(
        cls,
        storage: Optional[StorageBackend] = None,
        tier_capacity: Optional[dict[Tier, int]] = None,
        list_capacity: Optional[dict[ListType, int]] = None,
        drift_thresholds: Optional[dict[Tier, float]] = None,
    ) -> SocialEnclave:
        """Create a new SocialEnclave with a fresh device secret.

        ⚠️  IMPORTANT: The device secret is the root of all proxy npub derivation.
        If lost, every proxy identity in this enclave becomes unrecoverable.
        Call export_secret() immediately after creation and store the result
        securely (e.g., encrypted backup, hardware vault, NostrKeep).

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

    def export_secret(self) -> str:
        """Export the device secret as a base64 string for secure backup.

        ⚠️  This is the root key for all proxy npub derivation in this enclave.
        Losing it means losing the ability to regenerate proxy identities.
        Store it securely — encrypted backup, hardware vault, or NostrKeep.

        Returns a base64-encoded string that can be passed to restore().
        """
        return base64.b64encode(self._device_secret).decode("ascii")

    @classmethod
    def restore(
        cls,
        secret_b64: str,
        storage: Optional[StorageBackend] = None,
        tier_capacity: Optional[dict[Tier, int]] = None,
        list_capacity: Optional[dict[ListType, int]] = None,
        drift_thresholds: Optional[dict[Tier, float]] = None,
    ) -> SocialEnclave:
        """Restore an enclave from a previously exported device secret.

        Use this to rebuild an enclave after data loss or migration.
        The same secret will derive the same proxy npubs for the same inputs,
        so contacts added with the same identifier+channel will get the same
        proxy identity.
        """
        if storage is None:
            storage = MemoryStorage()
        secret = base64.b64decode(secret_b64)
        contacts = ContactList(secret, tier_capacity, list_capacity, drift_thresholds)
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

    # --- Cross-channel recognition ---
    # This is about resonance, not surveillance. We're not mining the internet.
    # We're recognizing someone we already have a relationship with,
    # so they get the continuity they deserve across channels.

    def recognize(
        self,
        identifier: str,
        channel: str,
        claimed_npub: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> list[Recognition]:
        """Check if a new contact might be someone you already know.

        Call this when someone new appears on a channel. It checks your
        existing contacts for potential matches — same npub, same display name.

        This is recognition, not search. It only looks at people you already
        have a relationship with. The question is: "Have we met before,
        just on a different channel?"
        """
        all_contacts = self._contacts.all_contacts()
        return find_recognitions(all_contacts, identifier, channel, claimed_npub, display_name)

    def link(
        self,
        identifier1: str,
        channel1: str,
        identifier2: str,
        channel2: str,
    ) -> LinkResult:
        """Link two channel identities as the same person.

        "alice@email and @alicedev on Twitter are the same person."

        The contact with the stronger relationship (higher tier, more interactions)
        becomes primary. The other's history folds in — interaction counts combine,
        linked_channels tracks the connection, and the best identity state wins.

        The secondary contact is removed from the graph. One person, one entry,
        multiple channels remembered.

        This requires explicit intent. The agent must decide these are the same
        person — we never auto-link. Trust is earned, not assumed.
        """
        contact1 = self._contacts.get_by_identifier(identifier1, channel1)
        contact2 = self._contacts.get_by_identifier(identifier2, channel2)

        if contact1 is None:
            raise KeyError(f"Contact not found on {channel1}")
        if contact2 is None:
            raise KeyError(f"Contact not found on {channel2}")
        if contact1.proxy_npub == contact2.proxy_npub:
            raise ValueError("Cannot link a contact to itself")
        if contact1.list_type == ListType.BLOCK or contact2.list_type == ListType.BLOCK:
            raise ValueError("Cannot link blocked contacts — unblock first")

        # Decide who's primary: higher tier wins, then more interactions, then earlier added
        primary, secondary = self._pick_primary(contact1, contact2)

        # Check if the merge would promote the primary to a tier that's at capacity
        if secondary.tier and primary.tier:
            s_idx = TIER_ORDER.index(secondary.tier)
            p_idx = TIER_ORDER.index(primary.tier)
            if s_idx < p_idx:  # Secondary has higher tier
                tier_count = sum(
                    1 for c in self._contacts._contacts.values()
                    if c.list_type == ListType.FRIENDS and c.tier == secondary.tier
                    and c.proxy_npub != primary.proxy_npub
                    and c.proxy_npub != secondary.proxy_npub
                )
                if tier_count >= self._contacts._tier_capacity[secondary.tier]:
                    raise CapacityError(
                        f"{secondary.tier.value} tier is at capacity — "
                        f"cannot promote via link"
                    )

        # Remember interaction count before merge
        secondary_count = secondary.interaction_count

        # Merge
        merge_contacts(primary, secondary)

        # Remove the secondary from the contact list
        self._contacts.remove(secondary.proxy_npub)

        return LinkResult(
            primary=primary,
            absorbed_identifier=secondary.identifier,
            absorbed_channel=secondary.channel,
            interaction_count_gained=secondary_count,
            rationale=(
                f"Linked [{secondary.channel}] into [{primary.channel}]. "
                f"{secondary_count} interactions carried over."
            ),
        )

    def get_linked_channels(self, identifier: str, channel: str) -> dict[str, str]:
        """Get all channels linked to a contact.

        Returns a dict mapping channel → identifier for all known channels,
        including the primary.
        """
        contact = self._contacts.get_by_identifier(identifier, channel)
        if contact is None:
            return {}
        result = {contact.channel: contact.identifier}
        result.update(contact.linked_channels)
        return result

    def _pick_primary(self, c1: Contact, c2: Contact) -> tuple[Contact, Contact]:
        """Pick which contact should be primary in a link operation."""
        # Higher tier wins (lower index in TIER_ORDER = higher tier)
        if c1.tier and c2.tier:
            i1 = TIER_ORDER.index(c1.tier)
            i2 = TIER_ORDER.index(c2.tier)
            if i1 < i2:
                return c1, c2
            if i2 < i1:
                return c2, c1

        # Friends over non-friends
        if c1.list_type == ListType.FRIENDS and c2.list_type != ListType.FRIENDS:
            return c1, c2
        if c2.list_type == ListType.FRIENDS and c1.list_type != ListType.FRIENDS:
            return c2, c1

        # More interactions wins
        if c1.interaction_count > c2.interaction_count:
            return c1, c2
        if c2.interaction_count > c1.interaction_count:
            return c2, c1

        # Earlier relationship wins
        if c1.added_at <= c2.added_at:
            return c1, c2
        return c2, c1

    def promote(self, identifier: str, channel: str, new_tier: Tier) -> Contact:
        """Move a contact to a higher trust tier (toward intimate)."""
        contact = self._contacts.get_by_identifier(identifier, channel)
        if contact is None:
            raise KeyError(f"Contact not found on {channel}")
        if contact.list_type != ListType.FRIENDS or contact.tier is None:
            raise ValueError("Can only promote friends with a tier")
        current_idx = TIER_ORDER.index(contact.tier)
        new_idx = TIER_ORDER.index(new_tier)
        if new_idx >= current_idx:
            raise ValueError(
                f"Cannot promote from {contact.tier.value} to {new_tier.value} — "
                f"new tier must be higher (closer to intimate)"
            )
        return self._contacts.move(contact.proxy_npub, ListType.FRIENDS, new_tier)

    def demote(self, identifier: str, channel: str, new_tier: Tier) -> Contact:
        """Move a contact to a lower trust tier (toward known)."""
        contact = self._contacts.get_by_identifier(identifier, channel)
        if contact is None:
            raise KeyError(f"Contact not found on {channel}")
        if contact.list_type != ListType.FRIENDS or contact.tier is None:
            raise ValueError("Can only demote friends with a tier")
        current_idx = TIER_ORDER.index(contact.tier)
        new_idx = TIER_ORDER.index(new_tier)
        if new_idx <= current_idx:
            raise ValueError(
                f"Cannot demote from {contact.tier.value} to {new_tier.value} — "
                f"new tier must be lower (closer to known)"
            )
        return self._contacts.move(contact.proxy_npub, ListType.FRIENDS, new_tier)

    def displacement_candidate(self, tier: Tier) -> Optional[Contact]:
        """Find who would be displaced if a new contact needed this tier slot.

        Returns the contact with the oldest last_interaction in the tier,
        or None if the tier has room. This lets the agent (or operator)
        make an informed decision before forcing a slot.
        """
        return self._contacts.displacement_candidate(tier)

    def displace(self, tier: Tier) -> Optional[Contact]:
        """Demote the weakest contact in a tier to make room for a new one.

        Returns the displaced contact (now in the tier below), or None if the
        tier wasn't full. The displaced contact moves down one tier — intimate→close,
        close→familiar, familiar→known. Known contacts move to gray.

        Uses ContactList.move() internally so capacity checks and upgrade_hint
        updates are applied. Raises CapacityError if the destination is also full.
        """
        candidate = self._contacts.displacement_candidate(tier)
        if candidate is None:
            return None  # Tier has room

        tier_idx = TIER_ORDER.index(tier)
        if tier_idx >= len(TIER_ORDER) - 1:
            # Known → gray
            return self._contacts.move(candidate.proxy_npub, ListType.GRAY)
        else:
            new_tier = TIER_ORDER[tier_idx + 1]
            return self._contacts.move(candidate.proxy_npub, ListType.FRIENDS, new_tier)

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

        # Record signal snapshot for temporal pattern detection
        if contact is not None:
            contact.record_signal({
                "ts": time.time(),
                "sentiment": signals.sentiment,
                "hostility": signals.hostility,
                "vulnerability": signals.vulnerability,
                "engagement": signals.engagement,
                "boundary_violation": signals.boundary_violation,
            })

        return evaluate(contact, signals)

    def screen(self, text: str) -> ScreenResult:
        """Screen conversation text for banned words, topics, or patterns.

        Returns a ScreenResult with severity, category, and recommended action.
        Use this before or alongside evaluate() to catch content that should
        trigger immediate action regardless of relationship context.
        """
        return self._guardrails.screen(text)

    def screen_entity(self, name: str) -> ScreenResult:
        """Screen a display name or alias for known bad-actor patterns.

        Use when processing contact requests or messages from unknown senders.
        """
        return self._guardrails.screen_entity(name)

    @property
    def guardrails(self) -> Guardrails:
        """Access the guardrails engine for direct use or inspection."""
        return self._guardrails

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

    def maintain(self, dry_run: bool = False) -> dict:
        """Run all maintenance: drift friends, decay gray, return summary.

        This is the single call an agent should make periodically.

        If dry_run=True, reports what WOULD happen without making any changes.
        Useful for previewing maintenance impact before committing.
        """
        if dry_run:
            drifting = self.get_drifting(threshold_pct=1.0)  # Past 100% = would drift
            # Estimate gray decay without actually removing
            now = time.time()
            would_decay = [
                c for c in self._contacts.list_gray()
                if (now - c.last_interaction) > 30 * 86400
            ]
            at_risk = self.get_drifting(threshold_pct=0.5)
            return {
                "dry_run": True,
                "would_drift": drifting,
                "would_decay": would_decay,
                "at_risk": at_risk,
                "summary": self._maintenance_summary_dry(drifting, would_decay, at_risk),
            }

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
            names = [c.display_name or f"[{c.channel}]" for c in decayed]
            parts.append(f"{len(decayed)} gray contact(s) expired: {', '.join(names)}")
        if at_risk:
            names = [c.display_name or f"[{c.channel}]" for c in at_risk]
            parts.append(f"{len(at_risk)} friend(s) at risk of drifting: {', '.join(names)}")
        if not parts:
            parts.append("All clear. No drift, no decay.")
        return "\n".join(parts)

    def _maintenance_summary_dry(
        self,
        would_drift: list[Contact],
        would_decay: list[Contact],
        at_risk: list[Contact],
    ) -> str:
        parts = ["[DRY RUN] Preview — no changes made."]
        if would_drift:
            names = [c.display_name or f"[{c.channel}]" for c in would_drift]
            parts.append(f"{len(would_drift)} contact(s) WOULD drift: {', '.join(names)}")
        if would_decay:
            names = [c.display_name or f"[{c.channel}]" for c in would_decay]
            parts.append(f"{len(would_decay)} gray contact(s) WOULD expire: {', '.join(names)}")
        if at_risk:
            names = [c.display_name or f"[{c.channel}]" for c in at_risk]
            parts.append(f"{len(at_risk)} friend(s) approaching drift: {', '.join(names)}")
        if len(parts) == 1:
            parts.append("All clear. Nothing would change.")
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
