# S1 Close-out

**Status: IN PROGRESS.** S1-a complete; S1-b complete with a caveat; S1-c partial; S1-d and S1-e not
started. This file is written incrementally, not at the end.

---

## Session log — 2026-07-26

### What was established

| Item | Result |
|---|---|
| **S1-a** | Reference frozen (Tufa duck harness, Qwen3.6-27B-FP8) + alternate (mbmmurad Gemma-4-31B). All `PROPOSED` values resolved; manifest frozen |
| **R1** | `deterministic` — 2 games × 2 prefixes × 3 replays, byte-identical, falsification check passed |
| **R2** | `accumulates`, `r` = 2.0357, waste validity 84/84. **`c_reset` = 1 measured** (RESET is itself scored) |
| **Controller fork** | **surgical information-per-action** — every probe costs score |
| **S1-b hard exit** | vc33 level 1 in **9 actions** (baseline 7), score **60.49**, log on disk |
| **S2 inheritance** | Measured across all 25 games and reproducible (`measure_arc_conventions.py`) |
| **Kaggle reference** | Full 25-game run on the true reference: 0 games won, 3806 actions, **mean score 2.19** |
| **Verification** | V2 resolved, V8 corrected, V15 closed as a premise error. Block frozen |

### The three-way model comparison (same game, same harness)

| configuration | levels | actions | game score |
|---|---:|---:|---:|
| Kaggle reference (27B dense FP8) | **2/7** | 49 | **10.71** — saturated the completed-weight cap |
| local dense (27B MLX 4-bit) | 1/7 | **9** | 2.16 |
| local MoE (35B-A3B, D11) | 0/7 | **742** | 0.00 |

**Conclusion: the MoE is a throughput vehicle, not a taxonomy vehicle.** ~5.2× faster per action and
~70× faster in wall-clock per action, with no progress. Use it for harness, latency and iteration work;
gather the Day-5 taxonomy on the dense 27B.

### Errors made and corrected (kept, because they shaped the work)

1. **120 s analyzer timeout** — the reference's value, calibrated for FP8 on an RTX PRO 6000. Locally
   **62% of generations exceeded it**, so most requests were cut off and retried. Every earlier local
   measurement of *agent behaviour* was measuring a misconfigured harness. Fixed as **D10**.
2. **Makefile bypass** — driving `inference.framework.run` directly drops every config-sourced setting
   to its code default. This silently disabled D6 request logging and replaced `tool_steps: 0`
   (unlimited) with 12. Fixed by `agent/harness/run_local.sh`.
3. **The same bug, in my own launcher** — `--analyzer-timeout` was never passed, so D10 had no effect on
   its first attempt. Caught because 6 timeouts in 25 minutes is impossible at a 900 s limit.
4. **Action counts were event-row counts** — `analysis` snapshots counted as actions. The hard-exit score
   was understated 2.4×, and the ft09 runs reported 24/8/20 actions when they executed **zero**.
5. **Three successive wrong explanations** for the ft09 stall (identical-inspection looping, then
   convergence failure) before reading the run log, which had the timeout in plain text throughout.
6. **Concurrency sweep measured on an unrepresentative prompt** — quoted as agent throughput when it was
   short-prompt synthetic.

---

## ⛔ Publishing policy

**This repository is never made public.** Entrant-authored work is released as a **new, clean
repository** built from scratch. `agent/reference/` holds an unlicensed third-party snapshot, and
**deleting it is not sufficient — git history counts as redistribution.** Full policy and the
publishable/not-publishable table: [`PUBLISHING.md`](../PUBLISHING.md).

Consequence already recorded: the reproduction cannot be the Day-6 payload, so a leaderboard reference
requires entrant-authored work — otherwise S1 exits on the §4.7 DEGRADED branch.

## S1-e stopped after one chunk at concurrency 2 — and why

**The local breadth run was stopped deliberately, not abandoned.** Two findings made the remaining
~8 hours poor value:

**1. Action rate is dominated by action TYPE, not by concurrency.** At concurrency 2, in 16 minutes:

| game | action space | actions |
|---|---|---:|
| `wa30-ee6fef47` | keyboard (ACTION1–5) | **59** |
| `lp85-305b61c3` | click (ACTION6 only) | **1** |

Projected to 45 min: ~166 versus ~3. Keyboard games reach reference-comparable volume (the reference
averaged 152 actions/game); click games produce stubs at any concurrency reachable locally. Fifteen of
the 25 public games open with ACTION6.

**2. We already hold better taxonomy data than the run would produce.** The completed Kaggle reference
run yields **25 failure episodes on the true reference model**, with full evidence packets. The local
run would have added ~6 keyboard episodes on a *different quantisation*, plus ~15 stubs.

**What the local run is still needed for is narrow:** the S1-c local thresholds. Those need a modest run,
not 25 games — `legal_action_validity` (0.9545) already came from chunk 1, and latency from earlier runs.

### 🔴 The pre-registration problem this exposed — erratum S1-E7

A failure episode is a level attempt that did not advance, so **one pass over a game yields at most one
episode.** Twenty-five games therefore yield at most 25. Measured on the reference run: **exactly 25**
(15 L2+, 10 L1). The manifest pre-registered `blind_rerate.sample_size: 30`.

**30 was never achievable from a single pass**, and the check was available at S1-a — the episode
definition and the game count were both already known. It was accepted at its PROPOSED value without
being tested against the achievable count.

Unresolved, and deferred deliberately: it trades runtime against statistical power. **Until it is
resolved, no re-rate sample should be drawn** — the draw script refuses unlabelled input but will not
refuse an under-powered one. If it is still open at S1-g, the consequence must be stated: no agreement
statistic means the `agreement_floor: 0.40` gate cannot be applied, and categories would drive the build
order with no stability check at all.

## Actionable queue while S1-e runs## Actionable queue while S1-e runs (all CPU-only — must not contend for the GPU)

Ordered by whether S1-e's output depends on them.

### Must be done BEFORE S1-e's episodes are labelled

1. **Separate level-1 from level-≥2 episodes in `s1d_label.py`.** The reference analysis showed 15/25
   games clear level 1 and only 3 clear level 2 — so a frequency ranking pooled across levels would be
   dominated by the easy case and would rank the *wrong* build order. The episode record already carries
   `level`; the frequency function must stratify on it.
2. **Blind re-rate sampling script.** Manifest `blind_rerate` requires: label first → draw a sample
   stratified by `primary_label`, oversampling `goal_unknown` and (per S1-E4) `exploration_or_probe_selection`
   restricted to the six simple-action games → produce a blinded copy stripping labels/confidences/notes
   while preserving the full evidence packet including `reasoning_text`. Needed on Day 5, not Day 7.

### Closes an open threshold

3. **D12 — runtime action logging.** `legal_action_validity` is currently *not measurable*: the agent
   builds action lists programmatically, so `emitted` cannot be recovered from tool source. A patch
   logging every action passed to `action()` at runtime would make it a real number. Cheap to write;
   needs a run to validate, so it would apply to a later run rather than S1-e.

### Standing obligations (§5)

4. **Methods prose** for S1-c and S1-d into `paper/methods/`, written the day they were built.
5. **`paper/hypotheses.md` / `related-work.md`** — the daily 30 min. Related-work already has the field
   survey; hypotheses has had nothing added today despite R1/R2 resolving the controller fork.

### Needs a decision or an outward-facing action — NOT mine to take

6. **Bucket-2 licence.** All three Tufa datasets declare no licence. Resolving it means **posting a
   question on the competition discussion thread under your account**. It blocks the S1-f payload if
   TAAF code ships, and blocks making this repository public. I have not posted anything.
7. **Whether to spend today's submission slot.** Untouched since S0. S1-f wants a leaderboard reference,
   but we have no *own* payload yet, and submitting the reference notebook would be someone else's work
   under an unresolved licence.

---

## S2 inheritance — ARC-compatible conventions the generators must match

**Measured 2026-07-26 across all 25 public games** (not taken from documentation). Close-out item 5;
the plan calls this "cheap now and expensive on Aug 12", and one item below would have been expensive.

**Reproducible evidence:** `agent/harness/measure_arc_conventions.py` → `logs/s2_arc_conventions.json`.
Every value in this section regenerates from that script; it was added after review noted the section
originally carried prose only, which could not be independently checked.

| Convention | Measured value |
|---|---|
| Grid shape | **64×64, always**, at reset across all 25 games |
| Cell values | **0–15, and all 16 values occur** — the documented range is fully exercised |
| Frames per observation | **1–N, and N VARIES WITHIN AN EPISODE** — see below |
| Levels per game | 6–10 (mode 6) |
| Level-1 human baselines | 6 (vc33 = 7) to 78; across all levels, up to 578 |
| Action space | `RESET` + `ACTION1`–`ACTION7`; `ACTION6` carries (x, y) |
| Action availability | **per-game** (measured). At reset: `ACTION6` in 19/25 games, `ACTION1–4` in ~16–17, `ACTION5` in 9, `ACTION7` in 6. ⚠ **Per-*state* variation is NOT evidenced** — see below |

### 🔴 The one that would have been expensive: observations are frame *sequences* of varying length

`FrameDataRaw.frame` is a **list** of 64×64 grids, not a single grid. Two games return 2 frames at reset
(`bp35-0a0ad940`, `lf52-271a04aa`) while 23 return 1 — but the count is **not a static per-game
property**. Stepping `ls20-9607627b` produced this sequence of frame counts:

```
1, 1, 1, 1, 1, 1, 1, 6, 6
```

Seven single-frame observations, then **six frames** in one observation. This is the environment's
"1–N grid frames" contract behaving dynamically — presumably animation of a multi-step consequence.

**Consequences for S2 and S4, to be honoured at design time rather than patched later:**

1. **The F1/F3 generators must emit variable-length frame sequences per observation**, not a fixed one
   grid per step. A generator that always emits one frame would produce a distribution the real
   environment never generates, and S4's advisor test would then be measured on a mismatch.
2. **Any encoder must consume 1–N frames per step.** A model assuming a single grid silently discards up
   to five-sixths of the observation at exactly the steps where something interesting happened — which is
   the worst possible place to lose information, and would be invisible in aggregate loss.
3. **This interacts directly with F1 (history-required aliasing).** If an observation is itself a short
   sequence, part of the "history" the aliasing test is about is *inside a single observation*. The
   generator's notion of a timestep must be defined against this, or F1's ceilings measure something
   other than what they claim.
4. Padding: grids are already uniformly 64×64, so no padding convention is needed — but record that this
   is *verified serialization*, not necessarily the environment's intrinsic grid size.

### ⚠ Correction — "per-state action availability" was asserted, not measured

An earlier version of this table said availability is "per-game **and per-state**, re-read every step".
Only the per-game half is measured. Probing `ls20-9607627b` for 8 steps records
`available_actions` unchanged at `[1,2,3,4]` throughout
(`logs/s2_arc_conventions.json → availability_varies_within_episode: false`).

What is true: the *harness* re-reads `available_actions` every step, and the reference's prompt describes
it as "the current list of valid action names" — so the interface permits per-state variation. What is
**not** established is that any game exercises it. A generator built to vary the action set per state
would be modelling a behaviour we have not observed; one built to hold it fixed per game matches
everything measured. **Leave this open and widen the probe before S2 commits to either.**

### Also inherited

- **Scoring** as V8 corrects it: `min(115, (baseline/actions)² × 100)` per level on a 0–100 scale, level
  score capped at 115, game score capped at completed-weight fraction, unweighted mean across games.
- **`c_reset = 1`** — RESET is itself a scored action (measured in R2).
- **Determinism** — offline environments replay exactly (R1), so generator-side reproducibility is a fair
  assumption for the offline path.

## S2 inheritance (original stub)

## Paper deposit
