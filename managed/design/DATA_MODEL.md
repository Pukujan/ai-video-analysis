# Canonical data ontology (design)

## Fundamental modeling rule
Store observable facts, creative interpretation, and future generation guidance separately. Never turn a proposed editing rule into an observation about a real creator.

A gameplay event can cause zero, one or several comedic beats; one joke can have several setups and callbacks over many minutes. An editorial cue can support multiple beats, and one beat can use multiple edits, music cues and speech turns. All are many-to-many with evidence links.

## Core tables / record types
1. source_artifacts: immutable video, audio, transcript and original model exports; content hash, byte length, provenance, ingest date, rights note.
2. reference_videos: game, title if known, total duration, frame rate, resolution, video and audio timebases.
3. analysis_runs: provider/model identifier, endpoint, prompt hash, transcript version, code version, frame sample policy, latency, cost, temperature.
4. coverage_windows: video ID, interval bounds, modalities actually exposed to the model, sampling policy, run ID and processing state, failure reason.
5. utterances: speaker, start_ms, end_ms, raw transcription, alignment method, disfluency tags, correction provenance.
6. word_alignments: utterance link, raw token, start/end_ms, diarization confidence, ASR confidence if present.
7. observations: time-bounded factual or measured records, modality type, native source location, extraction method, certainty.
8. evidence_spans: link observation or claim to precise transcript quote, sampled frame, audio region and media timebase.
9. gameplay_events: actor/entity, action, enemy behavior, environment, outcome, player action, contextual threat, uncertainty.
10. comedy_beats: setup, incongruity, payoff, target of humor, stance changes, mechanism labels (multi-label), speech/visual dependency, narrative role.
11. vocal_delivery: acoustic measurements (prosody, pause, rate, energy, pitch movement) and separately marked inferred affect; null when audio not semantically analyzed.
12. character_state: temporally scoped beliefs, fear/confidence, grudges, expectations, memories; inferred with evidence and alternatives.
13. response_decisions: whether narrator speaks, reacts, laughs, stays silent or delegates to SFX; includes contextual reason and negative/non-joke examples.
14. edit_events: edit_type and precise output timeline interval, input/source range if known, continuity classification, detection method, visual effect properties, evidence.
15. shots_and_continuity: continuous gameplay spans, cuts vs in-game loading/transitions, fades, jump cuts, freeze frames, motion effects, camera vs editing ambiguity.
16. audio_events: source stream, speech, in-game ambience, SFX, silence, peaks/transients, onset/offset, confidence.
17. music_cues: start/end_ms, energy/arousal/mood (if evidenced), rhythm/onsets, fades, change reason, foreground/underscoring status; music identity ONLY if verified.
18. audio_mix_events: ducking, crossfades, relative loudness, dynamic range, interruption/punctuation, speech-to-music synchronization.
19. narrative_entities: recurring NPC/enemy/monster/loot/motif persona targets; stable IDs across windows.
20. event_relations: directed temporal, caused_by, sets_up, pays_off, callback_to, undermines, contrasts_with, synchronized_with, edits_for.
21. style_patterns: aggregated generalizable event triggers, mental-state transitions, optional techniques, exceptions, counterexamples, evidence IDs.
22. reviews: human annotation corrections and disagreements without mutating underlying model evidence.
23. generation_trials: scenario, prompt/model, drafts, rejected candidates, TTS audio IDs, editorial variants, reviewer scores.
24. human_preferences: pairwise or ordinal blind ratings, groundedness, naturalness, funny/annoying, intentional silence preference.

## Domain constraints
- Times use source-relative integer milliseconds; wall-clock timestamps and other timebases are separate.
- start_ms < end_ms <= reference duration; zero-duration point cues explicitly marked as points.
- Intervals are half-open [start_ms, end_ms).
- No invented frame-accurate edit boundaries; attach estimation method and tolerance.
- A detected low-volume section is not automatically a comedic pause or deliberate silence.
- No inferred sarcasm from audio solely on volume. Dialogue semantics and actual performance are separate.
- No verified music track identity solely from general acoustic similarity.
- Capture positive and negative examples; 'nothing noteworthy' is an explicit decision, not missing data.
- Store source quotes verbatim and original transcript spelling; corrected ASR in a separate field.
- Music/sound selections for generated videos must be new or appropriately licensed, not extracted copyrighted assets by default.
- Historical claim revisions use supersedes relationships, preserving the rejected/earlier interpretation.

## Physical layout
Use a single local DuckDB file for curation and queries; Parquet files as export/snapshot, not one tiny file per 20-second window. Store model raw JSON responses and source metadata as append-only JSONL. Do not put 46 MB video binaries into a relational cell.

Recommended paths when implemented:
- media/ and transcripts/ for original assets kept locally or in explicit user-approved storage.
- raw/model_runs/<run_id>.jsonl for immutable model output.
- data/analysis.duckdb for locally validated and reviewed facts/labels.
- exports/*.parquet for curated analytical exports.
- managed/ for epistemic history, source notes, versioned specifications and evaluation definitions.

## Query goals
- Explain why a throwaway NPC observation lands as humor.
- Retrieve gameplay contexts in which narrators reverse opinions.
- Quantify variation in silence, genuine reactions and performed sarcasm.
- Compare cuts, uninterrupted shots, music onset/stops, audio ducking and punchline alignment.
- Link payoff 7:45 back to the multiple earlier knight avoidance sequences.
- Find cases where editor's action itself acts as a conversational comedic turn.
