# Profiles: the config and control layer

Status: DESIGN + BUILT. Implemented by `src/harness/config.py`; the shipped config is `config/base.toml` and `config/profiles/`. This is the spec for that layer.

## Why a config layer

The harness core is game- and creator-agnostic. Everything specific to one creator or one game — the measurement thresholds and the declared vocabulary of entities, motifs and HUD slots — lives in a versioned profile rather than in code. A new domain is then a data change, not a code change, and a run records which profile produced it.

This is the **Application Profile** pattern (as in Dublin Core): a frozen base plus versioned per-domain extensions. The base is stable; profiles evolve on their own version numbers. The discipline that keeps it scalable is that the base only ever grows additively — a new profile may add keys it owns, never redefine a core meaning.

## File layout

```
config/
  base.toml            # the frozen base; reproduces the historical deterministic pass exactly
  profiles/
    ds3.toml           # Dark Souls III (one creator, one game, one run)
```

`--config-dir` overrides the root; `DEFAULT_CONFIG_DIR` is derived from the installed package location (`Path(__file__).resolve().parents[2] / "config"`), which is correct for the editable install in use. A non-editable wheel that does not ship `config/` must pass `--config-dir`.

## Overlay rules

`load_profile(profile_id, config_dir)` always reads `base.toml`. When `profile_id` is given and is not `"base"`, it reads `profiles/<id>.toml` and deep-merges it onto the base: **tables merge key-by-key, lists and scalars replace.** The merged dict is validated once, so a profile cannot produce a half-valid config.

## Keys

| Key | Type | Base default | Constraint |
| --- | --- | --- | --- |
| `schema_version` | str | `1.0.0` | must equal `CONFIG_SCHEMA_VERSION` |
| `profile.id` | str | `base` | `^[a-z0-9_]+$` |
| `profile.version` | str | `1.0.0` | `MAJOR.MINOR.PATCH` |
| `profile.creator_id` | str? | absent | optional domain identity |
| `profile.game_id` | str? | absent | optional domain identity |
| `profile.game_label` | str? | absent | stamped onto `reference_video.game` |
| `policy.id` | str | `det-v1` | leading token of the policy string |
| `windowing.window_ms` | int | `25000` | `> 0` |
| `windowing.overlap_ms` | int | `5000` | `>= 0`, `< window_ms` |
| `silence.noise_db` | float | `-32.0` | `< 0` |
| `silence.min_s` | float | `0.4` | `> 0` |
| `scene.threshold` | float | `0.4` | `0 < t < 1` |
| `scene.cut_score_threshold` | float | `0.6` | `> threshold` |
| `tooling.ffmpeg_version` | str | `8.1.1` | recorded as the model id |
| `vocabulary.terms` | list[str] | `[]` | each `ext:<slug>`, may not shadow a core member |
| `vocabulary.entities` | list | `[]` | `kind` must be an `EntityKind` member |
| `vocabulary.motifs` | list | `[]` | ids unique |
| `vocabulary.hud_regions` | list | `[]` | ids unique; coordinates all-present or all-absent |

Unknown keys are rejected (`extra="forbid"`). Strictness lives here, at load time, so a typo cannot enter silently.

## Vocabulary

A profile's own terms are `ext:<slug>` tokens — the extension slot already defined in `src/harness/vocab.py`. A bare string is rejected (a typo would otherwise enter silently) and a token that shadows a core vocabulary member is rejected. The core vocabularies stay closed; the profile is where new terms are named.

`entities`, `motifs` and `hud_regions` are **declared, not consumed**. The deterministic pass reads no pixels, so nothing here is asserted as having appeared in any video; these are names the model-backed extraction pass will cite once it exists. HUD coordinates are optional and their convention (absolute px vs normalized) is deliberately undecided until a reader consumes them.

## Reproducibility

Each run stamps three fields on the `analysis_run` record:

- `profile_id` — `profile.id`
- `profile_version` — `profile.version`
- `config_hash` — `sha256` of the resolved profile's canonical JSON (64 hex)

The run id is `run_<digest[:12]>_<tag>` where `<tag>` is `det_v1` for the base profile and `det_v1_<profile>` otherwise, so the same bytes measured under two profiles land in distinct rows and neither clobbers the other.

Two strings are derived from the config rather than written by hand, so a threshold change cannot leave the recorded evidence lying:

- `policy_string()` — `det-v1:ebur128=peak;silencedetect=-32dB/0.4s;scene>0.4`; hashed into `prompt_hash` (`sha256(...)[:16]`).
- `silence_method()` — `ffmpeg 8.1.1 silencedetect=noise=-32dB:d=0.4`.

Thresholds render with `:g` (so `-32.0` prints as `-32`). This is exact for the current values; a very small float would render in exponent form, which is why the base strings are pinned in tests.

## Deliberately out of scope

Provider, model id, endpoint, temperature and cost are **not** here. They belong to the model-backed extraction pass and arrive with it; the deterministic pass has no provider but ffmpeg.
