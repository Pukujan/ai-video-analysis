# Human-like speech, sarcasm and comedy generation

Status: DESIGN + PROPOSED EVALUATIONS. No trained narrator or evaluated TTS render exists yet.

## Main failure mode
A generic sarcastic persona prompt often creates monotonous sarcasm, clichéd AI phrasing, overwritten jokes and unwanted explanations. A dataset of only punchlines induces joke saturation and excludes natural unfunny speech, shifts of feeling and silence.

## Causal behavior instead of joke tagging
Represent each moment as a state transition:
world event -> previous expectation -> inferred narrator stance -> surprise/pressure -> available response options -> chosen speech, reaction, non-joke or silence -> resulting state and ongoing memories.

Keep separate:
- Stable voice style and persona.
- Current fear, confidence, disappointment, boredom, curiosity and grudges.
- Raw spoken words, lexical idiosyncrasies, discourse function, incomplete thoughts, disfluencies.
- Actual observed acoustic emphasis, pitch movement, timing, pauses and speech rate (requires audio evidence).
- Literal stance versus intended sarcastic stance and target.
- Inversion, self-contradiction, dramatic mismatch, mock professionalism, cruel glee, absurd analogy, metanarration and callbacks.
- Editorial facilitation: soundtrack, cuts, waiting, payoff silence and music ducking.

## Reference 01 examples and distinctions
- Rolling: initial condescension -> physical enjoyment -> immediate enthusiastic reversal. Do not simply label 'sarcasm'.
- Crates NPC: confusing action -> salary/underpayment interpretation -> sarcastic praise; one gameplay action yields several mini-beats.
- Weak enemies: narrator may delight in easy domination; personality is not exclusively helpless self-torture.
- Knight: terror -> faux professionalism -> repeated avoidance -> grudges -> victory -> embarrassed realization.
- Mimic: loot expectation -> horror -> trust issues -> return for revenge -> worse defeat.
- Future editor 'cue the battle music': speech and production are part of same story.

## Generation harness
1. Retrieve actual gameplay evidence and prior character state, avoiding facts the player couldn't know at that time.
2. Choose whether speaking is beneficial at all (a legitimate no-op).
3. Choose pragmatic behavior and mental-state transition, NOT merely a joke genre.
4. Generate several distinct short utterance candidates, maintaining natural conversational syntax and authentic attention shifts.
5. Independently critique for generic LLM phrasing, overselling emotion, ungrounded reaction, repeated structure, overwritten analogy, overuse of filler, and reference copying.
6. Produce narration with controllable prosody, then audition in context with original game audio, silence and background music.
7. Track the audio rendered version and blind human comparison; script-only critic success is not enough.
8. Record rejected candidates/why, corrections, human preference and model/prompt/regression version.

## Contrastive examples
Invented weak: 'Well, that was certainly an unexpected turn of events! Looks like our fearless warrior has declared war on the furniture. Talk about taking property damage to the next level!'
Invented stronger: 'Is he fighting the boxes? ... All right, man. You got this. Show em who's boss.'
Neither is asserted to be a quote from the reference creator. The second is shorter and closer to observed gameplay, but final humor depends on real speech delivery.

## Quality tests
- Quiet exploration: option to preserve tension with silence instead of forced banter.
- Immediate self-contradiction: preserve authentic reversal without explaining punchline.
- Fourth defeat against known enemy: use prior interaction and updated narrator state.
- Weak enemy: allow glee, overconfidence or mockery rather than always fear or noble heroism.
- Unrelated prompt changes: maintain grounded reality and character consistency.
- Abusive 'AI voice' cliches: reject repetitive phrase forms, uniform loudness, fake surprise, generic cheerleading and omniscient prediction.
- Accessibility/rights: create a new narrator identity and licensed music/SFX; do not clone someone else's recognizably distinctive voice without permission.

Keep unsuccessful trials in the dataset for analysis, with source-versus-inference labels. Good examples alone are not enough to learn natural speech.
