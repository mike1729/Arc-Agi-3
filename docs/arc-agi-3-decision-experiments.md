# Stage 0 — Score-Oriented Screening Sprint

**Written 2026-07-25, rev. 2026-07-25 (final).** Supersedes the build orders in
[`arc-agi-3-agent-architecture.md`](arc-agi-3-agent-architecture.md) §9 and
[`arc-agi-3-execution-plan.md`](arc-agi-3-execution-plan.md) §13. Both architecture documents are held as
candidate designs; neither is committed.

**Utility ordering** (governs everything below, and is not derived from the experiment): **leaderboard
score is primary.** The paper is a continuous by-product (§9), not a fallback activated later. The
"leaderboard placement is a non-goal" line in the execution plan is superseded.

**What this is.** A **component-screening sprint**, not a publishable experiment. Its job is to decide what
to build, cheaply, and then get out of the way. Two seeds and two synthetic families are adequate for a
build decision; they are not adequate for a scientific claim, and confirmatory replication happens later
on whichever contrast survives integration (§12).

**Budget.** 40–50 h/week solo. Focused working days (~5/week).

---

## 1. Why this replaces the 33-day protocol

The previous version optimized the probability of making a correct architectural decision. That is the
wrong target given a score-primary ordering, and it contained a contradiction: it claimed leaderboard-first
stayed viable on 5.3 weeks while simultaneously postponing the object compiler, goal induction, coordinate
system, belief ledger, executive and DSL — precisely the score-bearing components. A reproduced baseline is
where construction begins, not evidence that it is finished.

| | 33-day protocol | This sprint |
|---|---:|---:|
| Decision-grade architectural evidence | 60–75% | ~40–50% (screening-grade) |
| Construction weeks before feature freeze | ~5.3 | **~8.4** |
| Paper-Prize-competitive | 3–8% | 3–8% (unchanged; §9 is what moves it) |
| Valuable preprint + engineering artifacts | 65–80% | 65–80% |

The trade is explicit: weaker initial evidence, four more weeks of score-bearing implementation.

---

## 2. Schedule

**~18.5 focused days ≈ 3.7 weeks. Hard stop Aug 22.** Leaves **~8.4 weeks** to the Oct 18 feature freeze.

| | Days |
|---|---:|
| S0 — starter submission, day one | 0.5 |
| S1 — baseline reproduction, light instrumentation, submission | 6 |
| S2 — minimal F1 + F3 generators with three ceilings | 3.5 |
| S3 — objective screening, 2 paired seeds | 5 |
| S4 — ARC advisor test | 2.5 |
| S5 — decision audit | 1 |
| **Total** | **18.5** |

*(The 14-day version of this plan cut the failure instrumentation and priced the advisor test at 1.5 days.
The instrumentation is directly score-relevant — it ranks which lever to build first — and the advisor test
is the only measurement that can retain or kill JEPA on operational grounds. Both are restored.)*

**Verify before relying on any date:** Nov 2 final submission and Nov 8 paper deadline are on the public
page; the Oct 26 entry/team-merge date comes from project notes. Confirm competition-mode constraints too —
level resets only, one environment creation per game, hidden in-flight scorecards — the second of which
materially constrains exploration strategy.

---

## 3. S0 — Starter submission, day one

**0.5 days, first 24–48 hours.** Submit the untouched or minimally modified official starter.

Kaggle runs both a validation pass and a hidden rerun, and a substantial fraction of failed submissions
surface no traceable notebook error. Proving the external execution path before building anything is the
cheapest risk reduction in the project.

---

## 4. S1 — Baseline reproduction and reference point

**6 days.** Reproduce one strong public local-model agent. Accept its harness rather than building your own
— that is where most of the saving comes from.

### Freeze the reference before starting

Otherwise the hard reproduction proves painful, you fall back to the template, and S1 is marked complete
without answering its question. Freeze in writing: repository URL and commit · exact model and weights ·
license interpretation against the CC0/MIT-0 release requirement · quantization · accelerator · expected
public behaviour · known score or reproduction target · permitted deviations.

The question is: **how far are we from a competitive working baseline, and which failures look improvable?**
A minimal template validates packaging but cannot answer it.

**Measure:** hardware fit · real per-action latency under the actual batching pattern · legal-action
reliability · public-game progress against the reproduction target · **reset and action accounting** ·
packaging and offline bundling.

**The reset experiment** gates nothing and configures everything: does a level reset preserve knowledge,
and does the scored action count accumulate or restart? It selects between an aggressive
identify-then-execute controller and a surgical information-per-action controller.

### Light failure instrumentation (1 d, included)

Classify failures by game, multi-label with a confidence field, storing the evidence per label:

goal unknown · action semantics unknown · perception/parsing · hidden-state aliasing or memory · coordinate
unreachable · planning depth · exploration or probe selection · progress-signal misinterpretation ·
irreversible mistake · invalid output/interface · retrieval or context · reasoning inconsistency · latency
or budget.

This produces the **build order** for §11 — which lever to attack first, ranked by observed frequency on
real games. Goal-unknown versus planning-depth cannot be inferred from behaviour alone, so re-rate a small
sample blind later rather than treating the first pass as causal.

### Submit the reproduced baseline

Establishes the leaderboard reference every later change is measured against. **It does not discharge the
Paper Prize submission requirement** — that submission must demonstrate the paper's approach, so a
reproduced baseline does not qualify a JEPA paper. `[verify]` the wording; §9 handles the consequence.

---

## 5. S2 — Two minimal causal families

**3.5 days.** Small, exhaustively testable, ARC-compatible conventions (same cell-value range, same
action-set structure, identical padding) so S4 needs no re-engineering.

**F1 — history-required aliasing.** Visually identical observations require different actions because of a
hidden switch, counter, or phase.

**F3 — sparse delayed causal memory.** A one-cell or one-object change with no short-term effect that
determines a later transition. This is the mechanism the feasibility analysis identifies as the central
risk for reconstruction-free prediction: the objective has almost no gradient pressure to preserve a bit
whose consequence lies outside the training horizon, while an exact target retains it structurally. F1
alone sits in the short-horizon regime where a latent predictor looks good, so **without F3 a positive
result is biased.**

*(F2 hypothesis-discrimination and F4 irreversible-diagnostic-choice are cut. They test
capability-as-science more than build-relevant viability.)*

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
relaid-out variants.

**The value criterion is evaluation-only.** If it trains a value head, S3 becomes supervised action ranking
rather than an objective comparison.

---

## 6. S3 — Objective screening

**5 days. Two paired seeds** — adequate for a build decision, explicitly not for a claim. Common
grid/patch encoder. Hybrid entity/region architecture deferred.

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
5. What is A's inference cost per candidate against S1's measured per-action budget?

---

## 7. S4 — ARC advisor test

**2.5 days.** The only measurement that can retain or kill JEPA on operational grounds.

**Primary:** train each objective on the same ARC replay training games, evaluate on **held-out games**
with identical frozen advisor interfaces. Readouts: candidate pruning quality · no-op avoidance ·
changed-region prediction · representation stability across games · latency per candidate.

**Plus a small closed-loop run** on two or three development games with the model as advisor only, against
the S1 baseline. Offline probes cannot establish control utility, and control utility is the retention
criterion.

**Do not treat the human's next action as ground-truth action quality** — that is imitation, not planning
utility. Stratify any action ranking by the replay action's observed outcome (terminal ·
persistent-progress · informative change · reversible change · no-op).

**Standing caveat:** public games are materially easier than hidden ones and public results are not
evidence of hidden generalization — 13.33% public against 7.78% semi-private for the frontier reference.

---

## 8. S5 — Decision audit

**1 day. Stop implementing.** Record four axes:

| Axis | Content |
|---|---|
| **B — baseline readiness** | accepted submission · hidden score · latency · reliability · gap to competitive |
| **M — mechanism evidence** | history effect · rollout effect · objective ranking · F3 retention · collapse frequency |
| **U — advisor utility** | held-out ARC readouts · closed-loop advisor delta over baseline · latency cost |
| **C — feasibility** | remaining calendar · integration complexity · remaining compute |

Cases that require all four and cannot be read from a 2×2: strong synthetic mechanism with weak ARC
utility · strong baseline with unresolvable licensing · weak public score with nonzero hidden score · JEPA
equivalent to reconstruction but materially faster · JEPA strong only with exact auxiliaries, meaning the
auxiliaries carry the result.

---

## 9. The paper as a continuous by-product

A prize-quality paper cannot begin after the score route is declared capped. Deferring it to September
forecloses it. So from day one, at low marginal cost:

- hypotheses and related work written now, not later;
- methods sections written alongside implementation, while the details are fresh;
- figures generated by script from logged results, never hand-assembled;
- **every submission linked to the ablation it represents** — this is what turns routine iteration into a
  component ablation table for free;
- negative results logged immediately, with the configuration that produced them;
- the Paper Prize submission requirement (§4) satisfied by keeping one method-bearing submission path warm,
  not by building it in the last fortnight.

This does not raise Paper-Prize odds much on its own. It preserves the *option*, which deferral destroys.

---

## 10. Pre-register before starting

Into `gate_manifest.yaml`, numbers filled, before the corresponding step:

- **S1:** frozen baseline specification · viability thresholds · operational definitions for every failure
  category · the blind re-rate sampling rule.
- **S2:** the value/distance-to-goal criterion per family · the three-ceiling margins validating F1 · F3's
  delay length and bit sparsity.
- **S3:** named primary metric and threshold for each of the five screening questions · `T_v`, `T_r` · the
  rescue recipe's fixed coefficients · the evaluator-doing-the-work criterion.
- **S4:** the retention threshold — what advisor improvement, at what latency cost, keeps JEPA in the agent.
- **S5:** the B/M/U/C pattern mapping to each branch in §11.

---

## 11. After Aug 22 — freeze and build

**~8.4 weeks to feature freeze.** Freeze the competition architecture immediately and build, ordered by
S1's failure-frequency ranking. The candidate set, from
[`arc-agi-3-agent-architecture.md`](arc-agi-3-agent-architecture.md): goal induction over terminal
transitions · object/delta modelling · active probing · ACTION6 candidate recall · context-conditioned
archive with node splitting · verified search · belief ledger.

Submit regularly. Every submission is an ablation entry per §9.

**Corrected 2026-07-25:** the quota is **1 submission per day, 2 final submissions** — not 5/day, as this
section previously stated (source: Kaggle competition rules, checked 2026-07-25). This changes the
iteration argument rather than merely a number. Roughly 59 submissions exist between Aug 22 and the Oct 18
freeze, a rejected one cannot be retried until the next calendar day, and there is no room for a
submit-and-see loop. Iteration still produces the score, but each submission must be *chosen*, which makes
the §9 rule — every submission linked to the ablation it represents — the mechanism that keeps a scarce
resource informative rather than a bookkeeping nicety.

**JEPA retention gate.** It stays in the agent only if S4's advisor test shows improvement at acceptable
latency, re-measured after integration. Otherwise the encoder is retained for retrieval only, or dropped.

Reserve the final ~3 weeks for tuning rather than construction.

---

## 12. Confirmatory science, later

Whatever contrast survives integration gets proper treatment when the competition work is done or the score
route is capped: three-plus seeds, more task families, the entity-factorization factor, matched interfaces
throughout, ARC-trained held-out evaluation, and the full control set from
[`arc-agi-3-jepa-feasibility-analysis.md`](arc-agi-3-jepa-feasibility-analysis.md).

Screening evidence at two seeds and two families supports a build decision and nothing more. Any paper
rests on the confirmatory pass plus the ablation table accumulated from §9 — not on this sprint.
