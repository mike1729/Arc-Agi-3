# E2 slice 3 — the maximal-context night on 3.6: boards in the window

**2026-08-05. Design + build spec + run protocol in one note. One GPU night, operator-
requested: the last 3.6 experiment.** The question, stated so either answer closes it:
**given everything the system can put in context — including, for the first time in
this line, actual rendered boards — do any of the three channels beat their controls
on Qwen3.6?** Protocol, controls, scoring, and readout are slice 2's verbatim
(`notes/e2-slice2.md`); only the context changes. If this loses too, "the games are
too hard for 3.6" is accepted with receipts, and everything model-side waits for 3.8.

**Prompt target: ≤ 50k tokens** (operator direction) — 4× slice 2, 19% of the window.
The budget is spent on the four things every prior digest destroyed, in priority order:
**what the board looks like** (frames) · **how the board maps to the handles predicates
must use** (segmentation join) · **what happened over time, including a win** (episode
render) · **which mechanics are already solved** (action gallery), so the model spends
its reasoning on what is unsolved rather than re-deriving what the miner knows. Nothing
here is speculative context-stuffing: each item below is tied to a measured failure.

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

## Arm F — frames in the digest (all 16 cells), target ≤ 50k tokens/prompt

Digest v4 = digest v3 (unchanged) + a rendered section per cell, own-store data only
(**no human-replay frames in context** — hidden games won't have them; human replays
remain the external test). Each item names the measured failure it attacks:

1. **Initial frame**, full board, letter-coded, row/col rulers. *(~4.3k tok)*
2. **Most-explored frame**, full board. *(~4.3k)*
3. **Inert-object overlay**: the initial frame with every cell that ever changed
   dimmed to `·`, so the static objects — the specification candidates — are visually
   isolated. The ft09/sb26 mechanism handed over directly. *(~4.3k)*
4. **Per-frame segmentation** for the frames above: object id · colour · bbox · area ·
   adjacency, in the census vocabulary. This is the **binding bridge** — the join
   between what the model sees and the handles its predicates must quantify over,
   which nothing in any previous slice ever gave it. *(~1.5k × 3)*
5. **One played episode, rendered temporally**: the walked route to the most-explored
   state (for sp80/lf52: **the completion route, ending at the completing action** —
   the closest thing to "watch me win" the system owns) as first frame full + per-step
   diff lines (`step k: ACTION4 → cells (r,c) a→b, …`). Temporal/causal structure is
   the one thing every digest destroyed. *(~6k: full frame + 40–60 diff steps)*
6. **Action-effect gallery**: per action id (and per click-colour for A6), 2 example
   before→after 11×11 patches **plus the miner's resolved rule where one exists** —
   the solved mechanics shown, so the model spends its window on the unsolved ones.
   *(~2.5k)*
7. **Per unresolved key, 2 example transitions as patches** (11×11, before → after,
   action labelled; r=5 covers the measured locality radius 2–3). *(~3k)*
8. **Alias exhibit** (games with recorded conflicts — m0r0, g50t class): the same
   (board, action) rendered twice with its two different outcomes, side by side. The
   concrete evidence channel B's latents are supposed to explain. *(~0.5k)*
9. **Think-scaffold headers** (instruction only, no examples): the reference harness's
   world-model discipline — `World model / Goal model / Action model / Open questions`
   — which structured its best recorded play. *(~0.2k)*

**Worst-case arithmetic, measured on real grids today** (tokenizer, not estimated):
dc22 full frame **4,335 tok**, 11×11 patch **131 tok**; dc22's digest v3 ≈ 12.7k tok.
Frames section ≈ 28k → **dc22 total ≈ 41k tokens**, inside the 50k target with ~9k of
headroom for the scaffold and the think-discipline headers. Sparse boards cost far
less (sp80 full frame 1,552 tok → ~14k section, ~25k total), so the target binds only
on the dense games. Prefill at ~400 tok/s ≈ **~2 min/cell**.

**Contamination hard rule:** the prompt must never name the five stock goal shapes —
they are the channel-A control, and showing them turns `in_prior_library` into
compliance instead of convergence. The generic framing stays neutral ("the completion
condition is some predicate over objects; it may or may not resemble anything you have
seen"). Verify by grep before the night: no shape-list phrasing anywhere in the
rendered prompts.

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
   rulers · dimmed inert overlay · 11×11 before/after patch pairs · per-step diff
   lines for the episode render · per-frame segmentation listing (reuse `_Objects`;
   ids consistent with the census vocabulary) · the alias exhibit. Unit-check against
   3 stored grids by eye and by round-trip.
2. **Digest v4 assembly** in `e2_slice.py` behind a flag (`--frames`), default off —
   slice-2 behaviour is preserved bit-for-bit without the flag. Episode source: the
   verified walked routes (`logs/e1_prefix_v2/`), completion route for sp80/lf52.
3. **Feedback turn** machinery: in-loop verification (the slice-2 checker, run at
   extract time), revision prompt template, second think+extract, both calls logged
   with separate verdicts.
4. **Render all 8 v4 digests**, record **token** counts (tokenizer, not chars) against
   the ≤ 50k target; if a cell overshoots, trim item 5's diff span first, then item
   6 — never items 3, 4, or 8 (the mechanism carriers).
5. **Contamination grep** (the hard rule above) over all rendered prompts.
6. **Budget probe, mandatory**: one call on the largest v4 prompt (protocol of
   `notes/think-budget-recheck.md`). The prompt grows ~4× over slice 2; the probe
   re-measures warm prefill tok/s at ~50k tokens (the wall estimate needs it) and
   confirms think closure — if the block does not close at 16,384, stop and report;
   no unilateral budget raise.

## Run (night)

16 F cells ≈ 6.5 h (measured decode ~15 min/cell + ~2 min prefill at 50k) + up to 8 FB
turns ≈ 2–2.5 h → **~9 h**. That is the longest night this line has run; it fits an
overnight window but leaves no slack, so: **seeds run sequentially, seed 1 first, and
seed 1 must include the FB turns.** If the night is cut short, a complete seed 1 with
both arms is the result; a half-finished seed 2 is not a loss. Outputs
`logs/e2_slice3_seed{1,2}.json`, traces tagged distinctly; `nohup` + `caffeinate`;
voids logged, never rerun mid-night. Morning readout = slice 2's structure + the FB
repair-rate line, appended to this note.

## Expectations, calibrated in advance

The reference agent had ascii boards, segmentation, *and* a Python query tool over its
own history — and still stalled goal-unknown on 76% of episodes. Boards are not magic;
the test is whether frames + our verification scaffolding beat **our controls**, and
the pre-registered bar is unchanged. Two specific sub-reads worth pre-naming: does
channel A improve on the games whose boards carry visible specification objects
(ft09's clue patterns, ls20's target shapes), and on the completion-route games
(sp80, lf52)? Those are where the mechanism, if it exists at 3.6, must show first.

**One risk this arm adds, stated before it can be explained away.** Slice 2's failures
were *ungrounded* but *disciplined*: 16/16 parsed, 0 prose. A 4×-longer, richer prompt
can degrade that — more surface to pattern-match, more chances to describe the board
instead of committing to a predicate. So the readout keeps three instrument counters
alongside the channel verdicts (**parse rate · think length · verdict passes**), and a
drop in any of them against slice 2 is reported as a *context-length cost*, not folded
into the capability verdict. This is also the only quantitative check we will ever have
on the "long context degrades this quantized deployment" hypothesis — slice 2 at ~12k
tokens is its matched control, and the pair is worth reporting whichever way it lands.

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
