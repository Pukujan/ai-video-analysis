"""Tests for the lenses. No network: parse is exercised on fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.backend import Completion, MalformedReply, Request
from harness.clips import WindowMedia
from harness.config import load_profile
from harness.lens import (
    SUPPLIED,
    DeliveryLens,
    InterpretationLens,
    LensContext,
    TranscriptLens,
    parse_transcript,
)
from harness.records import RecordError, parse_record
from harness.vocab import NarrativeRole, ResponseDecision

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lens"
_MODEL = "ali/qwen3.8-omni-flash"


def _ctx() -> LensContext:
    return LensContext(
        video_id="ds3_ep_3",
        source_id="art_" + "a" * 12,
        run_id="run_test_ex_ds3",
        profile=load_profile("ds3"),
        frame_rate=30.0,
    )


def _utterance(text: str, start_ms: int = 0, end_ms: int = 1_000):
    """A real ``utterance`` record, for verifying a quote against the words."""
    return parse_record(
        "utterance",
        {
            "utterance_id": f"u_test_{abs(hash(text)) % 10_000}",
            "video_id": "ds3_ep_3",
            "speaker": "narrator",
            "raw_text": text,
            "alignment_method": "transcript_slice",
            "start_ms": start_ms,
            "end_ms": end_ms,
        },
    )


def _media(tmp_path: Path, has_audio: bool = True) -> WindowMedia:
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00")
    wav = tmp_path / "clip.wav"
    if has_audio:
        wav.write_bytes(b"\x00")
    return WindowMedia(clip, wav if has_audio else None, (), 0, 25_000)


# --------------------------------------------------------------------------
# Transcript lens
# --------------------------------------------------------------------------


def test_parse_transcript_reads_m_ss_prefixes() -> None:
    lines = parse_transcript(_FIXTURES / "test_transcript.txt")
    assert lines[0].start_ms == 0
    assert lines[0].text == "I almost feel bad for constantly"
    assert lines[2].start_ms == 5_000


def test_supplied_lens_slices_window(tmp_path: Path) -> None:
    lens = TranscriptLens(_FIXTURES / "test_transcript.txt", _MODEL)
    assert lens.mode == "supplied"
    records = lens.run((0, 5_000), _media(tmp_path), _ctx(), (), None)
    types = [t for t, _ in records]
    assert "utterance" in types and "word_alignment" in types
    utterances = [m.model_dump() for t, m in records if t == "utterance"]
    assert [u["raw_text"] for u in utterances] == [
        "I almost feel bad for constantly",
        "interrupting this beautiful church",
    ]
    assert all(u["alignment_method"] == SUPPLIED for u in utterances)


def test_supplied_lens_empty_window(tmp_path: Path) -> None:
    lens = TranscriptLens(_FIXTURES / "test_transcript.txt", _MODEL)
    assert lens.run((600_000, 625_000), _media(tmp_path), _ctx(), (), None) == []


def test_word_alignment_interpolates_across_span(tmp_path: Path) -> None:
    lens = TranscriptLens(_FIXTURES / "test_transcript.txt", _MODEL)
    records = lens.run((0, 5_000), _media(tmp_path), _ctx(), (), None)
    words = [m.model_dump() for t, m in records if t == "word_alignment"]
    assert words[0]["token"] == "I"
    assert words[0]["start_ms"] == 0
    assert words[-1]["end_ms"] <= 5_000
    # tokens are ordered and non-overlapping
    for a, b in zip(words, words[1:], strict=False):
        assert a["end_ms"] <= b["start_ms"]


def test_asr_mode_used_when_no_transcript(tmp_path: Path) -> None:
    lens = TranscriptLens(None, _MODEL)
    assert lens.mode == "asr"
    assert lens.run((0, 5_000), _media(tmp_path), _ctx(), (), None) == []  # no backend


class _StubBackend:
    """Returns scripted completions, recording the prompts it was sent.

    A scripted item may be an ``Exception`` instance, which is raised instead
    of returned — so a test can script a non-JSON reply (``MalformedReply``).
    """

    def __init__(self, *contents: object) -> None:
        self.contents = list(contents)
        self.prompts: list[str] = []

    def complete(self, request: Request) -> Completion:
        self.prompts.append(request.prompt)
        item = self.contents.pop(0)
        if isinstance(item, Exception):
            raise item
        return Completion(item, _MODEL, {}, 1)  # type: ignore[arg-type]


def test_asr_emits_utterances_and_words(tmp_path: Path) -> None:
    lens = TranscriptLens(None, _MODEL)
    backend = _StubBackend(
        {"utterances": [{"start_ms": 0, "end_ms": 2_000, "text": "hello there"}]}
    )
    records = lens.run((0, 5_000), _media(tmp_path), _ctx(), (), backend)
    types = [t for t, _ in records]
    assert types.count("utterance") == 1
    utterance = next(m for t, m in records if t == "utterance").model_dump()
    assert utterance["raw_text"] == "hello there"
    assert utterance["alignment_method"] == f"asr:{_MODEL}"


def test_malformed_asr_reply_is_a_record_error_not_a_crash(tmp_path: Path) -> None:
    """A reply missing a timestamp must fail the *reply*, not raise a raw error.

    ``_asr_records`` used to do ``int(item["start_ms"])``, so a model that
    omitted the field raised ``KeyError`` — which escapes the per-window loop
    and kills the whole video. It is normalized to ``RecordError`` now.
    """
    lens = TranscriptLens(None, _MODEL)
    bad = {"utterances": [{"end_ms": 1_000, "text": "x"}]}
    backend = _StubBackend(bad, bad)
    with pytest.raises(RecordError):
        lens.run((0, 5_000), _media(tmp_path), _ctx(), (), backend)
    assert len(backend.prompts) == 2  # the re-ask ran; it stayed malformed


def test_asr_reasks_once_on_a_malformed_reply(tmp_path: Path) -> None:
    lens = TranscriptLens(None, _MODEL)
    backend = _StubBackend(
        {"utterances": "not a list"},
        {"utterances": [{"start_ms": 0, "end_ms": 1_000, "text": "recovered"}]},
    )
    records = lens.run((0, 5_000), _media(tmp_path), _ctx(), (), backend)
    assert len(backend.prompts) == 2
    assert "rejected" in backend.prompts[1]
    assert next(m for t, m in records if t == "utterance").model_dump()["raw_text"] == "recovered"


def test_asr_non_json_reply_is_reasked_once(tmp_path: Path) -> None:
    """A reply that is not JSON at all gets the same one re-ask as a bad shape.

    ``_extract_json`` raises ``MalformedReply``; the lens catches it, so the
    window recovers instead of failing on the first non-JSON reply (which cost
    real windows on the live ep2 run).
    """
    lens = TranscriptLens(None, _MODEL)
    backend = _StubBackend(
        MalformedReply("model reply was not JSON: Expecting value"),
        {"utterances": [{"start_ms": 0, "end_ms": 1_000, "text": "recovered"}]},
    )
    records = lens.run((0, 5_000), _media(tmp_path), _ctx(), (), backend)
    assert len(backend.prompts) == 2
    assert "rejected" in backend.prompts[1]
    assert next(m for t, m in records if t == "utterance").model_dump()["raw_text"] == "recovered"


def test_asr_non_json_twice_fails_as_record_error(tmp_path: Path) -> None:
    """A second non-JSON reply is normalized to ``RecordError``, not left raw.

    Both are reply-shape failures, so the window must land in the
    ``schema_rejected:`` bucket rather than splitting the class across
    ``schema_rejected:``/``extraction_error:``.
    """
    lens = TranscriptLens(None, _MODEL)
    bad = MalformedReply("model reply was not JSON")
    backend = _StubBackend(bad, bad)
    with pytest.raises(RecordError):
        lens.run((0, 5_000), _media(tmp_path), _ctx(), (), backend)
    assert len(backend.prompts) == 2


def test_asr_clamps_a_start_past_the_window(tmp_path: Path) -> None:
    """A timestamp beyond the clip is clamped, not failed.

    The live ep2 run lost four windows to ``interval start 165300 must not
    exceed end``: ``s`` was unclamped while ``e`` was clamped, so a start past
    ``window[1]`` inverted the interval. Both ends clamp now.
    """
    lens = TranscriptLens(None, _MODEL)
    backend = _StubBackend(
        {"utterances": [{"start_ms": 25_300, "end_ms": 26_000, "text": "late"}]}
    )
    records = lens.run((140_000, 165_000), _media(tmp_path), _ctx(), (), backend)
    utterance = next(m for t, m in records if t == "utterance").model_dump()
    assert utterance["start_ms"] < utterance["end_ms"]
    assert utterance["start_ms"] >= 140_000 and utterance["end_ms"] <= 165_000


def test_asr_clamps_a_start_on_the_window_end(tmp_path: Path) -> None:
    """A start landing exactly on ``window[1]`` still yields a valid interval."""
    lens = TranscriptLens(None, _MODEL)
    backend = _StubBackend(
        {"utterances": [{"start_ms": 25_000, "end_ms": 25_000, "text": "edge"}]}
    )
    records = lens.run((140_000, 165_000), _media(tmp_path), _ctx(), (), backend)
    utterance = next(m for t, m in records if t == "utterance").model_dump()
    assert utterance["start_ms"] < utterance["end_ms"]


# --------------------------------------------------------------------------
# Delivery lens
# --------------------------------------------------------------------------


def test_delivery_lens_emits_nothing_without_audio(tmp_path: Path) -> None:
    lens = DeliveryLens()
    assert lens.run((0, 5_000), _media(tmp_path, has_audio=False), _ctx(), (), None) == []


# --------------------------------------------------------------------------
# Interpretation lens
# --------------------------------------------------------------------------


def test_interpretation_builds_request(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    request = lens.build((0, 25_000), _media(tmp_path), ())
    assert request.model == _MODEL
    assert request.media[0].kind == "video"
    assert request.schema is not None


def test_interpretation_parses_beats(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    response = json.loads((_FIXTURES / "interpretation_response.json").read_text("utf-8"))
    records = lens.parse(response, (0, 25_000), _ctx(), utterances=(_utterance("how sweet"),))
    types = [t for t, _ in records]
    assert types.count("comedy_beat") == 2
    assert types.count("response_decision") == 2
    assert types.count("evidence_span") == 2

    beat = next(m for t, m in records if t == "comedy_beat").model_dump()
    assert beat["epistemic_level"] == "E2"
    assert beat["model_id"] == _MODEL
    assert beat["alternate_hypotheses"] == ["genuine appreciation of the art design"]
    assert beat["mechanism_labels"] == ["sarcasm", "irony"]
    assert beat["speech_visual_dependency"] == "needs the slaughter on screen"

    span = next(m for t, m in records if t == "evidence_span").model_dump()
    assert span["kind"] == "transcript_quote"
    assert span["quote"] == "how sweet"


def test_interpretation_offsets_timestamps_to_media_time(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    response = json.loads((_FIXTURES / "interpretation_response.json").read_text("utf-8"))
    records = lens.parse(response, (20_000, 45_000), _ctx(), utterances=())
    beat = next(m for t, m in records if t == "comedy_beat").model_dump()
    assert beat["media_start_ms"] == 21_000  # 20_000 window start + 1_000 clip offset


def test_beat_without_alternates_is_rejected(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    response = {
        "beats": [
            {
                "start_ms": 0,
                "end_ms": 1_000,
                "quote": "q",
                "quote_source": "transcript",
                "incongruity": "x",
                "mechanism_labels": ["sarcasm"],
                "speech_visual_dependency": "words",
                "decision": "react",
                "decision_reason": "r",
                "alternate_readings": [],
            }
        ]
    }
    with pytest.raises(RecordError):  # an E2 claim needs alternate_hypotheses
        lens.parse(response, (0, 25_000), _ctx(), utterances=())


def test_schema_carries_the_label_vocabularies(tmp_path: Path) -> None:
    """The model must be told the closed labels, not just have them checked.

    A bare ``{"type": "string"}`` let the model answer ``narrative_role`` with a
    free-text description, which ``parse`` then rejected — so every live window
    failed. The schema has to carry the vocabulary.
    """
    request = InterpretationLens(_MODEL).build((0, 25_000), _media(tmp_path), ())
    beat = request.schema["properties"]["beats"]["items"]
    assert beat["properties"]["narrative_role"]["enum"] == [
        m.value for m in NarrativeRole
    ]
    assert beat["properties"]["decision"]["enum"] == [m.value for m in ResponseDecision]
    assert "sarcasm" in beat["properties"]["mechanism_labels"]["items"]["enum"]
    assert "narrative_role" in beat["required"]
    assert beat["properties"]["quote_source"]["enum"] == ["transcript", "audio", "visual"]
    assert "quote_source" in beat["required"]


def test_build_prompt_states_the_quote_rule(tmp_path: Path) -> None:
    """The model must be told to copy quotes exactly and to declare the source.

    Verification in ``parse`` can only be honest if the model is told the rule;
    otherwise it silently prefers the clip's audio and every quote it read is
    mislabelled as a transcript quote.
    """
    prompt = InterpretationLens(_MODEL).build((0, 25_000), _media(tmp_path), ()).prompt
    assert "quote_source" in prompt
    assert "transcript" in prompt and "audio" in prompt and "visual" in prompt


def test_free_text_narrative_role_is_rejected(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    response = {
        "beats": [
            {
                "start_ms": 0,
                "end_ms": 1_000,
                "quote": "q",
                "quote_source": "transcript",
                "incongruity": "x",
                "mechanism_labels": ["sarcasm"],
                "speech_visual_dependency": "words",
                "narrative_role": "establishes the narrator's sadistic persona",
                "decision": "react",
                "decision_reason": "r",
                "alternate_readings": ["literal"],
            }
        ]
    }
    with pytest.raises(RecordError, match="narrative_role"):
        lens.parse(response, (0, 25_000), _ctx(), utterances=())


def test_unknown_mechanism_labels_are_dropped_not_fatal(tmp_path: Path) -> None:
    """One invented label must not discard a beat whose other labels are good."""
    lens = InterpretationLens(_MODEL)
    response = {
        "beats": [
            {
                "start_ms": 0,
                "end_ms": 1_000,
                "quote": "q",
                "quote_source": "transcript",
                "incongruity": "x",
                "mechanism_labels": ["sarcasm", "vibes-based humor"],
                "speech_visual_dependency": "words",
                "narrative_role": "isolated",
                "decision": "react",
                "decision_reason": "r",
                "alternate_readings": ["literal"],
            }
        ]
    }
    records = lens.parse(response, (0, 25_000), _ctx(), utterances=())
    beat = next(m for t, m in records if t == "comedy_beat").model_dump()
    assert beat["mechanism_labels"] == ["sarcasm"]


def test_all_unknown_mechanism_labels_are_rejected(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    response = {
        "beats": [
            {
                "start_ms": 0,
                "end_ms": 1_000,
                "quote": "q",
                "quote_source": "transcript",
                "incongruity": "x",
                "mechanism_labels": ["vibes", "chaos energy"],
                "speech_visual_dependency": "words",
                "narrative_role": "isolated",
                "decision": "react",
                "decision_reason": "r",
                "alternate_readings": ["literal"],
            }
        ]
    }
    with pytest.raises(RecordError, match="mechanism_labels"):
        lens.parse(response, (0, 25_000), _ctx(), utterances=())


# --------------------------------------------------------------------------
# Evidence spans: the kind is earned, not assumed
# --------------------------------------------------------------------------


def _beat(quote: str, source: str, start_ms: int = 1_000, end_ms: int = 2_000) -> dict:
    return {
        "beats": [
            {
                "start_ms": start_ms,
                "end_ms": end_ms,
                "quote": quote,
                "quote_source": source,
                "incongruity": "x",
                "mechanism_labels": ["irony"],
                "speech_visual_dependency": "words",
                "narrative_role": "isolated",
                "decision": "react",
                "decision_reason": "r",
                "alternate_readings": ["literal"],
            }
        ]
    }


def _span(records: list, ctx: LensContext) -> dict:
    return next(m for t, m in records if t == "evidence_span").model_dump()


def test_span_kind_is_transcript_quote_when_the_quote_verifies(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    utterances = (_utterance("I almost feel bad for constantly"),)
    records = lens.parse(
        _beat("I almost feel bad", "transcript"), (0, 25_000), _ctx(), utterances=utterances
    )
    assert _span(records, _ctx())["kind"] == "transcript_quote"


def test_span_verifies_across_two_utterances(tmp_path: Path) -> None:
    """A quote spanning two transcript lines still earns ``transcript_quote``."""
    lens = InterpretationLens(_MODEL)
    utterances = (_utterance("gods. Time for"), _utterance("rolling. What am I"))
    records = lens.parse(
        _beat("gods. Time for rolling.", "transcript"), (0, 25_000), _ctx(), utterances=utterances
    )
    assert _span(records, _ctx())["kind"] == "transcript_quote"


def test_decensored_quote_is_audio_region_even_when_declared_transcript(
    tmp_path: Path,
) -> None:
    """The live defect, frozen: a quote the censored transcript cannot vouch for.

    The supplied ep3 transcript reads ``gigantic [ __ ] dragon``; the model
    quoted the clip's real audio, ``gigantic fucking dragon``. It declared
    ``transcript``, but the transcript does not contain it — so it is an audio
    span, not a transcript quote.
    """
    lens = InterpretationLens(_MODEL)
    utterances = (_utterance("It's a gigantic [ __ ] dragon."),)
    records = lens.parse(
        _beat("It's just a gigantic fucking dragon.", "transcript"),
        (0, 25_000),
        _ctx(),
        utterances=utterances,
    )
    assert _span(records, _ctx())["kind"] == "audio_region"


def test_visual_quote_is_a_frame_span(tmp_path: Path) -> None:
    """A picture description is a ``frame`` span, with an index at the beat start."""
    lens = InterpretationLens(_MODEL)
    records = lens.parse(
        _beat("[Please Stand By screen]", "visual", start_ms=1_000),
        (0, 25_000),
        _ctx(),
        utterances=(),
    )
    span = _span(records, _ctx())
    assert span["kind"] == "frame"
    assert span["frame_index"] == 30  # 1_000ms at 30 fps


def test_verification_overrides_the_declared_source(tmp_path: Path) -> None:
    """A quote that verifies is a transcript quote even if declared ``audio``."""
    lens = InterpretationLens(_MODEL)
    records = lens.parse(
        _beat("how sweet", "audio"),
        (0, 25_000),
        _ctx(),
        utterances=(_utterance("Aww, how sweet."),),
    )
    assert _span(records, _ctx())["kind"] == "transcript_quote"


def test_declared_transcript_that_fails_verification_is_audio_region(
    tmp_path: Path,
) -> None:
    """A near-miss quote resolves to ``audio_region`` without burning a re-ask."""
    lens = InterpretationLens(_MODEL)
    records = lens.parse(
        _beat("where was I, what did you drop", "transcript"),
        (0, 25_000),
        _ctx(),
        utterances=(_utterance("a completely different line"),),
    )
    assert _span(records, _ctx())["kind"] == "audio_region"


def test_missing_quote_source_is_rejected(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    response = _beat("q", "transcript")
    del response["beats"][0]["quote_source"]
    with pytest.raises(RecordError, match="quote_source"):
        lens.parse(response, (0, 25_000), _ctx(), utterances=())


def test_unknown_quote_source_is_rejected(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    with pytest.raises(RecordError, match="quote_source"):
        lens.parse(_beat("q", "vibes"), (0, 25_000), _ctx(), utterances=())


def test_interpretation_non_json_reply_is_reasked_once(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    backend = _StubBackend(
        MalformedReply("model reply was not JSON: Unterminated string"),
        _beat("how sweet", "transcript"),
    )
    records = lens.run(
        (0, 25_000), _media(tmp_path), _ctx(), (_utterance("how sweet"),), backend
    )
    assert len(backend.prompts) == 2
    assert "rejected" in backend.prompts[1]
    assert any(t == "comedy_beat" for t, _ in records)


def test_interpretation_non_json_twice_fails_as_record_error(tmp_path: Path) -> None:
    lens = InterpretationLens(_MODEL)
    bad = MalformedReply("model reply was not JSON")
    backend = _StubBackend(bad, bad)
    with pytest.raises(RecordError):
        lens.run((0, 25_000), _media(tmp_path), _ctx(), (), backend)
    assert len(backend.prompts) == 2
