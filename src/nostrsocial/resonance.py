"""Cross-channel recognition and identity linking.

This module is about RESONANCE — recognizing the same person across
different channels, tools, and interfaces. It is not surveillance.

The distinction matters:
- Surveillance collects data about people without their knowledge or consent.
- Resonance recognizes someone you already have a relationship with,
  so you can treat them with the continuity they deserve.

When Alice emails you on Monday and DMs you on Nostr on Tuesday, she shouldn't
have to re-introduce herself. She's still Alice. The relationship carries across.

The npub is the anchor. When someone claims or verifies an npub, it becomes
the sovereign proof that links their identities — because THEY chose to share it,
not because we scraped it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .types import (
    Contact,
    IdentityState,
    ListType,
    Tier,
    TIER_ORDER,
)


@dataclass
class LinkResult:
    """Result of linking two channel identities into one contact."""

    primary: Contact  # The surviving contact
    absorbed_identifier: str  # What was merged in
    absorbed_channel: str  # From which channel
    interaction_count_gained: int  # How many interactions carried over
    rationale: str


@dataclass
class Recognition:
    """A potential cross-channel match — the agent thinks these might be the same person."""

    existing_contact: Contact
    new_identifier: str
    new_channel: str
    confidence: float  # 0.0-1.0
    reason: str  # Why we think it's a match
    suggestion: str  # What to do about it


def find_recognitions(
    contacts: list[Contact],
    identifier: str,
    channel: str,
    claimed_npub: Optional[str] = None,
    display_name: Optional[str] = None,
) -> list[Recognition]:
    """Look for existing contacts that might be the same person.

    This is NOT a search engine. It only checks contacts you already
    have a relationship with. The question is: "Do I already know this person
    through a different channel?"

    Recognition signals (strongest to weakest):
    1. Same claimed/verified npub — near certain match
    2. Same display name across channels — possible match, needs confirmation
    """
    matches: list[Recognition] = []

    for contact in contacts:
        # Skip if it's literally the same identifier+channel
        if contact.identifier == identifier and contact.channel == channel:
            continue

        # Signal 1: npub match — strongest signal
        if claimed_npub and contact.claimed_npub and claimed_npub == contact.claimed_npub:
            matches.append(Recognition(
                existing_contact=contact,
                new_identifier=identifier,
                new_channel=channel,
                confidence=0.95,
                reason="Same npub claimed across channels",
                suggestion=(
                    "High confidence match. Consider linking these identities. "
                    "They share the same npub — this is almost certainly the same person."
                ),
            ))
            continue

        # Signal 2: display name match — weaker, needs confirmation
        if (
            display_name
            and contact.display_name
            and display_name.lower().strip() == contact.display_name.lower().strip()
            and contact.channel != channel  # Different channel
        ):
            matches.append(Recognition(
                existing_contact=contact,
                new_identifier=identifier,
                new_channel=channel,
                confidence=0.3,
                reason="Same display name on different channels",
                suggestion=(
                    "Possible match based on display name alone. "
                    "Ask them to confirm — 'Are you the same {name} I know from {channel}?' "
                    "Don't assume. Display names aren't unique."
                ).format(name=display_name, channel=contact.channel),
            ))

    return sorted(matches, key=lambda r: r.confidence, reverse=True)


def merge_contacts(primary: Contact, secondary: Contact) -> Contact:
    """Merge two contacts into one, preserving the best of both.

    The primary contact survives. The secondary's data is folded in.
    This is a one-way operation — the secondary should be removed after.

    Merge rules:
    - Keep the higher trust tier (the person earned it on some channel)
    - Keep the earlier added_at (they've been in your life since then)
    - Keep the most recent last_interaction
    - Sum interaction counts (total engagement across channels)
    - If either has a claimed npub, keep it
    - If either is verified, keep that state
    - Combine notes
    - Add secondary's channel to linked_channels
    """
    # Tier: keep the higher one (closer to intimate)
    if primary.tier and secondary.tier:
        p_idx = TIER_ORDER.index(primary.tier)
        s_idx = TIER_ORDER.index(secondary.tier)
        if s_idx < p_idx:  # Lower index = higher tier
            primary.tier = secondary.tier
    elif secondary.tier and not primary.tier:
        primary.tier = secondary.tier
        primary.list_type = ListType.FRIENDS

    # Timestamps: earliest start, most recent interaction
    if secondary.added_at < primary.added_at and secondary.added_at > 0:
        primary.added_at = secondary.added_at
    if secondary.last_interaction > primary.last_interaction:
        primary.last_interaction = secondary.last_interaction

    # Interaction counts: sum them
    primary.interaction_count += secondary.interaction_count

    # Identity: keep the strongest
    if secondary.identity_state == IdentityState.VERIFIED:
        primary.identity_state = IdentityState.VERIFIED
    elif (
        secondary.identity_state == IdentityState.CLAIMED
        and primary.identity_state == IdentityState.PROXY
    ):
        primary.identity_state = IdentityState.CLAIMED

    # Npub: keep whichever exists
    if secondary.claimed_npub and not primary.claimed_npub:
        primary.claimed_npub = secondary.claimed_npub

    # Display name: keep primary's unless it's empty
    if not primary.display_name and secondary.display_name:
        primary.display_name = secondary.display_name

    # Notes: combine
    if secondary.notes:
        if primary.notes:
            primary.notes = f"{primary.notes}\n[linked from {secondary.channel}] {secondary.notes}"
        else:
            primary.notes = f"[linked from {secondary.channel}] {secondary.notes}"

    # Track the linked channel
    primary.linked_channels[secondary.channel] = secondary.identifier

    # If secondary also had linked channels, carry them forward
    for ch, ident in secondary.linked_channels.items():
        if ch not in primary.linked_channels:
            primary.linked_channels[ch] = ident

    return primary
