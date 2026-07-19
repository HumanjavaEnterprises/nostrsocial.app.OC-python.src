"""Security tests — repr redaction and input validation for nostrsocial.

Ensures that classes holding secrets redact them in __repr__, error messages
never leak secret values, and all input validation rejects dangerous inputs.
"""

import base64

import pytest

from nostrsocial.contacts import ContactList
from nostrsocial.enclave import SocialEnclave
from nostrsocial.proxy import generate_device_secret
from nostrsocial.types import (
    Contact,
    ListType,
    Tier,
)


# --- Repr redaction: SocialEnclave ---


class TestSocialEnclaveRepr:
    """SocialEnclave.__repr__ must never expose the device secret."""

    def test_repr_hides_device_secret(self):
        enclave = SocialEnclave.create()
        r = repr(enclave)
        secret_b64 = enclave.export_secret()
        secret_bytes = base64.b64decode(secret_b64)
        # The raw secret (bytes or hex or base64) must not appear
        assert secret_b64 not in r
        assert secret_bytes.hex() not in r
        assert str(secret_bytes) not in r

    def test_repr_shows_redacted_marker(self):
        enclave = SocialEnclave.create()
        r = repr(enclave)
        assert "***" in r

    def test_repr_shows_counts(self):
        enclave = SocialEnclave.create()
        enclave.add("johnny5@example.com", "email", Tier.KNOWN, display_name="Johnny5")
        r = repr(enclave)
        assert "friends=1" in r
        assert "blocked=0" in r
        assert "gray=0" in r

    def test_repr_type(self):
        enclave = SocialEnclave.create()
        r = repr(enclave)
        assert r.startswith("SocialEnclave(")


# --- Repr redaction: ContactList ---


class TestContactListRepr:
    """ContactList.__repr__ must never expose the device secret."""

    def test_repr_hides_device_secret(self):
        secret = generate_device_secret()
        cl = ContactList(secret)
        r = repr(cl)
        assert secret.hex() not in r
        assert base64.b64encode(secret).decode() not in r
        assert str(secret) not in r

    def test_repr_shows_redacted_marker(self):
        secret = generate_device_secret()
        cl = ContactList(secret)
        r = repr(cl)
        assert "***" in r

    def test_repr_shows_contact_count(self):
        secret = generate_device_secret()
        cl = ContactList(secret)
        r = repr(cl)
        assert "contacts=0" in r

    def test_repr_type(self):
        secret = generate_device_secret()
        cl = ContactList(secret)
        r = repr(cl)
        assert r.startswith("ContactList(")


# --- Repr redaction: Contact (already has safe repr, verify it) ---


class TestContactRepr:
    """Contact.__repr__ must not expose PII."""

    def test_repr_hides_identifier(self):
        contact = Contact(
            identifier="johnny5@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            tier=Tier.KNOWN,
            proxy_npub="npub1test",
        )
        r = repr(contact)
        assert "johnny5@example.com" not in r
        assert "npub1test" not in r

    def test_repr_hides_notes(self):
        contact = Contact(
            identifier="johnny5@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            tier=Tier.KNOWN,
            notes="super secret note about this person",
        )
        r = repr(contact)
        assert "super secret" not in r

    def test_repr_shows_channel_and_tier(self):
        contact = Contact(
            identifier="johnny5@example.com",
            channel="email",
            list_type=ListType.FRIENDS,
            tier=Tier.INTIMATE,
        )
        r = repr(contact)
        assert "email" in r
        assert "intimate" in r


# --- Error message safety ---


class TestErrorMessageSafety:
    """Ensure error messages never include secret values."""

    def test_capacity_error_no_secret(self):
        """CapacityError messages should not contain device secrets."""
        from nostrsocial.types import CapacityError

        enclave = SocialEnclave.create()
        secret_b64 = enclave.export_secret()

        # Fill the intimate tier (capacity 5)
        for i in range(5):
            enclave.add(f"user{i}@example.com", "email", Tier.INTIMATE)

        with pytest.raises(CapacityError) as exc_info:
            enclave.add("overflow@example.com", "email", Tier.INTIMATE)

        msg = str(exc_info.value)
        assert secret_b64 not in msg
        assert "device_secret" not in msg.lower() or "***" in msg

    def test_restore_bad_secret_no_leak(self):
        """Restoring with garbage base64 should not leak the value in the error."""
        bad_secret = "dGhpcyBpcyBub3QgYSByZWFsIHNlY3JldA=="  # valid b64 of garbage
        # This should work (just creates an enclave with a weird secret)
        enclave = SocialEnclave.restore(bad_secret)
        assert enclave is not None
        # The repr should still redact
        assert bad_secret not in repr(enclave)


# --- Input validation ---


class TestInputValidation:
    """Ensure inputs are validated before processing."""

    def test_friends_require_tier(self):
        enclave = SocialEnclave.create()
        with pytest.raises(ValueError, match="tier"):
            # Direct ContactList.add without tier for friends
            enclave._contacts.add(
                identifier="test@example.com",
                channel="email",
                list_type=ListType.FRIENDS,
                tier=None,
            )

    def test_non_friends_reject_tier(self):
        enclave = SocialEnclave.create()
        with pytest.raises(ValueError, match="tier"):
            enclave._contacts.add(
                identifier="test@example.com",
                channel="email",
                list_type=ListType.BLOCK,
                tier=Tier.KNOWN,
            )

    def test_promote_non_friend_fails(self):
        enclave = SocialEnclave.create()
        enclave.gray("test@example.com", "email")
        with pytest.raises(ValueError, match="friends"):
            enclave.promote("test@example.com", "email", Tier.KNOWN)

    def test_demote_non_friend_fails(self):
        enclave = SocialEnclave.create()
        enclave.gray("test@example.com", "email")
        with pytest.raises(ValueError, match="friends"):
            enclave.demote("test@example.com", "email", Tier.KNOWN)


# --- Export/restore round-trip safety ---


class TestSecretRoundTrip:
    """Ensure secret export/restore works without leaking."""

    def test_export_produces_base64(self):
        enclave = SocialEnclave.create()
        exported = enclave.export_secret()
        # Should be valid base64
        decoded = base64.b64decode(exported)
        assert len(decoded) == 32

    def test_restore_produces_same_proxy_npubs(self):
        enclave1 = SocialEnclave.create()
        secret = enclave1.export_secret()
        enclave1.add("johnny5@example.com", "email", Tier.KNOWN)
        contact1 = enclave1._contacts.get_by_identifier("johnny5@example.com", "email")

        enclave2 = SocialEnclave.restore(secret)
        enclave2.add("johnny5@example.com", "email", Tier.KNOWN)
        contact2 = enclave2._contacts.get_by_identifier("johnny5@example.com", "email")

        assert contact1.proxy_npub == contact2.proxy_npub

    def test_repr_after_restore_still_redacted(self):
        enclave1 = SocialEnclave.create()
        secret = enclave1.export_secret()
        enclave2 = SocialEnclave.restore(secret)
        r = repr(enclave2)
        assert secret not in r
        assert "***" in r
