"""Deterministic core of the video-analysis harness.

The harness turns edited gaming VODs into reusable, evidence-grounded style
knowledge. This package holds the parts that need no model and no network:
the immutable source registry, transcript ingest, the coverage planner, and
the local event store. Model-backed analysis plugs in behind a backend seam.
"""

SCHEMA_VERSION = "1.0.0"
__version__ = "0.1.0"
