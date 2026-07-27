# 8-bit quantization arm — H5, running notes (2026-07-27)

Matched pair, `mlx-community/Qwen3.6-27B-4bit` vs `mlx-community/Qwen3.6-27B-8bit`: same base weights,
same converter, same `group_size: 64`, same `affine` mode. **Only `bits` differs.** Same harness, same
45-minute budget, concurrency 1, `max_output` unchanged at 16384.

This is H5's pre-registered question — *does quantisation shift which failures dominate, not merely
their magnitude* — and it was recorded as "untested and consequential".

## `tn36-ef4dde99` — 4-bit failed, 8-bit cleared level 1

| arm | generations | acted | actions | actions/gen | L1 cleared |
|---|---:|---:|---:|---:|---|
| 4-bit | 33 | 12% | 4 | 0.12 | no |
| **8-bit** | **31** | **32%** | **14** | **0.45** | **yes, in 11 actions** |
| reference, FP8 | 30 | — | 82 | 2.73 | yes, in 45 actions |

**Generations are 33 / 31 / 30 across all three arms.** Compute was never the variable. What precision
changed is willingness to commit: acting rate 12% → 32%, actions per generation 0.12 → 0.45, a 3.75×
shift — and that was enough to clear a level the 4-bit model never reached in the same wall-clock.

Clearing efficiency: 11 actions against a 32-action human baseline (0.34×), better than the reference's
45 (1.41×). Verified the same way as `ar25` — `score` 0 → 1, `reward = 0.1428` paid by the environment,
level markers monotonic `[1, 2]`.

## What this does not settle

**Precision explains part of the gap, not all of it.** 8-bit reaches 0.45 actions/generation against the
reference's 2.73 — still ~6× short, despite 8-bit and FP8 carrying comparable bit budgets. Something
besides quantisation is also suppressing action commitment. Untested candidates: the serving stack
(`mlx_vlm` here versus vLLM with the `qwen3_coder` tool parser there) and prompt/template handling.

**n = 1, on the most extreme case.** `tn36` had the lowest actions-per-generation in the entire 4-bit
arm, so it is the game most likely to improve by regression to the mean. Sampling is stochastic
(`temperature 0.6`, no seed) and `vc33` alone swung 23 → 51 actions across two identical 4-bit runs, so
the noise floor is roughly 2×. This result is above it, but one game does not carry the claim.

## Consequence if the remaining games agree

The 17-episode 4-bit corpus would then be substantially **a measurement of the quantisation rather than
of the task**, and the failure-frequency ranking derived from it would inherit that. The build order is
ranked on those frequencies, so this is not a footnote — it decides whether the corpus can be used at
all for its stated purpose.

## Throughput cost

8-bit runs at ~8.3 tok/s against 4-bit's ~12.1 — about ⅔ the speed — so it gets slightly fewer
generations per 45 minutes (31 vs 33). The action gain is not bought with extra compute; it is bought
per turn.
