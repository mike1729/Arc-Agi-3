# E3 — the X-phase executor: search over the mined model (design)

**2026-08-05. Status: design, not results.** Drafted while E2's model-side questions run;
the executor is **pure machinery** — zero model calls in the core, so nothing here is
(3.6)-bound and all of it survives the Qwen 3.8 transition. Frame from
`notes/l1-evidence-first.md`: *L2 clear rate and efficiency with the L1-built model vs
vendored taaf on the same games; misprediction frequency, repair cost, full-fallback
frequency; wall-clock priced against the (unverified, ~8 h) envelope.*

## Honest-input boundary

Executor inputs are the system's own: the E1 store, rules mined from it, goal candidates
from its own evidence, and its own L2 actions. **Human replays never flow in** — they
stay external test/comparison data, or E3 stops measuring the autonomous system. taaf is
the comparison baseline, vendored unmodified (`agent/reference/taaf`; deviations as patch
files per standing convention).

## Eligible cohort

Autonomous L2 entry requires an autonomous L1 completion. The E1 v2 explorer completed
4: **lp85 (43 actions), r11l (135), lf52 (149), sp80 (1106)** — the initial E3 cohort.
All four have the completion row retained in the store (the one positive goal example).
Games without autonomous L1 completion enter the cohort if/when X itself completes their
L1 (stage X2 below tests exactly that on known ground).

## Components

**1. Forward model over mined rules.** State = object catalogue (existing segmentation /
`_Objects`); a step is O(objects), never O(64×64); closed set on state hash. Applying an
action returns a predicted effect signature plus a **confidence class**:
- `confident` — a tier-1 rule fires (support > 0, zero contradictions on store);
- `weak` — only a majority-tier rule fires;
- `uncovered` — unresolved key or no rule.
The planner treats these differently; that split is the design's load-bearing idea, and
the measured basis exists (per-game tier-1 guard families and failure splits in the dose
files).

**2. Planner.** Iterative-deepening A* over predicted states toward the goal predicate.
Plan cost = actions (the scorer's currency). Expansion policy: **confident edges first;
relax to weak edges only if no plan is found** — a policy switch, not a numeric penalty,
so nothing is invented. Uncovered edges are never planned through; they are probe targets
(component 4).

**3. Execution + verification.** Execute the plan one action at a time; compare observed
vs predicted effect signature. Match → continue. Mismatch → repair policy. Every executed
transition is appended to the (X-phase, sidecar) evidence pool regardless.

**4. Repair policy.** On mismatch, classify against the miner's failure taxonomy:
- **guard-fixable** (the rule family exists, the guard split it wrong) → local repair:
  a few targeted probes at the failure context, then re-guard that rule on pooled
  evidence. This is the same replay-to-state-and-deviate machinery the probe-channel
  task is building now — shared component, build once.
- **unpredicted** (no rule family covers what happened) → invalidate + re-mine on pooled
  evidence; replan.
The repair-vs-invalidate default comes from the **measured per-game failure split**
(`failure_split` in `logs/e2_dose_vocab_v2.json` — e.g. sp80's human-L2 failures are 174
guard-fixable / 0 unpredicted, a repair-dominant profile), not from an invented
threshold. Worst case: E-phase re-entry on the current level (explore, re-synthesize),
taxing only that level — a legitimate outcome E3 counts, not a crash.

**5. Goal supply — active disambiguation, not oracle goals.** Priority order:
1. Row-C grammar survivors of the store's own negatives **plus the own completion
   positive** (available for all 4 cohort games). Multiple survivors are not a blocker:
   plan to the nearest state satisfying **any** survivor — executing there either
   completes the level or falsifies candidates in situ. Goal probing is evidence.
2. Completion-row precondition matching where the grammar keeps nothing.
3. Neither → X cannot plan; E-phase on L2 until completion/saturation. Counted as
   `goal-starved` — the E3 measurement of the goal gap, not a failure of the harness.
Qwen goal candidates are **excluded in v1** (the (3.6) channel measured weak); the seam
stays open for 3.8 per `notes/qwen-3.8-upgrade.md`.

**6. L2 goal transfer.** On L2 entry, the L1-identified goal predicate (when L1 completed
through a candidate that survived) is re-instantiated on L2's objects and tested
**first**; fresh universe enumeration + active disambiguation is the fallback. Whether
the goal family transfers is itself an E3 readout column.

**7. taaf comparison harness.** Vendored taaf on the same games, same driver, same action
accounting, same scorer arithmetic (`min(115, (baseline/actions)² × 100)`, level-position
weights). Report per-game clears and actions side by side.

## Build order — each stage gates the next, zero model calls throughout

- **X1 — forward-model self-check (pure compute).** Replay each store through its own
  forward model: self-prediction accuracy and the confident/weak/uncovered edge fractions
  per game. This is the ceiling sanity number — if self-prediction is weak on the
  explorer's own distribution, stop and say so.
- **X2 — planner on known ground (pure compute).** For the 4 cohort games: does search
  over the model find the L1 completion the explorer found — and shorter? Ground truth
  exists (store completion prefix + per-level human baselines in the game source's
  metadata, labels only). Readout: found / plan length / vs human baseline / vs
  explorer's path.
- **X3 — live execution + repair on L1.** Execute X2's plans in the live games;
  mispredictions exercise the repair machinery where the answer is known. Readout:
  clears, actions, mispredictions/action, repair outcomes by class.
- **X4 — E3 proper.** L2 entry via replayed completion; the full loop on L2; taaf
  comparison; the E3 metric set: clear rate · actions · scorer value · mispredictions ·
  repairs (local vs invalidate) · full-fallback count · goal-starved count · wall-clock.

X1/X2 are runnable with nothing but the store and the miner — no game contact, no risk,
immediate numbers. That is deliberately the first week's work.

## Risks, stated

- **Transfer accuracy is low** (median on-human-L2 ~0.08–0.13 full mode). If that rate
  applies to planned trajectories, multi-step L2 plans break early and often → the system
  lives in the repair loop. X1/X3 measure whether the repair loop converges on L1 (where
  self-accuracy is far higher) before L2 exposes the hard case. The moveset layer
  (median 0.188, at parity with the human ceiling) may carry more of the planning load
  than exact effects — X1 reports both.
- **Goal supply is the known weak flank** (S1: `goal_unknown`). The active-disambiguation
  design turns ambiguity into actions instead of stalls, but `goal-starved` on L2 is a
  live possibility and is counted honestly.
- **taaf parity**: identical driver and action accounting must be verified before any
  comparison number is quoted (`agent/work/taaf` has run configs from the kaggle_v*
  probes).

## Working defaults — all (w), all from measured data

Repair-vs-invalidate split per game from `failure_split` · expansion relaxation
(confident→weak) as a recorded policy switch · E-lite budget on L2 from E1's
actions-to-outcome distribution · nothing else parameterized until X1/X2 report.

## Handoff

X1 and X2 are one implementable unit (`agent/harness/e3_executor.py` + this note's
results section) — pure compute, no conflicts with the three live tasks, same isolation
rules (new files only, stage own files). X3/X4 need the live-game driver and should wait
for X2's readout and the probe-channel task's replay machinery, which they share.
