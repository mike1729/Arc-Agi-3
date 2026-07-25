# ARC-AGI-3 × Sequential–Hierarchical World Models — Research and Execution Plan

**Frozen 2026-07-23.** Design and decision rules are fixed. W1–W2 may fill only predeclared
operational fields: verified platform constants, `task_manifest.yaml`, `gate_manifest.yaml`, fold
manifests, seeds, data snapshots, tuning budgets, latency measurements. Any change to the estimand,
conditions, endpoint, split logic, or decision rules requires a dated erratum. Dated
literature/baseline updates may be appended freely provided they change none of the above.

**Standing rules.** No claim tagged `[verify]` becomes a constant, gate threshold, or paper claim
before primary-source audit. Manifests are committed before any result they govern is viewed. "TRM"
throughout means Trajectory Reachability Metrics.

**Companions.** [`arc-agi-3-executive-summary.md`](arc-agi-3-executive-summary.md) (posture,
priors, expected outcomes) and
[`arc-agi-3-ship-jepa-x-architecture.md`](arc-agi-3-ship-jepa-x-architecture.md) (component
specification).

Where the two source drafts of this plan diverged, the frozen quantitative spine governs: three
training seeds per confirmatory condition (not two), the objective-family × context factorial as the
ARC confirmatory core with hierarchical arms held in the synthetic factorial and behind G4, and the
paired easy/stress boundary suite rather than a full factorial over the axis levels. The wider axis
levels, hypothesis set, metric taxonomy, and success criteria from the research draft are retained in
full below.

## 1. Purpose and posture

The project develops and evaluates a compact agent for unfamiliar, instruction-free, interactive grid
environments. The central hypothesis is that effective control requires both:

- **sequential inference**, to infer environment-specific mechanics and hidden state from interaction
  history;
- **temporal hierarchy**, to reduce long-horizon search through grounded intermediate events.

A learned model is not trusted as the sole record of discrete state. The agent retains exact
observations, exact transition deltas, and a persistent transition graph. Latent prediction supplies
abstraction and transfer; exact memory supplies identity, contradiction detection, and execution
safety.

Primary goal: durable expertise and a public repo. Secondary: one controlled, predeclared result on
world-model objective families for interactive discrete environments. Tertiary: paper award.
Non-goal: leaderboard placement.

Honest floor: a working submission plus an engineering report. A *defensible* scientific result
additionally requires the Track-A spine to survive intact — it is the secondary goal, not the floor.

Track B never contaminates Track A: agent iteration and confirmatory science share a codebase, not
a critical path.

### Primary deliverables

- reproducible environment and evaluation harness;
- procedural boundary suite;
- exact archive and graph baseline;
- sequential exact, reconstructive, and latent world models;
- grounded event-level planner;
- held-out ARC-AGI-3 evaluation;
- public code, manifests, and research report;
- working competition submission.

### Non-goals

- claiming that one implementation represents every token or latent objective;
- treating public-game performance as hidden-environment generalization;
- building a general symbolic program synthesizer;
- unrestricted latent macro-action learning;
- adding every recent JEPA extension;
- optimizing for leaderboard position at the expense of the controlled study.

## 2. Hard constraints and W1 verification items

**Dates.** Milestone 2 Sept 30 (optional) · entry and team-merge Oct 26 · final submission Nov 2,
23:59 UTC · paper by ~Nov 5 (ties favor earliest; hard deadline Nov 8) · results Dec 4.

**Platform.** Sandboxed, no internet; CC0/MIT-0 release required; 5 submissions/day; parallel
stateless game threads over one shared batched-inference GPU (RTX 6000 reserved for this
competition).

**Environment.** Observations contain 1–N grid frames plus metadata; grids are up to 64×64 with
integer cell values 0–15. Actions: RESET, ACTION1–5, ACTION6(x,y), and ACTION7/Undo where
advertised by available-action metadata.

**Official metric.** Per level, (human actions / agent actions)² capped at 1.15, level-position
weighting, equal averaging across games.

**W1 verification list.**
- RESET accounting and its archive consequences (competition mode permits level resets only).
- Itemized per-action latency: preprocess · encoder · branching × depth · ensemble · verification ·
  policy · optional TTT step · synchronization.
- Runtime envelope: ~8 h wall-clock and ~10 actions/s are working assumptions; the documented
  figure is a 600 req/min API limit. `[verify]` any Kaggle-local cap.
- Scoring constants re-read from the methodology page.
- Toolkit padding and submitted-agent tensor shapes; if the API always pads to 64×64, record that
  as verified serialization, not as the environment definition.
- ACTION7 exposure on both local and Kaggle paths.

## 3. Scientific hypotheses

### H1 — Sequential predictive-state inference

History conditioning improves control when current observations are insufficient because of partial
observability, hidden inventory or counters, environment-specific action semantics, delayed effects,
rule switches, or visually aliased states.

Evidence requires more than better next-frame prediction. The inferred context must decode
action-effect mappings and improve counterfactual action ranking.

### H2 — Exact versus latent predictive targets

Reconstruction-free latent prediction helps when exact next-state prediction spends capacity on
irrelevant variation, or when transfer and data efficiency dominate.

Exact or reconstructive prediction helps when:

- one cell determines legality or success;
- transitions are brittle and irreversible;
- the latent encoder aliases control-distinct states;
- planner ranking depends on exact terminal identity.

### H3 — Grounded temporal hierarchy

Hierarchy improves planning when local dynamics are sufficiently accurate, useful plans exist within
the candidate generator, flat search cost grows rapidly with horizon or branching, goals require
non-greedy prerequisite events, and intermediate states are reachable by the low-level controller.

Hierarchy does not repair an inadequate predictive state or an incorrect goal hypothesis.

### H4 — Exact archive support

A persistent exact transition graph reduces repeated exploration, protects against latent aliasing,
grounds subgoals, and allows predictions to be checked against observed transitions.

### H5 — Hybrid agency

The complete hybrid agent outperforms either a purely exact archive system or a purely latent planner
on environments combining unfamiliar mechanics, long horizons, and sparse progress evidence.

## 4. System conditions and architecture invariants

### 4.1 Exact archive baseline

Components: exact observation hashing; exact changed-cell and connected-component deltas; a directed
transition graph; frontier and event novelty; shortest known replay paths; reversible-path tracking;
coordinate-action proposal heuristics; deterministic contradiction logging.

This baseline is always retained. Learned components must improve useful progress per action or
planning capability beyond it.

### 4.2 Sequential exact predictive model

Inputs: current and recent observation frames; recent actions; exact transition deltas;
available-action metadata; retrieved relevant archive transitions.

Outputs: exact next-grid or exact delta distribution; event prediction; irreversibility prediction;
action-availability prediction; counterfactual successor scores.

### 4.3 Sequential compact reconstructive model

A learned compact state trained with a lightweight decoder for next-state or next-delta prediction.
It controls for compact representation without removing exact reconstruction pressure — separating
"the prediction target discards information" from "compact learned state discards information."

### 4.4 Sequential latent predictive model

The model predicts target-encoder representations rather than the exact grid. Exact changed-cell,
event, legality, and irreversibility auxiliaries ensure that action-critical information remains
inspectable. The default stabilization is an EMA target encoder with stop-gradient.

### 4.5 Grounded hierarchical models

Both exact and latent predictive systems can be paired with the same high-level protocol: event-state
candidates from the archive, frontiers, and validated predictions; learned reachability probability;
learned action cost; irreversible-risk estimate; high-level graph or beam search; low-level
short-horizon planning; closed-loop execution and replanning.

The controlled synthetic study includes both target families with flat and hierarchical planning.

### 4.6 Exact-dynamics ceiling

The common candidate generator, reachability interface, and planner operate with exact simulator
transitions. This identifies whether failures come from dynamics or from search, goal specification,
or candidate generation.

### 4.7 Architecture invariants

All learned conditions use:

- the full atomic observation bundle;
- the same categorical grid vocabulary;
- the same action and coordinate interface;
- the same sequence window and retrieval protocol;
- matched model-capacity and training-compute budgets where meaningful;
- identical training-game and generator-instance splits;
- identical candidate budgets for equal-expansion comparisons;
- measured equal-time sensitivity comparisons;
- fold-bounded downstream evaluators;
- no game-name or environment-identity embedding.

Condition-specific heads are permitted only when their parameter and optimization budgets are matched
and disclosed.

## 5. Data and environment design

### 5.1 ARC-AGI-3 data

Public games are divided into development games — implementation, tuning, task auditing, and launch
gates — and held-out cross-game folds for ecological evaluation (§6.8).

Data sources: random and structured exploration; exact archive trajectories; released human replays
as references and policy seeds; self-collected agent trajectories; counterfactual simulator branches
where permitted.

A held-out game's trajectories are never used to train the model evaluated on that game. Replay
corpus: 342 released human plays, 145 completed-game solves, unevenly distributed — hence the
fallback rules in §5.2. These are references and policy seeds, not pretraining data.

### 5.2 Task construction

Per test game: evaluation-only successful replays, firewalled from all training → start states at
predeclared replay quantiles → goal states at fixed separation strata (1–2, 3–5, 6–10, 11–20
actions) → require at least one decision-relevant state change, excluding persistence tasks and
animation-only differences → deduplicate near-identical starts and goals. Uniform primary
denominator A_ref = replay-segment length; exact-BFS and stronger-search denominators are
sensitivity strata only, never mixed into the primary. Tasks do not cross level boundaries.

**`task_manifest.yaml` must fix:** replay-eligibility rule; tasks per game and per horizon stratum;
start quantiles; per-replay contribution cap; goal-exemplar count and canonicalization;
near-duplicate thresholds; the decision-relevant-change detector; animation-exclusion rule;
short-level and few-replay fallbacks; generator seed; executable tests for every goal-equivalence
transformation; a second-person audit of a task-validity sample; a published sample of accepted and
rejected equivalences. Games are weighted equally regardless of eligible-task counts.

### 5.3 Task strata

**Replay-path goal reaching (primary).** Start and goal states from successful replay segments at
predefined separations. This measures controlled local planning and carries the confirmatory
estimand.

**Counterfactual branches.** From a replay state, execute legal actions not taken by the replay
policy. Evaluate successor prediction and candidate ranking.

**Off-policy robustness and recovery (secondary).** Start states drawn from (a) replay states
followed by 1–3 legal non-replay actions and (b) states produced by random, frontier, and
event-novelty exploration rollouts. The planner must recover to the replay manifold, reach the
supplied goal, or correctly flag the state unrecoverable within budget. On- versus off-trajectory
degradation is a reported result. Runs on development games before the matrix launches; stays
secondary in confirmatory.

**Irreversible-event tasks.** Evaluate prediction and avoidance of traps, destructive
transformations, and one-way transitions.

**Cross-level rule-use tasks.** Provide interaction history from earlier levels and evaluate
predictions or decisions in a later level without gradient updates.

**Level completion (secondary diagnostic).** Built from full-level tasks; success is level
advancement relative to the start snapshot. Never pooled with the primary within-level set.

**Full-agent progress tasks.** Measure useful progress per action under goal uncertainty and
exploration.

Tasks remain nested within games. They are never treated as independent transfer units.

### 5.4 Procedural boundary suite

The suite contains environment families with randomized layouts, visual assignments, object
identities, and mechanic parameters. Mandatory axes, with their full level sets:

1. **Observability** — full state; local view; hidden counter or inventory; delayed observation.
2. **Action semantics** — fixed globally; remapped by environment; state-dependent; changed after an
   event.
3. **Dynamics** — reversible motion; discrete toggles; irreversible transformations; delayed effects.
4. **State relevance** — broad geometry; object relation; one-cell-critical state; visually identical
   but control-distinct state.
5. **Goal geometry** — direct approach; key-before-door; move-away-before-progress; ordered event
   chain.
6. **Transition uncertainty** — deterministic; observation aliasing; hidden-mode transition; genuine
   stochastic branching.
7. **Horizon** — one-step; four-to-eight-step; multi-event; long maze or prerequisite chain.
8. **Generalization** — unseen layout; unseen parameterization; unseen combination of known
   mechanics; held-out mechanic family.

The committed confirmatory design is **eight paired one-factor-at-a-time micro-environments — not a
2⁸ factorial** — each axis instantiated as an easy arm and a stress arm: observability (visible ↔
hidden timer or switch); action semantics (fixed ↔ resampled per episode); dynamics (smooth ↔
discrete irreversible); state relevance (broad ↔ one-cell-critical); goal geometry (visible ↔
non-greedy prerequisite chain); latent distribution (isotropic ↔ clustered); transition uncertainty
(unimodal ↔ aliased); horizon (one-step ↔ compositional 4–16). The remaining axis levels above are
reserve gradations, used for diagnosis rather than confirmatory contrasts.

Each family exposes train, validation, and test generators. Environment definitions, generator seeds,
three seeds per condition, held-out combinations, and readouts are committed in the manifests before
any suite result is viewed.

## 6. Track A — the controlled study (the paper)

### 6.1 Question and registered claim scope

**Question.** Under matched data, architecture class, optimization budget, and planner protocol, how
do the exact-token and latent-predictive objective families, crossed with Markov versus sequence
context, differ in cross-game transfer, adaptation, and action-efficient planning? End-to-end arms
differ in loss geometry, anti-collapse machinery, output entropy, and rollout state; the claim is
about families as practiced, not an isolated prediction target.

**Registered claim scope.** The confirmatory estimand is the difference between two pre-specified
systems representative of their families, on goal-conditioned planning over replay-derived,
within-level subtasks from held-out public games under cross-game training. Family-level
generalization, benchmark-level generalization, and end-to-end instruction-free agency are
explicitly not claimed by the primary. The synthetic mechanism suite and the secondary strata carry
the where/why questions; Track B's hidden-set run carries the ecological story.

### 6.2 Run ledger

| Tier | Conditions | Folds | Seeds | Models | Status |
|---|---|---|---|---|---|
| Confirmatory core | token/latent × Markov/sequence | 4 | 3 | **48** | mandatory |
| Capacity control | larger token, sequence-only (matched to dual-head total) | 4 | 3 | 12 | strong default |
| Reconstruction control | compact state + next-grid decoder, sequence-only | 4 | 3 | 12 | strong default |
| Dual-head | shared trunk, sequence-only | dev first | 1–3 | 1–3 | Track B |
| Detached auxiliary | sequence-only | dev first | 1–3 | 1–3 | Track B |
| Neutral encoder | token/latent, sequence | conditional | conditional | — | reserve |

Mandatory core 48 models; strong-default total 72; planned ceiling 84–96. At ~4 GPU-h per 20M-scale
run, the strong default is ~290 GPU-h ≈ $350–700 spot. Engineering conditions never automatically
receive confirmatory-fold replication.

The exact archive baseline (§4.1) and the exact-dynamics ceiling (§4.6) accompany every fold as
reference points rather than trained conditions. Hierarchical arms are not part of the ARC
confirmatory core: they live in the synthetic factorial (§6.10) and enter ARC folds only behind G4
and only if the measured evaluation budget permits.

### 6.3 Operational spine — design locked; manifests completed by end of W2

Encoding takes the full observation bundle plus deterministic exact-change descriptors, applied
identically to every condition. Corpus and splits fixed. 20M trainable parameters per primary
condition, matched ±5%; training FLOPs and planning expansions matched; wall-clock and peak memory
reported rather than forced equal.

**Context isolation.** Markov and sequence arms share the same K-slot architecture, positional
structure, action interface, parameter count, and primary compute path. The sequence arm fills all K
observation/action slots; the Markov arm masks the preceding K−1 and receives only the current
atomic bundle. Sparse-compute skipping of masked slots is deployment-only, never used in the matched
primary comparison.

**Data manifest.** Game name and version hash (games are patched mid-season), replay snapshot,
preprocessing commit, split manifest, action masks and metadata, seeds.

**Identity-leakage rules.** Game ID and version hash are metadata only — no game-specific
embeddings or per-game heads in the confirmatory core. Normalization is global, or online without
test labels. Action-availability metadata is permitted, being officially observable.

### 6.4 Goal semantics — three separated objects

1. **Success predicate.** Simulator-side membership in the frozen goal-equivalence class derived
   from the task's goal snapshot. For the separate level-completion stratum, success is level
   advancement relative to the start snapshot. Never exposed to any model; carries no game-specific
   transition logic. Equivalence transformations are executable, documented, and audited; hidden
   state is included whenever it changes future transitions. Language rule: supplied goal exemplars
   remove goal discovery from the primary task — never "oracle goals," which implies an executable
   predicate handed to the planner.
2. **Planner goal representation.** A frozen equivalence class of goal exemplars from the
   task-construction protocol, given to every arm through its own frozen encoder. End-to-end tasks
   instead use the goal-hypothesis module (§8).
3. **Learned reachability interface.** A standardized downstream adaptation protocol: matched
   heads over (current or predicted state, exemplar set), each representation entering the common
   head through a condition-specific fixed-width adapter, with adapter-plus-head parameter count,
   training data, checkpoint count, and optimization FLOPs matched, and the adapter included in
   cross-fitting. The protocol predicts probability that a candidate endpoint reaches the goal or
   subgoal, expected scored actions, probability of irreversible failure, and calibration
   uncertainty. The protocol is fixed; weights necessarily differ, and equal budgets do not
   guarantee equal effective difficulty — that residual is part of the measurand and is decomposed
   by the audit ladder in §6.7. Head-capacity sensitivity is evaluated on development data.

### 6.5 Estimand, metric, decision rule

**Primary contrast.** Δ = E[Y(latent, sequence) − Y(token, sequence)] on the confirmatory folds.
Markov arms are mechanistic controls; sequence gains and the target × context interaction are
reported.

**Primary metric — Replay-Normalized Goal-Reaching Efficiency (RN-GRE).** For a task with replay
reference length \(A_{\mathrm{ref}}\) and agent action count \(A\):

\[
G =
\mathbf 1[\text{success}]
\min\left(1.15,\left(\frac{A_{\mathrm{ref}}}{A}\right)^2\right).
\]

Failures and budget exhaustion score zero, never omitted; diverged or invalid plans are failures;
replanning actions count; goal-specification strata are never pooled. This is not presented as the
official competition metric: "RHAE-inspired" may appear in methods, never in the headline.

**Decision rule.** δ_G = 0.04 absolute. For each held-out game, average the paired
latent-minus-token effect across the three aligned training seeds. Because one fold-seed model is
evaluated on all five games of its fold, seeds are never resampled independently per game.
Bootstrap the 20 seed-averaged game effects, stratified by outer fold, 10,000 replicates, 95%
interval. Classification: latent practical advantage if the lower bound exceeds +0.04; token
practical advantage if the upper bound is below −0.04; practical equivalence if the interval lies
inside [−0.04, +0.04]; otherwise inconclusive. Family-blocked and leave-one-game-out analyses are
sensitivity checks, never alternate decision rules.

**Interpretation rule (registered pre-data, estimation-first).** The primary analysis is the paired
effect estimate with its interval, plus decomposed readouts: success probability, actions
conditional on success, relative effect conditional on baseline. The four-way classification is a
secondary readout. If the pre-W3 precision simulation shows the expected interval exceeding the
equivalence region, the paper reports classification as unattainable by design. Stated estimand
conditionality: variation across these 20 public games, conditional on the frozen folds and the
three-seed average. Seed-averaging is not an ensemble — Track B deploys the development-selected
single-seed system, or an explicit ensemble as its own engineering condition — and per-seed effects
are always reported.

**Failed runs.** Infrastructure failures are rerun with identical seed and configuration.
Algorithmic collapse or divergence is retained as a condition outcome, never silently replaced: a
collapsed but executable checkpoint is evaluated as-is; if divergence leaves no executable
checkpoint, every task for that condition–fold–seed scores zero, which is an outcome, not missing
data. Development-game variability feeds only the pre-W3 precision simulation (interval width,
P(equivalence), one-outlier and family-cluster sensitivity).

**Evaluation regimes.** Primary: frozen weights — sequence context may include within-game history,
but no gradient updates, no buffer fitting on the test game, heads frozen. Secondary: adaptation AUC
at predeclared interaction counts, permitted adapters only, observed transitions only, no goal or
completion labels. Compute: primary at equal expansions; secondary sensitivity at equal wall-clock
per decision, with the equal-expansions × equal-time outcome matrix reported.

### 6.6 Metric taxonomy — the capability chain

The study does not rely on a single end-to-end score. The principal systems endpoint is closed-loop
action-efficient success; the chain below localizes where it comes from.

**Predictive-state metrics.** Action-effect mapping accuracy; hidden-state discrimination;
mechanic-shift detection; action-availability prediction; counterfactual action ranking.

**Dynamics metrics.** Whole-state exact match; changed-cell precision, recall, and F1; event and
irreversible-transition accuracy; exact rollout survival by horizon; latent rollout error;
direct-versus-composed prediction consistency.

**Planning metrics.** True candidate-set ceiling; selected-candidate regret; oracle top-k recall;
pairwise ranking accuracy; reachability calibration; expected versus actual action cost.

**Closed-loop metrics.** RN-GRE (§6.5); success probability; actions conditional on success;
recovery probability; catastrophic failure probability; on- versus off-trajectory degradation.

**End-to-end metrics.** Useful irreversible events per action; discovered regions and mechanics per
action; level advancement; goal-hypothesis calibration; official external score when available.

### 6.7 Planner interfaces and audits

**A — primary score.** Matched-protocol goal heads (§6.4), cross-fitted.

**B — systems comparison.** Native costs: token likelihood or exact verification versus latent
distance, with a whitened-latent-distance middle arm. Raw versus whitened versus learned head is
itself a result: gain from whitening means the information is present but the geometry misleading;
no gain means content is missing; the head beating both means goal geometry is nonlinear.

**C — attribution: same-candidate oracle audit.** Identical candidate sequences are rolled through
every model and executed in the deterministic simulator, giving ground-truth candidate quality with
no learned judge. Four stages:

1. Candidate quality — best true outcome in the set → sampler or horizon limits.
2. Rollout fidelity — predicted versus exact outcomes → dynamics.
3. Terminal evaluation conditional on exact endpoints — exact simulator endpoints fed through each
   condition's frozen encoder and head, removing rollout error → interface and geometry. (Named
   precisely: this isolates terminal evaluation given exact endpoints, not "pure goal geometry.")
4. Closed-loop executed result → replanning, compounding error, execution.

Audit ladder within stage 3: (i) simulator-state oracle ranking → (ii) a shared frozen external
featurizer of representation-independent grid features (changed-cell counts, object statistics,
event flags) → (iii) condition encoder plus linear or bilinear comparator → (iv) condition encoder
plus full head. Gaps read as (i)→(ii) feature sufficiency, (ii)→(iii) representation accessibility,
(iii)→(iv) nonlinear interface value.

**Candidate pools.** Two common pools are required: a fixed-size **exogenous** pool generated
independently of all conditions, and a fixed-size **union** pool sampled evenly from all model
proposal sources. The exogenous pool carries the primary audit; the union pool is secondary, with
its endogeneity named. Both are stratified by true endpoint diversity, changed-cell count,
irreversibility, true progress, legality, horizon, and recovery/non-greedy requirement; constants in
the manifest, coordinate actions from a frozen sampling scheme, legality masks and horizon
distributions identical across conditions. Whitening transforms are fit on outer-train games only.
Metrics: selected-candidate regret, oracle top-k recall, pairwise ranking accuracy, rank
correlation, calibration.

**Cross-fitting.** Every learned evaluator — heads, probes, calibration maps, classifiers, decoders,
thresholds — obeys outer-fold boundaries: trained on outer-train, tuned on development or inner
validation, applied once to outer-test.

**Diagnostic contract.** Frozen baselines every condition is read against: copy-last-observation
persistence; random candidate ranking; exact-simulator planning under the same candidate budget;
archive or exact-transition-table baseline where applicable. Reported per condition: whole-frame
exact match; changed-cell precision, recall, F1; irreversible-event and level-transition prediction
accuracy; multi-step exact-rollout survival; counterfactual action discrimination. If the token loss
uses change weighting, the weighting rule is frozen from outer-train data only. Unchanged-cell
accuracy never substitutes for dynamics knowledge.

**Tuning and run integrity.** Shared hyperparameters are tied across conditions where meaningful.
Family-specific loss and stabilization knobs are permitted, but their search spaces and maximum
development-tuning FLOPs are frozen before tuning and matched across families. Every condition gets
the same number of evaluated checkpoints on the same frozen optimizer-step grid; each run's primary
checkpoint is the best development-game matched-interface G, ties selecting the earlier checkpoint;
no family-specific early-stopping metric. A code defect found before unblinding is fixed only by
rerunning every affected condition symmetrically. No confirmatory metric is opened merely to
diagnose an underperforming condition.

### 6.8 Splits, governance, and the fallback ladder

Tasks are nested within games; games — not tasks or levels — are the transfer units. Mechanics
labels guide fold stratification; near-duplicate games and related versions always share a fold.

Development set: 5 public games, carrying all debugging, tuning, margin calibration, and interface
validation; never confirmatory. Confirmatory set: 20 games in 4 mechanics-stratified outer folds,
train 15 / test 5, every game held out exactly once, all conditions complete before aggregates are
unblinded.

Labeling uses a frozen codebook — navigation, manipulation, toggles and irreversibility, counters
and hidden state, spatial transforms, click interaction, delayed effects, partial observability,
mechanic reuse — assigned before results are seen, with a second independent labeler if a
collaborator is available. Leave-mechanic-family-out is a secondary stress test, not the primary
analysis.

**Fallback ladder (pre-registered; the confirmatory core is cut last, consistent with §15).**
(1) Drop the neutral-encoder follow-up → (2) drop confirmatory replication of the reconstruction and
engineering conditions → (3) reduce or remove capacity-control fold replication → (4) drop
transfer and data-quality scaling curves → (5) single mechanic labeler → (6) reduce the three-seed
replication of the confirmatory core to two → (7) only then reduce 4 folds to 2, and label the
result a reduced confirmatory study rather than the original design.

**Language discipline.** This is cross-game held-out *training* evaluation on the public benchmark,
not blind transfer to unseen mechanics; researcher-level exposure to public games is unavoidable.
Kaggle provides ecological external validation of the selected end-to-end agent, not of the matched
Track-A contrast.

### 6.9 Statistical analysis

**Synthetic suite.** Environment instances are the primary independent units; generator family and
mechanic parameters are modeled hierarchically. Report mean paired effects; mechanic interactions;
between-family heterogeneity; practical margins; held-out-combination performance;
held-out-family stress results. The generated suite supplies enough independent instances to
estimate mechanism interactions with useful precision.

**ARC public games.** ARC games are treated as a finite benchmark set. Beyond the primary decision
rule (§6.5), report paired game effects; fold-training-set sensitivity; per-seed results;
leave-one-game-out and leave-one-fold-out analyses; mechanic-tagged descriptive effects; uncertainty
intervals without extrapolating to all environments. Levels and generated tasks are not independent
transfer samples. The ARC analysis emphasizes paired per-game effects and failure profiles rather
than a universal superiority classification.

**Failed runs.** Per §6.5.

### 6.10 Synthetic factorial and mandatory sequence diagnostics

Holding sequence conditioning fixed, the synthetic primary conditions are:

| Condition | Predictive target | Planning |
|---|---|---|
| Exact-flat | Exact state or delta | Flat |
| Exact-hierarchical | Exact state or delta | Grounded hierarchy |
| Latent-flat | Latent target | Flat |
| Latent-hierarchical | Latent target | Grounded hierarchy |

Three training seeds per primary condition. The compact reconstructive model is a mandatory
mechanistic control on the principal environment families; the exact-dynamics planner supplies the
ceiling. Primary contrasts: latent versus exact under flat planning; hierarchy gain under exact
prediction; hierarchy gain under latent prediction; target-by-hierarchy interaction. Predefined
environment interactions focus on partial observability, action remapping, one-cell-critical state,
non-greedy prerequisites, transition aliasing, and horizon.

**Two mandatory sequence diagnostics.** *Rule resampling:* remap action→effect per episode and
compare frozen-Markov, frozen-sequence, adapted, and sequence-plus-adapted conditions, decoding the
mapping from the aggregate — sequence context must demonstrate system identification, not memory.
*Composition:* ‖P(P(z_t, a_t), a_{t+1}) − enc(true two-step state)‖ as a function of horizon —
strong one-step prediction can still be a local lookup table, while planning needs compositional
consistency.

**Paper positioning.** Not "PLDM applied to ARC" but: does the PLDM result survive discrete exact
dynamics, cross-game mechanics, history-dependent rules, non-Euclidean goal geometry, and partly
self-collected data? Data-quality and training-game-count analyses are development-only,
sequence-arm, two to three nested predeclared subsets, one seed initially; replication or
confirmatory evaluation only if reserve remains.

### 6.11 External reference class (audited 2026-07-23)

- **Public-set saturation.** Rodionov, "Do Coding Agents Need Executable World Models,
  Simplification, and Verification to Solve ARC-AGI-3?" (arXiv 2607.15439) reports ~99% RHAE with
  GPT-5.6 Sol across the 25 public games via a fixed-interface verification treatment. Public-only;
  the model postdates the environments; no held-out evaluation. This is saturation of the public
  set, not benchmark-level generalization.
- **ARC-standardized frontier reference.** GPT-5.6 Sol at 13.33% public and 7.78% semi-private — a
  separate system and evaluation regime, so no ratio may be formed against the line above; the
  valid within-system factor is ~1.7×. Public saturation alongside single-digit verified
  semi-private is why public-set score is a dead novelty axis. Two facts, not one ratio.
- **Online programmatic reference.** OPINE-World: 20/25 games, 160/183 levels, action-efficiency
  78.4 (arXiv 2607.01531). Rodionov's earlier executable-world-model system: 15/25, mean RHAE
  58.12% with GPT-5.5 (arXiv 2605.05138v2).
- **Compact-model reference.** 0.5B explore-first agent: 4/25, RHAE 0.2116 (arXiv 2605.25931).
- **Neural latent reference.** Zero under OPINE's Dreamer- and MuZero-family setup — an external
  failure reference. Faithful reproduction is attempted only within a predeclared two-day
  development timebox if that setup can be matched; otherwise the paper labels our closest
  implemented analogue an adapted baseline.

Positioning: public-set score alone is insufficient novelty evidence. This work studies controlled
cross-game training transfer under matched resources and interfaces. Public-set saturation does not
establish semi-private or hidden-set generalization.

## 7. Launch gates

Expensive evaluation begins only after a complete vertical slice — one token system, one latent
system, and the reconstruction control run end-to-end on development games: harness → training →
task generator → interfaces → audit. Interface engineering must not be discovered inside the matrix
window. The 48-run matrix launches only if every gate below passes. Thresholds are proposed shapes,
finalized in `gate_manifest.yaml` before any sub-gate result is viewed.

### G0 — Harness and exact baseline

Required: accepted local and external execution path; deterministic replay; exact transition
archive; coordinate-action candidate generation; itemized latency table; at least \(10^5\) stored
transitions; reproducible environment and data manifests; RESET-accounting experiment done;
methodology constants read.

Failure response: stop learned-agent work until the harness is reliable.

### G-A.1 — Planning headroom

Exact-simulator dynamics with oracle ranking must beat the strongest simple baseline by ≥0.15 task
success or ≥0.10 RN-GRE on the median development game, and solve ≥60% of eligible development
tasks. Exact planning must materially exceed persistence and archive replay, and the candidate pool
must contain successful candidates often enough to expose dynamics quality.

Failure response: the task generator, horizon, sampler, budget, or goal interface is the bottleneck.
Fix the experiment, not the models. Do not launch the matrix.

### G-A.2 — Task validity

Persistence baseline <50% success; archive or exact-transition-table baseline <80%; exact oracle
>60%; per-replay cap respected; ≥3 usable horizon strata in most games; no replay or game dominates
the task set; manual audit error <5%; equivalence and hidden-state errors <2% on the audited sample.

Failure response: repair the task generator and repeat the audit.

### G-A.3 — Model competence, not superiority

Per system: ≥2 of 3 development seeds executable, no unrecoverable divergence; changed-cell and
event prediction beat persistence; counterfactual ranking beats random; 4-step rollout and event
survival beat copy-last-state; evaluation fits the runtime budget. A stable latent system that is
*worse* than token still passes — it is a valid negative candidate. Collapse or trivial prediction
does not pass.

### G-A.4 — Interface attribution and validity

Across oracle / raw / whitened / learned-head rankings: exact-endpoint ranking must materially
exceed random; the learned head must not close >90% of the learned-versus-exact gap for every
condition (the head doing the task), nor reduce a strong oracle-conditioned representation to within
0.02 of random (adapter failure); candidate ranking must remain calibrated enough for closed-loop
use. Conclusions must survive a small-versus-full head-capacity repeat.

Failure response: redesign the interface before any confirmatory training.

### G-A.5 — Off-policy robustness

Both learned systems are evaluated on random, frontier, and recovery states; degradation is
quantified; catastrophic error is below a predefined tolerance; training data include adequate
exploratory support.

Failure response: expand the data mixture or narrow the claim to replay-supported control.

### G-A.6 — Precision and pipeline cost

Simulate the full analysis from development variance under inflation factors. Launch only if the
expected 95% half-width is ≤0.05, or |Δ| = 0.08 classifies ≥60% of the time, or the study is
explicitly relabeled as estimation and failure localization — in which case that relabel becomes the
headline framing. Extrapolated full-pipeline cost (training, checkpoints, cross-fitted interfaces,
candidate generation, simulator execution, audits, metrics, analysis, artifacts) must fit within 65%
of remaining compute and 70% of remaining workdays, retain the 25–30% runtime margin, and permit
one complete fold to be regenerated unattended without manual intervention.

Failure response: reduce folds, conditions, or audit breadth before the matrix starts.

## 8. Track B — agent ladder

Target architecture, **SHiP-JEPA-X** (Sequential Hierarchical Predictive JEPA with eXact
verification): sequential inference over history for hidden state and action semantics; short-horizon
latent dynamics; event-level hierarchy; a persistent exact object/event archive; a goal-hypothesis
bank; and exact verification with an irreversible-risk veto around every executed chunk. This names
what v5-complete looks like if every gate fires — not a build order. Component-to-version map: exact
parser and archive → v0–v1; spatial-latent sequential inference → v2; multi-horizon heads, event
hierarchy, and reachability-constrained subgoals → v5 behind G4; grounded macros and ACTION6
factorization → v1/v3; goal-hypothesis bank, heuristics first → v3/v5. The full component
specification is in
[`arc-agi-3-ship-jepa-x-architecture.md`](arc-agi-3-ship-jepa-x-architecture.md).

Standing design choices: coordinate actions are factored as P(ACTION6) × P(x,y | state, context)
with candidates drawn from object centroids, changed components, boundaries, and unexplored cells,
plus coordinate-class exploration priors; macros are grounded — replay chunks, parameterized local
skills, and effect-clustered archive edges — never learned latent macro-actions first; subgoals are
drawn only from archive nodes, frontier states, event prototypes, or predicted states passing a
manifold test.

| Wk | Version | Gate (binary; development games only where learned models are compared) |
|---|---|---|
| 1 (Jul 27–Aug 2) | v0 harness | **G0:** accepted submission ∧ determinism verified ∧ ≥10⁵ transitions logged ∧ latency table measured ∧ RESET-accounting experiment done ∧ methodology constants read |
| 2–3 | v1 archive + contingency probe; S0 (5 working days) | **G1** (Aug 9): harness and archive functional, else descope |
| 3–6 | v2 vertical slice → Track-A matrix; agent adopts the development-selected family | **G2** (Sept 6, development games only): retain latent in Track B iff (a) latent G exceeds token by ≥0.04, or (b) latent is within 0.04 and reduces median decision time or peak memory by ≥20%, or (c) latent trained on the nested 80%-game subset stays within 0.04 of the full-data token model. Confirmatory folds stay sealed until scientific unblinding. |
| 6–8 | v3 exploration | **G3:** the learned explorer must beat random, exact-hash frontier search, event-level graph search, archive replay, and irreversible-event novelty on useful-progress-per-action; kill K=5 if per-wall-clock discovery falls below single-model novelty |
| 7–9 | v4 policy (+TTT behind safeguards) | Milestone 2 ships Sept 30 with a no-TTT control submission |
| 10–11 | v5 subgoal planner | **G4:** per §9 |
| 12–13 | contingency reserve (~20%) + paper | Feature freeze Oct 18; architecture freeze requires ≥25–30% wall-clock margin |
| 14–15 | hardening; submit Nov 2; paper by ~Nov 5 | — |

**S0 — stabilization, 5 working days.** Default: EMA target plus stop-gradient — the only option
that composes with test-time adaptation, since a five-sample buffer makes VICReg and SIGReg
batch-statistic estimates unreliable. Single fallback: VICReg-style variance/covariance, including
the delta-conditioned variance variant. SIGReg is a development-only diagnostic, run fairly or not
at all: pooled batch statistics, batch-size sweep, mean and max directional discrepancy logged, raw
*and* whitened probes, temporal action-conditioned configuration. On day five the default ships and
collapse theory becomes post-competition work. Whitened probes are mandatory wherever probes appear;
raw-versus-whitened gaps are reported; RankMe is never substantive evidence when isotropy is
optimized.

**Exploration ladder (v3).** Random, state novelty, event novelty, predictive disagreement,
progress-exemplar similarity, and an oracle-progress upper bound are compared on useful progress per
action — irreversible transitions, level-transition discovery, completion, and resulting RN-GRE —
never raw state coverage.

**Conditional extensions and kill rules** (constants in `gate_manifest.yaml`):

- *Reconstruction control.* Same encoder and backbone as the latent arm, compact or discrete
  bottleneck, lightweight next-grid decoder, no reward. Strong default on the confirmatory folds and
  mandatory on the synthetic suite and development games; it is the interpretability control for the
  principal contrast, separating "the target discards information" from "compact learned state
  discards information." First item cut at fallback step (2).
- *SIGReg.* Dead for 2026 after one correct implementation plus one retry if ≥2 of 3 seeds fail,
  whitened counterfactual ranking drops >0.02 versus EMA, event or changed-cell F1 drops >0.05, no
  predefined benefit appears (≥0.04 planning or ≥20% data efficiency on a stress condition),
  pooled-batch requirements bust the budget, or conclusions are batch-size-unstable. Fallback is
  EMA/stop-gradient, never an improvised hybrid.
- *Mechanics-hypothesis particles.* J ≤ 4 context variants with variance-penalized planning,
  admitted only as a *replacement* for the K-predictor ensemble if development games show ensemble
  disagreement poorly calibrated against realized error — never two uncertainty systems at once.
  Two-day timebox.
- *Archive-retrieval context.* Admitted only if dense-context in-context-learning curves plateau on
  long development episodes.
- *Hierarchy.* Per §9. In writing, hierarchy "addresses" rather than "resolves" PLDM's boundaries.

Auxiliary-objective stacks and composition penalties may enter the deployed agent after G2 if
development shows value; they never touch the registered Track-A losses.

## 9. Hierarchy admission and retention (G4)

The non-greedy diagnostic set runs first. Hierarchy is admitted only when:

1. short-horizon prediction is adequate;
2. short-horizon ranking is adequate;
3. flat planning fails on verified non-greedy or long-horizon tasks — a sharp drop, not general
   weakness;
4. increasing the flat search budget does not close the gap economically;
5. oracle event subgoals improve success by at least 20%;
6. the low-level planner reaches oracle subgoals reliably.

Automatic grounded subgoals are built only after the oracle beats flat by ≥20%, and retained only
when they recover at least half of the oracle hierarchy gain without material runtime or catastrophe
cost. The first implementation is multi-horizon heads (1/2/4/8) plus coarse-goal selection, not
learned macro-actions.

Candidate subgoals are initially restricted to archive states; frontiers; detected event states;
validated trajectory predictions; and exact object-relation transformations supported by observed
transitions. Free optimization over arbitrary latent vectors is outside the committed scope, as is a
learned hierarchical level.

## 10. Adaptation

### In-context adaptation — always permitted

Update sequence context; update archive; update mechanics hypotheses; retrieve contradictory or
analogous transitions.

### Gradient adaptation (TTT, v4+) — admitted only after all prerequisites pass

Per-game adapters on a frozen base. Updates are limited to small adapters or final predictor layers;
the base encoder remains frozen unless there is strong evidence that perception, rather than
dynamics, is the bottleneck.

Shadow validation: a small recent-transition subset never used for the current gradient step, with an
update committing only if shadow rollout loss and candidate-ranking diagnostics stay within frozen
tolerances, else rollback. Parameter-norm cap; replay balancing.

Synthetic dynamics-shift gains required: median > 0, gains on ≥60% of games, ≤10% catastrophic
regressions, bounded runtime. Two stress tests: rule reversal (A→B→A — recovers B, retains A,
re-adapts) and long-horizon drift (hundreds to thousands of updates with no shift, tracking held-out
replay loss, ranking accuracy, planning score, parameter distance, rollback frequency).

TTT is conceptually simple and operationally non-free; it enters the competition agent only after
passing all of the above, and every milestone ships a no-TTT control.

## 11. Multiple successor modes

Not implemented unless the aliasing admission gate passes: the same encoded history and action yields
reproducibly different exact successors; the complete observable history and metadata remain
insufficient; exact-state diagnostics exclude an encoder or metadata bug; longer history closes <50%
of the successor gap; residual modes are reproducible across ≥2 of 3 seeds and ≥2 synthetic aliasing
environments.

After a two-day timebox, retained only on ≥10-percentage-point improvement in true-successor top-k
recall or ≥0.04 planning gain, with ≤0.02 degradation on unimodal environments, ≤20% median
inference overhead (unless the gain exceeds 0.08), and stable convergence in ≥2 of 3 seeds.

Fallback order: longer history → observation and encoder audit → larger deterministic latent →
discrete or reconstructive state → exact-token. Otherwise the deterministic model remains the final
system and mixture modelling becomes post-competition work.

## 12. Cross-cutting laws and diagnostics

Spend unscored compute inside the model; spend scored actions only on vetted plans. A runtime
governor — token-head perplexity alarm plus divergence-under-ensemble-agreement — demotes the agent
v5 → v3 → v1 under distribution shift or premature commitment. Harness hygiene: no game-name
leakage, no parallel-client tricks. Gate numbers land in the paper repo the day they are produced;
the paper is assembled, not written. Hidden-set scores are ecological validation only.

The synthetic boundary suite (§5.4) is a preregistered secondary mechanism study: it carries the
mechanism and "where" claims while the ARC primary carries the system comparison, and the paper stays
ARC-facing.

## 13. Schedule

The version/gate ladder in §8 is the spine; the calendar phases below are the work items.

**July 20–26 — specification and primary-source audit.** Finalize hypotheses, environment axes,
manifests, and launch gates; complete the minimum literature audit; play representative public games
manually; define exact task predicates and event vocabulary.

**July 27–August 2 — harness and exact archive (v0).** Local and external execution path;
deterministic replay; exact transition graph; random, frontier, event-novelty, and archive baselines;
latency and reset accounting. → G0.

**August 3–9 — procedural suite and task generator (v1, S0).** Implement synthetic environment
families; build replay, counterfactual, recovery, and cross-level tasks; run task-validity audits;
measure exact-planning ceilings; ship the stabilization default. → G1.

**August 10–16 — complete vertical slice (v2).** Train one exact, one reconstructive, and one latent
sequential model; fit the common reachability interface; run the full common-candidate audit;
evaluate off-policy robustness; decide whether the confirmatory matrix launches. → G-A.1–G-A.6.

**August 17–September 6 — controlled mechanism study.** Train the synthetic factorial; run
sequence-system-identification and composition tests; test oracle and grounded hierarchy; freeze
mechanism conclusions after all conditions complete. → G2 (development games only).

**September 7–27 — ARC held-out evaluation.** Collect fold-bounded training data; train the
confirmatory core; run replay, branch, recovery, event, and rule-use tasks; produce paired game
analyses.

**September 28–October 11 — end-to-end agent (v3–v4).** Integrate the development-selected predictive
model; add grounded goal hypotheses and information-seeking exploration; retain gradient adaptation
only if all prerequisites pass; prepare a stable milestone submission (Milestone 2, Sept 30, with a
no-TTT control). → G3.

**October 12–25 — contingency, analysis, and writing (v5 behind G4).** Close remaining evaluation
gaps; rerun symmetric defect fixes; prepare figures, manifests, documentation, and report; freeze the
learned architecture early enough to preserve runtime margin. Feature freeze Oct 18.

**October 26–November 2 — hardening and submission.** Remove unstable optional components; verify
deterministic fallback paths; validate packaging and licenses; submit the final agent.

**November 3–5 — research report submission.** Submit the report with confirmatory results frozen;
identify external evaluation as prospective where results are not yet available.

## 14. Pre-mortem

The modal failure narrative: harness works → the token model is exact on familiar transitions → the
latent model is stable on probes → neither discovers goals → exploration burns budget on irrelevant
novelty → TTT improves loss but hurts planning → the oracle gap is large and automatic subgoals
recover little → interface engineering eats the matrix window → integration forces shallow search →
the hidden score is low but nonzero → the paper holds many observations and no decisive result.

Countermeasures, in the same order: goal-acquisition metrics by W7; the frozen spine and single
primary contrast; TTT stress gates; oracle stratification; the matrix-launch gate; the contingency
reserve; and the honest floor statement.

## 15. Cut order

Remove optional complexity before weakening the scientific spine:

1. unrestricted goal-hypothesis learning;
2. v5 subgoal planner, then v3 learning components;
3. gradient-based test-time adaptation;
4. multiple-successor prediction;
5. hierarchical exact model on ARC folds;
6. extensive head-capacity sweeps;
7. exhaustive common-candidate audits on secondary conditions;
8. reconstruction-control fold replication, then capacity-control fold replication;
9. additional ARC replication beyond the default;
10. only then reduce the controlled synthetic factorial.

**Never cut:**

- the 48-model confirmatory core and the Interface C audit — they are the paper;
- exact archive baseline;
- exact-dynamics ceiling;
- compact reconstructive control on the synthetic suite and development games;
- common-candidate audit for principal conditions;
- off-policy recovery stratum;
- task-validity audit;
- game-level analysis;
- reproducible manifests.

## 16. Success criteria

### Strong scientific success

- controlled evidence for a target-by-hierarchy boundary;
- clear predictive signatures explaining the result;
- replicated synthetic mechanism findings;
- corresponding failure profiles on held-out ARC games;
- public reproducible code and data manifests.

### Solid scientific success

- no clear average winner, but robust localization of when latent prediction or hierarchy fails;
- useful exact, reconstructive, and latent comparisons;
- reliable end-to-end harness and external submission.

### Engineering success

- working hybrid agent;
- exact archive and event graph;
- stable sequential world model;
- documented evaluation and failure cases.

### Minimum acceptable outcome

- reproducible benchmark and planning harness;
- strong exact/archive baseline;
- transparent account of why the learned architecture did not reach confirmatory competence.
