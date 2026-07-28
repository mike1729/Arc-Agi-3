# Screening Experiments and Results — S0 through S5

> **This document does not define the deployed architecture.** It supplies evidence for the gates and
> decisions in [`arc-agi-3-implementation-spec.md`](arc-agi-3-implementation-spec.md). Where the two
> conflict, **the implementation specification governs** until explicitly amended. A result recorded
> here becomes binding only through a dated amendment to that document — never automatically.

**Written 2026-07-25. Restructured 2026-07-27** (component-first). **Re-scoped 2026-07-28** to the
evidence-and-results role, on the arrival of the binding implementation specification. Revision log
at §15.

*Historical note, retained because it explains what this file used to be:* until 2026-07-28 this
document claimed to supersede the build orders in `agent-architecture.md` §9 and
[`execution-plan.md`](archive/arc-agi-3-execution-plan.md) §13, and held both architecture documents
as uncommitted candidate designs. **That claim is withdrawn.** The implementation specification is
now binding for everything built, and its §3 tier table replaces the component inventory that used to
stand at §2 here.

**What this is.** A **component-screening sprint**, not a publishable experiment. Two seeds and two
synthetic families are adequate for a build decision; they are **not** adequate for a scientific
claim, and confirmatory replication happens later on whichever contrast survives integration (§14).

**What this owns:** S0–S5 protocols · hypotheses and experimental arms · schedules and compute
budgets · actual results · deviations and amendments · limitations · the evidence behind each gate
decision · pre-registration records · the S5 decision audit.

**What it does not own:** component definitions and interfaces · tier membership · runtime
arbitration · build order and slack policy · production retention rules · predeclared production
tolerances · fallback behaviour. All of those live in the specification.

**Governance is one-way:**

```
experiments produce evidence  →  decision register evaluates it
                              →  implementation spec is amended  →  code implements the amendment
```

**Section references** in the form **SPEC §9** point to
[the implementation specification](arc-agi-3-implementation-spec.md); **A §16** to
[Track A](arc-agi-3-ship-jepa-x-architecture.md). Bare `§n` is this document.

**Budget.** 40–50 h/week solo. Focused working days (~5/week).



## 2. Which binding decision each experiment informs

**The component inventory that stood here is withdrawn.** The binding tier table is
[SPEC §3](arc-agi-3-implementation-spec.md), and the binding build order is SPEC §12. Nothing in this
document defines a component, a tier, or an interface.

### 2.1 Experiment → decision map

The inverse of SPEC §1.1's table. Each sprint names exactly which binding decision it feeds, and what
the specification consumes from it.

| Sprint | Informs (binding) | Output the spec consumes | Status |
|---|---|---|---|
| **S0** | execution path only | that a submission can pass validation + hidden rerun | **complete** — public score 0.06 |
| **S1** | SPEC §4.1 reset posture · D0 §10.1 latency inputs · SPEC §2 per-action budget | reset **Case**, `r`, `c_reset` · measured latency table · failure-frequency ranking · the variance floor | **complete, DEGRADED** on payload |
| **S2** | nothing directly — builds the instruments | F1 and F3 generators, matching measured ARC conventions | next |
| **S3** | **R0 / SPEC §11** predictive objective | latent vs reconstructive vs exact-delta, and whether rollout pays | not started |
| **S4** | **SPEC §11.2 rung gates** — belief-model production value | retain or drop rungs, at what latency cost | not started |
| **S5** | **SPEC §12.2 slack policy** | build / defer / drop per component | not started |
| *(G0-R, G0-A)* | **SPEC §9 gate G0** | integrate recognizer and/or ranker, or defer | spec-side; W7 |

**S2 and S3 do not inform the goal decision.** That is gate G0's business (SPEC §9), and §3.2 below
records why the gap exists and how the specification closed it.

### 2.2 Tier snapshot — which ordering was in force when each measurement was designed

Measurements are designed against an architecture, so a measurement outlives the ordering that
motivated it and must be read against the ordering that was current at the time.

| In force | Ordering | Measurements designed under it |
|---|---|---|
| **2026-07-27 → 07-28** *(withdrawn)* | Tier 1 submittable agent → **Tier 2 goal induction** → Tier 3 belief model → Tier 4 gated extensions. Goal induction ranked second on the strength of S1-d's 75%. | S1-d labelling and frequency ranking · the §3.2 coverage-gap analysis · §4's float claims |
| **2026-07-28 → present** *(binding, SPEC §3)* | Tier 1 substrate → **Tier 2 cheap delegation layer** (evaluator + invocation gate) → Tier 3 belief-model rungs, verified programs, **G0 experiments** → Tier 4 goal-model production integration, rung 6, hierarchy | everything from S2 onward |

**The reordering looked like a disagreement on 07-27; the 07-28 cross-run result largely settles it in
the specification's favour.** The withdrawn ordering promoted goal induction on a single-run
`primary_share` of 75%. Re-measured across three runs of one byte-identical configuration, that share
fell **75% → 53% → 27%** (§3.1). Whether that is real run-to-run variation or a rating artifact is
**not yet established** — the only re-rate available is partial (17 of 25), not blind, and covers
primary labels only; it is consistent with real variation and cannot demonstrate it. Either way the
conclusion for the ordering is the same: a build order pinned to a statistic this unstable is the
failure mode, whereas a **gate** with predeclared margins and a non-inferiority floor — what SPEC §9
makes G0 — is the right instrument. The blind re-rate decides which explanation holds, not whether the
ordering was sound.

What still stands from the withdrawn ordering: `goal_unknown` is the **top pooled category in all three
runs** (76% / 56% / 44%), its `episode_share` is flat at 76–92%, and nothing else is close. So goal
inference remains the largest single lever; what the evidence no longer supports is *scheduling* it
ahead of everything else on the strength of one number. Sections §3.2 and §3.3 below were written under
the withdrawn ordering and are annotated where that matters.


## 3. What S1 measured, and what it ranks

### 3.1 The failure-frequency ranking

25 reference episodes (Kaggle, Qwen3.6-27B-FP8, 7920 s budget), all labelled against the pre-registered
taxonomy. Full numbers and limits: [`notes/s1d-failure-frequencies.md`](../notes/s1d-failure-frequencies.md).
**Rater was an LLM, not a human** (erratum S1-E10) — read that before using these.

`primary_share`, one label per episode, the one judged causally earliest. **This is what ranks Tier 2
above Tier 3.**

| category | L2+ (n=12) | L1 (n=13) | pooled (n=25) |
|---|---:|---:|---:|
| **`goal_unknown`** | **75.0%** | **76.9%** | **76.0%** |
| `action_semantics_unknown` | 8.3% | 15.4% | 12.0% |
| `latency_or_budget` | 8.3% | 7.7% | 8.0% |
| `progress_signal_misinterpretation` | 8.3% | — | 4.0% |

**⚠ Re-measured 2026-07-28 across three runs, and the margin did not hold.** The corpus is now 75
episodes — 25 each from v2, v3, v4 of one byte-identical configuration, all labelled.
`goal_unknown`'s L2+ share fell **75% → 53% → 27%**, and in v4 `action_semantics_unknown` (33%) overtook
it. Only **5 of 16** `(game, level)` triples agree on a primary label across all three runs; three split
three ways, including v2's two headline counter-examples `g50t` and `sp80`.

Rater drift was suspected and **tested**: 17 of v2's 25 episodes were re-rated on the same scripted
worksheet as v3/v4, and **16 of 17 primary labels reproduced (94%)**. The primary-assignment rule did not
drift, so **the decline reads as genuine run-to-run variation** — three runs of one configuration do not
agree about how the agent fails. A narrower convention change is real but harmless to the ranking
(`latency_or_budget` as a *secondary* label moved 48% → 100%, and secondaries do not enter
`primary_share`). The re-rate was not blind and 8 episodes remain outstanding; full analysis in
[`notes/s1d-cross-run-stability.md`](../notes/s1d-cross-run-stability.md).

What survives: `goal_unknown` is the top pooled category in all three runs (76% / 56% / 44%) at roughly
twice the runner-up, and its *episode_share* is flat at 76–92% — it is detected consistently; what moved
is how often it is designated primary. **Tier 2 stays ahead of Tier 3.** What does not survive: the
67-point margin, and with it the claim that the ranking is robust without a blind re-rate.
`action_semantics_unknown` at 24–33% in the later runs is a far stronger second than v2's 8% — and it is
a **Tier 3 rung-2** capability, so the gap between the tiers is narrower than the first pass implied.

### 3.2 The coverage gap — **CLOSED 2026-07-28 by SPEC §9**

**The problem, as identified 2026-07-27:** the dominant measured failure had no experiment anywhere in
the S2 → S3 → S4 chain.

| | screened by | measures |
|---|---|---|
| `goal_unknown` — 75% / 53% / 27% primary L2+ across runs | *nothing, at the time* | — |
| `action_semantics_unknown` — 8% / 24% / 33% | S2 F1 → S3 | objective A/B/C on history-required aliasing |
| `hidden_state_aliasing_or_memory` — 0% primary, 17% episode | S2 F1 → S3 | as above |
| (no observed instance) | S2 F3 → S3 | sparse delayed causal memory |

F1 targets a category that is 0% primary. F3 targets a mechanism that **did not occur in the corpus at
all** — a hypothesis about where latent objectives fail, not an observed failure. That is legitimate:
**F1 and F3 are instruments for screening objectives, not a ranking of what to build.** What was not
legitimate was leaving it implicit, because S2 → S3 as specified screens only the transition-prediction
objective and **could return a clean, well-controlled answer about a component that is not the
bottleneck.**

**How it was closed.** Not by any of the three options recorded here on 07-27 — accept the gap, add an
F5 family to S2, or add a goal readout to S4. The implementation specification instead created a
dedicated gate:

- **G0-R** — post-outcome recognition: terminal / progress-bearing classification, prerequisite and
  partial-progress grading, ledger goal-hypothesis pruning. Runs independently of any transition model,
  in parallel with R0.
- **G0-A** — pre-action utility, with the **outcome source declared** (exact branch · cheap-evaluator
  prediction · belief-model prediction · verified program), credited per source against that source's
  frozen progress-event-head ranking.
- **Fork G-F** (SPEC §9.6) adds **F4 ordered-event-program** and **F5 cumulative-counter** families —
  essentially option (b), but two families rather than one and conditioned on ≥ 5 build-days of slack at
  Aug 22, falling to "family transfer declared untestable and reported as such" otherwise.
- A decision table (SPEC §9.7) covering all four outcomes, with the fallback being a heuristic plus
  executive structural goal system.

This is stronger than any option on the 07-27 table, and the cross-run instability in §3.1 is why: a
gate with predeclared margins tolerates an unstable measurement in a way a build-order promotion does
not. **S2 and S3 still do not speak to goal inference, and under the current specification they are not
required to.**

### 3.3 The tension this creates, recorded rather than smoothed

The reference agent is **good at mechanics and bad at objectives**, and the gap is not close. It derived
correct non-obvious transition rules from a handful of observations across many games, using no learned
world model at all. Then it had nothing to aim them at: one episode reached the state its own goal model
called the solution and the level did not complete; another enumerated all six legal block positions,
correctly concluded the goal was elsewhere, and could generate no replacement hypothesis.

Track A's parameter budget is dominated by transition prediction. Goal inference is a **1.0M-parameter
head — 5% of the budget against 75–92% of the episodes.**

Three honest readings, recorded 2026-07-27:

1. **The build order follows the measurement** — goal work before transition prediction.
   **⚠ Weakened 2026-07-28.** This reading rested on the single-run 75%, which fell to 27% by v4
   (§3.1). It survives only in the weaker form the pooled numbers support: goal inference is the
   largest single lever, not that it should be scheduled first.
2. **A latent world model is instrumental to goal inference** — you cannot hypothesise a win condition
   over a representation you do not have. Defensible, but it is an argument, not a measurement, and it is
   the kind of argument that survives any result.
3. **The reference's bottleneck is not ours** — it has a 27B LLM doing perception; a 20M model may fail
   elsewhere. Also defensible, and it implies this corpus ranks *the reference's* build order, not ours.

**How it was resolved:** by none of the three. SPEC §9 makes goal inference a **gate** rather than a
position in the build order, which is the response that does not depend on which reading is right. The
1.0M/20M budget imbalance recorded above is a Track A fact and remains unaddressed — the specification
defers belief-model internals to Track A (SPEC §11), so nothing has yet re-argued that split.

What is not defensible is proceeding as though the measurement came out the other way.

### 3.4 The variance floor — a constraint on every later sprint

Two identical 25-game reference runs disagreed on the cleared-level count in **9 of 25 games (36%)**;
mean score moved 2.19 → 1.14; exactly one game reproduced identically
([`notes/s1-reference-variance.md`](../notes/s1-reference-variance.md)). The environment is deterministic
(R1); the *agent* is not, by published design — temperature 0.6, top-p 0.95, no seed.

**Consequence, binding on S3 and S4: per-episode outcome comparisons from single runs are
uninterpretable.** Two configurations differing on 37% of games are indistinguishable from one
configuration differing from a rerun of itself. Prefer within-run rate statistics, which average over
tens of generations; where a per-episode comparison is unavoidable, **paired replicates are mandatory and
must be budgeted before the sprint starts, not discovered during it.**

---

## 4. Schedule and float

**~18.5 focused days ≈ 3.7 weeks. Hard stop Aug 22.** Leaves **~8.4 weeks** to the Oct 18 feature freeze.

| | Budgeted | Actual | State |
|---|---:|---:|---|
| S0 — starter submission, day one | 0.5 | 0.5 | **complete** Jul 25, public score 0.06 |
| S1 — baseline reproduction, instrumentation, submission | 6 | **2 + re-rate** | **in progress** — measurement done Jul 26–27 (DEGRADED on payload); reopened Jul 27, gate not yet applied |
| S2 — minimal F1 + F3 generators with three ceilings | 3.5 | — | next |
| S3 — objective screening, 2 paired seeds | 5 | — | |
| S4 — ARC advisor test | 2.5 | — | |
| S5 — decision audit | 1 | — | |
| **Total** | **18.5** | **2.5 spent** | |

**~4 focused days of float now exist where the plan assumed zero.** S1 came in at 2 days against 6,
largely because accepting the reference's harness worked as intended and because the Kaggle run replaced
a planned local breadth run that would have produced worse data
([`notes/s1-closeout.md`](../notes/s1-closeout.md)).

**Claims on the float, in order:**

1. **Paired replicates for S3 and S4** (§3.4). The strongest claim. An unreplicated S4 produces a
   retention decision indistinguishable from a coin flip — worse than no measurement, because it would be
   reported as one.
2. **An entrant-authored payload** (~1 d), which converts the DEGRADED branch to PASS and restores S5's
   B axis (§6).
3. **Closing the coverage gap** (§3.2), at (b) ~1 d or (c) ~0.25 d.

Do not let the float be absorbed silently. If it is spent on overrun rather than on 1–3, that is a
descope of the decision quality this sprint exists to produce, and it should be recorded as one.

**Verify before relying on any date:** Nov 2 final submission and Nov 8 paper deadline are on the public
page; the Oct 26 entry/team-merge date comes from project notes.

---

## 5. S0 — Starter submission, day one · **COMPLETE**

**0.5 days.** Submit the untouched official starter. Kaggle runs both a validation pass and a hidden
rerun, and a substantial fraction of failed submissions surface no traceable notebook error. Proving the
external execution path before building anything is the cheapest risk reduction in the project.

**Result, 2026-07-25:** validation PASS, hidden rerun PASS (`Succeeded`), public score **0.06**,
wall-clock to result ~4h42m–5h41m. Ledger row in [`submissions/ledger.md`](../submissions/ledger.md).

**Decides:** Tier 0, execution path only. It measures Kaggle's Random Agent, not anything of ours.

---

## 6. S1 — Baseline reproduction and reference point · **IN PROGRESS (measurement done, DEGRADED)**

**6 days budgeted, 2 spent.** Reproduce one strong public local-model agent; accept its harness rather
than building your own — that is where most of the saving came from.

**Decides:** all of Tier 0 except the payload; the **order** of Tiers 1–4, via failure frequency (§3.1).

### What it answered

| Question | Result |
|---|---|
| Hardware fit — VRAM | **PASS one model resident, FAIL two** |
| Hardware fit — throughput | **NOT INTERPRETABLE** from this run |
| Per-action latency | **PASS** — 139.39 s against 225.00 s (S1-E12 denominator) |
| Per-decision latency | **PASS** — 361.33 s against 675.00 s; FAIL at 258.51 s under the old denominator |
| Wall-clock margin | **FAIL — there is no margin.** Median action span 2518 s of a 2700 s budget (93%) |
| Legal-action reliability | **PASS** — 0.9831 (349/355) against 0.95 |
| Reproduction fidelity | **PASS** |
| Reset and action accounting | **`accumulates`**, `r` = 2.0357, `c_reset` = 1 — RESET is itself scored |
| Packaging / offline bundling | **SCOPE CHANGED** — the reproduction is no longer a candidate payload |

**The reset experiment gated nothing and configured everything.** It selected the **surgical
information-per-action controller** over an aggressive identify-then-execute one: every probe costs
score. That decision now propagates into Tier 2's probe controller.

### Why the branch is DEGRADED

The reference is unlicensed third-party code, so it cannot be submitted and the repository can never be
made public ([`PUBLISHING.md`](../PUBLISHING.md)). **No leaderboard reference exists.** The consequences,
recorded in the manifest and repeated here because later sprints depend on them:

- **S5's B axis has no score to read.**
- **S4's closed-loop run has no leaderboard baseline**, and instead uses a **local paired control** —
  same games, same budget, same model, advisor on versus off. On internal validity this is *better* than
  a leaderboard delta against a differently-configured public run. What it cannot do is establish
  hidden-set utility, so any retention decision must be stated at that scope.
- **Recoverable at any point** by packaging the official starter with our own harness (licence-clear
  under bucket 1). Costs one day's submission quota; see §4's float claim 2.

### Still open — **S1 is reopened until these close**

The blind re-rate. S1-E7 (`sample_size: 30` unachievable from 25 episodes) was resolved by **S1-E11** —
an enlarged corpus of up to 75 episodes, making the pre-registered sample achievable without amending
it — and **S1-E14** then changed the mechanism from three passes inside one kernel to **three separate
single-pass runs** of a byte-identical configuration. `sample_size: 30` is unchanged throughout, and the
corpus reached 75 episodes on 2026-07-28, putting the sample at 40% of it. All 75 are labelled.

**§3.1's re-measurement changed what the re-rate must do.** It was scoped to measure rater agreement; it
must now also **re-rate the v2 episodes on the scripted worksheet** (`agent/harness/s1d_worksheet.py`),
because those labels came from a different, unreproducible evidence slice under a demonstrably different
convention. Without that the three runs are not comparable and no cross-run claim is available at all.
`agreement_floor: 0.40` has still not been applied to anything, and the 67-point margin that made this a
limitation rather than a blocker is withdrawn.

**Reopened 2026-07-27.** §4 previously marked S1 complete while this gate was unapplied and
`failure_frequency_ranking`, `build_order` and `viability_verdict` were still null in the manifest — a
stage cannot be closed on a pre-registered gate it never ran. S1 closes when:

1. **the third single-pass run lands** and the corpus is rebuilt with `s1d_build_corpus.py --replicates`.
   Runs v2 and v3 are in hand and pool to **50 evidence-bearing episodes** — already above
   `sample_size: 30`, so the re-rate is not blocked on the third run; v4 is needed only to reach the 75
   episodes that make 30 a 40% sample rather than a 60% one. Pooling is admissible because v2 and v3
   carry byte-identical configuration signatures, which the builder now verifies mechanically;
2. the re-rate is drawn and scored as an **independent re-rate, same model** (S1-E10 — *not* delayed
   test-retest, and no cooling period: an LLM rater has no memory to decay);
3. categories below `agreement_floor: 0.40` are excluded from the ranking, and the manifest's three null
   roll-up fields are filled from what survives.

The measurement work of S1 is done and is not repeated by this. What reopens is the gate, and the cost
falls on the float §4 banks — which is what the float is for.

---

## 7. S2 — Two minimal causal families

**3.5 days.** Small, exhaustively testable, ARC-compatible conventions so S4 needs no re-engineering.

**Decides:** no component directly. S2 **builds the instruments** that S3 uses to decide Tier 3's
objective. Priced accordingly: if S2 overruns, it is taking days from the sprint's only decision-bearing
blocks.

**F1 — history-required aliasing.** Visually identical observations require different actions because of
a hidden switch, counter, or phase.

**F3 — sparse delayed causal memory.** A one-cell or one-object change with no short-term effect that
determines a later transition. This is the mechanism the feasibility analysis identifies as the central
risk for reconstruction-free prediction: the objective has almost no gradient pressure to preserve a bit
whose consequence lies outside the training horizon, while an exact target retains it structurally. F1
alone sits in the short-horizon regime where a latent predictor looks good, so **without F3 a positive
result is biased.**

*(F2 hypothesis-discrimination and F4 irreversible-diagnostic-choice are cut. They test
capability-as-science more than build-relevant viability.)*

### Measured conventions the generators must match

**Measured 2026-07-26 across all 25 public games**, not taken from documentation. Reproducible via
`agent/harness/measure_arc_conventions.py` → `logs/s2_arc_conventions.json`. Full detail in
[`notes/s1-closeout.md`](../notes/s1-closeout.md).

| Convention | Measured |
|---|---|
| Grid shape | **64×64 always** at reset, all 25 games — so no padding convention is needed |
| Cell values | **0–15, all 16 occur** |
| Frames per observation | **1–N, and N varies *within* an episode** — see below |
| Levels per game | 6–10 (mode 6) |
| Level-1 human baselines | 6–78; across all levels up to 578 |
| Action availability | **per-game** (measured at reset: ACTION6 in 19/25). ⚠ **per-*state* variation is permitted by the interface but NOT evidenced** — hold it fixed per game until a wider probe says otherwise |

**🔴 Observations are frame sequences of varying length.** `FrameDataRaw.frame` is a *list* of 64×64
grids. Stepping one game produced frame counts `1,1,1,1,1,1,1,6,6`. Three consequences, to be honoured at
design time rather than patched later:

1. **The F1/F3 generators must emit variable-length frame sequences**, or they produce a distribution the
   real environment never generates and S4's advisor test is measured on a mismatch.
2. **Any encoder must consume 1–N frames per step.** A model assuming one grid silently discards up to
   five-sixths of the observation at exactly the steps where something interesting happened — invisible in
   aggregate loss.
3. **This interacts directly with F1.** If an observation is itself a short sequence, part of the
   "history" the aliasing test is about lives *inside a single observation*. F1's notion of a timestep
   must be defined against this or its ceilings measure something else.

### F1 needs three ceilings, not one

Oracle-hidden-state beating observation-only shows hidden information *matters*. It does not show that
history contains enough to *recover* it. Run:

1. observation-only;
2. **complete observable history with an oracle decoder**;
3. oracle hidden state.

Required pattern: observation-only < history-oracle ≈ hidden-state-oracle. If the history oracle stays far
below the hidden-state oracle, the task is not learnably history-resolvable and model failure is expected —
without this ceiling that would be misread as a model result.

### Generator interface

Legal action set · exact successor for every legal action · terminal/progress predicate · **immediate action
value or distance-to-goal** (the ranking criterion — without it, ranking regret has no ordering) ·
hidden mechanic state and parameters · which state variables are causally relevant · recoloured and
relaid-out variants · **variable-length frame sequences per observation**.

**The value criterion is evaluation-only.** If it trains a value head, S3 becomes supervised action ranking
rather than an objective comparison.

---

## 8. S3 — Objective screening

**5 days. Two paired seeds** — adequate for a build decision, explicitly not for a claim. Common
grid/patch encoder. Hybrid entity/region architecture deferred.

**Decides:** *which* Tier 3 objective, not whether Tier 3 is retained. That is S4.

| Objective | Target |
|---|---|
| A | reconstruction-free latent (JEPA) |
| B | matched reconstructive next-state predictor |
| C | matched exact structured delta |

**Exact-delta is mandatory.** The decision is not "JEPA versus reconstruction" but "JEPA versus the
strongest compact alternative." Without C, a mediocre decoder in B yields a false JEPA-positive.

### Rollout is an ablation within each objective, not a separate arm

For each of A, B, C: **with rollout** versus **without rollout** (candidate ranking from the representation
alone). A standalone "no-dynamics arm" has no specified training objective, so any difference could come
from an unspecified encoder rather than from dynamics. Six configurations, three encoders.

**Training budget is measured, not assumed:** a 21.2M-parameter model trains at 7.22 steps/s in 7.54 GB
locally, so twelve S3 runs at 100k steps cost ~46.2 h against a 120 h budget. Capacity is not the binding
constraint at this scale.

### Matched information

**Every configuration receives identical observation history, actions, metadata, retrieval context,
training data, and data ordering. Only the predictive target differs.** Otherwise the comparison varies
target *and* information and is uninterpretable. The cheap controls (observation-only variant of A;
affordance/no-op classifier) also get matched history, or "JEPA beats affordance" merely restates "history
beats no history."

### Matched ranking interface

All configurations share the same candidate action set, the same downstream evaluator class and fitting
budget, and an **oracle-successor ranking ceiling**. Plus one cheap guard: **if the without-rollout
configurations approach the with-rollout ones, the evaluator is doing the work** and no dynamics conclusion
is available. Interface effects can swamp this contrast — published results show terminal-cost changes
alone moving a latent planner from 7% to 97% success.

### Degeneracy monitoring — symmetric

Report per-dimension variance, effective rank, and control-variable probe accuracy **for every learned
representation, not only JEPA.** Reconstructive and exact-delta representations cannot collapse totally but
can still be partially degenerate, exploit shortcuts, discard hidden variables, or lean on decoder
structure.

Rescue remains JEPA-specific and pre-registered: trigger on variance below `T_v` or effective rank below
`T_r`; probe accuracy is diagnostic only and never an abort trigger, since aborting on it means aborting on
the measured outcome; one fixed-coefficient variance/covariance recipe, untuned; **at most one remedial
rerun**; **collapse frequency reported as a result.**

### The screening questions

1. Does history conditioning help at all? *(A vs. observation-only A)*
2. Does rollout add anything over the same representation without it?
3. Does A beat B and C on counterfactual ranking regret and identification?
4. **Does A retain the sparse delayed causal bit on F3?**
5. What is A's inference cost per candidate against S1's measured per-action budget — noting that S1's
   **wall-clock margin verdict was FAIL**, so this is a live constraint, not a formality.

---

## 9. S4 — ARC advisor test

**2.5 days.** The only measurement that can retain or kill JEPA on operational grounds.

**Decides:** whether **Tier 3 is retained at all**, and per §3.3 reading 3, whether S1-d's ranking is ours
or only the reference's.

**Primary:** train each objective on the same ARC replay training games, evaluate on **held-out games**
with identical frozen advisor interfaces. Readouts: candidate pruning quality · no-op avoidance ·
changed-region prediction · representation stability across games · latency per candidate · **goal
hypothesis quality, if §3.2(c) is adopted.**

**Plus a small closed-loop run** on two or three development games with the model as advisor only. Offline
probes cannot establish control utility, and control utility is the retention criterion.

**Two constraints inherited from S1, both binding:**

- **The control is local and paired**, not a leaderboard delta — there is no leaderboard reference (§6).
  Advisor on versus off, same games, same budget, same model. Better internal validity; **no claim to
  hidden-set utility.**
- **Replicates are mandatory** (§3.4). At a 36% run-to-run noise floor, an unreplicated advisor-on/off
  comparison cannot resolve any effect smaller than the noise. Budget the replicates before S4 starts.

**Do not treat the human's next action as ground-truth action quality** — that is imitation, not planning
utility. Stratify any action ranking by the replay action's observed outcome (terminal ·
persistent-progress · informative change · reversible change · no-op).

**Standing caveat:** public games are materially easier than hidden ones and public results are not
evidence of hidden generalization — 13.33% public against 7.78% semi-private for the frontier reference.

---

## 10. S5 — Decision audit

**1 day. Stop implementing.** Record four axes:

| Axis | Content | State entering S5 |
|---|---|---|
| **B — baseline readiness** | accepted submission · hidden score · latency · reliability · gap to competitive | **impaired** — no score unless §4 float claim 2 is spent |
| **M — mechanism evidence** | history effect · rollout effect · objective ranking · F3 retention · collapse frequency | from S3 |
| **U — advisor utility** | held-out ARC readouts · closed-loop advisor delta · latency cost | from S4, local scope only |
| **C — feasibility** | remaining calendar · integration complexity · remaining compute | ~46.2 h of 120 h used by S3 |

Cases that require all four and cannot be read from a 2×2: strong synthetic mechanism with weak ARC
utility · strong baseline with unresolvable licensing · weak public score with nonzero hidden score · JEPA
equivalent to reconstruction but materially faster · JEPA strong only with exact auxiliaries, meaning the
auxiliaries carry the result.

**S5's output is a revised §2** — the component inventory with each row marked build / defer / drop, and
the order fixed for the ~8.4 weeks that follow.

---

## 11. The paper as a continuous by-product

A prize-quality paper cannot begin after the score route is declared capped. Deferring it to September
forecloses it. So from day one, at low marginal cost:

- hypotheses and related work written now, not later;
- methods sections written alongside implementation, while the details are fresh;
- figures generated by script from logged results, never hand-assembled;
- **every submission linked to the ablation it represents** — this is what turns routine iteration into a
  component ablation table for free;
- negative results logged immediately, with the configuration that produced them;
- the Paper Prize submission requirement (§6) satisfied by keeping one method-bearing submission path warm,
  not by building it in the last fortnight.

This does not raise Paper-Prize odds much on its own. It preserves the *option*, which deferral destroys.

---

## 12. Pre-register before starting

Into `gate_manifest.yaml`, numbers filled, before the corresponding step. **S1 is frozen with results;
S2–S5 are still `NOT_STARTED` and must be filled before their block begins.**

- **S2:** the value/distance-to-goal criterion per family · the three-ceiling margins validating F1 · F3's
  delay length and bit sparsity · **the frame-sequence length distribution the generators emit** (§7).
- **S3:** named primary metric and threshold for each of the five screening questions · `T_v`, `T_r` · the
  rescue recipe's fixed coefficients · the evaluator-doing-the-work criterion · **the parameter count**,
  which is currently a guess and is not pre-registered.
- **S4:** the retention threshold — what advisor improvement, at what latency cost, keeps JEPA in the
  agent · **the replicate count** (§3.4) · the goal-hypothesis readout if §3.2(c) is adopted.
- **S5:** the B/M/U/C pattern mapping to each branch in §13.

---

## 13. After Aug 22 — freeze and build

**~8.4 weeks to feature freeze.** Freeze the competition architecture immediately and build §2's inventory
in tier order, which is now grounded in measurement rather than in a forward reference:

**Tier 1 → Tier 2 → Tier 3 (if S4 retains it) → Tier 4 (each gated).**

Reserve the final ~3 weeks for tuning rather than construction.

**Submission quota is 1 per day, 2 final submissions** — not 5/day, as an earlier version of this section
stated (source: Kaggle competition rules, checked 2026-07-25). This changes the iteration argument rather
than merely a number. Roughly 59 submissions exist between Aug 22 and the Oct 18 freeze, a rejected one
cannot be retried until the next calendar day, and there is no room for a submit-and-see loop. Iteration
still produces the score, but each submission must be *chosen*, which makes the §11 rule — every submission
linked to the ablation it represents — the mechanism that keeps a scarce resource informative rather than a
bookkeeping nicety.

**JEPA retention gate.** Tier 3 stays in the agent only if S4's advisor test shows improvement at
acceptable latency, re-measured after integration. Otherwise the encoder is retained for retrieval only,
or dropped — and §2's Tier 1 + Tier 2 is a complete, submittable agent without it.

---

## 14. Confirmatory science, later

Whatever contrast survives integration gets proper treatment when the competition work is done or the score
route is capped: three-plus seeds, more task families, the entity-factorization factor, matched interfaces
throughout, ARC-trained held-out evaluation, and the full control set from
[`arc-agi-3-jepa-feasibility-analysis.md`](arc-agi-3-jepa-feasibility-analysis.md).

Screening evidence at two seeds and two families supports a build decision and nothing more. Any paper
rests on the confirmatory pass plus the ablation table accumulated from §11 — not on this sprint.

---

## 15. Revision log

This document is the sprint's authority, so changes to it are recorded rather than made silently. It is
**not** pre-registration — that is `gate_manifest.yaml`, which is append-only. Editing here is permitted;
editing without a log entry is not.

| Date | Change |
|---|---|
| 2026-07-25 | Written; final revision under the score-primary utility ordering |
| 2026-07-27 | **Restructured component-first.** New §2 (component inventory, five tiers) and §3 (what S1 measured). Sprint sections renumbered §5–§10 and each now states which inventory rows it decides. S0 and S1 marked complete with actuals and verdicts. New: §3.2 coverage gap and its open decision · §3.4 variance floor as a constraint on S3/S4 · §4 float and its claims · §6 DEGRADED branch consequences · §7 measured ARC conventions including the variable-length frame sequence requirement · §10 state-entering-S5 column · this log. Former §11's forward reference to "S1's failure-frequency ranking" replaced by the measured ranking itself |

---

## 16. Appendix — evaluation apparatus (definition site)

These five terms are **evaluation apparatus**: they define how a measurement is read, not what the
agent contains, so they belong with the evidence rather than with the specification. Their original
definition sites were the two documents frozen 2026-07-23, archived 2026-07-28; they passed briefly
through `agent-architecture.md` §10, archived the same day. **This appendix is the definition site.**
Only the *procedural boundary suite* also appears in the specification, as Tier 1's "procedural suite
core (F1, F3)".

**demotion ladder** *(also Track A §21, reliability governor)* — the fallback modes the agent drops
through when it stops being trustworthy: full sequential hierarchical agent → sequential flat model →
exact archive and graph agent → conservative frontier exploration. Triggered by rollout disagreement
beyond tolerance · exact-delta error rising sharply · reachability calibration failure · no validated
subgoal · high rule-shift probability · time reserve below the required margin.

**common-candidate audit** *(= the same-candidate oracle audit)* — identical candidate sequences are
rolled through every model and executed in the deterministic simulator, giving ground-truth candidate
quality **with no learned judge.** Four stages, each isolating one failure source:

1. **candidate quality** — best true outcome in the set → sampler or horizon limits;
2. **rollout fidelity** — predicted versus exact outcomes → dynamics;
3. **terminal evaluation conditional on exact endpoints** — exact endpoints fed through each
   condition's frozen encoder and head, removing rollout error → interface and geometry;
4. **closed-loop executed result** → replanning, compounding error, execution.

Two candidate pools are required: a fixed-size **exogenous** pool generated independently of all
conditions, which carries the primary audit, and a fixed-size **union** pool sampled evenly from all
model proposal sources, which is secondary with its endogeneity named. This is what makes §3.4's
recall metric interpretable — same candidates for every arm, so a difference is the ranker's.

**attribution ladder** — the four rungs within stage 3 above, separating "the model is wrong" from
"the interface is wrong": (i) simulator-state oracle ranking → (ii) a shared frozen external
featurizer of representation-independent grid features (changed-cell counts, object statistics, event
flags) → (iii) condition encoder plus a linear or bilinear comparator → (iv) condition encoder plus
full head. The gaps are the reading: (i)→(ii) feature sufficiency · (ii)→(iii) representation
accessibility · (iii)→(iv) nonlinear interface value. Works for *any* pair of arms, which is why
[`architecture-alternatives.md` §11](arc-agi-3-architecture-alternatives.md) calls this apparatus the
most transferable scientific asset in the project.

**diagnostic contract** — the frozen baselines every condition is read against: copy-last-observation
persistence · random candidate ranking · exact-simulator planning under the same candidate budget ·
archive or exact-transition-table baseline where applicable. Reported per condition: whole-frame exact
match · changed-cell precision, recall, F1 · irreversible-event and level-transition prediction
accuracy · multi-step exact-rollout survival · counterfactual action discrimination. If the token loss
uses change weighting, the weighting rule is frozen from outer-train data only. **Unchanged-cell
accuracy never substitutes for dynamics knowledge.**

**procedural boundary suite** — synthetic generators producing many independent environments while
varying one factor at a time: visible versus partially observable state · fixed versus
environment-specific action semantics · smooth versus exact irreversible transitions · broad versus
one-cell-critical state relevance · direct versus non-greedy prerequisite goals · unimodal versus
genuinely aliased successors · short versus compositional horizons · familiar versus held-out
combinations of mechanics. Committed as **eight paired one-factor-at-a-time micro-environments with
easy and stress arms — not a 2⁸ factorial.** **S2's F1 and F3 are the two families of this suite that
survive the screening sprint**, and SPEC §3 carries them as Tier 1 "procedural suite
core (F1, F3)".
