"""Deterministic core of the video-analysis harness.

The harness turns edited gaming VODs into reusable, evidence-grounded style
knowledge. This package holds the parts that need no model and no network:
the immutable source registry, transcript ingest, the coverage planner, and
the local event store. Model-backed analysis plugs in behind a backend seam.
"""

SCHEMA_VERSION = "1.1.0"
__version__ = "0.1.0"


def __getattr__(name: str) -> object:
    if name in ("RECORD_TYPES", "parse_record"):
        from harness import records

        return getattr(records, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
