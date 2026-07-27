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

---

## Is the residual gap a setup difference? — five candidates checked, 2026-07-27

Both local arms sit far below the reference's 2.73 actions/generation (4-bit 0.12–0.53, 8-bit
0.25–0.56). Since precision alone does not close that, the question is whether our reproduction differs
from the reference in configuration. Five candidates were checked against the vendored reference.

| candidate | verdict |
|---|---|
| full config diff | **faithful.** Only model, concurrency, and the D10/D13 fixes differ |
| `analyzer.tool_steps = 0` (unlimited) | **same**, and correctly exported by `run_local.sh` |
| `analyzer.yield_seconds = 60` per-turn budget | **refuted — see below** |
| `multimodal.context = current_grid`, upscale 4 | **same**, and every request carries an image part |
| reasoning/content token split | 8-bit is *more* concise (687 vs 1657 chars); does not explain |

### The hypothesis that failed, recorded because it was a good one

`yield_seconds` is a wall-clock budget per agent turn, checked *before* each tool-call iteration. Our
generations take ~80 s against a 60 s budget, which would break the loop after the first iteration
every time — capping us at one tool call per turn while the reference, at seconds per generation, could
inspect *and* act within one. That would have explained the whole gap, and it fits the observed
"inspect, inspect, inspect, act" pattern exactly.

**It is wrong.** Measured requests per `analysis_step`: 4-bit `{1:58, 2:80, 3:20, 4:4, 5:16, 6:2, 10:1,
12:1, 13:3, 14:1, 17:1}`, 8-bit similar. Only 31% and 23% of steps got exactly one turn; multi-turn is
routine, up to 17. The budget is not binding.

### What is left, and it is not configuration

1. **A different model artifact, not merely a different precision.** The reference runs
   `vrfai/Qwen3.6-27B-FP8`; we run `mlx-community/Qwen3.6-27B-{4,8}bit`. Different quantizer, different
   format, different provenance. "8-bit versus FP8" was therefore never a clean precision contrast, and
   the quantization arm above should be read as *4-bit versus 8-bit within one conversion lineage*
   rather than as a step toward the reference.
2. **A different inference engine.** vLLM with `tool_call_parser: qwen3_coder` and
   `reasoning_parser: qwen3`, versus `mlx_vlm`. Tool-call extraction and thinking-token handling are
   engine-specific.
3. Concurrency 28 versus 1 — should not affect actions *per generation*, but is uncontrolled.

These are exactly the deviations the reference freeze pre-registered as D1–D5, with D5 (tool calling)
named "the most likely single point of failure". D5 passes *functionally* — tool calls parse — but
"parses correctly" and "elicits the same behaviour" are different bars and only the first was tested.

**What would settle it.** Rent one RTX PRO 6000 (the competition accelerator, $1.69/hr) and run
`vrfai/Qwen3.6-27B-FP8` on vLLM — the reference's exact artifact and engine. That separates
model-and-stack from task difficulty, which no amount of config inspection can.
