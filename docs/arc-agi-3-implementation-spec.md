# ARC-AGI-3 Deployed Agent — Binding Implementation Specification

**Version 1.2 (final), 2026-07-28 — binding.** Implementation plan for the deployed score-oriented
agent (Track B); this version closes the review cycle. Changes from v1.1: full belief-ledger
specification restored (§4.6); probe-selection baseline and retention rule (§7); step-5
envelope-mode call-reduction target with the formal-acceptance measurement point (§6.4, §13.1);
\(n_{causal}\) feasibility decision at R1 under the 17-game dev partition (§13.1); per-game
utilities normalized to [0,1] before pairing (§13.2). Changes from v1.0: metric orientation and
discordant-outcome handling repaired (§13.2);
paired-run evaluation-state contract (§6.6); causal utility label for the learned gate (§6.8);
pre-R1 autonomy envelope (§6.4); binding control portfolio (§7); verified-program specification
(§8); belief model specified to admission level (§11); public-game partition and leakage policy
(§13.5); statistics corrections throughout §13.

**Self-containment scope.** This document fully specifies the substrate, delegation layer, control
portfolio, verified programs, gates, estimators, and all binding numbers. The belief model (§11) is
specified to the level required for admission, evaluation, and retention decisions; internal
architecture choices within §11's constraints are left to implementation.

**Terminology.** "Executive" denotes the slow-loop reasoning component; whether it is a language
model is decided by gate D0 (§10), not by this document.

---

## 1. Objective and governing principle

Objective: ARC-AGI-3 score under the platform's runtime budget.

> Neural models propose; exact evidence falsifies; verified programs simulate; a control portfolio
> decides how much to trust each source. The executive is an exception handler, not the default
> policy; every invocation and every suppression is logged as a decision whose causal value must be
> estimated. **Executive disagreement is never treated as executive value: that the executive
> changed an action does not imply it improved the action.** Causal value estimates come only from
> branched outcomes and paired policy runs.

The deployed agent is: *a cheap autonomous agent that escalates selected ambiguities to the
executive, records the executive's claims as falsifiable predictions, and progressively learns which
escalations were worth their cost.*

### 1.1 Decision map and governance

**This document is normative. It is never amended implicitly by an experimental result.**

```
experiments produce evidence  →  decision register evaluates it
                              →  THIS document is amended  →  code implements the amendment
```

Evidence lives in
[`arc-agi-3-screening-experiments-and-results.md`](arc-agi-3-screening-experiments-and-results.md);
amendments are logged in [`README.md`](README.md)'s decision register. Where that document and this
one conflict, **this one governs until explicitly amended.** Only the decision and a pointer to its
evidence belong here — never the experimental narrative.

| Decision | Binding here | Evidence from | Output consumed |
|---|---|---|---|
| Executive viability | **D0** §10.1 | S1 measurements + a dedicated D0 run | model choice · per-action call budget |
| Reset posture | §4.1 — **resolved** | S1 reset experiment (R1, R2) | no online branching; counterfactuals offline only |
| Per-action budget | §2 | S1 latency table, re-measured at step 1 | candidate count × predictor passes |
| Cheap evaluator retention | §5 | R1 branched audits | ranker version · fallback to archive + guards |
| Invocation-gate operating point | §6, §13.1 | procedural τ sweep; public validation vetoes | τ, and the two selected operating points |
| Belief objective | **R0** §10.2, §11 | S2 → S3 | latent vs reconstructive vs exact delta |
| Belief-model production value | rung gates §11.2 | S4 advisor test | retain / drop rungs 1–5 |
| Goal model | **G0** §9 | G0-R / G0-A; Fork G-F | integrate recognizer and/or ranker, or defer |
| Final scope | §12.2 slack policy | S5 decision audit | build / defer / drop per component |

The screening document carries the inverse of this table at its §2.1: each sprint names which row it
feeds. An experiment that maps to no row is either infrastructure or should not be run.

---

## 2. The binding constraint

Working envelope: ~8 h wall-clock, ~10 actions/s, order 10⁴ scored actions → **≈ 2.9 s per action**
(re-measured in step 1). A 27–31B-class model on the target GPU generates tens of tokens/s per
stream; batching raises throughput, not per-request latency, so the per-action token budget for a
reasoning executive is on the order of a hundred tokens — the executive cannot run every action.

*Why this is architecture and not tuning:* a compact predictive model costs **milliseconds** per
forward pass — three orders of magnitude below an executive call. That gap is the only reason a fast
loop can exist at all, and the whole delegation layer (§§5–6) is built to exploit it. **Measured
confirmation, 2026-07-27:** the reference agent ran 25 games in parallel, 3806 actions in 7962 s, i.e.
**2.09 GPU-serialized seconds per action against the ~2.9 s budget — 73%** — while making one
executive call per action and doing nothing else. A strong published agent already sits near the
ceiling doing the cheapest possible version of this job.

**Two-rate control.** A slow loop (executive) runs on events. A fast loop (archive, cheap evaluator,
verified programs, portfolio, guards, gate) runs every action, its cost dominated by
(candidate count) × (predictor passes per candidate). The invocation gate (§6) and the control
portfolio (§7) are first-class components with their own instrumentation and retention rules.

---

## 3. Component tiers

Membership only; each component is defined in the section named beside it.

| Tier | Components |
|---|---|
| **1 — unconditional substrate** | harness and accounting §4.1 · branching primitive §4.2 · canonicalizer and delta compiler §4.3 · archive §4.4 · ACTION6 candidate system §4.5 · minimal hypothesis store §4.6 · executive I/O contract §4.7 · terminal-transition logging §4.8 · procedural suite, F1 and F3 §4.9 · public-game partition §13.5 |
| **2 — required delegation layer** | cheap action evaluator §5 · two-stage gate and autonomy envelope §§6.1, 6.4 · adaptive threshold controller §6.2 · shadow-mode instrumentation §6.5 · paired-run and branching estimators §6.6 · control portfolio §7 · full belief ledger §4.6 |
| **3 — gated enhancements** (internal order binding) | belief-model rungs 1–3 and R0 §§10.2, 11.2 → **verified partial programs §8** → rungs 4–5, each gated §11.2 · learned probe selection §7 · learned invocation gate §6.8 · goal families F4/F5, Fork G-F §9.6 · **G0 gate experiments §9** |
| **4 — speculative score multipliers** | goal-model **production integration** §9.7 · mechanism retrieval, rung 6 §11.2 · longer-horizon latent planning · hierarchical subgoals |

Tier 4 items are never dependencies of the production agent. Within Tier 3, verified programs precede
rungs 4–5: they offload the executive with less scientific uncertainty, and the slack policy (§12.2)
deletes rungs 4–5 while retaining programs — the calendar must not schedule the disposable item
first. G0's *experiments* are Tier 3 (they are measurements); only *integration* of a passing goal
model is Tier 4.

### 3.1 Build difficulty `[planning judgment; binding on nothing]`

Estimated build effort, **distinct from §3.2's data-acquisition scale** — a component can be trivial
to build and starved of data, or the reverse. 0–2 = a day or less, no open questions · 3–4 = large
but fully specified · 5–6 = an open design decision or a dependency that lands late · 7–8 =
correctness is not locally checkable, or output quality is itself a measured unknown. Per-component
reasoning: [`build-difficulty.md`](../notes/build-difficulty.md).

| Tier 1 | § | | Tier 2 | § | |
|---|---|---:|---|---|---:|
| Harness, accounting, latency table | 4.1 | 2 | Cheap action evaluator | 5 | **6** |
| Branching primitive | 4.2 | **7** | Two-stage gate + envelope | 6.1, 6.4 | 4 |
| Canonicalizer + delta compiler | 4.3 | 4 | Adaptive threshold controller | 6.2 | 3 |
| Archive | 4.4 | **7** | Shadow-mode instrumentation | 6.5 | 3 |
| ACTION6 candidate system | 4.5 | 5 | Paired-run + branching estimators | 6.6 | **6** |
| Minimal hypothesis store | 4.6 | 1 | Control portfolio | 7 | 4 |
| Executive I/O contract | 4.7 | 3 | Full belief ledger | 4.6 | 5 |
| Terminal-transition logging | 4.8 | 1 | | | |
| Procedural suite (F1, F3) | 4.9 | 6 | | | |
| Public-game partition | 13.5 | 1 *(blocked)* | | | |

| Tier 3 | § | | Tier 4 | § | |
|---|---|---:|---|---|---:|
| Belief rungs 1–3 + R0 | 10.2, 11.2 | **8** | Goal-model integration | 9.7 | 3 |
| Verified partial programs | 8 | 5 | Mechanism retrieval (rung 6) | 11.2 | 4 |
| Rungs 4–5, each gated | 11.2 | **6** | Longer-horizon latent planning | — | 8 *(sketch)* |
| Learned probe selection | 7 | 4 | Hierarchical subgoals | — | 8 *(sketch)* |
| Learned invocation gate | 6.8 | **6** | | | |
| Goal families F4/F5 (Fork G-F) | 9.6 | 5 / 0 | | | |
| G0 experiments (G0-R, G0-A) | 9 | **6** | | | |

Tier 3 and 4 ratings are conditional on gates that have not run, and the two Tier 4 entries marked
*sketch* have no specification section — those estimate a plausible cost, not a design, and cannot
be scheduled without a spec amendment first.

Five consequences for scheduling:

- **§§4.2 and 4.4 carry Tier 1's uncertainty and are one risk, not two.** §4.2's identity check reads
  the inferred context signature and history equivalence class that §4.4 produces, so they cannot be
  built strictly in sequence, and both fail *silently*.
- **Tier 2 has no 7 and is still the more fragile tier.** Five of its seven components cannot be
  validated until §4.9 exists — §13.1's \(\tau\) bounds and \(q_{hi}/q_{lo}\), §6.4's ECE clause,
  §6.6's paired runs, §6.3's acceptance region, §5's progress supervision.
- **The 1s are urgent for reasons unrelated to their size.** §4.8's data is unrecoverable if it
  starts late; §13.5 blocks four components behind an unregistered tolerance; §4.5 is what makes the
  19 of 25 public games exposing ACTION6 playable at all.
- **Tier 3's binding order runs opposite to its difficulty, deliberately.** rungs 1–3 + R0 (8) →
  verified programs (5) → rungs 4–5 (6): the slack policy deletes the rungs and retains programs, so
  the harder disposable item must not be scheduled first.
- **One measurement decides whether half of Tier 3 is fundable.** Learned probe selection, the
  learned invocation gate, exact-branch G0-A and rung-3 discrimination all draw on branched evidence,
  so R1's yield at W4 is their common evidence ceiling — not only the learned gate's.

### 3.2 Training-data readiness `[planning snapshot; not an admission threshold]`

The build is **not globally data-starved**. It has enough executed transitions for factual prediction
and representation learning. Its shared acquisition risk is narrower: labels requiring an
unexecuted alternative, a verified no-return result, or a real progress event. Counts below are
measured planning inputs; where the specification has no minimum, the table says so rather than
promoting a convenient count into a gate. Detailed artifact-by-artifact inventory:
[`training-data-master.md`](../notes/training-data-master.md).

Difficulty is acquisition difficulty on the same 0–8 scale used by that inventory: 0–2 = on disk or
one extraction pass; 3–4 = scheduled generation/logging; 5–6 = a new instrument; 7–8 = capped
interaction with uncertain yield.

| Artifact group | Needed | Available now | Difficulty | Build consequence |
|---|---|---|---:|---|
| **Click salience (§4.5)** | state, clicked coordinate and observed outcome; no minimum registered | **56,347** replay ACTION6 transitions before §13.5 partitioning | **2** | in hand; partition balance governs coverage |
| **Evaluator factual heads (§5)** | exact deltas, settled-frame comparisons and return evidence | ≈**701M** changed-cell labels; 8,945 replay no-ops; 5,065 demonstrated-reversible examples | **0–2** | sufficient; `P(persistent)` still needs one extraction pass |
| **Progress head + G0-R (§§5, 9)** | real terminal/progress transitions plus procedural positives; minimum positive count not registered | **1,614** replay + 49 agent terminals; an unconstrained 17/8 draw leaves 850–1,287 replay terminals | **4–5** | scarce real positives; synthetic prevalence must be registered and calibrated |
| **Belief model (§11)** | matched-history transitions and multi-step windows; the 100k-step S3 budget presents **51.2M transitions/run** | **180,144** replay + 12,475 agent transitions; procedural source not built yet | **2 for ARC; 4 for procedural** | ARC data is epoch-limited, not absent; S2 throughput and instance diversity gate the synthetic work |
| **Counterfactual consumers (§§4.5, 6.8, 7, 9.1, 11.2)** | verified outcomes for competing actions; only the learned gate has a numeric minimum: \(n_{causal}\ge800\) | **0** frozen \(Y_{useful}\) labels; replays contain 23,032 effective-action coordinate pairs but only **204** involving progress | **6 via local fork; 8 via R1–R3** | all require R1–R3 unless a separately declared local-fork dataset is approved; a yield shortfall weakens six artifacts at once |
| **Demonstrated irreversible (§5)** | verified absence of a return route within \(H_{rev}\); no minimum registered | **0** — replay non-return is `unknown`, never negative | **7** | must be actively searched via branching or a local fork |
| **Gate validation (§13)** | \(n_{val}\ge150\) stratified suppression checks and \(n_{causal}\ge800\) valid disagreement states | **0**; nominal disagreement ceiling 2,040 requires ≥39% end-to-end validity | **6–8** | explicitly allowed to be unfundable; fallbacks in §§5 and 6.8 remain load-bearing |
| **Verified programs (§8)** | \(N_{prog}\ge8\) held-out context-matched transitions per program | generated by ordinary play | **1** | no separate acquisition project |

**Interpretation.**

- Dense supervision is abundant, but it cannot substitute for rare label kinds. In particular,
  180k on-policy replays do not discharge a counterfactual requirement.
- S2's procedural suite feeds nine downstream artifacts in addition to screening. Its throughput,
  instance diversity, held-out-instance count and progress prevalence are therefore data-interface
  requirements, not generator tuning details.
- The hard-data rows share one failure mode. R1's measured branch yield should be read not only as a
  learned-gate feasibility result, but also as the available evidence ceiling for causal ACTION6
  recall, learned probe selection, exact-branch G0-A, rung-3 discrimination and irreversible search.
- A local fork of the public game sources can manufacture exact successors, but does not silently
  enter training: version fidelity, third-party/replay-derived-weight licensing and §13.5 leakage
  must be resolved first. Validation games remain quarantined.

---

## 4. Tier 1 — substrate

### 4.1 Harness, accounting, and reset posture

Deterministic replay · scored-action accounting · measured latency table (environment step,
evaluator forward pass, executive call under the real batching pattern) · derived per-action budget.

**Reset accounting** `[amended 2026-07-28 — RESET-CASE-2026-07-28]`**.** Measured `accumulates`,
\(r\) = 2.0357, `c_reset` = 1: wasted actions carry across resets **and** RESET is itself a scored
action. **Everything scores, so there is no online branching** — counterfactual data comes from
procedural environments, replay reconstruction and development runs exclusively, which is the posture
§13.1's dev-partition branching budget assumes. Every deployed probe costs score directly, which is
what selects the surgical information-per-action controller (§7).

**Scope, binding on reuse.** Measured on the **offline** competition environment files, *not*
competition mode — V5–V7's hidden-scorecard and one-`make()` restrictions are unexercised — and the
accounting rule rests on **one game** (tu93), single-game by design so the level weight cancels.
Cross-game generalisation is untested and must not be asserted. Step 1 retains the experiment as
**confirmation**, extended to at least one further game; a contradicting result reopens the register
entry rather than being absorbed into it.

### 4.2 Branching primitive

For target state \(s_t\): record the trajectory prefix · verify deterministic reconstruction by
replay · execute candidate \(a_i\) · record immediate and K-step outcome · reset · replay · **verify
reconstructed identity including context and relevant history class** (final-hash match alone is
insufficient; mismatch invalidates the branch) · execute \(a_j\) · compare under a fixed continuation
policy (§9.3).

**Cost model.** Per audited state \(C \approx d_{verify} + n_{cand}(d + K)\) plus resets, \(d\) = the
archive's **shortest known path from reset**, not historical depth; audit-state selection prefers
short verified reconstruction routes.

**Yield accounting (binding).** Budgets cap **attempted actions**. Log per branch: attempted / valid
/ invalidity reason (stochasticity, context mismatch, animation timing, reset behaviour, unavailable
prefix, projection change, action nondeterminism) / wasted actions / valid yield. Every sample-size
claim is conditional on achieved yield. Round R1 is the yield pilot; measured yield re-plans R2/R3
budgets (§13.6 classifies this as cost-side re-anchoring, done before loss data is inspected).

### 4.3 Canonicalizer and delta compiler

Canonicalizer preserves categorical cell values 0–15, frame dimensions and separation, explicit
padding, metadata and available-action masks; strips serialization noise so identical situations
hash identically. Delta compiler emits: changed-cell count and set · changed bounding boxes · colour
transitions · connected changed regions · translation/merge/split hypotheses · appeared/disappeared
regions · animation-vs-persistent classification (settled-frame comparison) · action-availability
changes · level/score markers. Multiview outputs (grid, image, ASCII, components under multiple
assumptions, motifs, relations) in parallel; object output is always "candidate region with
confidence," never "object."

### 4.4 Archive

**Immutable evidence layer** (append-only): canonical observation · full frame sequence · settled
frame · action + coordinate · metadata · exact delta · trajectory-prefix id · resulting observation ·
evaluator and executive predictions at execution time with realized error.

**Versioned interpretation projections:** context signatures · history equivalence assignments ·
node partitions · alias flags · contradiction sets. Node identity =
(observation hash, inferred context signature, history equivalence class); a hypothesis revision
creates a **new projection**, never rewrites evidence.

*Why identity is not the observation hash alone:* with a bare hash, an observation reached under two
different hidden states becomes **one node with two contradictory out-edges on the same action**. The
graph has recorded a contradiction it cannot represent, so it cannot act on it — it will keep planning
through that node as if the transition were reliable. Widening the key lets the two situations occupy
different nodes, which is what makes cycle detection, reversible return routes and contradiction
retrieval well-defined. The price is that two of the three key components are **inferred**, so node
identity is revisable — hence projections rather than mutation. A monotonic counter (step, level,
score) must never enter the key: it makes every node unique by construction, which makes cycles
undetectable and contradictions unrepresentable, defeating the fix.

**Single-active-projection rule.** The fast loop queries exactly one active projection; swaps occur
only at slow-loop events. **Swap is atomic: all projection-dependent caches, routes, reversibility
claims, frontier labels, cycle memberships, candidate subgoals, and program-applicability records
carry a projection version and are invalidated on mismatch.**

**Override rule.** A known transition overrides prediction only when observation, action, context,
and relevant history all match and no contradictory successor is on record. Divergent successors
from equal visible states: mark aliased, retrieve differentiating histories, propose a hidden-mode
variable, split the context signature in a new projection.

### 4.5 ACTION6 candidate system

4096 coordinate actions per step; ACTION6 available at reset in 19 of 25 public games (measured
2026-07-26). Generators: learned click salience (dev-partition replays only, §13.5) · component
centroids · boundaries and corners · recently changed cells · rare colours and shapes · symmetry
correspondences · uniform background probes · uncertainty hotspots · successful coordinate classes.
*Why the quota is mandatory rather than prudent:* a salience head trained on replays learns what
humans clicked. A hidden game requiring a coordinate class no human in the training set ever clicked
gets near-zero salience and becomes **unreachable** — not unlikely, unreachable, because the ranker
never sees it. Uniform background probes are deliberately uninformed and statistically independent of
the learned proposer for exactly this reason, and they cost slots from the candidate budget.
**Measured, 2026-07-27:** with no proposal mechanism, a click-only game produced **1 action in 16
minutes** against 59 for a keyboard game — coordinate games are not merely harder, they are unplayable
without §4.5. **Diversity quota mandatory.** Measured continuously at budgets top-1/3/6/unrestricted, with three
distinct recall metrics: **demonstrated-coordinate recall** (vs replay clicks — a replay coordinate
is demonstrated-useful, not necessarily uniquely required) · **useful-region recall** (where
equivalence classes of coordinates are known) · **causal useful-coordinate recall** (from branched
audits). Recall separates "proposal omitted the action" from "ranker misordered it"; no ranking or
planning result is interpretable without it.

### 4.6 Minimal hypothesis store and full ledger

**Minimal store (Tier 1, step 2):** `id · claim · scope · status ∈ {proposed, supported,
contradicted, retired} · supporting transition refs · contradicting transition refs`. Sufficient for
the executive I/O contract and contradiction logging.

**Full ledger (Tier 2, step 6)** extends each mechanics hypothesis with: preconditions · predicted
effect · evidence-based confidence · cheapest discriminating test · irreversible-risk estimate. It
adds **goal-hypothesis records** (predicate family, level scope, transferable parameters, graded
evidence, counterexamples, current executability) and an **unknowns section** — which action
semantics, object roles, and goal candidates remain unresolved, and which experiment separates
them; unknowns are what turn uncertainty into probe selection (§7). Executive decision calls
receive active hypotheses, relevant contradictions, unresolved goal candidates, and the current
intended test — never retired hypotheses or raw trajectory. **Retention:** the compression policy
must beat rolling context on progress-per-action with the same executive; the gate applies to the
policy, never to the store's existence.

### 4.7 Executive I/O contract

**Input packet** (never unrestricted raw history unless explicitly escalated): invocation reason ·
observation summary · exact last-action delta · relevant archive transitions · top candidates with
evaluator predictions · active mechanics and goal hypotheses · known contradictions · current
intended probe or plan · risk and return-route information · token/action budget.

**Output schema:**

```json
{
  "selected_action": {"type": "ACTION6", "x": 21, "y": 14},
  "decision_type": "probe",
  "target_hypothesis_ids": ["H17", "H22"],
  "expected_event": {"class": "region_toggle", "persistent": true,
                     "changed_region": [18, 12, 28, 16]},
  "expected_information": "distinguishes paired-toggle from independent-toggle",
  "risk": "low",
  "ledger_updates": [],
  "program_candidate": null,
  "replan_after": ["expected_event_missing", "contradictory_successor",
                   "irreversible_change", "plan_exhausted"]
}
```

**Post-execution verification** — expected event vs exact delta · persistence vs later observation ·
hypothesis discrimination vs evidence · predicted vs realized risk — written to the decision record
(§6.9): executive calibration as a logged quantity and a principled trigger for the next call.

**Call types.** *Decision calls* request an action. *Compression calls* (critic mode) compress
history into the ledger and return no action. Context pressure (§4.10) triggers compression calls
only. Costs and productivity reported separately by call type.

### 4.8 Terminal-transition logging

Every `(o_t, a_t, Δ_{t+1}, level advanced)` tuple is logged from step 1, unconditionally. Goal
**acquisition** is main-line (heuristic hypotheses + executive-structural reasoning from step 3);
learned goal induction is gated by G0 (§9).

### 4.9 Procedural suite

**Two families, generated rather than sampled.** **F1 — history-required aliasing:** visually
identical observations require different actions because of a hidden switch, counter or phase.
**F3 — sparse delayed causal memory:** a one-cell change with no short-term effect that determines a
later transition. F3 is not optional coverage. F1 alone sits in the short-horizon regime where a
latent predictor looks good, so an objective comparison run on F1 without F3 is biased in favour of
the latent arm — the failure §10.2 and §11.3's controls exist to detect.

**Why this is unconditional substrate and not an experiment fixture.** Every retention decision in §6
rests on procedural paired runs; \(\tau\) bounds and the controller's calibration quantiles are
defined against procedural held-out error (§13.1); §6.4's clause 3 needs ECE-verified calibration on
procedural held-out data; D0's capability thresholds and R0's invariance and hidden-mechanics
criteria are measured on it (§§10.1, 10.2); §9.4's splits require held-out procedural instances and
held-out goal parameters; and it is the only supervision source whose progress prevalence and
counterfactual labels are **design parameters** rather than whatever a corpus happens to contain
(§5). Absent or unfaithful, those decisions are not delayed — they are unmeasurable.

Because instances are generated, §13.5's leakage policy does not apply to them. That is precisely why
procedural evidence **retains** while public validation only **vetoes** (§§6.7, 13.5).

**Interface (binding).** Per instance the generator exposes:

- legal action set · **exact successor for every legal action** — the counterfactual supply §4.1
  leaves to this component · terminal / progress predicate;
- **immediate action value or distance-to-goal**, the ranking criterion. **Evaluation-only:** if it
  trains a value head, an objective comparison silently becomes supervised action ranking;
- hidden mechanic state and parameters, and which state variables are causally relevant — §10.2's
  hidden-mechanics recovery reads these;
- recoloured and relaid-out variants with **colour roles explicitly permuted**, since §10.2 requires
  invariance across permuted-role environments while requiring colour *sensitivity* within one;
- **ground-truth state IDs** — §6.6's Jensen–Shannon divergence needs a policy-independent key;
- **instance seed and environment random-stream control.** Whether common random numbers are
  supported is **declared per generator, never assumed** (§6.6, §14);
- **on-demand generation.** §13.1's insufficient-evidence rule extends procedural paired runs, which
  a fixed pre-generated set cannot serve.

**Observation fidelity.** Generated observations match the conventions measured across all 25 public
games (2026-07-26): 64×64 grids at reset · cell values 0–15, all sixteen occurring · **1–N frames per
observation** · 6–10 levels per instance · action availability fixed per instance, not per state
(per-state variation is permitted by the interface but not evidenced). **The frame-sequence
requirement is load-bearing three times over:** 71% of real observations are a single grid but the
mean is 2.86 and the maximum 404, so a single-grid generator emits a distribution the real
environment never produces; any encoder must consume 1–N frames or silently discard most of the
observation at exactly the steps where something changed; and F1's timestep must be defined against
this, because part of the history the aliasing test concerns lives *inside* one observation.

**Validity conditions.** A generator failing these produces uninterpretable results, not weak ones.

- **F1 carries three ceilings, not one:** observation-only · complete observable history with an
  oracle decoder · oracle hidden state. Required pattern: observation-only < history-oracle ≈
  hidden-state-oracle. If the history oracle sits far below the hidden-state oracle, the task is not
  learnably history-resolvable and model failure on it is expected rather than informative.
- Convention mismatches against the table above are **reported, never silently accepted**.

**Provenance and timing.** The suite is built in screening sprint S2 and inherited by the build
phase, not rebuilt. §12.1 lists no step for it because there is none — but step 1's D0 measures
capability on held-out procedural environments, so a working suite is a **step-1 precondition, not a
step-1 deliverable**. If S2 slips, D0 slips with it.

**Predeclared numbers: none yet** — the one component in Tier 1 with no registered constant, while
four downstream users depend on its scale.

| Quantity | Who needs it | Status |
|---|---|---|
| Generator throughput | S3 is compute-budgeted; below its compute-bound rate the screening runs become data-bound (derivation: `notes/screening-training-data.md`) | **not registered** |
| Held-out instance count | §9.4's splits · §13.1's \(q_{hi}, q_{lo}\) · §6.4 clause 3's ECE | **not registered** |
| Progress-event prevalence | §5's progress head — the whole point of a generated source is that this is settable | **not registered**; §3.2 requires it registered *and* calibrated |
| Instance diversity per family | §9.4's held-out-parameter splits · §11's transfer claims | **not registered** |

§13.1's *20 instances × 3 seeds per condition per \(\tau\) grid point* is a floor for the paired-run
use only and is **not** a suite size. All four go into `gate_manifest.yaml` before the work that
consumes them, per the pre-registration rule — not backfilled from whatever the generator turns out
to produce.

### 4.10 Definitions

**Context pressure:** serialized input packet exceeds \(B_{ctx}\) tokens, or active ledger
hypotheses exceed \(N_h\). Triggers a **compression-only** executive call, not an action-selection
call.

**New persistent event class** (Stage-1 trigger): established only when all hold — (1) exact
deterministic delta signature does not match any ledger event class; (2) cluster novelty in a
**frozen** feature space; (3) the change persists in settled frames; (4) deduplication against
existing classes; (5) per-level cooldown — an unresolved candidate class cannot re-trigger within
the level. Prevents a noisy classifier from fragmenting events and repeatedly waking the executive.

---

## 5. Tier 2 — cheap action evaluator

A modest grid encoder scoring only the common candidate set of §4.5
`[amended 2026-07-28 — EVAL-SCOPE-2026-07-28]`.

**Scoring granularity — one encoder pass per step.** The encoder runs once on the observation and
emits a spatial map (Track A §5: output grid 8×8 or 16×16, token width 128–192, depth 4–6). Heads are
**dense over that map**: the coordinate head scores every location simultaneously — structurally a
segmentation head, consistent with Track A §14's factorization \(P(a,x,y) = P(a)P(x,y \mid a, z_t,
c_t)\) — and discrete-action heads read the pooled embedding with a small action embedding, batched
across ACTION1–5. **Evaluator cost is O(1) in candidate count.** §2's (candidate count) × (predictor
passes per candidate) product governs the **belief model's rollout** (§11), not this component. An
implementation that runs the encoder per candidate is **non-conforming**: ~40× cost at a typical
candidate budget, enough to consume the fast loop by itself.

**Encoders are shared across this component's own heads only — never with the belief model.** The
evaluator and the belief model (§11) have **separate encoders**, for measurement integrity rather
than modularity. The evaluator ships at step 4 (W3) trained on exact factual targets; the belief
model's objective is chosen at R0 (W5) by comparing latent, reconstructive and exact-delta arms. An
encoder pretrained on exact factual supervision would give **every arm exact supervision and confound
the comparison** — the precise failure §11.3 and S3's mandatory arm C exist to prevent, and the one
S5 names as "JEPA strong only with exact auxiliaries, meaning the auxiliaries carry the result."
Encoder weights never cross between the two. Sharing *inputs* — the canonicalizer, delta compiler and
candidate set — is required and unaffected.

Heads, with **frozen targets**:

- **P(no-op), P(visible change), P(persistent change)** — exact settled-frame labels.
- **P(progress event)** — predicts a **predeclared observable event class** (level/score marker or
  registered progress signature). Never long-term goal utility; never trained on executive or goal
  labels. This head is the source-paired baseline for G0-A (§9.1), so its target is frozen here.
- **Reversibility / irreversible risk — three-valued labels:** *demonstrated reversible* (return
  transition observed, or replay-verified return route, within the same level and \(\le H_{rev}\)
  actions) · *demonstrated irreversible* (verified no return route within horizon, or level/score
  state destroyed) · ***unknown*** — absence of return evidence is not evidence of reversibility and
  **is never trained as negative**. Class imbalance handled by reweighting; calibration reported.
- **Changed-region estimate** — exact delta labels.
- **Candidate value** — frozen formula
  \(U(a) = w_p P(\text{progress}) + w_c P(\text{persistent}) - w_n P(\text{no-op}) -
  w_r P(\text{irrev})\), weights in §13.1. Stage-4b weak labels (executive preferences) may
  additionally train this head only; they never enter the progress-event head.
- **Uncertainty / OOD.**

**Data sourcing.** Factual heads are data-rich (one transition = 4,096 dense cell labels; **180,144
valid replay transitions** and 12,475 logged agent transitions already exist). The
**progress-event head is the binding constraint**: measured prevalence is 0.90% in human replays
(1,614 terminal transitions) and 0.39% in reference-agent logs (49 terminals), and across all possible
17/8 draws the dev partition holds **850–1,287** replay positives before the §13.5 balance rule is
applied. **The partition is drawn under §13.5's multi-criterion balance constraint**
`[amended 2026-07-28 — PARTITION-2026-07-28]` — balancing terminal count alone leaves this
component's other heads unprotected.
Procedural F1/F3 is the only source whose progress prevalence and counterfactual labels are design
parameters, which makes the S2 generators primary supervision for this component and not only an
instrument for objective screening. Sizing: [`notes/evaluator-training-data.md`](../notes/evaluator-training-data.md).

**Supervision honesty — three stages:** **4a** factual heads on executed transitions + procedural
branches (exact, free labels) · **4b** weak candidate value (pointwise, biased, declared) ·
**post-R1 evaluator v2** — the first version with genuine common-candidate counterfactual
supervision. No unbiased-ranking claim before v2. Retention: beat archive nearest-neighbour and
random ranking on the common candidate set; failing that, the delegation layer degrades to
archive + guards, the gate pins to \(\tau_{max}\), and this is reported.

---

## 6. Tier 2 — invocation and suppression gate

### 6.1 Two stages

**Stage 1 — pre-emption (pre-proposal).** Fires on: level start or advance · plan exhaustion ·
first occurrence of a new persistent event class (§4.10) · **reset**, unconditionally — under §4.1's
accounting a reset is itself scored, so there are no routine ones.
Context pressure triggers a compression call, not a Stage-1 decision call. Stage-1 calls are **not
suppressible under the V1 gate** — which is not the same as productive: they may yield no usable
hypothesis, duplicate a cheap default, or be redundant once a level-family plan transfers. Stage-1
metrics: useful-plan rate · hypothesis-generation rate · actions saved per call · level-start
redundancy within a family · cost per subsequent progress event. Cached plans and family transfer
may later make Stage-1 suppressible; the metrics exist to detect when.

**Stage 2 — accept/escalate (post-proposal).** Runs after the portfolio (§7) yields a cheap
proposal.

**Forced escalations (bypass scoring):** observed delta contradicted the active prediction · an
active plan's `replan_after` fired.

**Hard safety vetoes (lexicographic, outside the score):** illegal action · unavailable per
metadata · **predicted irreversible risk > \(R_{max}\), or reversibility *unknown* with high
consequence, in either case with no verified return route → escalate.** The veto is not purchasable
by margin.

**Scalar acceptance score:**

\[
A_t = w_m m_t + w_a q_t - w_u u_t - w_n p^{noop}_t - w_r p^{risk}_t - w_c c_t,
\qquad \text{accept iff } A_t \ge \tau_t
\]

(\(m\) top-1/2 margin, \(q\) archive route quality, \(u\) uncertainty/OOD, \(c\) contradiction
count). Tightening is **increasing \(\tau_t\)**, always.

### 6.2 Adaptive threshold controller

**Fast term — dynamics error.** \(e_w\): fraction of last \(W\) autonomous actions whose exact delta
contradicted the evaluator (wrong persistence class or changed-region IoU below floor).
\(e_w > q_{hi}\) → raise \(\tau_t\); \(e_w < q_{lo}\) for a full window → lower, floored at
\(\tau_{V1}\).

**Slow term — decision-error correlates.** No-progress streak \(\ge N_{np}\) (see suspension rule
below) · `replan_after` failures in window above threshold. Either → raise \(\tau_t\).

**No-progress suspension.** The streak counter is suspended while executing an exact archive route
or a verified-program plan whose declared prediction includes delayed visible progress; those plans
are policed by their own `replan_after` conditions instead. Six quiet actions during a verified
setup sequence are not evidence of failure.

**Epistemic boundary (binding).** Dynamics error controls OOD recalibration; decision-error signals
are correlates; **neither measures suppression regret**. Causal regret comes only from branching and
paired runs.

**Mechanics:** \(\tau_t \in [\tau_{min}, \tau_{max}]\) · ≤ one adjustment per \(H\) autonomous
actions · condition must persist a full window · cold start: \(\tau = \tau_{max}\) at game start, no
relaxation before \(W\) autonomous actions · level advance: \(\tau \leftarrow \min(\tau +
\Delta_{lvl}, \tau_{max})\) · suppressed-then-irreversible-loss → snap to \(\tau_{max}\) for the
level.

### 6.3 Retention rules (three distinct components)

- **Deterministic gate (step 5):** must meet §13.1's absolute acceptance region vs always-call on
  procedural paired runs. This is the condition for "budget-credible."
- **Learned gate:** must meet the same absolute region **and** weakly dominate the deterministic
  gate's cost/loss frontier, with predeclared minimum improvement: ≥ 10% additional call reduction
  at non-inferior loss, or equal calls at strictly lower loss.
- **Adaptive controller:** vs fixed-\(\tau\) on procedural held-out games — improve the frontier or
  cut irreversible-suppression events at equal call rate.

### 6.4 Pre-R1 autonomy envelope `[binding until evaluator v2 ships]`

Before evaluator v2 exists, the step-5 gate acts on factual heads and weak value only. Until v2, an
autonomous (non-escalated) action is permitted **only when at least one holds**:

1. exact context-matched archive route;
2. verified replay of the same action class in matching context;
3. factual heads predict a safe, non-no-op outcome with \(P(\text{persistent non-no-op}) \ge 0.9\)
   under ECE-verified calibration on procedural held-out data;
4. the top candidate is invariant across all available weak rankers and baselines (factual-head
   ordering, archive-NN, weak value);
5. the action is a reversible low-risk probe (\(P(\text{reversible}) \ge 0.9\), risk
   \(< R_{max}/2\)).

Weak value alone never authorizes a high-risk or strategically committed action pre-v2. This is what
makes "budget-credible after step 5" believable.

**Step-5 numeric target.** "Budget-credible" at step 5 is a structural claim — the machinery exists,
is instrumented, and acts autonomously under this envelope. Its predeclared envelope-mode target is
**≥ 40% executive-call reduction** vs always-call on procedural paired runs (cost-side, §13.6): the
envelope's clauses are restrictive while the archive is thin, so the 70% figure of §13.1 is **not**
a step-5 requirement. The full acceptance region is formally evaluated at the step-7 operating
points, after evaluator v2 retires the envelope.

### 6.5 What shadow mode is, and is not

Development episodes run always-call while the full fast loop runs counterfactually, logging §6.9
each step. Shadow observes the executive action's outcome, **never the suppressed cheap action's
outcome**: it estimates invocation and intervention rates, action/hypothesis/plan disagreement, gate
calibration against executive disagreement, candidate overlap, and bootstrap signal. It **cannot**
estimate suppression loss. **Shadow disagreement oracle** (baseline): call exactly when the
executive action would differ — an upper bound on *predicting executive intervention*, not on
achievable policy value.

**Estimator hierarchy (binding):** (1) paired policy runs — end-to-end suppression loss; (2)
branching — per-decision causal regret, attribution of paired-run loss, sole basis for learned-gate
claims; (3) shadow — intervention supervision and calibration; (4) proxy labels and natural
revisitation — supporting evidence only.

### 6.6 Paired evaluation — frozen evaluation-state contract

Conditions: always-call · deterministic gate at operating \(\tau\) · candidate learned gate.
**State contract, mandatory for a run to count as paired:**

- fresh archive, ledger, goal posterior, caches, and adaptation memory per policy-instance
  replicate; no data sharing across arms;
- identical procedural generator instance and initial environment seed; identical environment random
  stream where the environment supports common random numbers;
- deterministic evaluator and gate; identical candidate-generator version and code version;
- executive decoding deterministic (temperature 0) — or, if stochasticity is retained, ≥ 3 paired
  executive seeds per replicate;
- identical action-tie-breaking rule.

**Dual budget matching:** primary at matched wall-clock (deployment question); attribution arm at
matched scored actions. Both reported.

**Measured:** primary progress endpoint (§13.2) · actions-to-completion · executive cost ·
irreversible failures · cumulative suppression loss · **state-distribution divergence over a
policy-independent key — Jensen–Shannon over canonical settled-observation hashes (procedural
ground-truth state IDs where available); projection-conditioned divergence only as a secondary
diagnostic after offline projection alignment**, since node IDs across policies need not share an
alphabet.

### 6.7 Frontier procedure

Sweep \(\tau\) over a 5–7 point grid on **procedural** paired runs; select two operating points
(conservative, target); **validate on the public validation partition (§13.5) as a veto-only
external-validity check** — the small public sample certifies nothing, but gross loss or discordant
completions beyond §13.2's tolerance trigger rollback to the conservative operating point.
Retention decisions rest on procedural evidence.

### 6.8 Learned gate — causal utility label

\(P(\text{intervention useful} \mid s, h, \hat a, u)\), bootstrapped on shadow + proxy, **claimed**
only against branched disagreement labels. **The label, frozen:** on a valid branched disagreement
(both branches executed from a verified reconstruction), \(Y_{useful} = 1\) iff the executive branch
**lexicographically dominates** the cheap branch:

1. avoids an irreversible loss the cheap branch incurs; else
2. reaches a terminal or progress event the cheap branch does not (within K); else
3. yields strictly more progress events within K; else
4. resolves strictly more active hypotheses — resolution verified by exact delta — at no greater
   realized risk and no fewer progress events.

Otherwise \(Y_{useful} = 0\); **ties are labeled not-useful** (equal value at executive cost is not
useful). Invalid branches are excluded and charged against yield. \(n_{causal}\) (§13.1) counts
valid labeled disagreement states. If yield cannot fund \(n_{causal}\), the learned gate ships as
uncalibrated ordering over the deterministic escalation queue, or not at all. Baselines: always-call
· deterministic-\(\tau\) · uncertainty-only · fixed-frequency (every 8th action) · shadow
disagreement oracle.

### 6.9 Per-action decision record (both modes)

```
portfolio source consulted · cheap proposed action · evaluator predictions + uncertainty ·
A_t terms and τ_t · gate stage · decision + reason code · veto/forced-escalation flags ·
envelope clause satisfied (pre-v2) · executive action if invoked or shadowed ·
changed action? hypothesis? plan? · observed exact delta · post-execution verification ·
progress within K · projection version · branch result if audited
```

---

## 7. Control portfolio `[binding]`

Arbitration of the action source, ordered by directness of evidence; the earliest admissible row
wins.

| # | Source | Admission condition | Gate interaction | Max chunk |
|---|---|---|---|---|
| 1 | **Exact archive route** | context-matched known path to a valuable state; no contradictory successor; passes risk guards | bypasses \(A_t\); hard vetoes still apply | 4 |
| 2 | **Verified program** | admitted program (§8) whose applicability predicate holds at current projection version; predicted path passes risk guards | bypasses \(A_t\); hard vetoes apply | 4, only if every step covered and path reversible |
| 3 | **Model search** | belief model passed rungs 3–4 for this context (R0 + rung gates); 2–4-step search under it | subject to \(A_t\) and envelope | 1 |
| 4 | **Discriminating probe** | active hypotheses disagree; a reversible low-consequence action separates them (ledger's cheapest test) | subject to \(A_t\) (probe clause of envelope) | 1 |
| 5 | **Evaluator direct action** | evaluator retention holds; envelope (pre-v2) or v2 confidence | subject to \(A_t\) | 1 |
| 6 | **Executive escalation** | any forced escalation, veto-triggered escalation, or \(A_t < \tau_t\) | is the escalation | 1 |

Execute one action by default; chunks only per the table. **After every action**, regardless of
source: exact delta vs prediction · event occurrence · contradiction detection · ledger and archive
update · program demotion check (§8). A source that mispredicts loses its bypass for the affected
scope until re-verified.

**Probe selection.** Deterministic v1 (row 4's admission mechanism) = the ledger's cheapest-test
field: the minimum-expected-cost action predicted to discriminate ≥ 2 active hypotheses, with
\(P(\text{reversible}) \ge 0.9\) and risk \(< R_{max}/2\). **Learned probe selection (Tier 3)** is
retained iff it beats random probing, novelty-based probing, and the deterministic cheapest-test
baseline on hypotheses-resolved-per-scored-action.

---

## 8. Verified partial programs `[full specification]`

Compile the **smallest useful verified fragment** — one action, one object class, one region, one
mode — never a complete simulator.

**Representations, one prediction interface:** (1) **typed rewrite-rule DSL first** — recolour ·
translate · copy · delete · create · toggle · swap · increment counter · activate region ·
transform-all-matching; reliable, fast to search; (2) **sandboxed Python optional** — pure function
of compiled state, resource-limited, no I/O, for global patterns the DSL cannot express.

**Program record:** applicability predicate + declared scope (game / level family / region / object
class / mode) · predicted delta and event · supporting transitions · known counterexamples ·
**projection version** (invalidated on swap, §4.4) · unsupported-case semantics: outside its
predicate a program returns *not applicable* — it never guesses.

**Admission (all required; fitting-set consistency alone is insufficient):** consistent with its
fitting transitions · predicts \(\ge N_{prog}\) held-out recent context-matched transitions with
exact-delta match · no counterexample in declared scope · simplicity or coverage benefit over
existing rules · survives exact replay where replay is possible.

**Demotion:** a single in-scope contradiction demotes the program to hypothesis status immediately;
re-admission requires the full test. Programs **never silently enter model-only evaluation** (§11.3)
— archive edges, programs, and simulator branches are all excluded from that regime.

**Retention:** reduces wasted actions or search cost relative to the step-5 agent, measured in
paired comparison. Executive may *propose* programs (`program_candidate` in §4.7); only exact
verification admits them.

---

## 9. Goal induction and gate G0

### 9.1 Two tasks

*Why the learnable object is a transition and not a winning state:* a completing action typically
returns the **next level's frame**, so a state satisfying the goal **may never be directly observed**.
There is no frame in the entire history depicting a solved board, so a state classifier has no positive
examples. Both tasks below are therefore defined over transitions. Observed failure of the alternative,
S1-d episode `sc25`: the agent reached the state its own goal model called the solution and the level
did not complete — *"Current state matches the purple dot pattern (cross). But level doesn't
complete."* Execution was correct; the target was the wrong **type** of object.

**G0-R — post-outcome recognition.** \(G_R(h_t, o_t, a_t, \Delta_{t+1})\): terminal /
progress-bearing classification of observed transitions · prerequisite and partial-progress grading
· goal-family classification where synthetic truth exists · ledger goal-hypothesis pruning. Runs
independently of any transition model, parallel with R0.

**G0-A — pre-action utility.** \(G_A(h_t, o_t, a)\) or \(G_A(h_t, o_t, a, \widehat{\Delta}^{(a)})\)
with the **outcome source declared**: exact branch · cheap-evaluator prediction · belief-model
prediction · verified program. Reported separately per source; **credit per source = improvement
over that source's frozen progress-event-head ranking without \(G_A\)** (§5 freezes that head's
target precisely so this baseline cannot move).

### 9.2 Terminal-action recall decomposition (binding)

(1) proposal recall — completing action in the candidate set? (2) conditional ranking recall — top-3
given present? (3) end-to-end. Without the split, G0 can fail on ACTION6 proposal rather than goal
ranking.

### 9.3 Deployment adaptation protocol

Backbone frozen. Each observed completion updates: per-family goal posterior over predicate classes
· prototype/retrieval memory of terminal transitions · ledger goal parameters (counts, regions,
orderings) · optional in-context examples for the executive. No gradient updates at deployment. The
{1, 2, 4, 8}-completion grid runs under exactly this protocol, sequentially.

### 9.4 Data, splits, baselines

Logged terminal transitions from dev-partition replays + procedural instances (validation-partition
replays excluded, §13.5). Splits: held-out levels within games · held-out trajectories · held-out
procedural instances · held-out goal parameters · held-out family per Fork G-F. Never random
transition splits. Baselines: generic persistent-change heuristic · rare-event heuristic · executive
structural score · terminal-transition NN · event-count / cumulative-change features · random
ranking over visited states.

### 9.5 Criteria

Margin rule, all offline criteria: beat the relevant baseline by
\(\max\!\big(10\text{pp}, \min(20\text{pp}, 2\sigma_{baseline})\big)\), \(\sigma\) estimated from
\(\ge 4\) baseline seeds (fewer → 10pp floor only), at ≤ 4 completions under §9.3. **At 1
completion:** non-inferiority with tolerance — regression ≤ 3pp and one-sided 90% lower confidence
bound of the paired improvement > −5pp.

- **G0-R:** margin rule on progress-state AUROC and on hypothesis-pruning at matched false-prune
  rate.
- **G0-A offline:** margin rule on conditional ranking recall, per outcome source, vs the
  source-paired baseline.
- **G0-A online (procedural agent-in-loop):** actions-to-first-completion improves ≥ 5% over the
  heuristic goal baseline, **or** non-inferior with ≥ 20% lower executive cost. Ties do not ship.

### 9.6 Fork G-F — goal families

Two sprint families (F1, F3) make hold-one-out train on n=1 — noise. Decided Aug 22:
**Branch A** (≥ 5 build-days slack): build **F4 ordered-event-program** and **F5
cumulative-counter** families (2–3 days each, generator + verifier + ground-truth parameters);
family transfer = train 3, hold out 1, rotate. **Branch B:** family transfer declared untestable and
reported as such; criterion weakens to held-out parameters within family; no cross-family claim
anywhere.

### 9.7 Scope of the commitment

**The G0 model is the only committed learned-goal artifact.** Decision table: G0-R and G0-A pass →
integrate recognizer + ranker (per passing outcome sources) · G0-R only → integrate recognizer
(pruning and labeling pay on their own); ranking stays heuristic · neither → heuristic + executive
structural goal system; terminal logging continues. Executable predicate induction remains
unscheduled Tier 4.

---

## 10. Gates D0 and R0

### 10.1 D0 — executive viability

License compatible with CC0/MIT-0 release and offline sandboxed bundling — resolved before any
benchmarking. Fit and throughput on the target GPU at intended quantization with compact models
resident → per-action token budget and affordable call frequency. **Capability on held-out
procedural environments, with numeric thresholds `[predeclared]`:** valid structured action output
≥ 99% · delta description: correct changed-region identification ≥ 90% on the trial set · no-op /
reversible / persistent classification ≥ 90% balanced accuracy · representation robustness measured
across image, ASCII, coordinate list (best is chosen, not assumed) · first-level progress: ≥ 1
progress event on ≥ 60% of unseen tutorial levels within 200 actions · guard adherence: zero illegal
actions on the trial set. Thresholds are frozen before results are inspected. On failure: the slow
loop is explicit hypothesis search plus evaluator probe selection; two-rate control does not depend
on an LLM.

### 10.2 R0 — belief-model viability

Criteria: no representational collapse (per-dimension variance, effective rank, whitened probe
accuracy for position/switch/inventory — a **training-time tripwire**) · sensitivity to causally
relevant state · **scoped nuisance invariance: invariance is required across synthetic environments
where colour roles are explicitly permuted; within a single game, colours are causally stable and
sensitivity to them is required, not penalized** · hidden-mechanics recovery on synthetic ground
truth · **beats the non-dynamics controls on held-out counterfactual ranking** (load-bearing). D0
and R0 are independent by construction.

---

## 11. Belief model — specification to admission level

### 11.1 State and training targets

\(z_t = (z^{ent}, z^{rel}, z^{reg}, z^{grid\text{-}res}, z^{mech}, z^{belief})\): entity and
relation slots from compiler candidate parses carried **with confidence**; a load-bearing grid
residual (protects against segmentation error; covers non-object mechanics — patterns, counters,
phase); history-conditioned mechanics context.

**Training:** candidate-conditioned forward model \(f(z_t, h_t, a_t)\) on the agent's own logged
transitions (labels free), dev-partition human replays, and the procedural suite. **Direct
multi-horizon heads at 1, 2, and 4 steps, with composition-consistency loss**
\(\lVert P_1 \circ P_1 - P_2 \rVert\) and its 4-step extension — retained as a training loss
regardless of which rungs ship, because it separates a compositional transition model from a lookup
table. The reconstruction-free latent objective and the exact auxiliaries are trained as
**explicitly separate conditions**: if heavy exact supervision turns the system into a supervised
dynamics model with a JEPA-shaped loss, that must be a measured finding (detached-auxiliary
control), not a hidden one. 8-step rollout is never a production dependency.

### 11.2 Capability ladder — production use, cost, retention

| Rung | Capability | Fast-loop use | Cost/action | Retained iff it beats |
|---|---|---|---|---|
| 1 | Predictive sufficiency | precondition | 1 encoder pass | whitened probes at chance |
| 2 | System identification | fewer probes to pin mechanics | 1 pass | explicit enumeration + ledger probe selection |
| 3 | Counterfactual discrimination | candidate pruning, probe choice, no-op avoidance | 1 pass × candidates | random, affordance-only, archive-NN |
| 4 | 2/4-step composition | look ahead without waking executive | k × predictor passes | iterated-copy and 1-step-only |
| 5 | Relational transfer | levels 2..N | — | held-out layout + colour-permutation eval |
| 6 | Mechanism retrieval | **Tier 4** — better executive prompts | ANN lookup | exact-hash + frozen-feature retrieval |

Auxiliary outputs consumed by the fast loop: P(persistent change) · changed region · event class ·
P(reversible) · P(no-op) · novelty · coordinate salience · uncertainty/OOD (a gate input).

### 11.3 Evaluation regimes and controls (always run, both reported)

**Model-only:** no exact transition result may be consulted for an unexecuted action — no archive
edge, no verified program, no simulator branch; supports attribution. **Hybrid:** archive and
programs may override; measures the deployed agent. Controls: retrieval-only · affordance-only ·
no-dynamics policy · archive nearest-neighbour · exact/reconstructive dynamics on the same backbone
· detached-auxiliary · iterated-copy. If affordance-only matches the full model, the architecture
simplifies — a result, not a failure.

**Compute constraint:** the model must fit resident alongside the executive on the target GPU; its
(candidates × passes) product fits the measured fast-loop budget or the candidate governor cuts
candidates first.

---

## 12. Build order

### 12.1 Steps

Dependency order primary; calendar is feasibility (W1 = Aug 24–30; W8 ends Oct 16; submission
Oct 18).

| # | Contents | Cal. |
|---|---|---|
| 1 | Harness, replay, accounting, latency table; D0; reset-accounting **confirmation** (§4.1, second game); branching primitive + yield instrumentation; terminal-transition logging; **public-game partition frozen (§13.5)** | W1 |
| 2 | Canonicalizer, compiler, archive (evidence, projections, atomic single-active), ACTION6 coverage + three recall metrics; minimal hypothesis store | W1–2 |
| 3 | Direct executive policy with full I/O contract, archive retrieval, legality guards → **functionally submittable agent** | W2 |
| 4 | Evaluator 4a (factual heads incl. three-valued reversibility) and 4b (weak value) | W3 |
| 5 | Two-stage gate (\(A_t\), vetoes, forced escalations), **pre-R1 autonomy envelope**, adaptive \(\tau\) controller, portfolio arbitration v1 (rows 1, 5, 6), shadow instrumentation, suppression metrics live → **budget-credible two-rate agent** | W3 |
| 6 | Full ledger, contradiction-triggered projection splitting, probes (portfolio row 4); **R1** on dev partition (yield pilot; continuation v1 frozen first) → evaluator v2, gate calibration; **envelope retired on v2 admission** | W4 |
| 7 | **W4:** R1 analysis, evaluator v2, deterministic-gate calibration, preliminary procedural \(\tau\) sweep. **W5:** complete sweep, select two operating points; belief rungs 1–3 + **R0**. G0-R runs opportunistically and may not delay R0 or gate work | W4–5 |
| 8 | **Verified partial programs (§8)**; portfolio rows 1–2 fully armed | W5–6 |
| 9 | Rungs 4–5, each gated; portfolio row 3; **R2** on dev partition (continuation v2 = evaluator-only, for ranker attribution; plus a small program-aware continuation audit, 5 states/game, labeled separately) | W6 |
| 10 | **G0-A** with declared outcome sources; G0 decision; integration per §9.7. **Public-validation paired runs at the two operating points (veto-only, §6.7)** | W7 |
| 11 | Ablation of every component against the **step-5 agent**, both regimes; **R3** (continuation v3 = final fast-loop policy); removal; freeze thin fallback | W8 |

> A functionally submittable agent exists after step 3. A budget-credible two-rate agent exists
> after step 5 — under the pre-R1 autonomy envelope until evaluator v2 — and no component after
> step 5 is on the critical path for a runtime-viable submission. The ablation baseline is the
> step-5 agent.
>
> The calendar guarantees steps 1–5. Tier-3 maturation by Oct 18 is best-effort, governed by the
> component gates and the slack policy: this is a score-first implementation plan with gated
> research work, designed to degrade by deleting components — never by compressing the submission.

### 12.2 Slack policy `[predeclared]`

Any slip ≥ 1 week deletes, in order: Tier-4 production integration (G0 gate experiments continue
only where opportunistically cheap; G0-R diagnostic always continues — it is analysis of logged
data) → G0-A evaluation → rungs 4–5 → Fork G-F Branch A (falls to Branch B) → R3 → public
validation reduced to one operating point. **Verified programs are never deleted before rungs 4–5.**
Steps 1–5 are never compressed; they are the submission.

---

## 13. Statistics and predeclared numbers

### 13.1 Gate and evaluation constants

| Quantity | Value |
|---|---|
| Acceptance region (deterministic gate, procedural paired runs, vs always-call) | ≥ 70% executive-call reduction AND \(D_{progress}\) within tolerance (§13.2) AND discordant-completion veto passed (§13.2) AND irreversible non-inferiority (§13.3) |
| Learned-gate additional condition | weakly dominate deterministic frontier: ≥ 10% further call reduction at non-inferior loss, or equal calls at strictly lower loss |
| Insufficient-evidence rule | decide on point estimates; if the 90% interval on \(D_{progress}\) is wider than 2× tolerance, extend **procedural** paired runs before deciding — procedural evidence retains; public validation only vetoes |
| \(\tau\) bounds, steps | \([\tau_{min}, \tau_{max}]\) from procedural calibration; \(\Delta\tau\) = 15% of range; \(\Delta\tau_{relax}\) = 5%; \(\Delta_{lvl}\) = 25% |
| \(W\); \(H\) | 50 autonomous actions; ≥ 10 between adjustments |
| \(q_{hi}, q_{lo}\) | 90th / 50th percentile of procedural held-out calibration error |
| \(N_{np}\) | 6 consecutive actions (suspended per §6.2 during verified plans) |
| Envelope constants | confidence 0.9 (clauses 3, 5); risk cap \(R_{max}/2\) for probes |
| Value-head weights \(w_p, w_c, w_n, w_r\) | 1.0, 0.5, 0.5, 1.0 — frozen |
| \(B_{ctx}\); \(N_h\) | 2,000 tokens; 24 active hypotheses |
| \(H_{rev}\) | reversibility evidence horizon: same level, ≤ 30 actions |
| \(N_{prog}\) | ≥ 8 held-out context-matched transitions, exact-delta match |
| Paired runs — procedural | 20 instances × 3 seeds per condition per \(\tau\) grid point (5–7 points) |
| Paired runs — public validation | all 8 validation games × 2 seeds per condition, 2 operating points, veto-only |
| Branching budget | 24,000 attempted actions/game/round on the dev partition; valid-state targets 40 (disagreement, \(n=8, d \le 30, K=5\)) / 15 (ACTION6, \(n=20, d \le 15, K=1\)) / 10 (irreversible/OOD, \(n=4, d \le 30, K=5\)); 3 rounds |
| \(n_{causal}\) | ≥ 800 valid \(Y_{useful}\)-labeled disagreement states (unit = audited state; clustering at state/trajectory/game) |
| \(n_{causal}\) feasibility decision | at R1: nominal ceiling = 3 rounds × 17 dev games × 40 slots = **2,040** valid disagreement states, so required end-to-end state validity ≥ 39% (a labeled state needs *both* decisive branches valid, so per-branch yield must run correspondingly higher); if R1 yield projects < 800 valid states across all rounds, the causal tier is declared unfundable at R1, the decision is logged, and the learned gate falls to §6.8's fallback |
| Step-5 envelope-mode target | ≥ 40% executive-call reduction vs always-call (cost-side; formal §13.1 acceptance measured at the step-7 operating points) |
| \(n_{val}\) | ≥ 150 valid stratified "suppression harmless" checks — strata: uncertainty and margin deciles, predicted risk, ACTION6 vs not, OOD, game, level position, \(\tau\) scale; borderline and high-risk oversampled, importance-weighted back |

### 13.2 Progress metric — orientation, zeros, and the primary statistic

**Orientation transform first.** Every endpoint is mapped to a higher-is-better utility before any
formula: level completions / platform score — identity · actions-to-completion —
\(u = 1/(1 + A)\) per completed instance, \(u = 0\) if not completed on this endpoint ·
progress events per scored action — identity. **No formula in this document is ever applied to
heterogeneously oriented raw metrics.**

**Per-game utility** \(P_{g,c} \in [0,1]\): the first available endpoint in the frozen hierarchy
(completions/score → oriented actions-to-completion → progress-event rate), at matched budget
(wall-clock primary; scored-actions attribution arm), **normalized to [0,1] before pairing** so no
single game's scale dominates the mean: completions divided by the game's known level count
(procedural) or by the maximum levels reached by either arm across the matched set (public);
\(u = 1/(1+A)\) is already in \((0,1]\); progress-event rate divided by the pair maximum (both zero
→ both 0). The paired difference is therefore a mean of bounded per-game effects.

**Primary statistic — paired difference, not a ratio:**

\[
D_{progress} = \frac{1}{G} \sum_g \big(P_{g,\text{gate}} - P_{g,\text{always}}\big),
\qquad \text{tolerance: } D_{progress} \ge -0.10 \cdot \bar P_{always}.
\]

All games enter \(D\), including zero-progress games — no exclusions. The ratio
\(1 - \bar P_{gate}/\bar P_{always}\) is reported descriptively only.

**Discordant-completion veto (lexicographic, binding):** the gate fails if
(matched instances uniquely completed by always-call) − (uniquely completed by gate) exceeds **10%
of matched procedural instances**, or exceeds **1 game** on public validation — regardless of
\(D_{progress}\). Both directions of discordance are reported.

Uncertainty: bootstrap clustered at game level over matched seeds; 90% intervals.

### 13.3 Irreversible-loss criterion

Primary inferential statistic — paired per-run difference:

\[
D_r = r_{gate} - r_{always}, \qquad \operatorname{UCB}_{90\%}(D_r) \le \delta_{NI},
\qquad \delta_{NI} = 1 \text{ event per 1,000 scored actions.}
\]

The hybrid margin \(r_{gate} \le \max(2 r_{always}, r_{always} + \delta_{NI})\) is reported
descriptively. Rare catastrophic events additionally reported per episode and per level.

### 13.4 G0 constants

Margin \(\max(10\text{pp}, \min(20\text{pp}, 2\sigma))\), \(\sigma\) from ≥ 4 baseline seeds (else
10pp floor); 1-completion non-inferiority: ≤ 3pp regression, one-sided 90% LCB > −5pp; online rule
≥ 5% actions-to-first-completion improvement or non-inferior with ≥ 20% lower executive cost; F4/F5
priced 2–3 days each; Branch A requires ≥ 5 slack days at Aug 22.

### 13.5 Public-game partition and leakage policy `[frozen at step 1]`

**17 development games / 8 validation games**, drawn before step 4.

**Draw method** `[amended 2026-07-28 — PARTITION-2026-07-28]`**.** The draw is accepted only when
**four** quantities each land within a pre-registered tolerance of the 17/8 proportional share:
**terminal-transition count · no-op count · ACTION6 transition count · total transitions.**
Reject-sample until all four hold; record the realized shares alongside the partition. The tolerance
is pre-registered in `gate_manifest.yaml`. Measured basis (`logs/s2_corpus_census.json`): across the
25 public games the worst-to-best dev share is 21%–97% for no-op positives, 22%–99% for ACTION6,
32%–96% for discrete counterfactual pairs, 44%–87% for transitions and 53%–80% for terminals; six
games contain no ACTION6 at all and five contain almost no no-ops.

Validation games are excluded
from: branching rounds R1–R3 · threshold and weight tuning · ablation iteration · click-salience
training · G0 training data (their replays are quarantined). ACTION6 availability statistics may use
all 25 (descriptive). Public validation is **external-validity evidence with veto power** (§6.7);
procedural paired runs are **retention evidence**. If any validation game is touched by development,
it is reclassified as dev and the validation set shrinks — reported, never silently backfilled.

### 13.6 Re-anchoring rules

**Cost-side** — call-reduction target, paired-run sample sizes, branching attempted-action caps and
targets, \(W\), \(H\), \(B_{ctx}\) — may be re-anchored **once**, after the D0 latency table,
measured actions/s, measured always-call cost, and R1's measured yield, and **before any loss-side
data is inspected**. **Loss-side** — the 10% \(D_{progress}\) tolerance, the discordant veto,
\(\delta_{NI}\), G0 margins and tolerances, D0 capability thresholds, envelope confidences,
value-head weights — are **frozen now**. Any change is logged with date and cause in this header.

---

## 14. Open items (measured, not assumed)

Per-action latency and true wall-clock envelope · request-rate caps on the evaluation platform ·
**accounting-rule scope** — §4.1's case is selected, its scope is not: whether the rule measured on
tu93 offline holds on a second game and in competition mode · RESET's archive consequences ·
ACTION7/undo exposure · toolkit padding and tensor shapes · scoring constants · measured always-call
executive cost (prices shadow mode and paired runs) · reconstruction-depth distribution (validates
§13.1 depth caps) · branch validity yield (R1) · calibration-drift magnitude on procedural held-out
games (sizes the adaptive controller) · common-random-number support in the environment (decides
§6.6's stochasticity handling) · **S2 generator throughput and held-out instance count** ·
**minimum positive counts for the progress and demonstrated-irreversible heads** ·
**`P(persistent change)` label census** · **replay/local-fork licensing and platform-version
fidelity before derived weights ship**.
