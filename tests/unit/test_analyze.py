"""Tests for the deterministic analysis pass."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from harness.analyze import (
    AnalysisError,
    Loudness,
    MediaProbe,
    SceneCut,
    SilenceSpan,
    _policy_hash,
    _strip_log_prefix,
    build_records,
    detect_scene_cuts,
    detect_silences,
    measure_loudness,
    plan_coverage,
    probe_media,
    slugify,
)
from harness.config import AnalysisProfile, load_profile
from harness.records import RECORD_TYPES

_FIXTURES = Path(__file__).resolve().parent / "fixtures"

_EBUR128_STDERR = """
[Parsed_ebur128_0 @ 000001e8138660c0] t: 574.599977 I: -18.2 LUFS LRA: 8.8 LU TPK: 0.6 dBFS
Summary:

  Integrated loudness:
    I:         -18.2 LUFS
    Threshold: -29.0 LUFS

  Loudness range:
    LRA:         8.9 LU
    Threshold: -39.0 LUFS
    LRA low:   -23.4 LUFS
    LRA high:  -14.5 LUFS

  True peak:
    Peak:        0.6 dBFS
"""

_SILENCE_STDERR = """
[Parsed_silencedetect_0 @ 0000024944816140] silence_start: 0
[Parsed_silencedetect_0 @ 0000024944816140] silence_end: 0.744422 | silence_duration: 0.744422
[Parsed_silencedetect_0 @ 0000024944816140] silence_start: 5.987211
[Parsed_silencedetect_0 @ 0000024944816140] silence_end: 6.406689 | silence_duration: 0.419478
"""

_SCENE_STDOUT = """frame:0    pts:453453  pts_time:15.1151
lavfi.scene_score=1.000000
frame:1    pts:763763  pts_time:25.458767
lavfi.scene_score=0.419398
"""


def _completed(stdout: str = "", stderr: str = "", code: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["ffmpeg"], returncode=code, stdout=stdout, stderr=stderr
    )


def _probe() -> MediaProbe:
    return MediaProbe(
        duration_ms=574_996,
        frame_rate=30000 / 1001,
        width=640,
        height=360,
        video_timebase="1/30000",
        audio_timebase="1/44100",
        has_audio=True,
    )


# --------------------------------------------------------------------------
# Parsers
# --------------------------------------------------------------------------


def test_measure_loudness_parses_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "harness.analyze._run", lambda cmd: _completed(stderr=_EBUR128_STDERR)
    )
    result = measure_loudness(Path("x.mp4"))
    assert result.integrated_lufs == -18.2
    assert result.loudness_range_lu == 8.9
    assert result.true_peak_dbfs == 0.6
    assert "I:" in result.raw and "LRA:" in result.raw


def test_measure_loudness_rejects_unparseable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("harness.analyze._run", lambda cmd: _completed(stderr="no summary"))
    with pytest.raises(AnalysisError):
        measure_loudness(Path("x.mp4"))


def test_detect_silences_pairs_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "harness.analyze._run", lambda cmd: _completed(stderr=_SILENCE_STDERR)
    )
    spans = detect_silences(Path("x.mp4"), -32.0, 0.4)
    assert [(s.start_ms, s.end_ms) for s in spans] == [(0, 744), (5987, 6407)]
    assert all("@ 0x" not in s.raw for s in spans)


def test_detect_silences_ignores_unpaired_start(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = "[Parsed_silencedetect_0 @ 0x1] silence_start: 10.0\n"
    monkeypatch.setattr("harness.analyze._run", lambda cmd: _completed(stderr=stderr))
    assert detect_silences(Path("x.mp4"), -32.0, 0.4) == []


def test_detect_scene_cuts_parses_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("harness.analyze._run", lambda cmd: _completed(stdout=_SCENE_STDOUT))
    cuts = detect_scene_cuts(Path("x.mp4"), 0.4)
    assert [(c.at_ms, round(c.score, 3)) for c in cuts] == [(15115, 1.0), (25459, 0.419)]


def test_strip_log_prefix_removes_pointer() -> None:
    line = "[Parsed_silencedetect_0 @ 0000024944816140] silence_start: 0"
    assert _strip_log_prefix(line) == "silence_start: 0"


# --------------------------------------------------------------------------
# Coverage planner
# --------------------------------------------------------------------------


def test_plan_coverage_tiles_without_gaps() -> None:
    windows = plan_coverage(100_000, window_ms=25_000, overlap_ms=5_000)
    assert windows[0] == (0, 25_000)
    assert windows[-1][1] == 100_000
    for (_, prev_end), (next_start, _) in zip(windows, windows[1:], strict=False):
        assert next_start < prev_end  # overlap
        assert next_start > 0


def test_plan_coverage_short_clip_is_one_window() -> None:
    assert plan_coverage(10_000, window_ms=25_000, overlap_ms=5_000) == [(0, 10_000)]


def test_plan_coverage_rejects_bad_overlap() -> None:
    with pytest.raises(AnalysisError):
        plan_coverage(1_000, window_ms=20_000, overlap_ms=20_000)


def test_slugify() -> None:
    assert slugify("ds3 ep 1") == "ds3_ep_1"
    assert slugify("Here-Comes-the-SnapYT.App") == "here_comes_the_snapyt_app"


# --------------------------------------------------------------------------
# Record assembly
# --------------------------------------------------------------------------


def _build(
    profile: AnalysisProfile | None = None,
) -> tuple[list[tuple[str, object]], list[str]]:
    return build_records(
        path="videos/ds3 ep 3.mp4",
        digest="a" * 64,
        byte_length=47_625_638,
        probe=_probe(),
        loudness=Loudness(-13.3, 10.5, 1.8, "I: -13.3 LUFS; LRA: 10.5 LU; Peak: 1.8 dBFS"),
        silences=[SilenceSpan(2962, 3519, "silence_start: 2.961542 | silence_end: 3.519388")],
        cuts=[SceneCut(11745, 1.0, "pts_time:11.745067 | lavfi.scene_score=1.000000")],
        run_id="run_test",
        artifact_id="art_" + "a" * 12,
        video_id="ds3_ep_3",
        windows=[(0, 25_000), (20_000, 45_000)],
        profile=profile or load_profile(),
    )


def test_build_records_emits_expected_types() -> None:
    records, _ = _build()
    types = [record_type for record_type, _ in records]
    assert types == [
        "source_artifact",
        "reference_video",
        "analysis_run",
        "observation",
        "audio_event",
        "edit_event",
        "shot_continuity",
        "shot_continuity",
        "coverage_window",
        "coverage_window",
    ]


def test_build_records_never_interprets() -> None:
    records, _ = _build()
    types = {record_type for record_type, _ in records}
    assert types.isdisjoint({"comedy_beat", "gameplay_event", "character_state"})
    assert types <= set(RECORD_TYPES)


def test_build_records_provenance_is_e1_without_confidence() -> None:
    records, _ = _build()
    for record_type, model in records:
        if record_type in {"comedy_beat", "gameplay_event"}:
            continue
        data = model.model_dump()
        if "epistemic_level" in data:
            assert data["epistemic_level"] == "E1"
            assert data["confidence"] is None
            assert data["model_id"] is None
            assert data["verbatim_evidence"]


def test_build_records_source_id_matches_artifact() -> None:
    records, _ = _build()
    artifact_id = "art_" + "a" * 12
    for _, model in records:
        data = model.model_dump()
        if "source_id" in data:
            assert data["source_id"] == artifact_id


def test_loudness_is_an_observation_not_a_mix_action() -> None:
    records, _ = _build()
    obs = next(m for t, m in records if t == "observation").model_dump()
    assert obs["modality"] == "audio"
    assert obs["measured"] is True
    assert obs["media_start_ms"] == 0 and obs["media_end_ms"] == 574_996
    assert "-13.3" in obs["verbatim_evidence"]
    # no fabricated ducking/crossfade claims
    assert not any(t == "audio_mix_event" for t, _ in records)


def test_silence_is_audio_event_not_a_comedic_pause() -> None:
    records, _ = _build()
    event = next(m for t, m in records if t == "audio_event").model_dump()
    assert event["kind"] == "silence"
    assert event["media_start_ms"] == 2962
    assert event["media_end_ms"] == 3519


def test_cut_is_a_point_edit_with_tolerance() -> None:
    records, _ = _build()
    edit = next(m for t, m in records if t == "edit_event").model_dump()
    assert edit["edit_type"] == "cut"
    assert edit["output_is_point"] is True
    assert edit["output_start_ms"] == edit["output_end_ms"] == 11745
    assert edit["tolerance_ms"] == 33  # one frame at 29.97 fps
    assert edit["continuity"] == "uncertain"


def test_marginal_scene_score_is_unknown_not_cut() -> None:
    records, _ = build_records(
        path="v.mp4",
        digest="a" * 64,
        byte_length=1,
        probe=_probe(),
        loudness=None,
        silences=[],
        cuts=[SceneCut(5000, 0.45, "pts_time:5.0 | lavfi.scene_score=0.450000")],
        run_id="run_test",
        artifact_id="art_" + "a" * 12,
        video_id="v",
        windows=[],
        profile=load_profile(),
    )
    edit = next(m for t, m in records if t == "edit_event").model_dump()
    assert edit["edit_type"] == "unknown"


def test_build_records_is_deterministic() -> None:
    first, _ = _build()
    second, _ = _build()
    assert [t for t, _ in first] == [t for t, _ in second]
    assert [m.model_dump() for _, m in first] == [m.model_dump() for _, m in second]


def test_no_audio_skips_loudness_and_warns() -> None:
    records, warnings = build_records(
        path="v.mp4",
        digest="a" * 64,
        byte_length=1,
        probe=MediaProbe(1_000, 25.0, 640, 360, "1/25", None, has_audio=False),
        loudness=None,
        silences=[],
        cuts=[],
        run_id="run_test",
        artifact_id="art_" + "a" * 12,
        video_id="v",
        windows=[],
        profile=load_profile(),
    )
    assert not any(t == "observation" for t, _ in records)
    assert any("no audio stream" in w for w in warnings)


def test_coverage_windows_claim_only_exposed_modalities() -> None:
    records, _ = _build()
    windows = [m.model_dump() for t, m in records if t == "coverage_window"]
    assert windows and all(w["modalities"] == ["visual", "audio"] for w in windows)
    assert all("whole-file deterministic pass" in w["sampling_policy"] for w in windows)


def test_claim_ids_are_content_derived_not_index_based() -> None:
    # Same detection content -> same id, even if it moves position in the list.
    records_a, _ = _build()
    records_b, _ = _build()
    ids_a = {m.model_dump()["claim_id"] for t, m in records_a if t == "edit_event"}
    ids_b = {m.model_dump()["claim_id"] for t, m in records_b if t == "edit_event"}
    assert ids_a == ids_b
    assert all("cut_" in cid for cid in ids_a)


def test_policy_hash_is_stable(base_profile: AnalysisProfile) -> None:
    policy = base_profile.policy_string()
    assert _policy_hash(policy) == _policy_hash(policy)
    assert len(_policy_hash(policy)) == 16
    assert _policy_hash(policy) == "4549e2f18465579f"


def test_analysis_run_stamps_profile(base_profile: AnalysisProfile) -> None:
    records, _ = _build(base_profile)
    run = next(m for t, m in records if t == "analysis_run").model_dump()
    assert run["profile_id"] == "base"
    assert run["profile_version"] == "1.0.0"
    assert run["config_hash"] == base_profile.config_hash()
    assert len(run["config_hash"]) == 64


def test_ds3_profile_stamps_identity_and_game(ds3_profile: AnalysisProfile) -> None:
    records, _ = _build(ds3_profile)
    run = next(m for t, m in records if t == "analysis_run").model_dump()
    video = next(m for t, m in records if t == "reference_video").model_dump()
    assert run["profile_id"] == "ds3"
    assert run["config_hash"] == ds3_profile.config_hash()
    assert video["game"] == "Dark Souls III"
    # Thresholds are inherited unchanged, so classification does not move.
    edit = next(m for t, m in records if t == "edit_event").model_dump()
    assert edit["edit_type"] == "cut"


def test_build_records_matches_pre_refactor_golden() -> None:
    # The golden fixture was captured before the constants moved to config. The
    # only permitted difference is the three fields the run now stamps.
    records, _ = _build()
    actual = [{"record_type": t, "data": m.model_dump(mode="json")} for t, m in records]
    golden = [
        json.loads(line)
        for line in (_FIXTURES / "analyze_build_golden.jsonl").read_text("utf-8").splitlines()
    ]
    assert len(actual) == len(golden)
    added = {"profile_id", "profile_version", "config_hash"}
    for got, want in zip(actual, golden, strict=True):
        assert got["record_type"] == want["record_type"]
        got_data = dict(got["data"])
        if want["record_type"] == "analysis_run":
            for key in added:
                got_data.pop(key)
        assert got_data == want["data"]


# --------------------------------------------------------------------------
# Real media (skipped when the local videos are absent)
# --------------------------------------------------------------------------

_VIDEO = Path("videos/ds3 ep 3.mp4")


@pytest.mark.skipif(not _VIDEO.is_file(), reason="local reference video not present")
def test_probe_real_video() -> None:
    probe = probe_media(_VIDEO)
    assert probe.duration_ms == pytest.approx(564_361, abs=2)
    assert probe.width == 640 and probe.height == 360
    assert probe.has_audio
    assert probe.video_timebase == "1/30000"
