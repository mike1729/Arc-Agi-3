# Screening Experiments and Results — S0 through S5

> **This document does not define the deployed architecture.** It supplies evidence for the gates and
> decisions in [`arc-agi-3-implementation-spec.md`](arc-agi-3-implementation-spec.md). Where the two
> conflict, **the implementation specification governs** until explicitly amended. A result recorded
> here becomes binding only through a dated amendment to that document — never automatically.

**This owns:** what each sprint decides · protocols and arms · results · the constraints a result
places on later sprints · what still needs pre-registering · the S5 audit.
**It does not own:** component definitions · tier membership · runtime arbitration · build order ·
retention rules · production tolerances. Those are the specification's.
**It is not the calendar.** Day-level dates live in
[`arc-agi-3-execution-schedule.md`](arc-agi-3-execution-schedule.md); §2 here carries only the budget
and what may claim the float.
**It is not the evidence archive.** Full numbers live in [`../notes/`](../notes/); this document is
their index and their interpretation.

**References:** **SPEC §n** → the implementation specification · **A §n** →
[Track A](arc-agi-3-ship-jepa-x-architecture.md) · bare **§n** → this document.

---

## 1. Status board

**Sprint: 18.5 focused days, hard stop Aug 22.** Budget 40–50 h/week solo, ~5 focused days/week.

| Sprint | Days | State | Decides (binding) | Evidence |
|---|---:|---|---|---|
| **S0** starter submission | 0.5 / 0.5 | ✅ **complete** — public score 0.06 | execution path only | [`ledger`](../submissions/ledger.md) |
| **S1** baseline reproduction | 6 / **2** | ⚠️ **measurement done, DEGRADED payload, gate reopened** | SPEC §4.1 reset posture · D0 latency inputs · SPEC §2 per-action budget | §6, [`s1-closeout`](../notes/s1-closeout.md) |
| **S2** F1 + F3 generators | 3.5 / — | ▶️ **next** | nothing directly — **builds the instruments S3 needs** | §7 |
| **S3** objective screening | 5 / — | not started | **R0 / SPEC §11** — the predictive objective | §8 |
| **S4** ARC advisor test | 2.5 / — | not started | **SPEC §11.2 rung gates** — is Tier 3 retained at all | §9 |
| **S5** decision audit | 1 / — | not started | **SPEC §12.2 slack policy** — build / defer / drop | §10 |
| *(G0-R, G0-A)* | — | spec-side, W7 | **SPEC §9 gate G0** | SPEC §9 |

**Three things are open right now and block their own sprints:**

1. **S1's blind re-rate has not run.** `agreement_floor: 0.40` has been applied to nothing, and three
   manifest roll-up fields are still null. S1 is *reopened*, not complete — §6.
2. **`gate_manifest.yaml → s2` is `NOT_STARTED`** while S2 begins. Pre-registration must precede the
   step it governs — §11.
3. **Two pre-registrations coexist** — the manifest and SPEC §13 both predeclare numbers. Open item 1
   in [`README.md`](README.md).

---

## 2. Budget and float

| | Budgeted | Spent |
|---|---:|---:|
| S0 · S1 · S2 · S3 · S4 · S5 | 0.5 · 6 · 3.5 · 5 · 2.5 · 1 | 0.5 · 2 · — · — · — · — |
| **Total** | **18.5** | **2.5** |

**~4 focused days of float exist where the plan assumed zero.** S1 came in at 2 days against 6 —
accepting the reference's harness worked as intended, and the Kaggle run replaced a planned local
breadth run that would have produced worse data.

**Claims on the float, in priority order:**

1. **Paired replicates for S3 and S4** (§12). An unreplicated S4 produces a retention decision
   indistinguishable from a coin flip — *worse* than no measurement, because it would be reported as
   one.
2. **An entrant-authored payload** (~1 d) — converts the DEGRADED branch to PASS and restores S5's B
   axis (§6).
3. **S1's re-rate**, whose cost the float is explicitly banked for (§6).

**Do not let the float be absorbed silently.** Spending it on overrun rather than on 1–3 is a descope
of the decision quality this sprint exists to produce, and must be recorded as one.

### Training-data readiness — do we have it, how much is needed, how hard is it to get?

**Short answer:** executed transitions are abundant; *procedural diversity* and *real
counterfactuals* are not. The replay archive already covers ARC-shaped observations and factual
targets. S3 still depends on a generator that has not been built, and the hardest S4 labels ask what
a different action would have done — information an on-policy replay cannot contain at any volume.

**Measured inventory, 2026-07-28:** 340 human sessions (6.4 GB) provide **180,144 valid
transitions**, including 171,199 changes, 8,945 no-ops, 1,614 terminal transitions, 56,347 ACTION6
transitions and 516,260 grids (mean 2.86 per observation). Three reference-agent runs add **12,475
transitions**, including 1,446 no-ops and 49 terminals. Procedural F1/F3 data is unbounded in
principle but **zero exists today**: S2 builds its source. Full census and derivations:
[`screening-training-data.md`](../notes/screening-training-data.md).

Difficulty below means **data acquisition**, not model implementation: 0–2 = in hand or one
extraction pass; 3–4 = produced by already-scheduled work; 5–6 = needs a new instrument; 7–8 =
hard-budget environment interaction with uncertain yield.

| Consumer | How much is needed | What exists now | Difficulty | Verdict |
|---|---|---|---:|---|
| **S2 ceilings** | Enough disjoint instances to resolve the registered F1/F3 margins; counts are **not yet registered** | generated on demand after S2 exists | **4** | volume is elastic; instance diversity is the risk |
| **S3 A/B/C × rollout × seeds** | **51.2M transition presentations/run; 614.4M total** at 100k steps. If pre-generated, **≥2.56M distinct transitions** at ≤20 epochs and hundreds-to-low-thousands of instances/family are planning judgments, not thresholds | **0 procedural transitions** | **4** | not volume-limited after S2; throughput- and compute-limited |
| **S4 ARC retraining** | A/B/C share one game-level split and one smaller, still-unregistered step budget | **180,144** replay transitions; any 17/8 split leaves 79,329–155,842 before the balance constraint | **1** | in hand, but epoch-limited: even 10k steps present 5.12M windows |
| **Changed-region / no-op readouts** | no minimum registered | ≈**701M** cell labels on changed transitions; **8,945** replay + 1,446 agent no-op positives | **0–2** | changed-region solved; no-op adequate but partition-sensitive |
| **Progress head / G0-R source** | minimum positive count **not registered**; splits must be by game/trajectory/instance, never random transitions | **1,614** replay + 49 agent positives; an unconstrained 17/8 draw leaves 850–1,287 replay positives | **4–5** | real positives are capped; procedural positives are elastic but synthetic |
| **Candidate pruning / rung-3 ranking** | common-state action pairs with a causal ordering; no S4 training minimum registered | 23,032 replay pairs distinguish two effective coordinate actions, but only **204** involve progress | **6 via local fork; 8 via platform branches** | the real shortage; replays cannot supply unbiased rankings |
| **Demonstrated irreversible class** | verified absence of a return route within \(H_{rev}\); no minimum registered | **0**; 5,065 demonstrated-reversible positives do not create the missing class | **7** | must be searched for, not inferred from missing return evidence |
| **S4 closed-loop delta** | paired replicates; count not registered | live development games | **4** | not a training-volume problem; run-to-run variance determines power |

Three consequences govern how these numbers are read:

1. **Raw transition count is not a sufficiency argument.** The same 180k replays can solve dense
   factual heads and still provide almost no causal action-ranking evidence.
2. **S2 is a data dependency, not only an experiment.** Before it binds, register generator
   throughput, distinct and held-out instance counts, emitted frame distribution, frame cap and
   procedural progress prevalence (§11).
3. **The hard labels share one acquisition path.** Counterfactual ranking, demonstrated
   irreversibility, causal ACTION6 recall, the learned gate and exact-branch G0-A all consume either
   the branching budget or a local game fork. All 25 public game sources are on disk, but local-fork
   use still has licensing, platform-fidelity and dev/validation-leakage constraints; evaluation-only
   use on the dev partition is the lowest-risk first use.

**One known compute risk, not yet resolved.** S3's 46.2 h estimate assumes one grid per transition;
the measured corpus averages **2.86**, and honouring the frame convention uncapped puts S3 at ~132 h
against a 120 h budget. A frame cap of 8 covers 92.5% of observations at ~97 h. Register the cap on
A2 — [`screening-training-data.md` §5a](../notes/screening-training-data.md).

---

## 3. Which binding decision each experiment informs

The inverse of SPEC §1.1's table. **An experiment that maps to no row is either infrastructure or
should not be run.**

| Sprint | Output the specification consumes |
|---|---|
| **S0** | that a submission can pass validation + hidden rerun |
| **S1** | reset **posture**, `r`, `c_reset` · measured latency table · failure-frequency ranking · the variance floor |
| **S2** | **SPEC §4.9 itself** — the procedural suite is Tier 1 unconditional substrate, not a screening fixture. Consumed by §6's retention decisions, §13.1's \(\tau\) calibration, §6.4's ECE clause, §10.1's D0, §10.2's R0 and §9.4's splits, as well as S3 |
| **S3** | latent vs reconstructive vs exact-delta, and whether rollout pays |
| **S4** | retain or drop belief-model rungs, at what latency cost |
| **S5** | build / defer / drop per component |

**S2 and S3 do not speak to goal inference, and under the current specification they are not required
to.** That is gate G0's business (SPEC §9). The gap was identified 2026-07-27 and closed 2026-07-28 by
the specification creating a dedicated gate rather than by adding an experiment here; the full record
is register entry `G0-SCOPE-2026-07-28` in [`README.md`](README.md).

---

## 4. What S1 established

Four results carry forward. Everything else about S1 is in [`../notes/`](../notes/).

### 4.1 The failure-frequency ranking — real, but unstable

25 reference episodes, pre-registered taxonomy, **LLM rater not human** (erratum S1-E10).
`primary_share` = one label per episode, the one judged causally earliest.

| category | pooled v2 | v3 | v4 |
|---|---:|---:|---:|
| **`goal_unknown`** | **76%** | **56%** | **44%** |
| `action_semantics_unknown` | 12% | 24% | 33% |

**Re-measured across three runs of one byte-identical configuration, the margin did not hold.**
`goal_unknown`'s L2+ share fell **75% → 53% → 27%**; only **5 of 16** `(game, level)` triples agree on
a primary label across all three runs.

**Whether that is genuine run-to-run variation or a rating artifact is not yet established.** The only
re-rate available is partial (17 of 25), not blind, and covers primary labels only — it is *consistent
with* real variation and cannot demonstrate it.

**What survives:** `goal_unknown` is the top pooled category in all three runs at roughly twice the
runner-up, and its `episode_share` is flat at 76–92% — it is detected consistently; what moved is how
often it is designated *primary*. **What does not survive:** the 67-point margin, and any claim that
the ranking is robust without the blind re-rate. `action_semantics_unknown` at 24–33% is a far
stronger second than v2's 8%, and it is a **Tier 3 rung-2** capability — so the gap between tiers is
narrower than the first pass implied.

**Consequence for the build order:** none directly. A build order pinned to a statistic this unstable
is the failure mode; SPEC §9 makes goal inference a **gate** with predeclared margins instead. Goal
inference remains the largest single lever — that is not in dispute — but it earns integration through
G0 rather than inheriting priority. Full record: `G0-SCOPE-2026-07-28`.
Detail: [`s1d-failure-frequencies`](../notes/s1d-failure-frequencies.md),
[`s1d-cross-run-stability`](../notes/s1d-cross-run-stability.md).

### 4.2 The variance floor — binding on S3 and S4

Two identical 25-game reference runs disagreed on cleared-level count in **9 of 25 games (36%)**; mean
score moved 2.19 → 1.14; exactly one game reproduced identically. The environment is deterministic;
the *agent* is not, by published design — temperature 0.6, top-p 0.95, no seed.

**Per-episode outcome comparisons from single runs are uninterpretable.** Two configurations differing
on 37% of games are indistinguishable from one configuration differing from a rerun of itself. Prefer
within-run rate statistics; where a per-episode comparison is unavoidable, **paired replicates are
mandatory and must be budgeted before the sprint starts.**
Detail: [`s1-reference-variance`](../notes/s1-reference-variance.md).

### 4.3 The reset posture — everything scores

`accumulates`, `r` = 2.0357, `c_reset` = 1 — **RESET is itself scored.** Two things follow.

**SPEC §4.1's reset posture is settled** — `RESET-CASE-2026-07-28`, spec amended 2026-07-28. Both
cheap-reset regimes require RESET to be free or to cost runtime only; `c_reset` = 1 falsifies them.
**No online branching:** counterfactual data comes from procedural environments, replay
reconstruction and development runs only. This changed no predeclared number — SPEC §13.1's branching
budget was already written against the dev partition.

**The controller fork** went the same way: **surgical information-per-action** over an aggressive
identify-then-execute one, because every probe costs score. That propagates into Tier 2's probe
controller.

**Scope both claims carry:** offline environment files, not competition mode; and the accounting rule
itself rests on one game (tu93), single-game by design so the level weight cancels.

### 4.4 The DEGRADED branch

The reference is unlicensed third-party code: it cannot be submitted, and the repository can never be
made public ([`PUBLISHING.md`](../PUBLISHING.md)). **No leaderboard reference exists.**

- **S5's B axis has no score to read.**
- **S4's closed-loop run has no leaderboard baseline.** It uses a **local paired control** instead —
  same games, same budget, same model, advisor on versus off. Better internal validity than a
  leaderboard delta against a differently-configured public run; **no claim to hidden-set utility**,
  so any retention decision must be stated at that scope.
- **Recoverable at any point** by packaging the official starter with our own harness (licence bucket
  1). Costs one day's submission quota — §2 float claim 2.

---

## 5. S0 — Starter submission · **COMPLETE**

**0.5 days.** Submit the untouched official starter. Kaggle runs both a validation pass and a hidden
rerun, and a substantial fraction of failed submissions surface no traceable notebook error. Proving
the external execution path before building anything is the cheapest risk reduction in the project.

**Result 2026-07-25:** validation PASS · hidden rerun PASS · public score **0.06** · ~4h42m–5h41m to
result. It measures Kaggle's Random Agent, not anything of ours.

---

## 6. S1 — Baseline reproduction · **REOPENED**

**6 days budgeted, 2 spent.** Reproduce one strong public local-model agent; accept its harness rather
than build one — that is where the saving came from.

| Question | Verdict |
|---|---|
| Hardware fit — VRAM | **PASS** one model resident, **FAIL** two |
| Hardware fit — throughput | **NOT INTERPRETABLE** from this run |
| Per-action latency | **PASS** — 139.39 s against 225.00 s |
| Per-decision latency | **PASS** — 361.33 s against 675.00 s |
| **Wall-clock margin** | **FAIL — there is no margin.** Median action span 2518 s of 2700 s (93%) |
| Legal-action reliability | **PASS** — 0.9831 (349/355) against 0.95 |
| Reproduction fidelity | **PASS** |
| Reset and action accounting | `accumulates`, `r` = 2.0357, `c_reset` = 1 |
| Packaging | **SCOPE CHANGED** — the reproduction is not a candidate payload |

**S1 closes when three things happen**, not before — a stage cannot close on a pre-registered gate it
never ran:

1. the corpus is rebuilt from the three single-pass runs *(done — 75 episodes, all labelled)*;
2. the re-rate is drawn and scored as an **independent re-rate, same model** (S1-E10 — not delayed
   test-retest; an LLM rater has no memory to decay), **including re-rating v2 on the scripted
   worksheet**, since those labels came from a different, unreproducible evidence slice;
3. categories below `agreement_floor: 0.40` are excluded and the manifest's three null roll-up fields
   are filled from what survives.

The measurement work of S1 is done and is not repeated by this. What reopens is **the gate**, and the
cost falls on the float §2 banks — which is what the float is for.

---

## 7. S2 — Two minimal causal families

**3.5 days. Decides no component — it *builds* one.** S2 runs no gate, but its output is **SPEC §4.9,
Tier 1 unconditional substrate**, and the specification's interface governs what S2 must deliver.
Beyond S3, the suite is consumed by §6's retention decisions, §13.1's \(\tau\) bounds and
\(q_{hi}/q_{lo}\), §6.4's ECE clause, §10.1's D0 thresholds, §10.2's R0 criteria and §9.4's splits —
and SPEC §4.9 makes a working suite a **build step-1 precondition**, so a slip here moves D0 and the
whole build, not just S3. If S2 overruns it also takes days from the sprint's only decision-bearing
blocks.

⚠ **The 3.5-day budget predates the interface below.** It was priced against a shorter list; three
requirements were added by SPEC §4.9 on 2026-07-28 and the budget has not been re-examined since.

**F1 — history-required aliasing.** Visually identical observations require different actions because
of a hidden switch, counter, or phase.

**F3 — sparse delayed causal memory.** A one-cell change with no short-term effect that determines a
later transition. **This is the central risk for reconstruction-free prediction:** the latent objective
has almost no gradient pressure to preserve a bit whose consequence lies outside the training horizon,
while an exact target retains it structurally. **F1 alone sits in the short-horizon regime where a
latent predictor looks good, so without F3 any positive result is biased.**

*(F2 and F4 are cut — they test capability-as-science more than build-relevant viability.)*

### Conventions the generators must match — measured, not documented

Across all 25 public games, 2026-07-26 (`measure_arc_conventions.py`):

| Convention | Measured |
|---|---|
| Grid shape | **64×64 always** at reset — no padding convention needed |
| Cell values | **0–15**, all 16 occur |
| Frames per observation | **1–N, varying within an episode** |
| Levels per game | 6–10 (mode 6) |
| Action availability | **per-game** (ACTION6 in 19/25). ⚠ per-*state* variation is permitted by the interface but **not evidenced** — hold fixed per game |

**🔴 Observations are frame sequences, and the tail is long.** Measured over the replay corpus: 71%
are a single grid, the mean is **2.86**, the maximum is **404**. Three consequences:

1. **The generators must emit variable-length frame sequences**, or they produce a distribution the
   real environment never generates and S4 is measured on a mismatch.
2. **Any encoder must consume 1–N frames.** A model assuming one grid silently discards most of the
   observation at exactly the steps where something interesting happened — invisible in aggregate loss.
   It also costs 2.86× the benchmarked compute (§2).
3. **This interacts with F1 directly.** If an observation is itself a sequence, part of the "history"
   the aliasing test is about lives *inside a single observation*. F1's timestep must be defined
   against this, or its ceilings measure something else.

### F1 needs three ceilings, not one

Oracle-hidden-state beating observation-only shows hidden information *matters*. It does not show that
history contains enough to *recover* it. Run **observation-only** · **complete observable history with
an oracle decoder** · **oracle hidden state**. Required pattern: observation-only < history-oracle ≈
hidden-state-oracle. If the history oracle stays far below the hidden-state oracle, the task is not
learnably history-resolvable and model failure is expected — **without this ceiling that would be
misread as a model result.**

### Generator interface

**SPEC §4.9 is the governing list; this restates it.** Legal action set · exact successor for every
legal action · terminal/progress predicate · **immediate action value or distance-to-goal** (the
ranking criterion — without it, ranking regret has no ordering) · hidden mechanic state and
parameters · which state variables are causally relevant · recoloured and relaid-out variants with
colour roles explicitly permuted · **variable-length frame sequences**.

**Three requirements added by SPEC §4.9, 2026-07-28**, each demanded by a consumer outside S3:

- **ground-truth state IDs** — §6.6's Jensen–Shannon divergence needs a policy-independent key;
- **instance seed and environment random-stream control**, with common-random-number support
  **declared per generator, never assumed** (§6.6, §14);
- **on-demand instance generation** — §13.1's insufficient-evidence rule extends procedural paired
  runs, which a fixed pre-generated set cannot serve. This is an architecture requirement, not a
  feature: it makes the generator a live reproducibly-seeded sampler rather than a dataset.

**The value criterion is evaluation-only.** If it trains a value head, S3 becomes supervised action
ranking rather than an objective comparison.

---

## 8. S3 — Objective screening

**5 days. Two paired seeds.** Adequate for a build decision, explicitly not for a claim.

**Decides *which* Tier 3 objective, not whether Tier 3 is retained.** That is S4.

| Arm | Target |
|---|---|
| **A** | reconstruction-free latent (JEPA) |
| **B** | matched reconstructive next-state predictor |
| **C** | matched exact structured delta |

**Exact-delta is mandatory.** The decision is not "JEPA versus reconstruction" but "JEPA versus the
strongest compact alternative." Without C, a mediocre decoder in B yields a false JEPA-positive.

**Rollout is an ablation within each objective, not a separate arm** — for each of A/B/C, with rollout
versus without. A standalone "no-dynamics arm" has no specified training objective, so any difference
could come from an unspecified encoder rather than from dynamics. **Six configurations, twelve runs.**

**Matched information.** Every configuration receives identical observation history, actions,
metadata, retrieval context, training data, and data ordering. **Only the predictive target differs.**
The cheap controls (observation-only A; affordance/no-op classifier) also get matched history, or
"JEPA beats affordance" merely restates "history beats no history."

**Matched ranking interface.** Same candidate set, same downstream evaluator class and fitting budget,
plus an **oracle-successor ranking ceiling**. One cheap guard: **if the without-rollout configurations
approach the with-rollout ones, the evaluator is doing the work** and no dynamics conclusion is
available. Interface effects can swamp this contrast — published results show terminal-cost changes
alone moving a latent planner from 7% to 97% success.

**Degeneracy monitoring is symmetric.** Per-dimension variance, effective rank and control-variable
probe accuracy for **every** learned representation, not only JEPA — reconstructive and exact-delta
representations cannot collapse totally but can still be partially degenerate or exploit shortcuts.
Rescue stays JEPA-specific and pre-registered: trigger on variance below `T_v` or effective rank below
`T_r`; **probe accuracy is diagnostic only and never an abort trigger**, since aborting on it means
aborting on the measured outcome; one fixed-coefficient recipe, untuned; **at most one remedial
rerun**; **collapse frequency reported as a result.**

**The five questions:** (1) does history conditioning help at all? (2) does rollout add anything over
the same representation without it? (3) does A beat B and C on counterfactual ranking regret and
identification? (4) **does A retain the sparse delayed causal bit on F3?** (5) what is A's inference
cost per candidate against S1's per-action budget — noting S1's **wall-clock verdict was FAIL**, so
this is a live constraint, not a formality.

**Compute:** twelve runs × 100k steps at 21.2M params ≈ 46.2 h measured against a 120 h budget —
**before** the frame-convention multiplier of §2. Capacity is not the binding constraint; frames are.

---

## 9. S4 — ARC advisor test

**2.5 days. The only measurement that can retain or kill JEPA on operational grounds.**

**Decides whether Tier 3 is retained at all.**

**Primary:** train each objective on the same ARC replay training games, evaluate on **held-out games**
with identical frozen advisor interfaces. Readouts: candidate pruning quality · no-op avoidance ·
changed-region prediction · representation stability across games · latency per candidate.

**Plus a small closed-loop run** on two or three development games, model as advisor only. Offline
probes cannot establish control utility, and control utility is the retention criterion.

**Two inherited constraints, both binding:**

- **The control is local and paired**, not a leaderboard delta (§4.4). Better internal validity; **no
  claim to hidden-set utility.**
- **Replicates are mandatory** (§4.2). At a 36% run-to-run noise floor, an unreplicated advisor-on/off
  comparison cannot resolve any effect smaller than the noise. **Budget them before S4 starts.**

**Do not treat the human's next action as ground-truth action quality** — that is imitation, not
planning utility. Stratify any action ranking by the replay action's observed outcome (terminal ·
persistent-progress · informative change · reversible change · no-op).

**Candidate pruning must be reported as an outcome-stratified evaluation, never trained as a ranking
objective.** Replays are on-policy: the whole corpus contains **204** counterfactual pairs where a
progress event distinguishes two actions. Sizing:
[`screening-training-data.md`](../notes/screening-training-data.md).

---

## 10. S5 — Decision audit

**1 day. Stop implementing.** Four axes:

| Axis | Content | State entering S5 |
|---|---|---|
| **B** baseline readiness | accepted submission · hidden score · latency · reliability | **impaired** — no score unless §2 float claim 2 is spent |
| **M** mechanism evidence | history effect · rollout effect · objective ranking · F3 retention · collapse frequency | from S3 |
| **U** advisor utility | held-out readouts · closed-loop delta · latency cost | from S4, **local scope only** |
| **C** feasibility | remaining calendar · integration complexity · remaining compute | ~46.2 h of 120 h used by S3 |

**Cases that need all four and cannot be read from a 2×2:** strong synthetic mechanism with weak ARC
utility · strong baseline with unresolvable licensing · weak public score with nonzero hidden score ·
JEPA equivalent to reconstruction but materially faster · **JEPA strong only with exact auxiliaries,
meaning the auxiliaries carry the result.**

**Output:** each component marked build / defer / drop, fed to the register and thence to SPEC §3 and
§12.

---

## 11. Still to pre-register

Into `gate_manifest.yaml`, **before the step it governs.** S1 is frozen with results; **S2–S5 are all
still `NOT_STARTED`.**

| Sprint | Numbers required |
|---|---|
| **S2** | value/distance-to-goal criterion per family · F1's three-ceiling margins · F3's delay length and bit sparsity · **the frame-sequence length distribution the generators emit** · **the generator's distinct-instance count and held-out instance count** · **the encoder's frame cap** · **procedural progress-event prevalence** · **generator throughput** (SPEC §4.9 names it unregistered; below its compute-bound rate S3 becomes data-bound) |
| **S3** | primary metric and threshold for each of the five questions · `T_v`, `T_r` · the rescue recipe's fixed coefficients · the evaluator-doing-the-work criterion · **the parameter count**, currently a guess · **the step count** ("matched optimization budget" currently has no number) |
| **S4** | the retention threshold — what advisor improvement at what latency cost · **the replicate count** (§4.2) · **the step budget and model size** · **the train/held-out game split, and whether it is drawn as the SPEC §13.5 partition** |
| **S5** | the B/M/U/C pattern mapping to each branch |

Items in **bold** were identified after the manifest comments were written and appear nowhere yet.
Sizing rationale: [`screening-training-data.md` §7](../notes/screening-training-data.md).

---

## 12. Limitations that bind every result in this document

1. **Two seeds, two families.** Adequate for a build decision; **not** adequate for a claim.
   Confirmatory replication happens later on whichever contrast survives integration — three-plus
   seeds, more families, the entity-factorization factor, ARC-trained held-out evaluation, and the
   full control set from
   [`arc-agi-3-jepa-feasibility-analysis.md`](arc-agi-3-jepa-feasibility-analysis.md). Any paper rests
   on that pass plus the accumulated ablation table, **not on this sprint.**
2. **A 36% run-to-run noise floor** (§4.2) makes unreplicated per-episode comparisons uninterpretable.
3. **No leaderboard reference** (§4.4). Every advisor result is local-paired scope.
4. **Public games are materially easier than hidden ones** — 13.33% public against 7.78% semi-private
   for the ARC-standardized frontier reference. **A public number is never evidence of hidden
   generalization.**
5. **The rater is an LLM, not a human** (S1-E10), and the blind re-rate has not run.

---

## 13. Revision log

Changes to this document are recorded rather than made silently. It is **not** pre-registration — that
is `gate_manifest.yaml`, which is append-only. Editing here is permitted; editing without a log entry
is not.

| Date | Change |
|---|---|
| 2026-07-25 | Written; final revision under the score-primary utility ordering |
| 2026-07-27 | Restructured component-first; §3 coverage gap, §3.4 variance floor, §4 float claims, DEGRADED consequences, measured ARC conventions |
| 2026-07-28 | **Re-scoped to evidence-and-results** on the arrival of the binding specification. Component inventory withdrawn in favour of SPEC §3 |
| 2026-07-28 | **Cut 673 → 470 lines and renumbered for navigability** *(old section numbers in this row)*. New §1 status board — the orientation view the document previously lacked. Schedule detail delegated to `execution-schedule.md`; old §13 "After Aug 22" deleted as duplicating SPEC §12; old §11 paper-by-product dropped as duplicating `CLAUDE.md`. Archaeology compressed to one paragraph each — the withdrawn tier ordering (old §2.2), the coverage-gap narrative (old §3.2) and the three readings (old §3.3) — their full record being register entry `G0-SCOPE-2026-07-28`. Limitations gathered from five places into one §12. **Corrected a stale overclaim:** old §3.1 still read "the decline reads as genuine run-to-run variation" after §2.2 had already withdrawn it; a partial, non-blind re-rate cannot establish that |
| 2026-07-28 | Added a measured training-data readiness summary: what exists, required presentation scale, acquisition difficulty, and the distinction between abundant factual transitions and scarce counterfactual labels |
| 2026-07-28 | §4.3 rewritten: the reset result had been reported as configuring the controller only, when it also **settles SPEC §4.1's reset posture** — recorded as `RESET-CASE-2026-07-28` and amended into the spec the same day. The scope limits both claims carry (offline, one game) are now stated where the result is |
| 2026-07-28 | **S2 re-scoped after the specification created SPEC §4.9.** S2 was described as building "the instruments S3 uses"; the suite is Tier 1 unconditional substrate with six consumers outside S3 and is a **build step-1 precondition**, so a slip moves D0 and the whole build. §7's generator interface was a strict subset of the spec's and now carries the three requirements §4.9 added — ground-truth state IDs, seed and random-stream control with CRN declared, and on-demand generation. **The 3.5-day budget predates that interface and has not been re-examined.** §3's S1 row lost a dangling `Case` label; §11 gained generator throughput |

---

## Appendix — evaluation apparatus `[definition site]`

**Reference material, not overview.** These five terms define how a measurement is *read*, not what the
agent contains, so they belong with the evidence. Their original definition sites were archived
2026-07-28; **this appendix is now the definition site.** Only *procedural boundary suite* also appears
in the specification, as Tier 1's "procedural suite core (F1, F3)".

**demotion ladder** *(also A §21)* — the fallback modes the agent drops through when it stops being
trustworthy: full sequential hierarchical agent → sequential flat model → exact archive and graph
agent → conservative frontier exploration. Triggered by rollout disagreement beyond tolerance ·
exact-delta error rising sharply · reachability calibration failure · no validated subgoal · high
rule-shift probability · time reserve below the required margin.

**common-candidate audit** *(= the same-candidate oracle audit)* — identical candidate sequences
rolled through every model and executed in the deterministic simulator, giving ground-truth candidate
quality **with no learned judge.** Four stages, each isolating one failure source: (1) **candidate
quality** — best true outcome in the set → sampler or horizon limits; (2) **rollout fidelity** —
predicted versus exact outcomes → dynamics; (3) **terminal evaluation conditional on exact endpoints**
— exact endpoints through each condition's frozen encoder and head, removing rollout error →
interface and geometry; (4) **closed-loop executed result** → replanning, compounding error,
execution. Two candidate pools are required: a fixed-size **exogenous** pool generated independently
of all conditions, carrying the primary audit, and a fixed-size **union** pool sampled evenly from all
model proposal sources, secondary with its endogeneity named.

**attribution ladder** — the four rungs within stage 3 above, separating "the model is wrong" from
"the interface is wrong": (i) simulator-state oracle ranking → (ii) a shared frozen external
featurizer of representation-independent grid features → (iii) condition encoder plus a linear or
bilinear comparator → (iv) condition encoder plus full head. The gaps are the reading: (i)→(ii)
feature sufficiency · (ii)→(iii) representation accessibility · (iii)→(iv) nonlinear interface value.
Works for *any* pair of arms, which is why
[`architecture-alternatives.md` §11](arc-agi-3-architecture-alternatives.md) calls this the most
transferable scientific asset in the project.

**diagnostic contract** — the frozen baselines every condition is read against: copy-last-observation
persistence · random candidate ranking · exact-simulator planning under the same candidate budget ·
archive or exact-transition-table baseline. Reported per condition: whole-frame exact match ·
changed-cell precision, recall, F1 · irreversible-event and level-transition prediction accuracy ·
multi-step exact-rollout survival · counterfactual action discrimination. If the token loss uses
change weighting, the weighting rule is frozen from outer-train data only. **Unchanged-cell accuracy
never substitutes for dynamics knowledge.**

**procedural boundary suite** — synthetic generators producing many independent environments while
varying one factor at a time: visible versus partially observable state · fixed versus
environment-specific action semantics · smooth versus exact irreversible transitions · broad versus
one-cell-critical state relevance · direct versus non-greedy prerequisite goals · unimodal versus
genuinely aliased successors · short versus compositional horizons · familiar versus held-out
combinations of mechanics. Committed as **eight paired one-factor-at-a-time micro-environments with
easy and stress arms — not a 2⁸ factorial.** **S2's F1 and F3 are the two families that survive the
screening sprint.**

**goal-predicate class taxonomy** — the ten classes S2 labels a game's terminal transition against,
enforced as a closed set by `agent/harness/s2_apply_labels.py :: TAXONOMY`. Originally
`agent-architecture.md` §5.2, archived 2026-07-28; **this appendix is now the definition site.** The
list is unchanged by the relocation — it is *evidentiary*, not a spec instrument: the specification
neither defines nor references it, and it binds S2's labelling only, via
[`docs/README.md`](README.md) entry `DOCS-TAXONOMY-2026-07-28`.

1. `state_relations` — a relation between objects or cells (adjacency, containment, alignment)
2. `quantified_object_conditions` — a condition holding over some or all objects of a kind
3. `counts` — a cardinality reaching a target
4. `region_membership` — an object inside or outside a designated region
5. `symmetry_and_template_match` — the grid matching a symmetry or a supplied template
6. `all_instances_transformed` — every instance of a kind having undergone a transformation
7. `event_occurrence` — a specific event having happened at all
8. `ordered_event_programs` — several events having happened **in order**
9. `action_conditioned_terminal_triggers` — the condition depending on the action, not only the state
10. `cumulative_counters` — an accumulated quantity crossing a threshold

Classes 8 and 9 are what make this more than a state classifier: an ordered program and an
action-conditioned trigger are both invisible to any predicate read off a single frame.

**Closed on purpose.** A predicate fitting none of them is labelled `outside_taxonomy` — recorded,
counted and reported separately, never absorbed — because a codebook that quietly stretches to fit
everything cannot be found wrong, and "the class library is incomplete" is a result worth having
before the induction machinery is built.

**It is a PRE-SPECIFIED CLOSED CODEBOOK, not a pre-registered instrument.** The distinction is not
pedantry: it was written down before any S2 labelling and has not changed since, which is what
pre-*specified* means — but it was never entered in `gate_manifest.yaml`, and `s2` there is still
`NOT_STARTED` (open item 2 on the status board: pre-registration must precede the sprint it governs).
So it carries the authority of a codebook fixed in advance, and none of the authority of the
pre-registration mechanism. Treating it as frozen is premature until `gate_manifest.yaml -> s2`
exists and adopts it; that adoption is the moment the "adding a class needs a dated erratum" rule
starts to bite. Until then, changes to it are ordinary evidentiary edits and the S2 frequencies
derived from it inherit the open pre-registration as a stated limitation.

The learnable object is the **terminal transition** `(o_t, a_t, Δ_{t+1}, level advanced)`, not a
positive goal state — a completing action typically returns the *next* level's frame, so a satisfying
state may never be directly observed. Labels are **graded, not binary**: a visited non-advancing state
is negative for *terminal now* but may be prerequisite-satisfied, partial-progress, or
unknown-because-hidden-state-unresolved. Granularity is **per game, not per level**, because
cross-level transfer is parameterised — so a class frequency here is a frequency over games and must
not be reported as a frequency over levels.

Not to be confused with the **S1-d failure taxonomy** (`goal_unknown`, `perception_parsing`, …), which
classifies why an agent failed. That one labels episodes; this one labels games.
