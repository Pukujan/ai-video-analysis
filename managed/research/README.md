# Research index — reverse-analyzing the mix, the frame, and the edit

Three surveys, ~600 named sources total, assembled 2026-10-09. Each is the
sourced basis for one layer of the project. Read in this order.

| File | Layer | Areas | Status |
|---|---|---|---|
| `AUDIO_SURVEY.md` | **Analysis — audio** | 1 music sep+ID · 2 event/SFX · 3 speech/prosody · 4 loudness/mix+QC · 5 game audio middleware+timeline · 6 AV+humor | COMPLETE (591 lines) |
| `VIDEO_SURVEY.md` | **Analysis — video** | 7 shot detect · video LLMs · action/TAL · gaming vision · dataset schemas · primitives · ingest · local inference | COMPLETE (453 lines) |
| `AUTOEDIT_SURVEY.md` | **Generation — auto-VOD** | 8 highlight · assembly · timeline · voice · jokes · avatars · agentic pipelines · real workflow | COMPLETE (194 lines) |

License is recorded as provenance metadata only; it is never a selection
criterion (`managed/design/LICENSE_POLICY.md`).

## The one-line answer to "does the system I want exist?"

**No — and the reason is precise.** The pipeline decomposes into six stages,
and every stage exists separately at good quality; **nothing fuses them, and
the comedic layer is missing from all of them.**

| Stage | Status today | Highest-quality current option |
|---|---|---|
| 1. Ingest raw stream/recording | **automatable** | yt-dlp, ffmpeg/ffprobe, OBS, platform VOD APIs |
| 2. Find moments worth keeping | **automatable** | Opus Clip / Sizzle / Eklipse (products); X-CLIP per-1s-clip method (research) |
| 3. Cut & assemble | **automatable** | `auto-editor`; OTIO timeline; Shotstack JSON render spec; ffmpeg |
| 4. Voice (own / cloned / TTS) | **automatable** | your own mic (best for comedy); XTTS-v2 / F5-TTS / Kokoro / ElevenLabs |
| 5a. Joke *text* | **automatable** | any frontier LLM |
| 5b. Joke *timing to a visual beat* | **research only — must build** | nothing packages this |
| 6. End-to-end funny VOD | **nonexistent — must build** | nothing fuses stages 1–5 |

## Why the comedic layer is the whole problem

Every production clipper — including **Twitch's own Auto Clips** — is
**transcript/emotion-driven and reframes around a centered face**. That is the
wrong signal shape for gameplay, and it confirms that at platform scale the
reliable moment-detector is still *audio*, not vision. Highlight datasets
(Gameplay-Highlights, 4,408 events) label **exciting** moments (Kill, Death,
Grenade); **none labels comedic moments**, with a mechanism and a landing
timestamp.

**No dataset or model jointly labels (visual event + audio event + comedic
mechanism + edit timing).** That fusion — across our own reference videos,
with evidence links — is the project's original contribution and the reason no
off-the-shelf system can be adopted wholesale. We adopt schemas per layer and
fuse them.

## The build target

One component is missing, and everything else bolts onto it: an
**analysis→generation bridge** that consumes our fused `GameplayEvent` +
`AudioEvent` + `ComedyBeat` records and emits a **timed edit + a line**. The
mature stages sit on either side of it (ingest → bridge → auto-editor/OTIO →
TTS-or-mic → publish). Audio-Oscar's critic loop (score 0–1, rewrite prompts
below 0.7, ≤3 retries) is the nearest published analogue to our
`GenerationTrial`/`HumanPreference` loop, and is the template for the
generation half.

## Schemas we adopt (the load-bearing picks)

- **Audio measurement:** ITU-R BS.1770-5 / EBU R 128 (M/S/I/LRA, LUFS,
  K-weighting, −70 abs + −10 rel gates, true peak).
- **Audio findings report:** EBU QC `qc.xsd` (Item/ItemResult + Severity +
  Locator + Confidence).
- **Ducking / mix events:** Torcoli 2019 parameters (LD, attack, release,
  shift, hold) + Torcoli 2024 speech metrics (SLD, SBLD, critical-speech %).
- **Audio events:** AudioSet ontology (632-class) + DCASE `onset/offset/label`
  shape; game-audio labels from FMOD/Wwise/Godot `AudioStreamInteractive`.
- **Music separation:** Cocktail Fork / MRX tri-stem (`speech`/`music`/`sfx`);
  Demucs / Mel-Band RoFormer (via `msst`) backbone.
- **Prosody:** openSMILE eGeMAPSv02 (25 LLD / 88 functionals) as the
  `VocalDelivery` column schema.
- **Edit timeline:** OpenTimelineIO (`Timeline→Stack→Track→Clip/Gap/
  Transition/Marker`, `LinearTimeWarp` for speed ramps); PySceneDetect emits
  it directly; EDL/FCPXML/AAF come free via adapters.
- **Shot grammar:** MovieNet 5 scale + 4 movement classes → `ShotContinuity`.
- **Game-frame state:** **VideoGameBunny's 16-field JSON** (HUD, player
  status, NPC status, animation states, glitches) → per-frame `Observation`.
- **Gameplay events:** ActionFormer TAL `(start, end, class, score)` +
  EPIC-KITCHENS verb/noun split → `GameplayEvent`.
- **Comedy:** theory triad (superiority/relief/incongruity) + benign-violation
  rubric → `ComedyMechanism`; laughter-follows-word timing (StandUp4AI) as the
  landing-point model.

## Confirmed gaps (the honest part)

1. **No end-to-end gameplay → funny-narrated-VOD system** anywhere, product or
   research.
2. **No comedic-moment dataset** (visual or audio) with mechanism + landing
   timestamp. Highlight datasets label *exciting*, not *funny*.
3. **No Souls-like / RPG game-state dataset** (boss phases, death screens,
   bonfires, invasions). VideoGameBunny's field vocabulary is the closest
   scaffold.
4. **No packaged sarcasm detector** with an API or output schema — treat
   sarcasm as E2 interpretation, never a detector output.
5. **Game-specific audio ML is thin** — no Dark Souls audio dataset, one small
   single-game SED benchmark (BattleSound). Our own annotated VODs are the
   resource.
6. **Detection tools never emit timelines; timeline tools never detect.**
   Nothing joins them — `auto-editor` (content-aware cut by
   `audio:threshold`/`motion:threshold`, exporting Premiere/Resolve/FCP XML)
   is the closest bridge.
