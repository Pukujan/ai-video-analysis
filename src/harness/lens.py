"""The lenses: units that turn a coverage window into validated records.

A lens is the unit of work in the extraction pass. It declares what it emits
and whether it needs the model, builds a request when it does, and maps the
reply onto record types. Splitting by lens is what makes the epistemic mapping
mechanical: the transcript lens is the only lens that may emit an E1
``utterance``, the delivery lens measures acoustics with ffmpeg (E1, no model),
and the interpretation lens may emit only E2 claims — which
:class:`~harness.provenance.ProvenanceAnnotation` refuses unless they carry a
``model_id`` and at least one alternate reading.

The transcript lens has two producers behind one interface: ``supplied`` slices
the creator's own timestamped transcript (no model, words are verbatim E0/E1),
and ``asr`` transcribes the window clip. Downstream lenses read the produced
utterances and never learn which producer ran.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from harness.analyze import detect_silences, measure_loudness
from harness.backend import Backend, MediaRef, Request
from harness.clips import WindowMedia
from harness.config import AnalysisProfile
from harness.records import RecordError, parse_record
from harness.vocab import (
    ComedyMechanism,
    EpistemicLevel,
    NarrativeRole,
    ResponseDecision,
    VocabError,
    validate_vocab,
)

__all__ = [
    "DeliveryLens",
    "InterpretationLens",
    "Lens",
    "LensContext",
    "TranscriptLens",
    "parse_transcript",
]

Record = tuple[str, BaseModel]

_TS_RE = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})\s+(\S.*?)\s*$")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")

SUPPLIED = "transcript_slice"


@dataclass(frozen=True, slots=True)
class TranscriptLine:
    """One timestamped line of a supplied transcript."""

    start_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class LensContext:
    """Per-video constants a lens needs, independent of the window."""

    video_id: str
    source_id: str
    run_id: str
    profile: AnalysisProfile


def parse_transcript(path: Path) -> list[TranscriptLine]:
    """Parse a ``[M:SS] text`` transcript, ignoring non-timestamped lines."""
    lines: list[TranscriptLine] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = _TS_RE.match(raw)
        if not match:
            continue
        hours, minutes, seconds, text = match.groups()
        total_ms = (
            (int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)) * 1000
        )
        lines.append(TranscriptLine(total_ms, text))
    return lines


def _anchor(*parts: object) -> str:
    seed = ":".join(str(part) for part in parts)
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10]


def _enum_values(vocabulary: type[StrEnum]) -> list[str]:
    """The vocabulary's labels, for the reply schema's ``enum``.

    Without this the schema says "a string" and the model invents a label like
    ``"establishes the narrator's persona"``; the vocabulary is enforced in
    ``parse``, so it has to be *told* to the model too, not just checked after.
    """
    return [member.value for member in vocabulary]


def _vocab(value: str, vocabulary: type[StrEnum], field: str) -> str:
    """Vocabulary check, reported as a reply-shape failure so it re-asks.

    ``validate_vocab`` raises :class:`VocabError`; the model's reply is the only
    source of these values, so an unknown label means the reply did not match
    the schema — the same failure class as a missing field, not a crash.
    """
    try:
        return validate_vocab(value, vocabulary, field)
    except VocabError as exc:
        raise RecordError(str(exc)) from exc


def _vocab_list(values: list[Any], vocabulary: type[StrEnum], field: str) -> list[str]:
    """Validate a label list, dropping unknown labels rather than failing.

    A mechanism list is a best-effort annotation: one label the model invented
    must not discard a beat whose other labels are good, and must not cost a
    re-ask. If *no* label survives, the reply is rejected — an empty list the
    model chose is a different thing from a list that was all nonsense.
    """
    kept: list[str] = []
    for value in values:
        try:
            kept.append(validate_vocab(str(value).strip(), vocabulary, field))
        except VocabError:
            continue
    if values and not kept:
        raise RecordError(
            f"{field}: none of {values!r} is a {vocabulary.__name__} member "
            "or an ext:<slug> token"
        )
    return kept


def _ms(beat: dict[str, Any], key: str) -> int:
    """Read an integer millisecond field from a model beat, or fail the reply."""
    try:
        return int(beat[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise RecordError(f"beat {key!r} is missing or not an integer: {exc}") from exc


def _prov(
    claim_id: str,
    ctx: LensContext,
    start_ms: int,
    end_ms: int,
    evidence: str,
    method: str,
    level: EpistemicLevel,
    model_id: str | None = None,
    alternates: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "source_id": ctx.source_id,
        "media_start_ms": start_ms,
        "media_end_ms": end_ms,
        "source_kind": "video",
        "verbatim_evidence": evidence,
        "extraction_method": method,
        "model_id": model_id,
        "run_id": ctx.run_id,
        "confidence": None,
        "epistemic_level": level.value,
        "review_status": "unreviewed",
        "supersedes_claim_id": None,
        "alternate_hypotheses": alternates or [],
    }


class Lens(Protocol):
    """The unit of work: declares its output, produces validated records."""

    name: str
    emits: frozenset[str]

    def run(
        self,
        window: tuple[int, int],
        media: WindowMedia,
        ctx: LensContext,
        utterances: tuple[BaseModel, ...],
        backend: Backend | None,
    ) -> list[Record]: ...


# --------------------------------------------------------------------------
# Transcript lens (E1)
# --------------------------------------------------------------------------


class TranscriptLens:
    """Turns a window into utterances and word alignments. E1 either way."""

    name = "transcript"
    emits = frozenset({"utterance", "word_alignment"})

    def __init__(self, transcript_path: Path | None, model: str) -> None:
        self.transcript_path = transcript_path
        self.model = model
        self.mode = "supplied" if transcript_path and transcript_path.is_file() else "asr"

    def run(
        self,
        window: tuple[int, int],
        media: WindowMedia,
        ctx: LensContext,
        utterances: tuple[BaseModel, ...],
        backend: Backend | None,
    ) -> list[Record]:
        if self.mode == "supplied":
            return self._supplied(window, ctx)
        return self._asr(window, media, ctx, backend)

    # -- supplied producer: no model call ---------------------------------

    def _supplied(self, window: tuple[int, int], ctx: LensContext) -> list[Record]:
        assert self.transcript_path is not None
        lines = parse_transcript(self.transcript_path)
        start, end = window
        inside = [line for line in lines if start <= line.start_ms < end]
        records: list[Record] = []
        for index, line in enumerate(inside):
            next_start = inside[index + 1].start_ms if index + 1 < len(inside) else end
            line_end = min(next_start, end)
            if line_end <= line.start_ms:
                line_end = min(line.start_ms + 1, end)
            utterance_id = f"u_{ctx.video_id}_{_anchor(line.start_ms, line.text)}"
            records.append(
                (
                    "utterance",
                    parse_record(
                        "utterance",
                        {
                            "utterance_id": utterance_id,
                            "video_id": ctx.video_id,
                            "speaker": "narrator",
                            "raw_text": line.text,
                            "alignment_method": SUPPLIED,
                            "start_ms": line.start_ms,
                            "end_ms": line_end,
                        },
                    ),
                )
            )
            records.extend(self._words(utterance_id, line.text, line.start_ms, line_end))
        return records

    # -- asr producer: one model call -------------------------------------

    def _asr(
        self,
        window: tuple[int, int],
        media: WindowMedia,
        ctx: LensContext,
        backend: Backend | None,
    ) -> list[Record]:
        if backend is None or not media.has_audio:
            return []
        request = Request(
            model=self.model,
            prompt=(
                "Transcribe the spoken words in this clip. Return JSON: "
                '{"utterances": [{"start_ms": int, "end_ms": int, "text": str}]} '
                "with timestamps in milliseconds from the start of the clip."
            ),
            media=(MediaRef("video", media.clip),),
            schema={
                "type": "object",
                "properties": {
                    "utterances": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start_ms": {"type": "integer"},
                                "end_ms": {"type": "integer"},
                                "text": {"type": "string"},
                            },
                            "required": ["start_ms", "end_ms", "text"],
                        },
                    }
                },
                "required": ["utterances"],
            },
        )
        completion = backend.complete(request)
        start = window[0]
        records: list[Record] = []
        for item in completion.content.get("utterances", []):
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            s = start + int(item["start_ms"])
            e = min(start + int(item["end_ms"]), window[1])
            if e <= s:
                e = min(s + 1, window[1])
            utterance_id = f"u_{ctx.video_id}_{_anchor(s, text)}"
            records.append(
                (
                    "utterance",
                    parse_record(
                        "utterance",
                        {
                            "utterance_id": utterance_id,
                            "video_id": ctx.video_id,
                            "speaker": "narrator",
                            "raw_text": text,
                            "alignment_method": f"asr:{self.model}",
                            "start_ms": s,
                            "end_ms": e,
                        },
                    ),
                )
            )
            records.extend(self._words(utterance_id, text, s, e, confidence=None))
        return records

    def _words(
        self,
        utterance_id: str,
        text: str,
        start_ms: int,
        end_ms: int,
        confidence: float | None = None,
    ) -> list[Record]:
        tokens = _WORD_RE.findall(text)
        if not tokens:
            return []
        span = max(end_ms - start_ms, 1)
        step = span / len(tokens)
        records: list[Record] = []
        for index, token in enumerate(tokens):
            word_start = start_ms + int(index * step)
            word_end = start_ms + int((index + 1) * step)
            records.append(
                (
                    "word_alignment",
                    parse_record(
                        "word_alignment",
                        {
                            "alignment_id": f"wa_{utterance_id}_{index}",
                            "utterance_id": utterance_id,
                            "token": token,
                            "start_ms": word_start,
                            "end_ms": max(word_end, word_start + 1),
                            "asr_confidence": confidence,
                        },
                    ),
                )
            )
        return records


# --------------------------------------------------------------------------
# Delivery lens (E1, measured — never asked of a model)
# --------------------------------------------------------------------------


class DeliveryLens:
    """Measures acoustics with ffmpeg. ``inferred_affect`` stays null."""

    name = "delivery"
    emits = frozenset({"vocal_delivery"})

    def run(
        self,
        window: tuple[int, int],
        media: WindowMedia,
        ctx: LensContext,
        utterances: tuple[BaseModel, ...],
        backend: Backend | None,
    ) -> list[Record]:
        if not media.has_audio or media.wav is None:
            return []
        silence = detect_silences(
            media.wav,
            ctx.profile.silence.noise_db,
            ctx.profile.silence.min_s,
        )
        pause_ms = sum(span.end_ms - span.start_ms for span in silence)
        loudness = measure_loudness(media.wav)

        word_count = sum(
            len(_WORD_RE.findall(u.model_dump()["raw_text"])) for u in utterances
        )
        speaking_ms = max((window[1] - window[0]) - pause_ms, 0)
        rate = round(word_count / (speaking_ms / 60_000), 1) if speaking_ms > 0 else None

        claim_id = f"vd_{ctx.video_id}_{_anchor(window[0], window[1])}"
        evidence = (
            f"ffmpeg {ctx.profile.tooling.ffmpeg_version} silencedetect="
            f"noise={ctx.profile.silence.noise_db:g}dB:d={ctx.profile.silence.min_s:g}; "
            f"pause {pause_ms}ms; I {loudness.integrated_lufs} LUFS"
        )
        return [
            (
                "vocal_delivery",
                parse_record(
                    "vocal_delivery",
                    _prov(
                        claim_id,
                        ctx,
                        window[0],
                        window[1],
                        evidence,
                        ctx.profile.silence_method(),
                        EpistemicLevel.E1_OBSERVATION,
                    )
                    | {
                        "pause_ms": pause_ms,
                        "speech_rate_wpm": rate,
                        "energy_db": loudness.integrated_lufs,
                    },
                ),
            )
        ]


# --------------------------------------------------------------------------
# Interpretation lens (E2)
# --------------------------------------------------------------------------

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_ms": {"type": "integer"},
                    "end_ms": {"type": "integer"},
                    "quote": {"type": "string"},
                    "incongruity": {"type": "string"},
                    "setup": {"type": "string"},
                    "payoff": {"type": "string"},
                    "target_of_humor": {"type": "string"},
                    "mechanism_labels": {
                        "type": "array",
                        "items": {"type": "string", "enum": _enum_values(ComedyMechanism)},
                    },
                    "speech_visual_dependency": {"type": "string"},
                    "narrative_role": {"type": "string", "enum": _enum_values(NarrativeRole)},
                    "decision": {"type": "string", "enum": _enum_values(ResponseDecision)},
                    "decision_reason": {"type": "string"},
                    "alternate_readings": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "start_ms",
                    "end_ms",
                    "quote",
                    "incongruity",
                    "mechanism_labels",
                    "speech_visual_dependency",
                    "narrative_role",
                    "decision",
                    "decision_reason",
                    "alternate_readings",
                ],
            },
        }
    },
    "required": ["beats"],
}


class InterpretationLens:
    """Reads the clip with the model and proposes comedy beats. E2 only."""

    name = "interpretation"
    emits = frozenset({"comedy_beat", "response_decision", "evidence_span"})

    def __init__(self, model: str) -> None:
        self.model = model

    def build(
        self,
        window: tuple[int, int],
        media: WindowMedia,
        utterances: tuple[BaseModel, ...],
    ) -> Request:
        quotes = "\n".join(
            f"- [{u.model_dump()['start_ms']}ms] {u.model_dump()['raw_text']}"
            for u in utterances
        )
        prompt = (
            "This clip is one window of an edited gaming-commentary video. "
            f"It covers media time {window[0]}ms to {window[1]}ms.\n\n"
            f"Known spoken lines:\n{quotes or '(none supplied)'}\n\n"
            "Identify each comedic beat. For each, give timestamps in "
            "milliseconds from the start of the clip, the verbatim quote, what "
            "is incongruous, the mechanism labels, the target of humor, whether "
            "the joke needs the picture (speech_visual_dependency), its "
            "narrative_role, the narrator's decision and reason, and at least "
            "one alternate reading (a different way to read the same moment).\n\n"
            "The label fields are closed vocabularies — pick the closest member, "
            "never a description:\n"
            f"- narrative_role: one of {_enum_values(NarrativeRole)}\n"
            f"- decision (what the narrator does with this moment): one of "
            f"{_enum_values(ResponseDecision)} — 'react' is an in-character "
            "response, 'speak' is added narration, 'delegate_sfx' lets the game "
            "audio carry it\n"
            f"- mechanism_labels: zero or more of {_enum_values(ComedyMechanism)}"
        )
        return Request(
            model=self.model,
            prompt=prompt,
            media=(MediaRef("video", media.clip),),
            schema=_SCHEMA,
        )

    def parse(
        self,
        response: dict[str, Any],
        window: tuple[int, int],
        ctx: LensContext,
    ) -> list[Record]:
        start = window[0]
        records: list[Record] = []
        beats = response.get("beats") if isinstance(response, dict) else None
        if not isinstance(beats, list):
            raise RecordError("reply must be an object with a 'beats' array")
        for beat in beats:
            if not isinstance(beat, dict):
                raise RecordError(f"each beat must be an object, got {type(beat).__name__}")
            quote = str(beat.get("quote", "")).strip()
            if not quote:
                continue
            s = min(max(start + _ms(beat, "start_ms"), window[0]), window[1])
            e = min(max(start + _ms(beat, "end_ms"), s + 1), window[1])
            alternates = [str(a) for a in beat.get("alternate_readings", []) if str(a).strip()]
            mechanisms = _vocab_list(
                beat.get("mechanism_labels", []), ComedyMechanism, "mechanism_labels"
            )
            role = _vocab(
                str(beat.get("narrative_role", "unknown")), NarrativeRole, "narrative_role"
            )
            claim_id = f"cb_{ctx.video_id}_{_anchor(s, e, quote)}"
            records.append(
                (
                    "comedy_beat",
                    parse_record(
                        "comedy_beat",
                        _prov(
                            claim_id,
                            ctx,
                            s,
                            e,
                            quote,
                            f"model:{self.model}",
                            EpistemicLevel.E2_INTERPRETATION,
                            model_id=self.model,
                            alternates=alternates,
                        )
                        | {
                            "incongruity": str(beat.get("incongruity", "")).strip() or quote,
                            "setup": beat.get("setup") or None,
                            "payoff": beat.get("payoff") or None,
                            "target_of_humor": beat.get("target_of_humor") or None,
                            "mechanism_labels": mechanisms,
                            "speech_visual_dependency": str(
                                beat.get("speech_visual_dependency", "")
                            ).strip()
                            or "unknown",
                            "narrative_role": role,
                        },
                    ),
                )
            )
            records.extend(self._decision(beat, s, e, ctx, quote, alternates))
            records.append(
                (
                    "evidence_span",
                    parse_record(
                        "evidence_span",
                        {
                            "span_id": f"es_{claim_id}",
                            "claim_id": claim_id,
                            "source_id": ctx.source_id,
                            "kind": "transcript_quote",
                            "quote": quote,
                            "start_ms": s,
                            "end_ms": e,
                        },
                    ),
                )
            )
        return records

    def _decision(
        self,
        beat: dict[str, Any],
        s: int,
        e: int,
        ctx: LensContext,
        quote: str,
        alternates: list[str],
    ) -> list[Record]:
        decision = str(beat.get("decision", "")).strip()
        if not decision:
            return []
        decision = _vocab(decision, ResponseDecision, "decision")
        reason = str(beat.get("decision_reason", "")).strip() or "unspecified"
        claim_id = f"rd_{ctx.video_id}_{_anchor(s, e, decision, quote)}"
        return [
            (
                "response_decision",
                parse_record(
                    "response_decision",
                    _prov(
                        claim_id,
                        ctx,
                        s,
                        e,
                        quote,
                        f"model:{self.model}",
                        EpistemicLevel.E2_INTERPRETATION,
                        model_id=self.model,
                        alternates=alternates,
                    )
                    | {"decision": decision, "reason": reason},
                ),
            )
        ]

    def run(
        self,
        window: tuple[int, int],
        media: WindowMedia,
        ctx: LensContext,
        utterances: tuple[BaseModel, ...],
        backend: Backend | None,
    ) -> list[Record]:
        if backend is None:
            return []
        request = self.build(window, media, utterances)
        completion = backend.complete(request)
        try:
            return self.parse(completion.content, window, ctx)
        except RecordError as exc:
            retry = replace(
                request,
                prompt=f"{request.prompt}\n\nYour previous reply was rejected: {exc}",
            )
            return self.parse(backend.complete(retry).content, window, ctx)
