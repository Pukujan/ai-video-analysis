"""The canonical record types (managed/design/DATA_MODEL.md).

Twenty-four record types in three families:

* substrate records describe the media and the analysis that produced claims
  (source artifacts, reference videos, runs, coverage windows, utterances,
  word alignments, evidence spans, relations);
* derived records are claims about the media and therefore carry the full
  provenance annotation (observations, events, beats, states, edit events,
  audio and music, entities, style patterns);
* human-feedback records hold review corrections, generation trials and
  preference ratings, kept separate so they never mutate model evidence.

Two interval conventions coexist on purpose. Derived records use the
provenance ``media_start_ms``/``media_end_ms`` — the media timebase the claim
is about. Substrate and editorial records use ``start_ms``/``end_ms`` for their
own timeline, which for an edit event is the output timeline, distinct from the
media range it was cut from.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from harness.provenance import ProvenanceAnnotation
from harness.timebase import MsInterval, TimebaseError
from harness.vocab import (
    ArtifactKind,
    AudioEventKind,
    ComedyMechanism,
    ContinuityClass,
    EditType,
    EntityKind,
    EpistemicLevel,
    Modality,
    MusicStatus,
    NarrativeRole,
    RelationKind,
    ResponseDecision,
    ReviewStatus,
    SpanKind,
    WindowStatus,
    validate_vocab,
)

__all__ = [
    "AnalysisRun",
    "AudioEvent",
    "AudioMixEvent",
    "CharacterState",
    "ComedyBeat",
    "CoverageWindow",
    "DerivedRecord",
    "EditEvent",
    "EventRelation",
    "EvidenceSpan",
    "GameplayEvent",
    "GenerationTrial",
    "HumanPreference",
    "MusicCue",
    "NarrativeEntity",
    "Observation",
    "RECORD_TYPES",
    "RecordError",
    "ReferenceVideo",
    "ResponseDecisionRecord",
    "Review",
    "ShotContinuity",
    "SourceArtifact",
    "StylePattern",
    "TimedRecord",
    "Utterance",
    "VocalDelivery",
    "WordAlignment",
    "parse_record",
]

_Unit = Annotated[float, Field(ge=0.0, le=1.0)]
_Scores = dict[str, _Unit]
_EditTypeLabel = Annotated[
    str, AfterValidator(lambda v: validate_vocab(v, EditType, "edit_type"))
]
_MechanismLabel = Annotated[
    str, AfterValidator(lambda v: validate_vocab(v, ComedyMechanism, "mechanism_labels"))
]


class RecordError(ValueError):
    """Raised when a record type is unknown or its payload fails validation."""


class _StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TimedRecord(_StrictRecord):
    """A record with a primary ``[start_ms, end_ms)`` interval of its own."""

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    is_point: bool = False

    @model_validator(mode="after")
    def _validate_interval(self) -> TimedRecord:
        try:
            MsInterval(self.start_ms, self.end_ms, self.is_point)
        except TimebaseError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @property
    def interval(self) -> MsInterval:
        return MsInterval(self.start_ms, self.end_ms, self.is_point)


class DerivedRecord(ProvenanceAnnotation):
    """A claim about the media; its interval is the provenance media range."""

    is_point: bool = False

    @model_validator(mode="after")
    def _validate_point(self) -> DerivedRecord:
        try:
            MsInterval(self.media_start_ms, self.media_end_ms, self.is_point)
        except TimebaseError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @property
    def interval(self) -> MsInterval:
        return MsInterval(self.media_start_ms, self.media_end_ms, self.is_point)


# --------------------------------------------------------------------------
# Substrate records
# --------------------------------------------------------------------------


class SourceArtifact(_StrictRecord):
    """An immutable supplied file or export (DATA_MODEL.md record 1)."""

    artifact_id: str = Field(min_length=1)
    kind: ArtifactKind
    path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    byte_length: int | None = Field(default=None, ge=0)
    provenance_note: str = Field(min_length=1)
    ingest_date: date | None = None
    rights_note: str | None = None
    registered: bool = True


class ReferenceVideo(_StrictRecord):
    """A media reference and its timebases (DATA_MODEL.md record 2)."""

    video_id: str = Field(min_length=1)
    source_artifact_id: str = Field(min_length=1)
    game: str | None = None
    title: str | None = None
    duration_ms: int = Field(ge=0)
    frame_rate: float | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    video_timebase: str = Field(min_length=1)
    audio_timebase: str | None = None


class AnalysisRun(_StrictRecord):
    """One provider invocation's reproducibility envelope (record 3)."""

    run_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    endpoint: str | None = None
    prompt_hash: str = Field(min_length=1)
    transcript_version: str | None = None
    code_version: str = Field(min_length=1)
    frame_sample_policy: str = Field(min_length=1)
    latency_ms: int | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0.0)
    temperature: float | None = Field(default=None, ge=0.0)


class CoverageWindow(TimedRecord):
    """A planned local window and its processing state (record 4).

    The coverage postcondition is that every window reaches a terminal status,
    so a failed window must say why; ``planned`` is the only non-terminal state.
    """

    window_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    modalities: list[Modality] = Field(min_length=1)
    sampling_policy: str = Field(min_length=1)
    run_id: str | None = None
    status: WindowStatus = WindowStatus.PLANNED
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _validate_failure(self) -> CoverageWindow:
        if self.status is WindowStatus.FAILED and not self.failure_reason:
            raise ValueError("a failed window must record a failure_reason")
        if self.status is not WindowStatus.FAILED and self.failure_reason:
            raise ValueError("failure_reason is only meaningful for a failed window")
        return self


class Utterance(TimedRecord):
    """A spoken turn as supplied (DATA_MODEL.md record 5).

    ``raw_text`` holds the original transcript spelling; ``corrected_text`` is a
    separate field so a correction never overwrites what was transcribed.
    """

    utterance_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    speaker: str = Field(min_length=1)
    raw_text: str = Field(min_length=1)
    alignment_method: str = Field(min_length=1)
    disfluency_tags: list[str] = Field(default_factory=list)
    corrected_text: str | None = None


class WordAlignment(TimedRecord):
    """A token aligned to the audio (DATA_MODEL.md record 6)."""

    alignment_id: str = Field(min_length=1)
    utterance_id: str = Field(min_length=1)
    token: str = Field(min_length=1)
    diarization_confidence: _Unit | None = None
    asr_confidence: _Unit | None = None


class EvidenceSpan(TimedRecord):
    """A precise pointer from a claim to its native source (record 8)."""

    span_id: str = Field(min_length=1)
    claim_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    kind: SpanKind
    quote: str | None = None
    frame_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_target(self) -> EvidenceSpan:
        if self.kind is SpanKind.TRANSCRIPT_QUOTE and not self.quote:
            raise ValueError("a transcript-quote span must carry the verbatim quote")
        if self.kind is SpanKind.FRAME and self.frame_index is None:
            raise ValueError("a frame span must carry a frame_index")
        return self


class EventRelation(_StrictRecord):
    """A directed edge between two events (DATA_MODEL.md record 20)."""

    relation_id: str = Field(min_length=1)
    kind: RelationKind
    source_event_id: str = Field(min_length=1)
    target_event_id: str = Field(min_length=1)
    evidence_claim_id: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _validate_self_edge(self) -> EventRelation:
        if self.source_event_id == self.target_event_id:
            raise ValueError("an event relation may not point at itself")
        return self


# --------------------------------------------------------------------------
# Derived records
# --------------------------------------------------------------------------


class Observation(DerivedRecord):
    """A time-bounded factual or measured record (DATA_MODEL.md record 7)."""

    modality: Modality
    native_location: str = Field(min_length=1)
    measured: bool = False
    certainty: _Unit | None = None


class GameplayEvent(DerivedRecord):
    """A gameplay occurrence and its context (DATA_MODEL.md record 9)."""

    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    enemy_behavior: str | None = None
    environment: str | None = None
    outcome: str | None = None
    player_action: str | None = None
    threat: str | None = None
    uncertainty: _Unit | None = None


class ComedyBeat(DerivedRecord):
    """A comedic beat and its mechanism (DATA_MODEL.md record 10)."""

    incongruity: str = Field(min_length=1)
    setup: str | None = None
    payoff: str | None = None
    target_of_humor: str | None = None
    stance_changes: list[str] = Field(default_factory=list)
    mechanism_labels: list[_MechanismLabel] = Field(default_factory=list)
    speech_visual_dependency: str = Field(min_length=1)
    narrative_role: NarrativeRole = NarrativeRole.UNKNOWN


class VocalDelivery(DerivedRecord):
    """Acoustic measures, with inferred affect held separately (record 11).

    ``inferred_affect`` stays null unless the audio stream was actually
    analyzed; the acoustic measurements above it are independent of that.
    """

    pause_ms: int | None = Field(default=None, ge=0)
    speech_rate_wpm: float | None = Field(default=None, ge=0.0)
    energy_db: float | None = None
    pitch_movement: float | None = None
    inferred_affect: str | None = None


class CharacterState(DerivedRecord):
    """A temporally scoped state of a narrative entity (record 12)."""

    entity_id: str = Field(min_length=1)
    beliefs: list[str] = Field(default_factory=list)
    fear: str | None = None
    confidence_level: str | None = None
    grudges: list[str] = Field(default_factory=list)
    expectations: list[str] = Field(default_factory=list)
    memories: list[str] = Field(default_factory=list)


class ResponseDecisionRecord(DerivedRecord):
    """What the narrator does at a beat, including non-jokes (record 13)."""

    decision: ResponseDecision
    reason: str = Field(min_length=1)
    is_negative_example: bool = False


class EditEvent(DerivedRecord):
    """An editorial change on the output timeline (DATA_MODEL.md record 14).

    ``output_start_ms``/``output_end_ms`` locate the edit in the finished
    video; the media range it draws from is optional, and no frame-accurate
    boundary is asserted without a ``tolerance_ms`` estimate.
    """

    edit_type: _EditTypeLabel
    output_start_ms: int = Field(ge=0)
    output_end_ms: int = Field(ge=0)
    output_is_point: bool = False
    source_start_ms: int | None = Field(default=None, ge=0)
    source_end_ms: int | None = Field(default=None, ge=0)
    continuity: ContinuityClass = ContinuityClass.UNCERTAIN
    detection_method: str = Field(min_length=1)
    visual_effect: str | None = None
    tolerance_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _validate_output(self) -> EditEvent:
        try:
            MsInterval(self.output_start_ms, self.output_end_ms, self.output_is_point)
        except TimebaseError as exc:
            raise ValueError(f"output interval: {exc}") from exc
        if (self.source_start_ms is None) != (self.source_end_ms is None):
            raise ValueError("source range needs both bounds or neither")
        if (
            self.source_start_ms is not None
            and self.source_end_ms is not None
            and self.source_start_ms > self.source_end_ms
        ):
            raise ValueError("source range start must not exceed its end")
        return self

    @property
    def output_interval(self) -> MsInterval:
        return MsInterval(
            self.output_start_ms, self.output_end_ms, self.output_is_point
        )


class ShotContinuity(DerivedRecord):
    """A continuous span and how it is classified (DATA_MODEL.md record 15)."""

    continuity: ContinuityClass
    effects: list[str] = Field(default_factory=list)
    camera_vs_editing_ambiguous: bool = False


class AudioEvent(DerivedRecord):
    """An event on one audio stream (DATA_MODEL.md record 16)."""

    stream: str = Field(min_length=1)
    kind: AudioEventKind
    confidence: _Unit | None = None


class MusicCue(DerivedRecord):
    """A music cue's role and evidence (DATA_MODEL.md record 17).

    A verified track identity is required before ``identity`` may be set; the
    design docs forbid inferring a track from acoustic similarity alone.
    """

    status: MusicStatus = MusicStatus.UNKNOWN
    energy: float | None = None
    arousal: float | None = None
    mood: str | None = None
    rhythm: str | None = None
    fade_in: bool = False
    fade_out: bool = False
    change_reason: str | None = None
    identity: str | None = None
    identity_verified: bool = False

    @model_validator(mode="after")
    def _validate_identity(self) -> MusicCue:
        if self.identity is not None and not self.identity_verified:
            raise ValueError(
                "music identity may only be recorded when independently verified"
            )
        return self


class AudioMixEvent(DerivedRecord):
    """A mix action over a span (DATA_MODEL.md record 18)."""

    ducking: bool = False
    crossfade: bool = False
    relative_loudness_db: float | None = None
    dynamic_range_db: float | None = None
    interruption: bool = False
    sync_with_speech: bool = False


class NarrativeEntity(DerivedRecord):
    """A recurring target with a stable ID (DATA_MODEL.md record 19)."""

    entity_id: str = Field(min_length=1)
    kind: EntityKind
    label: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)


class StylePattern(DerivedRecord):
    """A reusable pattern generalized across examples (record 21).

    A style pattern is always a generalization (E3) — never a claim about what
    the original producer actually intended.
    """

    trigger: str = Field(min_length=1)
    mental_state_transitions: list[str] = Field(default_factory=list)
    optional_techniques: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    counterexamples: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_generalization(self) -> StylePattern:
        if self.epistemic_level is not EpistemicLevel.E3_GENERALIZATION:
            raise ValueError("a style pattern must be an E3 generalization")
        return self


# --------------------------------------------------------------------------
# Human-feedback records
# --------------------------------------------------------------------------


class Review(_StrictRecord):
    """A human correction or disagreement (DATA_MODEL.md record 22).

    Reviews are separate records, so a correction is recorded as a new claim
    that supersedes the old one rather than editing the underlying evidence.
    """

    review_id: str = Field(min_length=1)
    target_claim_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    status: ReviewStatus
    correction: str | None = None
    disagreement: str | None = None
    created_at: date | None = None


class GenerationTrial(_StrictRecord):
    """One generation attempt and its candidates (DATA_MODEL.md record 23)."""

    trial_id: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    drafts: list[str] = Field(default_factory=list)
    rejected_candidates: list[str] = Field(default_factory=list)
    tts_audio_ids: list[str] = Field(default_factory=list)
    editorial_variants: list[str] = Field(default_factory=list)
    reviewer_scores: _Scores = Field(default_factory=dict)


class HumanPreference(_StrictRecord):
    """Blind pairwise or ordinal preference ratings (DATA_MODEL.md record 24)."""

    preference_id: str = Field(min_length=1)
    trial_ids: list[str] = Field(min_length=2)
    blind: bool = True
    preferred_trial_id: str | None = None
    groundedness: _Scores = Field(default_factory=dict)
    naturalness: _Scores = Field(default_factory=dict)
    funny: _Scores = Field(default_factory=dict)
    annoying: _Scores = Field(default_factory=dict)
    intentional_silence_preferred: bool | None = None

    @model_validator(mode="after")
    def _validate_preference(self) -> HumanPreference:
        if self.preferred_trial_id is not None and self.preferred_trial_id not in self.trial_ids:
            raise ValueError("preferred_trial_id must be one of trial_ids")
        return self


RECORD_TYPES: dict[str, type[BaseModel]] = {
    "source_artifact": SourceArtifact,
    "reference_video": ReferenceVideo,
    "analysis_run": AnalysisRun,
    "coverage_window": CoverageWindow,
    "utterance": Utterance,
    "word_alignment": WordAlignment,
    "observation": Observation,
    "evidence_span": EvidenceSpan,
    "gameplay_event": GameplayEvent,
    "comedy_beat": ComedyBeat,
    "vocal_delivery": VocalDelivery,
    "character_state": CharacterState,
    "response_decision": ResponseDecisionRecord,
    "edit_event": EditEvent,
    "shot_continuity": ShotContinuity,
    "audio_event": AudioEvent,
    "music_cue": MusicCue,
    "audio_mix_event": AudioMixEvent,
    "narrative_entity": NarrativeEntity,
    "event_relation": EventRelation,
    "style_pattern": StylePattern,
    "review": Review,
    "generation_trial": GenerationTrial,
    "human_preference": HumanPreference,
}


def parse_record(record_type: str, data: dict[str, Any]) -> BaseModel:
    """Validate ``data`` as the named record type, or raise ``RecordError``."""
    model = RECORD_TYPES.get(record_type)
    if model is None:
        raise RecordError(
            f"unknown record type {record_type!r}; "
            f"known: {sorted(RECORD_TYPES)}"
        )
    try:
        return model(**data)
    except Exception as exc:  # pydantic ValidationError carries the detail
        raise RecordError(f"{record_type}: {exc}") from exc
