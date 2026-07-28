# Track B — Score-Oriented ARC-AGI-3 Agent Architecture

**Written 2026-07-25, revised 2026-07-25. Expository pass 2026-07-27** — §§3.1, 3.2, 3.4 and 3.5 each
gained a *what it is* opening, because each previously began mid-specification and assumed
[Track A](arc-agi-3-ship-jepa-x-architecture.md); §3.1's three identity components are now defined,
with the observation hash expanded (what canonicalization covers, why the hash and not the encoder
representation, and three open specification questions); §10's five otherwise-undefined "retained"
terms now carry pointers. **No design decision changed** — the three open questions in §3.1 are
recorded as open, not answered.
Complements
[`arc-agi-3-ship-jepa-x-architecture.md`](arc-agi-3-ship-jepa-x-architecture.md) rather than
superseding it: that document remains the reference for the learned predictive components, which are
retained here in reduced but non-trivial roles.

**Scope.** This document specifies the *deployed agent* (Track B), whose objective is ARC-AGI-3 score
under the platform's runtime budget. It does not govern the research track. The registered design in
[`arc-agi-3-execution-plan.md`](arc-agi-3-execution-plan.md) is **redesigned** around a new factorial
(§11) rather than suspended — the 48-model matrix as specified does not run because the design
changed, not because a local model may score well.

**Gate independence.** The local-model viability gate (D0, §6.1) determines only whether Track B uses
a language-model executive. It has no bearing on whether the predictive belief model is worth
building; that is decided by R0 (§6.2). The two are independent by construction.

**Design principle.** *Neural models propose; exact evidence falsifies; verified programs simulate; a
control portfolio decides how much to trust each source.* The available evidence says model strength
dominates harness sophistication — so build the exact substrate and the cheap predictive components
first, measure, and add machinery only where it demonstrably pays.

---

## 1. The binding constraint, and why it determines the architecture

Everything below follows from one piece of arithmetic that must be run before anything is built.

The runtime envelope in the execution plan is ~8 h wall-clock with ~10 actions/s as a working
assumption, both flagged `[verify]`. Take 8 h = 28,800 s. If a full evaluation run requires on the
order of 10⁴ scored actions across all games and levels, the per-action budget is ≈ 2.9 s.

A 27–31B-class model on a single RTX 6000 generates on the order of tens of tokens per second in a
single stream. Batching across parallel stateless game threads multiplies *throughput* but does not
reduce *per-request latency*. So the per-action token budget for a reasoning executive is on the order
of **a hundred tokens or fewer** — nowhere near enough for chain-of-thought on every step.

**Therefore the executive cannot run every action.** This is not a tuning detail; it is the
architecture:

> **Two-rate control.** A *slow loop* (the reasoning executive) runs on events — level start,
> contradiction, new persistent change, plan exhaustion, repeated no-progress. A *fast loop* (exact
> archive, predictive belief model, verified programs, guards) runs every action.

A compact predictive model costs milliseconds per forward pass, three orders of magnitude below the
executive. **That gap is the entire reason the belief model exists**: it is what can afford to run on
every action, evaluate dozens of counterfactual candidates, and look two to four steps ahead without
waking the expensive loop. Its job is to make the fast loop good enough that the slow loop is rarely
needed.

The exact numbers must come from measurement (§6.1). If the real budget turns out far more generous,
the slow loop can run more often — but the architecture should be built assuming it cannot.

### Fast-loop budget discipline

The fast loop's total per-action cost must fit within the measured per-action budget minus execution
and I/O overhead. The controlling product is **(candidate count) × (predictor passes per candidate)**,
and it is the knob the candidate governor turns first under pressure. Every component in §3 carries a
measured cost and a retention gate; anything that cannot be priced does not ship.

---

## 2. Architecture

```
                    ┌─────────────────── STATE OF RECORD ───────────────────┐
                    │  exact archive (context-conditioned)                  │
                    │  belief ledger: rules · goals · unknowns · refutations │
                    │  verified partial programs                            │
                    └───────────────────────────────────────────────────────┘
                             ▲                              │
             writes/refutes  │                              │  reads
                             │                              ▼
  ┌──────────────────────────────────┐        ┌──────────────────────────────────┐
  │  SLOW LOOP — event-triggered     │        │  FAST LOOP — every action        │
  │  reasoning executive             │        │                                  │
  │  · interpret deltas & events     │        │  · multiview state compile       │
  │  · propose rules / goals         │        │  · archive lookup (context-match) │
  │  · choose representation to view │        │  · candidate generation + prune   │
  │  · write partial programs        │        │  · predictive belief model:       │
  │  · pick discriminating probes    │        │      counterfactuals, 1/2/4-step  │
  │  · compress history → ledger     │        │  · program / exact search         │
  │                                  │        │  · guards + verify + execute      │
  └──────────────────────────────────┘        └──────────────────────────────────┘
```

**Triggers into the slow loop:** level start or advance · rule contradiction · new persistent event
class · plan failure · N consecutive no-change actions · goal-hypothesis set becomes ambiguous ·
belief-model uncertainty or OOD score above threshold · context pressure. Never on a fixed step
interval.

---

## 3. Fast loop components

### 3.1 Exact archive — context-conditioned (retained from SHiP-JEPA-X, with the identity fix)

**What it is.** A directed multigraph built online from what the agent has actually done. **Nodes are
states it has stood in; edges are transitions it has executed.** Nothing in it is predicted or
inferred — an edge exists because an action was taken and an outcome was recorded. That is what
*exact* means here, and it is why the archive outranks every other source (§2). Node and edge fields
are specified in [Track A §9.1–9.2](arc-agi-3-ship-jepa-x-architecture.md); the one worth repeating is
that every edge stores **the model's prediction and its error at execution time**, which makes the
archive a running scorecard for the belief model and not only a map of the game.

**What the fast loop asks it** (Track A §9.3): exact replay · shortest known path · frontier
identification · cycle detection · reversible return paths · event bottleneck discovery ·
contradiction retrieval · candidate subgoal generation · exact transition substitution during planning.

**The identity fix.** Node identity is **not** the observation hash alone:

```
node = (observation hash, inferred context signature, history equivalence class)
```

- **observation hash** — the exact frame or frame sequence, canonicalized. Observed.
- **inferred context signature** — the current hypothesis about hidden mechanics: which mode the game
  is in, how a switch or counter is set, what the actions currently mean. Sourced from the belief
  model's mechanics context (§3.3) and the ledger's supported hypotheses (§5.1). **A belief, not an
  observation.**
- **history equivalence class** — a coarsening of the path taken to reach this observation, retaining
  only what has been shown to matter (which switches were thrown, which objects collected) and
  discarding the rest. **Also inferred:** what "matters" is itself a hypothesis.

Two of the three components are beliefs, so **node identity is revisable** — the graph can be wrong
about what is the same state, and re-partitions as hypotheses change. That is the cost of the fix. The
benefit is that a bare observation hash cannot represent "same picture, different truth," so it cannot
record a contradiction, so nothing downstream can falsify anything.

#### What the observation hash covers

Not the raw payload — the output of [Track A §4.1](arc-agi-3-ship-jepa-x-architecture.md)'s
canonicalizer, whose preserve-list *is* the specification: categorical cell values (the integers 0–15,
never a rendered image) · original frame dimensions · frame separation · padding marked explicitly ·
metadata and available-action masks. Canonicalization strips serialization-level noise so that two
genuinely identical situations produce identical bytes. The hash is then trivial and costs
microseconds — **the canonicalizer is where the risk lives, not the hash.**

Track A §9.1 stores *both* the observation hash and the encoder representation on every node, and
**only the hash is part of identity.** The hash is exact and discrete, so distinct states never
collide; a learned embedding is approximate and continuous, so two behaviourally different states can
embed arbitrarily close. An embedding in the key would silently merge states — and merged states
manufacture false contradictions, sending the override rule below hunting a hidden variable that does
not exist. The embedding is a retrieval field. It never decides sameness.

**The rule that generalizes: invariance belongs in the representation, never in identity.** ARC
instinct pushes the wrong way here, because in ARC-AGI-1/2 colour-permutation invariance is usually
wanted. Inside one ARC-AGI-3 game colours are stable and causally meaningful, so two states differing
only by colour genuinely behave differently — §4.1's "preserves categorical cell values" is what
protects that. Generalization is the encoder's job (§3.3 rung 5), not the key's.

**Three questions this leaves open, which a builder must settle:**

1. **All N frames, or the settled final frame?** Observations arrive as 1–N grids, measured varying
   *within* an episode (one game produced `1,1,1,1,1,1,1,6,6`). Hashing all of them makes two arrivals
   at the same settled state via different animations into different nodes; hashing only the last
   discards the evidence §3.2's animation-versus-persistent view runs on. *Suggested: settled frame for
   identity, full sequence as a node field.* Not currently specified either way.
2. **Is the available-action mask in the key?** §4.1 preserves it, but preserved-in-the-record and
   in-the-key are different. For: §4.2 treats action-availability change as a delta feature, so the
   states genuinely differ. Against: metadata churn then splits nodes spuriously. Measured today,
   availability is per-game and **not observed to vary within an episode** — so it currently makes no
   difference, which is exactly why it is cheap to get wrong now and expensive to discover later.
3. **Level or score position?** No — §9.1 carries those as separate node fields. A monotonic counter in
   the key makes every node unique by construction, which makes cycles undetectable and contradictions
   unrepresentable, defeating the point of the fix.

Edges store action + coordinate, exact delta, resulting node, event tags, reversibility evidence,
whether the outcome matched the active rules, and any contradiction.

**Override rule, corrected.** A known transition overrides prediction only when observation, action,
inferred context, and relevant history all match, *and* no contradictory successor is on record. On
divergent successors from equal visible states: mark aliased, retrieve differentiating histories,
propose a hidden-mode variable, split the context signature, retain both modes until resolved.

This is the system of record. Neither executive prose nor any learned latent is authoritative over it.

### 3.2 Multiview state compiler

**What it is.** The fast loop's perception step. It takes the raw observation — 1 to N grids of 64×64
cells with values 0–15 — and produces several *simultaneous* views of it, because no single
representation suits every mechanic. A colour-based segmentation finds the objects in one game and
destroys the structure of another; the executive reads ASCII well and raw integer grids badly; the
belief model wants the categorical grid. Committing to one view early is the failure this component
exists to avoid.

Produce in parallel, expose a compact default, let the executive request more:

raw categorical grid · rendered image · compact ASCII/run-length form · exact changed-cell deltas ·
connected components under multiple connectivity and colour assumptions · repeated-motif candidates ·
bounding boxes and region summaries · relation candidates · animation-versus-persistent
classification · available-action metadata · level/reset/progress markers.

Object output is labelled **candidate region/object with confidence**, never "object." Segmentation is
a hypothesis; correspondence across a transition is near-exact and comes from the delta parser's
translation/merge/split hypotheses.

### 3.3 Predictive belief model — the JEPA component

This is the compact learned core of the fast loop. It is not an affordance classifier with a latent
attached; it is a history-conditioned predictive state that supports counterfactual evaluation and
short-horizon composition, because those capabilities are what the per-action budget can afford and
the executive cannot.

#### State decomposition — hybrid, not pure slots

\[
z_t = (z^{\text{entity}}_t,\; z^{\text{relation}}_t,\; z^{\text{region}}_t,\;
z^{\text{grid-residual}}_t,\; z^{\text{mechanics}}_t,\; z^{\text{belief}}_t)
\]

Entities and relations come from the compiler's candidate parses, **carried with confidence rather
than as truth.** The grid residual is load-bearing, not a fallback ornament: it protects against
segmentation error and covers mechanics that are genuinely not object-based — global patterns,
textures, topology, counters, phase state. Mechanics context is the history-conditioned inference of
action semantics and hidden mode.

#### Capability ladder — each rung justified by score, priced, and gated

| # | Capability | Fast-loop use | Cost per action | Retained if it beats |
|---|---|---|---|---|
| 1 | **Predictive sufficiency** — latent preserves the variables needed to predict consequences | precondition for everything below | one encoder pass | whitened probes at chance |
| 2 | **System identification** — infer action semantics and hidden mechanics from few interventions | fewer probes to pin down a game; directly what the quadratic penalty rewards | one encoder pass | explicit enumeration and the ledger's own probe selection |
| 3 | **Counterfactual discrimination** — rank actions not taken | candidate pruning; probe selection; no-op avoidance | one pass × candidate count | random, affordance-only, archive nearest-neighbour |
| 4 | **Composition, 2 and 4 step** — chained prediction stays consistent | look ahead without waking the executive | k × predictor passes | iterated-copy baseline and 1-step-only |
| 5 | **Relational transfer** — mechanic carries to new objects, positions, colours, layouts | levels 2..N, which carry the level-position weight | — | held-out layout and colour-permutation evaluation |
| 6 | **Mechanism-based retrieval** — retrieve by mechanism, not surface similarity | better executive prompts, fewer wake-ups | ANN lookup | exact-hash retrieval and a frozen feature baseline |

Rungs 1–3 come largely from one-step training. Rungs 4–6 do not, which is why one-step-only was the
wrong cut.

**Eight-step and beyond is not on the production path.** It is evaluated only after 2- and 4-step
composition pass their gates, and it never becomes a production dependency. Composition consistency
(‖P₁∘P₁ − P₂‖ and its 4-step extension) is retained as a training loss regardless, because it is what
separates a compositional transition model from a local lookup table.

#### Auxiliary outputs consumed directly by the fast loop

P(persistent visible change) · approximate changed region · event class · P(reversible) · P(no-op) ·
novelty versus archive · coordinate salience · **uncertainty and OOD score** — the last of which is a
slow-loop trigger, not just a diagnostic.

#### Training

Supervised from the agent's own logged transitions (labels are free — every executed action produces
its own ground truth), plus human replays, plus the procedural suite. The reconstruction-free latent
objective and the exact auxiliaries are trained as **explicitly separate conditions** (§7.2), because
heavy exact supervision can turn the system into an ordinary supervised dynamics model with a
JEPA-shaped loss — and if that is what happens, it should be a measured finding rather than a hidden
one.

### 3.4 ACTION6 candidate system

**The problem it solves.** ACTION6 carries an (x, y) coordinate over a 64×64 grid — **4096 candidate
actions at every step**, against five for ACTION1–5. Scoring them all is impossible inside the
per-action budget (§1), and ACTION6 is available at reset in **19 of the 25 public games**
(measured 2026-07-26). So a proposal mechanism that nominates a few dozen coordinates is not an
optimization; without one the coordinate action space is simply unusable, and the majority of games
are unreachable.

Union of: learned click salience (human replays) · object/region centroids · boundaries and corners ·
recently changed cells · rare colours and shapes · symmetry correspondences · uniformly spaced
background probes · uncertainty hotspots · previously successful coordinate classes.

**Keep a diversity quota.** A salience model can be confidently wrong and exclude the one required
cell; systematic ACTION6 avoidance is a documented failure mode in the reference class, including on
games solvable by a single click.

*Measured continuously, at several budgets (top-1, top-3, top-6, unrestricted):* required-coordinate
recall against human replays · no-change rate · persistent-change rate · progress-event recall.

Candidate recall separates two failure modes that are otherwise indistinguishable — the proposal
mechanism omitted the useful action, versus the ranker saw it and ordered it wrongly. No planner
result is interpretable without it.

### 3.5 Control portfolio

**What it is.** The fast loop's final step: everything above *proposes*, and this decides which
proposal to act on. The "use when" column is each mode's admission condition. Where several are
admissible the **earlier row wins**, because the rows are ordered by directness of evidence — the same
ordering §2 gives for the state of record: exact observation, then verified program, then learned
prediction, then executive judgement.

| Mode | Use when |
|---|---|
| **Archive/exact** | a context-matched known path reaches a valuable state |
| **Program search** | verified partial programs cover the relevant actions and objects |
| **Model search** | belief model has passed rungs 3–4 for this context; search 2–4 steps under it |
| **Probe** | hypotheses disagree and a cheap reversible action discriminates them |
| **Direct** | no verified model exists; executive picks one action (tutorial levels, first contact) |

Execute **one action by default**. Chunks of 1–4 only on exact archive routes, or where every step is
covered by verified rules and the path is reversible.

Guards before execution: legality · availability metadata · irreversible-risk veto · return-route
preservation when uncertainty is high. After execution: exact delta versus prediction, event
occurrence, contradiction detection, ledger and archive update.

---

## 4. Slow loop — the reasoning executive

One capable local multimodal model, invoked in role-specific modes rather than as multiple
continuously interacting agents:

- **observer** — interpret deltas and events, classify what changed and whether it persisted;
- **scientist** — propose mechanics and goal hypotheses, name the cheapest discriminating test;
- **planner** — produce a candidate plan or select a subgoal;
- **programmer** — write a verified partial program or a one-off analysis script;
- **critic** — detect contradictions, compress history into the ledger.

Only the cheap modes run on ordinary events; expensive modes run on contradictions, level boundaries,
and plan failures.

**Memory discipline.** Raw history stays out of the model's context. Three layers: a recent buffer
(last few transitions in full), an event ledger (persistent changes, contradictions, level
transitions, failed plans), and a belief summary (current rules, goals, unknowns, intended tests).
Refresh on events, never on a fixed step count.

If D0 fails, this loop is served by explicit hypothesis search plus the belief model's own probe
selection instead of a language model. The two-rate structure does not depend on an LLM.

---

## 5. Knowledge representation

### 5.1 Belief ledger

Typed, external, falsifiable — not rolling prose.

*Mechanics hypothesis:* statement · optional executable predicate · scope (game, level family, region,
object class, mode) · preconditions · predicted effect · supporting transitions · contradicting
transitions · evidence-based confidence · cheapest discriminating test · irreversible-risk estimate ·
status (proposed / supported / verified / contradicted / retired).

*Goal hypothesis:* state, event, or temporal predicate · level scope and transferable parameters ·
evidence from terminal transitions · weak evidence from structural progress · counterexamples ·
prerequisites · whether currently executable by the planner.

*Unknowns:* which action semantics remain uncertain · which object roles are unresolved · which goal
candidates remain indistinguishable · what experiment separates them. This section is what turns
uncertainty into action selection.

### 5.2 Goal induction over terminal transitions — stays on the main line

**This is deliberately not externalized.** Supplying the goal predicate would make failure cleanly
attributable, but hidden games supply no goals, and goal acquisition is the largest single score lever
identified in the architecture analysis. Externalizing it optimizes for attribution in a study rather
than for score. Attribution is instead protected by the model-only evaluation regime and the control
set in §7.2.

The learnable object is the **terminal transition**, not a positive state:

```
(o_t, a_t, Δ_{t+1}, level advanced)
```

A completing action typically returns the *next* level's frame, so a state satisfying the goal may
never be directly observed. Reconstruct it where possible via the rule or belief model; otherwise
learn `G(history, action, outcome)` directly.

Predicate classes: state relations · quantified object conditions · counts · region membership ·
symmetry and template match · "all instances transformed" · event occurrence · **ordered event
programs** · action-conditioned terminal triggers · cumulative counters.

**Labels are graded, not binary.** A visited non-advancing state is negative for *terminal now*, but
may be prerequisite-satisfied, partial-progress, or unknown-because-hidden-state-unresolved. Label
relative to each hypothesis.

**Cross-level transfer is parameterized, not literal.** The goal *family* usually persists; target
counts, regions, orderings, and participating objects change. Carry the family with free parameters
and re-fit per level.

**Bootstrap** (no completion observed yet): executive's structural reasoning · priors learned from
public replay completion transitions · tutorial-level exploration · generic progress hypotheses ·
small reversible probes · direct-policy fallback.

### 5.3 Verified partial programs

Compile the **smallest useful verified fragment**, not a complete simulator. A program may cover one
action, one object class, one region, or one mode, and reports its applicability conditions, predicted
delta, predicted event, support, and known unsupported cases.

Two representations behind one prediction interface: a typed rewrite-rule DSL (reliable, fast to
search) and sandboxed Python (coverage for global patterns and unusual mechanics).

*Admission:* consistent with its fitting transitions · predicts held-out recent context-matched
transitions · no counterexample in declared scope · simplicity or coverage benefit · survives exact
replay where replay is possible. Fitting-set consistency alone is not sufficient.

Programs must never silently enter the belief model's evaluation path — see §7.1.

---

## 6. Two independent gates

### 6.1 D0 — deployment gate: local model viability

Determines **only** whether Track B uses a language-model executive.

**License.** Weights must be compatible with the CC0/MIT-0 release requirement and with offline
bundling in a sandboxed submission. Resolve this first — it eliminates candidates before any
benchmarking effort is spent.

**Fit and throughput.** On the target GPU, at the intended quantization, with the compact models
resident alongside: measured tokens/s under the *actual* batching pattern (N parallel stateless game
threads), measured per-request latency, and cache behaviour across repeated calls. Derive the
per-action token budget and the affordable executive-call frequency.

**Capability, on held-out procedural environments** (never on games used for evaluation):

| Check | Requirement |
|---|---|
| Structured legal action output | ≥99% valid over the trial set |
| Delta description | correctly states what changed between before/after |
| Change classification | separates no-op, reversible, and persistent change |
| Representation robustness | works from rendered image, ASCII grid, and coordinate list — *measure which is best rather than assuming* |
| First-level progress | meaningful progress on unseen tutorial-style levels |
| Instruction adherence | respects legality guards and refuses out-of-scope actions |

**Also resolve here — the reset-accounting fork.** Does a level reset preserve knowledge while the
scored action count restarts or is measured only on the successful attempt? If yes, explore-then-
speedrun dominates and the exploration controller should be aggressive. If all actions accumulate,
exploration must be surgical. These are different agents; one cheap experiment decides which.

**On failure:** the executive role is served by explicit hypothesis search and the belief model's probe
selection (§4), and the compact learned components move to the centre of the agent.

### 6.2 R0 — belief-model viability gate

Determines whether the predictive belief model earns further compute. **This is a viability check on
this implementation, not a verdict on whether latent predictive architectures can reason.**

- no representational collapse — per-dimension variance, effective rank, and *whitened* probe accuracy
  for agent position, switch state, and inventory, monitored as a **training-time tripwire**, not an
  eval-time diagnostic;
- sensitivity to causally relevant state — control-distinct states separate in the representation;
- invariance to nuisance — colour permutation, translation, irrelevant distractors;
- recovery of hidden mechanics on synthetic environments where ground truth exists;
- **beats the non-dynamics controls (§7.2) on held-out counterfactual ranking.** This is the load-
  bearing criterion; the others are necessary conditions.

### 6.3 Independence

| D0 | R0 | Interpretation |
|---|---|---|
| Pass | Pass | LLM executive + belief model as fast loop. Both tracks proceed. |
| Pass | Fail | Strong deployment agent; negative result for this belief-model design. Fast loop reduces to archive + programs + affordance heads. |
| Fail | Pass | Compact agent with explicit hypothesis search; the belief model becomes central rather than advisory. |
| Fail | Fail | Exact archive + rule induction + goal induction agent. Document the belief-model failure precisely — it is the most informative outcome for the research question. |

---

## 7. Evaluation regimes and mandatory controls

### 7.1 Model-only versus hybrid

Every learned dynamics component is evaluated in two regimes, always reported separately:

- **Model-only** — no exact transition result may be consulted for an unexecuted action. No archive
  edge, no verified program, no simulator branch. This regime supports attribution.
- **Hybrid** — archive and verified programs may override or complement predictions. This regime
  measures agent usefulness.

Without the first, archive override makes it impossible to tell whether the model contributed
anything. Without the second, the number does not describe the deployed agent.

### 7.2 Mandatory controls

No claim that the belief model contributes reasoning survives unless it beats all of these:

- **retrieval-only** — the embedding used for nearest-neighbour transition retrieval, no transition
  prediction;
- **affordance-only** — change/no-op/event heads with no state-transition prediction;
- **no-dynamics policy** — candidate ranking from encoder states and generators alone, zero rollout;
- **archive nearest-neighbour** — exact-hash and near-match retrieval, no learned model;
- **exact / reconstructive dynamics** — the same backbone predicting sparse deltas or decoding a
  compact state;
- **detached-auxiliary** — exact auxiliary heads detached from the latent trunk, isolating how much of
  the gain the auxiliaries carry;
- **iterated-copy** — for composition rungs, the trivial baseline that predicts no change.

If retrieval-only or affordance-only matches the full model, the stronger claim fails and the
architecture simplifies accordingly. That is a useful outcome, not a failed one.

---

## 8. Retention gates for everything else

Each component stays only if it pays, measured against the tier below it.

- **Belief model rungs** — per §3.3, each against its named baseline, in both regimes.
- **Partial programs** — reduce wasted actions or search cost relative to direct policy plus exact
  archive alone.
- **Belief ledger** — improves progress-per-action over the same executive with rolling context only.
- **Probe selection** — beats random and novelty-based probing on hypotheses-resolved-per-action.
- **Hierarchy** — not built until goals are executable, local rules are reliable, flat search is
  demonstrably inadequate, and an oracle decomposition helps. Otherwise it is overhead.

---

## 9. Build order (dependency, not calendar)

1. Exact harness, deterministic replay, action accounting, latency table — plus **D0** and the
   reset-accounting experiment.
2. Context-conditioned archive, multiview compiler, ACTION6 candidate coverage with measured recall at
   all budgets.
3. Direct executive policy with retrieval and legality guards. *A submittable agent exists at this
   point, before any learned dynamics.*
4. Belief ledger, contradiction-triggered archive splitting, discriminating probes.
5. Predictive belief model rungs 1–3 (encoder, mechanics context, counterfactual ranking) — plus
   **R0**.
6. Rungs 4–6 (2/4-step composition, relational transfer, mechanism-based retrieval), each gated.
7. Verified partial programs; program/exact/model search portfolio.
8. Goal induction over terminal transitions; cross-level parameter transfer.
9. Ablate everything against step 3 in both regimes; remove what does not pay; preserve the thin
   fallback.

The dependency that matters: a working agent exists at step 3, so no component after it is on the
critical path for having a submission.

---

## 10. What is retained, and what is dropped

**Retained from SHiP-JEPA-X:** exact grid canonicalization and the transition-delta parser (its
transformation vocabulary is the seed of the rule DSL) · the archive graph and its services · event
detection · exact verifier and irreversible-risk veto · the demotion ladder · ACTION6 factorization ·
coordinate candidate generators · sequential/history-conditioned inference · direct multi-horizon
heads at 1/2/4 with composition consistency · counterfactual action ranking · the common-candidate
audit and attribution ladder · the diagnostic contract · the procedural boundary suite (now training
and evaluation infrastructure for the belief model, D0, and R0).

*Five of those names appear nowhere else in this document. They are specified elsewhere, and this list
is the only place they are claimed — so the pointers matter:*

| Term | Defined in | In one line |
|---|---|---|
| **demotion ladder** | [Track A §21](arc-agi-3-ship-jepa-x-architecture.md), reliability governor | the four fallback modes the agent drops through when it stops being trustworthy: full hierarchical → sequential flat → exact archive/graph → conservative frontier exploration |
| **common-candidate audit** | [`execution-plan.md` §6.7](arc-agi-3-execution-plan.md) | every arm ranks the *same* candidate set, so any difference is the ranker's and not the proposal mechanism's — this is what makes §3.4's recall metric interpretable |
| **attribution ladder** | [`architecture-alternatives.md` §11](arc-agi-3-architecture-alternatives.md) | the four rungs separating "the model is wrong" from "the interface is wrong"; called the most transferable scientific asset in the project, and it works for any pair of arms |
| **diagnostic contract** | [`execution-plan.md` §6.7](arc-agi-3-execution-plan.md) | the frozen baselines every condition is read against (copy-last-observation, random ranking, exact-simulator planning, archive baseline) plus the reported metrics — and the standing refusal to let unchanged-cell accuracy stand in for dynamics knowledge |
| **procedural boundary suite** | [`executive-summary.md`](arc-agi-3-executive-summary.md), *Controlled mechanism study* | synthetic generators producing many independent environments while varying one factor at a time. **S2's F1 and F3 are the two families of this suite that survive the screening sprint** |

**Dropped from the deployed agent:** unbounded and 8-step latent rollout as a production dependency ·
learned latent goal geometry · automatic latent subgoals · learned event hierarchy · test-time
gradient adaptation · multiple-successor neural predictors · mechanics-particle ensembles · the
thirteen-term joint loss in favour of predeclared grouped weights with principled normalization.

---

## 11. Track governance and the research factorial

**Track A is not gated by D0.** The research design is replaced, not suspended, because the scientific
question changed shape. The primary factorial becomes:

| Representation | Prediction target |
|---|---|
| Grid | exact sparse delta / reconstructive |
| Grid | reconstruction-free latent |
| Hybrid entity–relation–region–grid-residual | exact sparse delta / reconstructive |
| Hybrid entity–relation–region–grid-residual | reconstruction-free latent |

All primary arms receive equivalent sequence context. Markov-only becomes a synthetic diagnostic
control rather than half the matrix — the earlier design spent most of its models answering a question
whose answer was predictable.

Controls per §7.2. Regimes per §7.1. Endpoints are the capability ladder in §3.3, not end-to-end
goal-conditioned planning — the ladder's rungs are simultaneously the scientific endpoints and the
fast loop's requirements, which is why this track and Track B share components rather than competing
for them.

**Open items, to be measured rather than assumed:** per-action latency and the true wall-clock
envelope · the 600 req/min figure versus any Kaggle-local cap · reset accounting · RESET's archive
consequences · ACTION7/undo exposure on both paths · toolkit padding and tensor shapes · scoring
constants.
