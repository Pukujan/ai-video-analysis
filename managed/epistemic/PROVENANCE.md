# Epistemic provenance protocol

## Evidence levels
- E0 / RAW_SOURCE: bytes of supplied files or user-authored text, hashed, never silently corrected.
- E1 / OBSERVATION: directly timestamped transcript quote, verified visible frame, or measurable audio feature; method must be recorded.
- E2 / INTERPRETATION: model or reviewer inference (e.g. sarcasm, social meaning, implied intention), with linked evidence and alternatives.
- E3 / GENERALIZATION: a reusable comedy/editing pattern derived across observed examples; attach support, counterexamples and uncertainty.
- E4 / GENERATION_GUIDANCE: proposed agent behavior, NEVER a fact about the original video's producer.

## Uncertainty policies
- Caption [ __ ] markers are in the source; do not guess missing words or call it assistant censorship.
- Caption errors (e.g. dessert/deserter, 'Kigot' versus knight) remain as supplied. Corrections, if made, belong in annotations with raw spans retained.
- Transcript enables semantic reading but not validated vocal tone. Require audio evidence for speaking style and prosody.
- Audio RMS/drop measurements establish dynamics, not music identity or comedic intention.
- Visual scene-cut detection may confuse game-camera motion with edits. Distinguish true editorial cuts, game transitions, continuous footage and uncertain cases.
- Shot duration and edit motivations cannot be inferred perfectly from the finished output; hidden source footage is unknown.
- Model names and product/API specs changed or contradicted during prior assistant responses; verify with official model docs at implementation time.

## Known historical quality issues
- v1: sparse visual sampling and scene/event estimates missed transient details and most verbal comedy.
- v2: added specific visual comedy scenes and audio-level evidence, but still no semantic hearing.
- v3: used user-supplied timestamped transcript, generated many joke labels and overarching interpretation, but was explicitly criticized as non-exhaustive by the user.
- Missing early cues specifically flagged by user: rolling enthusiasm contradiction, reveling in easy kills, NPC attacking crates.
- A 7:21 'PLEASE STAND BY' cue received competing characterizations across analyses before subsequent confirmation; preserve history and flag for independent recheck.

## Annotation fields every derived claim needs
claim_id, source_id, media_start_ms, media_end_ms, source_kind, verbatim_evidence, extraction_method, model_id, run_id, confidence, epistemic_level, review_status, supersedes_claim_id, alternate_hypotheses.

## Future updates
Append immutable source files for subsequent reference videos and chat exports; do not overwrite original transcriptions. Corrections should be represented as newer records linked to original claims.
