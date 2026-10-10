"""Live smoke test: one real window through InferHub. Marked ``live``.

Run it explicitly — it is excluded from the default run::

    .venv/Scripts/python.exe -m pytest -m live tests/live

Asserted on *shape* only, never on comedic judgment: whether a beat is funny is
the human's call, recorded later as a ``review``. The provider's content gate is
probabilistic, so a gate-tripped window is a passing outcome here as long as it
is recorded as terminal-and-failed with the provider's reason — that is exactly
the stability guarantee the pass makes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.backend import BackendError, get_backend
from harness.config import load_profile
from harness.extract import extract_video

pytestmark = pytest.mark.live

_VIDEO = Path(__file__).resolve().parents[2] / "videos" / "ds3 ep 3.mp4"


@pytest.mark.skipif(not _VIDEO.is_file(), reason="reference video is not present")
def test_one_window_through_inferhub(tmp_path: Path) -> None:
    try:
        backend = get_backend("inferhub")
    except BackendError as exc:
        pytest.skip(f"no InferHub credentials available: {exc}")

    report = extract_video(
        _VIDEO, tmp_path, load_profile("ds3"), backend=backend, limit_windows=1
    )

    windows = [m.model_dump() for t, m in report.records if t == "coverage_window"]
    assert len(windows) == 1
    window = windows[0]
    assert window["status"] in {"succeeded", "failed"}

    if window["status"] == "failed":
        assert window["failure_reason"].startswith("content_gate:")
        return

    utterances = [m.model_dump() for t, m in report.records if t == "utterance"]
    assert utterances, "a succeeded window carries utterances"
    assert all(u["raw_text"].strip() for u in utterances)

    for beat in (m.model_dump() for t, m in report.records if t == "comedy_beat"):
        assert beat["epistemic_level"] == "E2"
        assert beat["model_id"]
        assert beat["alternate_hypotheses"], "an E2 claim must carry alternate readings"
