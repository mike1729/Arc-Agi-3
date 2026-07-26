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
`raw_model_output` several categories are defined on. It is a **config flag, not a code patch**, and it
is off by default. It is enabled in `agent/harness/build_local.sh`.

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
| 5 | `coordinate_unreachable` | candidate set at the step + the coordinate that later worked | **available with D6** — `valid_actions` is in the prompt, captured by `requests.jsonl` | already enabled (config flag) | D6 |
| 6 | `planning_depth` | shortest known successful sequence length vs the agent's effective horizon | **UNAVAILABLE** — see the callout below | no | — |
| 7 | `exploration_or_probe_selection` | action taken + its no-op/redundant outcome + the available alternative | **available with D6** — no-op detectable from board equality; alternatives from `valid_actions` | already enabled | D6 |
| 8 | `progress_signal_misinterpretation` | score/level marker vs the agent's recorded belief | **partial** — markers `available` (`score`, `level`, `reward`); belief is prose only | no | — |
| 9 | `irreversible_mistake` | the transition + the subsequent dead-end | **available** — boards plus terminal `state` | — | — |
| 10 | `invalid_output_interface` | raw agent output + the rejection | **available with D6** — `finish_reason`, raw `tool_calls`, and the harness's own `_recover_tool_calls_from_markup` path flags malformed output | already enabled | D6 |
| 11 | `retrieval_or_context` | the stored record + the context snapshot that omitted it | **available with D6** — `requests.jsonl` stores the full `messages` array, which *is* the context snapshot | already enabled | D6 |
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

#### Still open — the real single-game constraint

Per-game wall-clock is bounded by **tokens per action**, not by parallelism. The first ft09 attempt
generated roughly 7.6k tokens (~7.5 min at 17 tok/s) before its *first* game action, all of it in the
duck's opening analysis phase. `mlx_vlm.server --thinking-budget` caps that directly, but the reference
runs `thinking: true` and a budget cap is a **new deviation with a real fidelity cost** — to be measured
as its own contrast, not folded in silently. Not yet run.

### Per-action latency table — S1-c

Generated table:

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

- R1 result:
- R2 result:
- Controller selected:
