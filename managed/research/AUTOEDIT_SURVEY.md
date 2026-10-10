# Auto-editing & auto-VOD survey — the generation side

Status: COMPLETE (Area 8). Assembled 2026-10-09 from web research, as the
generation-side counterpart to `AUDIO_SURVEY.md` (analysis side).

## Why this survey exists

The audio and video surveys answer *how to reverse-analyze* a reference VOD
into a data model. This survey answers the forward question: **is there any
production or OSS system that takes raw gameplay recording + a voice, and
auto-produces a finished, funny VOD** — highlight selection, cuts, edits,
narration, jokes — and can it be composed with the analysis stack?

The user's target pipeline, decomposed:

1. **Ingest** a raw stream/recording.
2. **Find the moments worth keeping** (highlight / event detection).
3. **Cut and assemble** them (programmatic editing, timeline).
4. **Add voice** — the user's own, cloned, or generated TTS.
5. **Write and time jokes** that land (comedy generation + beat timing).
6. **Publish** as a VOD.

Findings are graded below on one axis: **does a system do this, off the
shelf, at usable quality?** License is recorded as metadata only
(`managed/design/LICENSE_POLICY.md`).

## Area 8.1 — Highlight detection & auto-clipping (STAGE 2: mature)

This is the **most solved stage**. Many production systems do it well.

### Streamer-side auto-clipping

| System | Kind | What it does | Note |
|---|---|---|---|
| **Twitch Auto Clips** | platform feature | clips created from chat spikes / streamer-set triggers | first-party; no external pipeline needed |
| **Sizzle.gg** | production SaaS | AI highlights from Twitch/YouTube VODs | streamer-focused |
| **Eklipse.gg** | production SaaS | AI gaming highlight clips, TikTok-ready | gaming-native |
| **Opus Clip** | production SaaS | long→shorts, "virality score" ranking | general-purpose, huge adoption |
| **Vizard.ai** | production SaaS | long→clips, auto-captions | general |
| **Klap.app** | production SaaS | long→clips | general |
| **ClipSpeed / Wayin / ViddyFlow** | production SaaS | gaming clip generators | narrower, gaming-specific |

### Research-grade highlight detection

- **Gameplay Highlights Generation (arXiv:2505.07721)** — in-house FPS event
  dataset: **4,408 annotated events + 2,745 background**, classes **Kill,
  Death, Grenade Throw, Reload, Bomb Planted, Knocked Down, Power Use,
  Background**, annotated in **VIA**, games CS:GO/PUBG/Valorant/OW2/Fortnite.
  Method: 1-second clips → **fine-tuned X-CLIP-B/16** (32 RGB frames @224² +
  text prompt "Game. Event. Description."), cosine similarity → softmax.
  Highlights = concatenated interesting intervals. **Dataset/model/code NOT
  released.** The *method* is reproducible; the *schema* (per-1s-clip event
  label + probability) is directly copyable.
- **Real-Time Game Highlight Detection (IRI/UPC, 2025,
  iri.upc.edu/download/scidoc/3040)** — fuses **visual + audio cues** in real
  time for impactful-moment detection. Confirms the audio-visual fusion
  approach is the research direction for gameplay highlights.

**Assessment:** highlight detection is a **solved, adoptable stage**. The
gap is not finding moments — it is everything after.

## Area 8.2 — Auto-editing / programmatic assembly (STAGE 3: mature, low-level)

| Tool | Kind | What it does | Reusable schema? |
|---|---|---|---|
| **auto-editor** (WyattBlue) | OSS Python | removes silence / dead air, auto-cuts, **splits audio & video at the same points** | CLI/JSON; `--edit audio:threshold=…`; no API |
| **Shotstack** | production API | JSON timeline → rendered video (cloud) | **YES — JSON edit spec is a real timeline schema** |
| **Editframe / Creatomate / JSON2Video** | production APIs | JSON→video render | similar JSON timeline models |
| **MoviePy** | OSS Python | programmatic composition | code, not a schema |
| **FFmpeg** | OSS | filter graphs, concat, cut | the substrate everything sits on |
| **OpenTimelineIO** (ASWF) | OSS schema | interchange format for editorial timelines | **YES — `Track`/`Clip`/`Gap`/`Transition`/`Marker` + `RationalTime`** |
| **Remotion** | OSS (React) | code-as-video composition | React, not a data schema |

**Assessment:** assembly is **solved at the mechanical level**. Cutting on
detected events, joining clips, adding transitions, exporting — all
automatable today. The reusable schemas are **OTIO** (editorial interchange)
and **Shotstack's JSON timeline** (render spec).

## Area 8.3 — Timeline schema (cross-reference)

Covered by the running edit-detection agent in Area 5. The adoptable
finding: **OTIO** as the interchange spine, with our `EditEvent` records
mapping onto `Clip`/`Transition`/`Marker` and our `[start_ms, end_ms)`
half-open intervals mapping onto OTIO `RationalTime` ranges.

## Area 8.4 — Voice: the user's own, cloned, or generated (STAGE 4: solved)

| Tool | Kind | What it does | Note |
|---|---|---|---|
| **XTTS-v2** (Coqui) | OSS TTS | zero-shot voice cloning from ~6 s reference | Coqui shut down; code/weights mirrored in community repos |
| **F5-TTS** | OSS TTS | flow-matching TTS, zero-shot cloning | strong naturalness |
| **Kokoro-82M** | OSS TTS | 82M params, very fast, Apache | CPU-viable, high quality/size ratio |
| **Chatterbox** (Resemble) | OSS TTS | open TTS + emotion control | emotion exaggeration knob |
| **StyleTTS2** | OSS TTS | human-level naturalness claim | English-focused |
| **OpenVoice** (MyShell) | OSS TTS | voice clone + style/tone transfer | separates tone from timbre |
| **ElevenLabs** | production API | SOTA cloning + TTS | highest naturalness tier |
| **PlayHT / Cartesia / Rime / Fish Audio** | production APIs | cloning + TTS | commercial tiers |
| **TTS Arena v2** (HF Space) | living benchmark | blind human preference ranking of TTS | **the source to re-check for current best** |

**Assessment:** voice is **fully solved**. The user's own recorded narration
needs no TTS at all — only alignment (Area 3: MFA/WhisperX). For *generated*
voice, cloned-from-user or a distinct persona voice are both available
off the shelf.

## Area 8.5 — Joke generation that lands (STAGE 5: the real gap)

| System | Kind | What it does | Note |
|---|---|---|---|
| **GPT/Claude/Gemini LLMs** | production models | competent setup/punchline joke writing | **can't time delivery to a visual moment on its own** |
| **Comedy-writing prompts / "roast my gameplay"** | prompt patterns | working, no framework | ad-hoc |
| **Audio-Oscar (arXiv:2606.07397, 2026)** | research agent | post-production **mixing agent**: gain, fade, crossfade, envelope, ducking, pan, EQ, compression, reverb; emits structured JSON per segment | closest thing to an *automated post-production agent*; ops vocabulary reusable |
| **StandUp4AI / ExFunTube / MHD** (Area 6) | datasets | ground truth for *what makes a moment land* and *when* | analysis-side; feed the generator |
| **No system found** | — | LLM that **watches gameplay, finds the funny visual beat, writes a line, and times the drop** | **genuine gap** |

**Assessment:** joke *text* is solved (any frontier LLM). Joke *timing to a
visual moment* is **not solved and not packaged anywhere**. The comedy-timing
ground truth exists only as datasets (StandUp4AI laughter-follows-word,
ExFunTube moment→explanation), which is exactly the supervision our own
reference analysis produces. **This is where the project's data model pays
off**: the `ComedyBeat` (setup/payoff/incongruity/landing point) + `EditEvent`
timing is the missing input that no generator currently has.

## Area 8.6 — Faceless-narrator / avatar rendering (optional)

Talking-head OSS: **SadTalker**, **Wav2Lip**, **LivePortrait**, **EchoMimic**,
**Hallo**, **MuseTalk**, **LatentSync** — audio→talking-face lip sync. For a
narrated gameplay VOD the voiceover is usually **not** on-camera, so this
stage is optional; it matters only if the user wants a visible presenter.

## Area 8.7 — End-to-end agentic pipelines (STAGE 6: emerging)

- **Audio-Oscar** (above) is the closest published *agentic post-production*
  system — text description → mixed audio, with a structured operation
  vocabulary. It is the template for "describe the edit, get the edit."
- **Video-editing agents** (research, 2024–2026): LLM/VLM agents that plan an
  edit from a prompt. Still research; no production-grade end-to-end
  gameplay→funny-VOD system was found.

**Assessment:** the *integrated* system the user describes — stream in,
funny VOD out — **does not exist off the shelf**. Every stage exists
separately; nothing fuses them.

## Area 8.8 — What real streamers actually do

The observed production workflow (from the tool ecosystem): OBS records →
editor or auto-clipper selects highlights → hand-cut in Premiere/Resolve/DaVinci
→ **hand-written narration recorded separately** → assembled. Auto-tools
(Opus/Vizard/Sizzle) are used for *shorts*, not for narrated long-form. No
streamer workflow found that auto-generates the comedic narration.

## Gaps (confirmed, load-bearing)

1. **No end-to-end system** does raw-gameplay → funny-narrated-VOD. Stages 1–4
   and 6 are mature; stage 5 (joke timing) is missing; nothing fuses them.
2. **Joke *timing* to a visual beat is unsolved and unpackaged.** LLMs write
   jokes; no system watches the game, finds the comedic visual moment, and
   lands the line on it.
3. **Comedic gameplay-narration datasets do not exist.** Highlight datasets
   (Area 8.1) label *exciting* events; none label *funny* moments with a
   comedic mechanism and a landing timestamp.
4. **The analysis→generation bridge is absent.** No generator consumes a
   structured "here is the visual event, the audio event, and the comedic
   beat" record. Our data model would be that bridge.

## Automatable today vs. research vs. nonexistent

| Stage | Status | Best current tool |
|---|---|---|
| Ingest / VOD download | **automatable** | yt-dlp, ffmpeg, platform APIs |
| Highlight detection | **automatable** | Opus Clip / Sizzle / X-CLIP method |
| Cut & assemble | **automatable** | auto-editor, Shotstack, OTIO, ffmpeg |
| Voice (own / cloned / TTS) | **automatable** | user's mic, XTTS-v2/F5/Kokoro, ElevenLabs |
| Joke *text* | **automatable** | any frontier LLM |
| Joke *timing to visual beat* | **research only** | — (must build) |
| End-to-end funny VOD | **nonexistent** | — (must build) |

## Adopt for our data model

- **Timeline interchange: OTIO** — map `EditEvent` onto `Clip`/`Transition`/
  `Marker`; `RationalTime` ranges align with our half-open `[start_ms, end_ms)`.
- **Render spec: Shotstack-style JSON timeline** — a second, renderable
  target alongside OTIO.
- **Highlight schema: the Gameplay-Highlights per-1s-clip shape** (event label
  + probability + background class) → our `GameplayEvent` + `Observation`
  with confidence.
- **Mix-operation vocabulary: Audio-Oscar's op list** (gain, fade, crossfade,
  envelope, ducking, pan, EQ, compression, reverb) → our `AudioMixEvent`
  and the generation-side edit vocabulary.
- **Voice: the user's own narration is the primary path** (no TTS needed);
  cloned/TTS is the fallback, chosen by current TTS-Arena ranking.
- **The build target:** the one missing component is the **analysis→generation
  bridge** — a consumer that takes our fused `GameplayEvent` + `AudioEvent` +
  `ComedyBeat` records and emits a timed edit + line. That bridge, plus the
  mature stages on either side, is the whole system.
