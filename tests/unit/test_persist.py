"""Tests for the shared output plumbing."""

from __future__ import annotations

import json
from pathlib import Path

from harness.persist import write_jsonl, write_parquet, write_store
from harness.records import parse_record

_RECORDS = [
    ("source_artifact", parse_record("source_artifact", {
        "artifact_id": "art_1",
        "kind": "video",
        "provenance_note": "test",
    })),
    ("analysis_run", parse_record("analysis_run", {
        "run_id": "run_x",
        "provider": "deterministic",
        "model_id": "ffmpeg",
        "prompt_hash": "p",
        "code_version": "0.1.0",
        "frame_sample_policy": "none",
    })),
]


def test_write_jsonl_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "run.jsonl"
    write_jsonl(path, _RECORDS)
    lines = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    assert [row["record_type"] for row in lines] == ["source_artifact", "analysis_run"]
    assert lines[0]["data"]["artifact_id"] == "art_1"


def test_write_store_is_idempotent_per_run(tmp_path: Path) -> None:
    db = tmp_path / "data" / "analysis.duckdb"
    write_store(db, "run_a", "vid", _RECORDS)
    write_store(db, "run_a", "vid", _RECORDS)  # same run again
    import duckdb

    con = duckdb.connect(str(db))
    try:
        count = con.execute("SELECT count(*) FROM records WHERE run_id = 'run_a'").fetchone()[0]
    finally:
        con.close()
    assert count == len(_RECORDS)


def test_write_store_keeps_other_runs(tmp_path: Path) -> None:
    db = tmp_path / "analysis.duckdb"
    write_store(db, "run_det", "vid", _RECORDS)
    write_store(db, "run_ex", "vid", _RECORDS)
    write_store(db, "run_ex", "vid", _RECORDS)  # rerun the second only
    import duckdb

    con = duckdb.connect(str(db))
    try:
        det = con.execute("SELECT count(*) FROM records WHERE run_id = 'run_det'").fetchone()[0]
        ex = con.execute("SELECT count(*) FROM records WHERE run_id = 'run_ex'").fetchone()[0]
    finally:
        con.close()
    assert det == len(_RECORDS)
    assert ex == len(_RECORDS)


def test_write_parquet_exports_one_run(tmp_path: Path) -> None:
    db = tmp_path / "analysis.duckdb"
    out = tmp_path / "exports" / "vid.parquet"
    write_store(db, "run_a", "vid", _RECORDS)
    write_parquet(db, out, "run_a")
    assert out.is_file() and out.stat().st_size > 0
