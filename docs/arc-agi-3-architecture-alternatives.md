# Architecture Alternatives for ARC-AGI-3 — What Would Have a Higher Chance of Success

**Written 2026-07-25.** Companion to
[`arc-agi-3-jepa-feasibility-analysis.md`](arc-agi-3-jepa-feasibility-analysis.md). That document
asked whether the committed design *can* work. This one asks what would work *better*, at the level
of substituting an arm or replacing the whole design.

Schedule and cost are excluded, as requested. Build risk is included, because it is an architectural
property, not a calendar property — a design that cannot be made correct is not a better design.

Probability estimates are my own judgments, roughly calibrated and stated as ordinals rather than
measurements.

---

## 1. Method: how to compare architectures for this benchmark

The mistake to avoid is comparing architectures on how well they model dynamics. Dynamics modeling is
not what separates the systems in the reference class. The correct method is:

1. Decompose the benchmark into the sub-capabilities it actually taxes.
2. Establish where the *points* live under the specific scoring rule.
3. Extract the domain facts that make some capabilities cheap and others expensive.
4. Derive requirements.
5. Score candidate architectures against requirements, including build risk.

The reference class is the strongest available evidence, and it is unambiguous in one respect: the
two systems that work (an online program-induction system at 20/25 games, and a large-model
verification harness at ~99% on public) both **represent rules explicitly and verify them exactly**.
The system that scores zero represents dynamics in a learned latent space and optimizes against
sparse reward. That is not a coincidence, and §3 explains why.

---

## 2. What actually determines success on ARC-AGI-3

Seven sub-capabilities, with an honest assessment of where difficulty concentrates:

| # | Capability | Difficulty | Who solves it cheaply |
|---|---|---|---|
| 1 | **Perception / parsing** — segment objects, detect changes | **Low** | Exact connected components + delta parser. Free. |
| 2 | **Action-semantics identification** — what does ACTION3 do here? | **Low–medium** | Small hypothesis space; identifiable in 5–20 actions. In-context inference or explicit enumeration. |
| 3 | **Mechanics / rule induction** — pushing, blocking, toggling, gravity, transformation | **Medium** | Program induction, or a learned dynamics model. This is where world models live. |
| 4 | **Goal inference** — what constitutes progress? | **HIGH — the binding constraint** | Almost nothing solves it cheaply. Unstated, unlabeled, and compositional. |
| 5 | **Planning** — reach the goal efficiently given 3 and 4 | **Low–medium** | Classical search, once 3 and 4 are solved. Solved problem. |
| 6 | **Efficiency under quadratic penalty** | **Medium** | Front-loading information, then executing near-optimally. |
| 7 | **Cross-level composition** — later levels reuse and compose mechanics | **Medium** | Explicit, portable rules beat implicit context. |

The decisive observation: **capabilities 1, 2, 5 are near-solved by classical machinery; 3 is
contested; 4 is the bottleneck and is where the current architecture is weakest.**

The current design allocates its architectural sophistication to capability 3 — a sequential
hierarchical predictive world model, thirteen loss terms, multi-horizon heads, composition
consistency — and allocates to capability 4 a flat bank of nine hand-listed goal-hypothesis classes
with heuristic weight updates (§15). **The sophistication is on the wrong subproblem.** That is the
single largest finding in this analysis, and it holds regardless of which dynamics arm is chosen.

### Where the points live

The metric is (human actions / agent actions)² per level, capped at 1.15, with level-position
weighting, averaged equally across games. Three consequences:

- **Quadratic penalty on wasted actions.** An agent taking 2× human actions scores 0.25, not 0.5.
  Exploration is brutally expensive. This punishes any architecture whose learning requires acting.
- **Level-position weighting means later levels matter more.** Early levels are the cheap place to
  pay for information; later levels are where it must be repaid.
- **Equal averaging across games means per-game success is the unit.** A bimodal architecture that
  solves some games near-optimally and fails others outright can outscore a uniformly mediocre one.
  This *favors* explicit-rule systems, whose failure mode is bimodal (the DSL covers the game or it
  doesn't) over neural systems, whose failure mode is uniform mediocrity.

---

## 3. Seven domain facts that should drive the architecture

These are the levers. Most are underused by the current design.

### 3.1 Exactness is free

Cell values are categorical, grids are small, transitions deterministic. Hashing, connected
components, exact deltas, and version-space consistency checks are all cheap and exact. **Any
architecture that gives up exactness is paying a price for abstraction the domain does not require.**

### 3.2 Objects are exactly recoverable — this is the biggest unused gift

In natural images, object-centric models fail at segmentation, which is why slot-attention methods
are fragile. Here, connected components give you objects *deterministically and for free*, and the
delta parser (§4.2 of the spec) already computes correspondence hypotheses — translations,
rotations, recolorings, merges, splits — which is precisely the slot-matching problem that makes
object-centric world models hard elsewhere.

The domain hands you the hard part of object-centric modeling for free, and the current architecture
uses object tokens only to "supplement raw grid tokens. They do not replace them" (§4.3). Rules in
these environments are almost always object-relational ("the controlled entity pushes blocks", "keys
open same-colored doors", "collect all of the small squares"), not cell-local. A cell-level
representation must rediscover object structure inside its weights, and will transfer worse.

### 3.3 Goals are verifiable post-hoc — the most underexploited fact in the whole design

Level advancement is *observable*. Therefore every level completion is a **labeled positive example
of goal satisfaction**, with full state available. Every non-completion state in that level is a
negative.

This changes the character of capability 4 completely. Goal inference is not an unsupervised problem
with sparse feedback. It is a **version-space learning problem with a small number of highly
informative positives**. A handful of positives can pin down a predicate drawn from a well-chosen
grammar, and — critically — **the same goal predicate usually holds across all levels of a game**.

The structure this creates is the key to the benchmark:

> Pay exploration cost once on level 1 to obtain the first positive example. Induce the goal
> predicate. Then levels 2..N become *goal-specified planning problems*, which are solved by search.
> And level-position weighting means levels 2..N are where the points are.

The current design has none of this. §15's goal-hypothesis bank has nine hand-listed classes, updated
by heuristic evidence weights, and the hypotheses are not executable predicates — so they cannot be
used as search targets, and they cannot be refuted by a completion state. Making goal hypotheses
**executable and induced** is, in my assessment, worth more to the final score than the entire
latent-versus-token question.

### 3.4 Unscored compute is free; scored actions are not

The plan already states this law ("spend unscored compute inside the model; spend scored actions only
on vetted plans") but does not architect around it aggressively. If you have an exact or
exactly-verified model, you can search *arbitrarily deep offline* and emit a near-optimal plan. This
strongly favors:

- explicit rule models that can be executed exactly, at speed, millions of times;
- classical search (BFS/A*/beam/MCTS) over that model;
- and against anything that must take real actions in order to learn.

### 3.5 Human replays are aligned supervision, not just "policy seeds"

The metric normalizes against human action counts. The replay corpus is therefore *literally a
demonstration of the target behavior*. 342 plays with 145 completed solves supports:

- **behavior cloning** for an action prior — which cuts search branching factor dramatically;
- **coordinate proposal supervision** — human clicks are ground truth for which of 4096 coordinates
  matter, directly attacking the largest branching problem in the action space;
- **goal-predicate positives** — every completion state in every replay;
- **near-optimal trajectory targets** for a value/reachability function.

The plan treats replays as "references and policy seeds, not pretraining data." That is the right
call for *world-model training* (bias), but it undersells three other uses that are not
contaminating and are directly metric-aligned.

### 3.6 The reference class says: AlphaZero-shaped, not MuZero-shaped

Latent-dynamics model-based RL (MuZero/Dreamer family) works when you have dense reward and enormous
sample counts. ARC-AGI-3 provides neither — sparse terminal signal, no reward shaping, and a budget
where each sample costs score. Meanwhile the exact-model + search + strong-prior recipe (AlphaZero
shape) needs a model it can trust, and this domain *gives* you one: the archive is exact by
construction, and induced rules are exact where they hold.

**The natural architecture here is AlphaZero-with-an-induced-model, not MuZero-with-a-learned-latent.**
That framing predicts the reference class correctly, and the current design is a MuZero-shaped bet
wrapped in AlphaZero-shaped safety machinery.

### 3.7 The reset-accounting fork is architecturally decisive

Already on the W1 verification list, but its weight is understated. If a level reset preserves the
agent's knowledge while the *action count for scoring* restarts or is measured only on the successful
attempt, then the optimal strategy is **explore exhaustively, then speedrun**, and the architecture
should be optimized for fast rule and goal induction with near-optimal replanning. If all actions on a
level accumulate, then exploration must be surgical and information-per-action becomes the dominant
objective.

These two regimes call for materially different exploration controllers and different risk postures.
This is one cheap experiment that should be run before anything else is built.

---

## 4. Requirements derived

An architecture with a high chance of success on ARC-AGI-3 should:

- **R1.** Represent state **object-relationally**, with exact grid state retained underneath.
- **R2.** Represent goals as **executable predicates**, induced from completion states, portable
  across levels of a game.
- **R3.** Represent rules **explicitly enough to be refuted** by a single contradicting transition.
- **R4.** Do **all heavy reasoning offline**, emitting vetted plans; never learn by acting when it can
  learn by thinking.
- **R5.** Use a **strong action prior** (behavior cloning + candidate generators) to make search
  tractable, especially for coordinate actions.
- **R6.** Keep an **exact archive and verifier** so model error costs efficiency, never correctness.
- **R7.** **Carry induced knowledge across levels** explicitly.
- **R8.** **Degrade gracefully** to a working non-learned agent.

The current design satisfies R6 and R8 excellently, R5 partly, R4 partly, R7 implicitly, and R1, R2,
R3 poorly.

---

## 5. The design space

Nine candidates, described at the level needed to compare them.

### D1. Cell-level reconstruction-free latent world model *(current primary arm)*

Spatial cell latents, EMA target, action-conditioned predictor, exact auxiliaries, hierarchy,
archive, verifier.

*Strengths:* the research question the project registered; cheap rollouts; the safety machinery
around it is excellent.
*Weaknesses:* sparse-causal-bit problem (§3 of the feasibility doc); bootstrapped supervision at small
data scale; latent geometry unusable as goal cost; rules learned implicitly and not refutable;
objects rediscovered rather than given.

### D2. Cell-level exact delta model

Same skeleton; predict sparse changed-cell deltas with categorical loss instead of latent targets.

*Strengths:* dense ground-truth supervision from step zero; exactness by construction; no collapse
machinery; sparse-delta output is cheap; directly verifiable against observations.
*Weaknesses:* still cell-level, so transfer across layouts relies on the network; rules still
implicit and unrefutable; no goal machinery.

### D3. Compact / discrete (VQ) latent + lightweight decoder

Compact learned state with an exact next-state decoder.

*Strengths:* keeps exactness pressure; reconstruction cannot collapse, so the entire anti-collapse
risk surface disappears; compact planning state; **permits decode → requantize → re-encode rollout
snapping**, a direct fix for latent drift that reconstruction-free arms structurally cannot perform.
*Weaknesses:* decoder cost per expansion; codebook collapse is a milder but real failure mode.

### D4. **Object-slot JEPA** — latent prediction over object slots

Slots from exact connected components; slot features (colour, shape, position, size, relations);
relational transformer encoder; EMA target over slot embeddings; action-conditioned relational
predictor; slot correspondence supplied by the delta parser.

*Strengths:* **preserves the JEPA research question while removing its worst failure mode in this
domain.** A switch is a slot attribute, not one cell in four thousand — so a sparse causal bit now
occupies a proportionate share of the representation and receives proportionate gradient. Permutation
equivariance and relational structure give real transfer across layouts. Rules over slots are the
natural form of the domain's rules. Slot-space distance is far more meaningful than cell-latent
distance.
*Weaknesses:* slot correspondence errors (mitigated by the exact delta parser); games whose relevant
structure is not connected-component-shaped (global symmetry, texture, patterns); variable slot
counts; background/foreground ambiguity.
*Mitigation:* hybrid tokens — slots as the primary carrier for dynamics, with coarse grid tokens
retained as a parallel path. This is already close to the spec's §4.3, inverted.

### D5. Object-relational exact model

As D4 but predicting **exact slot attribute deltas** (which object moved where, what changed colour,
what appeared/disappeared) instead of slot embeddings.

*Strengths:* all of D4's structural benefits, plus ground-truth-anchored dense supervision and exact
verifiability. Predicting "object 3 translates by (0,−1), object 7 toggles state" is compact,
learnable, verifiable, and transfers.
*Weaknesses:* needs correspondence to be right; less "interesting" as a research object.

### D6. Learned exact simulator + deep offline search (AlphaZero-shaped)

Train a model to be a drop-in simulator for exact next-state prediction; run classical search
(A*/beam/MCTS) with a BC policy prior and learned value; archive overrides where known; every executed
step verified.

*Strengths:* maximal exploitation of R4 — search depth bounded only by wall-clock, not by score.
Exact and verifiable. Aligned with the reference class's winning shape. Composes with D2/D3/D5 as the
simulator.
*Weaknesses:* compounding error over deep search unless verified; needs a good value/heuristic;
does not by itself solve goal inference.

### D7. Symbolic rule induction (program induction over transitions)

Typed object-relational rewrite rules: condition (object types, attributes, relations, region) →
effect (translate, recolour, delete, spawn, toggle, merge). Induce by enumeration under a neural
proposal prior, filtered by consistency against every observed transition in the archive.

*Strengths:* extreme sample efficiency (one transition can eliminate a large hypothesis class);
exact; refutable; portable across levels and games; executes at machine speed for deep search;
bimodal failure mode, which the equal-per-game averaging rewards.
*Weaknesses:* DSL coverage is the whole ballgame — games outside the grammar get nothing. Search over
programs is combinatorial. This is where projects of this type die.
*Crucial mitigation:* **the DSL is already half-written.** The spec's §4.2 delta parser enumerates
exactly the transformation vocabulary a rule language needs — translations, rotations, reflections,
recolouring, appearance/disappearance, merge/split, availability changes, irreversibility. The step
from "parser emits transformation hypotheses" to "rules composed of those transformations, filtered by
consistency" is much smaller than it looks.

### D8. Executable goal-predicate induction *(a module, not a competing architecture)*

A grammar of goal predicates over the object graph — quantified relations, counts, region membership,
alignment/symmetry, template match — induced by version-space filtering against level-completion
states, with a cross-game learned prior over predicate classes.

*This composes with every other design and is the highest-value single addition available.* Treated
separately in §6.

### D9. In-context meta-learned agent (algorithm-distillation shape)

Train a sequence model across a large procedurally generated environment population to do in-context
adaptation; deploy as a policy that improves within an episode.

*Strengths:* directly addresses capability 2 and part of 3; strong fit for the "unknown action
semantics" problem.
*Weaknesses:* needs a very large generated environment population to work; provides no goal inference
without reward; hard to verify; the compact-model constraint bites. Best used as a *component* (the
sequence-context module, which the current design already has) rather than as the whole agent.

---

## 6. Head-to-head

Scored against the requirements from §4. ● = strong, ◐ = partial, ○ = absent.

| | R1 object | R2 goals | R3 refutable | R4 offline | R5 prior | R6 exact | R7 cross-level | R8 floor | Build risk |
|---|---|---|---|---|---|---|---|---|---|
| **D1** cell latent *(current)* | ○ | ○ | ○ | ◐ | ◐ | ● | ◐ | ● | medium |
| **D2** cell exact delta | ○ | ○ | ◐ | ● | ◐ | ● | ◐ | ● | low |
| **D3** VQ latent + decoder | ○ | ○ | ◐ | ● | ◐ | ● | ◐ | ● | low–med |
| **D4** object-slot JEPA | ● | ○ | ○ | ◐ | ◐ | ● | ● | ● | medium |
| **D5** object exact delta | ● | ○ | ◐ | ● | ◐ | ● | ● | ● | low–med |
| **D6** learned simulator + search | – | ○ | ◐ | ● | ● | ● | ◐ | ● | low–med |
| **D7** symbolic rule induction | ● | ○ | ● | ● | ◐ | ● | ● | ● | **high** |
| **D8** goal-predicate induction | – | ● | ● | ● | – | ● | ● | – | medium |
| **D9** in-context meta-agent | ○ | ○ | ○ | ○ | ● | ◐ | ● | ○ | high |

My rough estimates for a compact (≈20M-parameter-class) agent, expressed on a public-set-like game
distribution — hidden games should be discounted:

| Architecture | Nonzero progress | Several games advanced past L1 | Multiple games completed end-to-end |
|---|---:|---:|---:|
| D1 cell latent + archive *(current)* | ~80% | ~55% | ~20% |
| D2 cell exact delta + archive | ~85% | ~60% | ~25% |
| D4 object-slot JEPA + archive | ~85% | ~65% | ~30% |
| D5 object exact delta + archive | ~88% | ~70% | ~35% |
| **any of the above + D8 goal induction** | **+3–5pp** | **+10pp** | **+20–25pp** |
| **+ D6 deep search + BC prior** | +2pp | +8pp | +10pp |
| D7 + D8 full neuro-symbolic | ~85% | ~70% | **~50%** |

The pattern to read out of that table: **swapping the dynamics arm buys ~5–15 percentage points.
Adding goal induction buys ~20–25.** The arm question is not where the leverage is.

---

## 7. The single highest-value change: executable, induced goal predicates

If only one change is made, make this one. It is additive, architecture-independent, and attacks the
actual bottleneck.

### Mechanism

**Grammar.** Predicates over the object graph, composed from a small typed vocabulary:

- existence / non-existence: `count(type=T) = 0`, `∃ o: attr(o)=v`
- universal relations: `∀ o ∈ S: R(o, X)` — all keys collected, all blocks on targets
- region membership: `in_region(controlled, Z)`
- relational configuration: `adjacent`, `contains`, `aligned`, `same_colour_as`, `symmetric`
- counting and comparison: `count(S) ≥ k`, `count(A) = count(B)`
- template match: object graph isomorphic to a reference configuration
- change-based: a designated event has occurred

**Induction.** Version-space filtering. A candidate predicate survives if it is *true at every
observed level-completion state* and *false at every observed non-completion state within the same
level*. Rank survivors by a learned prior over predicate classes plus simplicity. Because negatives
are abundant (every state you visited that didn't advance the level) and positives are decisive, a
handful of positives collapses the space fast.

**Cross-game prior.** This is the learnable part, and it is where a small neural component earns its
place: which predicate classes are common, which correlate with which visual signatures. Train it on
the 25 public games (completion states from the 145 replay solves) plus the synthetic suite, where
goal predicates are known by construction. This is a genuinely learnable cross-game regularity, unlike
per-game mechanics.

**Bootstrap.** The chicken-and-egg — you need one completion to induce the predicate — is handled by:
(i) the cross-game prior making the first level's goal a *ranked shortlist* rather than a blank
search; (ii) partial-progress signals (score changes, action-set changes, region unlocks,
irreversible events) as weak positives; (iii) the design convention that level 1 is a tutorial that
teaches the mechanic, so guided exploration completes it at a reasonable rate.

### Why this is worth more than the arm question

Once a goal predicate is executable, three things change at once:

1. **Planning becomes well-posed.** You can run exact search against a checkable target instead of
   ranking candidates by a learned reachability head trained on a proxy.
2. **Levels 2..N become exploitation, and they carry the level-position weight.** The information
   paid for on level 1 is repaid where the points are.
3. **The reachability head's job shrinks to a heuristic**, which is a far easier learning problem
   than being the sole arbiter of goal proximity — and it removes the interface-attribution problem
   that the feasibility analysis flagged as bottleneck 1.

It also converts the project's most likely disappointing finding — *accurate dynamics, no useful
progress*, the last row of the spec's own failure table — into a solvable subproblem rather than a
conclusion.

---

## 8. The second highest-value change: make objects primary

This is the arm substitution proper. Two variants, and I would run both.

### 8.1 The science-preserving substitution: D4, object-slot JEPA

If the goal is to keep studying reconstruction-free latent prediction, **stop doing it over cells and
do it over object slots.**

Concretely:
- Slots from exact connected components, plus a background slot and a global slot.
- Slot features: colour, size, bbox, normalized shape descriptor, centroid, adjacency/containment
  relations, inferred controllability flag.
- Encoder: per-slot embedding + relational transformer, permutation-equivariant, position via centroid
  embedding.
- Target: EMA over the slot encoder.
- Predictor: action-conditioned relational transformer → slot embeddings at t+h, h ∈ {1,2,4,8}, with
  the existing composition-consistency loss carried over unchanged.
- **Correspondence** between t and t+1 supplied by the delta parser's translation/merge/split
  hypotheses — this is the piece that makes object-centric modeling tractable here and impossible
  elsewhere.
- Auxiliaries as before, now at slot granularity: attribute deltas, appearance/disappearance, event
  type, irreversibility.

Why this dominates D1 on the same research question:

- **The sparse-causal-bit problem largely dissolves.** A switch's state is a slot attribute occupying
  a proportionate share of the representation, receiving proportionate gradient — not one cell in
  4096 that the objective is indifferent to losing.
- **Transfer improves structurally**, not by learned invariance: permutation equivariance and
  relational encoding generalize across layouts by construction.
- **Slot-space geometry is more meaningful**, which partially rehabilitates the raw-distance arm in
  the interface comparison and makes the whitened-versus-learned-head ladder more informative.
- **Aliasing risk drops sharply**, because control-distinct states usually differ in a slot attribute
  rather than in a single cell.

This is the recommendation I would make if the project keeps its current scientific identity.

### 8.2 The score-maximizing substitution: D5, object-relational exact deltas

Same representation, exact targets: predict which object moved where, what changed, what appeared. It
is more sample-efficient, exactly verifiable, and directly consumable by the verifier and archive. For
the *deployed* agent, this is what I would ship.

---

## 9. The third change: deep offline search with a behaviour-cloned prior

Cheap, low-risk, and currently underused.

- **BC policy prior** `p(action | state, context)` trained on the 342 replays cross-game. Cuts
  branching factor for every search, and is directly aligned with a metric that normalizes against
  human action counts.
- **Coordinate proposal supervised by human clicks.** The single largest branching problem in the
  action space is ACTION6 over up to 4096 cells; human replays are ground truth for which coordinates
  matter. This turns the coordinate-recall risk (flagged as tripwire in the feasibility analysis) from
  a hand-designed heuristic set into a supervised ranking problem.
- **Search depth as the free variable.** With an exactly-verified model, search until the wall-clock
  budget is spent, then emit a vetted plan. Every unit of thinking is free; every action is not.

None of this requires changing the world model, and it composes with all of D1–D7.

---

## 10. The whole-design substitution: neuro-symbolic rule and goal induction

If the objective were purely "maximize the chance of solving ARC-AGI-3," this is what I would build.

### Layered specification

**Layer 0 — exact, nonparametric (keep from the current spec, unchanged).**
Grid canonicalization; delta parser; connected-component object extraction; object correspondence;
archive multigraph; event detection; exact verifier. This layer is already well designed and should
survive any redesign.

**Layer 1 — rule model, dual implementation with arbitration.**
- *1a, symbolic:* typed object-relational rewrite rules — `condition(object type, attributes,
  relations, region, action) → effect(translate | recolour | delete | spawn | toggle | merge)` — with
  global rules (gravity, timers, propagation) as a separate class. Induced by enumeration under a
  neural proposal prior, filtered by consistency against **every** transition in the archive. One
  contradicting transition eliminates a rule permanently.
- *1b, neural:* the object-relational model from §8 (D4 or D5), as fallback for games the grammar
  does not cover.
- *Arbitration:* run both; track per-game predictive accuracy on held-out recent transitions; use the
  winner, verified either way. Cheap, robust, and it converts "did we pick the right arm" from a
  design decision into a runtime measurement.

**Layer 2 — goal model.** Executable predicate grammar, version-space induction from completion
states, cross-game learned prior over predicate classes, weighted goal beliefs. Per §7.

**Layer 3 — control.** BC policy prior; learned value/heuristic; exact search over archive + Layer 1
model against the Layer 2 predicate; event-level hierarchy where justified; verification and
replanning each step; irreversible-risk veto.

**Layer 4 — meta.** Two-phase per-level strategy (identify → execute) tuned to whichever
reset-accounting regime §3.7 turns out to be; exploration controller maximizing information gain per
scored action; the existing demotion ladder.

### What the neural components do in this design

They **propose and rank; they never decide.** Rule proposal prior, goal-class prior, policy prior,
search heuristic, coordinate ranking. Every one of them is a distribution over a symbolic hypothesis
space that a verifier can check. This is the abstraction of the recipe that demonstrably works on this
benchmark — the large-model verification harness replaces the proposer with an LLM; here it is a
compact model trained on the synthetic suite.

### Honest risk assessment

The failure mode is DSL coverage: games whose mechanics lie outside the grammar get nothing from
Layer 1a. Three things make this survivable: the neural arm 1b is a genuine fallback; the archive
floor is unchanged; and the equal-per-game averaging rewards bimodal competence. The build risk is
real and is the reason this is presented as the alternative rather than the default — but the
increment from the existing §4.2 delta parser to a working rule grammar is smaller than a
from-scratch program-synthesis project, because the transformation vocabulary is already enumerated.

---

## 11. What should not change under any substitution

The current design gets these right and they are architecture-independent:

- the exact archive with **known transitions overriding model predictions**;
- the exact verifier and irreversible-risk veto around every executed chunk;
- the **demotion ladder** (hierarchical → flat → archive graph → conservative frontier);
- the delta parser and its transformation vocabulary;
- the same-candidate oracle audit and the four-rung attribution ladder — this apparatus is the most
  transferable scientific asset in the project and it works for *any* pair of arms;
- the diagnostic contract, especially the refusal to let unchanged-cell accuracy stand in for dynamics
  knowledge;
- the failure-interpretation table;
- the run-integrity and cross-fitting discipline.

Roughly 60–70% of the existing specification survives every substitution proposed here.

---

## 12. Consequences for the research question

Substituting the arm changes what the paper is about, and in my view it changes it for the better.

**Current primary factorial:** prediction target {exact token, latent} × context {Markov, sequence}.
My prediction, stated in the feasibility analysis: a large clean context effect and a small or
ambiguous target effect — i.e. the primary contrast most likely lands *inconclusive*, which the plan's
own power analysis already anticipates.

**Proposed alternative factorial:** representation {cell-level, object-factored} × target {exact,
reconstruction-free latent}, with sequence context held on for all arms and symbolic rule induction
as a reference ceiling.

Why this is a better study:

1. **It is more likely to resolve.** Object factorization should produce a *large* effect in this
   domain, not a marginal one — and a study whose primary contrast resolves is worth more than one
   whose primary contrast is well-designed and inconclusive.
2. **It tests the mechanism that actually matters here.** The interesting question is not "exact
   versus latent" in the abstract; it is "under what representation does reconstruction-free
   prediction become viable in exact discrete environments" — for which the answer "when the
   representation is object-factored, because sparse causal bits become proportionate features" is a
   real, mechanistic, transferable finding.
3. **It keeps latent prediction in the study** rather than abandoning it, which preserves the personal
   objective of building expertise on this line.
4. **The entire evaluation apparatus carries over unchanged** — same interfaces, same audit ladder,
   same metric, same folds, same decision rule. The estimand's *conditions* change; its machinery does
   not.

The cost is honest and should be stated: this is a change to the registered conditions and requires a
dated erratum under the plan's own discipline, and the freeze date passes with the design not yet
frozen.

**The two-track structure resolves the tension between science and score.** Track B (the deployed
agent) can be symbolic-first with a neural fallback; Track A (the controlled study) can continue to
compare representation × target arms under matched budgets. The plan already forbids Track B from
contaminating Track A, so switching the deployed architecture costs the science nothing.

---

## 13. Decision guide

Three coherent paths, depending on which objective dominates.

### Path A — maximize expected benchmark score

D5 (object-relational exact) + D8 (goal induction) + D6 (deep search) + D7 (symbolic rules) as the
primary rule model with the neural arm as fallback. Neural components are proposers only.
*Highest ceiling; highest build risk; weakest fit to the registered research question.*

### Path B — maximize the value of the research result *(my recommendation)*

Substitute the arm to **object-slot JEPA (D4)** against an **object-relational exact (D5)** control,
keep the cell-level pair as the second factor, add **D8 goal induction** and the **BC policy prior**
as agent-side infrastructure shared by all arms. Refactor the primary factorial to representation ×
target per §12.

*Rationale:* it keeps the project's scientific identity and the latent-world-model learning objective;
it removes the failure mode most likely to make the latent arm incompetent; it attacks the actual
score bottleneck through a module that is orthogonal to the contrast and therefore does not
contaminate it; and it produces a primary contrast that is more likely to resolve than the current
one.

### Path C — minimize risk

D2/D3 (cell exact delta, or VQ latent with decoder) + D8 + BC prior + search. Lowest build risk,
solid floor, modest ceiling, and the least interesting paper. Worth naming because it is a legitimate
choice and because it is what the project will fall back to if the arm substitution runs into
trouble.

### If only three things are done

1. **Executable induced goal predicates (§7).** Largest score effect of anything in this document.
2. **Objects as the primary state representation (§8).** Largest architectural effect, and it is what
   makes the latent arm defensible.
3. **BC policy prior + supervised coordinate proposals (§9).** Cheapest large win; directly attacks
   the branching problem and is aligned with the metric by construction.

---

## 14. Risks of these recommendations

Stated plainly, because a recommendation without its failure modes is not usable.

- **Object-centric is not universal.** Games built on global patterns, symmetry, textures, or
  cell-level cellular-automaton rules will not decompose into connected components usefully. The
  hybrid slot + coarse-grid token path is the mitigation, and the fraction of games where objects fail
  should be measured on development games *before* committing, not assumed.
- **Slot correspondence errors propagate.** If the delta parser mis-associates objects across a
  transition, the training target is wrong in a structured, non-random way. Correspondence accuracy
  needs its own validation against the synthetic suite, where ground truth exists.
- **Goal-predicate grammar coverage is the same risk as DSL coverage**, one level up. Games whose
  goal lies outside the grammar get nothing — though they are no worse off than under the current
  design. Measure grammar coverage against the 145 completed replay solves before building on it;
  that measurement is cheap and decisive.
- **The bootstrap problem is real.** Goal induction needs a first completion. On hidden games with no
  replays, that first completion must come from exploration. The cross-game prior helps; it does not
  eliminate the need to solve level 1 the hard way.
- **Symbolic rule induction is where projects die.** I have weighted D7 as high build risk
  deliberately. The dual-implementation arbitration in §10 exists so that a partly-working rule
  induction layer is an asset rather than a sunk cost.
- **Changing the registered design has a scientific cost.** The plan's erratum discipline exists for
  good reasons. A redesign at the freeze boundary is defensible; a redesign after results are viewed
  is not. If any of this is adopted, it should be adopted now, dated, and recorded before any
  confirmatory result exists.
- **Everything here raises the number of components.** The current design's greatest practical virtue
  is that its failure modes are attributable and its floor is guaranteed. Any substitution must
  preserve Layer 0 and the demotion ladder, or it trades a bounded risk for an unbounded one.
