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

**Sprint: 18.5 focused days, hard stop Aug 22** — **hard stop lifted 2026-08-03** (register
`SCHED-2026-08-03`, manifest errata `META-E1`): discovery of whether anything is possible at all now
precedes the calendar; external Kaggle dates unchanged. Budget 40–50 h/week solo, ~5 focused days/week.

| Sprint | Days | State | Decides (binding) | Evidence |
|---|---:|---|---|---|
| **S0** starter submission | 0.5 / 0.5 | ✅ **complete** — public score 0.06 | execution path only | [`ledger`](../submissions/ledger.md) |
| **S1** baseline reproduction | 6 / **2** | ✅ **complete 2026-07-28 — DEGRADED payload, no hidden score** · gate applied (κ 0.7207, 30/30, floor 0.40); build order filled | SPEC §4.1 reset posture · D0 latency inputs · SPEC §2 per-action budget | §6, [`s1-closeout`](../notes/s1-closeout.md) |
| **S2** Alias + Delay generators | 3.5 / — | ▶️ **next** | decides no component, but **builds SPEC §4.9** — Tier 1 substrate — and carries its own gate, SPEC §12.1 **step 0** (schedule day A5-G). Passing it releases D0 and all procedural-dependent build work; failing it leaves W1's non-dependent substrate free to continue | §7 |
| **S3** objective screening | 5 / — | not started | **R0 / SPEC §11** — the predictive objective | §8 |
| **S4** ARC advisor test | 2.5 / — | not started | **SPEC §11.2 rung gates** — is Tier 3 retained at all | §9 |
| **S5** decision audit | 1 / — | not started | **SPEC §12.2 slack policy** — build / defer / drop | §10 |
| *(G0-R, G0-A)* | — | spec-side, W7 | **SPEC §9 gate G0** | SPEC §9 |

**Two things are open right now and block their own sprints:**

1. **`gate_manifest.yaml → s2` is `DRAFT`, not `frozen`.** It was written 2026-07-28, before the A2
   generator work it governs, so the pre-registration order holds. What remains is **operator
   acceptance of its PROPOSED values** — they must be accepted or replaced before A2 begins, exactly
   as S1's were before S1-b. The list is `s2.open_before_A2`; the numbers are summarised in §11.
2. **Two pre-registrations coexist** — the manifest and SPEC §13 both predeclare numbers. Open item 1
   in [`README.md`](README.md). The `s2` block deliberately does **not** resolve this: it registers
   only quantities SPEC §4.9 marks unregistered and cites §13.1/§9.4/§9.5 rather than restating them,
   so it adds nothing to the collision and can migrate whole if the item resolves toward the spec.

**Closed 2026-07-28 — S1's blind re-rate.** `agreement_floor: 0.40` has now been applied: 30 of the 75
labelled episodes, drawn stratified, re-rated in a fresh `claude-opus-5` context, overall κ **0.7207**.
`logs/s1d_rerate_result.json` is a promoted `gate_valid: true` result and the four manifest roll-up
fields are filled from it. **S1 closes on the DEGRADED branch: `hidden_score` is null and stays null** —
no submission has ever carried an entrant-authored payload — §6.

---

## 2. Training-data readiness — do we have it, how much is needed, how hard is it to get?

**Short answer:** executed transitions are abundant; *procedural diversity* and *real
counterfactuals* are not. The replay archive already covers ARC-shaped observations and factual
targets. S3 still depends on a generator that has not been built, and the hardest S4 labels ask what
a different action would have done — information an on-policy replay cannot contain at any volume.

**Measured inventory, 2026-07-28:** 340 human sessions (6.4 GB) provide **180,144 valid
transitions**, including 171,199 changes, 8,945 no-ops, 1,614 terminal transitions, 56,347 ACTION6
transitions and 516,260 grids (mean 2.86 per observation). Three reference-agent runs add **12,475
transitions**, including 1,446 no-ops and 49 terminals. Procedural Alias/Delay data is unbounded in
principle but **zero exists today**: S2 builds its source. Full census and derivations:
[`screening-training-data.md`](../notes/screening-training-data.md).

Difficulty below means **data acquisition**, not model implementation: 0–2 = in hand or one
extraction pass; 3–4 = produced by already-scheduled work; 5–6 = needs a new instrument; 7–8 =
hard-budget environment interaction with uncertain yield.

| Consumer | How much is needed | What exists now | Difficulty | Verdict |
|---|---|---|---:|---|
| **S2 ceilings** | Enough disjoint instances to resolve the registered Alias/Delay margins; counts are **not yet registered** | generated on demand after S2 exists | **4** | volume is elastic; instance diversity is the risk |
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

## 6. S1 — Baseline reproduction · **COMPLETE (DEGRADED branch)**

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

**S1 closed on 2026-07-28.** The three conditions it was reopened for are all discharged:

1. the corpus is rebuilt from the three single-pass runs — **75 episodes, all labelled**;
2. the re-rate is drawn and scored as an **independent re-rate, same model** (S1-E10 — not delayed
   test-retest; an LLM rater has no memory to decay), on the scripted worksheet for all 30 sampled
   episodes including the v2 ones;
3. categories below `agreement_floor: 0.40` are excluded and the manifest's four null roll-up fields
   are filled from what survives.

### 6.1 The blind re-rate — result

30 of the 75 labelled episodes, stratified on first-pass `primary_label`, oversampling `goal_unknown`
and `exploration_or_probe_selection` (S1-E3/E4 eligibility: **1 of its 4 first-pass episodes eligible**,
6 of 25 games qualify). Re-rated by `claude-opus-5` in a fresh context with no access to the first pass.
**Overall κ 0.7207** on primary label, 25 of 30 exact matches. Cooling period **INAPPLICABLE**, not
satisfied — S1-E10.

| Category | κ primary | κ any-label | Drives build order |
|---|---:|---:|---|
| `goal_unknown` | 0.7945 | 0.5161 | ✅ |
| `action_semantics_unknown` | 0.6296 | 0.5714 | ✅ |
| `exploration_or_probe_selection` | 0.6512 | 0.4690 | ✅ |
| `progress_signal_misinterpretation` | 1.0 | 0.5833 | ✅ |
| `latency_or_budget` | 0.7826 | **0.011** | ❌ fails any-label |
| `irreversible_mistake` | **0.0** | 0.5946 | ❌ fails primary |
| `retrieval_or_context` | — | **0.2941** | ❌ |
| `perception_parsing` | — | **0.1045** | ❌ |
| `hidden_state_aliasing_or_memory` | — | **0.0** | ❌ |
| `invalid_output_interface` | — | **0.0** | ❌ |
| `reasoning_inconsistency` | *(never drawn)* | *(never drawn)* | ❌ — untested, not failed |

**`latency_or_budget` is the instructive exclusion.** Its primary κ is high (0.7826) and its any-label
κ is ~0 — because **all 75 episodes were budget-terminated**, so the label applies vacuously everywhere
and the two passes differ mainly on whether termination *caused* the failure or merely ended it. In the
sample the first pass attached it to **27 of 30** episodes and the re-rate to **11**, overlapping on 10;
the re-rate applied the definition's "rather than because of a decision error" clause and the first pass
largely did not. It carries the second-highest `episode_share` in the corpus (0.8267) and would have
ranked high on frequency alone. The two-axis rule is what caught it: a category that is always
technically present discriminates nothing, and building for it first would have been building for the
budget rather than for a decision failure.

### 6.2 Limitations of the gate, recorded rather than argued away

- **It bounds label STABILITY, not correctness.** An LLM re-rating an LLM may share systematic blind
  spots (S1-E10); no human-rated sample bounds that.
- **The evidence slice is an opening-and-closing one** — first analysis step plus the last two, at
  fixed caps. `hidden_state_aliasing_or_memory` is under-counted **by construction**, because the
  repeated states it is defined on sit in the elided middle. It is also one of the excluded categories,
  so nothing here rehabilitates it.
- **The two passes rated matched evidence for 22 of 30 episodes, not all 30.** The v2 first pass
  predates `s1d_worksheet.py` and used an unreproducible ad-hoc slice; the re-rate used the scripted
  worksheet throughout. Diagnostic split: **v2 subset 8/8 exact, κ 1.0** · **v3+v4 subset 17/22, κ
  0.6194**. The mismatch therefore did **not** inflate agreement — the matched-evidence subset is the
  *more conservative* number, and 0.7207 is if anything flattered by the 8 unmatched episodes. At n=8
  this is a diagnostic, not a finding.
- **Four categories drive the build order; seven do not.** Six were measured and excluded, one was
  never drawn. That is a real narrowing of what S1 can order, and it is the point of having run
  the gate.

Artifacts: [`logs/s1d_rerate_result.json`](../logs/s1d_rerate_result.json) (promoted, `gate_valid:
true`) · `logs/s1d_rerate_draw.json` + its `.manifest.json` commitment · `logs/s1d_rerate_pass2.json` ·
roll-ups generated by `agent/harness/s1d_rollup.py`, which `--verify` re-checks against the artifacts.

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

**Alias — history-required aliasing.** Visually identical observations require different actions because
of a hidden switch, counter, or phase.

**Delay — sparse delayed causal memory.** A one-cell change with no short-term effect that determines a
later transition. **This is the central risk for reconstruction-free prediction:** the latent objective
has almost no gradient pressure to preserve a bit whose consequence lies outside the training horizon,
while an exact target retains it structurally. **Alias alone sits in the short-horizon regime where a
latent predictor looks good, so without Delay any positive result is biased.**

*(Two further families from the original four were cut — they test capability-as-science more than
build-relevant viability. They were `F2` and `F4` under the retired numbering, and are deliberately
not renamed here: they were never specified beyond that line, so a name would imply a definition
that does not exist. The `F4` of SPEC §9.6 was a **different** family — now `Order` — and the
collision between the two is one reason the numbering was retired.)*

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
3. **This interacts with Alias directly.** If an observation is itself a sequence, part of the "history"
   the aliasing test is about lives *inside a single observation*. Alias's timestep must be defined
   against this, or its ceilings measure something else.

### Alias needs three ceilings, not one

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
identification? (4) **does A retain the sparse delayed causal bit on Delay?** (5) what is A's inference
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
| **M** mechanism evidence | history effect · rollout effect · objective ranking · Delay retention · collapse frequency | from S3 |
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

Into `gate_manifest.yaml`, **before the step it governs.** S1 is frozen and **CLOSED** with results;
**S2 is drafted** (2026-07-28, before the A2 work it governs); **S3–S5 remain `NOT_STARTED`.**

**S2 — drafted, not yet frozen.** Every number SPEC §4.9 listed as unregistered now has a registered
value, in two kinds. **Derived and accepted:** generator throughput **3,710 transitions/s** (arithmetic
over the measured 7.22 steps/s benchmark — 512 transitions/gradient step at 138 ms) and the full
observation-fidelity table (measured across 25/25 games and 340 replays, including the frame-length
distribution: 71.0% single, mean 2.86, max 404). **Proposed, awaiting operator acceptance:** held-out
instance count · instance diversity per family · progress-event prevalence (against a measured 0.90%
anchor) · Alias's three-ceiling margins · Delay's causal-delay length and bit sparsity · the encoder frame cap ·
the value criterion and its goal families.

The block freezes when those are accepted or replaced — `s2.open_before_A2` is the list. Proposed
values borrow already-registered structure where one exists (Alias's margins reuse SPEC §9.5's margin
rule; Delay's causal-delay range is set against §11.1's trained horizons of 1/2/4 steps, the 8-step rollout and
the K=16 window) rather than inventing a scale, and each says which it is.

| Sprint | Numbers required |
|---|---|
| **S2** | ~~all registered~~ — drafted 2026-07-28; PROPOSED values pending acceptance before A2 |
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
5. **The rater is an LLM, not a human** (S1-E10). The blind re-rate has now run (κ 0.7207, §6.1), but
   it is an LLM re-rating an LLM: it bounds label **stability**, not correctness, and the two passes
   may share systematic blind spots that no amount of agreement between them would reveal. Nothing in
   this document rests on a human-rated sample.

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
| 2026-08-03 | §1: **the Aug 22 hard stop no longer binds** — operator decision, register `SCHED-2026-08-03`, manifest errata `META-E1`. The screening line (VP → GI-2 → ES → MU) has not yet established that any usable local-model capability exists; the sprint continues until that feasibility question is answered by measurement. External Kaggle dates and the 1/day quota unchanged; the Aug 24 → Oct 18 build window compresses day-for-day; SPEC §9.6/§13.4 calendar anchors amended the same day |

---

## Appendix — evaluation apparatus `[definition site]`

**Reference material, not overview.** These five terms define how a measurement is *read*, not what the
agent contains, so they belong with the evidence. Their original definition sites were archived
2026-07-28; **this appendix is now the definition site.** Only *procedural boundary suite* also appears
in the specification, as Tier 1's "procedural suite core (Alias, Delay)".

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
changed-cell precision, recall, F1 score · irreversible-event and level-transition prediction accuracy ·
multi-step exact-rollout survival · counterfactual action discrimination. If the token loss uses
change weighting, the weighting rule is frozen from outer-train data only. **Unchanged-cell accuracy
never substitutes for dynamics knowledge.**

**procedural boundary suite** — synthetic generators producing many independent environments while
varying one factor at a time: visible versus partially observable state · fixed versus
environment-specific action semantics · smooth versus exact irreversible transitions · broad versus
one-cell-critical state relevance · direct versus non-greedy prerequisite goals · unimodal versus
genuinely aliased successors · short versus compositional horizons · familiar versus held-out
combinations of mechanics. Committed as **eight paired one-factor-at-a-time micro-environments with
easy and stress arms — not a 2⁸ factorial.** **S2's Alias and Delay are the two families that survive the
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
pre-*specified* means. `gate_manifest.yaml -> s2` is now `DRAFT`, but its
`prior_work_not_governed_by_this_block` section explicitly places the goal-predicate extraction
outside that block and does not adopt this taxonomy. So the codebook carries the authority of a
codebook fixed in advance, and none of the authority of the pre-registration mechanism. Treating it
as frozen is premature unless a frozen manifest block adopts it; that adoption would be the moment
the "adding a class needs a dated erratum" rule starts to bite. Until then, changes to it are
ordinary evidentiary edits and the S2 frequencies derived from it inherit the draft
pre-registration as a stated limitation.

The learnable object is the **terminal transition** `(o_t, a_t, Δ_{t+1}, level advanced)`, not a
positive goal state — a completing action typically returns the *next* level's frame, so a satisfying
state may never be directly observed. Labels are **graded, not binary**: a visited non-advancing state
is negative for *terminal now* but may be prerequisite-satisfied, partial-progress, or
unknown-because-hidden-state-unresolved. Granularity is **per game, not per level**, because
cross-level transfer is parameterised — so a class frequency here is a frequency over games and must
not be reported as a frequency over levels.

Not to be confused with the **S1-d failure taxonomy** (`goal_unknown`, `perception_parsing`, …), which
classifies why an agent failed. That one labels episodes; this one labels games.
