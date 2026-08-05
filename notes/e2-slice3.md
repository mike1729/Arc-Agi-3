# E2 slice 3 — the maximal-context night on 3.6: boards in the window

**2026-08-05. Design + build spec + run protocol in one note. One GPU night, operator-
requested: the last 3.6 experiment.** The question, stated so either answer closes it:
**given everything the system can put in context — including, for the first time in
this line, actual rendered boards — do any of the three channels beat their controls
on Qwen3.6?** Protocol, controls, scoring, and readout are slice 2's verbatim
(`notes/e2-slice2.md`); only the context changes. If this loses too, "the games are
too hard for 3.6" is accepted with receipts, and everything model-side waits for 3.8.

## Why boards, specifically (measured, not vibes)

- In the entire E2 line the model has **never seen a grid** — digests are feature-space
  summaries. Yet the only reproducible discovery mechanism ever observed (ft09/sb26,
  3/3 each, S1 corpus) was the model **reading a rendered board** and treating a static
  object as a specification. Our inert-object *inventory* was the textual proxy for
  that; slice 2 measured the proxy dead. The real thing is untested.
- The reference harness those discoveries happened in (inspected today,
  `logs/kaggle_v4/prompts/`) used **letter-coded ascii boards** (ARC colour symbols)
  with segmentation as the primary view — that rendering is *proven readable* by this
  model family. Use it, don't invent one.
- **Context is not a constraint: 262,144 tokens** (`text_config.max_position_embeddings`,
  measured today). The costs are prefill wall (~400 tok/s measured) and attention
  quality — so the design below is generous but not indiscriminate.
- Measured render costs: full 64×64 frame ≈ **4,335 tokens** (hex; letter-coding
  similar), 11×11 patch ≈ **131 tokens**. Worst-case v4 prompt (dc22): digest ~12.5k +
  3 full frames ~13k + ~20 patches ~3k + scaffold ≈ **~30k tokens** → ~75–90 s prefill.
  Fine.
- ⚠ The model config carries a **vision tower**. It stays out of scope: the voided July
  lineage ran through the vlm server, the verified instrument is text-only direct
  `mlx_lm`, and a vision bring-up is its own gated project. Text rendering only.

## Arm F — frames in the digest (all 16 cells)

Digest v4 = digest v3 (unchanged) + a rendered section per cell, own-store data only
(**no human-replay frames in context** — hidden games won't have them; human replays
remain the external test):

1. **Initial frame**, full board, letter-coded, row/col rulers.
2. **Most-explored frame** (the state with the most tested actions), full board.
3. **Completion pre-frame** where the store holds one (sp80, lf52).
4. **Inert-object overlay**: the initial frame re-rendered with non-inert cells dimmed
   (e.g. lowercase/`·`), so the static objects — the specification candidates — are
   visually isolated. This is the ft09/sb26 mechanism handed to the model directly.
5. **Per unresolved key, 2 example transitions as local patches** (11×11 around the
   change, before → after, action labelled) — r=5 covers the measured locality
   (`notes/e3-grounded-delta.md`: median determining radius 2–3).

## Arm FB — one contradiction-feedback turn (seed 1 only)

For seed-1 cells whose channel-A predicate **fails mechanical verification**
(store-falsified or self-refuting): one revision turn — the concrete counterexample
rendered (the falsifying transition's patches, or the completion frame where the
predicate evaluated false/true wrongly), plus "your refuter was already satisfied at
step t" where applicable — then fresh think + extract, same budget, same verdict
machinery. **Within-night attribution**: F vs F+FB on the same cells; the S1 corpus
says re-specification-under-contradiction is the capability that separated the
reference's L2 recoveries from its L2 deaths. Scored: revised predicates through the
identical pipeline; readout adds one line — repair rate (failed → survived/correct).

## What does NOT change

Channels, schemas, DSL, prior library, random controls, adjudication rubric, v2
floors, seeds (1, 2 — never 20260804), temp 0.6, `THINK_BUDGET = 16384`, two-phase
decode, first token never constrained, per-call mechanical verdicts, worktree pinning,
explicit `--out`. The pre-committed comparisons are slice 2's, verbatim, plus the FB
repair-rate line. Attribution: F effect = slice 3 vs slice 2 per cell; FB effect =
within-night.

## Build (day task, zero-model, ~4–6 h)

1. **Frame renderer** (`agent/harness/e2_frames.py`, new): letter-coded board with
   rulers · dimmed inert overlay · 11×11 before/after patch pairs. Unit-check against
   3 stored grids by eye and by round-trip.
2. **Digest v4 assembly** in `e2_slice.py` behind a flag (`--frames`), default off —
   slice-2 behaviour is preserved bit-for-bit without the flag.
3. **Feedback turn** machinery: in-loop verification (the slice-2 checker, run at
   extract time), revision prompt template, second think+extract, both calls logged
   with separate verdicts.
4. **Render all 8 v4 digests**, record token counts (tokenizer, not chars).
5. **Budget probe, mandatory**: one call on the largest v4 prompt (protocol of
   `notes/think-budget-recheck.md`). The prompt roughly doubles; the probe also
   re-measures warm prefill tok/s at ~30k tokens, which the wall estimate below needs.

## Run (night)

16 F cells ≈ 5.5–6 h (prefill grows ~1–2 min/cell) + up to 8 FB turns ≈ 2 h →
**~7.5–8 h**, slice-1.1-sized. Outputs `logs/e2_slice3_seed{1,2}.json`, traces tagged
distinctly; `nohup` + `caffeinate`; voids logged, never rerun mid-night. Morning
readout = slice 2's structure + the FB repair-rate line, appended to this note.

## Expectations, calibrated in advance

The reference agent had ascii boards, segmentation, *and* a Python query tool over its
own history — and still stalled goal-unknown on 76% of episodes. Boards are not magic;
the test is whether frames + our verification scaffolding beat **our controls**, and
the pre-registered bar is unchanged. Two specific sub-reads worth pre-naming: does
channel A improve on the games whose boards carry visible specification objects
(ft09's clue patterns, ls20's target shapes), and on the completion-pre-frame games
(sp80, lf52)? Those are where the mechanism, if it exists at 3.6, must show first.

## Cautions

- PUBLISHING.md: rendered frames of competition games in *local* logs and prompts are
  fine; **no frame renders in committed artifacts** — the committed JSONs carry
  hashes, counts, and verdicts, never grids. Check before commit.
- Concurrent agents: build in new files + the flagged `e2_slice.py` section; stage own
  files only; `git status` first.
- No invented numbers; render/token costs above are measured today; wall estimates (w).
- The 3.8 plan is unchanged (`notes/qwen-3.8-upgrade.md`): whatever tonight says,
  slice 3 reruns there as the generation contrast — tonight's run doubles as its 3.6
  baseline.
