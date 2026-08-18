# Slice 4 — refinement and continuation plan

**Draft protocol revision 4, 2026-08-18.** This document prepares the next run. It
does **not** authorize model generation, create a freeze, change the operator's selected
pilot, or supersede an append-only result artifact.

The scientific question remains:

> Can the pinned local Qwen3.8-27B 8-bit MLX conversion infer a game's causal completion objective from
> autonomous observations and histories, without receiving human actions, human solved
> boards, human L1→L2 transitions, source truth, or human-derived goal feedback?

Every capability conclusion in this revision is scoped to that exact Q8 conversion and
runtime. It is not a result about the upstream BF16 checkpoint, an FP8/vLLM deployment,
other Qwen3.8 sizes, or the model family as a whole.

An L1→L2 transition earned by the autonomous agent remains admissible evidence and must
be reported as a separate `autonomous_completion_exposed` stratum. The stricter stratum
contains no observed completion at all.

## Decision summary

1. Preserve the night-2 result as two separate findings:
   `packet/page/frame binding = PASS`; `exact one-cell localization in a 28-frame,
   4px/cell, full-context storyboard = FAIL`.
2. Do not interpret that failure as a goal-inference result. No goal-inference pilot
   cell ran.
3. Keep 4px storyboards for sequence, topology, change detection, and frame binding.
   Do not claim cell-exact readout from them.
4. Do not blanket-upscale every board to 8px. Use a hybrid carrier: compact structural
   overviews, exact semantics-free delta records, existing magnified crops, and a
   separately certified precision carrier for actions that require a click.
5. Replace the universal probe verdict with arm-scoped claims. An unrelated coordinate
   diagnostic may not veto T, V, or O.
6. Add frozen, task-shaped positive controls for causal and history-sensitive goal
   inference. Readability microtasks alone do not establish construct validity.
7. Run every model-dependent eligibility check under the production sampler. A
   temperature-0 result is a wiring diagnostic, not the inferential arm bar.
8. Retain the operator's selections in the revised preregistration:
   `arms=["T","V","O","P"]`, `seeds=[2]`, and `ceiling_spec.kind="model"` with
   the already pinned same-checkpoint descriptive comparator; all other selected values
   remain unchanged.
9. Stage A remains descriptive. It cannot close the project. Closure still requires a
   genuinely untouched Stage-B inventory, which the current public game set cannot
   provide.
10. Set `KAGGLE_EVAL_BUDGET=0` for this protocol through final grading. The scientific
    run is local/offline; it may not spend a hidden-test submission to tune a carrier,
    rescue a failed control, or interpret Stage A. Deployment is a later, separately
    approved experiment with a much tighter runtime, token, and action envelope.

## What the completed probe did and did not establish

The recapture and packet lineage are healthy: 9,055/9,055 recaptured steps verify,
packets have ten matched pages, and the no-model suites and renderer self-test pass.
The final v2.2 certificate is `SEMANTIC_FAIL` only because Gate 3 combined several
claims into one universal bar.

In the sound, convention-pinned run, Qwen bound all ten queried pages under both
permutations and identified frame 23 twice. The truth was `(row=37, col=11)`; its two
coordinate answers were `(47,12)` and `(22,10)`. Mechanical decoding of the rendered
PNG confirms the truth and rules out row/column transposition, indexing, page
permutation, source-truth, and renderer errors. The traces instead contain inconsistent
invented image geometry. This is evidence for failure of the named dense 4px exact
localization profile, not for failure to understand a game's objective.

The post-hoc resolution ladder is hypothesis-generating only. It reused one coordinate,
had one observation per condition, and confounded resolution with presentation density.
It cannot support a multiplicative scale-by-tiling claim, a general 8px floor, or an
exact-coordinate claim at 16px. Gate 4 tested coarse left/right/none grounding, not
exact coordinates.

Token-accounting correction: the 28-frame 4px storyboard itself cost 2,088 visual
tokens; the full 16-image Gate-3 request cost 12,295. The night log's 7,364 value for
that condition was not the final processor-expanded call total.

The narrow defensible statement is therefore:

> The pinned model passed serving, packet binding, and event-frame identification, but
> failed exact singleton-cell localization in the tested dense 4px full-context carrier.
> Goal inference was not tested.

## Measurement model

The next run separates the construct from its nuisance channels:

| Layer | Question | Failure means |
|---|---|---|
| Serving | Were the intended bytes, order, prompt, runtime, and budgets delivered? | Instrument failure |
| Readability | Can the model recover the information that a particular arm promises? | That arm/carrier is ineligible |
| Identifiability | Does the visible evidence actually distinguish the sealed goal constraints? | Packet/sample inadequacy |
| Goal inference | Does the model infer the causal completion condition, including every required constraint? | Scoped capability failure on the tested games/interface |
| Plan execution | Can a plan based on the inferred goal complete the game? | Secondary planning/control failure |

The primary endpoint remains the final, post-interaction `best_goal`: correct in kind
and containing every sealed necessary constraint. Exact coordinates, citations,
confidence, probe quality, and plan execution remain diagnostic or secondary unless a
particular constraint genuinely is spatial.

## Carrier revision 4

### Structural channel

- Retain the clean 8px opening board and the complete 4px full-board causal pairs and
  storyboards. Their certified claim is structural and temporal, not cell-exact.
- Retain all response frames. Never silently sample an animation or fall below 4px.
- Retain clean raw evidence independently of overlays.
- Retain or enlarge the existing 16–32px/cell crops for small changed regions.

### Exact semantics-free channel

For every selected transition and live probe result, add a deterministic record derived
only from the observed arrays:

- pre, intermediate, settled, and response-frame IDs in order;
- changed-cell count and bounding box per adjacent frame pair;
- palette-transition histogram;
- exact sparse deltas as `(row, col, before, after)`; and
- a lossless compact delta mask/RLE when the sparse representation would exceed its
  frozen limit.

These records state what changed, not what any object means or what the goal is. They
must be generated inside the source-blind packet/probe boundary. Every changed cell
must be recoverable from the model-visible sparse or bbox-anchored row/flat-RLE carrier;
a full record kept only in audit metadata does not satisfy this requirement. The exact
channel replaces redundant ledger text rather than silently exceeding the tokenizer
cap.

### Precision-action channel

P must not be forced to derive an A6 click from a dense 4px atlas. Exact action grounding
must use one frozen profile that is present in the real interaction path, for example:

- a deterministic magnified frame/crop with explicit 0-based row/column rulers; or
- an overlay component ID whose exact bounding box and legal representative click are
  listed in the semantics-free ledger.

The model still chooses the object, region, and action. The carrier only translates an
observed location into the environment's coordinate API. It must not name a target,
player, objective, or preferred action. `SHOW_FRAME` should return the certified
precision view so P can spend one round obtaining precision when needed.

Packet construction must remeasure the real processor's text and visual tokens. If a
precision exhibit does not fit, reduce redundant composition or the frozen retrieval
reserve; never omit evidence after seeing a request and never exceed 16 images or 16,384
visual tokens.

## Gate v2.3: certify claims, then derive arm eligibility

| Claim | Required behavior | Arms depending on it |
|---|---|---|
| `G0_protocol_serving` | Hashes, dimensions, order, template, completion metadata, runtime identity, budgets, source blindness | T, V, O, P |
| `GT_text_exact` | Ledger/EID/TID binding, lossless grids, action records, temporal and effect/no-effect comparisons | T |
| `GV_raw_readout` | Ten-page raw binding, pre/post order, structural changes, event frame, and features shown at their actual carrier resolution | V, O, P |
| `GO_overlay_readout` | Annotation-versus-state distinction; raw/marked/pre/post/diff alignment; component-ID binding | O, P |
| `GP_interaction` | Four-turn 10→16-image chronology, retrieval/probe result binding, settled-outcome interpretation, no silent repair | P |
| `GX_precision_action:<profile>` | Legal exact A6 click using the byte-identical precision carrier used in production | P and executable-plan claims |
| `GD_dense_4px_exact` | Exact row/column in a 28-frame 4px full-context storyboard | Reported diagnostic only |

An arm is eligible only if every claim in its frozen requirement set passes. A failed
claim cannot invalidate an arm that does not consume it. If one selected arm is
ineligible, the runner must refuse the entire declared matrix; silently falling back
from T/V/O/P to a subset would change the experiment after seeing results.

`G0` is mechanical and must pass 100%. Deterministic model calls may diagnose template
or permutation wiring but cannot authorize an inferential arm. All model-dependent
readability decisions must be confirmed with the exact production sampler, reasoning
effort, prompt schema, image history, and token envelope.

The frozen Qwen3.8 thinking sampler is the checkpoint's official
`temperature=1.0`, `top_p=0.95`,
`top_k=20` configuration, with behaviorally neutral `min_p=0`,
`presence_penalty=0`, and `repetition_penalty=1` made explicit. Multi-turn calls must
retain each prior assistant turn as separate `reasoning_content` and final `content`,
and must set and trace `preserve_thinking=true`; an empty historical `<think></think>`
is a serving defect. The per-call output ceiling is 32,768. Every call must also prove
`expanded_prompt_tokens + max_tokens <= 262,144`; the worst-case cumulative text cap is
therefore 212,992 after reserving 16,384 visual tokens.

For each final model-dependent claim, use two counter-permutations over three fresh
source-blind fixtures and require 6/6 complete call-level passes. This is an operational
stability bar, not a claim of 90% reliability: six successes only reject a `p<=0.5`
configuration at `1/64 = 1.56%`. No retry, majority vote, silent repair, or ±1
conversion to an exact pass is allowed.

For `GX_precision_action`, additionally require eight fresh sealed coordinates covering
all row/column patch phases and nuisance strata, decoded mechanically from the final
PNG, with 8/8 exact. JSON coordinates must satisfy `type(value) is int`; floats that
happen to compare equal are invalid.

### Optional attribution study for the old Gate-3 failure

If causal attribution of the dense-coordinate failure is worth the compute, run a
development-only paired factorial:

- `cell_px`: 4 vs 8;
- presentation: isolated frame vs exact 28-frame storyboard; and
- context: target only vs full 16-page mixed packet.

Use eight source-blind blocks, rendering every block in all eight conditions. Across
blocks, cover all target phases modulo the final 16px and 32px processor grids, sparse
and cluttered boards, storyboard rows, outer-page positions, quadrants, edges, and
counterbalanced colours. Verify patch phase from the final rendered target bounding
box, not from board coordinates. This produces 64 paired diagnostic calls.

This adaptive discovery set may choose a precision profile but may never certify it.
Certification uses the fresh holdouts above. Because the primary experiment no longer
depends on dense 4px exact localization, this factorial is optional and must not delay
the goal-inference pilot unless an attribution claim will be published.

### Bounded pre-freeze parameter calibration

Do not grid-search temperature or top-p on real-game outcomes. Before freezing, use
fresh procedural development sentinels for eleven local calls: three active pre-probe
calls, one same-process same-seed duplicate, one different-seed call on that same
high-entropy structured prompt, and paired stripped-history versus preserved-reasoning
post-probe calls for those three fixtures. A separate condition-blind worksheet must
score goal constraints and executable plans from the six post-probe answers, then
rejoin the hidden stripped/preserved labels only after the judgments are fixed. The
calibration passes only if same-seed raw output
repeats, different seeds do not produce identical raw bytes, preserved reasoning causes
no schema/completeness regression, no call is truncated at 32,768, and preserved
history is componentwise non-worse than stripped history on goal, constraints, and
machine-replayed plan validity for all three variants. With only three pairs this is an
operational no-regression check, not a statistical non-inferiority claim. A genuinely
truncated call may be rerun once at 49,152 under this
predeclared rule; any resulting budget change loops through code, tests, packet rebuild,
and calibration. This costs zero Kaggle compute and zero competition submissions.
`agent/harness/s4_qwen_calibration.py --plan` prints the immutable no-model inventory;
`--run --model <pinned-MLX-checkpoint>` consumes the clean commit's single fixed
development attempt and creates a read-only trace/result directory. It never performs
the manual escalation itself. `--prepare-semantic`, `--finalize-semantic`, and
`--validate-semantic` then bind the keyed blind worksheet, the operator's complete
blind judgments, the condition-blind machine plan replays, and the final PASS/FAIL.
The key file must be retained read-only through freeze so the HMAC identities and
permutations can be independently regenerated.

This calibration verifies the serving choice; it does not establish that the sampler
is globally optimal. The official sampler and template-default `xhigh` effort remain
the baseline because the primary task values correctness over throughput. If a later
experiment compares `medium` with `xhigh`, or compares entropy settings, it must use a
new preregistered development/validation split of procedural fixtures, common seeds,
condition-blind scoring, and no Stage-A outcomes. Temperature 0 remains a deterministic
wiring diagnostic and cannot win an inferential arm. No parameter search in this
revision consumes Kaggle compute or a competition submission.

## Frozen goal-inference sentinels

Readability is necessary but not sufficient. Before real-game cells, run synthetic
mini-games using the actual packet formats and answer schema. They contain no public
game assets, names, source, or human histories.

### Passive controls: three counterbalanced variants

Each variant has a conjunctive causal objective and a history-sensitive condition.
It includes:

- multiple genuine successes;
- one near-miss for each individual required constraint;
- at least one pair with the same or near-identical final board but different ordered
  histories and different outcome; and
- unused actions and visually salient distractors.

The three variants preserve latent logic while permuting palette, action labels,
locations, page order, chronology position, and blind nonces. Run each through T, V,
and O under the production sampler, one answer call per variant. Each arm must infer
the complete objective in at least 2/3 variants, with no constraint credited from a
partial or merely correlated description.

### Active controls: three counterbalanced P variants

Initial evidence is deliberately consistent with two plausible goals. Exactly one of
the available legal probes distinguishes them; attractive alternatives are redundant
or non-discriminating. The pre-probe answer must preserve the ambiguity and request a
discriminating observation. After the real probe result, the model must revise to the
correct complete goal.

P must pass the final goal in at least 2/3 variants and make a valid discriminating
interaction in at least 2/3. A lucky pre-probe guess without the discriminating
interaction does not pass the interaction criterion.

### Sentinel adequacy and leakage controls

- A committed generator seed and generator hash define all fixtures before model use.
- Model-visible IDs are nonces; fixture/gold maps are sealed separately.
- Gold is derived from the generated state machine, then independently checked against
  final arrays and rendered PNGs.
- A source-blind independent reviewer must recover all sentinel goals from every
  intended carrier and attest that the evidence is sufficient. The pinned same-model
  descriptive comparator is not an independent adequacy ceiling.
- Sentinel outputs never enter the model's real-game prompt and never modify packet
  selection.
- Any sentinel failure ends that frozen protocol version. A redesign receives a new
  version, new sealed fixtures, and a new freeze; it is not a rerun.

The recommended control suite costs 15 model generations: nine passive calls
(3 variants × T/V/O) and six active calls (3 variants × pre/post). This is small enough
to be a real construct check while avoiding a second pilot-sized experiment.

## Two-stage sealing and continuation rule

The current single-certificate flow must be replaced with two append-only artifacts:

1. `FROZEN.json` binds the clean git commit; runtime; recapture and packet hashes;
   arm-requirement map; exact prompts and samplers; gate and sentinel assets/gold;
   control seeds; thresholds; stopping rules; real-game gold hashes; revised
   preregistration; and ceiling spec. It is created **before any confirmatory gate or
   sentinel answer is generated**.
2. `CONTINUE.json` may be created only once. It binds `FROZEN.json`, the complete
   confirmatory gate outputs, sentinel outputs, independent adequacy attestation, and
   their mechanical scores. It says either `CONTINUE` or `STOP`; it never rewrites the
   freeze.

The pilot runner must require an exact `CONTINUE` verdict and verify every bound hash.
If controls fail, the frozen run ends. Versioned sealed directories are required so a
failed revision remains inspectable and does not make later, explicitly new revisions
impossible.

## Kaggle evaluation and deployment budget

Three different resources must be counted separately:

| Resource | Slice-4 revision-4 budget | Accounting unit |
|---|---:|---|
| Local model work | 11 development calibration calls, gates, 15 sentinels, 64 Qwen pilot generations, four comparator generations; optional 64-call attribution study separate | Calls, generated tokens, wall/GPU hours |
| Kaggle notebook/accelerator work | Zero by default; a non-submitting hardware-profile run needs separate remote-ops approval | Kernel runs and accelerator hours |
| Kaggle competition evaluation | **0** | Kaggle-accepted hidden-test submissions |

Reading the historical `logs/kaggle_v4` observation corpus, replaying public games,
building packets, and running local gates consume zero new Kaggle evaluations. A Kaggle
kernel with `TRUE_SUBMISSION=false` also consumes zero competition evaluations, but it
does consume remote compute and belongs in the second ledger. `CONTINUE`, “run the
pilot,” or generic approval to continue never grants submission authority.

### Why the capability package cannot simply be added to the actor

Our submission-shaped `kaggle-duck` harness currently fixes a 540-minute internal
experiment cap, 132 minutes per game, and 28 concurrent jobs. The live Kaggle wall limit
has not been independently verified; the repository explicitly labels its older
approximately-eight-hour assumption unverified. The historical non-submission
`kaggle_v4` public run used 2h12m33s for 25 games, 1,779,674 total tokens, and 198,097.6
seconds of summed game wall-clock. Its mean is therefore about 132.1 game-minutes. An
idealized 110-game/28-job projection under our internal cap is:

`110 × 132.1 / 28 = 519 minutes`, before setup, tail imbalance, failures, or vision
encoding — about 96% of that nine-hour planning envelope.

This is a capacity warning, not a hidden-score forecast. The private games can have a
different runtime distribution, and Qwen3.8 VLM on Kaggle FP8/vLLM will not have the
same throughput as the local 8-bit mlx-vlm run. It nevertheless rules out treating the
four-call, up-to-32,768-output-token P protocol as additive deployment work. The local
protocol is a capability upper bound.

The only repository-confirmed platform request ceiling is 600 requests/minute. It is
not evidence for usable actor throughput: `kaggle_v4` completed 3,833 actions in 7,953
session seconds, only about 0.48 aggregate actions/second across the concurrent run.
Do not budget from the superseded approximately-10-actions/second assumption.

If Slice 4 finds useful goal inference, the follow-up deployment candidate must
**replace** existing analyzer work and action waste, not sit beside it. Its separate
preregistration should require:

- a single bounded goal-synthesis call after a mechanically defined exploration
  cutoff, with at most one uncertainty-triggered refresh;
- a frozen, much shorter output schema containing only the chosen goal constraints,
  confidence/ambiguity, and executable plan interface;
- end-to-end trace replay on all 25 public games and the submission-shaped 110-clone
  harness using the Kaggle model/runtime/image path;
- measured batching, queue delay, vision-encoder cost, peak memory, generated tokens,
  action counts, and full wall-clock rather than a per-call estimate;
- every game below the 132-minute cap and projected end-to-end evaluation time at or
  below 459 minutes, reserving 15% of the 540-minute envelope for setup and tails; and
- a debit for every active probe action. The scientific P allowance of three probes is
  not free under completion/efficiency scoring or the environment action cap.

Failure of this deployment screen means “scientifically useful but not affordable in
the current Kaggle actor,” not “goal inference failed.” The compression study may use
the successful Slice-4 traces as development data, but needs fresh controls for its
short prompt and sampler.

### Remote-compute allocation

Quota snapshot at the 2026-08-18 audit: Kaggle reports GPU `0/30 h` and TPU `0/20 h`
used, with the quota refreshing at 2026-08-22 00:00. Historical full 25-game Qwen3.6
non-submission sessions cost about 2.36–2.38 GPU hours. That does not price Qwen3.8
vision; one measured target-stack run is required before allocating a deployment study.

Recommended allocation, outside the zero-submission scientific run:

- Slice-4 gates, sentinels, pilot, comparator, and grading: 0 Kaggle GPU hours;
- optional Qwen3.8 FP8/vLLM compatibility and throughput profile:
  one `TRUE_SUBMISSION=false` kernel, capped at 3 GPU hours, only with separate
  remote-ops approval;
- only after a useful local Slice-4 result, a paired mini-S1 actor study:
  provisional 2 conditions × 3 replicas × 2.37 hours = 14.2 GPU hours, re-estimated
  after the first Qwen3.8 measurement; and
- retain at least 12.8 of the 30 weekly GPU hours for packaging failures, a required
  rerun, or the stronger unrelated score-bearing line.

The optional profile must be byte-identical to the intended deployment serving path
and may measure only compatibility, throughput, memory, and queueing. It cannot use a
leaderboard score to choose the scientific carrier.

### Competition-submission guard

The verified competition allowance is one submission per day and selection of at most
two final submissions. The two finals are selections from submitted candidates, not
extra attempts. At the 2026-08-18 audit, account history contained one accepted
submission (the 2026-07-25 random-agent V2, public score 0.06) and no submission on the
current day. Because this is mutable external state, reconcile history and quota
immediately before any future attempt. The daily limit is a ceiling, not a target. No
scored submission is part of this protocol, including after a `STOP`, a 0/4 Stage-A
result, or a successful P cell.

Any later actor-system evaluation requires a separate operator-approved submission
card naming the competition/team, candidate commit, payload/kernel/dataset hashes,
entrant-authored code provenance, hypothesis, expected information, quota before and
after, maximum accepted submissions, and a predeclared decision rule. It must already
pass the local end-to-end deployment screen. The unlicensed vendored reference payload
is not eligible to become that submission.

Maintain an append-only competition ledger:

- write `PREPARED` before the attempt;
- after the attempt, append `ACCEPTED`, `SCORED`, `REJECTED_BEFORE_ACCEPTANCE`, or
  `AMBIGUOUS`, with UTC, approver, exact command/API, all candidate hashes, Kaggle ID,
  and scores when available;
- count an accepted submission as one even if scoring later fails;
- pessimistically count an ambiguous network result as one until Kaggle history proves
  otherwise; and
- allow at most one accepted evaluation per frozen candidate, with no automatic retry,
  duplicate-hash submission, or adaptive leaderboard hill-climbing.

Reserve the two final selections prospectively: one for the strongest score-bearing
configuration and one for a method-bearing goal-inference configuration needed by the
paper path, unless one entrant-authored candidate is strongest on both criteria.

The implementation should fail closed on submission-capable commands/modes unless a
matching unspent submission card is supplied. A hidden aggregate score cannot certify
the Slice-4 carrier or goal endpoint because it also combines exploration, planning,
execution, action efficiency, runtime, and packaging.

## Implementation work packages

### A. Protocol and schemas

- Promote the design note to revision 4 and incorporate the corrected claim boundary.
- Add versioned `FROZEN`/`CONTINUE` schemas and arm-specific requirement sets.
- Preserve the selected T/V/O/P, seed 2, and descriptive model-ceiling values in a new
  preregistration revision; do not overwrite the historical file.

### B. Renderer, packet, and live probes

- Add exact temporal delta records and the precision-action carrier.
- Bind every derived fact to frame/TID/EID and observation hashes.
- Keep the packet builder unable to import or read game source, human material, sealed
  gold, or earlier model analyses.
- Recompute tokenizer, visual-token, image-count, and future-round reserves from the
  final produced assets.

### C. Gate and sentinel harness

- Split the v2.2 monolith into claim records and derive eligibility mechanically.
- Generate truth procedurally and independently decode the produced PNG; remove
  hardcoded fake-model truths.
- Use multiple coordinates and processor patch phases, strict integer schemas, moved
  targets in every permutation, and the actual 10-page/full-round contexts.
- Keep development fixtures and sealed confirmation fixtures disjoint.

### D. Runner and grader

- Require both the frozen manifest and the append-only continuation certificate.
- Enforce the full preregistered arm set; never drop a failed arm silently.
- Preserve pre-probe answers, complete transcripts, evidence hashes, and missing-output
  handling.
- Report gate/readability, packet adequacy, primary goal, and secondary plan results as
  separate layers.

### E. Regression coverage

At minimum, add tests for final-PNG truth decoding, strict integer coordinates,
permutation movement, arm-scoped eligibility, stale/mismatched continuation rejection,
one-shot continuation creation, control failure, packet-source read refusal, real token
accounting, 10→16-image interaction growth, and no-silent-repair behavior.

### F. Resource guards

- Add separate append-only ledgers for local generations, remote Kaggle compute, and
  accepted competition evaluations.
- Freeze `KAGGLE_EVAL_BUDGET=0` into this experiment and reject submission-capable
  modes from every Slice-4 command path.
- Add a deployment-budget report generator, but do not make deployment success a
  prerequisite for the scientific capability pilot.

## Exact continuation order

1. Preserve and hash the v2.2 failure artifact, both convention-pinned call traces, and
   resolution diagnostics. Mark their claims; do not relabel them PASS.
2. Approve this protocol revision and implement work packages A–F.
3. Skip the optional 64-call attribution study for this run; execute the bounded
   eleven-call sampler/reasoning calibration on development sentinels only.
4. Run all seven no-model suites, renderer self-test, probe/runner smokes, schema checks,
   and `git diff --check`.
5. Commit a clean candidate. Revalidate the existing 9,055-step recapture lineage;
   recapture again only if the replay/capture/source lineage changed. Rebuild packets
   whenever renderer, packet, ledger, selector, or probe-result carriers changed.
6. Run the one-shot development calibration on fixtures disjoint from confirmation;
   validate its mechanical PASS, prepare one HMAC-blinded semantic worksheet, obtain
   the identified operator's single-pass judgments without access to the result/key,
   finalize, and validate strict operational no-regression using the retained key. Any
   change loops back through tests, clean commit, packet rebuild, and a new candidate.
7. Generate and seal final confirmation fixtures, sentinel assets/gold, independent
   adequacy record, real-game gold hashes, and the revised preregistration.
8. Create `FROZEN.json`, requiring and binding the mechanical calibration result,
   semantic result, read-only blinding key, independent adequacy receipt,
   `KAGGLE_EVAL_BUDGET=0`, and the submission-command guard. No prompt, threshold,
   carrier, budget, fixture, sampler, or code change is allowed after this point within
   the version.
9. Run the final arm-scoped gates and frozen sentinels once. Write `CONTINUE.json` with
   `CONTINUE` only if every common/selected-arm gate, adequacy check, and sentinel
   threshold passes. Otherwise write `STOP` and end the version.
10. On `CONTINUE`, run all 16 Qwen cells (4 games × T/V/O/P × seed 2) without inspecting
    outcomes or stopping early.
11. Prepare and run the four transcript-matched P comparator cells, then freeze all
    answers.
12. Grade the primary causal-goal endpoint and secondary diagnostics. Report the
    autonomous-completion-exposed and no-completion strata separately.

At observed xhigh throughput, the pilot remains roughly 64 Qwen generations plus four
comparator generations and is plausibly a 24–40 GPU-hour run. Final gates and sentinels
add material calibration time; schedule them separately rather than compressing their
budgets or inspecting pilot cells mid-run. All of that consumes local model budget and
exactly zero Kaggle competition evaluations.

## Interpretation matrix

| Outcome | Permitted conclusion | Next move |
|---|---|---|
| Any selected gate or sentinel fails | The frozen instrument/version is inadequate or unstable | Stop; diagnose under a new version |
| T passes real goals, V/O fail | Exact autonomous evidence is sufficient, but visual representation/integration is the bottleneck | Refine carrier; do not reject goal inference generally |
| O passes, P regresses | The interaction policy or accumulating context harms inference | Inspect probe choices and context growth |
| P changes wrong→right after discriminating evidence | Positive evidence for active goal disambiguation | Characterize which evidence resolved it |
| P succeeds on any real game | The necessary role remains open | Expand characterization and acquire Stage-B holdouts |
| All four Stage-A games fail after controls pass | A scoped negative for this checkpoint, packet, interface, and four exposed games | Do not close; acquire untouched Stage-B games and an adequate independent ceiling |

Even a clean 0/4 Stage-A result cannot support the project-closing sentence “Qwen3.8 is
too weak to infer game goals.” All 25 public games have prior source/goal exposure in
the project, the pilot has one seed, and the selected comparator is the same model and
descriptive only. The strongest honest result would be that this frozen system failed
on these four games under this autonomous-evidence interface.

## Approval checklist before implementation becomes a run

- [x] Accept the hybrid carrier and the non-blocking status of `GD_dense_4px_exact`.
- [x] Accept the 6/6 arm-readability and 2/3 goal-sentinel thresholds.
- [x] Skip the optional 64-call attribution factorial for this run.
- [ ] Review the sentinel generator, independent adequacy record, sealed real-game gold,
      and familiarity/exposure records without exposing them to the model.
- [x] Confirm that T/V/O/P, seed 2, and the same-checkpoint model comparator remain the
      intended descriptive Stage-A matrix.
- [x] Confirm that no project-closure action is attached to Stage A.
- [x] Confirm `KAGGLE_EVAL_BUDGET=0`, reserve all competition submissions, and
      acknowledge that neither `FROZEN` nor `CONTINUE` grants submission authority.
