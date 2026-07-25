# ARC-AGI-3 Sequential–Hierarchical World Model Research Plan

## 1. Purpose and posture

The project develops and evaluates a compact agent for unfamiliar, instruction-free, interactive grid environments. The central hypothesis is that effective control requires both:

- **sequential inference**, to infer environment-specific mechanics and hidden state from interaction history;
- **temporal hierarchy**, to reduce long-horizon search through grounded intermediate events.

A learned model is not trusted as the sole record of discrete state. The agent retains exact observations, exact transition deltas, and a persistent transition graph. Latent prediction supplies abstraction and transfer; exact memory supplies identity, contradiction detection, and execution safety.

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

---

## 2. Scientific hypotheses

### H1 — Sequential predictive-state inference

History conditioning improves control when current observations are insufficient because of:

- partial observability;
- hidden inventory or counters;
- environment-specific action semantics;
- delayed effects;
- rule switches;
- visually aliased states.

Evidence requires more than better next-frame prediction. The inferred context must decode action-effect mappings and improve counterfactual action ranking.

### H2 — Exact versus latent predictive targets

Reconstruction-free latent prediction helps when exact next-state prediction spends capacity on irrelevant variation or when transfer and data efficiency dominate.

Exact or reconstructive prediction helps when:

- one cell determines legality or success;
- transitions are brittle and irreversible;
- the latent encoder aliases control-distinct states;
- planner ranking depends on exact terminal identity.

### H3 — Grounded temporal hierarchy

Hierarchy improves planning when:

- local dynamics are sufficiently accurate;
- useful plans exist within the candidate generator;
- flat search cost grows rapidly with horizon or branching;
- goals require non-greedy prerequisite events;
- intermediate states are reachable by the low-level controller.

Hierarchy does not repair an inadequate predictive state or incorrect goal hypothesis.

### H4 — Exact archive support

A persistent exact transition graph reduces repeated exploration, protects against latent aliasing, grounds subgoals, and allows predictions to be checked against observed transitions.

### H5 — Hybrid agency

The complete hybrid agent outperforms either a purely exact archive system or a purely latent planner on environments combining unfamiliar mechanics, long horizons, and sparse progress evidence.

---

## 3. System conditions

### 3.1 Exact archive baseline

Components:

- exact observation hashing;
- exact changed-cell and connected-component deltas;
- directed transition graph;
- frontier and event novelty;
- shortest known replay paths;
- reversible-path tracking;
- coordinate-action proposal heuristics;
- deterministic contradiction logging.

This baseline is always retained. Learned components must improve useful progress per action or planning capability beyond it.

### 3.2 Sequential exact predictive model

Inputs:

- current and recent observation frames;
- recent actions;
- exact transition deltas;
- available-action metadata;
- retrieved relevant archive transitions.

Outputs:

- exact next-grid or exact delta distribution;
- event prediction;
- irreversibility prediction;
- action-availability prediction;
- counterfactual successor scores.

### 3.3 Sequential compact reconstructive model

A learned compact state is trained with a lightweight decoder for next-state or next-delta prediction. It controls for compact representation without removing exact reconstruction pressure.

### 3.4 Sequential latent predictive model

The model predicts target-encoder representations rather than the exact grid. Exact changed-cell, event, legality, and irreversibility auxiliaries ensure that action-critical information remains inspectable.

The default stabilization is an EMA target encoder with stop-gradient.

### 3.5 Grounded hierarchical models

Both exact and latent predictive systems can be paired with the same high-level protocol:

- event-state candidates from the archive, frontiers, and validated predictions;
- learned reachability probability;
- learned action cost;
- irreversible-risk estimate;
- high-level graph or beam search;
- low-level short-horizon planning;
- closed-loop execution and replanning.

The controlled synthetic study includes both target families with flat and hierarchical planning.

### 3.6 Exact-dynamics ceiling

The common candidate generator, reachability interface, and planner operate with exact simulator transitions. This identifies whether failures come from dynamics or from search, goal specification, or candidate generation.

---

## 4. Architecture invariants

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

Condition-specific heads are permitted only when their parameter and optimization budgets are matched and disclosed.

---

## 5. Data and environment design

### 5.1 Procedural boundary suite

The suite contains environment families with randomized layouts, visual assignments, object identities, and mechanic parameters.

Mandatory axes:

1. **Observability**
   - full state;
   - local view;
   - hidden counter or inventory;
   - delayed observation.

2. **Action semantics**
   - fixed globally;
   - remapped by environment;
   - state-dependent;
   - changed after an event.

3. **Dynamics**
   - reversible motion;
   - discrete toggles;
   - irreversible transformations;
   - delayed effects.

4. **State relevance**
   - broad geometry;
   - object relation;
   - one-cell-critical state;
   - visually identical but control-distinct state.

5. **Goal geometry**
   - direct approach;
   - key-before-door;
   - move-away-before-progress;
   - ordered event chain.

6. **Transition uncertainty**
   - deterministic;
   - observation aliasing;
   - hidden-mode transition;
   - genuine stochastic branching.

7. **Horizon**
   - one-step;
   - four-to-eight-step;
   - multi-event;
   - long maze or prerequisite chain.

8. **Generalization**
   - unseen layout;
   - unseen parameterization;
   - unseen combination of known mechanics;
   - held-out mechanic family.

Each family exposes train, validation, and test generators. Generator seeds and held-out combinations are committed before confirmatory analysis.

### 5.2 ARC-AGI-3 data

Public games are divided into:

- development games for implementation, tuning, task auditing, and launch gates;
- held-out cross-game folds for ecological evaluation.

Data sources:

- random and structured exploration;
- exact archive trajectories;
- released human replays as references and policy seeds;
- self-collected agent trajectories;
- counterfactual simulator branches where permitted.

A held-out game's trajectories are not used to train the model evaluated on that game.

### 5.3 Task strata

#### Replay-path goal reaching

Start and goal states are sampled from successful replay segments at predefined separations. This measures controlled local planning.

#### Counterfactual branches

From a replay state, execute legal actions not taken by the replay policy. Evaluate successor prediction and candidate ranking.

#### Recovery tasks

Introduce one to three plausible wrong actions, then ask the agent to return to a recoverable state or reach the goal.

#### Irreversible-event tasks

Evaluate prediction and avoidance of traps, destructive transformations, and one-way transitions.

#### Cross-level rule-use tasks

Provide interaction history from earlier levels and evaluate predictions or decisions in a later level without gradient updates.

#### Full-agent progress tasks

Measure useful progress per action under goal uncertainty and exploration.

Tasks remain nested within games. They are never treated as independent transfer units.

---

## 6. Evaluation interfaces

### 6.1 Exact task predicate

The simulator determines success and exact event occurrence. The predicate is never exposed to the learned model.

Equivalence transformations are executable, documented, and audited. Hidden state is included whenever it changes future transitions.

### 6.2 Goal representation

Controlled tasks provide a set of goal exemplars. End-to-end tasks instead use the goal-hypothesis module.

### 6.3 Standardized reachability interface

A common protocol predicts:

- probability that a candidate endpoint reaches the goal or subgoal;
- expected scored actions;
- probability of irreversible failure;
- calibration uncertainty.

Condition-specific adapters are kept small and matched. Head-capacity sensitivity is evaluated on development data.

### 6.4 Common-candidate audit

Identical action sequences are evaluated under every condition and executed in the exact simulator.

Audit stages:

1. best true candidate in the common pool;
2. predicted versus exact endpoint;
3. ranking from exact endpoints;
4. selected action executed closed-loop.

This separates candidate quality, dynamics fidelity, terminal evaluation, and execution effects.

### 6.5 Candidate pools

Two common pools are required:

- an exogenous pool generated independently of model proposals;
- a fixed-size union sampled evenly from all model proposal sources.

Pools are stratified by horizon, legality, true progress, endpoint diversity, irreversible events, and recovery requirement.

---

## 7. Metrics

### 7.1 Predictive-state metrics

- action-effect mapping accuracy;
- hidden-state discrimination;
- mechanic-shift detection;
- action-availability prediction;
- counterfactual action ranking.

### 7.2 Dynamics metrics

- whole-state exact match;
- changed-cell precision, recall, and F1;
- event and irreversible-transition accuracy;
- exact rollout survival by horizon;
- latent rollout error;
- direct-versus-composed prediction consistency.

### 7.3 Planning metrics

- true candidate-set ceiling;
- selected-candidate regret;
- oracle top-k recall;
- pairwise ranking accuracy;
- reachability calibration;
- expected versus actual action cost.

### 7.4 Closed-loop metrics

For a task with replay reference length \(A_{\mathrm{ref}}\) and agent action count \(A\):

\[
G =
\mathbf 1[\text{success}]
\min\left(1.15,\left(\frac{A_{\mathrm{ref}}}{A}\right)^2\right).
\]

This is called **Replay-Normalized Goal-Reaching Efficiency**. It is not presented as the official competition metric.

Also report:

- success probability;
- actions conditional on success;
- recovery probability;
- catastrophic failure probability;
- on-trajectory versus off-trajectory degradation.

### 7.5 End-to-end metrics

- useful irreversible events per action;
- discovered regions and mechanics per action;
- level advancement;
- goal-hypothesis calibration;
- official external score when available.

---

## 8. Confirmatory design

### 8.1 Controlled synthetic factorial

Primary conditions:

| Condition | Predictive target | Planning |
|---|---|---|
| Exact-flat | Exact state or delta | Flat |
| Exact-hierarchical | Exact state or delta | Grounded hierarchy |
| Latent-flat | Latent target | Flat |
| Latent-hierarchical | Latent target | Grounded hierarchy |

Three training seeds are used for every primary condition.

The compact reconstructive model is a mandatory mechanistic control on the principal environment families.

Primary contrasts:

1. latent versus exact under flat planning;
2. hierarchy gain under exact prediction;
3. hierarchy gain under latent prediction;
4. target-by-hierarchy interaction.

Predefined environment interactions focus on:

- partial observability;
- action remapping;
- one-cell-critical state;
- non-greedy prerequisites;
- transition aliasing;
- horizon.

### 8.2 ARC ecological comparison

Mandatory conditions:

- exact archive baseline;
- sequential exact-flat;
- sequential latent-flat;
- sequential latent-hierarchical;
- exact-dynamics ceiling.

Two training seeds per held-out fold are the default. A hierarchical exact model is added when the measured evaluation budget permits.

The ARC analysis emphasizes paired per-game effects and failure profiles rather than a universal superiority classification.

---

## 9. Statistical analysis

### 9.1 Synthetic suite

Environment instances are the primary independent units. Generator family and mechanic parameters are modeled hierarchically.

Report:

- mean paired effects;
- mechanic interactions;
- between-family heterogeneity;
- practical margins;
- held-out-combination performance;
- held-out-family stress results.

The generated suite supplies enough independent instances to estimate mechanism interactions with useful precision.

### 9.2 ARC public games

ARC games are treated as a finite benchmark set.

Report:

- paired game effects;
- fold-training-set sensitivity;
- per-seed results;
- leave-one-game-out and leave-one-fold-out analyses;
- mechanic-tagged descriptive effects;
- uncertainty intervals without extrapolating to all environments.

Levels and generated tasks are not independent transfer samples.

### 9.3 Failed runs

Infrastructure failures are rerun with the same configuration and seed.

Algorithmic collapse is retained as an outcome. A collapsed but executable checkpoint is evaluated. A condition with no executable checkpoint receives failure scores rather than being silently omitted.

---

## 10. Pre-matrix launch gates

### Gate A — Harness and exact baseline

Required:

- accepted local and external execution path;
- deterministic replay;
- exact transition archive;
- coordinate-action candidate generation;
- itemized latency table;
- at least \(10^5\) stored transitions;
- reproducible environment and data manifests.

Failure response: stop learned-agent work until the harness is reliable.

### Gate B — Planning headroom

Required on development tasks:

- exact dynamics plus oracle ranking solves at least 60% of eligible tasks;
- exact planning materially exceeds persistence and archive replay;
- the candidate pool contains successful candidates often enough to expose dynamics quality.

Failure response: redesign task generation, horizon, sampler, or goal interface. Do not launch the model matrix.

### Gate C — Task validity

Required:

- persistence success below 50%;
- exact oracle above 60%;
- stratified manual audit error below 5%;
- hidden-state and animation-equivalence error below 2%;
- adequate representation across horizon strata;
- no replay or game dominates the task set.

Failure response: repair the task generator and repeat the audit.

### Gate D — Model competence

For both exact and latent systems:

- at least two of three development seeds produce executable checkpoints;
- changed-cell or event metrics beat persistence;
- counterfactual ranking beats random;
- four-step prediction carries useful signal;
- runtime stays within the measured budget.

A stable but inferior latent model passes. Collapse or trivial prediction does not.

### Gate E — Interface validity

Required:

- exact-endpoint ranking materially exceeds random;
- the standardized head does not erase all differences among dynamics conditions;
- results are stable across a small and full head;
- candidate ranking remains calibrated enough for closed-loop use.

Failure response: redesign the interface before any confirmatory training.

### Gate F — Off-policy robustness

Required:

- both learned systems are evaluated on random, frontier, and recovery states;
- degradation is quantified;
- catastrophic error is below a predefined tolerance;
- training data include adequate exploratory support.

Failure response: expand the data mixture or narrow the claim to replay-supported control.

### Gate G — Precision and throughput

Required:

- a complete fold can be regenerated without manual intervention;
- projected compute uses no more than 65% of the available pre-report budget;
- projected person-time uses no more than 70% of remaining workdays;
- deployment retains at least 25% wall-clock reserve;
- simulated uncertainty supports either useful estimation or a clearly stated failure-localization study.

Failure response: reduce folds, conditions, or audit breadth before the matrix starts.

---

## 11. Hierarchy admission and retention

Hierarchy is admitted only when:

1. short-horizon prediction is adequate;
2. short-horizon ranking is adequate;
3. flat planning fails on verified non-greedy or long-horizon tasks;
4. increasing flat search does not close the gap economically;
5. oracle event subgoals improve success by at least 20%;
6. the low-level planner reaches oracle subgoals reliably.

Automatic grounded subgoals are retained only when they recover at least half of the oracle hierarchy gain without material runtime or catastrophe cost.

Candidate subgoals are initially restricted to:

- archive states;
- frontiers;
- detected event states;
- validated trajectory predictions;
- exact object-relation transformations supported by observed transitions.

---

## 12. Optional adaptation

### In-context adaptation

Always permitted:

- update sequence context;
- update archive;
- update mechanics hypotheses;
- retrieve contradictory or analogous transitions.

### Gradient adaptation

Admitted only after:

- synthetic dynamics-shift gain;
- rule reversal and re-adaptation;
- long-run no-shift drift test;
- shadow validation;
- norm caps;
- rollback;
- bounded runtime.

Updates are limited to small adapters or final predictor layers. The base encoder remains frozen unless there is strong evidence that perception, rather than dynamics, is the bottleneck.

---

## 13. Optional multimodal prediction

A multiple-successor model is considered only if:

- the complete observable history and metadata remain insufficient;
- longer context closes less than half of the successor gap;
- exact-state diagnostics exclude an encoder bug;
- residual successor modes are stable across seeds and environments.

Retention requires:

- at least 10 percentage points improvement in true-successor top-k recall or 0.04 gain in planning score;
- no more than 0.02 degradation on unimodal environments;
- no more than 20% median inference overhead unless the control gain is large;
- stable convergence in at least two of three seeds.

Otherwise the deterministic model remains the final system.

---

## 14. Schedule

### July 20–26 — specification and primary-source audit

- finalize hypotheses, environment axes, manifests, and launch gates;
- complete the minimum literature audit;
- play representative public games manually;
- define exact task predicates and event vocabulary.

### July 27–August 2 — harness and exact archive

- local and external execution path;
- deterministic replay;
- exact transition graph;
- random, frontier, event-novelty, and archive baselines;
- latency and reset accounting.

### August 3–9 — procedural suite and task generator

- implement synthetic environment families;
- build replay, counterfactual, recovery, and cross-level tasks;
- run task-validity audits;
- measure exact-planning ceilings.

### August 10–16 — complete vertical slice

- train one exact, one reconstructive, and one latent sequential model;
- fit the common reachability interface;
- run the full common-candidate audit;
- evaluate off-policy robustness;
- decide whether the confirmatory matrix launches.

### August 17–September 6 — controlled mechanism study

- train the synthetic factorial;
- run sequence-system-identification and composition tests;
- test oracle and grounded hierarchy;
- freeze mechanism conclusions after all conditions complete.

### September 7–27 — ARC held-out evaluation

- collect fold-bounded training data;
- train exact-flat, latent-flat, and latent-hierarchical models;
- run replay, branch, recovery, event, and rule-use tasks;
- produce paired game analyses.

### September 28–October 11 — end-to-end agent

- integrate the development-selected predictive model;
- add grounded goal hypotheses and information-seeking exploration;
- retain gradient adaptation only if all prerequisites pass;
- prepare a stable milestone submission.

### October 12–25 — contingency, analysis, and writing

- close remaining evaluation gaps;
- rerun symmetric defect fixes;
- prepare figures, manifests, documentation, and report;
- freeze learned architecture early enough to preserve runtime margin.

### October 26–November 2 — hardening and submission

- remove unstable optional components;
- verify deterministic fallback paths;
- validate packaging and licenses;
- submit the final agent.

### November 3–5 — research report submission

- submit the report with confirmatory results frozen;
- identify external evaluation as prospective where results are not yet available.

---

## 15. Cut order

Remove optional complexity before weakening the scientific spine:

1. unrestricted goal-hypothesis learning;
2. gradient-based test-time adaptation;
3. multiple-successor prediction;
4. hierarchical exact model on ARC folds;
5. extensive head-capacity sweeps;
6. exhaustive common-candidate audits on secondary conditions;
7. additional ARC replication beyond the default;
8. only then reduce the controlled synthetic factorial.

Never cut:

- exact archive baseline;
- exact-dynamics ceiling;
- compact reconstructive control;
- common-candidate audit for principal conditions;
- off-policy recovery stratum;
- task-validity audit;
- game-level analysis;
- reproducible manifests.

---

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
