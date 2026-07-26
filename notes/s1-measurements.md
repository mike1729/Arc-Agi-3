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
