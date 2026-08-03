# GI-2: grounded hypothesis testing

**Date:** 2026-07-30
**Status:** SPRINT A STOPPED AT REPRESENTABILITY (2026-07-30) — A0–A3 measured
through 2026-07-30. Decisions the operator has accepted are marked ACCEPTED; remaining numbers
introduced later must be marked PROPOSED with rationale.
**Responds to:** [gi1-iteration-audit.md](gi1-iteration-audit.md); replaces §8 of
[design-pivot.md](design-pivot.md) if accepted.

---

## 1. Failure model

GI-1 asked one response to do perception, entity naming, rule induction, and logical
composition. The 0/440 entity-field result locates the break. Transcript autopsy
(`logs/gi1_iteration_27b_raw.jsonl`, audited) adds mechanism:

- **Completion deltas were read as activity, not as an achieved condition** — on ft09 the gold
  class was in (b)'s top-3 at every zero-completion checkpoint and dropped at every completion
  checkpoint, replaced by transformation/count narratives. Hence 93% → 28–33%.
- **Scene narration replaces mechanics** — dc22's top hypotheses describe an invented
  panel-matching story; the controlled player never appears as a subject.
- **Binding fails independently of class** — 102 correct-class hypotheses still produced 204
  strictly-wrong entity fields.
- **The class prior has a structural blind spot** — (e) scored 0% on m0r0, whose class is
  unique in the pool; 83.3% top-3 is an average over games whose classes recur.

This is a semantic grounding failure, not a scoring or formatting failure (parse validity
92.7–96.4%; blind equivalence review changed nothing).

## 2. Machine components

### 2.1 Trace evidence: terminal frames already exist

Human recordings retain **every frame returned by an action**; GI-1's packet layer kept only
`frame[-1]` and therefore discarded the solved board. Verified 2026-07-30 across **all 18
selected iteration sessions — 123 completions, all six games** (operator extension of the
initial nine-session check). Illustrative structure:

- non-final completions: 2 frames, `state: NOT_FINISHED` — solved terminal then next-level
  board (dc22, ls20);
- final completions: 1 frame, `state: WIN` (dc22 level 6/6, ls20 level 7/7);
- tu93: 9–14 frames per completion (terminal animations), final `WIN` with 13 frames.

Extraction rule:

```
if state == WIN:  terminal frame = frame[-1]
else:             terminal frame = frame[-2]; next-level frame = frame[-1]
```

with all earlier frames in the list retained and tagged as intermediate animation.

Consequences:

- **A new GI-2 trace extractor** (`gi2_traces.py`) supersedes `gi1_packets.py` for this sprint;
  the frozen GI-1 module is not modified. The extractor keeps all returned frames with roles
  (intermediate / solved terminal / next-level initial) and validates the rule per row.
- Predicates are evaluated **directly on the observed solved frame** — no counterfactual
  (pre-terminal ∘ action) evaluation is needed for observed completions.
- The platform returns 1–N frames per action in deployment too, so there is no deployment
  asymmetry — but the advisor integration must capture full frame lists outside the vendored
  harness, which currently also keeps only the last frame. Integration note for E4.
- **Source replay is needed only for negative forks.** Fidelity comparisons cover **all
  returned frames**, not merely settled ones.

### 2.2 Observation layer: handles with groups and lineage

Tracks assign every visible object a stable ID and a description:

```
o12: blue L-shaped mover, bbox [18,4–20,6]
o17: yellow patterned tile, bbox [3,28–5,30]
```

Four-connected color components are not necessarily objects. The layer must represent:

- **multicolor composite objects** (grouped by co-movement and persistent adjacency);
- **split/merge events**, with lineage links between parent and child handles;
- **recoloring** (same object, new color — not a delete/create pair);
- **occlusion or replacement**;
- **one action controlling several linked objects**.

Group handles (`g3 = {o12, o14, o15}`) are first-class citizens alongside object handles.
Role tags from action correlation: `controlled`, `click-responsive`, `autonomous`, `static`.
Each ID gets a visual crop or highlighted frame (upscale 4, reusing the render layer). The
action-effect catalogue records per (action, class) observed delta type and frequency, and is
gated before use (§3).

Qwen, wherever it appears, **selects handles**; it never generates entity descriptions.

### 2.3 Terminal contrasts, not terminal summaries

For every human completion, the evidence is a contrast set:

- the board immediately before the completing action;
- the completing action;
- the **observed solved terminal frame** (§2.1);
- alternative valid actions from the same state that do **not** complete (negative forks,
  produced by the replay driver over local game source, runnable under `arcengine`);
- facts true only on the successful branch;
- earlier states where similar relations existed without completion.

Positive completions alone cannot distinguish "reach the goal," "remove everything," "match a
template," and correlated incidental conditions; the forks can.

**Bounded MOUSE-fork policy (ACCEPTED as amended).** `MOUSE` is thousands of coordinates, not
one alternative action — and raw changed *cells* are unbounded too, so the set uses
deterministic representatives only:

- the centroid of every atomic handle, plus one canonical boundary cell per handle
  (ACCEPTED canon: lexicographically smallest (row, col) boundary cell);
- a member medoid per group;
- one centroid per **connected changed region** of the most recent delta.

Centroids and changed-region centroids **snap to the nearest member cell, with lexicographic
tie-breaking** (ACCEPTED clarification), so concave objects or regions never produce
background coordinates. Deduplicated; realized fork counts reported in Sprint A.

**Replay fidelity.** Replayed frame lists must reproduce the recorded frame lists. Per-game
fidelity is reported; a game failing fidelity falls back to recorded-positive-only evidence
and its identification claim is flagged as weakened. S1's REPLAY-DET governs what replay
determinism may be assumed at deployment.

**Deployment mapping.** Source replay is a development instrument, and fork evidence is an
**oracle upper bound, not the deployment condition** — exhaustive alternative actions are
unavailable online. In competition, negatives arrive free from the trajectory body
(non-completing actions near terminal states); resets cost actions under the (human/agent)²
score, so fork-by-reset is a last resort. Identification is therefore gated and reported in
two arms (§3), and the dev-time forks measure how much negative evidence identification
needs.

### 2.4 Compositional DSL and version space

The GI-1 predicate schema cannot remain unchanged: its flat per-class fields pack nested
logic into entity strings (tu93 "all movers overlap exits"; vc33's same-color receptacle with
lateral alignment and supporting platform; ft09's conditional neighborhood template).

GI-2 defines a **versioned compositional DSL** (`GIDSL v1`) with object-set handles,
quantifiers, and nested relations:

```
all(m in movers, exists(e in exits, overlapping(m, e)))
all(i in items,  exists(r in receptacles, same_color(i, r) and aligned_lat(i, r) and flanks(r, support(i))))
count(active_movers) == 0
```

- **The grammar is finite, not recursive.** GIDSL v1 enumerates class-specific AST skeletons
  with declared maximum nesting and arity, canonical deduplication, and per-game reporting of
  candidate counts and generation runtime — an unrestricted recursive grammar over handles,
  sets, quantifiers, and conjunctions would be combinatorial. Caps are **decided during A0**
  (ACCEPTED): A0 defines the normative GIDSL specification before writing GIDSL gold and
  produces a table of each class skeleton, maximum nesting/arity, the six gold AST sizes, and
  resulting candidate counts. At A0, counts are finite **structural instantiations over each
  game's declared authoring vocabulary**; A3 must separately report the realized count over
  extracted handles. Those caps are **frozen before A3 runs the miner**. A0 defines the
  language and gold; A3 implements its handle-grounded generator, verifier, and scorer. This
  resolves the sequencing circularity between language definition and gold authoring without
  pretending that A0 already has A2's handles.
- The ten legacy class labels remain as tags on templates; a **legacy adapter** reports class
  accuracy in the old terms for comparability with GI-1's logged numbers.
- The GI-1 parser/scorer do **not** apply. A **new mechanical grounding scorer** compares DSL
  ASTs under declared syntactic canonicalizations (ACCEPTED): alpha-renaming of bound
  variables, associative flattening and sorting of `and`/`or`, symmetric-operator argument
  ordering, and extensional set equality over member handles — canonicalizations, not
  subjective equivalences. Gold is re-expressed in GIDSL and grounding annotations map each
  gold entity to its observable component or component group; both are Sprint A deliverables
  (§8), available before the Sprint A read.
- Candidates are generated mechanically over handles; survivors are candidates consistent with
  the solved terminal frame, every negative fork, and the trajectory body. Ranking:
  cross-completion/cross-level consistency of the lifted template → discrimination →
  simplicity.
- **The class prior orders template instantiation; it never filters** (ACCEPTED). All
  templates evaluate by default; prior-top-k-only runs as an ablation.

Qwen may rank survivors, explain ambiguities, or propose the next probe. It never invents the
candidate vocabulary. The verifier-only posterior is measured as its own row (B0).

### 2.5 Retrieval: deferred

GI-1's board-histogram features capture visual similarity, not goal mechanics — consistent
with retrieval reducing class accuracy. Cross-game retrieval is suspended until grounded
predicate/event signatures exist, and is out of scope for GI-2's sprints.

## 3. Sprint A — representability and observability (zero model calls)

Build the trace extractor, object tracks, terminal contrasts, and GIDSL for the six iteration
games. Iteration GIDSL gold (A0) and grounding annotations (A3) exist **before** the Sprint A
read — representability, identifiability, and gold rank all consume them, so they cannot be
Sprint B deliverables. Measure, per game:

- extraction-rule validation and replay fidelity over all returned frames;
- **representable** — the gold predicate is expressible in GIDSL **and every gold entity maps
  to an observable component or component group** in the tracks, not merely something named in
  source;
- **identifiable — two arms, gated and reported separately:**
  - **trajectory-only** (the deployable condition): recorded trajectory, observed
    completions, and the free negatives the human actually produced;
  - **trajectory + exhaustive forks** (the oracle headroom);
  each with its ambiguity curve (surviving-set size at 1/2/3 completions) and gold's rank
  under the mechanical ordering;
- **catalogue decision-level validity (ACCEPTED, operator-specified as a global paired
  gate)** — for each session-held-out state, with the action selected **without access to
  that state's fork outcomes**:

  ```
  lift = actual elimination(selected action)
         − mean actual elimination(all legal candidate actions)
  ```

  The catalogue passes for Sprint C only if the game-balanced mean lift is positive **and**
  lift is positive in at least 4/5 zero-completion iteration games (vc33 has no
  zero-completion rows). Per-game results remain diagnostic — a per-game gate would let the
  catalogue operate only where it happened to pass, a condition unavailable on a hidden game.
  Passing is the precondition for using "expected elimination" in Sprint C, which is
  otherwise not mechanically defined.

**Funding gates (ACCEPTED): representable on ≥ 5/6, identifiable on ≥ 4/6** — the
identifiability gate reads on the **trajectory-only arm** (ACCEPTED). **If only the
fork arm succeeds, continuation depends on Sprint C showing that sequential probes recover
enough evidence within the 30-action budget** (operator rule). The stop rule stands: stop if
the correct rule cannot be represented or cannot be identified from observable evidence;
identification failing despite representability is an evidence-insufficiency stop, not a
coding task.

### 3.1 A0 measured result (2026-07-30)

A0 is complete and model-free:

- [`gi2_frame_validation.json`](../logs/gi2_frame_validation.json) reproduces the frozen
  session selection and validates **6 games, 18 sessions, 123 completions**. Observed
  completion response structures are `NOT_FINISHED:2` ×81, `NOT_FINISHED:9` ×9,
  `NOT_FINISHED:14` ×15, `WIN:1` ×15, and `WIN:13` ×3. Every extracted terminal and
  next-level frame is individually digested.
- [`gi2_replay_environment_freeze.json`](../logs/gi2_replay_environment_freeze.json) pins
  the six source and metadata files, 18 normalized action streams, engine implementation
  files, reset semantics, `arcengine` distribution 0.9.3, and `arc-agi` 0.9.9. The local
  wrapper requests seed 0, but all six game constructors omit a seed parameter, so the
  effective seed is explicitly recorded as null rather than falsely reported as controlled.
- [`gi2_gidsl_v1_spec.json`](../logs/gi2_gidsl_v1_spec.json) freezes finite skeletons and caps
  for all ten legacy classes.
  [`gi2_gidsl_gold_iteration.json`](../logs/gi2_gidsl_gold_iteration.json) contains the six
  iteration predicates, validates each against the class draw and the sole source
  `self.next_level()` site, and reports gold AST sizes of 2–15 nodes. The A0 structural
  candidate counts over declared authoring vocabularies are dc22 2, ft09 1, ls20 6, m0r0 2,
  tu93 2, vc33 14. A3 must still report realized counts over extracted handles.

This result validates the frame rule, replay inputs, and **syntactic** representability of the
six authored predicates. It does not claim replay fidelity, observable handle grounding,
trajectory-only identifiability, or fork-oracle identifiability; those remain A1–A3 measurements.

### 3.2 A1–A3 measured result (2026-07-30)

Sprint A stopped at its first predeclared funding gate:

- **A1 replay fidelity:** exact over every returned frame for dc22, ft09, ls20, m0r0, and
  tu93 — 15/18 sessions and 8,711 recorded action rows. vc33 diverged by two cells in each
  selected session (first at steps 138, 185, and 166), so it is positive-only and supplies
  no replayed negatives. `full_reset` metadata differs on the first row of every session;
  ft09 also advertises all six actions in the recordings while its frozen local source
  advertises only MOUSE. Neither metadata difference changes the exact-frame fidelity gate.
- **A2 observations and contrasts:** 9,913 action rows produced 1,141,870 atomic-component
  observations. The five fidelity-passing games supplied **102 completion states, 8,928
  alternative forks, 8,889 negatives, and 39 alternative completions**. Branch grids are
  retained losslessly as zlib+base85 (4.1 MB); effect-count summaries alone were insufficient
  for a predicate verifier.
- **A3 strict grounding:** dc22, m0r0, tu93, and vc33 pass. ft09 fails because 3/22 clue
  entities never form an exact observable component/group. ls20 fails because 1/8 goal
  entities never maps to an observable component/group anywhere in its track. The result is
  therefore **4/6, below the accepted 5/6 representability gate**.
- Enumerating generic dense local component groups does not rescue the gate cleanly: the
  checkpoint registry reaches 3,948 groups on ft09 and 5,809 on tu93. This is finite, but not
  a useful bounded hypothesis vocabulary.

The machine-readable verdict is
[`gi2_sprint_a_results.json`](../logs/gi2_sprint_a_results.json). Per the stop rule in §3,
trajectory-only and fork-oracle identifiability were **not run after representability failed**;
their values are null, not failures disguised as zero. The v3 fork grids remain available if
the observation/group representation is redesigned later.

### 3.3 Post-stop forensics and diagnostic identifiability (2026-07-30, exploratory)

Operator-commissioned after the stop; both passes are **exploratory and non-funding** — the
5/6 gate verdict is unchanged, no one-shot game touched, zero model calls. Artifacts:
[`gi2_grounding_forensics.json`](../logs/gi2_grounding_forensics.json) and
[`gi2_diagnostic_identifiability.json`](../logs/gi2_diagnostic_identifiability.json), both
with deterministic `--verify` rebuilds.

**Forensics — the four failures have exact mechanical causes:**

- **vc33's fidelity failure is cosmetically transient.** One action row per session (the
  level-4 completion click) diverges on 12 contiguous *intermediate* frames; every divergent
  cell is the same substitution (recorded colour 11 → replayed 14, 84 cell-instances per
  session); **no settled, solved-terminal, or next-level frame differs anywhere**. A
  settled-frame fidelity criterion would rescue vc33's replayed negatives as a dated erratum.
- **ft09's three clues are exactly maximal connected non-background regions** partitioned by
  their nine pure 2×2 components (`region_equals_sprite=true` for all three). The generative
  rule "adjacency-connected multicolor composite" grounds them with no per-game tuning and
  replaces the dense grouping that exploded to 3,948–5,809.
- **ls20's failing goal is a same-colour-as-socket merge**: 19 visible tile pixels + a
  24-cell surrounding frame form one 43-pixel component at purity 0.442 (< 0.5); the other
  seven goals ground only because their colours differ from the frame. Fixing it needs
  ring/containment decomposition — generative but new.
- ft09's recordings advertise six actions while the frozen local source advertises MOUSE
  only, and `full_reset` differs on first rows — version-skew signals worth carrying.

**Diagnostic identifiability (grounded games, structure sweep with sets fixed to gold):**

- **Set description is now the binding bottleneck (3/4 games).** Under history-free
  appearance features (≤2-term conjunctions), gold sets bind on tu93 only. m0r0's
  `active_movers` spans four sprite variants — it needs **unions**, which the planned
  conjunctive language cannot express (planned curve 0/0/0 even with `role`). dc22's
  `goal_tiles` is appearance-ambiguous and binds only via `role` (excluded from
  verification because single-step fork registries cannot supply it). vc33's sets stop
  binding at three completions even with `role` (curve 12/2/0).
- **Where sets bind, the verifier machinery behaves correctly** — tu93's gold candidate has
  trajectory satisfaction 0.0 and rejects all 81 replayed negatives — **but frame-only
  evaluation is blind at the solved state**: the mover covers the exit, the exit's extension
  is empty exactly when the relation is satisfied, and the gold evaluates false. The
  verifier instead converges on the observable consequence (`empty_set` over the exit-like
  descriptor ranks first; 125–128 survivors).
- **Object permanence at evaluation time is the missing mechanism**: §2.2 already requires
  occlusion handling in tracking; evaluation registries must carry occluded tracked objects
  (last-known cells) — or evaluation must run on (pre-terminal ∘ action) — for relational
  golds to be verifiable at solved frames.

Together with §3.2 this itemizes the full remediation menu with measured causes: composite
grouping (rule measured exact), ring decomposition, descriptor unions + role-capable
evaluation registries, and evaluation-time permanence — versus letting the stop stand. That
routing decision remains the operator's under the pre-registered rule.

**Routing decision (operator, 2026-07-30): Option A′ — one pre-registered remediation
round with the observational-equivalence success definition. Rules pre-registered before
implementation (§3.4).**

### 3.4 Sprint A-R pre-registration — FROZEN 2026-07-30

**Operator freeze (2026-07-30): U = 4, θ_occ = 1.0, top-3, and the vc33 settled-frame
fidelity erratum are all ACCEPTED.** vc33 is therefore fork-eligible and this round
regenerates its forks; changes below this line after this date would require a dated
erratum.

One remediation round of the observation/description/evaluation layers, then one rerun of
the Sprint A gates. **A second failure of either gate is a permanent stop for
goal-inference-from-replay-evidence, and the budget routes to the action-semantics
artifact.** No rule below may be added to, tuned, or reinterpreted after this section is
frozen; iteration slice only; one-shot and reserved games sealed; zero model calls.

**R-1 — Composite grouping (promoted from the diagnostic, measured exact on ft09).**
Atomic components stay as A2 defines them. The group vocabulary becomes adjacency
composites of non-background components at exactly two granularities: adjacent pairs, and
maximal adjacency-connected clusters. Non-background = not the modal colour of the frame.
The dense local compaction is retired everywhere.

**R-2 — Ring/containment decomposition (ls20's cause).** A component whose cells contain
the full perimeter of its own bounding box, with nonempty remainder, decomposes into two
derived registry objects: the perimeter ring and the interior remainder (re-segmented by
connectivity), each with lineage to the parent. Applied once per component, not
recursively. No colour or game constants.

**R-3 — Descriptor unions (m0r0/vc33/dc22's cause).** Set descriptors become disjunctions
of at most **U = 4** conjunctions (PROPOSED; calibration rule: the minimal U covering all
six iteration golds — m0r0's four sprite variants set the bound), each conjunction at most
two feature terms over (kind, colors, shapes, pixels, bbox_size, role). `role` is
admissible everywhere because of R-4. Selection: minimal total terms, then the existing
complexity/lexicographic ordering; extensional deduplication unchanged.

**R-4 — Role-capable, permanence-capable evaluation registries (dc22's and tu93's cause).**
Every evaluation registry derives from the maintained session tracker — never from a fresh
single-frame tracker. Fork states: deepcopy the tracker at the fork point, update once with
the fork result frame. Occlusion carryover: a track visible at t−1 and unmatched at t is
retained with its last-known cells, colours, and role, flagged occluded, **iff** all of its
last-known cells are covered by non-background cells of current components (θ_occ = 1.0,
PROPOSED — strictest; distinguishes occlusion from destruction so that m0r0's merged movers
still count as removed); dropped at level reset or reappearance. Occluded objects
participate fully in sets and relations.

**R-5 — Gates and the A′ success definition.**
- Representability gate unchanged: every gold entity maps to an observable component,
  group, or R-2 derived object; **≥ 5/6 games** (ACCEPTED previously).
- Identifiability gate as originally planned: **≥ 4/6 on the trajectory-only arm**
  (ACCEPTED previously), fork arm reported as oracle headroom.
- **A′ success predicate**: a game is identifiable if the gold candidate, **or a candidate
  observationally equivalent to it**, survives verification and ranks in the **top 3**
  (PROPOSED; matches the design's top-three posture). Observational equivalence is
  mechanical: identical truth values to permanence-evaluated gold at every evidence state
  of the game (all solved states, all sampled trajectory states — stride cap 40/session,
  carried from the diagnostic — and all fork branches). No rater judgment.
- Before the measured rerun, a freeze artifact pins the R-1..R-4 implementations, the
  scorer, and this section's digest — the GI-1 lesson that a repaired contract is not a
  pre-run contract.

**R-6 — Parallel, non-gating measurement.** The action-effect catalogue's global paired
lift gate (§3, operator-specified) runs in the same round on session-held-out fork tables.
Its result routes Sprint C later and informs the fallback if this round fails; it does not
affect this round's gates.

**Operator decision required at freeze, alongside U, θ_occ, and top-3:**
- **vc33 settled-frame fidelity erratum — accept or reject.** The forensics showed vc33's
  divergence is confined to intermediate animation frames. If accepted as a dated erratum
  (a session is replay-faithful when all settled, solved-terminal, and next-level frames
  match; intermediate-only divergences are flagged), vc33 becomes fork-eligible and this
  round regenerates its forks; if rejected, vc33 stays positive-only, trajectory-arm-only.

Estimated effort: R-1 ≈ 0 (promotion), R-2 ≈ 0.5 d, R-3 ≈ 0.5 d, R-4 ≈ 0.5–1.5 d (the one
unsized item: whether A2's tracker already retains occlusion lineage internally — the first
implementation task is that one-hour inspection), scoring + rerun + read ≈ 1 d. Total
≈ 2.5–3.5 d, zero model calls.

### 3.5 Sprint A-R measured result — SECOND FAILURE, PERMANENT STOP (2026-07-30)

**Both gates failed on the measured pass** (`logs/gi2_sprint_ar_results.json`, freeze
`logs/gi2_ar_freeze.json`): representability **3/6** (dc22, m0r0, tu93; required 5),
trajectory-only identifiability **0/6** (required 4). Per the frozen §3.4 rule this is the
second failure: **goal-inference-from-replay-evidence stops permanently and the budget
routes to the action-semantics artifact.**

The verdict is rule-forced, not implementation-limited — the bound is arithmetic:

- **ft09** cannot represent under frozen R-1: on levels where the modal colour differs, a
  non-background field bridges clues into ~34-member clusters, and the needed
  intermediate-size group is neither an adjacent pair nor a maximal cluster.
- **vc33** cannot represent under frozen R-1: items containing modal-coloured parts are
  excluded from the composite pool, so their exact groups can never form.
- With two games rule-blocked, representability tops out at 4/6 < 5 under any
  implementation; with **m0r0** also rule-blocked on identifiability (a consumed mover
  remains visible with features identical to an active one — no frozen appearance
  conjunction separates them), identifiability tops out at 3/6 < 4.

Implementation corrections during bring-up, each justified from the frozen text and
documented (bring-up artifacts were discarded before the measured pass): occluded
carryovers excluded from sprite grounding (visible-pixel semantics; restored tu93 and one
m0r0 state). Two further text-faithful corrections were identified but **not applied,
because the bound above makes them unable to change either gate**: restricting R-2 to
genuine frames (a solid rectangle is not "a closed frame around an interior", so its
ring/interior ghosts should not pollute registries) and including occluded carryover ids in
per-state gold extensions (R-4's "participate fully in sets"). They are recorded for any
future observation-layer reuse.

What the round measured positively: the vc33 settled-frame erratum machinery worked (981
forks regenerated, 21/21 completions authorable); permanence, composite, ring, and DNF
primitives are unit-tested (9 tests); the failure inventory for grounded goal inference is
now complete across three independent formulations (LLM generation, frame-observable
verification, appearance-descriptor binding).

**GI-2's goal-inference thread is closed.** The reusable estate — replay driver, fork
tables (plus vc33's), trace extractor, observation layer, permanence tracker, GIDSL — feeds
the action-semantics sprint next.

## 4. Sprint B — oracle decomposition

On the same games, factor the task with the 27B-8bit model (MoE stays development-only):

| Arm | Given | Asked | Metric |
|---|---|---|---|
| B1 | oracle class + handle menu | select the relevant objects | handle accuracy |
| B2 | oracle objects + relation menu | select relation/transformation | relation accuracy |
| B3 | full generated candidate list | rank; top-3 | exact GIDSL predicate accuracy |
| B0 | — (no model) | verifier ranking alone | same metrics, free |

Interpretation: B1 fails → grounding fails even with a menu; B1 passes, B2 fails → rule
induction is the wall; B1+B2 pass, B3 fails → composition/search belongs to the verifier
permanently. GI-1 could not distinguish these.

All arms are scored by the new grounding scorer; oracle inputs are the Sprint A grounding
annotations, already built. Per the avoid-list, no new equivalence rules.

**Two gate regimes initially (ACCEPTED):** 6 games × 3 sessions × 2 regimes × 3 arms =
**108 calls**, well under one overnight at 8.3 tok/s. Full five-checkpoint coverage only if
the first read is ambiguous.

## 5. Sprint C — active probing at zero completions

Static exact-goal accuracy at action 10 may ask for unavailable information; the useful output
before any completion is a small candidate set, the cheapest legal probe, the predicted
observation under each candidate, and the posterior update after executing it.

Compare three probe selectors from the same state and candidate set:

1. deterministic candidate elimination (max expected elimination under the gated catalogue);
2. Qwen-selected probe (handles + candidates in context);
3. simple information-gain selection.

Execute proposed actions in the replay driver and measure **actual** elimination, reported as
an **elimination curve over the action budget** (ACCEPTED), not only the endpoint.
**Budget: 30 actions (ACCEPTED).** MOUSE probes draw from the bounded fork policy (§2.3).
Five games carry valid zero-completion rows (vc33 does not).

Selectors 1 and 3 run only where the catalogue gate (§3) passed; if it fails broadly, Sprint C
degrades to Qwen-probe versus a random-probe control (ACCEPTED) — labelled **exploratory**,
because it cannot by itself validate the deterministic advisor.

**Inspection tools deferred until after B/C (ACCEPTED).** Sprint C's Qwen-probe arm is the
minimal first test of Qwen-as-investigator; the fuller tool interface (crop requests,
trajectory queries, relation queries, contrast queries, consistency queries) is the target API
if B and C show staged competence.

## 6. After the sprints

Only if A, B, and C support it: freeze the new design and expose the one-shot games once.

- **Replay-environment freeze (required before measured Sprint A outputs):** per-game
  environment-source digests (already pinned in gold provenance), seeds, action-data digests,
  `arcengine` **distribution metadata 0.9.3** and `arc-agi` 0.9.9, and reset semantics. The
  freeze must read distribution metadata, not `arcengine.__version__`, which incorrectly
  reports 0.1.0 (verified 2026-07-30).
- **Ledger unchanged:** the 15 one-shot games are still clean; reserved games stay untouched,
  never replayed, never annotated. One-shot contrasts are generated post-freeze by the frozen
  pipeline with no human inspection of intermediate outputs before scoring.
- **E2 mapping, refined** (from `s1d_corpus_pooled.json`, non-reserved): of the 39
  `goal_unknown` episodes, 18 stalled at level ≥ 2 and have own terminal evidence. These split
  into **14 one-shot episodes across nine games — the only confirmatory evidence — and 4
  development episodes (m0r0 ×1, vc33 ×3), scored separately and reported as diagnostic
  only.** The 21 level-1 stalls are the active-probing population, scored on candidate-set
  reduction and handle/role identification, not on fabricated predicates.
- **E4 unchanged in shape:** advisor payload is the surviving predicate set (post-completion)
  or handle menu + probe plan (zero-completion); model-free at runtime except optional
  survivor ranking.

## 7. Explicitly not doing

Per the operator avoid-list: no additional equivalence rules, no additional replay sessions,
no learned heads, no further tuning of the GI-1 digest/retrieval prompts. Retrieval deferred
per §2.5. The GI-1 raw log remains the frozen comparison baseline.

## 8. Order of work (PROPOSED estimates)

| Step | Content | Est. |
|---|---|---:|
| A0 · **complete** | GI-2 trace extractor + machine-readable frame-validation artifact (18 sessions / 123 completions) + replay-environment freeze block + **normative GIDSL spec with caps table** + **iteration GIDSL gold** | measured |
| A1 · **complete** | replay driver (forks only) + all-frames fidelity check | measured |
| A2 · **complete** | tracks, groups, lineage, roles, crops, catalogue + exhaustive fork table | measured |
| A3 · **stopped at gate** | GIDSL runtime, canonical grounding scorer, legacy adapter, grounding annotations, Sprint A read | measured |
| B | oracle arms and scoring + ≈108 calls | 1 d |
| C | probe selectors + replayed execution + elimination curves | 1–1.5 d |

≈ 8–10.5 dev days before the freeze decision. GIDSL gold and grounding annotations moved from
Sprint B into A0/A3 because the Sprint A read consumes them — nothing in Sprint A is scored
against gold built later. Sprint A alone (≈ 6–8 d) carries the stop rule and spends zero
model calls.

## 9. Decision state

**Accepted by the operator (2026-07-30):** prior orders templates, never filters · Sprint B
at two regimes initially · inspection tools deferred until after B/C · 5/6 representability
and 4/6 identifiability as development funding gates · 30-action Sprint C budget reported as
an elimination curve · decision-level catalogue gate on session-held-out fork tables (§3) ·
Qwen-vs-random Sprint C fallback, exploratory only (§5) · GIDSL syntactic canonicalizations:
alpha-renaming, associative flatten/sort of `and`/`or`, symmetric-operator ordering,
extensional set equality (§2.4) · MOUSE-fork deterministic representatives (§2.3) ·
identifiability gated and reported in trajectory-only and fork-oracle arms, with fork-only
success routing continuation through Sprint C (§3).

**Resolved by the operator (2026-07-30, final):** skeleton caps decided during A0 via the
caps table, frozen before A3 (§2.4) · trajectory-only 4/6 funding gate accepted — deployment
evidence funds; fork-oracle success is headroom routed through Sprint C (§3) · boundary-cell
canon accepted with nearest-member-cell snapping, lexicographic ties (§2.3) · catalogue gate
is a global paired lift gate: game-balanced mean lift > 0 and positive lift in ≥ 4/5
zero-completion games, selection blind to the held-out state's fork outcomes (§3).

**No design decisions remain open.** A0 additionally turns the 18-session/123-completion
frame check into a machine-readable validation artifact rather than prose evidence.

---

## 10. Dated addendum — 2026-08-03: prospective ES-only supersession of the §3.4 stop

Appended cross-reference. Nothing above this line is modified; §3.4/§3.5 remain the accurate
historical record and their frozen text is untouched.

The operator decision of 2026-08-03, recorded in the header of
`notes/qwen-evidence-sufficiency-screen.md` and registered as `ES-GOV-2026-08-03` in
`docs/README.md`, prospectively supersedes the §3.4 permanent stop **for the ES protocol only**
(`ES-IDENT`, `ES-USE`, conditionally earned `ES-VALUE`, under their own caps and freezes; numeric
authority `gate_manifest.yaml → es`). Grounds: the stop's evidential basis was the frozen
observation grammar's representability failure and unmeasured identifiability, and ES makes
grammar coverage and replay identifiability measured, gated prerequisites before any model claim.
This addendum reopens no other formulation, does not reinterpret the Sprint A / A-R results, and
leaves the routing of the Sprint A budget to the action-semantics artifact unchanged. The reusable
estate listed in §3.5 is consumed by ES as read-only, versioned dependencies (ES note §8).
