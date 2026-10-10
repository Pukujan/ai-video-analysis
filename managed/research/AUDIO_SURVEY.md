# Audio analysis survey — reverse-engineering the mix

Status: COMPLETE — all 6 audio areas done (1 music separation + ID,
2 audio event/SFX, 3 speech/prosody/laughter, 4 loudness/mix + QC,
5 game audio middleware + edit/timeline schemas, 6 AV + humor).
Assembled 2026-10-09. Video-side analysis lives in `VIDEO_SURVEY.md`;
auto-VOD/auto-editing (generation side) in `AUTOEDIT_SURVEY.md`.

## Why this survey exists

The reference video's audio is a mono-summed stereo track (L and R channels
bit-identical), so narration, game SFX, and music are permanently fused — no
channel split can recover them. Deep audio analysis therefore requires ML
source separation before any per-layer analysis. The design docs require
acoustic evidence for prosody, music, and mix events; a transcript alone is
explicitly insufficient.

## Area 2: audio event detection / SFX tagging (COMPLETE)

### Models (all AudioSet-output)

| Model | Kind | License | AudioSet classes | Notes |
|---|---|---|---|---|
| YAMNet | pretrained (TF Hub) | Apache-2.0 | 521 | CPU-friendly, 2019, older |
| PANNs CNN14 | pretrained + OSS | MIT | 527 | mature; SED variants for frame-level |
| HTS-AT | pretrained | MIT | 527 | 30M params, SED localization mode |
| BEATs | pretrained (Microsoft) | MIT | 527 | SSL, strongest current tagging |
| CED | pretrained (Xiaomi) | GPL-3.0 (repo) / Apache-2.0 (HF) | 527 | CPU-fast, ONNX builds |
| AST | pretrained | BSD-3-Clause | 527 | foundational transformer |
| VGGish | feature extractor | Apache-2.0 | — (128-D embedding) | superseded |
| LAION-CLAP | pretrained | CC0-1.0 repo / Apache-2.0 HF | none (zero-shot free-text) | can probe custom prompts like "you died sting" |

### Schemas and datasets

- **AudioSet ontology** — 632-class hierarchical graph, `/m/...` MIDs,
  CC BY-SA 4.0 (ShareAlike applies to the ontology itself).
  `ontology.json`: `{id, name, description, child_ids, restrictions}`.
  THE strongest reusable label backbone — every model above outputs into it.
- **AudioSet Strong** — onset/offset labels; TSV `clip_id, onset(s), offset(s),
  MID`; 934k events / 447 MIDs; CC BY 4.0. The record shape is exactly the
  target shape for our `audio_events`.
- **DCASE Task 4** — the community-standard SED output schema:
  `onset(s), offset(s), event_label` (min event 250 ms, gaps <150 ms merged).
- **FSD50K** — 200-class curated subset of AudioSet ontology; CC-BY dataset
  but per-clip licenses vary (CC0/CC-BY/CC-BY-NC/CC-Sampling+).

### Gaps (confirmed, load-bearing)

- **No game-SFX ontology exists.** AudioSet has only `Video game music` plus
  generic `Gunshot`/`Explosion`/`Slam`. General taggers misclassify stylized
  game audio (BGG paper's own framing).
- Game datasets are narrow for our purposes: PUBG/BGG gunshot dataset (37 firearm
  types) is non-commercial-research-only; BattleSound (CHI 2023) is 3 classes
  (VOICE/EFFECT/MIXED) with no stated license.
- Laughter: jrgillick/laughter-detection (MIT, Switchboard, segment output)
  works; voc2vec (2025) broader; no production speech/laughter/SFX taxonomy.
- "AudioSet Unsupervised Sound Events" — not confirmed to exist; treat as
  unverified.

### Adopt for our data model

1. Event labels: AudioSet MIDs as the base vocabulary, via our `ext:<slug>`
   escape hatch for game-specific labels (`ext:you_died_sting`,
   `ext:mimic_chomp`) — mirrors the vocab.py design already committed.
2. Event records: AudioSet-Strong/DCASE `onset, offset, MID` shape maps
   directly onto `AudioEvent(start_ms, end_ms, kind, confidence)`.
3. Zero-shot game labels: LAION-CLAP with hand-written prompts, validated
   against known adversarial examples (the 7:27 battle-music cue etc.).

## Area 6: audio-visual + humor/comedy research (COMPLETE)

### Audio-visual (sound ↔ image)

| Dataset/model | License | Reusable schema? | Note |
|---|---|---|---|
| AVE (4,143 videos, 28 classes) | research use | partial — `{class, start, end}` | links audio event to a window, not a visual object |
| VGGSound (~200k clips, 309 classes) | CC BY 4.0 | weak — `{id, start, end, class}` | clean single-label vocabulary |
| Sound of Pixels / MUSIC | MIT-style (MIT CSAIL) | yes — `sound_source → region + channel` | instruments only |
| AVA-ActiveSpeaker | CC BY 4.0 (annotations) | yes — `{frame, face_track, speaking}` | "who talks when" |
| AVSBench | research | yes — pixel masks per sounding source | finest audio↔object binding |
| SyncNet / VocaLiST | open code | no — scalar sync score | feature extractor only |

### Humor, laughter, comedy mechanism

| Dataset/framework | License | Reusable schema? | Note |
|---|---|---|---|
| UR-FUNNY (TED, tri-modal) | CC BY-NC-SA 4.0 | partial — `{punchline, context, binary}` | context/punchline split is reusable; binary only |
| MUStARD (sitcom sarcasm) | MIT | yes — `{utterance, context[], sarcasm_bool}` | cleanest "line + prior turns + label" |
| MHD (sitcom, laughter track) | research | yes — laughter as audience-verified label | most defensible "did it land" |
| HumorDB (3,545 image pairs) | CC BY 4.0 | yes — `{binary, rating, pairwise}` | controlled-pair method is copyable |
| ExFunTube (10,136 funny shorts) | CC BY 4.0 (URLs only) | **yes — `{video, [{start, end, explanation}]}`** | ties timestamped moment to why-funny text |
| StandUp4AI (3,617 videos, 128k laugh labels) | CC BY 4.0 (annotations) | yes — `{word, laughter_follows}` | models comedic TIMING |
| THInC | CC BY 4.0 (paper) | yes — theory taxonomy (superiority/relief/incongruity/incongruity-resolution) | proxy classifiers, not human labels |
| Benign Violation Theory | theory | partial — violation × benign rubric | principled axis, no dataset |
| Mazzocconi laughter taxonomy | paper | yes — laughter FUNCTION vocabulary | complements binary "laughed" |

### Editing style / shot grammar (also here, overlaps Area 5)

| Dataset | License | Reusable schema? | Note |
|---|---|---|---|
| **MovieCuts** (173,967 pairs) | not stated | **YES — 10 pro-validated cut types** | best editing label schema found |
| **AVE "Anatomy of Video Editing"** (196k shots) | not stated | YES — per-shot attributes incl. sound-source | closest to a general shot grammar |
| MovieNet (1,100 films) | OpenDataLab agreement | YES — `{shot, scale, movement, scene}` | scale/movement vocabulary adoptable |
| Cinemetrics | open methods | partial — metric set (ASL, cutting rate) | quantify editing rhythm |
| Gameplay Highlights (4,408 events, 5 FPS) | proprietary, not released | partial — 7-class event vocab | no edit modeling |

### The decisive finding

**No dataset or model jointly labels (visual event + audio event + comedic
mechanism + edit decision/timing).** Audio-visual datasets carry zero humor
labels; humor datasets carry little editing or sounding-object structure and
are mostly binary; editing datasets carry zero humor labels. Nothing explains
why a given line over a given image, cut a certain way, is funny.

That fusion — across our own reference videos, with evidence links — is the
original contribution this project would make. It is also why no off-the-shelf
system can be adopted wholesale; we adopt schemas per layer and fuse them.

### Adopt for our data model

- Cut/edit labels: **MovieCuts' 10 cut types** → our `EditEvent.edit_type`
  extension tokens (`ext:j_cut`, `ext:l_cut`, `ext:smash_cut`, `ext:match_cut`).
- Shot grammar: **AVE per-shot attributes** + MovieNet scale/movement → our
  `ShotContinuity` fields.
- Humor mechanism: theory triad + benign violation → our `ComedyMechanism`
  vocabulary (already built); `NarrativeRole` covers setup/callback/payoff.
- Timing ground truth: laughter-follows-word (StandUp4AI) is the model for
  how we mark a beat's landing point.
- Why-funny text: ExFunTube's `{start, end, explanation}` is the shape our
  `ComedyBeat.setup/payoff/incongruity` fields should be populated against.

## Area 1: music source separation + music identification (COMPLETE)

### The on-target finding

**Cocktail Fork Problem / MRX (MERL, ICASSP 2022)** — outputs *exactly* our
three buckets: `speech.wav`, `music.wav`, `sfx.wav`. For a narrated gameplay
mix this is the correct decomposition (narration = speech, game audio =
sfx, soundtrack = music). Code MIT; the **DnR dataset is CC BY 4.0** and
ships `mix/music/speech/sfx.wav` + `annots.csv` (speech transcriptions, SFX
sound classes, music genre labels) — a real labeled schema to copy.
Successor: **TUSS** (MERL, ICASSP 2025) — prompt-driven, 8 prompts including
`musicbg` (= background music as one stem); AGPL-3.0-or-later.

### Music stem separation (vocals/drums/bass/other)

| Tool | License | Quality | Note |
|---|---|---|---|
| **Demucs htdemucs** (Meta) | MIT (code+weights) | 9.00 dB SDR MUSDB-HQ | best all-round permissive baseline; CPU ~1.5× duration |
| BS/Mel-Band RoFormer | MIT (impl) | SOTA, SDX'23 winners | GPU practically required; run via msst |
| **msst** (ZFTurbo) | MIT | reference impl of SOTA | `pip install msst`; one CLI over htdemucs/roformer/mdx23c/apollo/bandit |
| MDX-Net / python-audio-separator | MIT | very good | 46+ models, CPU supported |
| Spleeter (Deezer) | MIT | aging baseline | superseded |
| Open-Unmix | MIT code; umxl weights CC BY-NC-SA | baseline | umxl weights are the stronger set |
| Apollo | CC BY-SA 4.0 | — | NOT separation; it's restoration (wrong tool) |

### Music identification / recognition

| Service | Kind | Output | Note |
|---|---|---|---|
| **AudD** | production API | **enterprise endpoint returns every track WITH start/end timestamps + confidence** | only ID service returning per-timestamp results on long mixed audio |
| ACRCloud | production API | JSON match + metadata | broadcast-grade; offset/confidence not documented publicly |
| ShazamIO | OSS (reverse-engineered) | title/artist/links | 12 s signature; "from 15 s up finds nothing"; fails on narration-heavy mix |
| Chromaprint/AcoustID | OSS fingerprint | AcoustID ID + score 0–1 | exact-recording dedup only; explicitly "not general-purpose" |
| Dejavu | OSS | `results[]` with `confidence` + `offset_seconds` | self-hosted DB only; good schema reference |

Key point: **all music ID requires separation first.** A track drowned under
narration will not fingerprint. So separation (Area 1-A) is a prerequisite for
identification (Area 1-C), not an alternative.

### Music understanding (mood / energy / tempo / key)

**Essentia `streaming_extractor_music` (MTG-UPF)** — the richest reusable
descriptor schema found: JSON with `lowlevel.*` (loudness_ebu128,
dynamic_complexity, silence_rate), `rhythm.*` (bpm, beat positions, onset_rate,
danceability), `tonal.*` (key, chords), `highlevel.*` (MTG-Jamendo mood-theme
56 classes, arousal/valence, genre, voice/instrumental, TempoCNN).
License: **Essentia AGPL-3.0; MTG models CC BY-NC-SA 4.0**.

### Datasets / label schemas

- **DnR (Divide and Remaster)** — CC BY 4.0; 60 s mixtures; stems
  `mix/music/speech/sfx` + `annots.csv`. The tri-stem schema to adopt.
- **SDX'23 Cinematic (CDX)** — target classes dialogue / sound effects /
  music — the same 3-way schema.
- MUSDB18-HQ — non-commercial; the standard MSS eval set.
- MTG-Jamendo — 195 tags (genre/instrument/mood-theme); metadata CC BY-NC-SA.
- **"MoMuSAD": unverified** — no primary source; likely a conflation of
  MoisesDB / DnR / SMAD.

### Adopt for our data model

- Separation: Cocktail Fork/MRX (or TUSS `musicbg`) → three stems feeding
  `vocal_delivery`, `audio_events`, `music_cues` respectively.
- Music understanding: Essentia descriptor JSON → `MusicCue` fields
  (energy, arousal, mood, rhythm) with `identity_verified` still gated.
- Music ID: only attempt on the separated `music.wav`, never the mix.

## Area 3: speech, prosody, laughter (COMPLETE)

### ASR with word timestamps

| Tool | License | Word timestamps | Note |
|---|---|---|---|
| Whisper (OpenAI) | MIT (code+weights) | approximate (segment-level) | the reason WhisperX exists |
| faster-whisper | MIT | yes, `Segment.words[{start,end,word,probability}]` | CTranslate2; bundles Silero VAD; int8 on CPU |
| **WhisperX** | BSD-2-Clause (bundled pyannote CC-BY-4.0) | **accurate via wav2vec2 forced alignment** | VAD→ASR→align→diarize pipeline; numbers/currency tokens get no timing |
| NVIDIA NeMo (Parakeet/Canary) | Apache-2.0 framework; models CC-BY-4.0 | yes, per-word + speaker | diarization built in; self-contained, no separate model download step |

### Diarization / VAD

- **pyannote.audio** — code MIT; **models distributed through HF repos**.
  `community-1` and `precision-2` tiers; outputs turns / RTTM.
- **Silero VAD** — MIT, ~2 MB, CPU 30 ms in <1 ms, timestamped speech regions.
- **WebRTC VAD** — BSD-3-Clause; boolean per 10/20/30 ms frame, no probability.

### Forced alignment (critical: our transcripts are user-supplied)

- **Montreal Forced Aligner (MFA)** — MIT, Kaldi-based, word AND phone-level
  alignment from a known transcript, TextGrid output, pretrained English
  models + dictionaries. The strongest fit for aligning a supplied verbatim
  script to audio.
- **Gentle** — MIT, tolerant of disfluencies (good for commentary), but
  effectively frozen since 2016; Docker is the practical route.
- **aeneas** — AGPL-3.0; DTW sync, not designed for word level.

### Prosody — the adoptable schema

- **openSMILE** — the most valuable reusable prosody schema found: fixed,
  named feature vectors. **eGeMAPSv02 = 25 LLD / 88 functionals**;
  **ComParE_2016 = 65 LLD / 6373 functionals**; GeMAPS 62. LLD (frame-level)
  vs Functionals (utterance-level) is exactly the two-resolution split our
  `VocalDelivery` record wants. CPU, RTF ~0.08.
- **Praat/Parselmouth** — GPL-3.0; raw F0, intensity, formants,
  jitter/shimmer/HNR. Best for pitch/energy *curves* as acoustic evidence.
- disVoice (MIT), pyAudioAnalysis (Apache-2.0) — broader feature sets, no
  standardized named schema.

### Laughter / sarcasm / emotion

- **Laughter: usable but domain-mismatched.** jrgillick/laughter-detection
  (MIT) emits `(start, end)` laugh segments + TextGrid; trained on
  **Switchboard** conversation, not comedy; semi-stale (2024).
  StandUp4AI (3,617 stand-up videos, 128k laughter labels), SMILE (887 clips,
  CC-BY-4.0, laugh-reasoning), ComParE 2013 laughter sub-challenge.
- **Sarcasm: NOT usable as tooling.** MUStARD/MUStARD++, PodSarc, MuSaG are
  research corpora; ProSarc (2026) is paper-only with no released code or
  weights. **No packaged, maintained sarcasm detector with an API or output
  schema exists.** Corpora are scripted/spontaneous-but-not-gaming, so
  transfer to a comedic DS3 narrator is unproven. Genuine gap.
- Emotion datasets: RAVDESS (CC BY-NC-SA), CREMA-D (ODbL),
  **MSP-Podcast** (409 h naturalistic podcast speech, V/A/D + 9 categorical,
  academic license) — closest to real narration.

### Adopt for our data model

- Transcript→timeline: **MFA** on the user-supplied script (keeps original
  spelling, E0) with WhisperX word timestamps for anything unaligned.
- Speaker: pyannote `community-1` or NeMo diarization → `Utterance.speaker`.
- Prosody: **eGeMAPSv02's 88 functionals as the named column schema** for
  `VocalDelivery` — a standard, citable feature vocabulary instead of
  ad-hoc field names; Parselmouth F0/energy curves as the per-frame evidence.
- Sarcasm: treat as **E2 interpretation only**, never a detector output —
  consistent with PROVENANCE.md ("No inferred sarcasm from audio solely on
  volume"). This is a real gap, not a solved detection problem.

## Area 4: loudness / mix measurement + broadcast QC (COMPLETE)

### Measurement standards (the canonical vocabulary)

- **ITU-R BS.1770-5** — *the* algorithm spec: K-weighting (head shelving +
  RLB high-pass), 400 ms blocks overlapping 75%, two-stage gate = absolute
  **−70 LKFS** then relative = (gated loudness) **−10**; unit **LKFS**
  (= LUFS); true-peak (inter-sample) estimation. Annex 1 = 3/2 multichannel,
  Annex 3 = advanced configs (BS.2051), Annex 4 = object-based. **No
  speech/dialogue gating in the spec** — that is Dolby/Netflix/EBU-adjacent.
  Free. **Adopt its metric names verbatim.**
- **EBU R 128 + Tech 3341/3342/3343/3344** — R 128 normalises to
  **−23 LUFS ±0.2 LU** (live ±1), relative gate −10 LU. **3341** = "EBU
  Mode" metering: **Momentary (400 ms) / Short-term (3 s) / Integrated**.
  **3342** = **LRA (Loudness Range)**: 10th–95th percentile spread of
  short-term loudness, deliberately ignoring the top ~5%. **3343** =
  production guidelines; **3344** = distribution/reproduction (AC-4, MPEG-H).
  Supplements: s1 short-form, s2 streaming, s3 radio, s4 cinematic.
  Reference signal 500–2000 Hz pink noise @ −23 LUFS. Free.
  **Adopt the meter-mode vocabulary (M/S/I/LRA, LU vs LUFS) — the single
  most adoptable naming scheme for a mix-timeline data model.**
- **Netflix Sound Mix Spec** — **dialogue-anchored**: average loudness
  **−27 LKFS ±2 LU, dialogue-gated**; peaks **≤ −2 dBTP**; **Program LRA
  4–18 LU** and **Dialogue LRA ≤ 7 LU**. Proprietary/public doc. Reusable
  concept: **dialogue-gated loudness as a separate metric alongside program
  loudness**, plus separate program-range vs dialogue-range targets. The
  partner-help page is JS-rendered and has moved; values corroborated by
  vendor KBs (RTW, production-expert) rather than read off the primary page.
- **Dolby dialnorm / Dialogue Intelligence** — **dialnorm** = metadata in
  AC-3/E-AC-3/Atmos, scale **−31 to −1 dB**, traditionally = measured
  average dialogue level; a decoder-level gain offset, not a sample change.
  **Dialogue Intelligence™** = speech-gating: loudness measured only on
  dialogue-bearing segments (rationale: dialogue sits at a fixed level and
  everything else is mixed around it). Dolby publishes the **speech-gating
  reference code free** under an EULA. Reusable: dialnorm is a single anchor
  field; Dialogue Intelligence is a reusable speech-gating *method*.

### Implementations (drop-in measurement)

- **pyloudnorm** — OSS (Python), **MIT**; BS.1770-4 integrated + Tech 3342
  LRA; `Meter.integrated_loudness()`, `Meter.loudness_range()`; pluggable
  filter classes (default BS.1770, DeMan, Fenton/Lee, Dash). **No true-peak.**
- **libebur128** — OSS (C), **MIT**; M/S/I modes, LRA, true peak, sample
  peak; live fns `ebur128_loudness_window()`, `ebur128_prev_true_peak()`,
  `ebur128_relative_threshold()`. The de-facto reference C implementation.
- **FFmpeg `ebur128`** — LGPL, already in our stack. Logs M/S/I/LRA at 10 Hz;
  `peak=none|sample|true`; `metadata=1` → 100 ms frames with `lavfi.r128.*`
  keys. **Exported values: `integrated` (LUFS), `range` (LU), `lra_low`,
  `lra_high` (LUFS), `sample_peak`, `true_peak` (dBFS).**
- **FFmpeg `loudnorm`** — options `I` (−70…−5, def −24), `LRA` (def 7),
  `TP` (def −2), `measured_I/LRA/TP/thresh`, `offset`, `linear`, `dual_mono`,
  `print_format=summary|json|none`. Two-pass = measure then apply.
  **The exported names + `loudnorm` JSON fields are a ready-made per-file
  schema.**
- **Essentia `LoudnessEBUR128`** — AGPLv3. Momentary/short-term/
  integrated + LRA; K-weighting exposed; −70 LUFS absolute gate.
- **DR meter** (Pleasurize/MAAT, proprietary) — **DR = improved PLR
  (peak-to-loudness ratio)**; real-time meter looks at the loudest 20% of the
  instantaneous signal; **DR_i is integrated** (whole-track, offline only).
  Deliberately distinct from LRA (which ignores the top 5%). The DR integer
  is a widely-recognised coarse dynamic-range tag ("DR14"); algorithm
  proprietary/loosely specified.

### Broadcast / streaming QC systems and their data models

- **EBU QC / qc.ebu.io XML Schema** (`github.com/ebu/qc`) — **the strongest
  reusable report schema found.** `qc.xsd` defines `Report (QCReportType)`,
  `Profile`, `Item (QCItemType)`, `ItemResult (QCItemResultType)`,
  `ItemDefinition`. Fields: `EBUQCID`, `EBUQCName`, `AnalysisMethodUsed`,
  `ExecutionStatus`, `CheckResult`, `Severity`, `DetectionMethod` enum =
  **automatic / human / assisted**, `Relevance` (0–10), `RuleType` =
  AND/OR/MinimumRelevance, `CardinalityType`, `LocatorType`
  (Start/End/SpatialRegion), `Inputs`/`Outputs` with `Value`/`Unit`/
  `ValueRange`, `Confidence` (0–1), `Annotation`, `ToolInformation`.
  Externally managed controlled lists: `EssenceType`, `LayerType`,
  `CategoryType`, `AnalysisMethodType`, `UnitType`, `RepresentationType`.
  **Adopt this Item/ItemResult + Severity + Locator + Confidence skeleton
  for mix-event findings.**
- **AMWA AS-11 UK DPP** — constrained MXF + DPT XML metadata. Audio fields:
  `UKDPP_Audio_Loudness_Standard` enum **`Loudness_None`(0) /
  `Loudness_EBU_R_128`(1)**; `AS_11_Audio_Track_Layout`, primary/secondary/
  tertiary language, audio-description flags. Field-level vocabulary only;
  it *points at* R 128 rather than measuring. No per-event mix vocabulary.
- **Commercial file-based QC** (Telestream Vidchecker/Aurora, Interra BATON,
  Tektronix Aurora) — proprietary/closed, no public schema. Useful only as a
  **feature checklist** of what QC measures: loudness target, true peak, LRA,
  per-track checks, timeline-of-faults.

### Research: ducking / music-swell / mix-move detection

- **Torcoli, Freke-Morin, Paulus, Simon, Shirley — "Preferred Levels for
  Background Ducking…", JAES 67(12):1003–1011, 2019** — **the key ducking
  paper** (Fraunhofer IIS / Salford / AudioLabs Erlangen). Defines ducking
  *broadly*: "any time-varying background attenuation with the aim of making
  the foreground speech clear" (broader than side-chain compression).
  Defines **Loudness Difference (LD)** = integrated loudness (BS.1770-4 /
  R 128, in LU) between foreground speech and background. Recommends
  **≥10 LU for CoM (Commentary over Music), ≥15 LU for CoA (Commentary over
  Ambience)**. Context: German public broadcasters ≥7 LU (16–23 LU for VoV);
  UK DPP min 4 LU separation. **The closest thing to a ducking parameter
  vocabulary in the literature**: splits ducking into **level parameters**
  (LD during ducking) and **time constants** — **attack, release, shift time**
  (attack offset before speech), **hold time** (prevents pumping across short
  gaps). **Adopt these as our ducking-event field names.**
- **Geary, Torcoli, Shirley et al. — "Loudness Differences for Voice-over-
  Voice…", JAES 2020 + VoV-DB** — ducking practices of **9 expert engineers**
  vs preferred LD of 13 non-expert listeners; documents actual broadcast VoV
  LD values. VoV-DB: **CC BY-NC 3.0** (3 stereo PCM 48 kHz/24-bit .mov +
  transcripts). Corpus + empirical LD targets; no formal schema.
- **Torcoli et al. — "Speech Loudness in Broadcasting and Streaming",
  AES 156th, 2024 (arXiv:2405.17364)** — **the most directly reusable
  vocabulary for "is music too loud under narration".** Beyond program
  loudness: **speech-gated loudness** (VAD-gated "anchor" loudness), **SL**
  (clean speech loudness), **SLD (Speech Loudness Deviation)** = short-term
  speech loudness − integrated clean-speech loudness (0 LU = program speech
  level; critical threshold **−10 LU**), **SBLD (Speech-to-Background
  Loudness Difference)** = speech − background loudness (macroscopic and
  short-term ~1 s; critical threshold **0 LU**), **critical speech
  percentage** = share of speech that is likely hard to understand. Uses a
  DNN to isolate speech when clean speech isn't available.
- **Venkatesh, Moffat et al. — YOHO (arXiv:2102.09959 / 2109.00962, 2021)** —
  radio-DJ-style synthetic mixes with **randomised fade curves and ducking**,
  trained for **music-speech detection**. Frame classes **music / speech /
  both / none**; outputs per-class presence + start/stop, 0.307 s rows.
  Reusable: a presence/start/stop label scheme for music-vs-speech overlap;
  ducking here is a synthesis parameter, not a labeled event.
- **Reiss & Brandtsegg — "Applications of Cross-Adaptive Audio Effects…",
  Frontiers in Digital Humanities 5:17, 2018** (CC BY) — taxonomy after
  Verfaille 2006: non-adaptive → adaptive → auto-adaptive → external-adaptive
  → **cross-adaptive** → networks. Places **ducking / side-chain compression**
  and the **automixer** (Dugan 1975) inside it; MIMO architecture (signal
  path + side-chain feature-extraction + feature-mapping). A control-
  architecture taxonomy, not a labeled mix-event schema.
- **Audio-Oscar (arXiv:2606.07397, 2026)** — post-production mixing agent;
  enumerates **gain adjustment, fade-in/out, crossfade, volume envelope,
  ducking, panning, equalization, compression, reverberation**, emits
  structured JSON per segment. No formal labeled taxonomy — a usable
  operation-name list for a mix-move enum. Code: `github.com/ziye26/Audio-Oscar`.

### Adopt for our data model

- **Measurement vocabulary: EBU R 128 / ITU-R BS.1770-5** — M/S/I/LRA,
  LU/LUFS, K-weighting, the −70 absolute + −10 relative gates, true peak.
- **Finding/report schema: EBU QC `qc.xsd`** Item/ItemResult + Severity +
  Locator + Confidence.
- **Mix-event vocabulary: Torcoli 2019** ducking parameters (LD, attack,
  release, shift, hold) + **Torcoli 2024** speech/background metrics (SLD,
  SBLD, critical speech %).
- **The decisive gap:** "mix move" detection as a reusable *labeled editorial
  schema* does **not** exist. There is no published taxonomy of duck / swell /
  stinger / sting-out / crossfade / silence-for-comedy. Ducking specifically
  has real research with reusable parameters and empirical LU targets, and
  music-vs-speech segmentation is well covered, but the editorial comedic-mix
  event taxonomy must be **built by us** — borrow the metric definitions, not
  a schema.

## Area 5: game audio middleware + edit/timeline schemas (COMPLETE)

### Game audio / music systems — the conceptual model

The industry vocabulary for "what kind of audio event is this" comes from
the middleware, not from ML. Adopt the vocabulary; no public schema exists.

- **FMOD Studio** (proprietary) — Project = folder tree of **Events**
  (the triggerable unit: 1D/2D/3D/Complex); each Event is a timeline of
  **Tracks** holding **Instruments**. **Buses + VCAs + Sends** = the mixer;
  **Snapshots** capture mixer state per context. Adaptive music = **Music
  Segment** (bar-quantized clip with tempo/meter) arranged with **Transition
  Regions** + **Transition Markers** for horizontal resequencing, and
  parameter-driven vertical layering. **Stingers** = one-shot triggers (on
  beat/bar/parameter-crossing); **Cues** = quantized trigger points inside
  segments. Bank files are machine-readable: OSS `Fmod-Bank-Tools`
  (GPL-3.0) and `FMOD-Decompiler` reconstruct the event tree from
  `.bank`/`.fspro` — useful as reference corpora.
  Docs: `fmod.com/docs/2.04/studio/mixing.html` (JS-rendered).
- **Wwise (Audiokinetic)** — the richest explicit music taxonomy. **Event**
  contains typed **Actions** (Play, Stop, Pause, Seek, SetSwitch, SetState,
  SetRTPC, Trigger, PostEvent). **Game syncs** = States (discrete global,
  e.g. music-state explore/combat/boss), Switches (per-object variants),
  RTPCs (continuous parameter curves), Triggers. Music hierarchy: **Music
  Switch Container** (state-driven segment choice = horizontal resequencing)
  → **Music Playlist Container** (layered tracks = vertical remixing) →
  **Music Segment** (bar-quantized, **Entry Cue / Exit Cue** sync points) →
  **Music Track**. **Transitions** are first-class objects with rules
  (crossfade, sync to beat/bar/next-bar, exit-cue). **Stingers** are a
  dedicated type, triggered by Events, synced to cues.
  Docs behind captcha/403; vocabulary documented via community guides
  (`synchrnzr.com`, Audiokinetic blog "About Dynamic Music Design") and the
  OSS Gyms sample project (`deepwiki.com/audiokinetic/Gyms`).
- **Unity Audio** (engine) — **AudioSource** → **AudioClip** → tree of
  **AudioMixerGroups** inside an **AudioMixer**; per-group effect chain +
  send/return; **Snapshots** capture all group params with a blend time;
  **Ducking** lowers one bus by another. No built-in adaptive-music
  sequencer — vertical layering is hand-rolled. Clean minimal "what is a
  bus" reference.
- **Unreal Engine 5 MetaSounds** — node-graph DSP render graph (replacing
  legacy Sound Cue), **sample-accurate Triggers**, audio-rate parameter
  modulation, graph I/O exposed to gameplay. **Submixes** = bus graph;
  **Audio Modulation** plugin = parameter buses. No Music-Segment/Stinger
  object; adaptive music is built procedurally. Borrow "trigger / parameter
  / sample-accurate cue point" for *timing* stingers and transitions.
- **Godot 4 (`AudioStreamInteractive`)** — **the closest thing to a
  borrowable open spec** for music-transition semantics. Clips + an explicit
  **transition table** with enums: `TransitionFromTime` (IMMEDIATE /
  NEXT_BEAT / NEXT_BAR / END), `TransitionToTime` (SAME_POSITION / START /
  PREVIOUS_POSITION), `FadeMode` (DISABLED / IN / OUT / CROSS / AUTOMATIC),
  plus `hold_previous` / `AUTO_ADVANCE_RETURN_TO_HOLD`. Also
  `AudioStreamPlaylist` and `AudioStreamSynchronized` (parallel layers =
  vertical remixing). Documented, MIT, lift almost verbatim as our
  "music transition event" schema.
- **Adaptive-music theory vocabulary** (non-spec, citable) — **horizontal
  resequencing** (switch pre-composed segments), **vertical remixing/
  layering** (add/remove stems), **stingers** (short one-shot accent),
  **transition matrices / cue sync**. The right ontological layer above the
  engine-specific terms.
- **AudioSet Ontology** (CC BY-SA 4.0) — the 632-class hierarchical
  vocabulary, `ontology.json` fields `id, name, description, citation_uri,
  positive_examples, child_ids, restrictions`; 7 top branches; depth ~6.
  Not game-specific, but its **Music / Music mood** and **Sounds of things**
  branches are a licensed, ML-tested baseline to *extend* with a game-audio
  branch (footstep→armor, spell-cast, boss-stinger, menu-click).

### Game-audio ML — honest status: thin

- **BattleSound** (Sensors 2023) — SED benchmark for *one* battle game, for
  haptic-feedback timing; MDPI blocks scraping, class list/size unverified;
  likely small and single-game. The only clearly game-specific SED dataset
  found.
- **No Dark Souls–specific audio dataset or ML paper exists.** Dark Souls
  scholarship is musicological only — "From epic fail to epic music: music,
  silence and failure on Dark Souls 3" (ResearchGate 355096297) and "Sonic
  Spaces in Dark Souls" (firstpersonscholar.com) — useful as *qualitative*
  priors (DS3 music is stateful: silence in exploration, choir-driven boss
  themes with phase-shift stingers) but not trainable resources.
- General SED ecosystem (DCASE 2024 Task 4; the 69-dataset audio-language
  survey arXiv:2407.06947) exists but none is game-audio-specific.
- **Conclusion:** build the game-audio event vocabulary from the middleware
  taxonomies (FMOD/Wwise/Godot `AudioStreamInteractive`) + an AudioSet
  extension, and bootstrap a small annotated dataset from the VODs.

### Reverse-engineering the video edit — the timeline schema

- **OpenTimelineIO (OTIO)** (Apache-2.0, ASWF) — **the one to adopt.** Root
  **Timeline** → **Stack** ("tracks") → **Track** (kind "Video"/"Audio") →
  ordered **Composable** items: **Clip**, **Gap**, **Transition**, or nested
  Stack/Track.
  - **Clip**: `source_range` (TimeRange into media) + `media_reference`
    (`ExternalReference` with `target_url` + `available_range`, or
    Missing/Generator); `trimmed_range()` resolves usage.
  - **Gap**: transparent empty time; a 0-length Gap at track start is the
    canonical fade-from-black placeholder.
  - **Transition**: `transition_type` (`SMPTE_Dissolve`, `Custom_Transition`)
    + `in_offset`/`out_offset`; does not change track length; must sit
    between exactly two composables; cannot overlap another transition.
  - **Marker**: `marked_range` + `color` + `comment` — **our hook for tagging
    detected edit-intent** (jump-cut, speed-ramp, music-stinger) inline.
  - **Effect** / **LinearTimeWarp** (`time_scalar`) — the built-in schema for
    **speed changes**, i.e. speed-ramp/retiming detection.
  - Serialization: JSON `.otio`; every object tagged
    `"OTIO_SCHEMA": "Timeline.1"` / `"Clip.2"` (per-type versioning);
    free-form `metadata` dict on every object. Audio tracks are additive;
    video compositing is painter-order; effects deliberately unspecified.
  - Adapters (`OpenTimelineIO-Plugins`): `cmx_3600` (EDL), `fcp_xml`,
    `fcpx_xml`, `aaf`, `ale`, `svg`, `xges` — adopting OTIO buys free
    EDL/FCPXML/AAF import-export.
- **CMX3600 EDL** (de-facto standard) — flat ordered text cut list: header
  `TITLE:` + `FCM:`; event lines `NNN REEL AA/V C SRC-IN SRC-OUT REC-IN
  REC-OUT`; edit types `C` (cut) / `D` (dissolve, paired with frame-count) /
  `W` (wipe); `*` comment lines keep clip names; 4 audio channels max; 999
  events max. **Export surface only, not our internal model** (no nesting,
  metadata, or markers).
- **FCPXML** (Apple) — document tree `event → project → sequence → spine →
  clip` (+ connectedClip/gap/title/effect); exact rational time (`120/30s`);
  assets referenced by `id`; `roles` for dialogue/music tagging. Single-vendor
  and deep; prefer OTIO as canonical, read FCPXML via the OTIO adapter.
- **PySceneDetect** (BSD-3) — the practical shot-boundary workhorse.
  Detectors `ContentDetector` (HSV diff), `AdaptiveDetector` (two-pass,
  camera motion), `ThresholdDetector` (fades), `HashDetector`,
  `HistogramDetector`. **v0.7.1 exports `write_scene_list_otio`** — emits
  `Timeline.1` → `Stack.1` → `Track.1` → `Clip.2` → `ExternalReference.1`
  (video + optional audio track), plus CSV/HTML/EDL/FCPXML/FCP7. **So
  PySceneDetect alone gives shot boundaries → OTIO in one step.**
- **ffmpeg `scdet` / `select='gt(scene,t)'`** — zero-dependency baseline;
  `select` exposes a `scene` variable; `scdet` sets `lavfi.scd.score` +
  `lavfi.scd.mafd` with threshold/duration. Good fast pass-1 candidates,
  weaker on graduals.
- **TransNetV2** (MIT; arXiv 2008.04838) — 3D-ConvNet SBD, per-frame
  transition probabilities (single/double/gradual), trained on ClipShots,
  evaluated on RAI + BBC Planet Earth; still the standard deep baseline
  (AutoShot beats it by only +4.2% F1). Its per-frame probability stream is
  the "cut-ness" signal to threshold into OTIO Transitions.
- **Datasets:** **ClipShots** (MIT; YouTube/Weibo 1–20 min, 20+ categories
  incl. handheld jitter — relevant to gameplay-with-commentary camera
  motion; classes **cut** + **gradual**{dissolve, fade, slide});
  **RAI** (988 shots / 198 gradual; the standard gradual-transition test
  set); **AutoShot / SHOT** (arXiv 2304.06116; 853 short videos, 11,606
  shot annotations — closest to our short-edited-video input type).
- **Editing-style / cut-intent research — thin, no dominant benchmark:**
  "Tools for placing cuts and transitions in interview video"; "Computational
  Video Montage from Themed Text" (explicit jump-cut predicate between
  neighbouring shots); **EditIQ** (arXiv 2502.02172 — parameterized
  editing-style generator, static wide-angle footage); "An Attentional
  Theory of Continuity Editing" (Smith 2006 — *why* cuts go where they do;
  our hypothesis layer); "The neural impact of editing on viewer narrative
  cognition" (2025). **No reusable schema or dataset** — treat "editing
  style" as an open modeling problem.

### Adopt for our data model

- **Edit-timeline schema: OpenTimelineIO.** Map `EditEvent` onto
  `Clip`/`Transition`/`Marker`; our half-open `[start_ms, end_ms)` onto OTIO
  `RationalTime` ranges; `LinearTimeWarp` for speed-ramps; free-form
  `metadata` dicts for our evidence/provenance. PySceneDetect already emits
  OTIO, and adapters give EDL/FCPXML/AAF for free.
- **Music-transition vocabulary: Godot `AudioStreamInteractive`'s enums**
  (`TransitionFromTime`, `TransitionToTime`, `FadeMode`, hold/auto-advance)
  as the compact, documented, borrowable spec; FMOD/Wwise terms (Event,
  Bus, Snapshot, Music Segment, Entry/Exit Cue, Stinger, Switch, State,
  RTPC) as the label space above it.
- **Game-audio event labels: extend the AudioSet ontology** (CC BY-SA 4.0)
  with a game-audio branch via our `ext:<slug>` escape hatch; bootstrap the
  Dark Souls corpus from the VODs themselves.
- **The gap:** game-specific audio ML is genuinely thin — no DS3 dataset,
  one small single-game SED benchmark. Our own annotated VODs are the
  resource.
