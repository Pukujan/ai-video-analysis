# AI Video Analysis — project and goal

Status: PROJECT DEFINITION. This document states what the project is for. It is a proposal about the project, not evidence about any video. Evidence lives under [`managed/sources/`](managed/sources); design proposals live under [`managed/design/`](managed/design); the provenance rules that keep those apart are in [`managed/epistemic/PROVENANCE.md`](managed/epistemic/PROVENANCE.md).

## The goal

Turn edited gaming VODs the user already likes into reusable, evidence-grounded style knowledge — then use that knowledge to narrate and edit the user's own long gameplay into original 10–20 minute entertainment videos, with comedic narration, music, SFX and cuts.

In the user's own words, the target is: *"all I have to do is play games and AI can make it interesting with background music, voice and edited cuts."*

The reusable unit is not the finished MP4. It is a **data model**: a timestamped, evidence-linked record of what happened in the reference video — spoken lines, gameplay events, comedy beats, edits, music and audio mix — so that an edit becomes regenerable from data rather than copied from the source file.

## What the user actually asked for

From the archived turns in [`managed/sources/chat/early-user-turns.md`](managed/sources/chat/early-user-turns.md):

- Whether any existing open-source or BYOK paid tool can reverse-analyze game stream videos so their edits become regenerable.
- Whether reference VODs can be converted into reusable data for the user's own long videos.
- A **strong data model** to classify everything a multimodal ("omni") model extracts from a video, and how exhaustively the model can do it.

## What exists today

This repository is an **archive plus a running deterministic pass**. What is committed:

- **Primary evidence (immutable).** One reference video's timestamped transcript, a pasted conversation export, and the earlier user turns, each preserved byte-for-byte and hashed in [`managed/epistemic/SOURCES.json`](managed/epistemic/SOURCES.json). The 46 MB source video is not committed; only its hash and metadata are recorded.
- **Historical analyses (not ground truth).** Three versions of model-derived analysis of reference 01, kept side by side and explicitly not merged or corrected.
- **Design proposals.** The harness brief ([`HARNESS_SPEC.md`](managed/design/HARNESS_SPEC.md)), the event ontology ([`DATA_MODEL.md`](managed/design/DATA_MODEL.md)), the validation plan ([`VALIDATION.md`](managed/design/VALIDATION.md)) and the voice-quality brief ([`VOICE_QUALITY.md`](managed/design/VOICE_QUALITY.md)).
- **A running harness core and deterministic pass.** [`src/harness/`](src/harness) holds the record types, the controlled vocabularies and timebase, the immutable source registry, the versioned profile config and the ffmpeg analysis pass. `python -m harness.analyze --video <path>` measures a video into validated records and writes a local DuckDB store plus a Parquet export. The layer map is [`managed/design/ARCHITECTURE.md`](managed/design/ARCHITECTURE.md).

What remains unbuilt is the model-backed half: multimodal extraction, the correction UI and the holdout set. The data model, the phases and the metrics are still proposals with target values; only the deterministic measurements are demonstrated.

## What is proposed (not yet built)

Per the design briefs, the intended system is small and local:

- Multi-lens dense extraction (speech, gameplay state, editorial cuts, audio mix/music, humor and deliberate non-jokes), with an independent transcript pass.
- An adaptable BYOK multimodal backend whose provider version is recorded per run.
- A minimal correction interface and a locked holdout set for evaluation.

Only after that: narration and edit generation, rendering, and blind human preference tests.

Already built, and mapped in [`managed/design/ARCHITECTURE.md`](managed/design/ARCHITECTURE.md): the immutable source registry with byte hashes, the ffmpeg/ffprobe preprocessor, the coverage planner over overlapping windows, the versioned profile config, and the local DuckDB store with Parquet exports.

## Boundaries

- **Evidence discipline.** No joke, sarcasm, emotion or music identity is recorded as observed without linked evidence. An interpretation is never stored as an observation. Caption `[ __ ]` markers are preserved, not guessed.
- **No false precision.** No invented frame-accurate edit boundaries and no metric presented as met before it is measured.
- **Separate generation guidance from fact.** A proposed editing rule is never a claim about the reference video's creator.
- **Scale.** Ten clips do not need Kafka, Kubernetes, a vector database or a workflow orchestrator.
- **Rights.** Music and sound for generated videos must be new or appropriately licensed; reference assets are not extracted by default.
- **Public and unredacted.** The repository keeps language exactly as supplied, without additional redaction.

## How claims are recorded

Every derived claim carries: `claim_id, source_id, media_start_ms, media_end_ms, source_kind, verbatim_evidence, extraction_method, model_id, run_id, confidence, epistemic_level, review_status, supersedes_claim_id, alternate_hypotheses` — with epistemic levels E0 (raw source) through E4 (generation guidance) as defined in [`managed/epistemic/PROVENANCE.md`](managed/epistemic/PROVENANCE.md).

## Next unit of work

The deterministic pass and its config/profile layer are in. The next unit is the model-backed extraction pass — the multi-lens dense extraction that produces the remaining substrate and derived record types — behind the BYOK backend seam, with the coverage planner driving per-window calls. See the `proposed` rows in [`managed/design/ARCHITECTURE.md`](managed/design/ARCHITECTURE.md).
