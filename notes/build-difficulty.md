# All four tiers — what each component takes to build, and how hard it is

**2026-07-28. Planning judgment, not a pre-registration.** Ratings are my estimate of build
difficulty; nothing here is a threshold, and no number in this note may be cited as measured.
Component definitions are SPEC §§4–11 and §13.5 — where this note disagrees with the
specification, the specification wins. Summary tables are mirrored in SPEC §3.1.

**Tiers 3 and 4 are treated differently in kind.** Several are *experiments* rather than components,
and their estimates are conditional on gates that have not run. Two Tier 4 items have no
specification section at all: they carry **no estimate** — `N/A — unspecified` — because there is
nothing designed to estimate against.

## The single 0–8 score was withdrawn 2026-07-28

The first version of this note rated each component on one ordinal scale. **That scale silently mixed
four different quantities** — implementation effort, missing training data, unknown branch yield, and
validation complexity — so a component scored high for lacking positives (§5) and a component scored
high for being genuinely hard to write (§4.4) received the same number, and the data axis duplicated
SPEC §3.2's. The scores were not comparable to each other and had no time interpretation, which made
them useless for checking a calendar. Four separate axes replace it.

| Axis | Meaning |
|---|---|
| **Days O / L / P** | Optimistic / likely / pessimistic **focused person-days**, solo, ~8 h each. **Excludes integration** — see the allowance below |
| **Impl** | How much design is still open. *Low* = fully specified · *Med* = choices remain but are bounded · *High* = a real design problem · *Open* = research-open or unspecified |
| **Verify** | Verification and integration risk. *High* = correctness is not locally checkable; a wrong implementation produces plausible output rather than an error |
| **Data** | Training-data readiness — **the SPEC §3.2 axis, referenced not restated.** `n/a` where the component consumes no training data |

**Integration allowance, stated as a judgment with no measurement behind it:** per-component days
cover building and unit-testing the component alone. Wiring it to its neighbours, and the paired or
procedural validation each retention rule demands, is **not** included. Budget a further **~30% at
step level**, more where the *Verify* column reads High. Nothing in the repo measures this figure yet;
it is a placeholder to be replaced by actuals after step 1.

**Day estimates are judgments, not measurements**, and none may be cited as pre-registered.

---

## Summary

### Tier 1 — unconditional substrate · likely **33.5 d**

| # | Component | § | Days O/L/P | Impl | Verify | Data |
|---|---|---|---|---|---|---|
| 1 | Harness, accounting, latency table | 4.1 | 2 / **3** / 5 | Low | Med | Low |
| 2 | Branching primitive | 4.2 | 3 / **5** / 9 | Med | **High** | **High** |
| 3 | Canonicalizer + delta compiler | 4.3 | 3 / **5** / 8 | **Open** | Med | Low |
| 4 | Archive | 4.4 | 4 / **6** / 10 | Med | **High** | Low |
| 5 | ACTION6 candidate system | 4.5 | 2 / **4** / 6 | Low | Med | **High** |
| 6 | Minimal hypothesis store | 4.6 | 0.5 / **1** / 1.5 | Low | Low | Low |
| 7 | Executive I/O contract | 4.7 | 1.5 / **2.5** / 4 | Low | Med | Low |
| 8 | Terminal-transition logging | 4.8 | 0.25 / **0.5** / 1 | Low | Low | Low |
| 9 | Procedural suite (Alias, Delay) | 4.9 | 3.5 / **6** / 10 | **High** | Med | n/a — it *is* the source |
| 10 | Public-game partition | 13.5 | 0.25 / **0.5** / 1 | Low | Low | **Blocked** |

*§13.5's `Blocked` is a dependency flag, not a difficulty: the code is half a day and cannot run
until the tolerance is registered. Blockers are tracked in* `docs/README.md`*'s open items, never
folded into an effort estimate.*

### Tier 2 — required delegation layer · likely **28.5 d**

| # | Component | § | Days O/L/P | Impl | Verify | Data |
|---|---|---|---|---|---|---|
| 11 | Cheap action evaluator | 5 | 4 / **7** / 12 | Med | Med | **High** |
| 12 | Two-stage gate + envelope | 6.1, 6.4 | 2 / **3.5** / 6 | Low | Med | Med |
| 13 | Adaptive threshold controller | 6.2 | 1 / **2** / 3 | Low | Med | Med |
| 14 | Shadow-mode instrumentation | 6.5 | 1.5 / **2.5** / 4 | Low | Med | Low |
| 15 | Paired-run + branching estimators | 6.6 | 3 / **5** / 8 | Med | **High** | Med |
| 16 | Control portfolio | 7 | 2 / **3.5** / 6 | Low | Med | Low |
| 17 | Full belief ledger | 4.6 | 3 / **5** / 8 | Med | Med | Med |

### Tier 3 — gated enhancements (internal order binding)

| # | Component | § | Days O/L/P | Impl | Verify | Data |
|---|---|---|---|---|---|---|
| 18 | Belief rungs 1–3 + R0 | 10.2, 11.2 | 8 / **14** / 25 | **High** | **High** | **High** |
| 19 | Verified partial programs | 8 | 3 / **5** / 9 | Med | Med | Low |
| 20 | Rungs 4–5, each gated | 11.2 | 3 / **5** / 9 | Med | Med | Med |
| 21 | Learned probe selection | 7 | 1.5 / **3** / 5 | Low | Med | **High** |
| 22 | Learned invocation gate | 6.8 | 3 / **5** / 8 | Med | Med | **High** |
| 23 | Goal families Order/Count — **Branch A** | 9.6 | 4 / **6** / 9 | Med | Med | n/a |
| | — **Branch B** | 9.6 | **N/A — not built** | — | — | — |
| 24 | G0 experiments (G0-R, G0-A) | 9 | 4 / **7** / 12 | Med | Med | Med |

### Tier 4 — speculative score multipliers

| # | Component | § | Days O/L/P | Impl | Verify | Data |
|---|---|---|---|---|---|---|
| 25 | Goal-model production integration | 9.7 | 1 / **2** / 4 | Low | Med | n/a — conditional on G0 |
| 26 | Mechanism retrieval (rung 6) | 11.2 | 1.5 / **3** / 5 | Low | Med | Med |
| 27 | Longer-horizon latent planning | — | **N/A — unspecified** | Open | — | — |
| 28 | Hierarchical subgoals | — | **N/A — unspecified** | Open | — | — |

*`N/A` means no estimate is possible or none is owed — Branch B is the decision **not** to build, and
27–28 have no specification section to estimate against. Neither is a zero.*

---

## The calendar does not fit the estimates

§12.1 declares *"the calendar guarantees steps 1–5"* and allots them **W1–W3**. At the project's own
~5 focused days/week that is **~15 person-days**. The components those steps contain:

| Step | Contents | Optimistic | Likely |
|---|---|---:|---:|
| 1 | §4.1 · §4.2 · §4.8 · §13.5 | 5.5 d | 9 d |
| | *+ D0 — a gate, not in the component tables* | *1.5 d* | *2 d* |
| 2 | §4.3 · §4.4 · §4.5 · §4.6 minimal | 9.5 d | 16 d |
| 3 | §4.7 | 1.5 d | 2.5 d |
| | *+ executive policy, archive retrieval, legality guards — not in the component tables* | *1.5 d* | *2 d* |
| 4–5 | §5 · §6.1/6.4 · §6.2 · §7 · §6.5 | 10.5 d | 18.5 d |
| | **Total against W1–W3 ≈ 15 d** | **30 d** | **50 d** |

Two lines above are **not** in the component tables and were previously folded into the step sums
without being shown — D0 and step 3's executive policy. §4.2 is counted once, in step 1, though the
v0/v1 split now spans steps 1–2. Step 4–5 uses §7's full estimate: portfolio v1 arms only rows 1, 5
and 6, so a case exists for discounting it, but discounting silently is how the earlier version of
this table came out ~2 days light.

**The optimistic column is 2× the allotted time; the likely column is over 3×** — before the
integration allowance, which the *Verify: High* entries in steps 1 and 2 make least safe to omit.
Step 4–5 alone is 18.5 likely days inside a single week.

**Either these estimates are substantially too high, or §12.1's calendar is substantially too tight.**
The gap is too large to close by adjusting individual numbers, and the honest statement is that
**§12.1 has never been checked against any effort model** — the W-numbers express dependency order,
which they do correctly, and were not derived from effort. Three ways to resolve it, none of which I
should pick unilaterally:

1. **Re-measure after step 1** and replace these judgments with actuals — step 1 is the cheapest
   calibration point and it happens anyway.
2. **Move the guarantee.** If steps 1–5 are the submission, the guarantee is the thing that must be
   true; W3 is negotiable and Oct 18 is far away.
3. **Cut scope inside steps 1–5.** §12.2's slack policy deletes Tier 3 and 4 first and explicitly
   never compresses steps 1–5 — so this option requires amending the slack policy, not applying it.

---

## 1. Harness, accounting, latency table — §4.1

**Needs:** environment client · deterministic replay driver · scored-action accounting reproducing
the platform's formula · latency table over environment step, evaluator forward pass and executive
call *under the real batching pattern* · derived per-action budget.

**Why it's cheap:** S1 already did this once. REPLAY-DET/RESET-ACCT drove the offline environment files, reproduced
the scoring formula exactly, and produced the accounting rule now binding in §4.1. The method is
proven and the traps are known.

**Why it isn't free:** the S1 harness is measurement scaffolding built around the vendored reference,
which can never ship — so the deployed accounting is a re-implementation, not a port. And the latency
table cannot be completed until D0 picks a model: "under the real batching pattern on the target GPU"
is not measurable before there is a model resident on that GPU. Step 1 therefore produces a partial
table.

## 2. Branching primitive — §4.2

**Needs:** trajectory-prefix recording · deterministic reconstruction by replay · a state-identity
verifier over *observation hash + inferred context signature + history equivalence class* · candidate
execution with immediate and K-step outcome capture · per-branch yield instrumentation over the seven
enumerated invalidity reasons · audit-state selection preferring short archive routes.

**Why the days run wide and *Verify* is High.** Two reasons, neither about lines written.

*It cannot be built before §4.4.* "Verify reconstructed identity including context and relevant
history class" requires the projection machinery — two of the three key components are inferred by
the archive. §4.2 and §4.4 are mutually entangled; the build order lists them in one step for good
reason, and treating them as sequential is the error to avoid.

*Its output quality is a measured unknown.* §13.1 needs ≥ 39% end-to-end state validity to fund
\(n_{causal} \ge 800\), and no one has measured branch yield. You can write correct code and still
produce an unusable instrument. R1 is the pilot; plan for the fallback (§6.8) rather than assuming
the number lands.

**Sharpest trap:** final-hash match is explicitly insufficient, and a contaminated branch has no
symptom — it produces a plausible label. Get the identity check wrong and every downstream causal
claim is quietly wrong.

## 3. Canonicalizer and delta compiler — §4.3

**Needs:** canonical form preserving cell values 0–15, dimensions, frame separation, explicit
padding, metadata and action masks, stripping serialization noise so identical situations hash
identically · a delta compiler emitting ten output families (changed-cell count and set, bounding
boxes, colour transitions, connected regions, translation/merge/split hypotheses,
appeared/disappeared, animation-vs-persistent by settled-frame comparison, action-availability
changes, level/score markers) · multiview outputs in parallel.

**The output list is enumerated; the semantics are not.** An earlier version of this note called §4.3
"fully specified" and that was wrong. The specification names *what* the compiler emits and leaves
open *how*:

- **connectedness** — 4- vs 8-connectivity for "connected changed regions";
- **frame settling** — the harness uses `frame[-1]` throughout S1/S2, but the specification never
  defines "settled" normatively, and animation-vs-persistent classification rests on it;
- **translation / merge / split matching** — what counts as the same region moving rather than one
  disappearing and another appearing;
- **confidence computation** for "candidate region with confidence";
- **conflict handling** when two hypotheses explain the same delta.

These are not cosmetic. Region identity feeds §4.4's node identity, and node identity is what §4.2's
branch verification checks — so a choice made casually here propagates into every causal label. Hence
**Impl: Open**: either the specification defines these five and the component becomes bounded design
work, or the estimate carries design risk it does not show.

What *is* settled is the input side: 64×64, values 0–15, 1–N frames and per-game action availability
are all measured.

**The discipline, not the difficulty:** object output is always "candidate region with confidence,"
never "object." Easy to write, easy to erode under pressure, and the erosion is invisible until a
downstream component trusts a segmentation it shouldn't.

## 4. Archive — §4.4

**Needs:** append-only evidence layer (canonical observation, full frame sequence, settled frame,
action, metadata, exact delta, prefix id, resulting observation, predictions with realized error) ·
versioned interpretation projections (context signatures, history equivalence assignments, node
partitions, alias flags, contradiction sets) · node identity as the triple · single-active-projection
rule with **atomic** swap · override rule.

**The evidence layer alone is ~2 days.** The rest, and all of the verification risk, is the projection layer:

- Node identity depends on two *inferred* quantities, so identity is revisable — hence projections
  rather than mutation. This is a versioned-view problem, not a database problem.
- The atomic swap must invalidate **eight** distinct kinds of derived state: caches, routes,
  reversibility claims, frontier labels, cycle memberships, candidate subgoals,
  program-applicability records, and anything else carrying a projection version. That is
  cache-coherence spanning the whole agent, and a missed invalidation surfaces as a wrong action
  much later, in a different component.
- The spec names one failure mode explicitly — putting a monotonic counter in the key makes every
  node unique, cycles undetectable and contradictions unrepresentable. It is the obvious shortcut and
  it defeats the entire design.

## 5. ACTION6 candidate system — §4.5

**Needs:** nine generators (learned click salience plus component centroids, boundaries and corners,
recently changed cells, rare colours and shapes, symmetry correspondences, uniform background probes,
uncertainty hotspots, successful coordinate classes) · a mandatory diversity quota · three recall
metrics measured at four budgets.

**Why the spread:** the eight heuristic generators are individually small, but the learned salience head is
blocked twice over — it trains on dev-partition replays only, so §13.5 must be frozen first, which is
itself blocked on the tolerance. And **causal useful-coordinate recall cannot be computed until
branching produces data**, so one of the three mandatory metrics is unavailable at the time this
component ships.

**Why it can't be deferred:** measured 2026-07-27 — with no proposal mechanism, a click-only game
produced **1 action in 16 minutes** against 59 for a keyboard game. Nineteen of 25 public games expose
ACTION6. This is not an enhancement.

## 6. Minimal hypothesis store — §4.6

**Needs:** `id · claim · scope · status ∈ {proposed, supported, contradicted, retired} · supporting
transition refs · contradicting transition refs`.

Six fields and an enum. Sufficient for the executive I/O contract and contradiction logging, which is
all Tier 1 asks of it. The *full ledger* — preconditions, predicted effect, confidence, cheapest
discriminating test, irreversible-risk estimate, goal-hypothesis records, unknowns section, plus a
retention gate on the compression policy — is Tier 2 at step 6 and is a different, much larger job.

## 7. Executive I/O contract — §4.7

**Needs:** input-packet assembly from eleven sources · the JSON output schema · post-execution
verification (expected event vs exact delta, persistence vs later observation, hypothesis
discrimination vs evidence, predicted vs realized risk) written to the §6.9 decision record · call
types separated, with costs and productivity reported per type.

**Why it is cheap:** schema and plumbing, fully specified including a worked example.

**Why it is scheduled late anyway:** the input packet reads from nearly every other Tier 1 component,
so it can be *written* early and *filled* only as they land. Post-execution verification is only as
trustworthy as §4.3's delta compiler.

## 8. Terminal-transition logging — §4.8

**Needs:** log every `(o_t, a_t, Δ_{t+1}, level advanced)` tuple, unconditionally, from step 1.

The smallest item in the tier and the one with the highest consequence-per-line. It is the sole
source of G0's training data and the progress head's real positives, and **the data cannot be
recovered retroactively** — an episode run without it is an episode whose terminals are gone. Ship it
in the first commit of step 1, before anything that could justify deferring it.

## 9. Procedural suite, Alias and Delay — §4.9

**Needs:** two generator families meeting the seven-item §4.9 interface (exact successors for every
legal action, evaluation-only ranking criterion, hidden mechanic state, colour-permuted variants,
ground-truth state IDs, seed and random-stream control, on-demand generation) · observations matching
the measured conventions including **variable-length frame sequences** · Alias's three ceilings.

**Why the likely estimate is 6 days against a 3.5-day S2 budget:**

- **Throughput is the sharp edge.** The requirement derived in
  [`screening-training-data.md`](screening-training-data.md) keeps S3 compute-bound rather than
  data-bound; it is unregistered, and a naive pure-Python generator will miss it by an order of
  magnitude. Discovering that during S3 costs S3's schedule, not S2's.
- **Delay is definitionally delicate.** A bit whose consequence lies *outside* the training horizon —
  set the delay too short and Delay collapses into Alias, which destroys the only contrast that makes the
  objective screening unbiased.
- **Variable-length frame sequences are not a detail.** 71% of real observations are one grid, the
  mean is 2.86 and the max 404. A single-grid generator emits a distribution the environment never
  produces, and Alias's timestep stops being well-defined because part of the relevant history lives
  inside one observation.
- **Four quantities are unregistered** — throughput, held-out instance count, progress prevalence,
  instance diversity — and all four must land in `gate_manifest.yaml` before the work consuming them.

## 10. Public-game partition — §13.5

**Needs:** a reject sampler over 17/8 draws holding four quantities within tolerance of proportional
share — terminal-transition count, no-op count, ACTION6 count, total transitions — recording realized
shares.

**The code is half a day.** Every input already exists in `logs/s2_corpus_census.json`.

**It cannot run.** The tolerance is unregistered — open item 4 in [`docs/README.md`](../docs/README.md)
— and the partition is frozen at build step 1 and never backfilled. Four components wait behind it:
the evaluator's progress head, the no-op head, G0's training data, and §4.5's click salience. This is
the cheapest blocker in the project and the one with the widest downstream shadow.

---

## 11. Cheap action evaluator — §5

**Needs:** one modest grid encoder (Track A §5: output grid 8×8 or 16×16, token width 128–192, depth
4–6) running **once per step**, with dense heads over the spatial map — coordinate head as a
segmentation head, discrete heads off the pooled embedding · seven head families (no-op / visible
change / persistent change · progress event · three-valued reversibility · changed region · candidate
value under the frozen \(U(a)\) formula · uncertainty and OOD) · the three-stage supervision ladder
4a → 4b → post-R1 v2.

**Why *Data* is High while the architecture is small:**

- **One head has zero training positives today.** *Demonstrated irreversible* requires verified
  absence of a return route; replay non-return is `unknown` and is never trained as negative. The
  class must be manufactured by §4.2's branching or a local fork. Building the head is easy; having
  anything to fit it on is not.
- **A second head is blocked on §13.5.** The progress head is the binding data constraint —
  0.90% prevalence, 1,614 replay terminals — and its dev-partition supply moves over an 850–1,287
  range depending on a draw that cannot be made until the tolerance is registered.
- **Three-valued reversibility is a non-standard loss.** *Unknown* is not a negative class and is
  never trained as one; imbalance is handled by reweighting, with calibration reported. This is easy
  to get subtly wrong in a way that looks like a working classifier.
- **No encoder reuse.** `EVAL-SCOPE-2026-07-28` forbids sharing an encoder with the belief model, so
  this is trained from scratch on its own supervision.

**Not why:** the O(1)-in-candidates design makes the *inference* cost trivial. The difficulty is
entirely supervision.

## 12. Two-stage gate and autonomy envelope — §§6.1, 6.4

**Needs:** Stage-1 pre-emption on level start/advance, plan exhaustion, first occurrence of a new
persistent event class, and reset · Stage-2 accept/escalate after the portfolio proposes · forced
escalations · hard lexicographic safety vetoes outside the score · the scalar acceptance score
\(A_t\) over six weighted terms · the five-clause pre-R1 envelope.

**Why it is cheap to write:** the logic is completely specified — it is careful conditional code against predeclared
constants, not a design problem. Three things add weight:

- The **new-persistent-event-class trigger** (§4.10) is a sub-component in its own right: five
  simultaneous conditions including cluster novelty in a *frozen* feature space and a per-level
  cooldown.
- **Envelope clause 3 cannot be validated before §4.9** — it requires ECE-verified calibration on
  procedural held-out data.
- **Envelope clause 4** ("top candidate invariant across all available weak rankers and baselines")
  requires factual-head ordering, archive-NN and weak value all implemented and comparable.

## 13. Adaptive threshold controller — §6.2

**Needs:** fast term (dynamics error \(e_w\) over a window of \(W\) autonomous actions, wrong
persistence class or changed-region IoU below floor) · slow term (no-progress streak, `replan_after`
failures) · the no-progress suspension during verified routes and plans · mechanics — \(\tau\)
bounds, ≤ 1 adjustment per \(H\), condition persists a full window, cold start at \(\tau_{max}\),
level-advance bump, snap to \(\tau_{max}\) after a suppressed-then-irreversible loss.

A small state machine whose every constant is predeclared in §13.1. The suspension rule is
the only piece requiring thought — six quiet actions inside a verified setup sequence must not read
as failure. \(q_{hi}, q_{lo}\) come from procedural held-out calibration error, so like §12 it is
buildable now and *tunable* only after §4.9.

## 14. Shadow-mode instrumentation — §6.5

**Needs:** development episodes running always-call while the full fast loop runs counterfactually,
logging the §6.9 decision record every step · estimates of invocation and intervention rates,
action/hypothesis/plan disagreement, gate calibration against executive disagreement, candidate
overlap, bootstrap signal · the shadow disagreement oracle as a baseline.

Two policies stepping in lockstep over one trajectory with both logged. Moderate plumbing, no unknowns.

**Its risk is interpretive, not technical.** §6.5 spends most of its words on what shadow *cannot*
do: it observes the executive action's outcome and **never the suppressed cheap action's outcome**,
so it cannot estimate suppression loss, and the disagreement oracle bounds *predicting executive
intervention*, not achievable policy value. The failure mode is a correct implementation whose
numbers get reported as regret.

## 15. Paired-run and branching estimators — §6.6

**Needs:** the frozen evaluation-state contract — fresh archive, ledger, goal posterior, caches and
adaptation memory per policy-instance replicate with no cross-arm sharing · identical procedural
instance and initial seed · identical environment random stream where CRN is supported · deterministic
evaluator, gate, candidate-generator version and code version · deterministic executive decoding or
≥ 3 paired seeds · identical tie-breaking · dual budget matching (wall-clock primary, scored-action
attribution) · six measured endpoints including Jensen–Shannon divergence over a policy-independent
key.

**This is a reproducibility contract, and every clause in it is a place a run can be silently
invalidated** — hence *Verify: High*. "No data sharing across arms" is one memoized projection away from being
false. Two dependencies are unresolved:

- **CRN support is an open item** (§14) — whether the environment supports a common random stream is
  unknown, and the contract has a branch for each answer.
- **The divergence key** needs canonical settled-observation hashes, or procedural ground-truth state
  IDs from §4.9. Projection-conditioned divergence is explicitly secondary, because node IDs across
  policies need not share an alphabet.

## 16. Control portfolio — §7

**Needs:** six-row arbitration where the earliest admissible row wins · per-row admission conditions,
gate interaction and max chunk · the after-every-action block regardless of source (exact delta vs
prediction, event occurrence, contradiction detection, ledger and archive update, program demotion
check) · the bypass-revocation rule · deterministic probe selection v1.

The arbitration itself is a short ordered scan. The weight is elsewhere:

- **Half the table has no component yet at step 5.** Row 2 needs verified programs (Tier 3, step 8);
  row 3 needs belief rungs 3–4. It ships as v1 with rows 1, 5, 6 and is armed progressively — so the
  component is built three times, not once.
- **"A source that mispredicts loses its bypass for the affected scope until re-verified"** is
  scope-tracking state. Scope is per game / level family / region / object class / mode, and getting
  the granularity wrong either revokes too much (the portfolio collapses to escalation) or too little
  (a known-bad source keeps bypassing the score).

## 17. Full belief ledger — §4.6

**Needs:** each mechanics hypothesis extended with preconditions, predicted effect, evidence-based
confidence, cheapest discriminating test and irreversible-risk estimate · goal-hypothesis records
(predicate family, level scope, transferable parameters, graded evidence, counterexamples, current
executability) · an unknowns section naming which action semantics, object roles and goal candidates
are unresolved and which experiment separates them · a retention gate on the compression policy.

**Why it is not just a data model:**

- **"Cheapest discriminating test" is an inference, not a field.** Something must compute the
  minimum-expected-cost action predicted to discriminate ≥ 2 active hypotheses under the reversibility
  and risk bounds. That computation *is* §7 row 4's admission mechanism, so the ledger owns a search
  problem, not just storage.
- **The retention gate is an experiment.** The compression policy must beat rolling context on
  progress-per-action with the same executive. That is a paired measurement to design and run, and
  the gate applies to the policy, never to the store's existence.

---

## 18. Belief-model rungs 1–3 and R0 — §§10.2, 11.2

**Needs:** the structured state \(z_t\) — entity and relation slots parsed from compiler candidates
*with confidence*, a load-bearing grid residual covering non-object mechanics, history-conditioned
mechanics context · a candidate-conditioned forward model \(f(z_t, h_t, a_t)\) · **direct
multi-horizon heads at 1, 2 and 4 steps with the composition-consistency loss**
\(\lVert P_1 \circ P_1 - P_2 \rVert\) · latent objective and exact auxiliaries trained as explicitly
separate conditions with a detached-auxiliary control · its own encoder, never shared with §5 ·
symmetric degeneracy monitoring · R0's five criteria · rungs 1–3 each with its own retention
baseline.

**The widest estimate in the project, and High on all three risk axes, for four independent reasons:**

- **It is the research artifact.** S3 screens the objective; the deployed version must additionally
  fit resident alongside the executive on the target GPU with its (candidates × passes) product
  inside the measured fast-loop budget, or the candidate governor cuts candidates first.
- **The invariance requirement pulls two ways at once.** §10.2 demands invariance across synthetic
  environments where colour roles are permuted *and* sensitivity to colour within a single game.
  Both must be demonstrated; a model that satisfies one trivially fails the other.
- **The load-bearing R0 criterion needs the project's scarcest data.** "Beats the non-dynamics
  controls on held-out counterfactual ranking" is counterfactual evidence, capped by branch yield.
- **Delay is unresolved by construction.** Whether a reconstruction-free objective preserves a bit whose
  consequence lies outside the training horizon is the question S3 exists to answer — so this
  component is being built against a risk that is still open at build time.

**Degeneracy monitoring is symmetric and non-negotiable:** per-dimension variance, effective rank and
whitened probe accuracy for *every* learned representation, not only the latent arm. Probe accuracy
is diagnostic and never an abort trigger — aborting on it means aborting on the measured outcome.

## 19. Verified partial programs — §8

**Needs:** a typed rewrite-rule DSL over ten operation families (recolour, translate, copy, delete,
create, toggle, swap, increment counter, activate region, transform-all-matching) · an optional
sandboxed Python path — pure function of compiled state, resource-limited, no I/O · the program
record with applicability predicate, declared scope, predicted delta and event, supporting
transitions, counterexamples and **projection version** · admission on five simultaneous conditions ·
immediate demotion on a single in-scope contradiction.

**Why it is not a research problem:** the search space is deliberately tiny — "the smallest useful verified fragment, one
action, one object class, one region, one mode, never a complete simulator." That constraint is what
keeps this out of general program-synthesis territory.

**What adds weight:** the sandboxed Python path is an isolation surface, not just a feature; the
projection version couples every program to §4.4's swap discipline; and admission requires exact-delta
match on held-out context-matched transitions, so it inherits §4.3's correctness entirely.

**Its real advantage is political, not technical.** §12.2 never deletes verified programs before
rungs 4–5, and §3's ordering puts programs *ahead* of the rungs precisely so the calendar cannot
schedule the disposable item first. It is the safest place to spend Tier 3 time.

## 20. Rungs 4–5, each gated — §11.2

**Needs:** rung 4 — 2/4-step composition used to look ahead without waking the executive, at
\(k \times\) predictor passes, retained only against iterated-copy and 1-step-only baselines. Rung 5 —
relational transfer to levels 2..N, retained against a held-out layout and colour-permutation
evaluation.

**Why the marginal cost is modest:** the composition-consistency loss is trained at rung 1–3 time
**regardless of which rungs ship**, because it separates a compositional transition model from a
lookup table. So the marginal model work is small.

**Where the cost actually is:** the evaluation apparatus and the cost accounting. Rung 4 multiplies
fast-loop cost by \(k\), which must fit the measured budget; rung 5's evaluation needs §4.9's
colour-permuted and relaid-out variants. And these are first in §12.2's deletion order after Tier 4 —
so effort spent here is the effort most likely to be discarded.

## 21. Learned probe selection — §7

**Needs:** a learned replacement for row 4's deterministic cheapest-test admission, retained only if
it beats random probing, novelty-based probing **and** the deterministic baseline on
hypotheses-resolved-per-scored-action.

Small model, clear target. It is gated twice — on the full ledger (§4.6) supplying
hypothesis-resolution outcomes, and on branch yield, since it is one of the six artifacts sharing
that ceiling (§3.2). Under §4.1's accounting every probe costs score, which is exactly why a *better*
probe selector is worth something and also why its training signal is expensive to collect.

## 22. Learned invocation gate — §6.8

**Needs:** \(P(\text{intervention useful} \mid s, h, \hat a, u)\) bootstrapped on shadow and proxy
labels but **claimed** only against branched disagreement · the frozen four-tier lexicographic
\(Y_{useful}\) label · \(n_{causal} \ge 800\) valid labeled disagreement states · five baselines.

**The model is small; the label pipeline is the work.** Each tier of the lexicographic test needs its
own detector — irreversible-loss avoidance, terminal-or-progress within \(K\), progress-event
counting, and hypothesis resolution *verified by exact delta* at no greater realized risk and no
fewer progress events. Ties are labeled not-useful. Invalid branches must be excluded and charged
against yield rather than silently dropped.

**It is the only Tier 3 item the specification explicitly permits not to ship.** If R1's yield
projects under 800 valid states, the causal tier is declared unfundable, the decision is logged, and
the gate falls back to uncalibrated ordering over the deterministic escalation queue — or nothing.
Build it expecting that branch.

## 23. Goal families Order/Count, Fork G-F — §9.6

**Needs, under Branch A:** two further generator families — **Order** (ordered-event-program) and **Count**
(cumulative-counter) — each with generator, verifier and ground-truth parameters, priced 2–3 days
apiece in §13.4. Family transfer then runs train-3-hold-out-1, rotating.

**Under Branch B it costs nothing:** family transfer is declared untestable and reported as such, the
criterion weakens to held-out parameters within family, and no cross-family claim is made anywhere.

**The estimate is mostly irrelevant to the schedule.** Branch A requires ≥ 5 build-days of slack at
Aug 22 and sits third in §12.2's deletion order. Plan for Branch B; treat A as an option the float
might buy. The reason the fork exists at all is that two sprint families make hold-one-out train on
n = 1, which is noise.

## 24. G0 gate experiments — G0-R and G0-A — §9

**Needs:** two models — G0-R for post-outcome recognition (terminal/progress classification,
prerequisite and partial-progress grading, goal-family classification where synthetic truth exists,
ledger pruning) and G0-A for pre-action utility with the **outcome source declared** and reported
separately per source (exact branch · cheap-evaluator prediction · belief-model prediction · verified
program) · the three-way terminal-action recall decomposition · the deployment adaptation protocol
with a frozen backbone and no gradient updates · five split types, never random transition splits ·
six baselines · the margin rule plus a 1-completion non-inferiority test.

This is a large *evaluation apparatus* around two modest models. Four declared outcome
sources each carrying their own source-paired baseline, six comparison baselines, five split types
and a sequential {1, 2, 4, 8}-completion grid is a lot of measurement surface, and §5 freezes the
progress-event head's target specifically so G0-A's baseline cannot move under it.

**Governance note.** `G0-SCOPE-2026-07-28` settled that goal induction earns integration *through*
this gate rather than inheriting build priority from S1-d's unstable 75% `primary_share`. The
experiments are Tier 3; only integration is Tier 4.

## 25. Goal-model production integration — §9.7

**Needs:** §9.7's decision table — both pass → integrate recognizer and ranker per passing outcome
source · G0-R only → integrate the recognizer, ranking stays heuristic · neither → heuristic plus
executive structural goal system, with terminal logging continuing regardless.

Wiring an already-trained, already-gated artifact into the portfolio and the ledger. Cheap by
construction — the expensive part was §24. Executable predicate induction remains
unscheduled Tier 4 and is not in this estimate.

## 26. Mechanism retrieval, rung 6 — §11.2

**Needs:** an ANN index over mechanism representations, serving better executive prompts, retained
only if it beats exact-hash and frozen-feature retrieval.

**The build is standard; the baseline is the problem.** Exact-hash plus frozen-feature retrieval is
cheap, has no training cost and no collapse risk. Beating it with learned representations is a real
bar, and failing to is a legitimate result rather than a defect.

## 27–28. Longer-horizon latent planning · Hierarchical subgoals

**No specification section exists for either.** They appear in Tier 4's membership list and nowhere
else — no interface, no retention rule, no cost model, no gate. No estimate is offered: there is
nothing to estimate against, which is why both read `N/A — unspecified` rather than a number.

Two constraints already bound them: §11.1 states that **8-step rollout is never a production
dependency**, and portfolio row 3 caps model search at 2–4 steps. Anything under these headings must
either respect those limits or amend them, which is a specification change, not a build task.

---

## What this says about the build

**Tier 1's risk is two entangled components; Tier 2's is one shared dependency.** §4.2 and §4.4 carry
essentially all of Tier 1's uncertainty, they cannot be built strictly in sequence, and both fail
*silently* — a bad projection swap or a contaminated branch produces plausible output, not an error.
Tier 2 has no High-Impl component, but **four of its seven cannot be validated until §4.9 exists** —
the evaluator (§5's progress supervision), the gate and envelope (§6.4's ECE clause *and* §6.3's
acceptance region, both one component), the adaptive controller (§13.1's τ bounds and
\(q_{hi}/q_{lo}\)) and the paired-run estimators (§6.6) — while §4.9 itself is 6 likely days against
a 3.5-day budget with four unregistered numbers. The delegation layer's
schedule risk is concentrated in a Tier 1 component built during the screening sprint.

**Supervision, not architecture, is what makes §5 expensive.** The evaluator's inference design is
deliberately O(1) in candidate count. What costs is that one head has zero positives today and
another is blocked behind an unregistered tolerance.

**Two components are easy to build and easy to over-read.** §6.5 cannot estimate suppression loss and
§6.2's decision-error signals are correlates — §6.2 states the epistemic boundary outright: causal
regret comes only from branching and paired runs. Both will produce clean, plausible numbers that
mean less than they appear to.

**Three items are cheap and urgent for reasons unrelated to their size.** §4.8 because the data is
unrecoverable if it's late. §13.5 because four components are blocked behind a number nobody has
chosen. §4.5 because coordinate games are unplayable without it and 19 of 25 public games have
ACTION6.

**One dependency is not in the build order.** §4.9 is built in S2, before W1, but §12.1 step 1's D0
measures capability on held-out procedural environments — so S2 slipping delays D0, and the build
order does not show that edge.

**Tier 3's binding internal order deliberately protects the cheaper item.** rungs 1–3 + R0 (**14 d likely**)
→ verified programs (**5 d**) → rungs 4–5 (**5 d**). §12.2 deletes the rungs while retaining programs, and
§3 says why in one line: the calendar must not schedule the disposable item first. Difficulty and
priority run in opposite directions here, on purpose.

**One measurement determines whether half of Tier 3 is fundable.** Learned probe selection, the
learned invocation gate, exact-branch G0-A and rung-3 counterfactual discrimination all draw on the
same branched evidence. R1's yield at W4 is not only a learned-gate feasibility result — it is the
evidence ceiling for four Tier 3 items at once, and §13.1 already declares the gate's fallback for
the case where it comes in low.

**Tier 4 is half-unspecified, and that is consistent rather than sloppy.** Two of its four entries
have no specification section, which is exactly what "never a dependency of the production agent"
buys. But it means those two cannot be scheduled even if slack appeared — they would need a spec
amendment first, not a sprint.

---

## Two specification changes this analysis argued for — both now made

Recorded 2026-07-28 as register entries `BRANCH-V0-2026-07-28` and `S2-GATE-2026-07-28`, each with
its dated amendment. Kept here as the reasoning that produced them; the specification is authoritative
for what they now say.

**1. §4.2 was scheduled a step before the identity layer it requires.** §12.1 put the branching
primitive in step 1 (W1) and the archive's versioned projections in step 2 (W1–2) — but §4.2's
verification is defined over *observation hash + inferred context signature + history equivalence
class*, and the latter two are what step 2 builds. A step-1 implementation has only a hash, and §4.2
says in terms that **final-hash match alone is insufficient**. The failure is silent: hash-only
branches produce plausible \(Y_{useful}\) labels indistinguishable from sound ones later.

**Resolved as branch v0/v1**, in preference to moving a minimal projection identity into step 1 —
that front-loads the highest-verification-risk component into the week already carrying D0, and an
identity revised later makes every v0 branch retroactively questionable. §12.1 now shows v0 in step 1
and v1 in step 2, so the dependency is visible in the build order. **One correction the amendment
forced:** v0 cannot produce full yield accounting either. *Context mismatch* and *projection change*
are two of the seven invalidity reasons and both need a projection, so v0 reports
\(yield_{mech}\) — an upper bound — and \(yield_{valid}\), which §13.1's \(n_{causal}\) decision
reads, is defined only for v1 at R1.

**2. §4.9 was an entry gate to the build with no acceptance milestone.** D0 at step 1 measures
capability on held-out procedural environments, so the suite gates W1 — yet §12 opened W1 with no
check that it exists or works, and §12.2's slack policy governs only *later* features.

**Resolved as §12.1 step 0 at W0**, a build step rather than a milestone hanging off W1, because the
suite is genuinely built during S2 rather than merely checked there. Six acceptance criteria: four
numeric ones that are exactly the quantities §4.9 lists as unregistered — throughput, held-out
instance count, instance diversity, progress prevalence — plus two structural ones with stated pass
conditions, generator correctness and observation fidelity. **The failure branch is declared, not
deferred:** W1's non-dependent substrate continues while D0 and every procedural-dependent item are
blocked, and blocked means recorded untested rather than passed.
