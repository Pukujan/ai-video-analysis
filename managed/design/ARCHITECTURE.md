# Architecture

Status: SYSTEM MAP. This document is a map of the running system, not a proposal. Each row names the module that implements a layer, the symbols it exposes, the record types it emits, and the design doc that specifies it. A `built` row's symbols are importable today; a `proposed` row names no module.

Formatting rule: **every table cell contains only backticked tokens, comma-separated, or `—` for none.** `tests/unit/test_architecture_doc.py` parses these tables, imports every `built` symbol to prove it exists, proves every `proposed` row claims no module, and proves the emitted record types account for all of `RECORD_TYPES`. A cell that gains prose breaks the test on purpose — the map is meant to be machine-checked, not read loosely.

## Layers

| Layer | Status | Module | Symbols | Emits | Spec |
| --- | --- | --- | --- | --- | --- |
| Archive / E0 sources | built | `src/harness/registry.py` | `SourceRegistry`, `sha256_file`, `ArtifactCheck` | — | `managed/epistemic/PROVENANCE.md` |
| Harness core types | built | `src/harness/records.py`, `src/harness/provenance.py`, `src/harness/vocab.py`, `src/harness/timebase.py` | `RECORD_TYPES`, `parse_record`, `ProvenanceAnnotation`, `validate_vocab`, `MsInterval` | — | `managed/design/DATA_MODEL.md` |
| Config / profile layer | built | `src/harness/config.py` | `load_profile`, `AnalysisProfile`, `ConfigError`, `DEFAULT_CONFIG_DIR` | — | `managed/design/PROFILES.md` |
| Deterministic analysis pass | built | `src/harness/analyze.py` | `probe_media`, `measure_loudness`, `detect_silences`, `detect_scene_cuts`, `plan_coverage`, `build_records`, `analyze_video` | `source_artifact`, `reference_video`, `analysis_run`, `observation`, `audio_event`, `edit_event`, `shot_continuity`, `coverage_window` | `managed/design/HARNESS_SPEC.md` |
| Store and export | built | `src/harness/persist.py` | `write_jsonl`, `write_store`, `write_parquet` | — | `managed/design/DATA_MODEL.md` |
| Model-backed extraction (speech + comedy) | built | `src/harness/clips.py`, `src/harness/backend.py`, `src/harness/lens.py`, `src/harness/extract.py` | `extract_window`, `WindowMedia`, `get_backend`, `load_keys`, `TranscriptLens`, `DeliveryLens`, `InterpretationLens`, `extract_video` | `utterance`, `word_alignment`, `evidence_span`, `comedy_beat`, `vocal_delivery`, `response_decision` | `managed/design/EXTRACTION.md` |
| Model-backed extraction (later slices) | proposed | — | — | `gameplay_event`, `character_state`, `music_cue`, `audio_mix_event`, `narrative_entity`, `event_relation`, `style_pattern` | `managed/design/HARNESS_SPEC.md` |
| Human feedback | proposed | — | — | `review`, `generation_trial`, `human_preference` | `managed/design/VALIDATION.md` |
| Generation | proposed | — | — | — | `managed/design/VOICE_QUALITY.md` |

## Record types

Every record type in `RECORD_TYPES`, the family it belongs to, the layer that emits it, and whether that layer is built.

| Record type | Family | Layer | Status |
| --- | --- | --- | --- |
| `source_artifact` | substrate | `Deterministic analysis pass` | built |
| `reference_video` | substrate | `Deterministic analysis pass` | built |
| `analysis_run` | substrate | `Deterministic analysis pass` | built |
| `coverage_window` | substrate | `Deterministic analysis pass` | built |
| `utterance` | substrate | `Model-backed extraction (speech + comedy)` | built |
| `word_alignment` | substrate | `Model-backed extraction (speech + comedy)` | built |
| `evidence_span` | substrate | `Model-backed extraction (speech + comedy)` | built |
| `event_relation` | substrate | `Model-backed extraction (later slices)` | proposed |
| `observation` | derived | `Deterministic analysis pass` | built |
| `gameplay_event` | derived | `Model-backed extraction (later slices)` | proposed |
| `comedy_beat` | derived | `Model-backed extraction (speech + comedy)` | built |
| `vocal_delivery` | derived | `Model-backed extraction (speech + comedy)` | built |
| `character_state` | derived | `Model-backed extraction (later slices)` | proposed |
| `response_decision` | derived | `Model-backed extraction (speech + comedy)` | built |
| `edit_event` | derived | `Deterministic analysis pass` | built |
| `shot_continuity` | derived | `Deterministic analysis pass` | built |
| `audio_event` | derived | `Deterministic analysis pass` | built |
| `music_cue` | derived | `Model-backed extraction (later slices)` | proposed |
| `audio_mix_event` | derived | `Model-backed extraction (later slices)` | proposed |
| `narrative_entity` | derived | `Model-backed extraction (later slices)` | proposed |
| `style_pattern` | derived | `Model-backed extraction (later slices)` | proposed |
| `review` | human-feedback | `Human feedback` | proposed |
| `generation_trial` | human-feedback | `Human feedback` | proposed |
| `human_preference` | human-feedback | `Human feedback` | proposed |

## Notes

- `source_artifact` is registered by the analysis pass from a supplied file; the archive layer (`SourceRegistry`) verifies the immutable manifest and emits no records.
- The deterministic pass reads no pixels and calls no model, so every record it emits is E0 or E1. The model-backed layers are where interpretation (E2+) enters.
- The model-backed layer is split because it is landing in slices: the speech-and-comedy slice is built, and the visual/music/entity slice is still proposed. A record type belongs to whichever slice will emit it, so the map stays true while the remainder is unbuilt.
- `edit_event` and `shot_continuity` are emitted by the deterministic pass as `uncertain`: a scene-score peak is a visual discontinuity, not proof of an editorial cut.
