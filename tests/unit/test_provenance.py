"""Tests for the provenance annotation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness.provenance import ProvenanceAnnotation
from harness.vocab import EpistemicLevel


def _base(**overrides: object) -> dict:
    data = {
        "claim_id": "c1",
        "source_id": "reference01-transcript",
        "media_start_ms": 0,
        "media_end_ms": 10_000,
        "source_kind": "transcript",
        "verbatim_evidence": "0:00 text",
        "extraction_method": "transcript_stamp_boundaries",
        "epistemic_level": "E1",
    }
    data.update(overrides)
    return data


class TestProvenanceAnnotation:
    def test_minimal_observation(self) -> None:
        claim = ProvenanceAnnotation(**_base())
        assert claim.epistemic_level is EpistemicLevel.E1_OBSERVATION
        assert claim.alternate_hypotheses == []

    def test_rejects_reversed_interval(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceAnnotation(**_base(media_start_ms=5_000, media_end_ms=1_000))

    def test_rejects_self_supersession(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceAnnotation(**_base(supersedes_claim_id="c1"))

    def test_allows_superseding_another_claim(self) -> None:
        claim = ProvenanceAnnotation(**_base(supersedes_claim_id="c0"))
        assert claim.supersedes_claim_id == "c0"

    def test_interpretation_requires_alternatives(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceAnnotation(**_base(epistemic_level="E2", model_id="m1"))

    def test_interpretation_requires_model_id(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceAnnotation(
                **_base(epistemic_level="E2", alternate_hypotheses=["reads as sarcasm"])
            )

    def test_interpretation_with_both_is_accepted(self) -> None:
        claim = ProvenanceAnnotation(
            **_base(
                epistemic_level="E2",
                model_id="m1",
                alternate_hypotheses=["sincere praise", "deadpan"],
            )
        )
        assert claim.epistemic_level is EpistemicLevel.E2_INTERPRETATION

    def test_raw_source_carries_no_confidence(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceAnnotation(**_base(epistemic_level="E0", confidence=0.9))

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceAnnotation(**_base(confidence=1.5))

    def test_is_frozen(self) -> None:
        claim = ProvenanceAnnotation(**_base())
        with pytest.raises(ValidationError):
            claim.claim_id = "c2"  # type: ignore[misc]

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            ProvenanceAnnotation(**_base(extra_field=1))
