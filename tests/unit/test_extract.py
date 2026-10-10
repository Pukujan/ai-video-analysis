"""Tests for the extraction pass. No network: a scripted fake backend stands in.

The pass is exercised end to end against a generated test video, with the
window size shrunk so one short clip yields several coverage windows. The fake
backend replies by request shape, so the transcript (ASR) and interpretation
lenses are driven independently, and an interpretation reply can be an
exception instance to drive the gate-trip path.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from harness.backend import Completion, GateTripped, MalformedReply, Request
from harness.config import WindowingConfig, load_profile
from harness.extract import extract_video
from harness.persist import write_store
from harness.records import parse_record
from harness.registry import sha256_file

_UTTERANCES = [
    {"start_ms": 100, "end_ms": 900, "text": "I almost feel bad"},
]

_BEAT = {
    "start_ms": 200,
    "end_ms": 800,
    "quote": "I almost feel bad",
    "quote_source": "transcript",
    "incongruity": "mock-pity over carnage",
    "mechanism_labels": ["sarcasm"],
    "speech_visual_dependency": "needs the fight on screen",
    "narrative_role": "isolated",
    "decision": "speak",
    "decision_reason": "sets up the reversal",
    "alternate_readings": ["genuine sympathy"],
}
_BEAT_REPLY = {"beats": [_BEAT]}
_NO_ALTERNATES = {"beats": [{**_BEAT, "alternate_readings": []}]}


@pytest.fixture(scope="session")
def test_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 4-second testsrc clip with a tone, so windows have audio and picture."""
    video = tmp_path_factory.mktemp("extract-media") / "test.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=duration=4:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video),
        ],
        check=True,
        capture_output=True,
    )
    return video


def _profile():
    """The ds3 profile with 1 s windows, so a 4 s clip covers several windows."""
    return load_profile("ds3").model_copy(
        update={"windowing": WindowingConfig(window_ms=1_000, overlap_ms=0)}
    )


def _is_asr(request: Request) -> bool:
    return "utterances" in ((request.schema or {}).get("properties") or {})


def _completion(request: Request, content: dict) -> Completion:
    return Completion(content=content, model=request.model, usage={}, attempts=1)


class FakeBackend:
    """A scripted :class:`~harness.backend.Backend` that records every call."""

    def __init__(self, *, utterances=None, beats=None) -> None:
        self.calls: list[Request] = []
        self._utterances = _UTTERANCES if utterances is None else utterances
        self._beats = [_BEAT_REPLY] if beats is None else list(beats)
        self._beat_index = 0

    @property
    def asr_calls(self) -> list[Request]:
        return [request for request in self.calls if _is_asr(request)]

    @property
    def interpretation_calls(self) -> list[Request]:
        return [request for request in self.calls if not _is_asr(request)]

    def complete(self, request: Request) -> Completion:
        self.calls.append(request)
        if _is_asr(request):
            return _completion(request, {"utterances": self._utterances})
        reply = self._beats[min(self._beat_index, len(self._beats) - 1)]
        self._beat_index += 1
        if isinstance(reply, Exception):
            raise reply
        return _completion(request, reply)


class BoomBackend:
    """A backend that fails the test if a dry run reaches it."""

    def complete(self, request: Request) -> Completion:  # pragma: no cover - guard
        raise AssertionError("dry run must not call the model")


def _coverage(report) -> list[dict]:
    return [m.model_dump() for t, m in report.records if t == "coverage_window"]


def _row_count(db: Path, run_id: str) -> int:
    import duckdb

    con = duckdb.connect(str(db))
    try:
        return con.execute(
            "SELECT count(*) FROM records WHERE run_id = ?", [run_id]
        ).fetchone()[0]
    finally:
        con.close()


# --------------------------------------------------------------------------
# Shape and namespace
# --------------------------------------------------------------------------


def test_run_id_uses_its_own_namespace(test_video: Path, tmp_path: Path) -> None:
    profile = _profile()
    digest = sha256_file(test_video)
    report = extract_video(test_video, tmp_path, profile, backend=FakeBackend(), limit_windows=1)
    assert report.run_id == f"run_{digest[:12]}_ex_ds3"
    assert report.run_id != profile.run_id(digest)  # never the deterministic namespace
    assert report.digest == digest and report.video_id == "test"
    assert report.profile_id == "ds3" and report.profile_version == profile.profile.version
    assert report.config_hash == profile.config_hash()


def test_extraction_emits_the_six_slice_types(test_video: Path, tmp_path: Path) -> None:
    report = extract_video(test_video, tmp_path, _profile(), backend=FakeBackend(), limit_windows=1)
    assert set(report.counts) == {
        "utterance",
        "word_alignment",
        "evidence_span",
        "comedy_beat",
        "vocal_delivery",
        "response_decision",
        "coverage_window",
    }
    assert not report.failures


def test_every_window_is_terminal(test_video: Path, tmp_path: Path) -> None:
    report = extract_video(test_video, tmp_path, _profile(), backend=FakeBackend(), limit_windows=2)
    windows = _coverage(report)
    assert len(windows) == 2
    assert all(w["status"] in {"succeeded", "failed"} for w in windows)
    assert all(w["run_id"] == report.run_id for w in windows)


def test_limit_windows_caps_coverage(test_video: Path, tmp_path: Path) -> None:
    report = extract_video(test_video, tmp_path, _profile(), backend=FakeBackend(), limit_windows=3)
    assert len(_coverage(report)) == 3


def test_asr_fallback_is_reported(test_video: Path, tmp_path: Path) -> None:
    report = extract_video(test_video, tmp_path, _profile(), backend=FakeBackend(), limit_windows=1)
    assert any("ASR" in w for w in report.warnings)


# --------------------------------------------------------------------------
# Failure paths
# --------------------------------------------------------------------------


def test_gate_trip_marks_window_failed_and_keeps_partial_records(
    test_video: Path, tmp_path: Path
) -> None:
    backend = FakeBackend(beats=[GateTripped("DataInspectionFailed: refused", 3)])
    report = extract_video(test_video, tmp_path, _profile(), backend=backend, limit_windows=1)
    window = _coverage(report)[0]
    assert window["status"] == "failed"
    assert window["failure_reason"].startswith("content_gate:")
    assert any("content_gate" in failure for failure in report.failures)
    # the ASR pass already succeeded, so its records survive the failed window
    assert report.counts.get("utterance", 0) >= 1
    assert report.counts.get("comedy_beat", 0) == 0


def test_invalid_reply_is_reasked_once(test_video: Path, tmp_path: Path) -> None:
    backend = FakeBackend(beats=[_NO_ALTERNATES, _BEAT_REPLY])
    report = extract_video(test_video, tmp_path, _profile(), backend=backend, limit_windows=1)
    assert report.counts.get("comedy_beat") == 1
    assert not report.failures
    assert len(backend.interpretation_calls) == 2  # original + one re-ask
    assert "rejected" in backend.interpretation_calls[1].prompt


def test_window_fails_when_reply_stays_invalid(test_video: Path, tmp_path: Path) -> None:
    backend = FakeBackend(beats=[_NO_ALTERNATES])  # repeats on the re-ask
    report = extract_video(test_video, tmp_path, _profile(), backend=backend, limit_windows=1)
    window = _coverage(report)[0]
    assert window["status"] == "failed"
    assert window["failure_reason"].startswith("schema_rejected:")
    assert report.counts.get("comedy_beat", 0) == 0
    assert len(backend.interpretation_calls) == 2


def test_non_json_reply_is_reasked_once_and_recovers(test_video: Path, tmp_path: Path) -> None:
    """A non-JSON reply is a reply-shape failure, so it gets the one re-ask.

    It cost real windows on the live ep2 run: ``MalformedReply`` escaped the
    lens's ``except RecordError`` and failed the window on the first try.
    """
    backend = FakeBackend(
        beats=[MalformedReply("model reply was not JSON: Unterminated string"), _BEAT_REPLY]
    )
    report = extract_video(test_video, tmp_path, _profile(), backend=backend, limit_windows=1)
    assert report.counts.get("comedy_beat") == 1
    assert not report.failures
    assert len(backend.interpretation_calls) == 2
    assert "rejected" in backend.interpretation_calls[1].prompt


def test_window_fails_schema_rejected_when_reply_stays_non_json(
    test_video: Path, tmp_path: Path
) -> None:
    backend = FakeBackend(beats=[MalformedReply("model reply was not JSON")])  # repeats
    report = extract_video(test_video, tmp_path, _profile(), backend=backend, limit_windows=1)
    window = _coverage(report)[0]
    assert window["status"] == "failed"
    # the same bucket as any other reply-shape failure, not ``extraction_error:``
    assert window["failure_reason"].startswith("schema_rejected:")
    assert len(backend.interpretation_calls) == 2


def test_unverified_quote_span_is_audio_region(test_video: Path, tmp_path: Path) -> None:
    """A quote the window's words cannot vouch for is not a transcript quote."""
    beat = {**_BEAT, "quote": "words the transcript never had"}
    backend = FakeBackend(beats=[{"beats": [beat]}])
    report = extract_video(test_video, tmp_path, _profile(), backend=backend, limit_windows=1)
    span = next(m for t, m in report.records if t == "evidence_span").model_dump()
    assert span["kind"] == "audio_region"


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def test_rerun_is_idempotent_per_run(test_video: Path, tmp_path: Path) -> None:
    profile = _profile()
    first = extract_video(test_video, tmp_path, profile, backend=FakeBackend(), limit_windows=2)
    db = tmp_path / "data" / "analysis.duckdb"
    after_first = _row_count(db, first.run_id)
    second = extract_video(test_video, tmp_path, profile, backend=FakeBackend(), limit_windows=2)
    assert second.run_id == first.run_id
    assert _row_count(db, second.run_id) == after_first


def test_extraction_does_not_clobber_deterministic_rows(test_video: Path, tmp_path: Path) -> None:
    profile = _profile()
    digest = sha256_file(test_video)
    det_run = profile.run_id(digest)
    db = tmp_path / "data" / "analysis.duckdb"
    det_records = [
        ("source_artifact", parse_record("source_artifact", {
            "artifact_id": f"art_{digest[:12]}",
            "kind": "video",
            "provenance_note": "deterministic pass",
        }))
    ]
    write_store(db, det_run, "test", det_records)

    report = extract_video(test_video, tmp_path, profile, backend=FakeBackend(), limit_windows=1)
    assert _row_count(db, det_run) == len(det_records)
    assert _row_count(db, report.run_id) == len(report.records)


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------


def test_dry_run_makes_no_calls_and_persists_nothing(test_video: Path, tmp_path: Path) -> None:
    report = extract_video(
        test_video, tmp_path, _profile(), backend=BoomBackend(), limit_windows=1, dry_run=True
    )
    assert report.jsonl_path is None and report.parquet_path is None
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "raw").exists()
    assert len(_coverage(report)) == 1


def test_dry_run_is_repeatable(test_video: Path, tmp_path: Path) -> None:
    def manifest() -> list[tuple[str, int]]:
        return sorted(
            (str(p.relative_to(tmp_path)), p.stat().st_size)
            for p in tmp_path.rglob("*")
            if p.is_file()
        )

    extract_video(test_video, tmp_path, _profile(), backend=None, limit_windows=2, dry_run=True)
    first = manifest()
    extract_video(test_video, tmp_path, _profile(), backend=None, limit_windows=2, dry_run=True)
    assert manifest() == first
