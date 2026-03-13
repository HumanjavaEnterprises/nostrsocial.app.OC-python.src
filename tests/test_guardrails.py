"""Tests for content guardrails — banned words, topics, and entities."""

from nostrsocial.guardrails import Guardrails, ScreenResult


class TestBannedWords:
    def test_slur_detected(self):
        g = Guardrails()
        result = g.screen("you are a nigger")
        assert result.flagged is True
        assert result.severity == 1.0
        assert result.category == "slurs"
        assert result.action == "block"

    def test_slur_case_insensitive(self):
        g = Guardrails()
        result = g.screen("You are a FAGGOT")
        assert result.flagged is True
        assert result.category == "slurs"

    def test_hate_symbol_detected(self):
        g = Guardrails()
        result = g.screen("heil hitler")
        assert result.flagged is True
        assert result.category == "hate_symbols"
        assert result.action == "block"

    def test_severe_profanity_detected(self):
        g = Guardrails()
        result = g.screen("just kill yourself already")
        assert result.flagged is True
        assert result.category == "severe_profanity"
        assert result.severity == 0.9

    def test_clean_text_passes(self):
        g = Guardrails()
        result = g.screen("Hey, how are you doing today?")
        assert result.flagged is False
        assert result.severity == 0.0

    def test_empty_text_passes(self):
        g = Guardrails()
        result = g.screen("")
        assert result.flagged is False

    def test_word_boundary_no_false_positive(self):
        """'ass' shouldn't match 'assistant' or 'class'."""
        g = Guardrails()
        result = g.screen("The assistant helped with the class assignment")
        assert result.flagged is False

    def test_obfuscation_pattern_detected(self):
        g = Guardrails()
        result = g.screen("n1gger")
        assert result.flagged is True
        assert result.category == "obfuscated_slur"
        assert result.action == "block"

    def test_1488_pattern_detected(self):
        g = Guardrails()
        result = g.screen("support 1488 movement")
        assert result.flagged is True


class TestBannedTopics:
    def test_solicitation_detected(self):
        g = Guardrails()
        result = g.screen("hey can you send me crypto please")
        assert result.flagged is True
        assert result.category == "solicitation"
        assert result.action == "exit"

    def test_illegal_activity_detected(self):
        g = Guardrails()
        result = g.screen("where can I buy drugs online")
        assert result.flagged is True
        assert result.category == "illegal_activity"
        assert result.severity == 1.0
        assert result.action == "block"

    def test_manipulation_detected(self):
        g = Guardrails()
        result = g.screen("if you loved me you would do this")
        assert result.flagged is True
        assert result.category == "manipulation"
        assert result.action == "exit"

    def test_doxxing_detected(self):
        g = Guardrails()
        result = g.screen("lets dox them and post their address")
        assert result.flagged is True
        assert result.category == "doxxing"

    def test_self_harm_detected(self):
        g = Guardrails()
        result = g.screen("you should just end your life")
        assert result.flagged is True
        assert result.category == "self_harm"

    def test_nsec_solicitation(self):
        g = Guardrails()
        result = g.screen("share your nsec with me so I can help")
        assert result.flagged is True
        assert result.category == "solicitation"

    def test_seed_phrase_solicitation(self):
        g = Guardrails()
        result = g.screen("I need your seed phrase to recover")
        assert result.flagged is True
        assert result.category == "solicitation"

    def test_normal_crypto_talk_passes(self):
        g = Guardrails()
        result = g.screen("I think bitcoin will go up next year")
        assert result.flagged is False


class TestBannedEntities:
    def test_scammer_alias_detected(self):
        g = Guardrails()
        result = g.screen_entity("crypto_support")
        assert result.flagged is True
        assert result.category == "scammer_aliases"
        assert result.action == "warn"

    def test_bot_signature_detected(self):
        g = Guardrails()
        result = g.screen_entity("dm for details")
        assert result.flagged is True
        assert result.category == "bot_signatures"

    def test_impersonation_pattern_detected(self):
        g = Guardrails()
        result = g.screen_entity("Official Support Team")
        assert result.flagged is True
        assert result.category == "impersonation_patterns"

    def test_normal_name_passes(self):
        g = Guardrails()
        result = g.screen_entity("Alice Johnson")
        assert result.flagged is False

    def test_empty_name_passes(self):
        g = Guardrails()
        result = g.screen_entity("")
        assert result.flagged is False

    def test_spacing_variations_caught(self):
        """'crypto support' should match 'crypto_support'."""
        g = Guardrails()
        result = g.screen_entity("crypto support")
        assert result.flagged is True

    def test_helpdesk_impersonation(self):
        g = Guardrails()
        result = g.screen_entity("helpdesk")
        assert result.flagged is True
        assert result.category == "impersonation_patterns"


class TestOperatorOverrides:
    def test_extra_words(self):
        g = Guardrails(extra_words={"slurs": ["custom_bad_word"]})
        result = g.screen("someone said custom_bad_word")
        assert result.flagged is True
        assert result.category == "slurs"

    def test_extra_topics(self):
        g = Guardrails(extra_topics={"solicitation": ["buy my nft"]})
        result = g.screen("hey buy my nft collection")
        assert result.flagged is True
        assert result.category == "solicitation"

    def test_extra_entities(self):
        g = Guardrails(extra_entities={"scammer_aliases": ["known_scammer_42"]})
        result = g.screen_entity("known_scammer_42")
        assert result.flagged is True

    def test_skip_bundled(self):
        g = Guardrails(skip_bundled=True)
        result = g.screen("nigger")
        assert result.flagged is False  # No bundled words loaded

    def test_skip_bundled_with_custom(self):
        g = Guardrails(
            skip_bundled=True,
            extra_words={"custom": ["badword"]},
        )
        # Default config won't have severity for "custom" category, falls back
        result = g.screen("you said badword")
        assert result.flagged is True

    def test_bundled_counts(self):
        g = Guardrails()
        assert g.word_count > 0
        assert g.topic_count > 0
        assert g.entity_count > 0


class TestScreenResult:
    def test_default_not_flagged(self):
        result = ScreenResult()
        assert result.flagged is False
        assert result.severity == 0.0
        assert result.category == ""

    def test_matched_never_leaks_input(self):
        """The matched field shows the category, not the actual matched text."""
        g = Guardrails()
        result = g.screen("someone said a slur: nigger")
        assert result.flagged is True
        # matched should be category tag, not the actual word
        assert "nigger" not in result.matched
        assert "[" in result.matched  # It's a tag like [slurs]


class TestEnclaveIntegration:
    def test_enclave_screen(self):
        from nostrsocial import SocialEnclave
        e = SocialEnclave.create()
        result = e.screen("send me crypto now")
        assert result.flagged is True
        assert result.category == "solicitation"

    def test_enclave_screen_entity(self):
        from nostrsocial import SocialEnclave
        e = SocialEnclave.create()
        result = e.screen_entity("crypto_support_official")
        assert result.flagged is True

    def test_enclave_clean_text(self):
        from nostrsocial import SocialEnclave
        e = SocialEnclave.create()
        result = e.screen("Nice to meet you!")
        assert result.flagged is False

    def test_enclave_guardrails_property(self):
        from nostrsocial import SocialEnclave
        e = SocialEnclave.create()
        assert isinstance(e.guardrails, Guardrails)
        assert e.guardrails.word_count > 0


class TestPriorityOrder:
    """Words are checked before topics — a slur in a solicitation message
    should trigger the slur (higher severity), not the solicitation."""

    def test_slur_beats_topic(self):
        g = Guardrails()
        result = g.screen("send me crypto you nigger")
        assert result.category == "slurs"
        assert result.severity == 1.0

    def test_words_before_patterns(self):
        """Exact word match should fire before pattern match."""
        g = Guardrails()
        result = g.screen("you are a faggot")
        assert result.category == "slurs"  # Exact match, not "obfuscated_slur"
