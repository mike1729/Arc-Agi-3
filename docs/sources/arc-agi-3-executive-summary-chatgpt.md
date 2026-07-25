# ARC-AGI-3 × Sequential–Hierarchical Predictive World Models

## Executive Summary

### Abstract

This project studies whether a compact, history-conditioned world model can infer the mechanics of an unfamiliar interactive environment and use a grounded temporal hierarchy to act efficiently over long horizons.

The target system combines four capabilities:

1. **Sequential predictive-state inference** from recent and retrieved observation–action transitions.
2. **Short-horizon exact or latent dynamics prediction** for local counterfactual planning.
3. **Reachability-constrained hierarchical planning** over observed or validated event states.
4. **Exact episodic memory and verification** to preserve discrete correctness and prevent unsupported latent plans.

The scientific objective is not to show that latent prediction is universally superior to exact prediction. It is to identify the conditions under which abstraction and temporal hierarchy earn their complexity, and to localize failures among state inference, transition prediction, subgoal reachability, goal acquisition, and exploration.

A procedurally generated boundary suite provides controlled mechanism evidence with many independent environments. Held-out public ARC-AGI-3 games provide ecological evaluation under exact, sparse, instruction-free mechanics. The competition submission is an external systems test rather than the source of the causal claim.

---

## Research question

Under matched data, model capacity, interaction budgets, and planning budgets:

> When do history-conditioned latent dynamics and grounded temporal hierarchy improve action-efficient control relative to exact-state predictive models, and when do discrete aliasing, unreachable subgoals, or goal uncertainty eliminate the benefit?

The project separates three questions that are often conflated:

- **Can the agent infer a sufficient predictive state from interaction history?**
- **Can the world model predict action consequences accurately enough for planning?**
- **Can temporal hierarchy reduce search cost without proposing impossible intermediate states?**

Goal acquisition and exploration are evaluated separately and then recombined in the end-to-end agent.

---

## Target architecture

The target agent is **SHiP-JEPA-X: Sequential–Hierarchical Predictive JEPA with exact-state support**.

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
- closed-loop verification after every action or short action chunk.

EMA target encoding and stop-gradient are the default latent-learning stabilizers. Batch-statistic regularizers are diagnostics only. Multiple successor predictors are admitted only after residual multimodality remains after observation completeness, context length, and encoder fidelity have been checked.

---

## Evidence design

### Controlled mechanism study

A synthetic boundary suite generates many independent environments while varying one or a small number of factors:

- visible versus partially observable state;
- fixed versus environment-specific action semantics;
- smooth versus exact irreversible transitions;
- broad versus one-cell-critical state relevance;
- direct versus non-greedy prerequisite goals;
- unimodal versus genuinely aliased successors;
- short versus compositional horizons;
- familiar versus held-out combinations of mechanics.

The primary factorial fixes sequence conditioning and varies:

| Factor | Condition 1 | Condition 2 |
|---|---|---|
| Predictive target | Exact state or exact delta | Reconstruction-free latent state |
| Planning scale | Flat short-horizon planning | Grounded event hierarchy |

A compact reconstructive model provides a mechanistic control between exact and reconstruction-free prediction. An exact-simulator planner supplies the planning ceiling.

This suite is the main source of claims about why a method succeeds or fails.

### ARC-AGI-3 ecological study

Public games are divided into development and held-out training folds. The ARC study evaluates:

- replay-path goal reaching;
- off-trajectory branches;
- recovery after plausible wrong actions;
- irreversible-event prediction;
- counterfactual action ranking;
- cross-level rule use;
- full-agent useful progress per action.

Games are the transfer units. Generated tasks, levels, and replay segments are nested observations rather than independent samples.

The ARC results are interpreted as performance over a finite public benchmark set. They are not treated as proof of generalization to all interactive environments or unseen mechanic families.

---

## Mandatory comparisons

The minimum system set is:

1. **Exact archive and graph baseline**  
   Deterministic transition memory, frontier exploration, event graph, and replay.

2. **Sequential exact predictive model**  
   History-conditioned exact-grid or exact-delta prediction with flat planning.

3. **Sequential compact reconstructive model**  
   Learned compact state with a lightweight exact next-state decoder.

4. **Sequential latent predictive model**  
   Reconstruction-free latent dynamics with exact control-critical auxiliaries.

5. **Sequential latent model with grounded hierarchy**  
   Event-level search over reachable archive-supported subgoals.

6. **Exact-dynamics planning ceiling**  
   The common planner operating with simulator transitions.

A token model with hierarchy is included in the controlled synthetic factorial. On ARC games it is added when the full evaluation budget remains feasible.

---

## Primary outcomes

The study does not rely on a single end-to-end score. It measures a chain of capabilities:

1. **Predictive-state sufficiency**
   - action-effect mapping recovery;
   - hidden-state discrimination;
   - counterfactual action ranking.

2. **Dynamics fidelity**
   - changed-cell precision, recall, and F1;
   - irreversible-event prediction;
   - exact multi-step rollout survival;
   - direct-versus-composed prediction consistency.

3. **Planning interface**
   - selected-candidate regret;
   - oracle top-k recall;
   - reachability calibration;
   - action-cost prediction.

4. **Closed-loop control**
   - task success;
   - scored actions;
   - replay-normalized goal-reaching efficiency;
   - off-policy degradation;
   - recovery success.

5. **End-to-end agency**
   - useful progress per action;
   - mechanic discovery;
   - level advancement;
   - external competition score.

The principal systems endpoint is closed-loop action-efficient success. Failure localization uses identical candidate pools and exact simulator execution.

---

## Launch gates

The expensive evaluation begins only after a complete vertical slice passes the following gates.

### Planning-headroom gate

The exact-dynamics planner must solve at least 60% of eligible development tasks and materially outperform persistence, archive replay, and simple graph baselines. Otherwise the task generator, sampler, horizon, or goal interface is the bottleneck.

### Task-validity gate

A stratified audit must show that generated goals are reachable, nontrivial, free from animation artifacts, and correctly classified under the success predicate.

### Model-competence gate

Both exact and latent systems must produce executable checkpoints, beat trivial persistence on decision-relevant prediction, and exceed random counterfactual action ranking. The latent model is not required to beat the exact model.

### Interface gate

The common reachability interface must preserve meaningful differences between dynamics systems. It must not solve the task almost independently of the world model or collapse strong representations through an adapter bottleneck.

### Off-policy gate

Performance is measured on exploratory and recovery states before the confirmatory matrix. Catastrophic degradation outside successful replay trajectories triggers additional data collection or a narrower claim.

### Precision and throughput gate

The complete analysis pipeline is timed end to end. The matrix launches only if the expected uncertainty is scientifically usable and the evaluation fits within machine-time and person-time reserves.

---

## Conditional components

### Test-time parameter adaptation

The default adaptation is in-context mechanics inference and exact archive updating. Gradient updates are admitted only after synthetic rule-switching, reversal, and long-run drift tests pass with rollback safeguards.

### Multiple successor predictors

A mixture model is admitted only when the same complete predictive state and action still produce reproducible distinct successors. It must improve successor top-k recall or planning without material degradation on unimodal environments.

### Automatic subgoals

Hierarchy is first tested with oracle event subgoals. Automatic subgoals are retained only when:

- flat planning fails for economic rather than modeling reasons;
- oracle decomposition produces a substantial gain;
- the low-level planner can reach the oracle states;
- constrained automatic subgoals recover a meaningful fraction of that gain.

### Unrestricted latent subgoal generation

Free optimization over arbitrary latent vectors is outside the committed scope. High-level goals must initially be observed, archive-supported, event-derived, or validated as reachable.

---

## Execution posture

The project has three priorities:

1. **A reproducible research and engineering asset**: public code, environment generators, manifests, evaluation harness, and documented failures.
2. **A controlled scientific result**: a boundary map for sequential inference, latent prediction, and grounded hierarchy.
3. **A working external submission**: a compact agent that demonstrates the architecture under competition constraints.

Leaderboard placement is not a scientific endpoint. A low external score does not invalidate a controlled mechanism result, and a high public-game score does not establish hidden-environment generalization.

---

## Expected outcomes

The most likely result is conditional:

- sequence conditioning helps when current observations omit environment state or action semantics;
- exact prediction is strongest when one-cell differences and irreversible mechanics dominate;
- latent prediction helps when distractors, layout variation, or data scarcity make exact reconstruction wasteful;
- hierarchy helps only after the predictive state is adequate and flat search becomes the bottleneck;
- archive grounding and exact verification are required to prevent unreachable or discretely invalid plans;
- goal acquisition remains harder than supplied-goal control.

The valuable outcome is not simply which model scores highest. It is a reproducible account of where the agent fails:

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

---

## One-line statement

A controlled study of whether history-conditioned predictive states and reachable temporal hierarchy can provide compact, transferable control in exact interactive environments, with explicit memory and verification preserving discrete correctness.
