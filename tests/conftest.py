"""Shared fixtures for the harness test suite."""

from __future__ import annotations

import pytest

from harness.config import AnalysisProfile, load_profile


@pytest.fixture(scope="session")
def base_profile() -> AnalysisProfile:
    """The base profile: reproduces the historical deterministic pass exactly."""
    return load_profile()


@pytest.fixture(scope="session")
def ds3_profile() -> AnalysisProfile:
    """The Dark Souls III overlay: same thresholds, game- and creator-specific vocabulary."""
    return load_profile("ds3")
