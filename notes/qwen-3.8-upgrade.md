# Qwen 3.8-27B upgrade — bring-up gate and rerun plan

> **2026-08-16: the model is out** (`mlx-community/Qwen3.8-27B-{8bit,4bit}` — ⚠ it is a
> VLM and the conversions are mlx-vlm-made; the bring-up gate matters more, not less).
> **Execution plan for night 1: [`notes/qwen-3.8-night1.md`](qwen-3.8-night1.md).** It
> supersedes this note's P1 in one respect: slice 3 + the fixed two-directional grader
> (built after this note) replace slice 1.1R as the rerun vehicle; the priorities and the
> gate below otherwise stand.

**2026-08-05. Status: pre-release plan; nothing here is runnable yet.** Qwen3.8-27B is
expected **~2026-08-12 (w) [verify]** with materially better capabilities
(operator-reported expectation, not a measurement). This note exists so that when it
lands, the reruns are pre-planned rather than re-derived — and so that until then,
**every model-bound verdict in the line is read as a claim about Qwen3.6, not about
"the model".**

## Why this matters

The line's current M-phase conclusions are capability findings about Qwen3.6-27B-8bit:

- the rule-proposal channel is worth ~zero (slice 1 + slice 1.1, causally isolated);
- the goal channel is dominated by the clear-the-board prior (autopsy; S1 cross-walk in
  flight);
- the hidden-state and probe channels are the strong outputs (m0r0 4/4; probe scoring in
  flight);
- `goal_unknown` is the deployed reference bottleneck (S1).

A generation jump can flip any of these. From today, tag such verdicts **(3.6)** when
citing them; the zero-model results need no tag (below).

## Bring-up gate — before ANY 3.8 number is trusted

The July disaster was a serving-path bug, not a model property. New model = new
bring-up; the gate is the same and non-negotiable:

1. **MLX build**: obtain/convert Qwen3.8-27B to MLX under `~/models/mlx/` (expect both
   8-bit and 4-bit; if no community conversion exists, convert locally).
2. **Thinking probe** (`e2_probe.py`) passes on the direct `mlx_lm` path: template opens
   `<think>`, no pre-filled empty think block, substantive body, closed, answer present.
   ⚠ 3.8's chat template may differ from 3.6's — re-inspect it; do not assume
   `enable_thinking` semantics carried over. **Never constrain the first decoded token.**
3. **Re-measure the envelope**: think length on the standard probe, output budget (16k
   (w) was calibrated on 3.6-8bit — 3.8 may think longer), tok/s gen + prefill → redo
   the feasibility arithmetic before scheduling any slice.
4. **Re-pin quantization with a stated rationale.** 8-bit was pinned for FP8 deploy
   fidelity, and on 3.6 quantization changed reasoning *behaviour* (8bit thought 2.7×
   longer than 4bit on the identical prompt) — re-measure on 3.8, don't inherit.

## Rerun list, priority-ordered

| P | What | Question it answers | Cost (w) |
|---|---|---|---|
| 0 | Bring-up gate above | is the instrument sound on 3.8? | ~1 h |
| 1 | **Slice 1.1R**: identical protocol, digests, seeds (1, 2), current `e2_slice.py` (repaired digest, lifted cap) — only the model changes | does the rule-channel ~zero survive a generation jump? cleanest possible model contrast; also re-reads goal/hidden-state channels for free | 1 night if speeds comparable |
| 1 | Fresh trace autopsy on the 1.1R traces | 3.8's failure modes are not 3.6's; the display repairs stay, the reading list resets | hours, zero model |
| 2 | Probe regeneration on 3.8 + scoring through the probe executor (model-independent machinery, built once) | is 3.8 a better experiment designer? | 1 slice + executor run |
| 2 | Hidden-state channel beyond m0r0 (if the parity loop-closure template worked) | can 3.8 propose latents where 3.6 couldn't? | rides on 1.1R |
| 3 | Mini-S1: reference agent spot-check on 3.8, few games incl. cleared-4 + tu93/m0r0 | does `goal_unknown` persist? does the prior mechanism persist? decides whether 3.8 becomes the deployed actor | expensive — decide only after P1 results |

**Decision checkpoint**: the slice-2 shape (and the deprecate-rule-channel call) is
re-opened **only if 1.1R contradicts the 3.6 verdicts.** Until the gate + 1.1R are done,
current work proceeds unchanged — everything being built now (probe executor, parity
injection, repaired digests, floors) is model-independent and pays off for either model.

## What does NOT rerun

All zero-model results are model-free and stand as-is: E0/E1 explorer stores and
outcomes, the dose floors (v1 and v2), memorizer floors and human ceilings, the goal
grammar curves, REPLAY-DET, conflict censuses, mechanical machinery of every kind. S1's
trace record stands as evidence about the 3.6-era reference (its *conclusions* about the
prior mechanism are (3.6)-tagged like everything model-bound).

## Comparability rules

- Every model-bound number states its model from now on; never mix 3.6/3.8 in a table
  without a model column.
- Floors and targets are shared across generations (zero-model) — cross-generation
  deltas against them are valid and are the point.
- Slice 1.1 (3.6) vs slice 1.1R (3.8), identical protocol: a clean model-generation
  contrast under a fixed instrument — paper-relevant, keep the protocol frozen for it.
- 3.6 artifacts (probes passed, traces, slices) are never deleted or overwritten;
  3.8 outputs get their own tags/paths (`*_38_*` or a `model` field, as the harness
  already records).

## Where this note is marked

- `CLAUDE.md` — operative section (every session reads it).
- `notes/e2-dose.md` — dated addendum next to the model pin it supersedes-in-time.
- Agent memory (cross-session).
- This file in git log.
