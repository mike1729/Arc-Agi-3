# S1 Measurements

**Status:** S1-b in progress, 2026-07-26. Field-availability table filled from the vendored source and
the first local run; latency, hardware fit, reliability and the reset experiment are S1-c (Day 3).

## What the reference actually emits — established 2026-07-26

Per-action event stream, `logs/runs/<run>/artifacts/<game>_p<pass>_events.jsonl`, one row per step:

| Field | Note |
|---|---|
| `board` | **full 64×64 grid, not a hash** — satisfies §4.2.1's explicit requirement |
| `board_ascii` | compact symbolic view the agent is actually shown |
| `action_num`, `action_display` | the executed action |
| `analysis_step` | which reasoning turn produced it |
| `level`, `score`, `reward`, `run_status`, `state` | progress markers |

Plus `taaf.game.GameRun`: `history: list[ActionRecord]` (`action`, `generated_tokens`,
`uncached_input_tokens`, `wallclock_seconds`), `intermediate_states`, **`actions_per_level`** and
**`base_actions_per_level`** (real per-level counts and the human baseline — *measured*, not estimated,
unlike AERA), `levels_completed`, `final_score`, `solver_note`, `state ∈ {won, gave_up, cancelled,
crashed}`. Also `transcripts/<game>_p<pass>.txt` and `prompts/prompt.log`.

**`save_request_logs` (D6) is the load-bearing instrumentation flag.** Set true it writes
`requests.jsonl` carrying the full `messages` array, `tools`, `tool_choice`, `finish_reason`,
`analysis_step`, `action` and `request_index_within_turn` — i.e. the `prompt_context_snapshot` and
`raw_model_output` several categories are defined on.

> ⚠ **CORRECTED 2026-07-26.** An earlier version of this note said D6 was "enabled in
> `build_local.sh`" via the config file. **It was not, and the first two ft09 runs produced no
> `requests.jsonl` at all.** `analyzer.save_request_logs` in the JSON config is never read;
> `inference/framework/run.py` sources it from the **CLI flag `--save-request-logs`**, which is an
> `argparse.BooleanOptionalAction` defaulting to `False`.

**Generalised caution — the JSON config is not a complete control surface.** This is now the *second*
setting found to be inert in the config file, after `analyzer.tool_steps` (which is read from the
`LOCAL_ANALYZER_TOOL_STEPS` environment variable and otherwise defaults to 12 in code). Both look
configured and neither is. **Before relying on any config field, verify it reaches the running object** —
either from the `HarnessSolver(...)` repr the runner prints at startup, or by importing the module and
reading the constant. Assuming the config is authoritative would silently produce runs that are not the
configuration we believe we pre-registered, which is precisely the failure the manifest exists to catch.

**The model's reasoning is exposed.** The MLX server returns `reasoning_content` separately from
`content` (591 and 665 chars in the two D5 probes), so `reasoning_text` is available verbatim.

## Field availability — fill Day 2 (S1-b), before any labelling

A vendored agent you did not write may have no goal field, no predicted delta, no search trace. Each of
the 13 failure categories is defined on specific evidence (`gate_manifest.yaml →
s1.failure_taxonomy.categories.*.evidence`); a category whose evidence the reference does not emit cannot
be labelled at all.

**Propagation rule (§4.2) — the reason this table exists:** a category marked `unavailable` here is
marked `unavailable` in the Day-7 ranking. It is **never counted as zero-frequency.** An unobservable
failure mode that silently ranks last would steer eight weeks of construction away from what may be the
largest lever.

Where a field is missing and cheap to add, adding it is a **permitted deviation** — implement it as a
patch in `agent/patches/` and reference the patch here.

Verdicts: `available` · `partial` (say which half) · `unavailable`.

| # | Category | Evidence the category is defined on | Exposed? | Cheap to add? | Patch ref |
|---|---|---|---|---|---|
| 1 | `goal_unknown` | agent goal field + the transition that actually advanced the level | **partial** — level advancement `available` (events `level`/`state`); **no structured goal field.** The objective exists only as prose inside `reasoning_content` / transcripts | no — would need a solver-side schema change, which alters control flow | — |
| 2 | `action_semantics_unknown` | predicted delta vs observed delta | **partial** — observed delta `available` (consecutive `board`s); **no `predicted_delta` field.** Predictions appear only as prose, when the model happens to state one | no — same objection as #1 | — |
| 3 | `perception_parsing` | frame + parsed state description | **available** — `board` + `board_ascii` + the segmentation view the agent is given, against its own description in `reasoning_content` | — | — |
| 4 | `hidden_state_aliasing_or_memory` | both frames, both actions, both outcomes | **available** — full grids per step make observationally-identical states directly detectable | — | — |
| 5 | `coordinate_unreachable` | candidate set at the step + the coordinate that later worked | **available with D6** — `valid_actions` is in the prompt, captured by `requests.jsonl` | **NOT yet enabled — needs `--save-request-logs`** | D6 |
| 6 | `planning_depth` | shortest known successful sequence length vs the agent's effective horizon | **UNAVAILABLE** — see the callout below | no | — |
| 7 | `exploration_or_probe_selection` | action taken + its no-op/redundant outcome + the available alternative | **available with D6** — no-op detectable from board equality; alternatives from `valid_actions` | **NOT yet enabled — needs `--save-request-logs`** | D6 |
| 8 | `progress_signal_misinterpretation` | score/level marker vs the agent's recorded belief | **partial** — markers `available` (`score`, `level`, `reward`); belief is prose only | no | — |
| 9 | `irreversible_mistake` | the transition + the subsequent dead-end | **available** — boards plus terminal `state` | — | — |
| 10 | `invalid_output_interface` | raw agent output + the rejection | **available with D6** — `finish_reason`, raw `tool_calls`, and the harness's own `_recover_tool_calls_from_markup` path flags malformed output | **NOT yet enabled — needs `--save-request-logs`** | D6 |
| 11 | `retrieval_or_context` | the stored record + the context snapshot that omitted it | **available with D6** — `requests.jsonl` stores the full `messages` array, which *is* the context snapshot | **NOT yet enabled — needs `--save-request-logs`** | D6 |
| 12 | `reasoning_inconsistency` | reasoning text + action | **available** — `reasoning_content` verbatim, paired with the executed action via `analysis_step` | — | — |
| 13 | `latency_or_budget` | timing and budget counters at the terminal step | **available** — `ActionRecord.wallclock_seconds`, `generated_tokens`, `uncached_input_tokens`, against `max_actions` / `max_runtime_minutes` | — | — |

### 🔴 The stratification problem, surfaced on Day 2 as the plan requires

The measurements stub warned: *"`goal_unknown` and `planning_depth` are oversampled by the blind re-rate
and are mutually confounded by design. If either is `unavailable`, the re-rate's stratification loses the
two strata it was built around — surface that on Day 2, not on Day 7."* **Both are now degraded, and this
is that surfacing.**

- **`planning_depth` is `unavailable`, structurally.** The duck is not a search agent — it writes and runs
  Python rather than expanding a search tree — so there is no `effective_search_depth`, no search trace,
  and no representable horizon to compare a sequence length against. This is not a missing log line that a
  patch could add; the quantity the category is defined on **does not exist in this architecture**.
- **`goal_unknown` is `partial`** — the objective is recoverable only as self-reported prose.

Consequences, none of them deferrable to Day 7:

1. Per the propagation rule, `planning_depth` is marked `unavailable` in the Day-7 ranking and is
   **never counted as zero-frequency**. It does not enter `build_order`.
2. The blind re-rate cannot stratify on `planning_depth`. **The re-rate design needs amending before
   Day 5**, since Day 5 is when the sample is drawn. Options, to decide in S1-c: oversample
   `goal_unknown` alone; or re-target the second stratum onto a category that *is* available and
   contested (`exploration_or_probe_selection` is the natural candidate — it is the nearest thing to a
   planning failure this architecture can express).
3. The pre-registered `goal_unknown` / `planning_depth` confound **cannot be measured at all here.**
   That confound was the stated reason the first pass is "descriptive, not causal". With one arm
   unobservable, the confound is not resolved — it is simply invisible. Say so in the close-out rather
   than reporting a clean `goal_unknown` frequency that quietly absorbs it.

This is a property of the *reference architecture*, not of our port, and it would have applied equally on
CUDA. It is the clearest example so far of why the field-availability table exists.

Two consequences to check before Day 5, not after:

- `goal_unknown` and `planning_depth` are **oversampled by the blind re-rate** and are mutually
  confounded by design. If either is `unavailable`, the re-rate's stratification loses the two strata it
  was built around — surface that on Day 2, not on Day 7.
- `reasoning_inconsistency` is defined *solely* on agent rationale. No rationale field means the category
  is unlabelable, not rare.

## Latency

### Concurrency scaling — measured 2026-07-26 (S1-c work pulled forward into S1-b)

Script: `agent/harness/concurrency_sweep.py`. Raw: `logs/concurrency_sweep.json`,
`logs/concurrency_sweep_merged.json`. Model `mlx-community/Qwen3.6-27B-4bit` on the M5 Pro via
`mlx_vlm.server` with `--enable-thinking`; 256-token generations; two sweeps (1,2,4,8 then 3,4,5,6).

| Concurrency | Aggregate tok/s | Per-request tok/s |
|---:|---:|---:|
| 1 | 17.0 | 17.0 |
| 2 | 31.8 | 16.0 |
| 3 | 42.9 | 14.3 |
| 4 | 54.5 | 13.7 |
| **5** | **59.9** ← peak | 12.0 |
| 6 | 54.4 | 9.1 |
| 8 | 45.9 | 5.7 |

Server RSS held flat at **15.7 GiB** across every level, so the ceiling is compute/scheduling, not
memory — nowhere near the 44.06 GiB `peak_resident_set_max_gib` threshold. The 17 tok/s at N=1 agrees
with the ~16.1–16.4 tok/s the server logged during a real game run, so the synthetic prompt is not
flattering the measurement.

**Aggregate scales ~3.5× to N=5, then regresses. Per-request throughput only ever falls.** Decode is
memory-bandwidth-bound on the weights: extra streams amortise the weight reads (aggregate rises) but no
single stream ever speeds up.

#### The consequence that matters for the build

**Concurrency buys breadth, not depth.** The duck's loop *within* one game is strictly sequential — each
model call is conditioned on the previous one — so `concurrent_jobs` parallelises *games*, never the
critical path of one game. It is therefore the right lever for the Day-5 run across 25 games and the
wrong lever for per-game wall-clock, which is what actually stalled the first ft09 attempt.

**Operating point selected: `concurrent_jobs: 4.`** N=5 is the aggregate peak but only ~10% above N=4
while costing ~12% per-request throughput, and N=4 leaves scheduling room for the Python tool sandbox and
the instrumentation processes that share the machine. Recorded in `agent/harness/build_local.sh` as the
default; every latency figure must carry the concurrency it was measured at (freeze §5).

**Escalation trigger #3 does not fire.** The freeze pre-registered "sustainable local concurrency < 4" as
a trigger to escalate to hybrid. The measured usable band is 4–5, so local-only holds — *but with no
margin above 5*, and this is the trigger to re-check after the Day-5 breadth run rather than to treat as
settled.

#### Why a single game is slow — the reference's own budgets, read from the code

Effective analyzer budgets, dumped from the installed module (`inference.agent.tool_agent`):

| Knob | Value | Meaning |
|---|---:|---|
| `_LOCAL_ANALYZER_TOOL_STEPS` | **12** | up to 12 model calls per **one** game action |
| `_LOCAL_ANALYZER_MAX_OUTPUT` | **0** | → `None`: **no cap** on output tokens per call |
| `_LOCAL_ANALYZER_ENABLE_THINKING` | True | reasoning tokens on top of the answer |
| `_LOCAL_ANALYZER_CONTEXT_WINDOW` | 32768 | |
| `_LOCAL_ANALYZER_TOOL_OUTPUT_TOKENS` | 1024 | tool result truncation |

So one game action costs **up to twelve uncapped generations**. At the measured 13.7 tok/s per stream at
concurrency 4, that is minutes per game action, and ft09 needs a 43-action level 1 (208 actions across its
six levels) — before accounting for the agent being less efficient than the human baseline.

**This is the reference's operating point, not a defect of our port.** It is affordable on an RTX PRO
6000 with FP8 weights and 32-way batching; it is not affordable at 13.7 tok/s. Note also that the
config's `analyzer.tool_steps: 0` is **not** wired to `_LOCAL_ANALYZER_TOOL_STEPS` — that constant reads
the `LOCAL_ANALYZER_TOOL_STEPS` environment variable and otherwise takes its code default of 12. Setting
the config field alone changes nothing; the env var is the real lever.

These are first-class knobs the reference already exposes, so bounding them is a *configuration*
deviation rather than a code change — but it is still a deviation with a real fidelity cost, and it must
be measured as its own contrast rather than folded in silently.

#### Still open — the real single-game constraint

Per-game wall-clock is bounded by **tokens per action**, not by parallelism. The first ft09 attempt
generated roughly 7.6k tokens (~7.5 min at 17 tok/s) before its *first* game action, all of it in the
duck's opening analysis phase. `mlx_vlm.server --thinking-budget` caps that directly, but the reference
runs `thinking: true` and a budget cap is a **new deviation with a real fidelity cost** — to be measured
as its own contrast, not folded in silently. Not yet run.

### Per-action latency table — S1-c

Generated table:

## Submission contract — read from the reference notebook, 2026-07-26 (S1-f prep)

Established without spending the 1/day submission quota, by reading the reference notebook we pushed as
a private copy. Two execution modes, switched by an environment variable:

| | Visible "Save & Run" | Hidden competition rerun |
|---|---|---|
| Selector | `KAGGLE_IS_COMPETITION_RERUN` unset/false | set to `1`/`true` |
| Games | **bundled offline env files** at `/kaggle/input/competitions/arc-prize-2026-arc-agi-3/.../environment_files` | live competition Arcade via the Kaggle **gateway** at `ARC_BASE_URL` (default `http://gateway:8001/`), `OperationMode.COMPETITION` |
| Scoring | not scored | through the gateway |
| Output | **must still write `submission.parquet`** | written by the framework |

`submission.parquet` schema is `["row_id", "game_id", "end_of_game", "score"]`; on the unscored visible
path the notebook writes a single placeholder row `["1_0", "1", True, 1]` purely to satisfy Kaggle's
output requirement. The notebook also forces `bm.n_passes = 1` and sets `TAAF_RUN_AS_SUBMISSION` /
`TAAF_MINIMAL_DIAGNOSTICS` so diagnostics and per-frame logging are suppressed during a real rerun.

**Confirms our local setup is on the reference's own offline path** — the competition
`environment_files` the notebook uses in visible mode are exactly the ones we downloaded with the Kaggle
CLI and pointed `--re-arc-environments-dir` at.

### 🔴 The development/submission divergence — a consequence of local-only, and a caveat on S1-d

Kaggle provides CUDA. A Day-6 payload therefore runs **vLLM + FP8 on an RTX PRO 6000** — the reference
stack unmodified. **D1 and D2 do not propagate to the submission at all**: the MLX 4-bit port is a
*local development and instrumentation vehicle*, not the submitted artifact.

That is good for the submission's fidelity, and it creates two problems that must not be discovered at
S1-g:

1. **Local latency and throughput figures do not transfer to Kaggle.** The 13.7 tok/s, the 284 s/action,
   the concurrency-4 ceiling — all are properties of MLX 4-bit on an M5 Pro and say nothing about the
   submitted agent's runtime envelope. `per_action_latency` must therefore be read against the
   *submission* stack before it can gate anything, or its verdict scoped explicitly to local development.
2. **Failure frequencies labelled locally are labelled on a different model.** The Day-5 run at MLX 4-bit
   produces the taxonomy that ranks the build order, but the agent that gets submitted is FP8. D2's
   "unquantified capability loss" was recorded as a fidelity risk; this is where it bites — a quantization
   that changes *which* failures dominate would misrank §11's construction order. The gap is not
   currently measured in either direction.

Neither is fatal and neither is a reason to abandon local-only, but both must be stated in the close-out
rather than absorbed. The cheapest mitigation available is the Kaggle reference run already in flight: it
produces FP8-on-RTX-6000 numbers for the *same solver*, which bounds the size of gap (1) directly and
gives a first handle on (2) via per-game outcomes.

## Hardware fit

- Peak VRAM:
- VRAM headroom:
- Throughput degradation:

## Legal-action reliability

- Accepted actions:
- Emitted actions:
- Validity:
- Rejection taxonomy:

## Public-game progress

- Frozen target:
- Observed result:
- Gap:

## Reset and action accounting

### R1 — knowledge preservation across RESET. **Result: `deterministic`** (2026-07-26)

Script `agent/harness/r1_determinism.py`; raw `logs/r1_determinism.json`. Sampling exactly as
pre-registered: 2 distinct public games (`ft09-0d8bbf25`, `ls20-9607627b`), 2 prefixes each (10 and 40
scripted actions), 3 replays per prefix, exact frame-sequence equality.

| Game | Prefix | Replays | Verdict |
|---|---:|---:|---|
| ft09-0d8bbf25 | 10 | 3 | identical |
| ft09-0d8bbf25 | 40 | 3 | identical |
| ls20-9607627b | 10 | 3 | identical |
| ls20-9607627b | 40 | 3 | identical |

No divergence anywhere, so no first-divergence index to record.

**Falsification check — required, because "identical" is trivially true if nothing ever changes.**
Distinct observations *within* each replay: ft09 **11/11** steps at prefix 10 and **34/41** at prefix 40;
ls20 **9/11** and **31/41**. The grids genuinely change step to step, so agreement across replays is a
real property and not an artefact of a static board. (ls20's repeats are no-op actions — incidentally
useful evidence for `exploration_or_probe_selection` later.)

**Scope — do not overclaim.** This ran against the **OFFLINE competition environment files**, the same
game implementations Kaggle's *visible* path uses. It is evidence about the **game code**. It is **not** a
test of competition mode, whose scorecard and one-`make()` restrictions (V5–V7) differ. The supported
claim is exactly: *these tested prefixes replay exactly, offline.* Not "everything learned transfers".

#### ⚠ A bug that would have inverted this result, caught before it was recorded

The first implementation hashed `FrameDataRaw.model_dump()`. That method **silently omits the `frame`
field holding the numpy grids**, so the digest compared metadata only and never looked at a single pixel.
It also included `full_reset` — `True` on the first reset after `make()`, `False` on every later one —
which made the first replay of each prefix "diverge at step 0" for a reason with nothing to do with
determinism. That run reported **`inconclusive`**, and it was wrong in both directions at once: a false
divergence on the short prefixes, and a meaningless "identical" on the long ones.

It was caught only because the pattern was internally contradictory — diverging at step 0 on a 10-action
prefix while a 40-action prefix on the same environment matched. **A metadata-only digest that had
happened to agree everywhere would have produced a confident `deterministic` with no pixel ever
compared.** The falsification check above now exists to make that failure mode impossible to repeat.

### R2 — action accounting

**Unblocked**: R2's precondition is `r1 == deterministic`, which now holds. Not yet run — it needs live
scorecards (close-then-read, forced by V7) and the three preconditions checked before any score is read.

- R1 result: `deterministic` — see above
- R2 result:
- R2 result:
- Controller selected:
