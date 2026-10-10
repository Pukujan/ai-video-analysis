"""Tests for timebase primitives.

Boundary cases come from the real reference-01 transcript, whose stamps run
0:00 to 9:22 in M:SS form.
"""

from __future__ import annotations

import pytest

from harness.timebase import MsInterval, TimebaseError, format_timestamp, parse_timestamp


class TestParseTimestamp:
    @pytest.mark.parametrize(
        ("stamp", "expected_ms"),
        [
            ("0:00", 0),
            ("0:10", 10_000),
            ("9:22", 562_000),
            ("1:02:03", 3_723_000),
            ("  0:41  ", 41_000),
        ],
    )
    def test_parses_valid_stamps(self, stamp: str, expected_ms: int) -> None:
        assert parse_timestamp(stamp) == expected_ms

    @pytest.mark.parametrize("stamp", ["", "9", "9:2:3:4", "abc", "0:60", "1:60:00"])
    def test_rejects_invalid_stamps(self, stamp: str) -> None:
        with pytest.raises(TimebaseError):
            parse_timestamp(stamp)


class TestFormatTimestamp:
    @pytest.mark.parametrize(
        ("ms", "expected"),
        [(0, "0:00"), (10_000, "0:10"), (562_000, "9:22"), (3_723_000, "1:02:03")],
    )
    def test_round_trips(self, ms: int, expected: str) -> None:
        assert format_timestamp(ms) == expected
        assert parse_timestamp(expected) == ms

    def test_rejects_negative(self) -> None:
        with pytest.raises(TimebaseError):
            format_timestamp(-1)


class TestMsInterval:
    def test_duration(self) -> None:
        assert MsInterval(1_000, 4_000).duration_ms == 3_000

    def test_rejects_reversed_bounds(self) -> None:
        with pytest.raises(TimebaseError):
            MsInterval(4_000, 1_000)

    def test_rejects_unmarked_zero_width(self) -> None:
        with pytest.raises(TimebaseError):
            MsInterval(2_000, 2_000)

    def test_accepts_marked_point(self) -> None:
        point = MsInterval(2_000, 2_000, is_point=True)
        assert point.duration_ms == 0
        assert point.is_point

    def test_rejects_negative_bounds(self) -> None:
        with pytest.raises(TimebaseError):
            MsInterval(-1, 100)

    def test_touching_endpoints_do_not_overlap(self) -> None:
        left = MsInterval(0, 1_000)
        right = MsInterval(1_000, 2_000)
        assert not left.overlaps(right)
        assert left.overlap_ms(right) == 0

    def test_overlapping_pair(self) -> None:
        left = MsInterval(0, 1_500)
        right = MsInterval(1_000, 2_000)
        assert left.overlaps(right)
        assert left.overlap_ms(right) == 500

    def test_containment(self) -> None:
        outer = MsInterval(0, 10_000)
        inner = MsInterval(2_000, 4_000)
        assert outer.contains(inner)
        assert not inner.contains(outer)

    def test_shift_preserves_width_and_point_flag(self) -> None:
        assert MsInterval(1_000, 2_000).shift(10_000) == MsInterval(11_000, 12_000)
        point = MsInterval(1_000, 1_000, is_point=True).shift(500)
        assert point == MsInterval(1_500, 1_500, is_point=True)

    def test_clamp_trims_to_duration(self) -> None:
        assert MsInterval(9_000, 11_000).clamped_to(10_000) == MsInterval(9_000, 10_000)

    def test_clamp_rejects_interval_outside_media(self) -> None:
        with pytest.raises(TimebaseError):
            MsInterval(11_000, 12_000).clamped_to(10_000)

    def test_frozen_and_hashable(self) -> None:
        assert len({MsInterval(0, 1_000), MsInterval(0, 1_000)}) == 1
