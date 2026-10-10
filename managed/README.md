# Managed epistemic archive

This folder is the canonical workspace for the gaming-video analysis research discussion.

## Source material (not interpretations)
- sources/reference-01/user-provided-timestamped-transcript.txt — timestamped transcript copied as supplied, including its existing [ __ ] tokens, speech-recognition errors, and [Music] labels.
- sources/chat/pasted_export_20261009_223002.txt — byte-for-byte preserved uploaded conversation export (original Windows CRLF endings).
- sources/chat/early-user-turns.md — earlier user messages visible in this session, excluding the separate complete video transcript.
- sources/chat/assistant-recap-pre-export.md — explicitly curated, NOT a verbatim copy of early assistant responses.
- sources/reference-01/*-v1/v2/v3 — verbatim bytes of separately generated, historical analysis artifacts. Versions are not merged or silently corrected.

## Research outputs (proposals or interpretations)
- epistemic/PROVENANCE.md — hierarchy of evidence, uncertainty, corrections.
- epistemic/SOURCES.json — source manifest, hashes and known gaps.
- design/ARCHITECTURE.md — system map: layer → module → record types → spec doc.
- design/HARNESS_SPEC.md — design decisions across the discussion.
- design/DATA_MODEL.md — event ontology, music/edit/speech linkage.
- design/PROFILES.md — the config/control layer: profiles, thresholds, vocabulary.
- design/VALIDATION.md — test strategy and evaluation principles.
- design/VOICE_QUALITY.md — stateful narration and human-likeness evaluation.

## System (code)
- The running implementation is `src/harness/`. The layer map is design/ARCHITECTURE.md.
- Runtime config lives at the repo root in `config/` (`base.toml` plus `config/profiles/<id>.toml`), specified by design/PROFILES.md. It is data, not part of this archive.
- The `managed/` tree stays read-only to the code: the analysis pass reads the source manifest and never writes here.

## Archive policy
1. Keep original sources immutable. Add new versions instead of editing historical raw evidence.
2. Every derived claim should cite a source ID plus time interval, quote, frame or audio segment, and assessment method.
3. Transcript statements do not prove vocal inflection or frame-accurate events. Waveforms do not prove joke meaning.
4. Keep fact, inference, hypothesis, user judgment and corrected/contradicted analysis separate.
5. Preserve uncertainties, omissions, ASR errors, prior assistant mistakes and correction history.
6. This public repository includes language as originally supplied, without additional redaction.
7. New chat messages are NOT automatically synchronized. Explicitly append new exported chats or request another commit.

## Completeness note
The attached conversation export begins with the message “how does a video omni model work?” Earlier user turns are archived separately. Earlier assistant wording outside that export is only represented by a clearly marked reconstruction, because no raw export of those earlier assistant messages was attached. Do not describe this collection as a full verbatim chat transcript.
