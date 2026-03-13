"""Tests for proxy npub derivation."""

from nostrsocial.proxy import derive_proxy_npub, generate_device_secret, normalize_identifier


class TestNormalize:
    def test_email_lowercase(self):
        assert normalize_identifier("Alice@Example.COM", "email") == "alice@example.com"

    def test_email_strip_plus(self):
        assert normalize_identifier("alice+tag@example.com", "email") == "alice@example.com"

    def test_email_strip_whitespace(self):
        assert normalize_identifier("  alice@example.com  ", "email") == "alice@example.com"

    def test_phone_e164(self):
        assert normalize_identifier("+1 (555) 123-4567", "phone") == "+15551234567"

    def test_phone_no_plus(self):
        assert normalize_identifier("15551234567", "phone") == "+15551234567"

    def test_other_lowercase(self):
        assert normalize_identifier("  @AliceDev  ", "twitter") == "@alicedev"


class TestDeviceSecret:
    def test_length(self):
        secret = generate_device_secret()
        assert len(secret) == 32
        assert isinstance(secret, bytes)

    def test_unique(self):
        s1 = generate_device_secret()
        s2 = generate_device_secret()
        assert s1 != s2


class TestDerive:
    def test_deterministic(self):
        secret = b"\x00" * 32
        npub1 = derive_proxy_npub("alice@example.com", "email", secret)
        npub2 = derive_proxy_npub("alice@example.com", "email", secret)
        assert npub1 == npub2

    def test_different_inputs_diverge(self):
        secret = b"\x00" * 32
        npub1 = derive_proxy_npub("alice@example.com", "email", secret)
        npub2 = derive_proxy_npub("bob@example.com", "email", secret)
        assert npub1 != npub2

    def test_different_channels_diverge(self):
        secret = b"\x00" * 32
        npub1 = derive_proxy_npub("alice", "email", secret)
        npub2 = derive_proxy_npub("alice", "twitter", secret)
        assert npub1 != npub2

    def test_different_secrets_diverge(self):
        s1 = b"\x00" * 32
        s2 = b"\x01" * 32
        npub1 = derive_proxy_npub("alice@example.com", "email", s1)
        npub2 = derive_proxy_npub("alice@example.com", "email", s2)
        assert npub1 != npub2

    def test_valid_npub_format(self):
        secret = b"\x00" * 32
        npub = derive_proxy_npub("alice@example.com", "email", secret)
        assert npub.startswith("npub1")
        assert len(npub) == 63  # standard npub length

    def test_normalization_applied(self):
        secret = b"\x00" * 32
        npub1 = derive_proxy_npub("Alice@Example.com", "email", secret)
        npub2 = derive_proxy_npub("alice@example.com", "email", secret)
        assert npub1 == npub2
