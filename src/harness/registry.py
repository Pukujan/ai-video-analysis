"""Immutable source registry.

Reads ``managed/epistemic/SOURCES.json`` read-only and verifies the recorded
sha256 of every entry that has both a path and a hash.

The recorded hashes are **repository** hashes: the bytes git stores, not the
bytes the working tree happens to hold. The two differ on Windows, where
``core.autocrlf=true`` rewrites line endings on checkout, so the working tree
is CRLF while the blob is LF. The chat export is the reverse case — committed
with CRLF deliberately, to stay byte-identical to what the user supplied. So a
single normalization rule cannot serve both; the only correct reference is the
committed blob. Verification therefore hashes ``git cat-file blob`` output and
falls back to the working-tree file only when the path is not in the index.

Entries registered without a path (the 46 MB reference video) are reported as
absent rather than fabricated. Entries without a hash are flagged with the
computed suggestion; the manifest is never rewritten in place.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "ArtifactCheck",
    "RegistryReport",
    "SourceRegistry",
    "sha256_bytes",
    "sha256_file",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class ArtifactCheck:
    """The verification result for one manifest entry."""

    source_id: str
    path: str | None
    declared_sha256: str | None
    computed_sha256: str | None
    exists: bool
    source: str = "worktree"

    @property
    def status(self) -> str:
        if self.path is None:
            return "absent_no_path"
        if not self.exists:
            return "absent_missing_file"
        if self.declared_sha256 is None:
            return "unhashed"
        if self.computed_sha256 == self.declared_sha256:
            return "verified"
        return "mismatch"

    @property
    def ok(self) -> bool:
        return self.status in {"verified", "absent_no_path", "unhashed"}

    @property
    def is_absent(self) -> bool:
        return self.path is None or not self.exists


@dataclass
class RegistryReport:
    checks: list[ArtifactCheck] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def mismatches(self) -> list[ArtifactCheck]:
        return [c for c in self.checks if c.status == "mismatch"]

    def suggested_manifest_additions(self) -> dict[str, str]:
        """Computed hashes for entries the manifest does not yet record."""
        return {
            c.source_id: c.computed_sha256
            for c in self.checks
            if c.status == "unhashed" and c.computed_sha256
        }


class SourceRegistry:
    """Loads the source manifest and verifies it against committed bytes."""

    def __init__(self, repo_root: Path, manifest_path: Path | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.manifest_path = (
            manifest_path.resolve()
            if manifest_path is not None
            else self.repo_root / "managed" / "epistemic" / "SOURCES.json"
        )

    def load_manifest(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(
            self.manifest_path.read_text(encoding="utf-8-sig")
        )
        return loaded

    def verify(self) -> RegistryReport:
        manifest = self.load_manifest()
        report = RegistryReport()
        for entry in manifest.get("raw_sources", []):
            report.checks.append(self._check(entry))
        for entry in manifest.get("historical_analyses", []):
            report.checks.append(self._check(entry, source_id_prefix="analysis"))
        for check in report.checks:
            if check.status == "unhashed":
                report.warnings.append(
                    f"{check.source_id}: manifest records no sha256; "
                    f"computed {check.computed_sha256} (not written back)"
                )
            elif check.status == "mismatch":
                report.warnings.append(
                    f"{check.source_id}: declared {check.declared_sha256} but "
                    f"committed bytes hash to {check.computed_sha256}"
                )
        return report

    def _check(self, entry: dict[str, Any], source_id_prefix: str = "") -> ArtifactCheck:
        source_id = entry.get("id") or f"{source_id_prefix}:{entry.get('path')}"
        raw_path = entry.get("path")
        declared = entry.get("sha256")
        if raw_path is None:
            return ArtifactCheck(source_id, None, declared, None, False)

        committed = self._committed_bytes(raw_path)
        if committed is not None:
            return ArtifactCheck(
                source_id, raw_path, declared, sha256_bytes(committed), True, "blob"
            )

        path = self.repo_root / raw_path
        if not path.is_file():
            return ArtifactCheck(source_id, raw_path, declared, None, False)
        return ArtifactCheck(
            source_id, raw_path, declared, sha256_file(path), True, "worktree"
        )

    def _committed_bytes(self, rel_path: str) -> bytes | None:
        """Bytes git has committed at HEAD, or None when unavailable.

        This is the canonical artifact the manifest describes. Returns None
        outside a repository, for an untracked path, or when git is missing.
        """
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.repo_root), "cat-file", "blob", f"HEAD:{rel_path}"],
                capture_output=True,
                check=False,
            )
        except OSError:
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout
