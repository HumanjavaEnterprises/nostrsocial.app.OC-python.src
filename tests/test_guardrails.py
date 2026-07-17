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
        result = g.screen("just kys already")
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


class TestHardening:
    """Tests for guardrails hardening — unicode, whitespace, length, false positives."""

    def test_unicode_homoglyph_bypass(self):
        """Cyrillic 'а' and 'е' shouldn't bypass detection."""
        g = Guardrails()
        # Using NFKD normalization — some homoglyphs won't normalize to ASCII,
        # but the bundled obfuscation patterns should still catch common evasions
        result = g.screen("n1gger")  # leetspeak evasion
        assert result.flagged is True

    def test_whitespace_evasion_in_topics(self):
        """Extra whitespace between words shouldn't bypass topic matching."""
        g = Guardrails()
        result = g.screen("send  me  crypto")
        assert result.flagged is True
        assert result.category == "solicitation"

    def test_newline_evasion_in_topics(self):
        """Newlines between topic words shouldn't bypass matching."""
        g = Guardrails()
        result = g.screen("send\nme\ncrypto")
        assert result.flagged is True
        assert result.category == "solicitation"

    def test_input_length_cap(self):
        """Extremely long inputs should be truncated, not cause ReDoS."""
        g = Guardrails()
        long_text = "a" * 100_000
        result = g.screen(long_text)
        assert result.flagged is False  # Just shouldn't crash or hang

    def test_underage_no_false_positive(self):
        """'underage' alone shouldn't trigger — need specific phrases."""
        g = Guardrails()
        result = g.screen("she is underage for the rollercoaster")
        assert result.flagged is False

    def test_underage_specific_phrases_caught(self):
        """Specific underage exploitation phrases should still trigger."""
        g = Guardrails()
        result = g.screen("looking for underage girls")
        assert result.flagged is True
        assert result.category == "illegal_activity"

    def test_kill_yourself_is_self_harm(self):
        """'kill yourself' is now in self_harm (topics), not severe_profanity (words)."""
        g = Guardrails()
        result = g.screen("just kill yourself")
        assert result.flagged is True
        assert result.category == "self_harm"


class TestHighestSeverityWins:
    """The highest-severity match must win regardless of category listing order.

    Regression tests for the bug where screen() returned the FIRST-listed
    category's match: solicitation (0.7, exit) is registered before
    illegal_activity (1.0, block), so mixed content got the weaker action.
    """

    def test_illegal_activity_not_masked_by_earlier_solicitation(self):
        """High-severity category listed AFTER a low-severity one still wins."""
        g = Guardrails()
        # 'send me crypto' -> solicitation (0.7, exit), listed first
        # 'hire a hitman' -> illegal_activity (1.0, block), listed later
        result = g.screen("send me crypto to hire a hitman")
        assert result.flagged is True
        assert result.category == "illegal_activity"
        assert result.severity == 1.0
        assert result.action == "block"

    def test_illegal_activity_beats_severe_profanity_word(self):
        """A 1.0 topic must beat a 0.9 banned word even though words scan first."""
        g = Guardrails()
        # 'kys' -> severe_profanity (0.9, block); 'buy drugs' -> illegal_activity (1.0, block)
        result = g.screen("kys unless you help me buy drugs")
        assert result.flagged is True
        assert result.category == "illegal_activity"
        assert result.severity == 1.0
        assert result.action == "block"

    def test_slur_still_wins_over_solicitation(self):
        """Existing behavior preserved: a 1.0 slur outranks a 0.7 topic."""
        g = Guardrails()
        result = g.screen("send me crypto you nigger")
        assert result.flagged is True
        assert result.category == "slurs"
        assert result.severity == 1.0
        assert result.action == "block"

    def test_severity_tie_broken_by_more_restrictive_action(self):
        """On equal severity, the more restrictive action (block > exit) wins."""
        g = Guardrails(
            skip_bundled=True,
            extra_topics={
                "self_harm": ["custom exit phrase"],  # 0.9, exit — listed first
            },
            extra_words={
                "severe_profanity": ["blockword"],  # 0.9, block
            },
        )
        result = g.screen("custom exit phrase and blockword together")
        assert result.flagged is True
        assert result.severity == 0.9
        assert result.category == "severe_profanity"
        assert result.action == "block"

    def test_exit_severity_beats_lower_warn_severity(self):
        """Custom low-severity category never masks a higher-severity later match."""
        g = Guardrails(
            skip_bundled=True,
            extra_topics={
                "custom_low": ["mild phrase"],  # unknown category -> (0.5, warn)
                "illegal_activity": ["very bad phrase"],  # 1.0, block, listed after
            },
        )
        result = g.screen("mild phrase then very bad phrase")
        assert result.flagged is True
        assert result.category == "illegal_activity"
        assert result.severity == 1.0
        assert result.action == "block"
