# ARC-AGI-3 × Sequential–Hierarchical Predictive World Models — Executive Summary

**Frozen 2026-07-23.** Companions: [`arc-agi-3-execution-plan.md`](arc-agi-3-execution-plan.md)
(schedule, gates, decision rules) and
[`arc-agi-3-ship-jepa-x-architecture.md`](../arc-agi-3-ship-jepa-x-architecture.md) (component
specification).

## Abstract

A solo project spanning about sixteen calendar weeks — a July 20–26 design-freeze week plus fifteen
execution weeks to November 8, 2026 — using the ARC Prize 2026 ARC-AGI-3 Kaggle competition as the
vehicle for learning and evaluating JEPA-style latent world models.

The scientific object is whether a compact, history-conditioned world model can infer the mechanics
of an unfamiliar interactive environment and use a grounded temporal hierarchy to act efficiently
over long horizons. The target system combines four capabilities:

1. **Sequential predictive-state inference** from recent and retrieved observation–action transitions.
2. **Short-horizon exact or latent dynamics prediction** for local counterfactual planning.
3. **Reachability-constrained hierarchical planning** over observed or validated event states.
4. **Exact episodic memory and verification** to preserve discrete correctness and prevent
   unsupported latent plans.

The mandatory scientific core is a frozen, compute-matched comparison of two pre-specified systems
representative of the exact-token and latent-predictive objective families, crossed with Markov
versus sequence context, evaluated on mechanics-stratified held-out games with predeclared
endpoints. The registered claim is deliberately narrow: goal-conditioned planning over
replay-derived, within-level subtasks, where supplied exemplars remove goal discovery. Family-level
and benchmark-level generalization are not claimed; a preregistered synthetic mechanism suite and
secondary strata — off-policy recovery, level completion — carry the where and why questions.

The objective is not to show that latent prediction is universally superior to exact prediction. It
is to identify the conditions under which abstraction and temporal hierarchy earn their complexity,
and to localize failures among state inference, transition prediction, subgoal reachability, goal
acquisition, and exploration.

A dual-head agent is retained as an engineering condition only. Model-guided exploration, test-time
adaptation, and subgoal hierarchy enter committed scope only when predeclared bottleneck tests
justify them.

The primary deliverable is durable expertise and a reproducible public codebase; the secondary is a
controlled answer to where latent prediction helps or hurts in exact, interactive, instruction-free
environments with sparse progress feedback. Agent submission November 2; paper by about November 5,
since ties favor the earliest entry. Competitive placement is not an objective.

## Research question

Under matched data, model capacity, interaction budgets, and planning budgets:

> When do history-conditioned latent dynamics and grounded temporal hierarchy improve
> action-efficient control relative to exact-state predictive models, and when do discrete aliasing,
> unreachable subgoals, or goal uncertainty eliminate the benefit?

Equivalently, in objective-family terms: under matched data, capacity, planner interface, and
interaction budgets, when does latent prediction improve transfer or action-efficient planning
relative to exact token prediction — and when does latent aliasing remove the discrete information
control requires?

The project separates three questions that are often conflated:

- **Can the agent infer a sufficient predictive state from interaction history?**
- **Can the world model predict action consequences accurately enough for planning?**
- **Can temporal hierarchy reduce search cost without proposing impossible intermediate states?**

Goal acquisition and exploration are evaluated separately and only then recombined in the end-to-end
agent.

## What — one stabilization stage, two tracks, one codebase, not one critical path

**Stabilization (timeboxed: five working days).** Ship an EMA target with stop-gradient by default;
fall back to VICReg-style variance/covariance regularization only if that fails; run SIGReg as a
development-only diagnostic under its required batch and whitening controls, and only if time
remains. Rank, covariance, and whitened probes are debugging tools here, not endpoints.

**The frozen experiment (Track A — the paper).** Token-only and latent-only world models under a
fixed budget of 20M trainable parameters per primary condition, matched within ±5%, with matched
training data, splits, optimization budget, and planning expansions; each family crossed with Markov
versus sequence context, the Markov arm receiving the full atomic observation bundle. Controls: a
token-only model matched to the dual-head system's total capacity, and a compact reconstruction
model that separates "the prediction target discards information" from "compact learned state
discards information." Every primary condition is replicated across three training seeds — 48
mandatory models, 72 including controls, roughly 290 GPU-hours.

Evaluation runs on a locked, mechanics-stratified held-out split never used for training, early
stopping, hyperparameter selection, or probe fitting. Mechanic-family labels, game-version hashes,
replay snapshots, and fold assignments are frozen before any result is inspected. Five development
games carry all tuning and calibration; the remaining twenty sit in four outer folds, each game held
out exactly once, with every learned evaluator bounded by the same folds.

One predeclared primary contrast — latent-sequence versus token-sequence — with Markov arms as
mechanistic controls. The primary metric is Replay-Normalized Goal-Reaching Efficiency: squared
action ratio, 1.15 cap, frozen replay-segment counts as the uniform denominator, shortest-path and
stronger-search denominators reported only as sensitivity analyses, failures scoring zero. A
decision-anchored equivalence margin classifies outcomes as advantage, practical equivalence, or
inconclusive; the primary analysis is estimation-first, reporting the effect with its interval and
decomposed readouts rather than leaning on the classification.

Candidate ranking runs through a frozen, cross-fitted, matched-protocol goal interface — identical
architecture, data, and budget per condition, weights necessarily differing — with native
representation-space costs reported separately as the systems comparison. A same-candidate oracle
audit rolls identical candidates through every model and executes them in the deterministic
simulator, so failure attribution rests on ground truth rather than a learned judge. This control
matters: Trajectory Reachability Metrics showed that changing only the planner-facing terminal cost
can move a latent planner from 7% to 97% success — an interface effect large enough to swamp any
prediction-target effect if left uncontrolled.

A matrix-launch gate makes the vertical slice a go/no-go: exact-dynamics headroom, task validity,
two-system competence (explicitly not superiority), interface attribution, off-policy robustness,
and precision plus full-pipeline cost must all pass on development games before the matrix is
authorized. Track B adopts the development-selected family, so confirmatory folds stay sealed until
scientific unblinding and agent decisions never peek at the result. Once conclusions are frozen, the
competition model is retrained on all permitted public data; the hidden Kaggle score is ecological
validation of the end-to-end agent, not of the matched contrast.

**Conditional agent extensions (Track B).** An exact replay harness and archive baseline come first.
Exploration methods — random, state novelty, event novelty, predictive disagreement,
progress-exemplar similarity, and an oracle-progress upper bound — are compared on useful progress
per action: irreversible transitions, level-transition discovery, completion, and resulting RN-GRE,
never raw state coverage. Per-game test-time adaptation enters only after passing a synthetic
dynamics-shift gate with rollback safeguards and two stress tests. Oracle subgoals are evaluated
only if flat planning fails despite adequate model accuracy, and automatic subgoals only if the
oracle gain clears its threshold. A learned hierarchical level is outside committed scope.

## Target architecture

The target agent is **SHiP-JEPA-X: Sequential–Hierarchical Predictive JEPA with exact-state
support**. It describes what the agent becomes if every gate fires — not the week-one system and not
a build order.

Its internal state is:

\[
\text{agent state}
=
\text{predictive latent}
+
\text{mechanics belief}
+
\text{goal belief}
+
\text{exact episodic graph}.
\]

The operating loop is:

\[
\text{infer mechanics}
\rightarrow
\text{select a grounded event subgoal}
\rightarrow
\text{plan locally}
\rightarrow
\text{verify}
\rightarrow
\text{act}
\rightarrow
\text{update}.
\]

The architecture contains:

- a categorical grid encoder retaining spatial tokens;
- an exact transition-delta parser;
- a sequence transformer that infers current state and environment mechanics;
- one-, two-, four-, and eight-step predictive heads;
- auxiliary changed-cell, event, legality, and irreversibility heads;
- an exact transition archive and event graph;
- a learned reachability and action-cost model;
- an event-level hierarchical planner restricted to archive-supported or validated subgoals;
- a goal-hypothesis bank and information-seeking exploration policy;
- closed-loop verification, with an irreversible-risk veto, after every action or short action chunk.

Standing design choices: coordinate actions are factored as P(ACTION6) × P(x,y | state, context)
with candidates drawn from object centroids, changed components, boundaries, and unexplored cells;
macros are grounded — replay chunks, parameterized local skills, and effect-clustered archive edges
— never learned latent macro-actions first; subgoals are drawn only from archive nodes, frontier
states, event prototypes, or predicted states passing a manifold test.

EMA target encoding and stop-gradient are the default latent-learning stabilizers. Batch-statistic
regularizers are diagnostics only. Multiple successor predictors are admitted only after residual
multimodality remains once observation completeness, context length, and encoder fidelity have been
checked.

## Evidence design

### Controlled mechanism study

A synthetic boundary suite generates many independent environments while varying one or a small
number of factors:

- visible versus partially observable state;
- fixed versus environment-specific action semantics;
- smooth versus exact irreversible transitions;
- broad versus one-cell-critical state relevance;
- direct versus non-greedy prerequisite goals;
- unimodal versus genuinely aliased successors;
- short versus compositional horizons;
- familiar versus held-out combinations of mechanics.

The committed design is eight paired one-factor-at-a-time micro-environments with easy and stress
arms — not a 2⁸ factorial. Holding sequence conditioning fixed, the synthetic factorial varies:

| Factor | Condition 1 | Condition 2 |
|---|---|---|
| Predictive target | Exact state or exact delta | Reconstruction-free latent state |
| Planning scale | Flat short-horizon planning | Grounded event hierarchy |

A compact reconstructive model provides a mechanistic control between exact and reconstruction-free
prediction. An exact-simulator planner supplies the planning ceiling. This suite is the main source
of claims about *why* a method succeeds or fails, and it carries the mechanism and "where" claims
while the ARC primary carries the system comparison. The paper stays ARC-facing.

### ARC-AGI-3 ecological study

Public games are divided into development and held-out training folds. The ARC study evaluates:

- replay-path goal reaching;
- off-trajectory branches;
- recovery after plausible wrong actions;
- irreversible-event prediction;
- counterfactual action ranking;
- cross-level rule use;
- full-agent useful progress per action.

Games are the transfer units. Generated tasks, levels, and replay segments are nested observations
rather than independent samples. The ARC results are interpreted as performance over a finite public
benchmark set; they are not treated as proof of generalization to all interactive environments or
unseen mechanic families.

## Mandatory comparisons

The minimum system set is:

1. **Exact archive and graph baseline** — deterministic transition memory, frontier exploration,
   event graph, and replay.
2. **Sequential exact predictive model** — history-conditioned exact-grid or exact-delta prediction
   with flat planning.
3. **Sequential compact reconstructive model** — learned compact state with a lightweight exact
   next-state decoder.
4. **Sequential latent predictive model** — reconstruction-free latent dynamics with exact
   control-critical auxiliaries.
5. **Sequential latent model with grounded hierarchy** — event-level search over reachable
   archive-supported subgoals.
6. **Exact-dynamics planning ceiling** — the common planner operating with simulator transitions.

On ARC confirmatory folds the frozen core is the objective-family × context factorial (systems 2 and
4, each in Markov and sequence form) with the archive baseline and exact ceiling as reference points.
Hierarchical arms (system 5) and a token model with hierarchy live in the controlled synthetic
factorial; they enter the ARC folds only behind the hierarchy gate and only if the measured
evaluation budget permits.

## Primary outcomes

The study does not rely on a single end-to-end score. It measures a chain of capabilities:

1. **Predictive-state sufficiency** — action-effect mapping recovery; hidden-state discrimination;
   counterfactual action ranking.
2. **Dynamics fidelity** — changed-cell precision, recall, and F1; irreversible-event prediction;
   exact multi-step rollout survival; direct-versus-composed prediction consistency.
3. **Planning interface** — selected-candidate regret; oracle top-k recall; reachability
   calibration; action-cost prediction.
4. **Closed-loop control** — task success; scored actions; replay-normalized goal-reaching
   efficiency; off-policy degradation; recovery success.
5. **End-to-end agency** — useful progress per action; mechanic discovery; level advancement;
   external competition score.

The principal systems endpoint is closed-loop action-efficient success. Failure localization uses
identical candidate pools and exact simulator execution.

## Launch gates

The expensive evaluation begins only after a complete vertical slice passes every gate. Thresholds
are finalized in `gate_manifest.yaml` before any sub-gate result is viewed; the execution plan holds
the operative numbers.

- **Harness gate.** Accepted submission, deterministic replay, exact transition archive, itemized
  latency table, at least 10⁵ logged transitions, reproducible manifests. Failure stops
  learned-agent work until the harness is reliable.
- **Planning-headroom gate.** The exact-dynamics planner must solve at least 60% of eligible
  development tasks and materially outperform persistence, archive replay, and simple graph
  baselines. Otherwise the task generator, sampler, horizon, or goal interface is the bottleneck —
  fix the experiment, not the models.
- **Task-validity gate.** A stratified audit must show that generated goals are reachable,
  nontrivial, free from animation artifacts, and correctly classified under the success predicate.
- **Model-competence gate.** Both exact and latent systems must produce executable checkpoints, beat
  trivial persistence on decision-relevant prediction, and exceed random counterfactual action
  ranking. The latent model is *not* required to beat the exact model; a stable latent system that is
  worse still passes, as a valid negative candidate.
- **Interface gate.** The common reachability interface must preserve meaningful differences between
  dynamics systems. It must neither solve the task almost independently of the world model nor
  collapse strong representations through an adapter bottleneck, and conclusions must survive a
  small-versus-full head-capacity repeat.
- **Off-policy gate.** Performance is measured on exploratory and recovery states before the
  confirmatory matrix. Catastrophic degradation outside successful replay trajectories triggers
  additional data collection or a narrower claim.
- **Precision and throughput gate.** The complete analysis pipeline is timed end to end. The matrix
  launches only if the expected uncertainty is scientifically usable and the evaluation fits within
  machine-time and person-time reserves.

## Why

**Personally.** The career transition targets AI/ML research engineering; the differentiated assets
are systems engineering under constraint and mathematical maturity, and this project exercises both
on the current latent-world-model line — PLDM, DINO-WM, HWM, AdaJEPA, Trajectory Reachability
Metrics. The cost is stated plainly: vLLM and infrastructure work is paused, which repositions the
portfolio toward research. A deliberate trade.

**Scientifically.** The primary question is the predictive-objective boundary. PLDM shows
reconstruction-free latent dynamics generalizing across held-out layouts in offline navigation;
ARC-AGI-3 demands a harder transfer, with new mechanics, unknown action semantics, unstated goals,
exact discrete transitions, and sparse progress feedback.

Two facts from the reference class set the positioning — and they are two facts, not a ratio, since
they come from different systems and evaluation regimes. A fixed-interface verification harness
reports about 99% RHAE on the 25 public games, self-reported, with a model postdating the
environments and no held-out evaluation; the ARC-standardized frontier model sits at 13.33% public
and 7.78% semi-private. Public saturation alongside single-digit verified semi-private is why
public-set score is a dead novelty axis. OPINE-World, an online program-induction system, solves
20/25 games and 160/183 levels while reporting a zero-score neural latent-world-model reference under
its Dreamer- and MuZero-family setup; a 0.5B explore-first agent reports 4/25. That zero is an
external failure reference to reproduce and diagnose, not a settled result for the model family: the
contribution is the controlled comparison plus failure localization among representation, dynamics,
planner-facing goal geometry, and goal acquisition. Learned-versus-written world models remain a
descriptive systems comparison, not the causal claim.

**Why this vehicle.** Hard deadlines, hidden-set evaluation, named baselines, an efficiency metric
aimed at exactly the capability under study, a small human-replay corpus of 342 plays serving as
references and policy seeds rather than pretraining data, and a paper track where a low score is
survivable — accuracy is one of six rubric criteria, not a gate. Runtime constraints reduce the value
of unconstrained inference scale and create a viable lane for compact models; they do not neutralize
scale, since milestone winners ran 27–31B local models.

## Goal hierarchy, with priors

| Outcome | Prior |
|---|---|
| Durable expertise and a public repo | 85–90% |
| A submitted paper | ~75% |
| A paper whose causal claim survives review (spine intact, replicated, matched interface) | 40–45% |
| The primary contrast resolves to something other than inconclusive | 30–40% |
| Latent beats the matched token control on the predeclared primary, given resolution | 25–35% |
| Paper award | ~10% |
| Beating on-platform template baselines on some hidden games | 15–40% |
| Leaderboard top-3 | ~1% (non-goal) |

Apply roughly a 10–15% haircut across all of these for exogenous disruption over a solo execution
window with a job search running in parallel.

## Bottlenecks, ranked

1. **Planner-facing goal geometry.** Supplied goal exemplars remove goal discovery from the primary
   task but do not by themselves make token and latent planners comparable — each arm bringing its
   own cost function is a second uncontrolled factor with published order-of-magnitude effects. The
   primary comparison fixes the reachability interface; native costs are secondary.
2. **Statistical power.** Twenty game-level units, a game-level bootstrap, and a 0.04 margin mean
   equivalence classification requires between-game SD below roughly 0.09, and a true +0.08 effect
   classifies as an advantage only about 20% of the time at SD 0.15. Hence the estimation-first
   interpretation rule, with the pre-matrix precision simulation as the gating artifact.
3. **Calendar compression of the Track-A apparatus.** The task generator, three interfaces, and
   cross-fitting are all built between early August and early September. The matrix-launch gate and
   the pre-registered fallback ladder exist to make that window survivable.
4. **Goal acquisition.** Predictive uncertainty is not task relevance; under the quadratic
   action-efficiency penalty an agent can learn more dynamics while scoring worse. Exploration is
   measured against its own baseline ladder on progress per action. The cost of decoupling it is
   registered openly: the primary tests supplied-goal, replay-derived control, not end-to-end
   instruction-free agency; the recovery stratum and the hidden-set run carry what it excludes.
5. **Development-set load.** Five games carry margins, checkpoint selection, tuning, and the
   family-selection decision. That is tolerable because the decision only configures Track B, but it
   is noisy and known to be so.
6. **Transfer validity.** Tasks are nested within games; games — not tasks or levels — are the
   transfer units. Mechanics labels guide fold stratification and near-duplicate games share a fold.
   Replay policy bias is handled by excluding a held-out game's replays from its fold and leaning
   world-model training on random and archive coverage.
7. **Exactness.** The risk is latent aliasing of action-relevant discrete detail. The factorial
   separates objective-family differences from the value of temporal context; dual-head and
   detached-auxiliary controls test multitask regularization separately; counterfactual action
   discrimination is the probe that matters, not rank.
8. **Runtime.** Architecture and search depth follow a measured end-to-end latency budget with a
   mandatory 25–30% wall-clock reserve before freezing. Platform figures live in the execution plan
   as verify-in-week-one assumptions, not established constants.

## Conditional components

**Test-time parameter adaptation.** The default adaptation is in-context mechanics inference and
exact archive updating. Gradient updates are admitted only after synthetic rule-switching, reversal,
and long-run drift tests pass with rollback safeguards, and every milestone ships a no-adaptation
control submission.

**Multiple successor predictors.** A mixture model is admitted only when the same complete predictive
state and action still produce reproducible distinct successors. It must improve successor top-k
recall or planning without material degradation on unimodal environments.

**Automatic subgoals.** Hierarchy is first tested with oracle event subgoals. Automatic subgoals are
retained only when flat planning fails for economic rather than modeling reasons, oracle
decomposition produces a substantial gain, the low-level planner can reach the oracle states, and
constrained automatic subgoals recover a meaningful fraction of that gain.

**Unrestricted latent subgoal generation.** Free optimization over arbitrary latent vectors is
outside the committed scope. High-level goals must initially be observed, archive-supported,
event-derived, or validated as reachable.

## Execution posture

The project has three priorities:

1. **A reproducible research and engineering asset**: public code, environment generators, manifests,
   evaluation harness, and documented failures.
2. **A controlled scientific result**: a boundary map for sequential inference, latent prediction, and
   grounded hierarchy.
3. **A working external submission**: a compact agent that demonstrates the architecture under
   competition constraints.

Leaderboard placement is not a scientific endpoint. A low external score does not invalidate a
controlled mechanism result, and a high public-game score does not establish hidden-environment
generalization.

## Expected outcomes

High confidence: a working submission, a reproducible harness and frozen data manifest, replicated
primary models, and a documented controlled comparison with server-verified scorecards at
milestones. Completion of test-time adaptation, automatic subgoals, or hierarchical modeling is not
assumed.

Modal scientific result: exact token prediction wins for verification and brittle discrete
mechanics, while latent prediction helps only under particular transfer, distractor, or
data-efficiency conditions — or yields no practically meaningful gain. More precisely, the most
likely result is conditional:

- sequence conditioning helps when current observations omit environment state or action semantics;
- exact prediction is strongest when one-cell differences and irreversible mechanics dominate;
- latent prediction helps when distractors, layout variation, or data scarcity make exact
  reconstruction wasteful;
- hierarchy helps only after the predictive state is adequate and flat search becomes the bottleneck;
- archive grounding and exact verification are required to prevent unreachable or discretely invalid
  plans;
- goal acquisition remains harder than supplied-goal control.

A useful result must localize the boundary rather than merely report a score. The valuable outcome is
a reproducible account of where the agent fails:

\[
\text{state inference}
\rightarrow
\text{dynamics}
\rightarrow
\text{reachability}
\rightarrow
\text{goal acquisition}
\rightarrow
\text{exploration}
\rightarrow
\text{execution}.
\]

Upside branches: latent wins the predeclared primary, a competitive result on selected games, or a
Paper Prize-quality contribution. Downside floor, stated plainly: a useful engineering report and
research diary. A defensible negative result additionally requires the frozen split, matched
controls, and primary endpoint to survive unchanged — the secondary goal, not the floor.

## One-line statement

A controlled, gate-driven study of whether history-conditioned predictive states and reachable
temporal hierarchy can provide compact, transferable control in exact interactive environments, with
explicit memory and verification preserving discrete correctness — and with the competition agent
serving as external validation rather than dictating the science.
