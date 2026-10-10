"""Tests for window clip extraction."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from harness.analyze import AnalysisError
from harness.clips import WindowMedia, extract_window, window_stem


@pytest.fixture(scope="session")
def test_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 2-second testsrc clip with a 440 Hz tone."""
    video = tmp_path_factory.mktemp("media") / "test.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x240:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", str(video),
        ],
        check=True,
        capture_output=True,
    )
    return video


@pytest.fixture(scope="session")
def silent_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    video = tmp_path_factory.mktemp("media") / "silent.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=duration=2:size=320x240:rate=30",
            "-an", "-c:v", "libx264", str(video),
        ],
        check=True,
        capture_output=True,
    )
    return video


def test_window_stem_is_content_addressed() -> None:
    assert window_stem("abc", 0, 25_000) == window_stem("abc", 0, 25_000)
    assert window_stem("abc", 0, 25_000) != window_stem("abc", 0, 20_000)
    assert len(window_stem("abc", 0, 25_000)) == 12


def test_extract_window_produces_all_artifacts(test_video: Path, tmp_path: Path) -> None:
    media = extract_window(test_video, 0, 1_000, "d" * 64, tmp_path)
    assert isinstance(media, WindowMedia)
    assert media.clip.is_file() and media.clip.stat().st_size > 0
    assert media.wav is not None and media.wav.is_file()
    assert len(media.frames) == 2 and all(f.is_file() for f in media.frames)
    assert media.has_audio


def test_extract_window_reuses_existing_bytes(test_video: Path, tmp_path: Path) -> None:
    first = extract_window(test_video, 0, 1_000, "d" * 64, tmp_path)
    stamp = first.clip.stat().st_mtime_ns
    second = extract_window(test_video, 0, 1_000, "d" * 64, tmp_path)
    assert second.clip == first.clip
    assert second.clip.stat().st_mtime_ns == stamp  # not re-encoded


def test_extract_window_no_audio_yields_no_wav(silent_video: Path, tmp_path: Path) -> None:
    media = extract_window(silent_video, 0, 1_000, "e" * 64, tmp_path, has_audio=False)
    assert media.wav is None
    assert not media.has_audio


def test_extract_window_rejects_empty_window(test_video: Path, tmp_path: Path) -> None:
    with pytest.raises(AnalysisError):
        extract_window(test_video, 1_000, 1_000, "d" * 64, tmp_path)
