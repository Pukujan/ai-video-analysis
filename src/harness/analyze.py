"""Deterministic analysis pass: media file -> validated records.

This pass uses only ffprobe/ffmpeg — no model, no network — so everything it
emits is a raw-source record (E0) or a direct measurement (E1). It therefore
never produces ComedyBeat, GameplayEvent or CharacterState: those are
interpretations and would need a model_id and alternates that this pass cannot
supply. A detected low-volume span is an AudioEvent(silence) and nothing more;
the design docs forbid reading it as a comedic pause.

Idempotency: claim ids are derived from the media hash, the tool and the record
index, so rerunning over the same bytes reproduces the same ids. The run is
keyed by ``run_id`` and re-ingesting replaces that run's rows rather than
appending a duplicate.

The managed/ tree is never written to; the source manifest is read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from harness import __version__
from harness.records import parse_record
from harness.registry import sha256_file
from harness.vocab import AudioEventKind, ContinuityClass, EpistemicLevel, Modality

__all__ = [
    "AnalysisError",
    "AnalysisReport",
    "MediaProbe",
    "Loudness",
    "SilenceSpan",
    "analyze_video",
    "probe_media",
    "measure_loudness",
    "detect_silences",
    "detect_scene_cuts",
    "plan_coverage",
    "slugify",
]

_FFMPEG = "ffmpeg"
_FFPROBE = "ffprobe"
_FFMPEG_VERSION = "8.1.1"
_POLICY = "det-v1:ebur128=peak;silencedetect=-32dB/0.4s;scene>0.4"
_SILENCE_METHOD = f"ffmpeg {_FFMPEG_VERSION} silencedetect=noise=-32dB:d=0.4"
_DEFAULT_WINDOW_MS = 25_000
_DEFAULT_OVERLAP_MS = 5_000
_SCENE_THRESHOLD = 0.4
_CUT_SCORE_THRESHOLD = 0.6
_SILENCE_NOISE_DB = -32.0
_SILENCE_MIN_S = 0.4

_I_RE = re.compile(r"^\s*I:\s*(-?\d+(?:\.\d+)?)\s*LUFS\s*$", re.MULTILINE)
_LRA_RE = re.compile(r"^\s*LRA:\s*(-?\d+(?:\.\d+)?)\s*LU\s*$", re.MULTILINE)
_PEAK_RE = re.compile(r"^\s*Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS\s*$", re.MULTILINE)
_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_SILENCE_END_RE = re.compile(
    r"silence_end:\s*(-?\d+(?:\.\d+)?)\s*\|\s*silence_duration:\s*(-?\d+(?:\.\d+)?)"
)
_PTS_RE = re.compile(r"pts_time:\s*(\d+(?:\.\d+)?)")
_SCORE_RE = re.compile(r"lavfi\.scene_score=\s*(\d+(?:\.\d+)?)")
_LOG_PREFIX_RE = re.compile(r"^\[[^\]]*\]\s*")


def _strip_log_prefix(line: str) -> str:
    """Drop ffmpeg's ``[filter @ 0x...]`` prefix.

    The pointer in that prefix changes every run, so keeping it would make the
    recorded evidence non-reproducible; the measurement after it is stable.
    """
    return _LOG_PREFIX_RE.sub("", line).strip()


class AnalysisError(RuntimeError):
    """Raised when a required external tool is missing or fails."""


def slugify(name: str) -> str:
    """A stable id fragment from a filename stem."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", name.lower())).strip("_")


@dataclass(frozen=True, slots=True)
class MediaProbe:
    duration_ms: int
    frame_rate: float
    width: int
    height: int
    video_timebase: str
    audio_timebase: str | None
    has_audio: bool


@dataclass(frozen=True, slots=True)
class Loudness:
    integrated_lufs: float
    loudness_range_lu: float
    true_peak_dbfs: float
    raw: str


@dataclass(frozen=True, slots=True)
class SilenceSpan:
    start_ms: int
    end_ms: int
    raw: str


@dataclass(frozen=True, slots=True)
class SceneCut:
    at_ms: int
    score: float
    raw: str


@dataclass
class AnalysisReport:
    run_id: str
    video_id: str
    digest: str = ""
    records: list[tuple[str, BaseModel]] = field(default_factory=list)
    jsonl_path: Path | None = None
    duckdb_path: Path | None = None
    parquet_path: Path | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for record_type, _ in self.records:
            tally[record_type] = tally.get(record_type, 0) + 1
        return tally


def _require(tool: str) -> str:
    found = shutil.which(tool)
    if found is None:
        raise AnalysisError(f"{tool} not found on PATH")
    return found


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------
# External-tool measurements
# --------------------------------------------------------------------------


def probe_media(video: Path) -> MediaProbe:
    """ffprobe -> duration, frame rate, resolution and both timebases."""
    _require(_FFPROBE)
    proc = _run(
        [
            _FFPROBE,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video),
        ]
    )
    if proc.returncode != 0:
        raise AnalysisError(f"ffprobe failed for {video.name}: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    fmt = data.get("format", {})
    duration_ms = int(round(float(fmt.get("duration", 0.0)) * 1000))
    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"), None
    )
    audio_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None
    )
    if video_stream is None:
        raise AnalysisError(f"no video stream in {video.name}")
    frame_rate = float(Fraction(video_stream.get("r_frame_rate", "0/1")))
    return MediaProbe(
        duration_ms=duration_ms,
        frame_rate=frame_rate,
        width=int(video_stream.get("width", 0)),
        height=int(video_stream.get("height", 0)),
        video_timebase=video_stream.get("time_base", "1/1000"),
        audio_timebase=audio_stream.get("time_base") if audio_stream else None,
        has_audio=audio_stream is not None,
    )


def measure_loudness(video: Path) -> Loudness:
    """ffmpeg ebur128 (ITU-R BS.1770 / EBU R 128) -> I, LRA and true peak."""
    _require(_FFMPEG)
    proc = _run(
        [
            _FFMPEG,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vn",
            "-filter:a",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode != 0:
        raise AnalysisError(f"ebur128 failed for {video.name}: {proc.stderr.strip()[-400:]}")
    text = proc.stderr
    i_match = _I_RE.search(text)
    lra_match = _LRA_RE.search(text)
    peak_match = _PEAK_RE.search(text)
    if not (i_match and lra_match and peak_match):
        raise AnalysisError(f"could not parse ebur128 summary for {video.name}")
    summary = text[text.rfind("Summary:") :] if "Summary:" in text else text
    # Keep only the measurement block; the trailing "[out#0/...] ... speed="
    # line carries a per-run pointer and elapsed time.
    measured_lines: list[str] = []
    for line in summary.splitlines():
        if line.lstrip().startswith("["):
            break
        if line.strip():
            measured_lines.append(line.strip())
    verbatim = " ".join(measured_lines)
    return Loudness(
        integrated_lufs=float(i_match.group(1)),
        loudness_range_lu=float(lra_match.group(1)),
        true_peak_dbfs=float(peak_match.group(1)),
        raw=verbatim,
    )


def detect_silences(
    video: Path, noise_db: float = _SILENCE_NOISE_DB, min_s: float = _SILENCE_MIN_S
) -> list[SilenceSpan]:
    """ffmpeg silencedetect -> measured silence spans."""
    _require(_FFMPEG)
    proc = _run(
        [
            _FFMPEG,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-vn",
            "-filter:a",
            f"silencedetect=noise={noise_db}dB:d={min_s}",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode != 0:
        raise AnalysisError(f"silencedetect failed for {video.name}: {proc.stderr.strip()[-400:]}")
    spans: list[SilenceSpan] = []
    pending_start: tuple[int, str] | None = None
    for line in proc.stderr.splitlines():
        start = _SILENCE_START_RE.search(line)
        if start:
            pending_start = (int(round(float(start.group(1)) * 1000)), _strip_log_prefix(line))
            continue
        end = _SILENCE_END_RE.search(line)
        if end and pending_start is not None:
            end_ms = int(round(float(end.group(1)) * 1000))
            raw = f"{pending_start[1]} | {_strip_log_prefix(line)}"
            spans.append(SilenceSpan(pending_start[0], end_ms, raw))
            pending_start = None
    return spans


def detect_scene_cuts(video: Path, threshold: float = _SCENE_THRESHOLD) -> list[SceneCut]:
    """ffmpeg scene score -> candidate cut points with their scores.

    A scene-score peak is a visual discontinuity, not proof of an editorial cut:
    combat flashes, camera motion and menus also spike it. Callers must classify
    the result as uncertain. Scores are emitted to stdout via ``metadata=print``.
    """
    _require(_FFMPEG)
    proc = _run(
        [
            _FFMPEG,
            "-nostdin",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video),
            "-filter:v",
            f"select='gt(scene,{threshold})',metadata=print:file=-",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )
    if proc.returncode != 0:
        raise AnalysisError(f"scene detect failed for {video.name}: {proc.stderr.strip()[-400:]}")
    cuts: list[SceneCut] = []
    pending: tuple[int, str] | None = None
    for line in proc.stdout.splitlines():
        pts = _PTS_RE.search(line)
        if pts:
            pending = (int(round(float(pts.group(1)) * 1000)), line.strip())
            continue
        score = _SCORE_RE.search(line)
        if score and pending is not None:
            raw = f"{pending[1]} | {line.strip()}"
            cuts.append(SceneCut(pending[0], float(score.group(1)), raw))
            pending = None
    cuts.sort(key=lambda c: c.at_ms)
    return cuts


def plan_coverage(
    duration_ms: int, window_ms: int = _DEFAULT_WINDOW_MS, overlap_ms: int = _DEFAULT_OVERLAP_MS
) -> list[tuple[int, int]]:
    """Overlapping local windows covering ``[0, duration_ms)`` with no gaps."""
    if window_ms <= 0 or overlap_ms < 0 or overlap_ms >= window_ms:
        raise AnalysisError("window must exceed overlap, and overlap must be non-negative")
    step = window_ms - overlap_ms
    windows: list[tuple[int, int]] = []
    start = 0
    while start < duration_ms:
        end = min(start + window_ms, duration_ms)
        windows.append((start, end))
        if end >= duration_ms:
            break
        start += step
    return windows


# --------------------------------------------------------------------------
# Record assembly
# --------------------------------------------------------------------------


def _prov(
    claim_id: str,
    source_id: str,
    start_ms: int,
    end_ms: int,
    evidence: str,
    method: str,
    level: EpistemicLevel,
    run_id: str,
    is_point: bool = False,
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "source_id": source_id,
        "media_start_ms": start_ms,
        "media_end_ms": end_ms,
        "source_kind": "video",
        "verbatim_evidence": evidence,
        "extraction_method": method,
        "model_id": None,
        "run_id": run_id,
        "confidence": None,
        "epistemic_level": level.value,
        "review_status": "unreviewed",
        "supersedes_claim_id": None,
        "alternate_hypotheses": [],
        "is_point": is_point,
    }


def _anchor(start_ms: int, end_ms: int, evidence: str) -> str:
    """A stable claim-id suffix from what the claim asserts, not its position.

    Deriving the id from the content means inserting or dropping an earlier
    detection never renumbers later claims, so an id keeps pointing at the same
    observed moment across reruns and across detector changes.
    """
    seed = f"{start_ms}:{end_ms}:{evidence}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]


def _emit(
    records: list[tuple[str, BaseModel]], record_type: str, data: dict[str, Any]
) -> None:
    records.append((record_type, parse_record(record_type, data)))


def build_records(
    path: str,
    digest: str,
    byte_length: int,
    probe: MediaProbe,
    loudness: Loudness | None,
    silences: list[SilenceSpan],
    cuts: list[SceneCut],
    run_id: str,
    artifact_id: str,
    video_id: str,
    windows: list[tuple[int, int]],
) -> tuple[list[tuple[str, BaseModel]], list[str]]:
    records: list[tuple[str, BaseModel]] = []
    warnings: list[str] = []

    _emit(
        records,
        "source_artifact",
        {
            "artifact_id": artifact_id,
            "kind": "video",
            "path": path,
            "sha256": digest,
            "byte_length": byte_length,
            "provenance_note": "user-supplied reference VOD, registered read-only",
        },
    )
    _emit(
        records,
        "reference_video",
        {
            "video_id": video_id,
            "source_artifact_id": artifact_id,
            "duration_ms": probe.duration_ms,
            "frame_rate": probe.frame_rate,
            "width": probe.width,
            "height": probe.height,
            "video_timebase": probe.video_timebase,
            "audio_timebase": probe.audio_timebase,
        },
    )
    _emit(
        records,
        "analysis_run",
        {
            "run_id": run_id,
            "provider": _FFMPEG,
            "model_id": f"{_FFMPEG}-{_FFMPEG_VERSION}",
            "prompt_hash": _policy_hash(),
            "code_version": __version__,
            "frame_sample_policy": "none; deterministic signal + frame-difference analysis",
        },
    )

    if loudness is not None:
        # ebur128 measures the whole stream's loudness; it is not a mix action,
        # so it is an Observation, and it asserts nothing about ducking,
        # crossfades or interruption that it did not measure.
        _emit(
            records,
            "observation",
            {
                **_prov(
                    f"c_{video_id}_loudness",
                    artifact_id,
                    0,
                    probe.duration_ms,
                    loudness.raw,
                    f"ffmpeg {_FFMPEG_VERSION} ebur128=peak=true (ITU-R BS.1770-5 / EBU R 128)",
                    EpistemicLevel.E1_OBSERVATION,
                    run_id,
                ),
                "modality": Modality.AUDIO.value,
                "native_location": "audio stream 0 (whole stream)",
                "measured": True,
                "certainty": None,
            },
        )
    else:
        warnings.append("no audio stream; loudness not measured")

    for span in silences:
        _emit(
            records,
            "audio_event",
            {
                **_prov(
                    f"c_{video_id}_silence_{_anchor(span.start_ms, span.end_ms, span.raw)}",
                    artifact_id,
                    span.start_ms,
                    span.end_ms,
                    span.raw,
                    _SILENCE_METHOD,
                    EpistemicLevel.E1_OBSERVATION,
                    run_id,
                ),
                "stream": "audio",
                "kind": AudioEventKind.SILENCE.value,
                "confidence": None,
            },
        )

    frame_ms = max(1, int(round(1000.0 / probe.frame_rate))) if probe.frame_rate else 33
    for cut in cuts:
        # A high score is very likely a hard editorial cut; a marginal one may
        # be camera motion or a game transition, so it stays "unknown".
        edit_type = "cut" if cut.score >= _CUT_SCORE_THRESHOLD else "unknown"
        _emit(
            records,
            "edit_event",
            {
                **_prov(
                    f"c_{video_id}_cut_{_anchor(cut.at_ms, cut.at_ms, cut.raw)}",
                    artifact_id,
                    cut.at_ms,
                    cut.at_ms,
                    cut.raw,
                    f"ffmpeg {_FFMPEG_VERSION} select gt(scene,{_SCENE_THRESHOLD})",
                    EpistemicLevel.E1_OBSERVATION,
                    run_id,
                    is_point=True,
                ),
                "edit_type": edit_type,
                "output_start_ms": cut.at_ms,
                "output_end_ms": cut.at_ms,
                "output_is_point": True,
                "source_start_ms": None,
                "source_end_ms": None,
                "continuity": ContinuityClass.UNCERTAIN.value,
                "detection_method": (
                    f"ffmpeg {_FFMPEG_VERSION} scene score {cut.score:.3f} "
                    f"> {_SCENE_THRESHOLD}; cut threshold {_CUT_SCORE_THRESHOLD}"
                ),
                "visual_effect": None,
                "tolerance_ms": frame_ms,
            },
        )

    boundaries = [0] + [c.at_ms for c in cuts] + [probe.duration_ms]
    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        if end <= start:
            continue
        evidence = f"span between scene-score boundaries {start}ms..{end}ms"
        _emit(
            records,
            "shot_continuity",
            {
                **_prov(
                    f"c_{video_id}_span_{_anchor(start, end, evidence)}",
                    artifact_id,
                    start,
                    end,
                    evidence,
                    f"ffmpeg {_FFMPEG_VERSION} scene-score segmentation",
                    EpistemicLevel.E1_OBSERVATION,
                    run_id,
                ),
                "continuity": ContinuityClass.UNCERTAIN.value,
                "effects": [],
                "camera_vs_editing_ambiguous": True,
            },
        )

    for index, (start, end) in enumerate(windows):
        _emit(
            records,
            "coverage_window",
            {
                "window_id": f"w_{video_id}_{index:04d}",
                "video_id": video_id,
                "start_ms": start,
                "end_ms": end,
                # Only the modalities this deterministic pass actually exposed.
                # Speech and comedy need a model and are not claimed here.
                "modalities": [Modality.VISUAL.value, Modality.AUDIO.value],
                "sampling_policy": (
                    f"{_DEFAULT_WINDOW_MS}ms nominal, {_DEFAULT_OVERLAP_MS}ms overlap; "
                    "window covered by the whole-file deterministic pass, "
                    "not a window-local model call"
                ),
                "run_id": run_id,
                "status": "succeeded",
                "failure_reason": None,
            },
        )

    return records, warnings


def _policy_hash() -> str:
    return hashlib.sha256(_POLICY.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Orchestration and output
# --------------------------------------------------------------------------


def _write_jsonl(path: Path, records: Iterable[tuple[str, BaseModel]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record_type, model in records:
            handle.write(
                json.dumps({"record_type": record_type, "data": model.model_dump(mode="json")})
                + "\n"
            )


def _write_store(duckdb_path: Path, report: AnalysisReport) -> None:
    import duckdb

    duckdb_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(duckdb_path))
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                run_id VARCHAR,
                video_id VARCHAR,
                record_type VARCHAR,
                record_id VARCHAR,
                start_ms BIGINT,
                end_ms BIGINT,
                epistemic_level VARCHAR,
                payload JSON
            )
            """
        )
        con.execute("DELETE FROM records WHERE run_id = ?", [report.run_id])
        rows = []
        for record_type, model in report.records:
            data = model.model_dump(mode="json")
            record_id = (
                data.get("claim_id")
                or data.get("artifact_id")
                or data.get("video_id")
                or data.get("window_id")
                or data.get("run_id")
                or ""
            )
            start = data.get("media_start_ms", data.get("start_ms", data.get("output_start_ms")))
            end = data.get("media_end_ms", data.get("end_ms", data.get("output_end_ms")))
            rows.append(
                (
                    report.run_id,
                    report.video_id,
                    record_type,
                    record_id,
                    start,
                    end,
                    data.get("epistemic_level"),
                    json.dumps(data),
                )
            )
        con.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    finally:
        con.close()


def _write_parquet(duckdb_path: Path, parquet_path: Path, run_id: str) -> None:
    import duckdb

    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(duckdb_path))
    try:
        con.execute(
            f"COPY (SELECT * FROM records WHERE run_id = '{run_id}') "
            f"TO '{parquet_path.as_posix()}' (FORMAT PARQUET)"
        )
    finally:
        con.close()


def manifest_cross_check(video: Path, digest: str, manifest_path: Path) -> str | None:
    """Report-only: does this file match a manifest entry's recorded hash/size?

    The manifest is never rewritten. This only names the registered source the
    bytes correspond to, so a run can say which reference it analyzed.
    """
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    size = video.stat().st_size
    for entry in manifest.get("raw_sources", []):
        if entry.get("sha256") == digest:
            return f"matches manifest entry {entry.get('id')!r} (sha256 exact)"
        if entry.get("bytes") == size and entry.get("path") is None:
            return (
                f"size matches manifest entry {entry.get('id')!r} "
                f"but sha256 differs (recorded {entry.get('sha256', '')[:12]}...)"
            )
    return None


def analyze_video(video: Path, out_root: Path) -> AnalysisReport:
    """Run the deterministic pass over one video and persist its records."""
    if not video.is_file():
        raise AnalysisError(f"no such file: {video}")
    digest = sha256_file(video)
    video_id = slugify(video.stem)
    artifact_id = f"art_{digest[:12]}"
    run_id = f"run_{digest[:12]}_det_v1"

    probe = probe_media(video)
    loudness = measure_loudness(video) if probe.has_audio else None
    silences = detect_silences(video) if probe.has_audio else []
    cuts = detect_scene_cuts(video)
    windows = plan_coverage(probe.duration_ms)

    records, warnings = build_records(
        video.as_posix(),
        digest,
        video.stat().st_size,
        probe,
        loudness,
        silences,
        cuts,
        run_id,
        artifact_id,
        video_id,
        windows,
    )

    report = AnalysisReport(
        run_id=run_id, video_id=video_id, digest=digest, records=records, warnings=warnings
    )
    report.jsonl_path = out_root / "raw" / "model_runs" / f"{run_id}.jsonl"
    report.duckdb_path = out_root / "data" / "analysis.duckdb"
    report.parquet_path = out_root / "exports" / f"{video_id}.parquet"

    _write_jsonl(report.jsonl_path, records)
    _write_store(report.duckdb_path, report)
    _write_parquet(report.duckdb_path, report.parquet_path, run_id)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m harness.analyze",
        description="Deterministic analysis pass: video -> validated records.",
    )
    parser.add_argument("--video", type=Path, action="append", required=True, dest="videos")
    parser.add_argument("--out-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("managed/epistemic/SOURCES.json"),
        help="source manifest for a report-only identity cross-check",
    )
    args = parser.parse_args(argv)

    exit_code = 0
    for video in args.videos:
        try:
            report = analyze_video(video, args.out_root)
        except AnalysisError as exc:
            print(f"FAILED {video}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        counts = ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items()))
        print(f"{report.video_id}  run={report.run_id}")
        check = manifest_cross_check(video, report.digest, args.manifest)
        if check:
            print(f"  source:  {check}")
        print(f"  records: {counts}")
        print(f"  jsonl:   {report.jsonl_path}")
        print(f"  duckdb:  {report.duckdb_path}")
        print(f"  parquet: {report.parquet_path}")
        for warning in report.warnings:
            print(f"  warn:    {warning}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
