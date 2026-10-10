"""Tests for the source registry, run against the real committed manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.registry import SourceRegistry, sha256_file

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def registry() -> SourceRegistry:
    return SourceRegistry(REPO_ROOT)


class TestAgainstRealManifest:
    def test_committed_sources_verify(self, registry: SourceRegistry) -> None:
        report = registry.verify()
        mismatches = [c.source_id for c in report.mismatches]
        assert mismatches == [], f"sources changed on disk: {mismatches}"

    def test_chat_export_hash_matches(self, registry: SourceRegistry) -> None:
        report = registry.verify()
        chat = next(c for c in report.checks if c.source_id == "chat-export-20261009")
        assert chat.status == "verified"

    def test_reference_video_is_registered_but_absent(self, registry: SourceRegistry) -> None:
        report = registry.verify()
        video = next(c for c in report.checks if c.source_id == "reference01-video")
        assert video.status == "absent_no_path"
        assert video.is_absent
        assert video.ok

    def test_transcript_without_hash_is_flagged_not_failed(
        self, registry: SourceRegistry
    ) -> None:
        report = registry.verify()
        transcript = next(c for c in report.checks if c.source_id == "reference01-transcript")
        assert transcript.status == "unhashed"
        assert transcript.ok
        assert report.suggested_manifest_additions()["reference01-transcript"]

    def test_historical_analyses_all_verify(self, registry: SourceRegistry) -> None:
        report = registry.verify()
        analyses = [c for c in report.checks if c.source_id.startswith("analysis:")]
        assert len(analyses) == 6
        assert all(c.status == "verified" for c in analyses)


class TestTamperDetection:
    def test_mismatch_is_reported(self, tmp_path: Path) -> None:
        (tmp_path / "managed" / "epistemic").mkdir(parents=True)
        payload = tmp_path / "artifact.txt"
        payload.write_text("original", encoding="utf-8")
        manifest = {
            "raw_sources": [
                {
                    "id": "tampered",
                    "path": "artifact.txt",
                    "sha256": "0" * 64,
                }
            ]
        }
        (tmp_path / "managed" / "epistemic" / "SOURCES.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        report = SourceRegistry(tmp_path).verify()
        assert not report.ok
        assert report.checks[0].status == "mismatch"
        assert report.mismatches

    def test_correct_hash_verifies(self, tmp_path: Path) -> None:
        (tmp_path / "managed" / "epistemic").mkdir(parents=True)
        payload = tmp_path / "artifact.txt"
        payload.write_text("original", encoding="utf-8")
        manifest = {
            "raw_sources": [
                {
                    "id": "good",
                    "path": "artifact.txt",
                    "sha256": sha256_file(payload),
                }
            ]
        }
        (tmp_path / "managed" / "epistemic" / "SOURCES.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        report = SourceRegistry(tmp_path).verify()
        assert report.ok
        assert report.checks[0].status == "verified"

    def test_missing_file_is_absent_not_a_crash(self, tmp_path: Path) -> None:
        (tmp_path / "managed" / "epistemic").mkdir(parents=True)
        manifest = {
            "raw_sources": [
                {"id": "gone", "path": "nope.txt", "sha256": "a" * 64}
            ]
        }
        (tmp_path / "managed" / "epistemic" / "SOURCES.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        report = SourceRegistry(tmp_path).verify()
        assert report.checks[0].status == "absent_missing_file"
        assert not report.checks[0].ok
