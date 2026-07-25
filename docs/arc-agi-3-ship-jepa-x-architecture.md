# SHiP-JEPA-X Architecture Specification

## Sequential–Hierarchical Predictive JEPA with Exact-State Support

## 1. Design objective

SHiP-JEPA-X is a compact agent architecture for unfamiliar interactive grid environments with:

- no natural-language instructions;
- unknown action semantics;
- sparse progress evidence;
- exact discrete transitions;
- possible partial observability;
- long non-greedy solution paths;
- irreversible mistakes;
- coordinate-based interactions.

The architecture is designed around a separation of responsibilities:

- **neural sequence inference** estimates hidden state and environment mechanics;
- **local predictive models** evaluate counterfactual actions;
- **grounded hierarchy** reduces long-horizon search;
- **exact memory** preserves state identity and known transitions;
- **goal hypotheses** represent uncertainty about what constitutes progress;
- **verification and replanning** prevent open-loop accumulation of model error.

The architecture does not assume that a continuous latent vector is an exact simulator or that latent distance is a valid goal cost.

---

## 2. Agent state

At time \(t\), the agent state is:

\[
\mathcal S_t =
(z_t,\; c_t,\; b_t,\; g_t,\; \mathcal A_t).
\]

### \(z_t\): current predictive state

A spatial latent representation retaining:

- object positions;
- local geometry;
- exact relational structure;
- action-relevant cell details;
- inventory and switch state;
- controllable-object identity;
- current affordances.

Recommended shape:

\[
z_t \in \mathbb R^{H_z \times W_z \times d}
\]

with an additional global state token.

### \(c_t\): inferred mechanics context

Represents environment-specific transition rules:

- meaning of each available action;
- state-dependent action effects;
- reversibility;
- delayed effects;
- object interaction rules;
- current rule regime;
- cross-level mechanic continuity.

### \(b_t\): mechanics belief set

A small set of alternative context hypotheses:

\[
b_t = \{(c_t^{(j)},w_t^{(j)})\}_{j=1}^{J}.
\]

The set prevents incompatible explanations from being prematurely averaged.

### \(g_t\): goal belief

A weighted bank of candidate progress hypotheses:

\[
g_t = \{(G_k,\pi_k)\}_{k=1}^{K_g}.
\]

Goal hypotheses may represent event completion, object relations, region access, state regularity, or cross-level patterns.

### \(\mathcal A_t\): exact episodic archive

A directed multigraph storing exact observed states and transitions.

---

## 3. Inputs

Each environment step supplies an atomic observation bundle:

\[
o_t =
(\text{frames}_t,\text{metadata}_t,\text{available actions}_t).
\]

The model additionally consumes:

- previous action \(a_{t-1}\);
- coordinate parameters when present;
- exact delta \(\Delta_t = D(o_{t-1},o_t)\);
- detected event candidates;
- retrieved archive transitions;
- level and reset boundary markers.

Environment identity, game name, or hidden split labels are never model inputs.

---

## 4. Exact perception path

### 4.1 Grid canonicalization

The deterministic front end:

- preserves categorical cell values;
- records original frame dimensions;
- separates multiple frames;
- marks padding explicitly;
- preserves metadata and available-action masks;
- hashes exact observations.

### 4.2 Transition-delta parser

For each observed transition, compute:

- changed-cell coordinates;
- old and new categorical values;
- connected components before and after;
- candidate translations;
- candidate rotations and reflections;
- recolouring;
- appearance and disappearance;
- component merge and split;
- action-availability changes;
- persistent versus animation-only changes;
- candidate irreversible events.

The parser emits hypotheses rather than claiming semantic certainty.

### 4.3 Object and relation candidates

Connected components and repeated patterns generate provisional object tokens:

\[
q_i =
(\text{mask},\text{colour},\text{shape},\text{position},\text{relations}).
\]

These tokens supplement raw grid tokens. They do not replace them.

---

## 5. Neural grid encoder

A small CNN or two-dimensional transformer maps the atomic bundle to spatial tokens.

### Cell embedding

Each cell token combines:

- categorical value embedding;
- row and column embeddings;
- frame index;
- padding mask;
- local connected-component features;
- changed-cell flag when processing a transition pair.

### Global tokens

Global tokens encode:

- available-action mask;
- metadata;
- frame dimensions;
- reset or level boundary;
- pooled object relations.

### Recommended configuration

- spatial token width: 128–192;
- encoder depth: 4–6 blocks;
- local attention or convolution for efficiency;
- occasional global attention for long-range relations;
- output grid: 8×8 or 16×16 depending on input size.

The encoder produces:

\[
e_t = E(o_t).
\]

An EMA target encoder produces training targets for latent prediction.

---

## 6. Sequential environment inference

### 6.1 Dense recent context

For a recent window of \(K\) transitions, construct tokens:

\[
x_i =
[e_i,\; a_i,\; \Delta_{i+1},\; m_i,\; r_i],
\]

where:

- \(e_i\) is the encoded observation;
- \(a_i\) is the action and coordinate;
- \(\Delta_{i+1}\) is the exact observed delta;
- \(m_i\) is action availability and metadata;
- \(r_i\) is a reset or level-boundary marker.

Recommended dense window: 16–32 transitions.

### 6.2 Archive retrieval

A query derived from the current state retrieves 8–16 transitions by:

- exact or near-exact state match;
- same object configuration;
- same action;
- contradictory successor;
- same detected event;
- same region or level;
- same goal hypothesis relevance.

Retrieved transitions are encoded with source and recency markers.

### 6.3 Context transformer

The sequence transformer outputs:

\[
(z_t,c_t,q_t,p_{\text{shift}},p_{\text{alias}}).
\]

- \(z_t\): current predictive state;
- \(c_t\): mechanics context;
- \(q_t\): archive query;
- \(p_{\text{shift}}\): probability that the mechanic regime changed;
- \(p_{\text{alias}}\): probability that the current visual observation is not a sufficient state.

### 6.4 Context supervision

The context is trained through predictive and auxiliary tasks:

- next-latent prediction;
- exact event prediction;
- action-effect signature;
- available-action prediction;
- transition-pair mechanic matching;
- rule-shift detection;
- counterfactual action ranking;
- mapping-decoding probes on synthetic environments.

The critical test is not whether \(c_t\) stores history. It is whether it enables correct environment-specific predictions from otherwise similar visible states.

---

## 7. Local dynamics model

### 7.1 Action-conditioned prediction

For horizon \(h\):

\[
\hat z_{t+h} =
P_h(z_t,c_t,a_{t:t+h-1}),
\qquad
h\in\{1,2,4,8\}.
\]

Direct multi-horizon heads are trained alongside recursive rollout.

### 7.2 Composition consistency

For two actions:

\[
\mathcal L_{\mathrm{comp}} =
d\left(
P_2(z_t,c_t,a_t,a_{t+1}),
P_1(P_1(z_t,c_t,a_t),c_t,a_{t+1})
\right).
\]

Equivalent checks extend to four and eight steps.

This distinguishes a compositional transition model from a one-step lookup system.

### 7.3 Exact control-critical auxiliaries

The latent predictor also estimates:

- changed-cell mask;
- changed categorical values;
- event type;
- available-action changes;
- irreversible-transition probability;
- reset or terminal risk;
- model confidence.

These auxiliaries preserve inspectable discrete information without requiring full unchanged-grid reconstruction in every rollout.

### 7.4 Exact predictive model

The exact condition shares the encoder and sequence interface where practical but predicts:

- full next-grid categorical distribution, or
- sparse next-delta plus unchanged-state copy.

Sparse delta prediction is preferred when full-grid loss is dominated by persistence.

### 7.5 Compact reconstructive model

The reconstructive control predicts through a compact state and lightweight next-state decoder. It tests whether any benefit comes from compression rather than reconstruction-free learning.

---

## 8. Mechanics belief management

### 8.1 Hypothesis initialization

When entering a new environment or detecting a rule shift, initialize \(J\) context hypotheses from:

- the sequence encoder posterior;
- common action-effect priors learned from training environments;
- alternative interpretations suggested by contradictory transitions;
- retrieved analogous environments without using identity labels.

Recommended \(J=4\) initially.

### 8.2 Bayesian-style weight update

For each observed transition:

\[
w_{t+1}^{(j)}
\propto
w_t^{(j)}
\exp\left[-\ell_j(o_{t+1}\mid o_t,a_t)\right].
\]

Normalize and prune low-weight hypotheses.

### 8.3 Hypothesis splitting

Split a hypothesis when:

- predicted successors remain multimodal;
- effects differ by object or region;
- an action meaning changes after an event;
- current history may contain aliased hidden state.

### 8.4 Hypothesis merge

Merge hypotheses that produce indistinguishable counterfactual distributions over the current reachable state set.

---

## 9. Exact episodic archive

### 9.1 Node record

Each node stores:

- exact observation hash;
- exact observation or compressed lossless record;
- encoder representation;
- inferred objects and relations;
- level and episode position;
- goal-hypothesis scores;
- visitation count;
- terminal and reset status.

### 9.2 Edge record

Each directed edge stores:

- source node;
- action and coordinate;
- target node;
- exact delta;
- event tags;
- reversibility evidence;
- execution count;
- observed outcome distribution;
- model prediction and error at execution time.

### 9.3 Graph services

The archive supports:

- exact replay;
- shortest known path;
- frontier identification;
- cycle detection;
- reversible return paths;
- event bottleneck discovery;
- contradiction retrieval;
- candidate subgoal generation;
- exact transition substitution during planning.

Known transitions always override model predictions.

---

## 10. Event representation

An event state is:

\[
v_i =
(z_i,\phi_i,\tau_i),
\]

where:

- \(z_i\) is the predictive state;
- \(\phi_i\) is an exact event signature;
- \(\tau_i\) is the time or action cost from the preceding event.

Event candidates include:

- new region entered;
- object acquired or attached;
- switch or control mode changed;
- obstacle removed;
- irreversible transformation;
- action set changed;
- persistent structural relation achieved;
- level advanced;
- reset or terminal failure.

Events are discovered from exact deltas and recurrent transition patterns, then clustered by effect.

---

## 11. Reachability model

For current state \(s_i\), candidate subgoal \(s_j\), and mechanics context \(c_t\):

\[
R(s_i,s_j,c_t)
=
(p_{\mathrm{reach}},\hat A,p_{\mathrm{risk}},\sigma).
\]

Outputs:

- probability of reaching the subgoal;
- expected scored actions;
- probability of irreversible failure;
- uncertainty.

Training data come from:

- archive path pairs;
- replay segments;
- simulator branches;
- failed planning attempts;
- synthetic exact shortest paths;
- negative unreachable pairs.

Cross-environment training emphasizes relational and event features rather than environment identity.

---

## 12. Grounded hierarchy

### 12.1 Candidate subgoal set

The high-level planner may choose from:

1. exact archive states;
2. frontier states;
3. observed event-state prototypes;
4. predicted future states validated by an empirical-manifold test;
5. object-relation transformations supported by observed transition rules.

Arbitrary latent vectors are not accepted as executable goals.

### 12.2 High-level edge cost

\[
C(i,j)=
\frac{\hat A_{ij}}{p_{\mathrm{reach},ij}+\epsilon}
+
\lambda_r p_{\mathrm{risk},ij}
+
\lambda_u \sigma_{ij}
-
\lambda_g \operatorname{Progress}(j).
\]

### 12.3 High-level search

Use A*, best-first search, or a bounded beam over event states.

High-level search horizon: two to four event transitions initially.

### 12.4 Low-level planner

For the selected next subgoal:

- reuse an exact archive path when available;
- otherwise generate primitive and macro candidates;
- roll out four to eight steps;
- evaluate progress, reachability, risk, and uncertainty;
- execute only the first action or a verified short chunk.

### 12.5 Hierarchy admission

The hierarchy is enabled only after:

- local prediction competence;
- flat-search failure;
- oracle-subgoal gain;
- reliable low-level subgoal reachability.

---

## 13. Macro-actions

### 13.1 Replay macros

Previously executed action chunks associated with a stable event.

### 13.2 Generic parameterized skills

- navigate to coordinate;
- approach object;
- click candidate;
- repeat until change;
- retreat along reversible path;
- visit nearest frontier;
- restore last known safe state.

### 13.3 Effect-clustered macros

Action sequences grouped by exact observed effect:

- move controlled entity;
- toggle state;
- acquire object;
- reveal region;
- align objects;
- transfer colour or pattern.

The architecture does not require a learned continuous macro-action vocabulary.

---

## 14. Coordinate-action handling

Coordinate actions are factored into action type and coordinate proposal.

\[
P(a,x,y)
=
P(a)\,P(x,y\mid a,z_t,c_t).
\]

Candidate coordinates come from:

- object centroids;
- object boundaries;
- recently changed cells;
- symmetry correspondences;
- unexplored cells;
- distinguished regions;
- previous successful coordinates;
- uncertainty-disagreement hotspots.

A coordinate proposal head ranks candidates. The planner evaluates only the top bounded set.

---

## 15. Goal-hypothesis module

### 15.1 Goal hypothesis classes

Candidate hypotheses include:

- reach a region;
- create or remove an object relation;
- activate a set of switches;
- transform all members of a pattern;
- align or symmetrize components;
- place a controllable object in a distinguished region;
- trigger a persistent event;
- reproduce a relation inferred from earlier levels;
- maximize a discovered progress signal.

### 15.2 Evidence update

Goal weights are updated from:

- level advancement;
- terminal failure;
- irreversible events;
- newly unlocked actions or regions;
- recurring relations across levels;
- human-replay progress states used only where permitted;
- consistency with observed environment design.

### 15.3 Planning value

\[
V(s)=
\sum_k \pi_k G_k(s)
+
\beta I_{\mathrm{mechanics}}(s)
+
\gamma I_{\mathrm{goal}}(s)
-
\lambda_A \hat A(s)
-
\lambda_R p_{\mathrm{risk}}(s).
\]

The system distinguishes learning what happens from learning what is useful.

---

## 16. Exploration controller

For candidate action or short plan \(a\):

\[
U(a)=
\alpha\,\mathbb E[\text{goal progress}]
+
\beta\,\mathbb E[\text{mechanics information gain}]
+
\gamma\,\mathbb E[\text{new reachable events}]
-
\lambda\,\mathbb E[\text{irreversible risk}]
-
\eta\,\text{scored action cost}.
\]

Information gain is approximated from disagreement among live mechanics hypotheses and predicted goal hypotheses.

Preferred experiments include:

- same action near different object classes;
- action before and after a switch;
- reversible probes before irreversible ones;
- coordinate clicks on representative object and background classes;
- actions with high hypothesis disagreement and bounded downside.

---

## 17. Exact verifier

Before execution, the verifier checks:

- action legality;
- agreement with known exact archive edges;
- consistency with available-action metadata;
- predicted irreversible risk;
- whether a subgoal is archive-supported or validated;
- whether the proposed path preserves a return route when uncertainty is high;
- divergence among mechanics hypotheses.

After execution, it checks:

- exact delta versus predicted delta;
- event occurrence;
- target-node identity;
- rule-shift evidence;
- whether graph edges and hypotheses must be invalidated.

A verifier veto produces either a safer candidate or an information-seeking action.

---

## 18. Closed-loop algorithm

```text
initialize exact archive, mechanics hypotheses, and goal hypotheses

for each environment step:
    parse the atomic observation bundle
    compute exact transition delta from the previous observation
    update the exact transition graph
    retrieve relevant historical transitions

    infer predictive state and mechanics context
    update mechanics-hypothesis weights
    update goal-hypothesis weights

    if a known exact path reaches a high-value state:
        propose the first safe action on that path
    else:
        generate grounded event subgoals
        score reachability, action cost, risk, and goal value
        choose a high-level subgoal
        generate local action candidates
        roll out candidates through exact archive edges and the local model
        rank candidates under all live mechanics hypotheses

    verify the selected action or short chunk
    execute the first approved action
    compare prediction with the observed transition
    replan
```

The default commitment is one environment action. Longer chunks are used only on exact known paths or when predicted outcomes are highly reliable and reversible.

---

## 19. Training objectives

The total loss is:

\[
\begin{aligned}
\mathcal L =\;&
\mathcal L_{\mathrm{latent},1}
+\lambda_2\mathcal L_{\mathrm{latent},2}
+\lambda_4\mathcal L_{\mathrm{latent},4}
+\lambda_8\mathcal L_{\mathrm{latent},8}\\
&+\lambda_\Delta\mathcal L_{\mathrm{delta}}
+\lambda_e\mathcal L_{\mathrm{event}}
+\lambda_a\mathcal L_{\mathrm{availability}}\\
&+\lambda_i\mathcal L_{\mathrm{irreversible}}
+\lambda_c\mathcal L_{\mathrm{composition}}\\
&+\lambda_{\mathrm{cf}}\mathcal L_{\mathrm{counterfactual}}
+\lambda_m\mathcal L_{\mathrm{mechanics}}\\
&+\lambda_r\mathcal L_{\mathrm{reachability}}
+\lambda_A\mathcal L_{\mathrm{action\ cost}}.
\end{aligned}
\]

### Sampling priorities

Oversample:

- changed-state transitions;
- irreversible events;
- alternate actions from the same state;
- same observation under different hidden contexts;
- same action with different effects;
- long prerequisite chains;
- failed predictions;
- recovery states;
- goal-relevant events.

Persistence-dominated data are downweighted or represented through a copy-plus-delta formulation.

---

## 20. Parameter budget

A compact implementation can target approximately 20 million trainable parameters.

| Module | Approximate parameters |
|---|---:|
| Spatial grid encoder | 4.0M |
| Sequential context transformer | 5.5M |
| Local predictive model | 3.5M |
| Multi-horizon and event heads | 2.0M |
| Reachability and action-cost model | 1.5M |
| Goal and exploration heads | 1.0M |
| Coordinate proposal head | 0.8M |
| Adapters and calibration | 0.7M |
| Reserve | 1.0M |
| **Total** | **20.0M** |

The archive, graph algorithms, delta parser, verifier, and search procedures are nonparametric.

---

## 21. Runtime controls

### Candidate governor

Reduce search in this order:

1. fewer optional coordinate candidates;
2. shorter local horizon;
3. narrower high-level beam;
4. disable uncertainty ensembles;
5. disable hierarchy;
6. use archive and exact graph only.

### Reliability governor

Demote the agent when:

- rollout disagreement exceeds tolerance;
- exact delta error rises sharply;
- reachability calibration fails;
- no validated subgoal exists;
- rule-shift probability is high;
- time reserve falls below the required margin.

Fallback modes:

1. full sequential hierarchical agent;
2. sequential flat model;
3. exact archive and graph agent;
4. conservative frontier exploration.

---

## 22. Adaptation

### Default adaptation

- update exact archive;
- update mechanics hypotheses;
- update sequence context;
- retrieve relevant transitions;
- recalibrate confidence online without labels.

### Optional gradient adaptation

Update only:

- small context adapters;
- final dynamics layers;
- calibration maps.

Every update uses:

- recent training samples;
- separate shadow samples;
- rollback on degradation;
- norm cap;
- bounded update count;
- archive embeddings generated by the frozen base encoder.

Full encoder updates are excluded from ordinary deployment because they would invalidate stored latent states and reachability relationships.

---

## 23. Multiple successor modes

A multiple-predictor extension is considered only after demonstrating residual branching under a complete observable predictive state.

The predictor returns a bounded set:

\[
\{\hat z_{t+1}^{(1)},\ldots,\hat z_{t+1}^{(M)}\}.
\]

Each mode carries:

- probability;
- event prediction;
- exact delta auxiliary;
- calibration score.

Planning penalizes unsupported mode count. Successor top-k recall is reported together with precision so that hallucinating many branches does not appear beneficial.

---

## 24. Development sequence

### Stage 1 — exact archive system

Deliver:

- deterministic parser;
- transition graph;
- replay;
- frontier and event novelty;
- coordinate proposals;
- exact planning ceilings.

### Stage 2 — sequential predictive state

Deliver:

- grid encoder;
- sequence context;
- exact and latent one-step prediction;
- action-effect mapping diagnostic;
- counterfactual ranking;
- off-policy evaluation.

### Stage 3 — multi-horizon local planning

Deliver:

- two-, four-, and eight-step heads;
- composition tests;
- flat closed-loop planner;
- standardized reachability interface.

### Stage 4 — grounded event hierarchy

Deliver:

- event-state extraction;
- oracle subgoal evaluation;
- reachability-constrained high-level search;
- archive-supported automatic subgoals.

### Stage 5 — goal uncertainty and exploration

Deliver:

- goal-hypothesis bank;
- mechanics information gain;
- progress-per-action exploration;
- conservative irreversible-risk handling.

### Stage 6 — optional adaptation and multimodality

Add only after the corresponding admission gates pass.

---

## 25. Required ablations

| Condition | Sequence | Latent target | Hierarchy | Exact archive | Goal uncertainty |
|---|---:|---:|---:|---:|---:|
| Archive baseline | No | No | Graph only | Yes | Heuristic |
| Exact-flat | Yes | No | No | Yes | Controlled |
| Exact-hierarchical | Yes | No | Yes | Yes | Controlled |
| Reconstructive-flat | Yes | Compact | No | Yes | Controlled |
| Latent-flat | Yes | Yes | No | Yes | Controlled |
| Latent-hierarchical | Yes | Yes | Yes | Yes | Controlled |
| End-to-end hybrid | Yes | Yes or selected | Yes | Yes | Learned + heuristic |

Additional ablations:

- no archive retrieval;
- no exact delta auxiliary;
- no mechanics belief set;
- raw latent distance versus whitened distance versus reachability;
- arbitrary latent subgoals versus grounded subgoals on development tasks;
- fixed context versus environment-specific context;
- in-context adaptation versus gradient adaptation.

---

## 26. Failure interpretation

### Strong local prediction, weak action ranking

Likely cause:

- goal geometry or reachability interface.

### Strong exact-endpoint ranking, weak model-endpoint ranking

Likely cause:

- transition prediction or rollout compounding.

### Strong flat planning on short tasks, collapse on long non-greedy tasks

Likely cause:

- search horizon; hierarchy is justified.

### Strong oracle-subgoal gain, weak automatic hierarchy

Likely cause:

- subgoal discovery or reachability grounding.

### Good replay-path control, weak recovery

Likely cause:

- training-distribution support and off-policy robustness.

### Same visible state requires different actions, context fails to separate it

Likely cause:

- predictive-state insufficiency or retrieval failure.

### Multiple predicted modes but low successor precision

Likely cause:

- hallucinated multimodality rather than genuine branching.

### Accurate dynamics, no useful progress

Likely cause:

- goal acquisition or exploration, not world modeling.

---

## 27. Architectural commitment

The committed architecture is hybrid:

\[
\boxed{
\text{sequence inference}
+
\text{local predictive dynamics}
+
\text{grounded event hierarchy}
+
\text{exact episodic graph}
+
\text{goal and mechanics beliefs}
+
\text{closed-loop verification}
}
\]

No single component is assumed to solve unfamiliar environments alone. The system is designed so that every major failure can be attributed to a specific interface and replaced or simplified without discarding the complete agent.
