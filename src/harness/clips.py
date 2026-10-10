"""Window clip extraction: one coverage window -> the media a lens consumes.

The extraction pass does not send whole videos to a model. For each coverage
window it cuts a small, fixed-profile clip (video + audio), a mono WAV for
acoustic measurement, and two stills for the visual lens. Clips are named by a
hash of (video digest, window bounds), so re-extracting the same window reuses
the same bytes on disk and only the model call downstream is nondeterministic.

No network, no model: this module is ffmpeg only, and every output is a pure
function of the source bytes and the window.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from harness.analyze import AnalysisError, require_tool, run_ffmpeg

__all__ = ["WindowMedia", "extract_window", "window_stem"]

_FFMPEG = "ffmpeg"


@dataclass(frozen=True, slots=True)
class WindowMedia:
    """The artifacts cut for one coverage window."""

    clip: Path
    wav: Path | None
    frames: tuple[Path, ...]
    start_ms: int
    end_ms: int

    @property
    def has_audio(self) -> bool:
        return self.wav is not None


def window_stem(digest: str, start_ms: int, end_ms: int) -> str:
    """A content-addressed stem for a window's artifacts."""
    seed = f"{digest}:{start_ms}:{end_ms}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


def _cut(out: Path, args: list[str]) -> None:
    if out.is_file() and out.stat().st_size > 0:
        return  # content-addressed: identical window -> identical bytes
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = run_ffmpeg([_FFMPEG, "-y", "-nostdin", "-hide_banner", "-loglevel", "error", *args])
    if proc.returncode != 0 or not out.is_file():
        raise AnalysisError(f"clip extraction failed for {out.name}: {proc.stderr.strip()[-400:]}")


def extract_window(
    video: Path,
    start_ms: int,
    end_ms: int,
    digest: str,
    out_dir: Path,
    has_audio: bool = True,
) -> WindowMedia:
    """Cut the clip, WAV and two frames for ``[start_ms, end_ms)``."""
    require_tool(_FFMPEG)
    if end_ms <= start_ms:
        raise AnalysisError(f"window [{start_ms}, {end_ms}) is empty")
    stem = window_stem(digest, start_ms, end_ms)
    span = (end_ms - start_ms) / 1000.0
    start_s = start_ms / 1000.0

    clip = out_dir / f"{stem}.mp4"
    _cut(
        clip,
        [
            "-ss", f"{start_s:.3f}", "-t", f"{span:.3f}", "-i", str(video),
            "-vf", "scale=480:-2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart",
            str(clip),
        ],
    )

    wav: Path | None = None
    if has_audio:
        wav = out_dir / f"{stem}.wav"
        _cut(
            wav,
            [
                "-ss", f"{start_s:.3f}", "-t", f"{span:.3f}", "-i", str(video),
                "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav),
            ],
        )

    frames: list[Path] = []
    for index, fraction in enumerate((1 / 3, 2 / 3)):
        at_ms = start_ms + int((end_ms - start_ms) * fraction)
        frame = out_dir / f"{stem}_f{index}.jpg"
        _cut(
            frame,
            ["-ss", f"{at_ms / 1000.0:.3f}", "-i", str(video), "-frames:v", "1",
             "-vf", "scale=640:-1", "-q:v", "3", str(frame)],
        )
        frames.append(frame)

    return WindowMedia(clip, wav, tuple(frames), start_ms, end_ms)
