# Quality assurance, validation and evaluation plan

Status: PLANNED. Values are target criteria, not demonstrated performance.

## PDD / SDD / TDD
- PDD (product brief): can the data reproduce grounded original comedic mechanisms, audio choices, edits and non-jokes without losing micro-moments?
- SDD (technical brief): adapter, immutable media registry, window planner, evidence store, DuckDB, reviewer, exporter, generator.
- TDD where deterministic: timestamp parsing/conversion, overlap interval arithmetic, schema validators, hash checks, segment coverage, dedup, reference integrity, idempotent ingestion and export reproducibility.

## Mandatory programmatic validation
- All planned intervals either succeeded or have explicit failure statuses (target: 100% accounting, not 100% semantic recall).
- Original media hashes and transcript hashes preserved, analysis runs linked to source and model/prompt versions.
- Event timestamps inside source duration; relations reference existing IDs.
- Every derived comedy claim has timestamped evidence and epistemic level. Missing audio => no verified vocal-tone claim.
- Attempts to ascribe copyrighted music identity without supporting evidence flagged.
- Edit detectors must distinguish unknown from cut, transition and continuous playback.
- JSON/Parquet schemas stable across run versions; validated controlled vocabularies with extension slots.

## Semantic evaluation
- Human-reviewed gold intervals covering sarcasm, rolling contradiction, crates-attacking NPC, profanity wordplay, teasing weak enemies, mime/body horror, callback to knight, music cue to future editor, long scenes without jokes.
- Event-level joke precision/recall with semantic equivalence adjudication; report per-mechanism results and agreement between reviewers.
- Coverage by transcript utterances plus annotated reason when none are comedic; multiple micro-jokes in one utterance are possible.
- Model/human disagreement audits; unknown is allowed. Explicitly track false-negative and false-positive modes.
- Proposed initial success targets to calibrate, not declare met: >=90% manually labeled joke recall, >=85% precision, >=95% evidence grounding, +/-2 second coarse timestamp accuracy. Revisit targets after annotation exercise.
- Keep a locked holdout of unseen clips/creators, not added to example prompts; report test-set leakage risks.

## Metamorphic/regression tests
1. Prepend 10 seconds of black or silence: source-relative event times shift by +10 seconds; semantics stable.
2. Change resolution 720p -> 360p: verbal mechanisms should remain; allow true small-text loss.
3. Re-encode video without changing content: stable labels within tolerance.
4. Overlapping windows: duplicate canonical event only once, while preserving both underlying observations.
5. Mute audio but retain video: do not infer exact spoken words/prosody absent independent transcript.
6. Remove transcript: uncertainty rises for unresolved speech events, unless model can hear/transcribe audio.
7. Expand context 20s -> 60s: existing local event persists unless context materially changes interpretation; callbacks may improve.
8. Shuffle unrelated windows: local observations remain but unsupported cross-scene causal arcs should not survive.
9. Replace narration with unrelated narration: speech-grounded comedy labels should respond; visual gameplay facts should not.
10. Add irrelevant low-volume background music: gameplay event IDs should remain; music classification may change.
11. Very brief visual gag between sampled frames: mark possible missed event; do not claim exhaustive high-FPS recall.
12. Regenerate the same trial with fixed config and seed where supported; record stochastic variability.

## Evaluating actual editing
- Human-annotated cut/onset agreement with +/- frame or +/-100ms targets depending extraction method and video FPS.
- Precision/recall separately for actual jump cuts, source game transitions, graphic overlays, speed ramps, zooms and uninterrupted footage.
- Music onset/offset MAE, ducking event accuracy, edit-to-punchline temporal relationship.
- No fabricated cuts or source ranges when original raw footage unavailable.

## Blind human preference tests
Rate at minimum: grounding to gameplay; spoken naturalness; joke originality and comedic effectiveness; character continuity; audiovisual delivery; whether silence would be better. Randomize A/B order and evaluate rendered audio, not transcript alone.

## Initial hidden holdout policy
Use several manually annotated development scenes from reference 01, plus distinct clips from unseen creators if/when uploaded. Keep identities and gold labels out of prompts and retrieval index. Freeze evaluation rubric and prompt version before major compare runs.

## Anti-regression fixtures
- Rolling mocked at ~00:13 followed by spontaneous joy at ~00:17.
- Underpaid box-attacking NPC ~00:23–00:41.
- Enemy heals repeatedly ~01:02–01:20.
- Dragon, knight and mimic cross-chapter callbacks.
- At ~05:33 semantic division-by-zero line paired with graphic.
- ~07:27 'future me' cue to battle music.
- Ordinary moments with no punchline: the editor must be allowed to do nothing.
