# ARC-AGI-3 × Learned World Models — Executive Summary

**Frozen 2026-07-23.** Companion to `arc-agi-3-execution-plan.md` and `arc-agi-3-paper-notes.md`.

## Abstract

A solo project spanning about sixteen calendar weeks — a July 20–26 design-freeze week plus fifteen
execution weeks to November 8, 2026 — using the ARC Prize 2026 ARC-AGI-3 Kaggle competition as the
vehicle for learning and evaluating JEPA-style latent world models.

The mandatory scientific core is a frozen, compute-matched comparison of two pre-specified systems
representative of the exact-token and latent-predictive objective families, crossed with Markov
versus sequence context, evaluated on mechanics-stratified held-out games with predeclared
endpoints. The registered claim is deliberately narrow: goal-conditioned planning over
replay-derived, within-level subtasks, where supplied exemplars remove goal discovery. Family-level
and benchmark-level generalization are not claimed; a preregistered synthetic mechanism suite and
secondary strata — off-policy recovery, level completion — carry the where and why questions.

A dual-head agent is retained as an engineering condition only. Model-guided exploration, test-time
adaptation, and subgoal hierarchy enter committed scope only when predeclared bottleneck tests
justify them.

The primary deliverable is durable expertise and a reproducible public codebase; the secondary is a
controlled answer to where latent prediction helps or hurts in exact, interactive, instruction-free
environments with sparse progress feedback. Agent submission November 2; paper by about November 5,
since ties favor the earliest entry. Competitive placement is not an objective.

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
two-system competence (explicitly not superiority), interface attribution, and precision plus
full-pipeline cost must all pass on development games before the matrix is authorized. Track B
adopts the development-selected family, so confirmatory folds stay sealed until scientific
unblinding and agent decisions never peek at the result. Once conclusions are frozen, the competition
model is retrained on all permitted public data; the hidden Kaggle score is ecological validation of
the end-to-end agent, not of the matched contrast.

**Conditional agent extensions (Track B).** An exact replay harness and archive baseline come first.
Exploration methods — random, state novelty, event novelty, predictive disagreement,
progress-exemplar similarity, and an oracle-progress upper bound — are compared on useful progress
per action: irreversible transitions, level-transition discovery, completion, and resulting RHAE,
never raw state coverage. Per-game test-time adaptation enters only after passing a synthetic
dynamics-shift gate with rollback safeguards and two stress tests. Oracle subgoals are evaluated only
if flat planning fails despite adequate model accuracy, and automatic subgoals only if the oracle
gain clears its threshold. A learned hierarchical level is outside committed scope. The target
architecture, SHiP-JEPA-X — sequential inference, event hierarchy, exact-archive grounding, goal
hypotheses, exact verification — describes what the agent becomes if every gate fires, not the
week-one system.

## Why

**Personally.** The career transition targets AI/ML research engineering; the differentiated assets
are systems engineering under constraint and mathematical maturity, and this project exercises both
on the current latent-world-model line — PLDM, DINO-WM, HWM, AdaJEPA, Trajectory Reachability
Metrics. The cost is stated plainly: vLLM and infrastructure work is paused, which repositions the
portfolio toward research. A deliberate trade.

**Scientifically.** The primary question is the predictive-objective boundary: under matched data,
capacity, planner interface, and interaction budgets, when does latent prediction improve transfer or
action-efficient planning relative to exact token prediction — and when does latent aliasing remove
the discrete information control requires? PLDM shows reconstruction-free latent dynamics
generalizing across held-out layouts in offline navigation; ARC-AGI-3 demands a harder transfer, with
new mechanics, unknown action semantics, unstated goals, exact discrete transitions, and sparse
progress feedback.

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

Apply roughly a 10–15% haircut across all of these for exogenous disruption over fourteen solo weeks
with a job search running in parallel.

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
5. **Development-set load.** Five games carry margins, checkpoint selection, tuning, and the G2
   decision. That is tolerable because G2 only configures Track B, but the decision is noisy and
   known to be so.
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

## Expected outcomes

High confidence: a working submission, a reproducible harness and frozen data manifest, replicated
primary models, and a documented controlled comparison with server-verified scorecards at
milestones. Completion of test-time adaptation, automatic subgoals, or hierarchical modeling is not
assumed.

Modal scientific result: exact token prediction wins for verification and brittle discrete
mechanics, while latent prediction helps only under particular transfer, distractor, or
data-efficiency conditions — or yields no practically meaningful gain. A useful result must localize
the boundary among representation, transition prediction, planner-facing goal geometry, and goal
acquisition rather than merely report a score.

Upside branches: latent wins the predeclared primary, a competitive result on selected games, or a
Paper Prize-quality contribution. Downside floor, stated plainly: a useful engineering report and
research diary. A defensible negative result additionally requires the frozen split, matched
controls, and primary endpoint to survive unchanged — the secondary goal, not the floor.

**One line:** a controlled, gate-driven study of when learned latent dynamics earn their complexity
on ARC-AGI-3, with the competition agent serving as external validation rather than dictating the
science.
