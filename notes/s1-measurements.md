# S1 Measurements

**Status:** Not started.

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
| 1 | `goal_unknown` | agent goal field + the transition that actually advanced the level | | | |
| 2 | `action_semantics_unknown` | predicted delta vs observed delta | | | |
| 3 | `perception_parsing` | frame + parsed state description | | | |
| 4 | `hidden_state_aliasing_or_memory` | both frames, both actions, both outcomes | | | |
| 5 | `coordinate_unreachable` | candidate set at the step + the coordinate that later worked | | | |
| 6 | `planning_depth` | shortest known successful sequence length vs the agent's effective horizon | | | |
| 7 | `exploration_or_probe_selection` | action taken + its no-op/redundant outcome + the available alternative | | | |
| 8 | `progress_signal_misinterpretation` | score/level marker vs the agent's recorded belief | | | |
| 9 | `irreversible_mistake` | the transition + the subsequent dead-end | | | |
| 10 | `invalid_output_interface` | raw agent output + the rejection | | | |
| 11 | `retrieval_or_context` | the stored record + the context snapshot that omitted it | | | |
| 12 | `reasoning_inconsistency` | reasoning text + action | | | |
| 13 | `latency_or_budget` | timing and budget counters at the terminal step | | | |

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
