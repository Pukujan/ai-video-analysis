"""Tests for the canonical record types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness.records import RECORD_TYPES, RecordError, parse_record
from harness.vocab import EpistemicLevel


def _prov(**overrides: object) -> dict:
    data = {
        "claim_id": "c1",
        "source_id": "reference01-transcript",
        "media_start_ms": 0,
        "media_end_ms": 1_000,
        "source_kind": "transcript",
        "verbatim_evidence": "0:00 text",
        "extraction_method": "transcript_stamp_boundaries",
        "epistemic_level": "E1",
    }
    data.update(overrides)
    return data


MINIMAL: dict[str, dict] = {
    "source_artifact": {
        "artifact_id": "a1",
        "kind": "transcript",
        "provenance_note": "supplied by the user",
    },
    "reference_video": {
        "video_id": "reference01",
        "source_artifact_id": "a1",
        "duration_ms": 564_000,
        "video_timebase": "ms",
    },
    "analysis_run": {
        "run_id": "r1",
        "provider": "example",
        "model_id": "example-v1",
        "prompt_hash": "deadbeef",
        "code_version": "0.1.0",
        "frame_sample_policy": "1 fps",
    },
    "coverage_window": {
        "window_id": "w1",
        "video_id": "reference01",
        "start_ms": 0,
        "end_ms": 20_000,
        "modalities": ["speech", "visual"],
        "sampling_policy": "20s nominal, 5s overlap",
    },
    "utterance": {
        "utterance_id": "u1",
        "video_id": "reference01",
        "speaker": "narrator",
        "start_ms": 0,
        "end_ms": 3_000,
        "raw_text": "hello",
        "alignment_method": "transcript_stamp_boundaries",
    },
    "word_alignment": {
        "alignment_id": "wa1",
        "utterance_id": "u1",
        "token": "hello",
        "start_ms": 0,
        "end_ms": 400,
    },
    "observation": _prov(modality="visual", native_location="frame 12"),
    "evidence_span": {
        "span_id": "s1",
        "claim_id": "c1",
        "source_id": "reference01-transcript",
        "kind": "transcript_quote",
        "quote": "hello",
        "start_ms": 0,
        "end_ms": 3_000,
    },
    "gameplay_event": _prov(actor="player", action="rolls into the room"),
    "comedy_beat": _prov(
        incongruity="childish rolling framed as sacred", speech_visual_dependency="speech"
    ),
    "vocal_delivery": _prov(),
    "character_state": _prov(entity_id="knight-01"),
    "response_decision": _prov(decision="speak", reason="the beat needs a callback"),
    "edit_event": _prov(
        edit_type="cut",
        output_start_ms=0,
        output_end_ms=1_000,
        detection_method="scene_cut",
    ),
    "shot_continuity": _prov(continuity="continuous"),
    "audio_event": _prov(stream="game", kind="sfx"),
    "music_cue": _prov(),
    "audio_mix_event": _prov(),
    "narrative_entity": _prov(entity_id="knight-01", kind="enemy", label="the knight"),
    "event_relation": {
        "relation_id": "rel1",
        "kind": "pays_off",
        "source_event_id": "e1",
        "target_event_id": "e2",
    },
    "style_pattern": _prov(
        epistemic_level="E3",
        model_id="m1",
        alternate_hypotheses=["mere coincidence"],
        trigger="narrator commits to a bit",
    ),
    "review": {
        "review_id": "rv1",
        "target_claim_id": "c1",
        "reviewer": "user",
        "status": "confirmed",
    },
    "generation_trial": {
        "trial_id": "t1",
        "scenario": "boss approach",
        "prompt": "narrate the approach",
        "model_id": "example-v1",
    },
    "human_preference": {"preference_id": "p1", "trial_ids": ["t1", "t2"]},
}


class TestCoverage:
    def test_every_documented_record_type_is_registered(self) -> None:
        assert len(RECORD_TYPES) == 24
        assert set(MINIMAL) == set(RECORD_TYPES)

    @pytest.mark.parametrize("record_type", sorted(MINIMAL))
    def test_minimal_payload_validates(self, record_type: str) -> None:
        record = parse_record(record_type, MINIMAL[record_type])
        assert record is not None

    def test_unknown_record_type_is_rejected(self) -> None:
        with pytest.raises(RecordError):
            parse_record("not_a_record", {})

    def test_bad_payload_is_wrapped_as_record_error(self) -> None:
        with pytest.raises(RecordError):
            parse_record("reference_video", {"video_id": "v"})


class TestIntervalRules:
    def test_zero_width_window_must_be_a_point(self) -> None:
        payload = dict(MINIMAL["coverage_window"], start_ms=5_000, end_ms=5_000)
        with pytest.raises(RecordError):
            parse_record("coverage_window", payload)

    def test_zero_width_window_accepts_point_flag(self) -> None:
        payload = dict(
            MINIMAL["coverage_window"], start_ms=5_000, end_ms=5_000, is_point=True
        )
        record = parse_record("coverage_window", payload)
        assert record.interval.duration_ms == 0  # type: ignore[attr-defined]

    def test_reversed_window_is_rejected(self) -> None:
        payload = dict(MINIMAL["coverage_window"], start_ms=9_000, end_ms=1_000)
        with pytest.raises(RecordError):
            parse_record("coverage_window", payload)

    def test_edit_event_output_interval_is_separate_from_media(self) -> None:
        record = parse_record("edit_event", MINIMAL["edit_event"])
        assert record.interval.start_ms == 0  # type: ignore[attr-defined]
        assert record.output_interval.end_ms == 1_000  # type: ignore[attr-defined]

    def test_edit_event_rejects_half_a_source_range(self) -> None:
        payload = dict(MINIMAL["edit_event"], source_start_ms=100)
        with pytest.raises(RecordError):
            parse_record("edit_event", payload)


class TestVocabularyEnforcement:
    def test_unknown_edit_type_is_rejected(self) -> None:
        payload = dict(MINIMAL["edit_event"], edit_type="hardcut")
        with pytest.raises(RecordError):
            parse_record("edit_event", payload)

    def test_extension_token_is_accepted(self) -> None:
        payload = dict(MINIMAL["edit_event"], edit_type="ext:hard_cut")
        parse_record("edit_event", payload)

    def test_unknown_comedy_mechanism_is_rejected(self) -> None:
        payload = dict(MINIMAL["comedy_beat"], mechanism_labels=["funniness"])
        with pytest.raises(RecordError):
            parse_record("comedy_beat", payload)

    def test_known_comedy_mechanisms_are_accepted(self) -> None:
        payload = dict(MINIMAL["comedy_beat"], mechanism_labels=["sarcasm", "wordplay"])
        parse_record("comedy_beat", payload)


class TestDomainGuarantees:
    def test_failed_window_needs_a_reason(self) -> None:
        payload = dict(MINIMAL["coverage_window"], status="failed")
        with pytest.raises(RecordError):
            parse_record("coverage_window", payload)

    def test_reason_on_a_non_failed_window_is_rejected(self) -> None:
        payload = dict(MINIMAL["coverage_window"], status="succeeded", failure_reason="x")
        with pytest.raises(RecordError):
            parse_record("coverage_window", payload)

    def test_music_identity_requires_verification(self) -> None:
        payload = dict(MINIMAL["music_cue"], identity="Some Song")
        with pytest.raises(RecordError):
            parse_record("music_cue", payload)

    def test_verified_music_identity_is_accepted(self) -> None:
        payload = dict(
            MINIMAL["music_cue"], identity="Some Song", identity_verified=True
        )
        parse_record("music_cue", payload)

    def test_style_pattern_must_be_a_generalization(self) -> None:
        payload = dict(
            MINIMAL["style_pattern"],
            epistemic_level="E2",
            alternate_hypotheses=["a reading"],
            model_id="m1",
        )
        with pytest.raises(RecordError):
            parse_record("style_pattern", payload)

    def test_event_relation_may_not_self_reference(self) -> None:
        payload = dict(MINIMAL["event_relation"], target_event_id="e1")
        with pytest.raises(RecordError):
            parse_record("event_relation", payload)

    def test_preferred_trial_must_be_in_the_comparison(self) -> None:
        payload = dict(MINIMAL["human_preference"], preferred_trial_id="t3")
        with pytest.raises(RecordError):
            parse_record("human_preference", payload)

    def test_transcript_quote_span_needs_the_quote(self) -> None:
        payload = dict(MINIMAL["evidence_span"])
        payload.pop("quote")
        with pytest.raises(RecordError):
            parse_record("evidence_span", payload)

    def test_derived_record_still_requires_alternatives_at_e2(self) -> None:
        payload = dict(MINIMAL["observation"], epistemic_level="E2", model_id="m1")
        with pytest.raises(RecordError):
            parse_record("observation", payload)

    def test_character_state_does_not_shadow_provenance_confidence(self) -> None:
        record = parse_record(
            "character_state", dict(MINIMAL["character_state"], confidence=0.5)
        )
        assert record.confidence == 0.5  # type: ignore[attr-defined]
        assert record.confidence_level is None  # type: ignore[attr-defined]

    def test_records_are_frozen(self) -> None:
        record = parse_record("observation", MINIMAL["observation"])
        with pytest.raises(ValidationError):
            record.claim_id = "c2"  # type: ignore[misc]

    def test_derived_records_default_to_unreviewed_e1(self) -> None:
        record = parse_record("observation", MINIMAL["observation"])
        assert record.epistemic_level is EpistemicLevel.E1_OBSERVATION  # type: ignore[attr-defined]
