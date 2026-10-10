"""The model-backed extraction pass: coverage windows -> derived records.

The deterministic pass (:mod:`harness.analyze`) measures the media and emits
substrate/E1 records. This pass runs after it, consumes its coverage windows,
and emits the claims that need a model or an interpretation: utterances, word
alignments, evidence spans, comedy beats, vocal delivery and response
decisions.

Run ids live in their own namespace (``run_<digest>_ex_<profile>``), distinct
from the deterministic ``run_<digest>_det_v1``, so both passes for one video
coexist in the store and a rerun of either replaces only its own rows.

The pass does not promise byte-identical reruns the way the deterministic pass
does. The provider's content gate is probabilistic — the identical profane
window is sometimes refused — so the guarantee here is *stability*: a gate trip
is retried, and a window that finally fails is recorded as failed with the
provider's reason rather than silently dropped.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from harness.analyze import (
    AnalysisError,
    plan_coverage,
    probe_media,
    slugify,
)
from harness.backend import Backend, BackendError, GateTripped, get_backend
from harness.clips import extract_window
from harness.config import DEFAULT_CONFIG_DIR, AnalysisProfile, ConfigError, load_profile
from harness.lens import (
    DeliveryLens,
    InterpretationLens,
    LensContext,
    TranscriptLens,
)
from harness.persist import write_jsonl, write_parquet, write_store
from harness.records import RecordError, parse_record
from harness.registry import sha256_file

__all__ = ["ExtractionReport", "extract_video", "main"]

_MODEL = "ali/qwen3.8-omni-flash"
_POLICY = "model-backed extraction pass"

# Supplied transcripts are keyed by video digest, not by filename: a transcript
# asserts the verbatim words of those exact bytes, so a re-encode or re-cut must
# not inherit them — it falls back to ASR instead. Only the reference episode
# (``videos/ds3 ep 3.mp4``) has one; ep1/ep2 are transcribed by the model.
_REFERENCE01_DIGEST = "3c06c4761b4513f243e66d9dd24741f384b500a09bb8e235ade9e3423c6f2726"
_SUPPLIED_TRANSCRIPTS = {
    _REFERENCE01_DIGEST: (
        Path(__file__).resolve().parents[2]
        / "managed"
        / "sources"
        / "reference-01"
        / "user-provided-timestamped-transcript.txt"
    ),
}


@dataclass
class ExtractionReport:
    run_id: str
    video_id: str
    digest: str = ""
    profile_id: str = ""
    profile_version: str = ""
    config_hash: str = ""
    records: list[tuple[str, BaseModel]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    jsonl_path: Path | None = None
    duckdb_path: Path | None = None
    parquet_path: Path | None = None

    @property
    def counts(self) -> dict[str, int]:
        tally: dict[str, int] = {}
        for record_type, _ in self.records:
            tally[record_type] = tally.get(record_type, 0) + 1
        return tally


def _coverage_record(
    ctx: LensContext,
    window: tuple[int, int],
    has_audio: bool,
    status: str,
    failure_reason: str | None,
) -> tuple[str, BaseModel]:
    modalities = ["visual", "audio"] if has_audio else ["visual"]
    return (
        "coverage_window",
        parse_record(
            "coverage_window",
            {
                "window_id": f"win_{ctx.video_id}_{window[0]}_{window[1]}",
                "video_id": ctx.video_id,
                "start_ms": window[0],
                "end_ms": window[1],
                "modalities": modalities,
                "sampling_policy": _POLICY,
                "run_id": ctx.run_id,
                "status": status,
                "failure_reason": failure_reason,
            },
        ),
    )


def extract_video(
    video: Path,
    out_root: Path,
    profile: AnalysisProfile,
    backend: Backend | None = None,
    limit_windows: int | None = None,
    dry_run: bool = False,
) -> ExtractionReport:
    """Run the extraction pass over one video."""
    if not video.is_file():
        raise AnalysisError(f"no such file: {video}")
    digest = sha256_file(video)
    video_id = slugify(video.stem)
    artifact_id = f"art_{digest[:12]}"
    run_id = f"run_{digest[:12]}_ex_{profile.profile.id}"

    if dry_run:
        backend = None  # a dry run is network-free by construction

    probe = probe_media(video)
    windows = plan_coverage(
        probe.duration_ms, profile.windowing.window_ms, profile.windowing.overlap_ms
    )
    if limit_windows is not None:
        windows = windows[:limit_windows]

    ctx = LensContext(video_id, artifact_id, run_id, profile, probe.frame_rate)
    transcript = TranscriptLens(_SUPPLIED_TRANSCRIPTS.get(digest), _MODEL)
    delivery = DeliveryLens()
    interpretation = InterpretationLens(_MODEL)

    report = ExtractionReport(
        run_id=run_id,
        video_id=video_id,
        digest=digest,
        profile_id=profile.profile.id,
        profile_version=profile.profile.version,
        config_hash=profile.config_hash(),
    )
    if transcript.mode == "asr":
        report.warnings.append(
            f"no supplied transcript for {digest[:12]}; windows are transcribed by ASR"
        )
    clip_dir = out_root / "clips" / video_id

    for window in windows:
        media = extract_window(
            video, window[0], window[1], digest, clip_dir, has_audio=probe.has_audio
        )
        status, reason = "succeeded", None
        try:
            utterance_records = transcript.run(window, media, ctx, (), backend)
            utterances = tuple(m for t, m in utterance_records if t == "utterance")
            report.records.extend(utterance_records)
            report.records.extend(delivery.run(window, media, ctx, utterances, backend))
            if dry_run:
                interpretation.build(window, media, utterances)
            else:
                report.records.extend(
                    interpretation.run(window, media, ctx, utterances, backend)
                )
        except GateTripped as exc:
            status, reason = "failed", f"content_gate: {exc.reason[:200]}"
            report.failures.append(f"{window}: {reason}")
        except RecordError as exc:
            status, reason = "failed", f"schema_rejected: {exc}"[:300]
            report.failures.append(f"{window}: {reason}")
        except BackendError as exc:
            status, reason = "failed", f"extraction_error: {exc}"[:300]
            report.failures.append(f"{window}: {reason}")
        report.records.append(_coverage_record(ctx, window, probe.has_audio, status, reason))

    if dry_run:
        return report

    report.jsonl_path = out_root / "raw" / "model_runs" / f"{run_id}.jsonl"
    report.duckdb_path = out_root / "data" / "analysis.duckdb"
    report.parquet_path = out_root / "exports" / f"{video_id}_ex.parquet"
    write_jsonl(report.jsonl_path, report.records)
    write_store(report.duckdb_path, run_id, video_id, report.records)
    write_parquet(report.duckdb_path, report.parquet_path, run_id)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m harness.extract",
        description="Model-backed extraction pass: coverage windows -> records.",
    )
    parser.add_argument("--video", type=Path, action="append", required=True, dest="videos")
    parser.add_argument("--out-root", type=Path, default=Path.cwd())
    parser.add_argument("--profile", default=None, help="profile id under config/profiles/")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--provider", default="inferhub")
    parser.add_argument("--limit-windows", type=int, default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="cut clips and build prompts without any model call",
    )
    args = parser.parse_args(argv)

    try:
        profile = load_profile(args.profile, args.config_dir)
    except ConfigError as exc:
        print(f"FAILED config: {exc}", file=sys.stderr)
        return 1

    backend: Backend | None = None
    if not args.dry_run:
        try:
            backend = get_backend(args.provider)
        except BackendError as exc:
            print(f"FAILED backend: {exc}", file=sys.stderr)
            return 1

    config_tag = profile.config_hash()[:12]
    print(f"profile: {profile.profile.id} v{profile.profile.version} ({config_tag})")
    if args.dry_run:
        print("dry run: no model calls, nothing persisted")

    exit_code = 0
    for video in args.videos:
        try:
            report = extract_video(
                video,
                args.out_root,
                profile,
                backend=backend,
                limit_windows=args.limit_windows,
                dry_run=args.dry_run,
            )
        except AnalysisError as exc:
            print(f"FAILED {video}: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        counts = ", ".join(f"{k}={v}" for k, v in sorted(report.counts.items()))
        print(f"{report.video_id}  run={report.run_id}")
        print(f"  records: {counts}")
        for warning in report.warnings:
            print(f"  warning: {warning}")
        if report.failures:
            for failure in report.failures:
                print(f"  failed:  {failure}")
        if report.jsonl_path is not None:
            print(f"  jsonl:   {report.jsonl_path}")
            print(f"  duckdb:  {report.duckdb_path}")
            print(f"  parquet: {report.parquet_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
