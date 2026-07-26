# S1 Close-out

**Status:** Not started.

## Distance to competitive

## Failure-frequency build order

## Controller fork

## Viability verdicts

## S2 inheritance — ARC-compatible conventions the generators must match

**Measured 2026-07-26 across all 25 public games** (not taken from documentation). Close-out item 5;
the plan calls this "cheap now and expensive on Aug 12", and one item below would have been expensive.

**Reproducible evidence:** `agent/harness/measure_arc_conventions.py` → `logs/s2_arc_conventions.json`.
Every value in this section regenerates from that script; it was added after review noted the section
originally carried prose only, which could not be independently checked.

| Convention | Measured value |
|---|---|
| Grid shape | **64×64, always**, at reset across all 25 games |
| Cell values | **0–15, and all 16 values occur** — the documented range is fully exercised |
| Frames per observation | **1–N, and N VARIES WITHIN AN EPISODE** — see below |
| Levels per game | 6–10 (mode 6) |
| Level-1 human baselines | 6 (vc33 = 7) to 78; across all levels, up to 578 |
| Action space | `RESET` + `ACTION1`–`ACTION7`; `ACTION6` carries (x, y) |
| Action availability | **per-game and per-state**, re-read every step. At reset: `ACTION6` in 19/25 games, `ACTION1–4` in ~16–17, `ACTION5` in 9, `ACTION7` in 6 |

### 🔴 The one that would have been expensive: observations are frame *sequences* of varying length

`FrameDataRaw.frame` is a **list** of 64×64 grids, not a single grid. Two games return 2 frames at reset
(`bp35-0a0ad940`, `lf52-271a04aa`) while 23 return 1 — but the count is **not a static per-game
property**. Stepping `ls20-9607627b` produced this sequence of frame counts:

```
1, 1, 1, 1, 1, 1, 1, 6, 6
```

Seven single-frame observations, then **six frames** in one observation. This is the environment's
"1–N grid frames" contract behaving dynamically — presumably animation of a multi-step consequence.

**Consequences for S2 and S4, to be honoured at design time rather than patched later:**

1. **The F1/F3 generators must emit variable-length frame sequences per observation**, not a fixed one
   grid per step. A generator that always emits one frame would produce a distribution the real
   environment never generates, and S4's advisor test would then be measured on a mismatch.
2. **Any encoder must consume 1–N frames per step.** A model assuming a single grid silently discards up
   to five-sixths of the observation at exactly the steps where something interesting happened — which is
   the worst possible place to lose information, and would be invisible in aggregate loss.
3. **This interacts directly with F1 (history-required aliasing).** If an observation is itself a short
   sequence, part of the "history" the aliasing test is about is *inside a single observation*. The
   generator's notion of a timestep must be defined against this, or F1's ceilings measure something
   other than what they claim.
4. Padding: grids are already uniformly 64×64, so no padding convention is needed — but record that this
   is *verified serialization*, not necessarily the environment's intrinsic grid size.

### Also inherited

- **Scoring** as V8 corrects it: `min(115, (baseline/actions)² × 100)` per level on a 0–100 scale, level
  score capped at 115, game score capped at completed-weight fraction, unweighted mean across games.
- **`c_reset = 1`** — RESET is itself a scored action (measured in R2).
- **Determinism** — offline environments replay exactly (R1), so generator-side reproducibility is a fair
  assumption for the offline path.

## S2 inheritance (original stub)

## Paper deposit
