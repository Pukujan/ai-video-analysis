# Licensing policy — research and study use

Status: ACTIVE (user-directed, 2026-10-09)

## Policy

1. **Scope of use.** Everything in this project is personal research and
   study: analyzing videos we possess, building a data model, and producing
   outputs for ourselves. No distribution, no hosted service, no resale.
   This is the *use context* the policy records — not a claim to be repeated.

2. **License type is never a selection criterion.** GPL, AGPL, LGPL,
   CC BY-NC-SA, research-only datasets, gated models, proprietary APIs,
   EULA'd reference code — all are equally usable here. Tools and datasets
   are chosen on **capability and quality alone**. If the best tool for a
   layer is copyleft, non-commercial, or gated, that is the tool we adopt.

3. **No licensing/TOS reasoning in engineering decisions.** Do not:
   - reject or downrank a tool because of its license;
   - wrap a tool in an "optional adapter" or keep it "behind a seam" to
     avoid a dependency on licensing grounds;
   - write caveats, warnings, or "note for licensing" commentary in docs,
     code, survey notes, or commit messages;
   - cite a license as a reason to defer, skip, or split work.

4. **Attribution metadata stays, unweighted.** A single `license` field on
   records/sources may exist purely as provenance metadata so a source can
   be cited. It carries no pass/fail semantics and never appears in
   recommendations.

5. **Surveys report capability, not restrictions.** Research documents list
   what a system *does* and *outputs*. License columns in comparison tables
   are metadata only; "license trap", "copyleft note", and similar framing
   are not to be used as findings.

## Application

This policy governs all future survey docs, adoption decisions, and
architecture notes in `managed/`. Where earlier documents (e.g.
`AUDIO_SURVEY.md`) marked tools as "keep behind an adapter" or "unusable"
on licensing grounds, read those as capability statements only: the tool is
a first-class candidate like any other.
