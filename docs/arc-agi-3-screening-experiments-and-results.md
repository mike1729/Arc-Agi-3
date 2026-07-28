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
| **S1** | reset **Case**, `r`, `c_reset` · measured latency table · failure-frequency ranking · the variance floor |
| **S2** | F1 and F3 generators matching measured ARC conventions |
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

### 4.3 The reset posture — gated nothing, configured everything

`accumulates`, `r` = 2.0357, `c_reset` = 1 — **RESET is itself scored.** This selected the **surgical
information-per-action controller** over an aggressive identify-then-execute one: every probe costs
score. That decision propagates into Tier 2's probe controller.

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

**3.5 days. Decides no component — it builds the instruments S3 uses.** Priced accordingly: if S2
overruns, it takes days from the sprint's only decision-bearing blocks.

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

Legal action set · exact successor for every legal action · terminal/progress predicate · **immediate
action value or distance-to-goal** (the ranking criterion — without it, ranking regret has no
ordering) · hidden mechanic state and parameters · which state variables are causally relevant ·
recoloured and relaid-out variants · **variable-length frame sequences**.

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
| **S2** | value/distance-to-goal criterion per family · F1's three-ceiling margins · F3's delay length and bit sparsity · **the frame-sequence length distribution the generators emit** · **the generator's distinct-instance count and held-out instance count** · **the encoder's frame cap** · **procedural progress-event prevalence** |
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
