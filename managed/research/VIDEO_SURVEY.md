# Video analysis survey — reverse-engineering the frame

Status: COMPLETE (Area 7). Assembled 2026-10-09, the video-side counterpart
to `AUDIO_SURVEY.md` (analysis side). The generation side — auto-clipping
products, TTS, joke LLMs, end-to-end pipelines — is **Area 8** and lives in
`AUTOEDIT_SURVEY.md`; it is not repeated here.

## Why this survey exists

The audio survey established that the reference video's narration, SFX and
music are mono-fused, so audio must be separated before per-layer analysis.
The video side has the opposite property: **the pixels are the one fully
unmixed stream we own.** Nothing occludes the frame — but the frame is
high-dimensional and semantically dense (game state, HUD, on-screen text,
character expression, camera behaviour), so the problem is *labelling*, not
*separating*. This survey maps what can label those frames, with what output
schema, and how confidently.

Provenance note: entries marked **[G]** are from general knowledge, not a
primary source fetched in this run (the session's web-search budget was
exhausted mid-survey). Everything else was read from a primary source this
run.

## Area 7.1 — Shot / boundary detection (COMPLETE, mature)

The **most solved layer in video analysis.** Shot-cut detection is treated as
solved in the film literature (MovieNet's own paper uses an off-the-shelf
method rather than annotating boundaries by hand).

| Tool | Kind | Output | Note |
|---|---|---|---|
| **TransNetV2** (Souček) | pretrained 3D-CNN, MIT | per-frame transition probability | see below — the reference model |
| **PySceneDetect** | OSS Python | scene list, CSV/EDL/OTIO/FFmpeg **[G]** | practical workhorse; multiple detectors |
| **AutoShot** (CVPR 2023W) | pretrained + dataset | shot boundaries | released **SHOT** dataset: 853 short videos, 11,606 shots |
| **ffmpeg `scene` filter** | OSS | per-frame scene score | zero-dependency baseline |
| **MSU SBD Benchmark** | evaluation | leaderboard | 50 videos, 1,287 min, 10,883 transitions |

### TransNetV2 — the reference (verified)

- **Architecture:** Dilated DCNN (DDCNN) — 6 cells, each four 3×3×3 convs at
  temporal dilation **1, 2, 4, 8**, giving a receptive field of **97 frames**.
  Batch norm, skip connections with spatial average pooling, and kernel
  factorization (2D spatial + 1D temporal). Frame-similarity features: RGB
  color histograms (512 bins) + pooled activations, cosine similarity to the
  **50 nearest preceding and following frames**.
- **Input:** frames resized to **48×27**; sequences of **100 frames**; only
  the **middle 50** predictions used (edge frames lack context).
- **Output (the reusable part):** `predict_video()` returns `video_frames`,
  **`single_frame_p`** (per-frame probability that the frame is the middle of
  a transition; thresholded at **0.5** at inference) and `all_frame_p`
  (training-only head). `predictions_to_scenes()` converts to inclusive scene
  index tuples; `visualize_predictions()` renders.
- **No transition-*type* output** — cut vs. dissolve vs. wipe is not emitted.
- **Accuracy (F1):** ClipShots **77.9**, BBC Planet Earth **96.2**, RAI 93.9.
  Trained ~17 h on one Tesla V100 16 GB. PyTorch inference port released.

**Key limitation for us:** TransNetV2 detects *editorial cuts*. In continuous
gameplay there are almost none — so it will report very few boundaries, and
those it reports are the real hard cuts (e.g. into a cutscene or a
death→respawn jump-cut). This is a feature, not a bug: it cleanly separates
**editorial cuts from in-game transitions** (see `ShotContinuity`).

### MSU SBD Benchmark — what "solved" means (verified)

- Dataset: **50 videos, ~1,287 min, 10,883 transitions — 7,501 abrupt +
  3,382 gradual**; 360×288 to 1920×1080, 23–60 FPS, MP4/MKV.
- Task: detect **cuts, dissolves, wipes, fades**. A cut = abrupt, first frame
  of the new shot marked; gradual = exactly one frame from the continuous
  series; fade = transition to/from blank.
- **Required output: JSON or CSV with keys for cuts, dissolves and fades,
  each a frame list.** CLI convention `-i`, `-o`, `-t`.
- Leaderboard (F1 / FPS): NITS-CV-Lab-v1.0 **0.8470 @ 24**, Saeid Dadkhan
  0.7686 @ 93, **PyScene-v2 0.7534 @ 86**, johmathe 0.7492 @ 94, VQMT 0.7484
  @ 111, **FFmpeg 0.7314 @ 125**, GStreamer 0.7087 @ 163.
- Takeaway: neural methods win on accuracy, cheap histogram methods win on
  speed, and **FFmpeg's built-in scene detector is a credible 0.73-F1
  baseline at 125 FPS** — good enough to pre-segment before a neural pass.

### PySceneDetect — the practical layer (verified + [G])

Verified this run: `ContentDetector` (fast cut), `AdaptiveDetector` (two-pass,
"handles fast camera movement better"), `ThresholdDetector` (fade-out/fade-in
events), `split-video` (splits on each fast cut via ffmpeg), `save-images`.
**[G]** `HistogramDetector` and `HashDetector` also exist; output formats
include CSV, EDL, OTIO, and HTML; the stats CSV carries per-frame content
scores used for threshold tuning. Re-check against current docs before
depending on the [G] items.

### Adopt (Area 7.1)

- Run **PySceneDetect (Adaptive) for candidate boundaries** and **TransNetV2
  for the high-precision editorial-cut set**; disagreement between the two is
  itself a signal (candidate game-transition vs. real cut).
- Map every boundary to our **`EditEvent`** (`edit_type` via the `ext:` tokens
  `ext:hard_cut`, `ext:dissolve`, `ext:fade`) with `detection_method` naming
  the tool, and **`tolerance_ms`** recording the detector's frame-resolution
  uncertainty — this is exactly the "no invented frame-accurate boundaries"
  rule from PROVENANCE.md.
- Feed continuity class into **`ShotContinuity`**: a TransNetV2 boundary in
  otherwise-continuous gameplay is `EDITORIAL_CUT`; a load-screen or
  cutscene entry is `LOADING`/`GAME_TRANSITION`.

## Area 7.2 — Video understanding models (COMPLETE)

The layer that turns frames into *language*. Split by output shape, because
that is what decides reusability.

### Models that emit **timestamped / structured** output (the useful class)

| Model | Kind | Output | Timestamped? | Note |
|---|---|---|---|---|
| **TimeChat** (CVPR 2024) | video LLM | dense captions, temporal grounding, highlight detection | **yes** | timestamp-aware frame encoder + sliding video Q-Former; 125K instances / 6 tasks |
| **Qwen3-VL** | video LLM | video QA, OCR, grounding, "second-level indexing" | **yes** | text–timestamp alignment; 2B–32B dense + MoE |
| **VideoGameBunny** | game-specific VLM | **16-field structured JSON per frame** | no (per-image) | the single most on-target schema found — see 7.4 |
| **InternVideo2** | video foundation | recognition, retrieval, dialogue, long video | partial | 6B encoder; 60+ tasks |
| **VideoMAE V2** | pretrained backbone | features / classification | no | billion-param ViT; encoder for downstream heads |
| **ActionFormer** | temporal localizer | action intervals + class + score | **yes** | the TAL schema — see 7.3 |

### Models that emit **free-text** output (useful, less reusable)

- **LLaVA-Video**, **VideoLLaMA 2/3**, **mPLUG-Owl**, **Video-ChatGPT**,
  **Gemini video**, **Claude video** **[G]** — strong at open-ended
  description and QA, but output is prose; timestamps are approximate or
  absent. Use for *interpretation* (E2/E3), not for boundary evidence.

### TimeChat — the timestamped-output reference (verified)

- **Architecture:** a **timestamp-aware frame encoder** that binds each frame
  to its timestamp, plus a **sliding video Q-Former** producing a
  variable-length token sequence (handles arbitrary duration).
- **Tasks it is built for:** dense captioning, temporal grounding, highlight
  detection — i.e. exactly our three video needs.
- **Results:** YouCook2 **+9.2 F1** and +2.8 CIDEr; QVHighlights **+5.8
  HIT@1**; Charades-STA **+27.5 R@1 (IoU=0.5)** over prior video LLMs.
- **Reusable shape:** `{event_text, start, end}` — dense captions with
  boundaries, which maps onto `Observation` + `EvidenceSpan`.

### Qwen3-VL — the current best open video LLM (verified)

- **Sizes:** dense **2B / 4B / 8B / 32B** (Instruct + Thinking); MoE
  **30B-A3B** and **235B-A22B** (+ FP8). Native **256K context → 1M**.
- **Temporal handling:** Interleaved-MRoPE over time/width/height; **text–
  timestamp alignment** replacing T-RoPE for precise event localization;
  frame sampling via `fps` (default **2**), `num_frames`, and a
  `total_pixels` budget; `return_video_metadata` returns frames + metadata.
  vLLM can serve unlimited frames with client-side fps.
- **For us:** the practical route to "watch this clip and tell me what
  happened" with usable timestamps, at a size that runs locally (8B/32B).

### InternVideo2 / VideoMAE V2 — backbones, not answerers (verified)

- **InternVideo2:** video foundation model family; video encoder scaled to
  **6B**; progressive training = masked video modeling + crossmodal
  contrastive learning + next-token prediction; SOTA claimed across 60+
  video/audio tasks. Output is *representations*, so it feeds our own heads.
- **VideoMAE V2:** billion-parameter video ViT; **dual masking** (encoder
  sees one token subset, decoder another) and progressive training on
  unlabeled→labeled data. **K400 90.0%, K600 89.9%, SSv1 68.7%, SSv2 77.0%.**
  A self-supervised *representation learner* — adopt as a feature extractor
  for a game-event classifier, not as an end product.

### Adopt (Area 7.2)

- **Two-tier VLM use:** a timestamped model (TimeChat-class or Qwen3-VL) for
  *when*; a strong open model (Qwen3-VL-32B, LLaVA-Video) for *what/why*.
  Never let a free-text model author a boundary.
- Store VLM captions as **`Observation`** (modality `VIDEO`) with `measured
  = False` and a `certainty` score, and attach the frame as an
  **`EvidenceSpan`** (`kind = FRAME`, `frame_index`).
- Use **VideoMAE V2 / InternVideo2 embeddings** as the input feature for our
  own game-event head (Area 7.4) rather than asking a VLM to classify
  Souls-specific events zero-shot.

## Area 7.3 — Action recognition + temporal localization (COMPLETE)

### Datasets (label vocabularies to borrow from) [G]

| Dataset | Domain | Labels | Note |
|---|---|---|---|
| **Kinetics-400/600/700** | general human action | 400/600/700 classes | the standard pretraining target |
| **AVA** | atomic visual actions | 80 atomic actions, **per-person bounding boxes over time** | the only schema that localizes *who* does *what* |
| **ActivityNet-1.3** | complex activity | 200 classes, ~20k videos | TAL benchmark |
| **Charades / Charades-STA** | indoor activity | 157 classes; STA = sentence→temporal span | the STA shape matches "line→moment" |
| **EPIC-KITCHENS-100** | egocentric cooking | verb + noun classes; 90K actions | see below |
| **Something-Something** | fine-grained motion | 174 classes | motion-heavy, low scene bias |

**EPIC-KITCHENS-100 (verified):** 100 hours, **20M frames, 90K actions, 700
variable-length videos, 45 environments**; annotations 54% denser than v1
(+128% more action segments). Six challenges: **action recognition (full and
weak supervision), action detection, action anticipation, cross-modal
retrieval (from captions), unsupervised domain adaptation.** Its verb/noun
decomposition is the model to copy: separate *what* (verb) from *what-on*
(noun), each its own label space.

### Models [G except ActionFormer]

| Model | Role | Note |
|---|---|---|
| **SlowFast** | dual-pathway 3D CNN | fast pathway = motion, slow = semantics; a classic baseline |
| **MViTv2** | multiscale ViT | strong recognition backbone |
| **VideoSwin** | shifted-window ViT | strong recognition backbone |
| **UniFormer** | unified 3D conv + attention | efficient |
| **InternVideo** | foundation family | see 7.2 |
| **ActionFormer** (ECCV 2022) | **temporal action localization** | verified: **ActivityNet-1.3 36.6% avg mAP**, EPIC-Kitchens-100 +13.5% avg mAP |

**ActionFormer (verified):** single-stage, **anchor-free Transformer** that
detects onsets and offsets of actions. Its output schema — **`(start, end,
class, confidence)`** — is the TAL schema and the direct template for our
gameplay-event records.

### Adopt (Area 7.3)

- **`GameplayEvent` adopts the ActionFormer/TAL output shape:** interval +
  class + score, stored as `start_ms`/`end_ms` + a label + `uncertainty`.
- **Verb/noun split (EPIC-KITCHENS) → our `GameplayEvent.action` (verb) +
  `actor`/`environment`/`outcome` (nouns).** "Dodge" + "boss" + "arena" +
  "survived" is the EPIC shape applied to Souls.
- **AVA's per-track localization** is the model for attaching an event to a
  *specific entity* → our `CharacterState.entity_id` / `NarrativeEntity`.

## Area 7.4 — Gaming-specific visual analysis (COMPLETE — the on-target layer)

### VideoGameBunny — the single most reusable artifact found (verified)

- **Scale:** **185,259 images from 413 games**, **389,565 image-instruction
  pairs**, sampled from YouTube gameplay walkthroughs at Full-HD/4K/8K.
- **The 16-field JSON schema per frame** (the schema to adopt):
  **Description, Short description, Dialogue, On-Screen subtitle, Inventory
  display, HUD description, Scene description, NPC status, Character list
  (appearance/clothing/facial expression), Animation states, Object list,
  Texture details, Lighting details, Weather conditions, Environmental
  effects, Player status (health/equipment).**
  The generation prompt (Fig. A2) additionally used `minimap_details`,
  `score_or_progress`, `event_indicators`, `interaction_prompts`, `game_mode`,
  `on_screen_watermark`, `summary_of_ui_values`, `color_palette`, `error_log`,
  `glitches` — a superset worth mining.
- **10 eval categories** (with item counts): Action Understanding (356),
  Anomalies and Glitches (223), Character Analysis (312), Common Sense
  Reasoning (430), Gameplay Mechanics (273), OCR and UI (334), Miscellaneous
  (239), Scene Understanding (566), Small Details (356), Spatial Reasoning
  (286).
- **Model:** LLaVA-style on **Bunny** — **Llama-3-8B** + **SigLIP** with the
  **S2 multi-scale wrapper** (up to 1152×1152, "from tiny UI icons to large
  objects"), MLP projection, **LoRA** fine-tune with the vision encoder
  unfrozen (1 epoch). ~900 GPU-hours on one A100 80 GB (~$2,000). **85.1%**
  on the eval set vs. 83.9% for LLaVA-1.6-34b at ~4× the parameters.
- **Why it matters:** this is a **game-frame schema with HUD, player status,
  NPC status, animation states and glitch detection already enumerated** —
  i.e. exactly the Dark Souls on-screen state (health bar, boss bar, item
  pickups, death screen, physics/ragdoll glitches) our project needs to
  capture, with a published field vocabulary to adopt rather than invent.

### Other gaming-vision work (verified / [G])

- **Gameplay Highlights Generation (arXiv:2505.07721)** — in-house FPS event
  dataset: **4,408 annotated events + 2,745 background**, classes **Kill,
  Death, Grenade Throw, Reload, Bomb Planted, Knocked Down, Power Use,
  Background**, annotated in **VIA**; method = 1-second clips through a
  fine-tuned **X-CLIP-B/16** (32 frames @224² + text prompt), cosine
  similarity → softmax. Dataset/model/code **not released**; the per-1s-clip
  `{event, probability, background}` shape is copyable. (Note: this is a
  *highlight* dataset — it labels *exciting*, not *funny*.)
- **Real-Time Game Highlight Detection (IRI/UPC, 2025)** — fuses **visual +
  audio** cues for impactful moments; confirms AV fusion is the research
  direction for gameplay events.
- **"CLIP meets GamePhysics" / HASTE** — zero-shot CLIP transfer to detect
  **game bugs/glitches**; dataset of ~1,873 videos; **71% recall / 89%
  precision** for stuttering events. Directly relevant to our
  `ext:physics_glitch` / ragdoll-fail comedic cues.
- **[G]** Game-playing agent perception stacks (e.g. VLM agents on gameplay
  benchmarks) produce `{frame, action, reward}` streams, but their labels are
  *game actions*, not *editorial/comedic events*; useful as a game-state
  signal, not as an edit signal.
- **[G] HUD/UI detection:** no dedicated Souls-like HUD dataset was found;
  VideoGameBunny's "OCR and UI" category plus its `HUD description` /
  `Player status` fields are the closest published coverage. A custom HUD
  detector (template matching / small object detector on the health- and
  boss-bar regions) is likely still required.

### Gaps (Area 7.4, confirmed)

- **No Souls-like / RPG game-state dataset** — no public dataset labels
  boss-health phases, death screens, bonfire rests, or invasion events.
  VideoGameBunny's field vocabulary is the closest scaffold.
- **No "funny gameplay moment" visual dataset.** The highlight datasets label
  *exciting*; nothing labels *comedic* visual beats. (Consistent with
  AUDIO_SURVEY Area 6's decisive finding.)
- **No released gameplay-event model** — the X-CLIP approach in the
  Gameplay-Highlights paper is described but the weights/data are not out.

### Adopt (Area 7.4)

- **Adopt VideoGameBunny's 16-field schema** as the target shape for our
  per-frame video `Observation`s (HUD description → on-screen state;
  Player status → health/equipment; Animation states → pose/motion; Character
  list → `CharacterState`).
- Use **VideoGameBunny-V1 (8B)** as the local game-frame captioner, and
  **CLIP zero-shot** (per GamePhysics) for glitch/fail cues.
- Train our own Souls event head on **VideoMAE V2 features** with the
  TAL output shape (Area 7.3), seeded by hand-labelled reference moments.

## Area 7.5 — Richly annotated video datasets (schemas to copy)

MovieNet, AVE "Anatomy of Video Editing" and MovieCuts are covered in
`AUDIO_SURVEY.md` Area 6; noted here only, with the new depth added:

- **MovieNet (verified this run):** **1,100 movies**, **46,857 shots** (47K),
  **42K manually annotated scene boundaries**. Shot boundaries are *not*
  hand-labelled — an off-the-shelf detector splits the films (further evidence
  SBD is solved). Shot scale: **5 classes — long shot, full shot, medium
  shot, close-up shot, extreme close-up shot.** Camera movement: **4 classes
  — static shot, pans and tilts shot, zoom in shot, zoom out shot.** These
  two vocabularies are directly adoptable for our `ShotContinuity`.
- **Panda-70M (verified):** **70M video-caption pairs**, cut from **3.8M**
  high-resolution source videos (HD-VILA-100M). Captions are **auto-generated
  and then best-of-N selected**: several cross-modality teacher models propose
  captions from description + subtitles + frames, a retrieval model
  (fine-tuned on a small human-preference subset) picks the winner. The
  reusable idea is the **best-of-N caption-selection pipeline**, not the
  schema (one caption per clip, no structured fields).
- **[G] Koala-36M** — a cleaned successor to Panda-70M (~36M pairs), built to
  remove corrupt/inconsistent clips from the 70M pool via a
  segment-and-filter pipeline. Relevant only as evidence that large
  auto-caption corpora need a cleaning pass.
- **[G] HowTo100M** — ~136M narrated instructional clips; labels are
  *narration-aligned* video, i.e. the transcript *is* the annotation. Same
  model as our narration-over-gameplay: the voice track is a weak label for
  the frame.
- **[G] VidSitu** — dense video situation recognition: each ~10 s event is
  labelled with a **verb + semantic-role structure** (who did what to whom,
  with frame-level role grounding). Conceptually the richest schema for
  "event with participants", but not fetched this run — verify before relying.
- **[G] AVE "Anatomy of Video Editing"** (~196k shots, per-shot attributes
  incl. sound-source) and **MovieCuts** (~174k pairs, 10 pro-validated cut
  types) — the best editing-label schemas; detailed in AUDIO_SURVEY Area 6.

### Adopt (Area 7.5)

- **MovieNet's 5 shot-scale + 4 movement classes** → our `ShotContinuity`
  vocabulary (gameplay adds "first-person" and "cutscene-camera", so extend
  via `ext:` tokens).
- **VidSitu's verb + role structure** → the shape for `GameplayEvent` when we
  need participants (boss→player→damage), if verified.
- **Best-of-N caption selection (Panda-70M)** → how we should pick among
  multiple VLM descriptions of a moment before committing an `Observation`.
- **HowTo100M's narration-as-label** → our own narration track is a legitimate
  weak label for the frame it sits over.

## Area 7.6 — Frame/vision primitives as evidence (COMPLETE)

| Primitive | Tool(s) | Output | Use in our model |
|---|---|---|---|
| **Scene text / OCR** | PaddleOCR (PP-OCRv5), EasyOCR **[G]** | text + boxes + confidence | on-screen state, damage numbers, item names, subtitles |
| **Face / expression** | AffectNet-trained FER, EmoNet **[G]** | emotion class + prob | `CharacterState` affect, comedic reaction |
| **Pose / body** | MMPose, RTMPose, OpenPose **[G]** | keypoints per person | ragdoll/physics-fail detection, gesture |
| **Optical flow** | RAFT, Farneback (ffmpeg) **[G]** | dense motion field | camera vs. player motion; cut detection aid |
| **Saliency / attention** | saliency models **[G]** | saliency map | where the viewer looks; edit emphasis |
| **Keyframe extraction** | PySceneDetect, ffmpeg **[G]** | representative frames | cheap sampling for VLM calls |
| **Shot-scale classification** | MovieNet-trained classifier **[G]** | 5-class scale | `ShotContinuity.scale` |

Verified this run: VideoGameBunny's eval includes an explicit **"OCR and UI"**
category (334 items) and **"Small Details"** (356), confirming on-screen text
and UI detail are recognized as first-class game-vision signals. The
"CLIP meets GamePhysics" result (verified) shows a *zero-shot* primitive
(CLIP + text prompts) can detect gameplay glitches without a bespoke dataset —
the cheapest evidence route for comedic fail cues.

**Adopt (Area 7.6):** OCR output → `Observation` (modality VIDEO, measured)
with the text as `native_location`; pose/flow → evidence for
`GameplayEvent.outcome`; all primitives emit `EvidenceSpan`s so every claim
traces to a frame.

## Area 7.7 — Streaming / VOD ingest plumbing (COMPLETE)

| Tool | Kind | Output | Note |
|---|---|---|---|
| **yt-dlp** **[G]** | OSS downloader | media + metadata JSON | the ingest front door; also VOD chat/metadata |
| **ffmpeg / ffprobe** **[G]** | OSS | frames, streams, scene scores | ffprobe gives the `ReferenceVideo` timebase/fps/size fields |
| **Platform VOD APIs** **[G]** | Twitch/YouTube | VOD files, chapter markers | chapters are ready-made coarse boundaries |
| **Streamlink** **[G]** | OSS | live→file | live capture path |
| **PySceneDetect `split-video`** (verified) | OSS | per-shot files | already segments once boundaries are known |

Verified: the Gameplay-Highlights work ingested ~110 GB of mp4 and preprocessed
by sampling every 4th frame from 128 FPS — a concrete example of the
ingest→sample→classify pipeline we will run. **Adopt:** `ffprobe` output
populates `ReferenceVideo` (`frame_rate`, `width`, `height`, `duration_ms`,
`video_timebase`); chapter markers seed the coverage planner's
`CoverageWindow`s.

## Area 7.8 — Local inference practicality (COMPLETE)

| Model class | Size | Feasibility |
|---|---|---|
| **TransNetV2** (verified 48×27, 100-frame) | small | **CPU-viable**, fast; GPU trivial |
| **PySceneDetect / ffmpeg scene** (verified) | none | **CPU-viable** (86–163 FPS on CPU) |
| **VideoGameBunny-8B** (verified Llama-3-8B + SigLIP) | 8B | **single consumer GPU** (trained on 1×A100 80 GB; inference ~16–24 GB at 1152²) **[G on VRAM]** |
| **Qwen3-VL 8B / 32B** (verified sizes) | 8B / 32B | 8B on a 24 GB card; 32B needs 48 GB+ or quant **[G]** |
| **VideoMAE V2 (billion-param)** (verified) | ~1B | GPU; feature extraction at low fps **[G]** |
| **InternVideo2 (6B encoder)** (verified) | 6B | GPU; heavier **[G]** |
| **OCR (PaddleOCR), pose, flow** **[G]** | small | **CPU-viable**; OCR the heaviest |

**[G] Serving:** ONNX Runtime / TensorRT give 2–4× over PyTorch for the
conv-heavy models (TransNetV2, OCR, pose); the video LLMs want
**vLLM** (Qwen3-VL supports unlimited frames via vLLM with client-side fps)
or llama.cpp/GGUF quantization for CPU/small-GPU. **Verified:** TransNetV2's
PyTorch inference port exists; Qwen3-VL ships FP8 MoE variants.

**Adopt:** run the **deterministic primitives (SBD, OCR, pose, flow) on CPU**
to produce evidence cheaply, and spend GPU budget only on the VLM/embedding
calls over *sampled keyframes* — never every frame.

## Gaps (confirmed, load-bearing)

1. **No Souls-like / RPG game-state dataset.** Boss phases, death screens,
   bonfire rests, invasions — none are labelled publicly. VideoGameBunny's
   field vocabulary is the closest scaffold; a bespoke event head is required.
2. **No "funny gameplay moment" visual dataset.** Highlight datasets label
   *exciting* (Kill/Death/etc.); nothing labels *comedic* visual beats with a
   mechanism and a landing timestamp. Mirrors AUDIO_SURVEY Area 6.
3. **SBD detects editorial cuts, not gameplay transitions.** TransNetV2 and
   friends will report ~nothing on continuous gameplay — which is useful
   (it isolates real cuts) but means **in-game transitions need a separate
   detector** (HUD-state change, loading screen, camera-mode switch).
4. **No released gameplay-event model.** The X-CLIP highlight approach is
   described but weights/data are not out; the CLIP-glitch result is zero-shot
   only.
5. **VLM timestamps are soft.** Even the best timestamped video LLMs localize
   to a coarse granularity; frame-accurate boundaries must come from the
   deterministic SBD layer, with the VLM supplying *what*, not *exactly when*.

## Adopt for our data model — consolidated

| Finding | Our record | Field mapping |
|---|---|---|
| TransNetV2 / PySceneDetect / MSU JSON | **`EditEvent`** | `edit_type` (`ext:hard_cut`/`dissolve`/`fade`), `detection_method`, `tolerance_ms` |
| Editorial-cut vs. game-transition split | **`ShotContinuity`** | `continuity` (EDITORIAL_CUT / GAME_TRANSITION / LOADING), `camera_vs_editing_ambiguous` |
| MovieNet 5 scale + 4 movement classes | **`ShotContinuity`** | `scale`, `movement` (`ext:` extended) |
| ActionFormer TAL `(start,end,class,score)` | **`GameplayEvent`** | `start_ms`/`end_ms`, class label, `uncertainty` |
| EPIC-KITCHENS verb/noun split | **`GameplayEvent`** | `action` (verb) + `actor`/`environment`/`outcome` |
| AVA per-track localization | **`CharacterState`** / `NarrativeEntity` | `entity_id` binds event to a subject |
| **VideoGameBunny 16-field JSON** | **`Observation`** (VIDEO) | HUD/Player status/Animation states/Character list → on-screen state fields |
| TimeChat / Qwen3-VL dense captions | **`Observation`** + **`EvidenceSpan`** | caption text + `{start,end}`; `FRAME` span with `frame_index` |
| OCR / pose / flow / CLIP-glitch primitives | **`EvidenceSpan`** | every claim traces to a frame; `native_location` = the primitive |
| Panda-70M best-of-N caption selection | (pipeline) | choose among VLM `Observation`s before committing |
| ffprobe metadata | **`ReferenceVideo`** | `frame_rate`, `width`, `height`, `duration_ms`, `video_timebase` |

**The decisive finding for the video side:** the *labelling* layers (SBD, TAL,
OCR, pose) are mature and cheap; the *game-semantic* layer (what a Souls
moment means) has a published field vocabulary (VideoGameBunny) but no trained
Souls model; and the *comedic-visual* layer does not exist at all. As on the
audio side, we adopt schemas per layer and fuse them — and the fusion across
(visual event + audio event + comedic mechanism + edit timing) remains the
original contribution.
