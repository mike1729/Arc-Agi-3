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

*Amendment 2026-08-05 (S1 end-to-end read, `aca2d47`): the carried schema is also a
trap.* All three sb26 reference passes failed L2 (156/252/203 actions vs baseline 28) by
enumerating variations **inside** the carried L1 schema; the ft09 passes that cleared L2
did so by treating "predicate satisfied, level did not advance" as a contradiction that
forces re-derivation, and the one pass that lost that thread brute-forced and timed out.
Rule for X: the carried predicate is tested first and **abandoned on first
contradiction** — the executor never enumerates within a contradicted schema;
contradiction routes to fresh-universe re-derivation. Anchor-trap frequency (plans built
inside a contradicted schema) is an E3 readout column.

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

---

# Results — X1 and X2, 2026-08-05

Ran per `notes/e3-x1-x2.md`. Zero model calls, zero game contact. Code
`agent/harness/e3_executor.py`, numbers `logs/e3_x1.json` (24 store games) and
`logs/e3_x2.json` (the 4-game cohort). Store `logs/e1_store_v2/` frozen, miner `rs_e0.mine`,
guard vocabulary **v2**, effect mode `full` with `moveset` as the coarser second view.

```
.venv/bin/python agent/harness/e3_executor.py --stage x1 --jobs 8 --out logs/e3_x1.json
.venv/bin/python agent/harness/e3_executor.py --stage x2 --jobs 4 --out logs/e3_x2.json
```

**Naming, stated once.** The design's `confident` (top trust) is `rs_e0`'s tier0 **and**
tier1 — both are mined zero-contradiction; `weak` is `rs_e0`'s `majority`. Mining and
firing run on the same store, so `uncovered` is 0 on every game **by construction** and the
`confident` effect accuracy is **1.000 by construction on all 24 games** — the tautology the
task note names. Neither number is evidence and neither is read as such below.

## X1 — forward-model self-check

| game | store edges | state-changing | confident | weak | weak eff. acc (full/moveset) | recon determinate, all | recon determinate, state-changing |
|---|---:|---:|---:|---:|---:|---:|---:|
| ar25 | 2972 | 711 | 0.722 | 0.278 | 0.730 / 0.758 | 0.761 | 0/711 |
| bp35 | 2873 | 2873 | 0.000 | 1.000 | 0.844 / 0.852 | 0.000 | 0/2873 |
| cd82 | 2922 | 2088 | 0.000 | 1.000 | 0.511 / 0.511 | 0.285 | 0/2088 |
| cn04 | 2885 | 2016 | 0.000 | 1.000 | 0.368 / 0.368 | 0.301 | 0/2016 |
| dc22 | 2939 | 1825 | 0.000 | 1.000 | 0.433 / 0.441 | 0.379 | 0/1825 |
| ft09 | 1231 | 88 | 0.824 | 0.176 | 0.636 / 0.636 | 0.928 | 0/88 |
| g50t | 1448 | 1132 | 0.000 | 1.000 | 0.270 / 0.271 | 0.218 | 0/1132 |
| ka59 | 2923 | 2181 | 0.000 | 1.000 | 0.493 / 0.513 | 0.254 | 0/2181 |
| lf52 | 146 | 145 | 0.438 | 0.562 | 0.598 / 0.598 | 0.000 | 0/145 |
| lp85 | 42 | 6 | 0.857 | 0.143 | 0.833 / 0.833 | 0.854 | 0/6 |
| ls20 | 2877 | 2870 | 0.000 | 1.000 | 0.670 / 0.683 | 0.002 | 0/2870 |
| m0r0 | 2943 | 1716 | 0.000 | 1.000 | 0.511 / 0.545 | 0.417 | 0/1716 |
| r11l | 130 | 129 | 0.000 | 1.000 | 0.638 / 0.661 | 0.000 | 0/129 |
| re86 | 2911 | 2905 | 0.000 | 1.000 | 0.242 / 0.300 | 0.002 | 0/2905 |
| sb26 | 2986 | 884 | 0.342 | 0.658 | 0.693 / 0.693 | 0.704 | 0/884 |
| sc25 | 1606 | 630 | 0.355 | 0.644 | 0.460 / 0.465 | 0.608 | 0/630 |
| sk48 | 2995 | 408 | 0.821 | 0.179 | 0.362 / 0.399 | 0.864 | 0/408 |
| sp80 | 1014 | 1013 | 0.099 | 0.901 | 0.918 / 0.918 | 0.000 | 0/1013 |
| su15 | 358 | 197 | 0.226 | 0.774 | 0.953 / 0.953 | 0.464 | **5**/197 |
| tn36 | 2875 | 2875 | 0.000 | 1.000 | 0.891 / 0.891 | 0.000 | 0/2875 |
| tr87 | 2925 | 2925 | 0.000 | 1.000 | 0.348 / 0.370 | 0.000 | 0/2925 |
| tu93 | 2573 | 2573 | 0.000 | 1.000 | 0.520 / 0.520 | 0.000 | 0/2573 |
| vc33 | 800 | 800 | 0.000 | 1.000 | 0.920 / 0.920 | 0.000 | 0/800 |
| wa30 | 2960 | 2578 | 0.000 | 1.000 | 0.586 / 0.586 | 0.129 | 0/2578 |

**1. Coverage.** Mean `confident` coverage **0.195**; **15 of 24 games have none at all** —
every action key is unresolved in the guard vocabulary, so every rule is majority-tier. Rule
counts are small throughout (4–18 per game): the key space is the simple actions plus ACTION6
keyed on the clicked colour, and one guard.

**2. Weak-class effect accuracy** (the non-tautological effect number): **0.242–0.953,
median 0.592**. The `moveset` coarsening — dropping movement vectors — buys almost nothing:
median 0.592, unchanged to three decimals, and identical rule counts and coverage on every
game. Whatever is failing is not vector precision.

**3. Reconstruction fidelity — the crux.** Across the 24 stores, 50,330 edges have a real
post frame; **35,568 (70.7%) actually changed the board**.

- The reconstructor is **sound**: wherever the *recorded* effect is determinate, applying it
  to the pre-grid reproduces the post-grid exactly — **14,767 / 14,767, all 24 games, no
  exceptions**. The canvas-and-paint decomposition is lossless (`identity_check` clean on
  every game). So what follows is a statement about the effect vocabulary, not about the
  implementation.
- The recorded effect is determinate on **14,767 / 50,330 (29.3%)** of edges — and **14,762
  of those 14,767 are no-op edges**, where the pre-grid is trivially the answer and the
  planner sees a self-loop. On the edges that move the board the grammar pins the next state
  on **5 of 35,568 — 0.014%**, all five in su15.
- The mined model, judged the same way: determinate on 14,761 edges, of which **3,385 are
  state-changing edges the model predicted as no-ops** — determinate and useless. Exact
  next-state match on state-changing edges: **0 / 35,568**.
- **Underdetermined kinds** (35,563 blocked edges; each blocked edge counted under every kind
  that blocks it): `reshape` 31,988 · `appear` 18,387 · `assignment` 12,475. Sole blocker:
  `reshape` alone 16,036 · `appear` alone 2,365 · `assignment` alone 180. `over_assignment`,
  `collision` and `out_of_bounds` never fired — nothing fails at the painting step; it all
  fails before it.

The mechanism is the position-free vocabulary doing exactly what it was designed to do.
`("reshape", c)` names a colour and says nothing about the new cells; `("appear", c)` gives
neither position nor extent; k events against m > k same-colour components do not say which
ones. Those are the properties that let a rule survive a level change (`rs_transitions`), and
they are the same properties that make the signature unusable as a transition function. Real
edges are also compound — a typical ar25 movement edge carries ten events, mixing `move` with
`appear`/`disappear`/`reshape` of other components, so a single blocking event in the bundle
sinks the whole edge.

**4. Moveset view.** Reported in the table; it cannot reconstruct anything by construction
(the vectors are dropped), and it does not improve effect accuracy either.

## X2 — planner on known ground

Cohort as specified; goal = the store's own recorded completion pre-state, plan = path +
the recorded completion action; BFS (unit action cost, so BFS is optimal and iterative
deepening would only re-expand — no admissible heuristic exists that was not invented for
this run); closed set on state hash; confident edges first, relax to weak, never through
uncovered. Action repertoire (w) = the distinct actions the explorer itself issued on that
game, RESET excluded.

| game | plan found | nodes expanded | forward-step census at the origin | store-only plan | explorer | human L1 baseline |
|---|---|---:|---|---:|---:|---:|
| lp85 | **no** | 1 | 16 confident **self-loop**, 1 confident underdetermined, 1 weak underdetermined, 1 uncovered | 7 | 43 | 17 |
| r11l | **no** | 1 | 66 weak underdetermined | 10 | 135 | 22 |
| lf52 | **no** | 1 | 6 confident + 32 weak underdetermined | 72 | 149 | 32 |
| sp80 | **no** | 1 | 46 confident + 34 weak underdetermined | 17 | 1106 | 39 |

**0 of 4, at both relaxation levels, and not by timeout** — every search terminated in
0.02–0.10 s having expanded the origin and found no legal successor at all. The caps
(400k nodes / 600 s) were never approached. On lp85 the model does produce 16 determinate
confident predictions at the origin and every one of them is "nothing happens": a self-loop
the closed set discards. On the other three, every predicted effect at the origin is
underdetermined. No plan exists to report composition for; no closed set ever grew past one
state, so nothing was merged and the sp80 latent-distinct question does not arise this round.

**The one positive number, and it is not the model's.** BFS over the *recorded* store edges
alone reaches the completion pre-state on all four games, at **7 / 10 / 72 / 17** actions
against the explorer's own **43 / 135 / 149 / 1106** — and against the human L1 baselines
**17 / 22 / 32 / 39**, that is shorter than the human baseline on three of four (lp85 7 vs 17,
r11l 10 vs 22, sp80 17 vs 39) and longer on lf52 (72 vs 32). These paths are replay-verified by construction (they are the store's own
prefixes: 6 / 9 / 71 / 16 edges, matching the completion rows' recorded `prefix` fields) and
carry the prefix audit's verification rates — 1.00 on lp85/r11l/lf52, **0.72 on sp80**, whose
row therefore stays provisional. They involve no forward model, no rules, and no
generalization: this is replay, and it is X3's cheapest experiment, not a planning result.

## Gate sentences

**X1 — the model is not rollable.** Rules mined from the explorer's own store reconstruct
the next state exactly on 100% of the edges where nothing happens and on **0 of 35,568**
edges where something does; the recorded effect grammar itself pins a moving next state on
**5 of 35,568 (0.014%)**, blocked overwhelmingly by `reshape` (31,988 edges) and `appear`
(18,387). The plannable fraction of the graph is, for search purposes, zero — the coverage
split (mean 0.195 confident, 15 of 24 games with none) is not the binding constraint.

**X2 — search does not recover the known completions, and the failure is structural, not
budgetary.** 0 of 4 games, at both relaxation levels, each search terminating in under 0.1 s
with no expandable successor at the origin; the only paths to the recorded completions are
the store's own replay-verified edges (7 / 10 / 72 / 17 actions vs the explorer's 43 / 135 /
149 / 1106).

## What this changes

X3 as designed (execute X2's plans) has nothing to execute. Before any planner is built
further, the effect vocabulary has to be split in two: the **position-free signature** stays
what rules are mined and transferred in, and a **grounded delta** — the one that names cells
— is what the forward model steps with. Whether the delta can be predicted at all is an open
question this stage did not ask. Two smaller findings worth carrying: the `moveset`
coarsening buys nothing and can be dropped from the planner's consideration; and the
store-only replay paths are a cheap, immediately runnable L1 experiment that needs no model
at all.

**Caveats.** Confident-class effect accuracy is tautological (mined and scored on one store)
and is not quoted as evidence. `uncovered` is 0 for the same reason — an out-of-distribution
state would not be. The action repertoire is the explorer's own (w), so X2's branching is a
lower bound on a real action space. sp80's state hashes are only 72% replay-verified
(`logs/e1_prefix_audit.json`), which taints any sp80 path claim, model or store. Everything
here is miner output — model-free, not (3.6)-bound, and unaffected by the Qwen 3.8 transition.
