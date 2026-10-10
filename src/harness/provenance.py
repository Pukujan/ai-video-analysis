"""The provenance annotation every derived claim carries.

Fields and levels are fixed by managed/epistemic/PROVENANCE.md. This mixin
composes into derived/claim records only; the substrate records it points at
(source artifacts, reference videos, analysis runs) do not carry it.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harness.vocab import EpistemicLevel, ReviewStatus

__all__ = ["ProvenanceAnnotation"]

_Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class ProvenanceAnnotation(BaseModel):
    """The 14 annotation fields required on every derived claim.

    The model is deliberately strict: an interpretation (E2 and above) must
    record its alternatives, and a claim may never supersede itself.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    claim_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    media_start_ms: int = Field(ge=0)
    media_end_ms: int = Field(ge=0)
    source_kind: str = Field(min_length=1)
    verbatim_evidence: str = Field(min_length=1)
    extraction_method: str = Field(min_length=1)
    model_id: str | None = None
    run_id: str | None = None
    confidence: _Confidence | None = None
    epistemic_level: EpistemicLevel
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    supersedes_claim_id: str | None = None
    alternate_hypotheses: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> ProvenanceAnnotation:
        if self.media_end_ms < self.media_start_ms:
            raise ValueError(
                f"media_end_ms {self.media_end_ms} must not precede "
                f"media_start_ms {self.media_start_ms}"
            )
        if self.supersedes_claim_id == self.claim_id:
            raise ValueError("a claim may not supersede itself")
        if self.epistemic_level in (
            EpistemicLevel.E2_INTERPRETATION,
            EpistemicLevel.E3_GENERALIZATION,
            EpistemicLevel.E4_GENERATION_GUIDANCE,
        ):
            if not self.alternate_hypotheses:
                raise ValueError(
                    f"{self.epistemic_level.value} claim needs at least one "
                    "alternate hypothesis"
                )
            if self.model_id is None:
                raise ValueError(
                    f"{self.epistemic_level.value} claim needs a model_id"
                )
        if self.epistemic_level is EpistemicLevel.E0_RAW_SOURCE and self.confidence is not None:
            raise ValueError("a raw-source record carries no confidence score")
        return self
