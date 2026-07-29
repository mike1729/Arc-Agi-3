# Design pivot: GI-1 goal-inference viability sprint

**Date:** 2026-07-29

**Status:** Experiment design resolved; implementation inputs frozen

**Purpose:** Decide whether structured goal inference is viable before resuming the long-run
roadmap.

## At a glance

GI-1 tests whether the reference agent can form a **correct, actionable goal belief on unseen
games**, including before it has completed a level.

The treatment has three parts:

1. restrict prediction to a measured, 10-class goal-hypothesis space;
2. present evidence in a structured form;
3. update the belief using observed completions.

No learned model carries the goal. Qwen still performs inference, but within a narrower and
better-supported task.

| Item | Decision |
|---|---|
| Development model | MoE 35B-A3B 4-bit, for prompt and pipeline debugging only |
| Measurement model | `Qwen3.6-27B-8bit` for new offline queries; recorded S1 FP8 beliefs supply the E2 baseline |
| Primary offline endpoint | Actionable predicate correctness, not coarse goal class |
| Hard offline test | Rescue baseline-incorrect `goal_unknown` cases without regressing baseline-correct cases |
| Behavioural test | Paired advisor-on/off runs on the Kaggle FP8 reference stack |
| Kill condition | Both actionable-predicate rescue (K4) and behavioural lift (K5) fail |
| Estimated duration | 4–5 offline days, plus an optional one-day/quota behavioural run |

The sprint follows this order:

> develop on the iteration games → freeze implementations → build iteration gold → run the
> 27B iteration pass → freeze the champion and retrieval specification → open the one-shot
> games once → score K1–K4 → optionally run E4/K5

---

## 1. Research question and scope

**Question:** Can the reference agent's goal belief be made correct and actionable on games it
has not seen—including with zero observed completions—by narrowing the prediction space,
compiling the available evidence, and retrieving analogous terminal transitions?

This is an offline viability sprint, followed by one optional closed-loop test. It does not
train a goal head or propose the full replacement architecture.

The parameter-gold normalization takes about one day and is built **unconditionally**. The
offline verdict depends on predicate bindings; a coarse class score cannot safely decide
whether that annotation work is worth doing.

## 2. Experimental controls

### 2.1 Model and freeze sequence

The model split follows the recorded DEV-11 evaluation, not the original S1-E5 switch.

The MoE 35B-A3B 4-bit model is a **development vehicle only**. It was rejected as a measurement
vehicle after the vc33 run produced 0/7 levels in 742 actions (`local-compute-options.md`).
Its outputs may help debug prompts, packets, and retrieval, but they may not select a treatment
or contribute a reported result.

After development:

1. freeze all condition implementations;
2. run conditions (b)–(f) once on the six iteration games, using
   `Qwen3.6-27B-8bit` for (b)–(d);
3. select the champion from that measured pass;
4. freeze the champion and retrieval specification;
5. only then open the one-shot set.

Every newly queried offline GI-1 number comes from the 8-bit model. Condition (a) is a
**targeted control, not a full-grid arm**:

- E1 reruns it only at the two gate regimes, where a matched comparison is required;
- E2 reuses the goal beliefs recorded during the original S1 runs and queries (a) only where
  that state is missing or cannot be reconstructed;
- the iteration pass and E1's descriptive checkpoints do not run it.

This preserves the comparisons that determine the verdict without paying to repeat a baseline
already measured several times. Reusing S1 outputs in E2 introduces an FP8-versus-8-bit artifact
difference; report that limitation explicitly. E4 on the exact Kaggle reference stack remains
the model-matched behavioural test.

The local 8-bit model runs at about 8.3 tokens/s and is not the same artifact lineage as the
reference FP8 model. A 20-call pilot determines whether the grid fits local throughput. If it
does not fit within three overnights, the one-shot pass moves to the Kaggle FP8 notebook. E4
uses the exact Kaggle reference stack and therefore bounds any remaining model-substitution
risk.

### 2.2 Game ledger

| State | Games | Permitted use |
|---|---:|---|
| Iteration | 6 | Prompt, digest, scorer, and retrieval development |
| One-shot | 15 | One frozen E1/E2/E3 pass; no later iteration |
| Reserved | 4 | Untouched by all GI-1 work, including E4; absent from every retrieval index |

Once a one-shot game is read, it is considered tainted for later prompt or system design. The
ledger records the date and the exposed material. E2 excludes reserved-game episodes, reducing
its corpus from 75 to 63 episodes. The preview-build game lp85 remains included but is flagged.

### 2.3 Common evidence packet

All conditions receive data derived only from the session prefix available at the checkpoint.
The representation has three layers.

#### Layer 1: canonical packet

The condition-independent packet contains:

- the initial settled board;
- settled-frame deltas within the level;
- actions taken and `available_actions`;
- for each observed completion:
  - the pre-terminal settled grid,
  - the completing action,
  - the within-level deltas leading to it,
  - the `levels_completed` increment.

The post-terminal frame is excluded because it is the next level's board, not a solved-state
image.

A zero-completion packet therefore contains the initial board and early deltas, with no
terminal evidence.

#### Layer 2: baseline rendering

Conditions (a) and (b) receive the same rendering: current grid at upscale 4 plus the reference
harness's native history format, reproduced as closely as offline replay permits. Their only
difference is the requested output structure.

#### Layer 3: compiled digest

Conditions (c) and (d) additionally receive object and count inventories, delta summaries, and
terminal-packet abstracts.

The digest may contain **no new information** beyond the canonical packet. It changes
representation and computation, not evidence. At checkpoints where both conditions run:

- (b) − (a) isolates output structure;
- (c) − (b) isolates the evidence compiler.

### 2.4 Retrieval

Conditions (d) and (f) use:

- earlier terminal packets from the same session; and
- terminal packets from other games.

They never use another human session from the current game, which would leak the answer.
At zero completions, retrieval is therefore cross-game only, matching the deployment setting.

Before the one-shot set is opened, freeze:

- features;
- distance metric;
- neighbour count;
- tie-breaking;
- index membership.

The cross-game pool is leave-one-game-out over the 21 non-reserved games. This is a declared
transductive design: a shipped library may contain public games, while a hidden target game is
absent from it. Reserved games appear in no index.

Before any E4 payload becomes a submission, resolve whether a replay-derived retrieval library
is compatible with the replay licence.

## 3. Experimental conditions

| ID | Inference | Output | Digest | Retrieval |
|---|---|---|---:|---:|
| (a) | Qwen | Free-form S1 status quo; targeted matched control and reused S1 records | No | No |
| (b) | Qwen | Hypothesis set over the 10-class codebook | No | No |
| (c) | Qwen | Hypothesis set | Yes | No |
| (d) | Qwen | Hypothesis set | Yes | Yes |
| (e) | None | Leave-one-game-out class prior | No | No |
| (f) | None | Prior plus nearest-terminal class vote | No | Yes |

The planned contrasts are:

| Contrast | What it estimates |
|---|---|
| (b) − (a) | Benefit of constrained output at the two E1 gate regimes |
| (c) − (b) | Benefit of the evidence compiler |
| (d) − (c) | Retrieval benefit for Qwen |
| (f) − (e) | Retrieval benefit without Qwen |
| (d) − (f) | Qwen's incremental value over the strongest programmatic floor |

Conditions (b)–(d) return a **top-three hypothesis set**. Each hypothesis contains:

- goal class, from the closed ten-class codebook;
- a **typed `predicate` object**, whose fields are fixed per class by
  `agent/harness/gi1_predicate_schema.py::PREDICATE_FIELDS` — enum, integer, entity and
  entity-list fields, with conditional fields declared in `CONDITIONAL_FIELDS`. **Not a free-text
  parameter sketch**, which this document specified until 2026-07-29: prose cannot be compared
  field-wise, so it would put open-ended rating back into K4, the primary verdict. The schema is
  the single contract shared by the prompt's field guide, the gold annotation, the output parser
  and the K4 scorer — all four are generated from or checked against that one table, and it is
  what freezes with the digest before the iteration pass;
- evidence for and against;
- the cheapest action expected to distinguish the top two hypotheses.

The design avoids forced early commitment because S1 observed confidently wrong goals being
preserved. Proposed discriminating probes are logged and reviewed, but not gated in GI-1;
testing their causal value requires a fork and belongs in a later sprint.

## 4. Scoring

### 4.1 Primary principle

**Goal class is a diagnostic filter. Actionable predicates are the verdict.**

A correct class with incorrect object or parameter bindings reproduces the sc25 failure and is
not a success.

Every condition's raw output is logged once. Annotation and scoring operate on those logs and
never trigger a second model query.

### 4.2 Goal class

Top-one and top-three class accuracy are scored mechanically against the per-game primary labels
(κ = 0.947). Class accuracy is necessary to interpret the pipeline, but neither sufficient for
viability nor a kill criterion by itself.

### 4.3 Actionable predicate

The normalized gold layer describes the actual terminal predicate and its bindings.

- Build iteration-game gold before champion selection.
- Build one-shot-game gold only after implementation freezes.
- Never annotate reserved games during GI-1.
- Score conditions (b)–(d) mechanically, field by field, against the normalized gold.
- Map condition (a)'s free text with blinded raters.
- Use raters otherwise only for a frozen, enumerated list of semantic-equivalence cases that
  the mechanical scorer cannot resolve. Log every invocation.

The iteration layer is implemented in `logs/gi1_predicate_gold_iteration.json`: six typed
predicate templates, each pinned to the packet-verified S2 annotation, the sole
`self.next_level()` line, and the SHA-256 of that game's source. Validate it with
`agent/harness/gi1_predicate_gold.py --verify`. Its status is `frozen` under the declared
implementation freeze; it contains no reserved or one-shot game. Full provenance
verification requires the ignored competition source bundle and
`logs/s2_goal_predicates_labelled.json`; a checkout missing either now receives an explicit
problem list instead of a traceback. The publishable gold intentionally excludes `guard_tests`:
those strings copied competition source verbatim, while source path, function, transition line,
and SHA-256 already pin the evidence without redistributing it.

Structured outputs are parsed by `agent/harness/gi1_output_parser.py`: duplicate keys, repaired
Markdown, non-finite numbers, contract drift, malformed ranks, and schema-invalid predicates are
all parse failures. `agent/harness/gi1_k4_scorer.py` compares enum, integer, entity, and ordered
entity-list fields mechanically through the shared schema and reports top-one/top-three class and
predicate outcomes plus every field decision. It also exposes top-one and best-top-three
`fields_correct`, `fields_total`, and field accuracy as headline outputs: exact free-text equality
is too conservative to be the only treatment-sensitive predicate read. A parse failure records
zero correct fields with the gold field count retained, not a dropped row. Exact
`predicate_correct` remains the all-fields bar and is never inferred from partial credit. Semantic
equivalences remain empty and unimplemented rather than being guessed by the scorer.

The primary offline verdict therefore does not depend on open-ended S1-E10-style rating.

### 4.4 Shared discipline

In E1, packets, checkpoints, model, sampling, and scoring remain identical across compared
conditions except for the declared treatment. E2 deliberately uses the recorded S1 goal belief
as its baseline; results must label the resulting FP8-versus-8-bit artifact difference. Labels
are scoring inputs only, never runtime inputs. Every result must also state that public-game
performance is not hidden-game performance (13.33% vs 7.78%).

## 5. Experiments

The four experiments answer different questions:

| Experiment | Main uncertainty |
|---|---|
| E1 | Can the goal be recognized from controlled human evidence, and which treatment helps? |
| E2 | Does the treatment still work on the agent's own incomplete and biased trajectories? |
| E3 | Does observed completion evidence cause useful adaptation, and what part of it matters? |
| E4 | Does a better goal belief improve actions and completed levels in closed-loop play? |

### E1: recognition ladder on human evidence

For each non-reserved game, use three completion-bearing human sessions. Evaluate conditions
(b)–(f) at:

- 10 actions with zero completions;
- 30 actions with zero completions;
- immediately after the first completion;
- immediately after the second completion;
- immediately after the third completion.

Run condition (a) only at 30 actions with zero completions and immediately after the first
completion. These are the two K1 gate regimes and the only E1 checkpoints where a matched
free-form control changes a decision. Condition (a) is not champion-eligible, and rerunning it
at 10 actions or after completions two and three would add descriptive cost without affecting a
gate.

The two zero-completion rows represent S1's stuck-on-level-1 regime. They are reported
separately and never averaged into completion-bearing results.

E1 asks:

- Is the goal recoverable at all?
- How much evidence is required?
- Which treatment provides the lift?

**What this discovers:** E1 is the clean recognition test. Human replays provide successful
trajectories at known evidence checkpoints, so failure cannot be blamed solely on the agent's
poor exploration. The zero-completion checkpoints test whether narrowing, compilation, or
cross-game retrieval can help before the agent has ever succeeded. The later checkpoints show
how quickly the correct goal becomes identifiable after one or more examples. Comparisons
between conditions attribute any improvement to output structure, the evidence compiler,
retrieval, or Qwen itself.

### E2: recognition from the agent's own evidence

Replay evidence streams from the S1 failure corpus and evaluate the frozen champion and (f) at:

- 10 actions into the stalled level attempt;
- 30 actions into the stalled level attempt;
- the episode's final state.

The non-reserved corpus contains **63 episodes**, including **39 `goal_unknown` primaries across
18 games**.

For condition (a), extract the goal belief recorded by the original agent at or immediately
before each checkpoint. Map that text to normalized predicate gold with the same blinded
procedure used elsewhere. Query the 8-bit baseline only when the historical goal state is
missing or cannot be scored. The `goal_unknown` failure label cannot substitute for this
concrete predicate: it selects the difficult corpus but does not establish what goal the
baseline predicted.

Report `goal_unknown` and its complement separately. Because `goal_unknown` episodes were
selected for the baseline agent not knowing the goal, condition (a) is near floor there by
construction. The primary E2 read is therefore paired rescue under K4, not the champion's
absolute accuracy.

**What this discovers:** E2 tests whether the E1 result survives the evidence the deployed
agent actually produces. Those trajectories may be repetitive, incomplete, or focused on the
wrong objects; a method that works only on clean human demonstrations would not solve the S1
failure. E2 therefore asks whether the champion can recover concrete, actionable predicates in
episodes where the original agent's goal belief was wrong, while preserving cases it already
understood. It is the main bridge between offline recognition and the observed
`goal_unknown` failure population.

### E3: adaptation and completion ablation

E3 reuses E1's grid rather than creating another corpus.

It has two reads:

1. **Ladder slope:** marginal lift from 0 → 1 → 2 → 3 completions.
2. **Completion-content ablation:** remove the pre-terminal grid, completing action, and
   preceding deltas while leaving the `levels_completed` increment visible.

The completion count is free platform metadata in every deployment regime. Hiding it would test
a state that does not occur in deployment.

Run conditions (d) and (f) to determine whether Qwen is required for adaptation or whether a
programmatic posterior can carry it.

**What this discovers:** E3 tests the mechanism behind improvement rather than only its final
accuracy. A positive ladder slope would show that the system updates its belief as successful
examples accumulate. The content ablation separates information in the terminal transition
from the bare fact that a level was completed. Comparing (d) with (f) then shows whether that
updating requires semantic inference from Qwen or can be carried by retrieval and a
programmatic posterior.

### E4: paired behavioural test

E4 is unlocked by K1, not blocked by a failed K4.

Run advisor-on/off pairs on the Kaggle reference stack for the 21 non-reserved games. Inject the
goal-hypothesis digest where the solver currently creates a free-form goal. Keep all four
reserved games untouched.

Use three replicates per arm, costing about 14.2 hours. The primary outcome is per-game level
completions. Interpret it against the observed run-to-run noise: identical runs changed cleared
level count on 20–36% of games.

The E4 payload is the natural first method-bearing submission.

**What this discovers:** E4 tests whether an improved offline goal description changes the
agent's decisions enough to matter. A predicate can score as correct yet arrive too late, be
ignored by the solver, or fail to identify a useful next action. Paired advisor-on/off runs
measure the complete causal chain—from goal inference, through action selection, to completed
levels—while the replicate and game-level pairing separate the treatment signal from the
reference agent's substantial run-to-run noise.

## 6. Selection and decision rules

### 6.1 Champion selection

Only conditions (b)–(d) are champion-eligible. Conditions (e) and (f) are attribution floors:
they emit class votes rather than bindable predicates and cannot be scored on K4.

Select the champion on the six iteration games from the measured 27B-8bit pass:

1. highest mean top-one field accuracy;
2. exact top-one predicate correctness;
3. class top-three accuracy as the final tie-break.

Freeze the champion before opening the one-shot set.

The confirmatory one-shot contrasts are:

- champion vs (a) at the two shared E1 gate regimes and against the recorded S1 baseline in E2;
- champion vs (e);
- (d) vs (f).

All other one-shot comparisons are descriptive and carry no confidence-interval claim.

### 6.2 Gates

| Gate | Role | Pass or routing rule |
|---|---|---|
| **K1: class recovery** | Diagnostic and non-inferiority guard | At both 30-action and first-completion regimes: champion top-three point regression vs (a) ≤ 3 pp and one-sided 90% lower bound > −5 pp |
| **K2: attribution** | Route work between Qwen and programmatic inference | Compare (d) with (f); never kills the project |
| **K3: adaptation** | Test whether completion evidence improves inference | Positive per-completion marginal lift, with ladder and content ablation agreeing in sign |
| **K4: actionable rescue** | Primary offline viability verdict | Rescue at least 25% of baseline-incorrect `goal_unknown` episode-levels, with game-clustered paired improvement above zero and no material regression on baseline-correct cases |
| **K5: behaviour** | Closed-loop verdict and possible K4 rescue | Positive paired improvement on the 21-game E4 test under the rule below |

#### K1 details

Compute the mean session outcome within each game, then bootstrap games with 10,000 draws.
Report 90% intervals separately for:

- the 30-action zero-completion regime;
- the first-completion regime.

K1 does not demand class superiority. A treatment may leave a saturated class score unchanged
while fixing bindings.

The early kill requires failure on **both** axes: no class lift over the floors and no positive
actionable-predicate signal over (a), in either regime. Failure only at zero completions, with a
positive predicate signal after one or more completions, routes to probe design rather than
killing the project.

#### K2 details

If (f) wins on class, the supported conclusion is narrow: **class identification does not need
Qwen**. It does not show that retrieval can bind objects or parameters in the current game.

That result routes to a programmatic classifier with Qwen used only for bindings. The named
follow-up is to extend (f) with transferred predicate templates and a deterministic binding
procedure.

#### K4 details

Use only `goal_unknown` episode-levels where the scored baseline predicate from condition (a)
is wrong. In E2 this is normally the recorded S1 belief, not a rerun and never the
`goal_unknown` category label itself.

Pass requires:

- the champion's actionable top-one predicate is correct on at least 25% of those cases;
- episode outcomes are aggregated within game before inference;
- the game-clustered 90% lower bound for paired champion − (a) improvement is above zero;
- on baseline-correct cases, point regression is no more than 3 pp and the one-sided 90% lower
  bound is above −5 pp.

This pairing prevents three false positives: taking credit for answers the baseline already
had, concentrating gains in repeated episodes from one game, and reporting a positive absolute
rate without incremental value.

#### K5 details

Average the three paired-replicate deltas within each game, then run a one-sided sign-flip
permutation test over the 21 game-level deltas.

Pass requires:

- p < 0.10;
- pooled mean level-completion delta > 0;
- at least two of the three replicate-pair means are nonnegative.

Requiring all three replicate means to be nonnegative would be too brittle at the observed
20–36% run noise.

A failed K4 does not automatically block E4: K5 can rescue an offline scorer that is pessimistic
about behavioural value. Whether to spend the 14.2 hours after a K4 failure remains an operator
decision. Failure of both K4 and K5 kills the approach.

The gate verdict is generated from logs by a verification script, following
`s1d_rollup.py --verify`.

## 7. Frozen execution values

### 7.1 Game draw

The draw uses `agent/harness/gi1_game_draw.py`, seed 20260729. The first stratified attempt was
accepted without redrawing. It is recorded in `logs/gi1_game_draw.json` and passes `--verify`.

Constraints:

- stratify by primary predicate class;
- keep lp85 out of iteration and reserved sets;
- include both action regimes in the iteration set.

| Bucket | Games |
|---|---|
| Iteration (6) | dc22 · ft09 · ls20 · m0r0 · tu93 · vc33 |
| Reserved (4) | g50t · r11l · su15 · tr87 |
| One-shot (15) | ar25 · bp35 · cd82 · cn04 · ka59 · lf52 · lp85 · re86 · s5i5 · sb26 · sc25 · sk48 · sp80 · tn36 · wa30 |

The two most-inspected games, vc33 and tu93, landed in the iteration set, where their previous
exposure is harmless. sc25, the motivating §9 failure, landed in the one-shot set and remains
confirmatory.

One caveat: reserved game g50t lacks two human sessions, so later external validation will
depend more heavily on fresh play.

The draw script, artifact, packet builder, inventory, and this note were committed as `c0fd2e3`
on 2026-07-29.

### 7.2 Sampling, checkpoints, and inference

| Parameter | Frozen value | Rationale |
|---|---|---|
| Sessions per game | 3 | Matches the three-replicate posture and retains session-variance information |
| Session selection | Most completions; ties by fewer actions, then GUID | Deterministic selection |
| Zero-completion checkpoints | 10 and 30 actions | 10 is early evidence; 30 is just below the human per-level p25 of 32 |
| Gate regimes | 30 actions and first completion | Keeps zero- and completion-bearing evidence separate |
| Ladder-only checkpoints | Second and third completion | Used by E3, not the main gate |
| Within-game aggregation | Mean session 0/1 outcome for each game and regime | Prevents games with more rows from dominating |
| Inference | Game-level bootstrap, 10,000 draws | Resamples the independent unit |
| Interval | 90%, two-sided unless a gate specifies one-sided | Appropriate for a viability screen over 15 one-shot games |

A zero-completion checkpoint is valid only if the session has not completed a level before that
action offset. Invalid rows are dropped and counted.

### 7.3 Measured packet inventory

`agent/harness/gi1_packets.py --inventory` produced
`logs/gi1_packet_inventory.json`; self-tests pass on ls20, vc33, and m0r0.

- All 21 non-reserved games provide three sessions with at least three completions.
- 275 of 315 checkpoints are valid.
- All 40 invalid checkpoints are zero-completion offsets from fast sessions.
- vc33 and lp85 have first completions at steps 6–10, so neither contributes a valid
  zero-completion row.
- vc33 is an iteration game; the other five iteration games still supply zero-completion
  development evidence.
- cn04 contains one or two empty-`frame` lines per session, always at `GAME_OVER`; those rows
  retain the previous settled grid and record `n_frames=0`.

### 7.4 Runtime and annotation budget

Estimated measured workload: about **1,413 8-bit calls**, plus fallback baseline calls for any
E2 checkpoint whose recorded S1 goal belief is missing or unscorable.

| Component | Calculation | Calls |
|---|---:|---:|
| Iteration E1 | 6 games × 3 sessions × 5 checkpoints × 3 Qwen conditions, excluding (a) | 270 |
| One-shot E1, conditions (b)–(d) | 15 × 3 × 5 × 3 | 675 |
| One-shot E1, targeted condition (a) | 15 × 3 × 2 gate checkpoints | 90 |
| E2 champion | 63 episodes × 3 checkpoints | 189 |
| E3 ablation | 21 × 3 × 3 | 189 |

Programmatic floors and extraction of existing S1 baseline states are effectively free. Any
necessary E2 baseline fallback query is counted separately and reported.

Annotation is budgeted separately from model measurement:

- gold generation uses source annotation, not 8-bit calls;
- at most approximately 279 blinded mappings of condition (a):
  - E1 one-shot targeted control: 90,
  - E2 recorded S1 beliefs: up to 189;
- enumerated-equivalence adjudications are additional and fully logged.

Before the iteration pass, run a 20-call pilot at achievable concurrency. The local grid must
fit within three overnights; otherwise move the one-shot pass to the Kaggle FP8 notebook.

### 7.5 Runner and implementation freeze

`agent/harness/gi1_experiment_runner.py` owns deterministic checkpoint scheduling, execution of
conditions (b)–(f), append-only raw JSONL logging, resume by stable row ID, and exclusion of
invalid or completion-ablation-contaminated rows before prompt rendering. `moe-debug` accepts
only the 35B-A3B development artifact and iteration games; `measured-iteration` accepts only
the 27B-8bit artifact, fixes conditions to (b)–(f), and requires the freeze manifest.

The replay-derived retrieval index is cached in `logs/gi1_retrieval_index.json` so a resume does
not rescan the corpus. Its library membership, selected sessions, full retrieval `SPEC`, record
shape, and SHA-256 are verified. `logs/gi1_implementation_freeze.json` pins that cache plus the
prompt, digest, retrieval, shared predicate schema, strict parser, scorer, sampling map, and
model artifact basenames. `agent/harness/gi1_freeze.py --verify` must pass before every measured
run. Raw API requests and responses remain in ignored JSONL logs; every scored output is derived
from those logs without re-querying.

---

## 8. Candidate GI-2: action semantics

GI-2 remains intentionally undesigned until GI-1's gate is read.

Its candidate target is `action_semantics_unknown` (20% primary; 49% episode share). The
proposed intervention is a per-game action-effect catalogue built online from programmatic
delta summaries for each `(action, context)` pair and injected into the prompt.

This requires no cross-game training data: it accumulates within the current game, so the
17-domain cap does not bind. The likely evaluation shape is the same as GI-1—offline replay of
S1 episodes with and without the catalogue, followed by paired runs. Discriminating probes
logged by GI-1 conditions (b)–(d) would inform the final GI-2 design.
