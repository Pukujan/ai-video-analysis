"""Controlled vocabularies.

Every closed vocabulary is a ``StrEnum``. Values may be extended only through
an explicit ``ext:<slug>`` escape hatch, so a typo in a bare string is rejected
rather than silently stored — the design docs require "validated controlled
vocabularies with extension slots".
"""

from __future__ import annotations

import re
from enum import StrEnum

__all__ = [
    "EditType",
    "EpistemicLevel",
    "Modality",
    "RelationKind",
    "ReviewStatus",
    "SpanKind",
    "VocabError",
    "WindowStatus",
    "is_extension_token",
    "validate_vocab",
]

_EXT_RE = re.compile(r"^ext:[a-z0-9_]+$")


class VocabError(ValueError):
    """Raised when a value is neither a vocabulary member nor an extension token."""


class EpistemicLevel(StrEnum):
    """Evidence levels from managed/epistemic/PROVENANCE.md."""

    E0_RAW_SOURCE = "E0"
    E1_OBSERVATION = "E1"
    E2_INTERPRETATION = "E2"
    E3_GENERALIZATION = "E3"
    E4_GENERATION_GUIDANCE = "E4"


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    IN_REVIEW = "in_review"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    CORRECTED = "corrected"


class WindowStatus(StrEnum):
    """Terminal status of a planned coverage window.

    ``PLANNED`` is non-terminal: the coverage postcondition requires every
    window to reach one of the other three before accounting passes.
    """

    PLANNED = "planned"
    ATTEMPTED = "attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RelationKind(StrEnum):
    """Directed edge kinds between events (DATA_MODEL.md record 20)."""

    TEMPORAL = "temporal"
    CAUSED_BY = "caused_by"
    SETS_UP = "sets_up"
    PAYS_OFF = "pays_off"
    CALLBACK_TO = "callback_to"
    UNDERMINES = "undermines"
    CONTRASTS_WITH = "contrasts_with"
    SYNCHRONIZED_WITH = "synchronized_with"
    EDITS_FOR = "edits_for"


class SpanKind(StrEnum):
    """The native source location an evidence span points at."""

    TRANSCRIPT_QUOTE = "transcript_quote"
    FRAME = "frame"
    AUDIO_REGION = "audio_region"


class Modality(StrEnum):
    SPEECH = "speech"
    VISUAL = "visual"
    EDIT = "edit"
    AUDIO = "audio"
    MUSIC = "music"


class EditType(StrEnum):
    CUT = "cut"
    TRANSITION = "transition"
    CONTINUOUS = "continuous"
    FADE = "fade"
    JUMP_CUT = "jump_cut"
    FREEZE_FRAME = "freeze_frame"
    SPEED_RAMP = "speed_ramp"
    ZOOM = "zoom"
    OVERLAY = "overlay"
    UNKNOWN = "unknown"


def is_extension_token(value: str) -> bool:
    return bool(_EXT_RE.match(value))


def validate_vocab(value: str, vocabulary: type[StrEnum], field: str) -> str:
    """Return ``value`` if it is a member of ``vocabulary`` or an extension token.

    A bare string that matches neither raises, so an unknown label cannot enter
    the store by accident.
    """
    allowed = {member.value for member in vocabulary}
    if value in allowed or is_extension_token(value):
        return value
    raise VocabError(
        f"{field}={value!r} is not a {vocabulary.__name__} member "
        f"or an ext:<slug> token; allowed: {sorted(allowed)}"
    )
