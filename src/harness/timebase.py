"""Timebase primitives.

All media times are source-relative integer milliseconds with half-open
intervals ``[start_ms, end_ms)``. Zero-duration point cues are marked
explicitly rather than represented by an empty interval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "MsInterval",
    "TimebaseError",
    "format_timestamp",
    "parse_timestamp",
]

_STAMP_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})$")


class TimebaseError(ValueError):
    """Raised for an interval or timestamp that violates the timebase rules."""


@dataclass(frozen=True, slots=True)
class MsInterval:
    """A half-open source-relative interval ``[start_ms, end_ms)``.

    A point cue (an instant with no duration) is a zero-width interval marked
    with ``is_point=True``; the constructor rejects an unmarked empty interval
    so that a missing duration is never silently treated as an instant.
    """

    start_ms: int
    end_ms: int
    is_point: bool = False

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < 0:
            raise TimebaseError("interval bounds must be non-negative")
        if self.start_ms > self.end_ms:
            raise TimebaseError(
                f"interval start {self.start_ms} must not exceed end {self.end_ms}"
            )
        if self.start_ms == self.end_ms and not self.is_point:
            raise TimebaseError(
                "zero-width interval must be marked is_point=True"
            )

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def overlaps(self, other: MsInterval) -> bool:
        """Half-open overlap: touching endpoints do not overlap."""
        return self.start_ms < other.end_ms and other.start_ms < self.end_ms

    def overlap_ms(self, other: MsInterval) -> int:
        if not self.overlaps(other):
            return 0
        return min(self.end_ms, other.end_ms) - max(self.start_ms, other.start_ms)

    def contains(self, other: MsInterval) -> bool:
        return self.start_ms <= other.start_ms and other.end_ms <= self.end_ms

    def shift(self, delta_ms: int) -> MsInterval:
        return MsInterval(self.start_ms + delta_ms, self.end_ms + delta_ms, self.is_point)

    def clamped_to(self, duration_ms: int) -> MsInterval:
        """Clamp to ``[0, duration_ms]``; raises if nothing remains."""
        start = min(max(self.start_ms, 0), duration_ms)
        end = min(max(self.end_ms, 0), duration_ms)
        if start == end and not self.is_point:
            raise TimebaseError("interval lies outside the media duration")
        return MsInterval(start, end, self.is_point)


def parse_timestamp(value: str) -> int:
    """Parse ``M:SS`` or ``H:MM:SS`` into milliseconds.

    Seconds are always two digits and minutes/seconds are zero-padded in the
    supplied transcripts, but a bare ``M:SS`` with a single-digit second is
    accepted so hand-written notes do not fail.
    """
    text = value.strip()
    match = _STAMP_RE.match(text)
    if not match:
        raise TimebaseError(f"unrecognized timestamp: {value!r}")
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    if seconds >= 60:
        raise TimebaseError(f"seconds out of range in timestamp: {value!r}")
    if hours and minutes >= 60:
        raise TimebaseError(f"minutes out of range in timestamp: {value!r}")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000


def format_timestamp(ms: int) -> str:
    """Render milliseconds as ``M:SS`` (or ``H:MM:SS`` past an hour)."""
    if ms < 0:
        raise TimebaseError("cannot format a negative timestamp")
    total_seconds = ms // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
