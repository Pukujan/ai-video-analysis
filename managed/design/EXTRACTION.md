# EXTRACTION.md — the model-backed extraction pass

Status: the speech-and-comedy slice is **built** (`clips.py`, `backend.py`,
`lens.py`, `extract.py`, `persist.py`); the record types not listed as
emitted below are later slices. The deterministic pass (`analyze.py`) emits 8
record types; this pass emits the model-backed types. It runs **after** the
deterministic pass and consumes its coverage windows; it does not modify
`analyze.py`'s behavior.

## What it is

A second pass over each video: for every coverage window, cut a clip,
extract speech, and ask one multimodal model to interpret the window.
Output is validated records in the same store, under a separate run-id
namespace, so both passes for one video sit side by side.

## Decisions already locked (with the evidence that locked them)

1. **Audio-first vertical: speech + comedy.** Emits `utterance`,
   `word_alignment`, `evidence_span`, `comedy_beat`, `vocal_delivery`,
   `response_decision`. The remaining model-backed types (gameplay, music,
   entities, relations, style patterns) are later slices.
2. **Split by claim type (E-levels).** Transcription is E1 — the model is a
   measuring instrument, `model_id` recorded. Acoustics are E1 measured by
   ffmpeg, never asked of a model. Interpretation (beats, decisions) is E2
   with model-supplied alternate readings — `provenance.py` rejects an E2
   claim with no `alternate_hypotheses` or no `model_id`, so the schema
   makes the honesty mechanical.
3. **Per-lens calls with a persisted transcript artifact.** The transcript
   lens runs first; downstream lenses read its output and never learn
   which producer made it (supplied transcript or ASR).
4. **Speech has two producers behind one interface.** ep3 has a supplied
   timestamped transcript (`managed/sources/reference-01/
   user-provided-timestamped-transcript.txt`, `[M:SS]` line prefixes) —
   words are sliced from it with no model call. ep1/ep2 have none — the
   window clip is transcribed by ASR. Both write the same artifact shape;
   `alignment_method` records which (`supplied` | `asr`).
5. **InferHub mp4 is the primary route; one call sees everything.**
   Empirically confirmed 2026-10-10: `ali/qwen3.8-omni-flash` accepts a
   base64 mp4 (video + audio track) and returns transcript, sarcasm
   reading, on-screen description, and visual-dependency in one reply.
   OpenRouter `qwen/qwen3.8-omni-flash` also works (audio + image blocks)
   but routes through Alibaba and is ~10x the cost; it stays in the
   router map as the named fallback, unwired in this slice.
6. **Stability, not bit-identity.** The provider gate
   (`InternalError.Algo.DataInspectionFailed` on InferHub input;
   `Output data may contain inappropriate content` via Alibaba output)
   is *probabilistic*: the identical profane window was rejected once and
   accepted on the next three runs, and when it accepts, profanity is
   transcribed verbatim. So the extraction pass guarantees stability —
   retry a gate trip up to 3 times, then record the window as failed
   with the provider reason — and the spec says plainly: reruns are not
   byte-identical to the first run.

## Components

### `harness/clips.py` — ffmpeg clip extraction (no network)

- `WindowMedia`: frozen dataclass — `clip`, `wav`, `frames` paths, plus
  `start_ms`/`end_ms` and a `has_audio` property.
- `extract_window(video, start_ms, end_ms, digest, out_dir, has_audio=True)
  -> WindowMedia`; a window without audio yields `wav=None`.
  Clip profile: `scale=480:-2, libx264 crf 30, aac 64k` (~0.5 MB / 25 s).
  Frames: 2 JPEGs at 1/3 and 2/3 of the window, `scale=640:-1`.
- Content-addressed filenames: `sha256(video_digest:start_ms:end_ms)[:12]`,
  so re-extraction reuses bytes and is bit-identical. Only the model call
  downstream is nondeterministic.
- Reuses `require_tool` / `run_ffmpeg` promoted public from `analyze.py`.

### `harness/backend.py` — the BYOK seam (provider-shaped)

- `GateTripped(Exception)` — carries the provider reason text.
- `MediaRef(kind, path)` — `kind ∈ {video, audio, image}`.
- `Request(model, prompt, media, schema)` — frozen.
- `Backend(Protocol)`: `complete(request) -> Completion` — the parsed JSON
  plus the model id, usage and attempt count, or raise.
- `InferHubBackend` — posts `video_url`/`image_url`/`input_audio` data
  URIs to `ali/qwen3.8-omni-flash`, requests JSON matching `schema`,
  retries gate trips up to 3 attempts with no sleep, raises
  `GateTripped` only after the last attempt. The gate-trip string lives
  here and nowhere else.
- `get_backend(provider_id)` — router map; `inferhub` wired, `openrouter`
  a named-but-unwired entry (raises `BackendError` naming the provider).
- `load_keys()` — reads `INFERHUB_API_KEY` from
  `C:/Users/pujan/Desktop/configs/.env` (falling back to
  `~/.dsh/.credentials.yaml`). Keys are never printed, logged, or put in
  exceptions.

### `harness/lens.py` — lens protocol + three lenses

- `Lens(Protocol)`: `name`, `emits`,
  `run(window, media, ctx, utterances, backend) -> list[Record]`. Each lens
  owns its own model call (or none), and `utterances` is the shared input
  downstream lenses read, so they never learn which producer made it.
- `TranscriptLens(transcript_path, model)`: `mode` is `supplied` when a
  transcript file exists, else `asr`.
  - `supplied`: slice the ep3 transcript into utterances by its
    `M:SS` prefixes against the window; emits `utterance` (E1,
    `alignment_method` = `"transcript_slice"`) + `word_alignment` rows
    (E1, interpolated per-word). No model call.
  - `asr`: one call per window asking for utterances as JSON;
    emits `utterance` (E1, `model_id` recorded,
    `alignment_method` = `"asr:ali/qwen3.8-omni-flash"`) +
    `word_alignment` (E1, interpolated across the model's span).
- `DeliveryLens`: **no model, no network.** ffmpeg only: `silencedetect`
  for `pause_ms`, word-count/rate for `speech_rate_wpm`,
  `loudnorm` print for `energy_db`. Emits `vocal_delivery` (E1).
  `inferred_affect` stays null in this slice — affect is interpretation
  and belongs to a later E2 claim.
- `InterpretationLens(model)`: one multimodal call on the mp4 clip. Its
  `build` and `parse` are public so a rejected reply can be re-sent; `run`
  is `build -> complete -> parse` with one re-ask (see error handling).
  Schema requires per beat: `start_ms, end_ms, quote, incongruity,
  mechanism_labels, target_of_humor, speech_visual_dependency,
  narrative_role, decision, decision_reason, alternate_readings`.
  The three label fields carry their vocabulary as an `enum` **and** the
  prompt names it: a bare `{"type": "string"}` let the model answer
  `narrative_role` with a free-text description, so every live window
  failed — the vocabulary has to be told to the model, not only checked
  after it answers. A single invented `mechanism_labels` entry is dropped
  rather than failing the beat; a list where *nothing* survives is a
  rejected reply like any other shape failure. Emits `comedy_beat` (E2),
  `response_decision` (E2), `evidence_span`
  (`kind="transcript_quote"`, verbatim `quote`) per claim. Every reply-shape
  failure — a missing field, a bad timestamp, an unknown vocabulary label —
  is normalized to `RecordError`, so one re-ask covers all of them.

### `harness/extract.py` — orchestration

- `ExtractionReport`: `run_id, video_id, digest, profile_id,
  profile_version, config_hash, records, counts, warnings, failures`.
- `extract_video(video, out_root, profile, backend=None, limit_windows=None,
  dry_run=False)`: probe → `plan_coverage` (the deterministic pass's own
  function) → per window: `extract_window` → `TranscriptLens` →
  `DeliveryLens` → `InterpretationLens` → assemble → persist.
- The supplied transcript is resolved by **video digest**, not filename: a
  re-encode or re-cut must not inherit another file's verbatim words, so it
  falls back to ASR — noted once in `warnings`. Only the reference episode
  has one.
- `run_id = run_{digest[:12]}_ex_{profile_id}` — a separate namespace
  from `det_v1`; `DELETE FROM records WHERE run_id = ?` idempotency is
  per-pass and cannot clobber the deterministic rows.
- Persistence: `write_jsonl` / `write_store` / `write_parquet` live in
  `harness/persist.py`, used by both passes unchanged.
- CLI: `python -m harness.extract --video V --profile ds3
  [--limit-windows N] [--dry-run]`. `--dry-run` forces `backend=None`, so it
  exercises clip cutting + prompt assembly + schema validation with zero
  network, and persists nothing.

## Data flow

```
det pass windows (plan_coverage)
  └─ clips.extract_window      ffmpeg → clip.mp4 + wav + 2 frames
  └─ TranscriptLens            supplied-slice | InferHub ASR → utterance, word_alignment
  └─ DeliveryLens              ffmpeg only → vocal_delivery
  └─ InterpretationLens        InferHub on clip.mp4 → comedy_beat,
                               response_decision, evidence_span
  └─ persist                   jsonl + duckdb (same store, ex_ namespace) + parquet
```

## Error handling

- **Gate trip** (provider content gate): retry ×3 inside the backend;
  on final failure the window is skipped and recorded — a `CoverageWindow`
  with `status="failed"`, `failure_reason` = `"content_gate: "` + the
  provider text — so the coverage postcondition (every window terminal)
  holds. Partial results from earlier lenses in that window are kept.
- **Schema violation by the model**: one re-ask with the validation error
  appended; then the window fails with `failure_reason` =
  `"schema_rejected: "` + the error.
- **Other backend failure**: the window fails with `"extraction_error: "`
  + the error; the pass continues to the next window.
- **No audio in window**: `DeliveryLens` emits nothing; `TranscriptLens`
  (asr) emits nothing; `InterpretationLens` may still run (visual-only).
- **Missing ffmpeg / missing key**: fail fast at startup with an
  actionable message; nothing partially written.
- **Network/timeout**: `urllib` timeout 180 s; a timeout counts as a
  failed attempt under the same retry policy.

## Testing

- **Unit, no network:** clip extraction on a generated test video (window
  math, content-addressed names, bit-identical re-extract); transcript
  slicing against the real ep3 transcript file; lens `parse` against
  recorded fixture responses; backend request assembly and retry policy
  against a stubbed transport; and the whole pass against a scripted fake
  backend — the six record types, every window terminal, gate-trip and
  schema-rejection failure marking, one-re-ask recovery, run-id namespace
  isolation vs `det_v1`, and no clobbering of the deterministic rows.
- **Metamorphic (the VALIDATION.md contract, applied to this pass):**
  `--dry-run` twice → identical file manifests; idempotent re-run →
  store row counts unchanged for the same run_id.
- **One live smoke test, marked and manual:** a single real window
  through InferHub, asserted only on shape (utterances non-empty,
  beats carry `alternate_hypotheses`, `model_id` set), never on
  specific comedic judgments. A gate-tripped window is a *passing*
  outcome there, as long as it is recorded terminal-and-failed with the
  provider's reason — that is the stability guarantee, not a failure.
  Comedic *quality* is judged by the human, via `review` records — the
  human-feedback family — not by tests. Its first run failed and earned
  its keep: the model answered `narrative_role` with a free-text
  description because the schema only said "a string", so *every* live
  window failed while all 200 offline tests passed. Fixtures cannot see
  what the model actually replies; that is the whole point of one live
  test.

## Non-goals for this slice

- No gameplay/editorial lens (needs longer visual context).
- No music/audio-mix lens (music identification must not be inferred).
- No cross-window canonicalization (beats spanning windows), no
  cross-video entity linking, no style-pattern generalization.
- No OpenRouter wiring (named fallback only).
- No `inferred_affect` (stays null; a later E2 claim).
