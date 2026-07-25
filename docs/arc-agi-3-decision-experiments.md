# Stage 0 — Direction-Neutral Evidence Sprint

**Written 2026-07-25, rev. 2026-07-25 (final planning revision).** Supersedes the build orders in
[`arc-agi-3-agent-architecture.md`](arc-agi-3-agent-architecture.md) §9 and
[`arc-agi-3-execution-plan.md`](arc-agi-3-execution-plan.md) §13. It supersedes neither architecture
document — both are held as candidate designs, neither is committed.

**Stated utility ordering** (this governs §11, and it is not derived from the experiment): leaderboard
score is primary; the paper is the fallback if the score path proves capped. The "leaderboard placement is
a non-goal" line in the execution plan is superseded.

**What this commits to.** One sprint whose only deliverable is information, plus two Kaggle submissions.
Nothing else — not the agent architecture, not the confirmatory study, not continuing the project.

**Budget.** 40–50 h/week solo. Estimates in *focused* working days (~5/week after the clocked-to-focused
discount).

---

## 1. Schedule — two options, consequences stated

The corrected protocol is **~33 focused days ≈ 6.7 weeks**. That does not fit a Sept 5 stop. Choose
deliberately:

### Option A — full protocol, hard stop **Sept 12** *(recommended)*

Runs everything below. Leaves **~5.3 weeks** to the Oct 18 feature freeze.

- *Leaderboard-first remains viable* — the reproduced baseline is already submitted and working, so the
  remaining time goes to improvement rather than construction.
- *Paper-first becomes tight.* ~1.5–2 weeks are needed for a method-bearing submission (§4), leaving
  ~3.3–3.8 weeks for study and writing. Realistically that is **a preprint, not a Paper-Prize-competitive
  submission.**

### Option B — reduced protocol, hard stop **Sept 5**

Cut F3 and E5's ARC-trained evaluation. ~26 days. Leaves ~6.3 weeks, which both branches can absorb — but
decision quality drops materially, because F3 tests the mechanism most likely to determine whether the
objective works here and the ARC-trained evaluation is the only commensurable utility measurement.

**Note.** Independent estimates put completion of even the *shorter* protocol by Sept 5 at roughly 40–55%.
Option B may in practice be Option A with a worse framework. Recommend A.

| Experiment | Days |
|---|---:|
| E0 — starter submission, day one | 0.5 |
| E1 — frozen baseline reproduction, harness, instrumentation | 8 |
| E2 — reproduced-baseline submission | 1 |
| E3 — three micro-families with full generator interface | 7 |
| E4 — narrowed comparison: 4 primary arms × 3 seeds | 10 |
| E5 — ARC evaluation (primary: ARC-trained; secondary: zero-shot) | 5 |
| E6 — decision audit | 2 |
| **Total** | **33.5** |

**Verify before relying on any date:** Nov 2 final submission and Nov 8 paper deadline are on the public
page; the Oct 26 entry/team-merge date comes from project notes and is not displayed there. Also confirm
competition-mode constraints — level resets only, one environment creation per game, hidden in-flight
scorecards — since the second of those materially constrains exploration strategy.

---

## 2. The validity problem this version fixes

The two decision axes were not commensurate. "Baseline strong" was inferred from a real agent under hidden
Kaggle evaluation; "JEPA strong" from two synthetic families and an offline probe. A positive result would
have meant *the model learned a mechanism in toys*, not *this is a promising ARC component* — while the
decision table treated them as equally operational.

Four changes close the gap: matched information across arms (§6), a mandatory exact-delta comparator (§6),
a sparse-delayed-causal-bit family (§5), and ARC-trained held-out evaluation as the primary utility
readout rather than synthetic zero-shot transfer (§7).

---

## 3. E0 — Starter submission, day one

**0.5 focused days, first 24–48 hours.** Submit the untouched or minimally modified official starter.

Kaggle performs both a validation run and a hidden competition rerun, and a substantial fraction of failed
submissions surface no traceable notebook error. Proving the external execution path before building
anything is the cheapest risk reduction available in the whole project.

---

## 4. E1–E2 — Baseline reference point and second submission

**E1: 8 focused days. E2: 1 day.**

### Freeze the reference before starting

"A strong public agent, or the official template" describes two wildly different reference points, and the
failure mode is concrete: the hard reproduction proves painful, you fall back to the template, and E1 is
marked complete without answering its question. Before any work, freeze in writing:

repository URL and commit · exact model and weights · license interpretation against the CC0/MIT-0 release
requirement · quantization · accelerator · expected public behaviour · known score or reproduction target ·
permitted deviations.

The question E1 answers is: **how far are we from a competitive working baseline, and which failures look
improvable?** A template validates packaging but cannot answer it.

**Measure:** hardware fit · real per-action latency under the actual batching pattern · legal-action
reliability · public-game progress against the reproduction target · **reset and action accounting** ·
packaging and offline bundling.

**The reset experiment** gates nothing but configures everything: does a level reset preserve knowledge,
and does the scored action count accumulate or restart? It selects between an aggressive
identify-then-execute controller and a surgical information-per-action controller.

### Failure instrumentation (+1 d, included)

Categories: goal unknown · action semantics unknown · **perception / state parsing** · **hidden-state
aliasing or memory failure** · coordinate unreachable · planning depth · **exploration or intervention
selection** · **progress-signal misinterpretation** · irreversible mistake · **invalid output / interface
failure** · **retrieval or context failure** · **reasoning inconsistency** · latency / budget.

**Method, not just labels.** The game is the primary unit. Multi-label with a confidence field. Store the
evidence for each label. **Independently re-rate a sample later without seeing the original label** —
goal-unknown versus planning-depth cannot be reliably inferred from behaviour alone, and the re-rate is
what makes the ranking usable rather than anecdotal.

### E2 — submit the reproduced baseline

Establishes the leaderboard reference every later comparison is measured against.

**It does not discharge the Paper Prize submission requirement.** The submission must demonstrate the
approach described in the paper, so a reproduced baseline does not qualify a JEPA paper. `[verify]` the
wording; plan against the conservative reading — **paper-first requires a later method-bearing submission
even if it scores poorly**, budgeted in §11.

---

## 5. E3 — Three causal micro-families

**7 focused days.** Small, exhaustively testable, ARC-compatible. Not an ARC simulator.

**F1 — history-required aliasing.** Visually identical observations require different actions because of a
hidden switch, counter, or phase. Tests whether history-conditioned belief is *necessary* and *learnable*.

**F2 — hypothesis discrimination.** Several mechanics explain the early observations but diverge under one
diagnostic action.

**F3 — sparse delayed causal memory.** *(New, and the most important addition.)* A one-cell or
one-object change has no short-term effect but determines a later transition. This is the mechanism the
feasibility analysis identifies as the central architectural risk for reconstruction-free prediction: the
objective has almost no gradient pressure to preserve a bit whose consequence lies outside the training
horizon, while an exact target retains it structurally. F1 and F2 both sit in the short-horizon regime
where a latent predictor looks good, so **without F3 a positive result is biased.**

*(F4 — irreversible diagnostic choice — is desirable and cut for budget.)*

### Required generator interface

Successors alone are insufficient: ranking regret needs a ranking criterion, or a model can predict every
successor perfectly while the evaluator has no principled ordering. Each state exposes:

legal action set · **exact successor for every legal action** (free here, one scored action each on ARC —
this is what makes E4's central measurement high-sample) · terminal/progress predicate · **immediate
action value or distance-to-goal** · diagnostic information gain where applicable · hidden mechanic state
and parameters · which state variables are causally relevant · recoloured and relaid-out variants.

**The value criterion is evaluation-only.** If it trains a value head, E4 becomes supervised action ranking
rather than a dynamics comparison.

**ARC-compatible conventions** — same cell-value range, same action-set structure, identical padding — so
E5's readouts are mechanically possible without re-engineering.

### Validity check, folded in

On F1, confirm an **oracle hidden-state** arm beats an observation-only arm. That validates the *task*.
Keep it strictly separate from the model contrast in §6 — conflating them is how a model failure gets
misfiled as an instrument failure.

---

## 6. E4 — Narrowed comparison

**10 focused days.** Four primary arms, **three fixed seeds each**, common grid/patch encoder. Hybrid
entity/region architecture deferred: if the objective has no signal, the representation interaction is
moot.

| Primary arm | Predictive target |
|---|---|
| 1 | history/action-conditioned **JEPA** (reconstruction-free latent) |
| 2 | matched history/action-conditioned **reconstructive** next-state predictor |
| 3 | matched history/action-conditioned **exact structured delta** |
| 4 | **no-dynamics** control — candidate ranking from encoder state and generators, zero rollout |

**Exact-delta is mandatory, not optional.** The decision question is not "is JEPA better than
reconstruction" but "is JEPA worth pursuing instead of the strongest compact exact alternative." Without
arm 3, a mediocre decoder in arm 2 produces a false JEPA-positive.

Cheaper mechanistic controls, one seed: observation-only JEPA (isolates the history effect) ·
affordance/no-op classifier · retrieval-only representation · oracle-successor ranking (ceiling).

**Three fixed seeds, not two-plus-a-conditional-third.** Selective third seeds oversample near-threshold
conditions while clear-looking results rest on two observations. Cost is recovered by cutting the primary
arm count from six to four.

### Matched information — the fix that makes question 3 interpretable

**Every primary arm receives identical observation history, actions, metadata, retrieval context, training
data, and data ordering. Only the predictive target differs.** If JEPA sees history and reconstruction sees
only the current observation, the comparison varies target *and* information, and is uninterpretable. The
cheaper controls must also have matched history access, or "JEPA beats affordance-only" merely restates
"history beats no history."

### Matched ranking interface

A latent predictor does not inherently assign value to successors; neither does a grid predictor. Some
downstream interface translates predictions into action values, and interface effects can swamp the
dynamics contrast — published results show terminal-cost changes alone moving a latent planner from 7% to
97% success. Therefore all arms share:

- the same candidate action set;
- the same downstream evaluator class and fitting budget;
- an **oracle-successor ranking ceiling**;
- the **no-dynamics control** (arm 4) as the floor;
- an explicit check that **the evaluator is not solving the task** — if arm 4 approaches the dynamics arms,
  the interface is doing the work and no dynamics conclusion is available.

### Collapse protocol — pre-registered, not discretionary

Restarting on breach until an arm succeeds biases the comparison, since reconstruction and exact-delta
cannot collapse and are never retried.

- **Trigger:** per-dimension variance below `T_v` **or** effective rank below `T_r`, both pre-registered.
- **Probe accuracy is diagnostic only, never an abort trigger** — aborting on it means aborting on the
  outcome being measured.
- **Rescue:** one recipe, fixed-coefficient variance/covariance regularization, coefficients pre-registered
  and untuned.
- **At most one remedial rerun** per arm–seed.
- **Collapse frequency is reported as a result** per arm — evidence about practical viability, not noise.

### Measurements and the ordered questions

Counterfactual action-ranking regret against the generator's value criterion · hidden-mechanic
identification · prediction after a diagnostic intervention · **F3 delayed-bit retention** · transfer to
recolouring and relayout · direct two-step accuracy **against true targets, not self-consistency** ·
inference cost per candidate.

1. Does history conditioning help? *(arm 1 vs. observation-only control)*
2. Does JEPA beat retrieval-only, affordance-only, and no-dynamics? *(if not, the objective is inert)*
3. Is it competitive with matched reconstruction **and** matched exact delta?
4. Does it hold a transfer, data-efficiency, or latency advantage the others lack?
5. Does it retain sparse delayed causal bits on F3?

**Scope discipline.** This measures identification *from provided interventions*, not active intervention
selection. Two-step prediction is horizon evidence, not composition of independently learned mechanics.

---

## 7. E5 — ARC evaluation

**5 focused days.** Two readouts, and the primary one changed.

### Primary — ARC-trained, held-out games

Train each objective family on the **same ARC replay training games**, evaluate on **entirely held-out
games**, with identical frozen probe/advisor interfaces. This is the only measurement in the sprint that is
commensurable with the baseline evidence, because both are then about ARC.

### Secondary — synthetic zero-shot compatibility probe

Frozen synthetic-trained encoder and predictor applied to ARC with no adaptation. **Label it an ARC
compatibility probe, not ecological validation** — failure admits too many explanations (nothing learned ·
interface mismatch · narrow synthetic visual distribution · semantics don't transfer · two/three families
insufficient as pretraining · encoder useful but predictor not) to be diagnostic on its own.

**No end-to-end ARC fine-tuning** — it would conflate representation transfer with adaptation capacity.

**Readouts:** no-op versus change · event classification · changed-cell or changed-region prediction ·
representation stability across games · inference latency against E1's measured budget.

**Do not treat the human's next action as ground-truth action quality** — that is imitation, not planning
utility. Stratify any action ranking by the replay action's observed outcome (terminal ·
persistent-progress · informative change · reversible change · no-op).

**A tiny closed-loop advisor comparison is required if E5 is to influence the leaderboard decision.**
Offline probes cannot establish control utility. If budget forces it out, E5 informs the paper axis only,
and that limitation is recorded in §8 rather than glossed.

**Standing caveat:** the official technical report warns public games are materially easier and public
results are not evidence of hidden generalization — 13.33% public against 7.78% semi-private for the
frontier reference. Every number here inherits that.

---

## 8. E6 — Decision audit

**2 focused days. Stop implementing.** Record four axes, not two:

| Axis | Content |
|---|---|
| **B — baseline readiness** | accepted submission · hidden score · latency · reliability · gap to competitive |
| **M — mechanism evidence** | history effect · target-family effect (incl. exact delta) · F3 retention · collapse frequency · data efficiency |
| **U — ARC utility** | held-out ARC-trained transfer · closed-loop advisor improvement, or its explicit absence |
| **C — execution feasibility** | remaining calendar · integration complexity · remaining compute |

The 2×2 in §11 is a *summary* of B and M+U. These cases require the four axes and cannot be read off it:

- strong synthetic mechanism, weak ARC utility;
- strong baseline but unresolvable licensing;
- weak public performance with nonzero hidden score;
- JEPA equivalent to reconstruction but materially faster;
- JEPA strong only with exact auxiliaries — meaning the auxiliaries, not the objective, carry the result.

---

## 9. Pre-register before starting

Into `gate_manifest.yaml`, numbers filled, before the corresponding experiment runs:

- **E1:** frozen baseline specification (§4) · viability thresholds · operational definitions for every
  failure category · the re-rate sampling rule.
- **E3:** the value/distance-to-goal criterion per family · the oracle-versus-observation margin
  validating F1 · F3's delay length and bit sparsity.
- **E4:** the named primary metric and threshold for each of the five ordered questions · collapse
  thresholds `T_v`, `T_r` · the rescue recipe's fixed coefficients · the evaluator-not-solving-the-task
  criterion.
- **E5:** which readout and which outcome stratum carries the headline number · whether the closed-loop
  advisor test is in scope.
- **E6:** the B/M/U/C pattern mapping to each conclusion in §11.

---

## 10. What not to build

Postponed: object/region compiler · goal-predicate grammar · coordinate-pruning system · belief ledger ·
program DSL · bespoke local executive · two-rate agent · multi-horizon JEPA heads · hybrid entity–grid
architectures · archive node splitting · test-time adaptation · multiple-successor predictors · the
confirmatory matrix at any size · any submission-optimized architecture.

Existing at the end: harness with deterministic logging · two submitted agents (starter, reproduced
baseline) · F1/F2/F3 with the full generator interface · a generic training loop · evaluation and latency
instrumentation.

---

## 11. Conclusions

| B baseline | M+U mechanism & utility | Interpretation |
|---|---|---|
| Strong | Strong | test the combined route |
| Strong | Weak | leaderboard-first |
| Weak | Strong | paper-first |
| Weak | Weak | pivot or stop |

Subject to the §8 exceptions, and read against the stated utility ordering: score primary, paper as
fallback when score is capped.

### Leaderboard-first
Build the score-oriented agent from the failure-category ranking. Retain JEPA components only if they pass
a retention gate. This branch absorbs a Sept 12 stop most comfortably — the baseline is already submitted,
so remaining time is improvement, not construction.

### Paper-first
Design the proper study: more families, three-plus seeds, entity-factorization factor added, ARC-trained
held-out evaluation. **Budget the method-bearing submission** — ~1.5–2 weeks of the remaining time, per §4.
Under Option A that leaves ~3.3–3.8 weeks for study and writing, which is a preprint rather than a
Paper-Prize-competitive entry. Note also that the rubric weights universality and progress-toward-85%
alongside accuracy, and a three-family synthetic result with a modest ARC probe scores weakly on both.

### Both
Means **both routes earn the next integration experiment** — not that improvement has been demonstrated.
The first work is the closed-loop advisor test, not an architecture commitment.

### Pivot or stop
A compact exact agent, a narrower representation paper, or stopping before investing the remaining months.
Legitimate, and the sprint is cheap precisely so that discovering it early is affordable.
