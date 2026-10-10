"""Output plumbing shared by every analysis pass.

The deterministic pass (:mod:`harness.analyze`) and the model-backed
extraction pass (:mod:`harness.extract`) write the same three artifacts into
the same working tree — a per-run JSONL, the DuckDB store, and a per-video
Parquet export — so the writers live here once rather than in either pass.

Idempotency is the store's contract: a run's rows are keyed by ``run_id`` and
re-ingesting a run replaces exactly that run's rows. Because the two passes use
distinct run-id namespaces (``det_v1`` vs ``ex_<profile>``), a rerun of one can
never delete the other's rows.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel

__all__ = ["write_jsonl", "write_parquet", "write_store"]

_RecordRows = Iterable[tuple[str, BaseModel]]


def write_jsonl(path: Path, records: _RecordRows) -> None:
    """Write one ``{"record_type", "data"}`` object per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record_type, model in records:
            handle.write(
                json.dumps({"record_type": record_type, "data": model.model_dump(mode="json")})
                + "\n"
            )


def write_store(
    duckdb_path: Path, run_id: str, video_id: str, records: _RecordRows
) -> None:
    """Replace ``run_id``'s rows in the shared store, then insert this run's.

    The ``DELETE`` is scoped to ``run_id`` so a rerun is idempotent and never
    disturbs another run's rows.
    """
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
        con.execute("DELETE FROM records WHERE run_id = ?", [run_id])
        rows = []
        for record_type, model in records:
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
                    run_id,
                    video_id,
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


def write_parquet(duckdb_path: Path, parquet_path: Path, run_id: str) -> None:
    """Export one run's rows to Parquet."""
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
