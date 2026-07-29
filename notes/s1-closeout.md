# S1 Close-out

**Status: CLOSED 2026-07-28, on the DEGRADED branch.** S1-a through S1-e are complete, the blind
re-rate is scored and promoted, and the manifest's four roll-up fields are filled from it. **No hidden
score exists and none is coming from S1** — the reproduction was withdrawn as a candidate payload by
operator decision on 2026-07-26, so S1 exits via §4.7's DEGRADED branch by scope change rather than by
a rejected submission.

> The opening status line above was stale for two days: it read *"S1-d and S1-e not started"* while
> both had run. This file is written incrementally, which is why the body below is a session log in
> date order rather than a summary — but a status line that describes a state two sessions old is worse
> than no status line, because it is read first and believed.

| | |
|---|---|
| **Gate** | `agreement_floor: 0.40` **APPLIED** — overall κ **0.7207**, 30 of 30 scored, floor exactly 0.40 |
| **Build order** | `goal_unknown` → `action_semantics_unknown` → `exploration_or_probe_selection` → `progress_signal_misinterpretation` |
| **Excluded** | 6 measured and below floor · 1 (`reasoning_inconsistency`) never drawn · 2 (`coordinate_unreachable`, `planning_depth`) structurally unobservable |
| **Hidden score** | **null**, permanently for S1. DEGRADED branch, costs recorded in the manifest |
| **Result of record** | [`logs/s1d_rerate_result.json`](../logs/s1d_rerate_result.json) — promoted, `gate_valid: true`, carrying its own invalidation chain |
| **Still open, not S1's** | `gate_manifest.yaml → s2` is `NOT_STARTED`. That was listed as an S1 exit item; with the gate closed it is an **S2 governance blocker** and blocks nothing in S1 |

---

## Session log — 2026-07-28 · the gate, applied

The measurement work was already done; what was missing was the gate itself, and running it changed
the build order rather than confirming it.

**Procedure, in the pre-registered order.** Label → sample → blind → re-rate → score → promote. The
sample was drawn by `s1d_blind_rerate.py draw` over the 75-episode pooled corpus at the pre-registered
`n = 30` and the default seed, stratified on first-pass `primary_label`, oversampling `goal_unknown`
(44 of 44 eligible) and `exploration_or_probe_selection` (**1 of 4 eligible** under S1-E4 — the
eligible pool is a minority by construction, and that fraction is reported beside the statistic
because an agreement number computed on a subset must say which subset). The draw wrote its
authoritative `.manifest.json` sidecar; scoring re-derives the selection from the corpus rather than
believing it.

**The second pass was produced in a fresh `claude-opus-5` context** with no access to this repository
at all — not the labels, not the notes, not the manifest. It was given exactly two files: the
taxonomy brief and a worksheet rendered by the unmodified `s1d_worksheet.py` from the *blinded* draw,
so the evidence slice matches the first pass's by construction rather than by assertion.

**Result: κ 0.7207 overall, 25 of 30 exact matches on primary label.** Four categories clear the floor
on both axes and drive the build order; six were measured and excluded; one was never drawn.

### What the gate actually changed

Two things, and neither was predictable from the frequency table alone.

**1. `latency_or_budget` is out, and it was the second-most-frequent label in the corpus.** Its primary
κ is 0.7826 — high — while its any-label κ is 0.011. All 75 episodes were budget-terminated, so the
label is available everywhere; the two passes then diverged on whether termination *caused* the failure
or merely ended it. The first pass attached it to 27 of the 30 sampled episodes, the re-rate to 11,
overlapping on 10. Its `episode_share` of 0.8267 would have put it near the top of any
frequency-ordered build list. **The two-axis rule is what caught it**, and a gate defined on primary
agreement alone would have passed it at 0.78.

**2. `irreversible_mistake` inverts the same pattern** — any-label κ 0.5946, primary κ 0.0. The raters
agree it is *present* and disagree entirely about whether it is *causally earliest*. Also excluded, and
for the opposite reason.

Both are arguments for the rule the scorer already encodes: the weaker axis decides.

### `reasoning_inconsistency` was not tested, and that is not the same as failing

It carries 1 episode in 75 and was not drawn into the sample, so it has no κ at all. The manifest
records it as `agreement_status: "untested"` rather than folding it in with the six that were measured
and failed. Both are excluded from the build order; only one of them is evidence about label stability.
A row that reads `survives_agreement_floor: false` with a null κ beside six real κs would otherwise be
read as a seventh failure.

### The one asymmetry left in the measurement

The v2 first-pass labels predate `s1d_worksheet.py` and came from an ad-hoc, unreproducible slice; the
re-rate used the scripted worksheet for all 30. So 22 of 30 episodes were rated on matched evidence and
8 were not. **This did not inflate the result.** Split by provenance: the 8 v2 episodes agree 8/8
(κ 1.0), the 22 matched ones 17/22 (κ 0.6194). The matched-evidence subset is the *more conservative*
number, so 0.7207 is if anything flattered by the unmatched 8 rather than propped up by them. At n = 8
this is a diagnostic and not a finding — but the direction is the one that costs nothing to accept.

Re-doing the v2 first pass on the scripted worksheet would fix the asymmetry and **break the
pre-registration**: the order is label → sample → blind, the corpus digest commits every first-pass
annotation, and re-labelling after the draw is precisely what that digest exists to prevent. Left as a
recorded limitation.

### Closing on DEGRADED

S1 exits without a hidden score, permanently. The reproduction stopped being a candidate payload on
2026-07-26, so the leaderboard reference S1-f was designed to establish does not exist and cannot be
retrofitted by any further S1 work. The costs are recorded in the manifest and are unchanged by the
gate closing: S5's B axis has no score to read, and **S4 rests on a local paired control** — same
games, same budget, same model, advisor on versus off — with **replicates mandatory**, because two
identical 25-game reference runs disagreed on cleared-level count in 9 of 25 games and the mean score
moved 2.19 → 1.14. A local positive establishes that the advisor helps *here*, not on the hidden set.

---

## Session log — 2026-07-26

### What was established

| Item | Result |
|---|---|
| **S1-a** | Reference frozen (Tufa duck harness, Qwen3.6-27B-FP8) + alternate (mbmmurad Gemma-4-31B). All `PROPOSED` values resolved; manifest frozen |
| **REPLAY-DET** | `deterministic` — 2 games × 2 prefixes × 3 replays, byte-identical, falsification check passed |
| **RESET-ACCT** | `accumulates`, `r` = 2.0357, waste validity 84/84. **`c_reset` = 1 measured** (RESET is itself scored) |
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
| local MoE (35B-A3B, DEV-11) | 0/7 | **742** | 0.00 |

**Conclusion: the MoE is a throughput vehicle, not a taxonomy vehicle.** ~5.2× faster per action and
~70× faster in wall-clock per action, with no progress. Use it for harness, latency and iteration work;
gather the Day-5 taxonomy on the dense 27B.

### Errors made and corrected (kept, because they shaped the work)

1. **120 s analyzer timeout** — the reference's value, calibrated for FP8 on an RTX PRO 6000. Locally
   **62% of generations exceeded it**, so most requests were cut off and retried. Every earlier local
   measurement of *agent behaviour* was measuring a misconfigured harness. Fixed as **DEV-10**.
2. **Makefile bypass** — driving `inference.framework.run` directly drops every config-sourced setting
   to its code default. This silently disabled DEV-6 request logging and replaced `tool_steps: 0`
   (unlimited) with 12. Fixed by `agent/harness/run_local.sh`.
3. **The same bug, in my own launcher** — `--analyzer-timeout` was never passed, so DEV-10 had no effect on
   its first attempt. Caught because 6 timeouts in 25 minutes is impossible at a 900 s limit.
4. **Action counts were event-row counts** — `analysis` snapshots counted as actions. The hard-exit score
   was understated 2.4×, and the ft09 runs reported 24/8/20 actions when they executed **zero**.
5. **Three successive wrong explanations** for the ft09 stall (identical-inspection looping, then
   convergence failure) before reading the run log, which had the timeout in plain text throughout.
6. **Concurrency sweep measured on an unrepresentative prompt** — quoted as agent throughput when it was
   short-prompt synthetic.

---

## Session log — 2026-07-27 · external review, S1 REOPENED

An external review of the three-pass / re-rate path found six blockers. All six reproduced. Five were
defects in this repository, not in the reading of it.

| # | Finding | Disposition |
|---|---|---|
| 1 | Notebook still set `bm.n_passes = 1` while the README's version 3 and S1-E11 both claim three passes | **superseded by S1-E14** — the divergence was real and had already cost a run; the resolution was to adopt single-pass runs deliberately, not to set it to 3. See below |
| 2 | `run_artifacts.py` keyed `game_runs` by `game_id`; the vendor appends one record per (pass, game) and *repeats the id* — `taaf/benchmark.py` checks uniqueness only on `pass_idx == 0` | **fixed** — keyed by pass. This is the 2026-07-26 `game_runs[0]` defect re-entering through the pass axis, and it would have served pass 2's action counts, state and wall clock as p0's and p1's for all 75 episodes |
| 3 | Corpus builder deduplicated on `(game, level)`, discarding the replicates S1-E11 was filed to obtain | **fixed, then re-scoped by S1-E14** — `--replicates` keys on `(game, level, run, pass)` and ownership keys on a **configuration signature** rather than the run directory, so same-configuration replicates pool across runs while a differently-configured run is still refused |
| 4 | Re-rate script recorded a 48 h cooling period and `delayed test-retest`, contradicting S1-E10 | **fixed** — reports `independent re-rate, same model`; cooling recorded as INAPPLICABLE, not as satisfied |
| 5 | Threshold `evidence_ref` pointed at a path that does not exist, and "26 games" described two different cohorts | **S1-E13** — see below |
| 6 | §4 marked S1 complete with the agreement gate unapplied and three roll-up fields still null | **S1 reopened** — and **discharged 2026-07-28**: gate applied at κ 0.7207, all four roll-up fields filled. The finding was correct and the re-open was worth its float; the gate excluded `latency_or_budget`, the corpus's second-most-frequent label |

### ⚠ Finding 1 was not hypothetical — the three-pass run ran one pass

The run launched as "the 3-pass reference run" **executed with `n_passes = 1`**. `logs/kaggle_v3`
confirms it: `benchmark.json` records `n_passes: 1`, 25 game-run records, no id repeated, and 25
`_p0_events.jsonl` artifacts with no `_p1` or `_p2`. The local edit setting 3 was never pushed before
launch, so the kernel ran the configuration it already had.

**Resolved by S1-E14, and not by setting the notebook to 3.** The position the accident produced was
judged the better instrument and adopted deliberately: the corpus is now built from **repeated
single-pass runs** of a byte-identical configuration. Passes inside one kernel share a session, a vLLM
server and a GPU, so they bound *within-run* variance — while S4 compares advisor-on to advisor-off as
separate runs and must clear the *run-to-run* floor. Two run-to-run pairs are measured (36% v1↔v2, 20%
v2↔v3); no within-run pass figure exists at all. `bm.n_passes = 1` is therefore now load-bearing: it is
what keeps runs 2, 3 and 4 configuration-identical and so poolable.

**The corpus is not blocked.** v2 and v3 pool to **50 evidence-bearing episodes** across 25 games — 20
game-levels with two replicates each — which already exceeds `sample_size: 30`. v4 is needed only to
reach 75, where 30 is a 40% sample rather than 60%. What made this work is the tooling change S1-E14
mandated: ownership keys on a **configuration signature**, not a run directory. Under the previous
directory rule v2+v3 collapsed to 30 episodes and silently discarded all 20 cross-run replicates.

**Do not re-rate from the 30-episode collapsed corpus.** Drawing 30 of 30 is the near-tautological
sample S1-E7 explicitly rejected; the whole point of the enlarged corpus is that 30 is a fraction of it.

Cost of the accident: ~2 h 12 m of GPU quota that bought a third replicate rather than the intended
corpus — which S1-E14 then made use of. The durable lesson is in the README: kernel status is not
evidence that the kernel you edited is the kernel that ran.

### On finding 5 — the numbers were right, the cohort was undocumented

The recorded figures reproduce **exactly** (349/355 = 0.9831; per-decision p50 median 139.39 s). What was
wrong was the provenance around them:

- the cited file is at `logs/quarantine/…`, a **quarantined** run under a superseded config, and
  `logs/quarantine/` is **untracked** — a frozen threshold cited evidence not in the repository;
- one chunk file was never the cohort; both figures aggregate all 27 tracked S1-e chunk files;
- "26 games" is the **latency** sample. Validity sums 32 game-run records over 18 distinct games.

`logs/s1c_threshold_cohort.json` is now the cohort of record, regenerable and self-checking
(`s1c_threshold_cohort.py --verify` exits non-zero on drift). The cohort takes **all** game-run records
and does not apply S1-E9 admissibility — operator decision, recorded in S1-E13 with the counterfactual
(344/350, 144.66 s) alongside. **Both verdicts PASS under either cohort**, so no verdict turned on it.

### Why S1 reopened rather than closing with a caveat

The gate was pre-registered. A stage cannot be closed on a gate that never ran — `agreement_floor: 0.40`
is unapplied and `failure_frequency_ranking`, `build_order` and `viability_verdict` are still null. The
measurement work stands and is not repeated; what reopens is the gate. Cost falls on the ~4 days of float
§4 banks, which is what the float is for.

> **DISCHARGED 2026-07-28** — see the session log at the top of this file. The gate ran at the
> pre-registered floor on the pre-registered sample size, and the roll-up fields are filled from the
> promoted result. Keeping this section is not an oversight: it records *why* a day of float was spent
> re-opening a stage that had already been marked complete once, and the reason it was right to spend
> it is that the gate excluded the corpus's second-most-frequent label.

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

> **RESOLVED — and not by choosing between runtime and power.** S1-E11/S1-E14 enlarged the corpus
> instead: three configuration-identical single-pass runs pool to **75 episodes**, so the
> pre-registered `sample_size: 30` became a **40% sample** rather than the near-tautological 30-of-30
> that made this erratum urgent. The draw executed on 2026-07-28 at exactly 30, and `score` enforces
> the constraint this section worried about — both `requested` and the scored count must equal the
> pre-registered 30 or `gate_valid` is withheld. The stated consequence never had to be invoked.

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

3. **DEV-12 — runtime action logging.** `legal_action_validity` is currently *not measurable*: the agent
   builds action lists programmatically, so `emitted` cannot be recovered from tool source. A patch
   logging every action passed to `action()` at runtime would make it a real number. Cheap to write;
   needs a run to validate, so it would apply to a later run rather than S1-e.

### Standing obligations (§5)

4. **Methods prose** for S1-c and S1-d into `paper/methods/`, written the day they were built.
5. **`paper/hypotheses.md` / `related-work.md`** — the daily 30 min. Related-work already has the field
   survey; hypotheses has had nothing added today despite REPLAY-DET/RESET-ACCT resolving the controller fork.

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

1. **The Alias/Delay generators must emit variable-length frame sequences per observation**, not a fixed one
   grid per step. A generator that always emits one frame would produce a distribution the real
   environment never generates, and S4's advisor test would then be measured on a mismatch.
2. **Any encoder must consume 1–N frames per step.** A model assuming a single grid silently discards up
   to five-sixths of the observation at exactly the steps where something interesting happened — which is
   the worst possible place to lose information, and would be invisible in aggregate loss.
3. **This interacts directly with Alias (history-required aliasing).** If an observation is itself a short
   sequence, part of the "history" the aliasing test is about is *inside a single observation*. The
   generator's notion of a timestep must be defined against this, or Alias's ceilings measure something
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
- **`c_reset = 1`** — RESET is itself a scored action (measured in RESET-ACCT).
- **Determinism** — offline environments replay exactly (REPLAY-DET), so generator-side reproducibility is a fair
  assumption for the offline path.

## S2 inheritance (original stub)

## Paper deposit
