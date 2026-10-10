"""Tests for controlled vocabularies."""

from __future__ import annotations

import pytest

from harness.vocab import (
    EditType,
    EpistemicLevel,
    RelationKind,
    VocabError,
    WindowStatus,
    is_extension_token,
    validate_vocab,
)


class TestVocab:
    def test_members_are_stable_strings(self) -> None:
        assert EpistemicLevel.E0_RAW_SOURCE == "E0"
        assert EpistemicLevel.E4_GENERATION_GUIDANCE == "E4"
        assert WindowStatus.SUCCEEDED == "succeeded"

    def test_accepts_member(self) -> None:
        assert validate_vocab("cut", EditType, "edit_type") == "cut"

    def test_accepts_extension_token(self) -> None:
        assert validate_vocab("ext:hard_cut", EditType, "edit_type") == "ext:hard_cut"

    def test_rejects_unknown_bare_string(self) -> None:
        with pytest.raises(VocabError):
            validate_vocab("hardcut", EditType, "edit_type")

    def test_rejects_malformed_extension(self) -> None:
        with pytest.raises(VocabError):
            validate_vocab("ext:Hard-Cut", EditType, "edit_type")

    def test_extension_token_shape(self) -> None:
        assert is_extension_token("ext:ok_1")
        assert not is_extension_token("ext:")
        assert not is_extension_token("cut")

    def test_relation_kinds_cover_the_ontology(self) -> None:
        expected = {
            "temporal",
            "caused_by",
            "sets_up",
            "pays_off",
            "callback_to",
            "undermines",
            "contrasts_with",
            "synchronized_with",
            "edits_for",
        }
        assert {k.value for k in RelationKind} == expected
