"""Tests for the lenses. No network: parse is exercised on fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
from harness.records import RecordError

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lens"
_MODEL = "ali/qwen3.8-omni-flash"


def _ctx() -> LensContext:
    return LensContext(
        video_id="ds3_ep_3",
        source_id="art_" + "a" * 12,
        run_id="run_test_ex_ds3",
        profile=load_profile("ds3"),
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
    records = lens.parse(response, (0, 25_000), _ctx())
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
    records = lens.parse(response, (20_000, 45_000), _ctx())
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
        lens.parse(response, (0, 25_000), _ctx())
