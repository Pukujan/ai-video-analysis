# Video-reference reverse-engineering harness — consolidated product and systems brief

Status: DESIGN PROPOSAL. Distinguish from source evidence, available under managed/sources.

## Product objective
Turn up to ten user-selected edited gaming VOD references (submitted one by one, approximately 5–15 minutes each, possibly 360p) into reusable, evidence-grounded style knowledge. Eventually analyze the user's own lengthy gameplay and generate original, coherent, editable 10–20-minute entertainment videos with comedic narration, music, SFX and edited cuts, without copying source creators' exact speech or assets.

## Non-goals and constraints
- Do not optimize solely for kill highlights, memes per minute, frame-difference peaks or scene-cut counts.
- Do not equate comprehensive attempted sampling with 100% recall or claim perfect sarcasm recognition.
- Do not substitute generic LLM 'sarcastic narrator' prompting for learned behavioral conditions and listening tests.
- Do not claim the model observed speaking pitch/emotion unless the audio stream was actually available.
- Do not assume the model name mentioned in earlier discussion was correctly identified. Implement a model provider adapter, validate its official video+audio payload contract, frame sampling, context limits and pricing before deployment.
- Keep small scale: local DuckDB, Parquet exports, Python/Pydantic, FFmpeg/ffprobe, segment scheduler, review UI. No Kafka, Kubernetes, vector DB or complex workflow orchestrator required for ten clips.

## Analysis phases
1. Import video and/or source transcript, hash immutable source bytes, detect media duration, frame rate, audio streams, channel layout, original encoding. Store timing origin/timebase.
2. Global narrative analysis of full reference: central conflict, setting, recurring NPCs, narrator persona, recurring jokes, arcs, callback setup/payoff.
3. Deterministic coverage planner: overlapping 20–30-second local audiovisual windows (nominal overlap 5 seconds; adjust according to local events). Maintain every-window attempted/succeeded/failed status. Do not apply top-k joke truncation.
4. Multi-lens dense extraction: (a) speech and language, (b) visible game state and actions, (c) editorial transformations/cuts/continuity, (d) audio mix/musical events, (e) humor/presentation and intentional non-jokes.
5. Independent transcript pass: every spoken turn classified, including small throwaways, context clues, syntax shifts, self-correction, abandoned thoughts and no-joke speech.
6. Cross-window canonicalization: deduplicate observations from overlap without discarding potentially distinct punchlines; represent multiple related beats independently.
7. Cross-video linking: track long-running targets (dragon, knight, mimic, loot etc.), setups, repeated failures, escalations and delayed payoffs with explicit directed edges.
8. Omission hunt: rescan joke-dense windows, empty windows, high uncertainty, semantic/audio disagreement and human-reported missed bits.
9. Review: curate per-claim facts/inference, source evidence, alternatives, and approved examples; export to DuckDB and Parquet.
10. Only later: generate new gameplay narration and edit decisions, render, compare blind human preferences and store revisions.

## Reference #1: known adversarial examples
- 00:00–00:10 sacred church scene contrasted with crude reverence (transcript).
- 00:11–00:20 rolling mocked as childish, instantly becomes joyful (transcript; undercounted previously).
- 00:23–00:41 NPC inexplicably attacking boxes framed as underpaid labor, then sarcastic praise (transcript; undercounted previously).
- 00:43–01:00 deserter/dessert trousers wordplay and tangential fat-pants fantasy (ASR uncertain).
- Early weak-enemy domination vs later fear: narrator mood/ethical contradiction, not only self-torture.
- Dragon frames as social behavior problems; repeatedly provides external danger and ironic targets.
- 03:10–03:25 panicked retreat reframed as strategic diplomacy; pursuing knight becomes recurring character.
- 04:34–04:48 'treasure chest' becomes mimic; body horror interpreted as trust issues.
- 05:33–05:40 zero-cares joke synchronized with division-by-zero graphic.
- 05:40–06:03 repeated mimic attempt ends in worse embarrassment.
- 07:27–07:45 narrator cues 'future me' and battle music; edit participates as character.
- 07:45–07:55 knight finally beaten; payoff is that avoidance was unnecessary.
- 08:39–08:48 'deep' axe turns into a misunderstood social outsider.
- Preserve even uncomfortable/raunchy text in raw evidence; generation suitability and user-preferred boundaries are a separate configuration.

## Regenerable editing target
Store separate source-relative audiovisual time ranges, story beat links, edit recipes and creative treatment. A finished MP4 is an output, not the canonical edit. Export to a portable timeline representation when supported (e.g., OpenTimelineIO) and keep the raw timestamped edit decision manifest.

## Architecture and deliverables
- Immutable source registry + original attachments hash manifest.
- Adaptable multimodal backend (BYOK), provider version recorded for reproducibility.
- Media analysis preprocessor; transcript aligned to audio when available.
- Local DuckDB event store and Parquet snapshots, JSONL raw model responses.
- Evidence-linked event and editorial ontology.
- Minimal correction interface with audio+frame preview per source range.
- Golden development set and locked hidden holdouts.
- Future downstream narrator/planner/editor contract.
