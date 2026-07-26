# Vendored references — read before making this repository public

Everything under this directory is **third-party material**, vendored **unmodified** at a frozen
snapshot. Deviations live in `agent/patches/` as patch files and are applied to a throwaway working
copy by `agent/harness/build_local.sh`. Nothing here is ever edited in place — the diff is the audit
trail (`CLAUDE.md`, working conventions).

## ⚠ LICENSE STATUS — CLOSED BY SCOPE. This directory is never published.

| Item | Status |
|---|---|
| `taaf/` — Kaggle dataset `jeroencottaar/taaf-kaggle-source-share`, snapshot 2026-06-12 07:57 UTC | **NO DECLARED LICENCE.** `kaggle datasets metadata` returns `licenses: []` |

**Decision, 2026-07-26:** the reproduction is a **local measurement vehicle only**. It is not shipped,
not submitted, and not published. The licence is therefore never *needed* — retaining a snapshot in a
private repository for local measurement is not redistribution.

### The enforcement point — intent alone does not hold

**Git history counts as redistribution.** This directory is committed, so making *this* repository
public would redistribute it **even if the directory were deleted first**. And something must eventually
be public: competition prize eligibility requires open-sourcing entrant-authored code.

So one of these is required before anything is published:

1. **Publish a separate clean repository** containing only entrant-authored work — the practical option, and
2. or scrub this repository's history before publishing it.

**Do not rely on deleting the directory.** That is the failure mode this note exists to prevent.

### What this changes downstream

The reproduced baseline **cannot be the Day-6 submission payload**. S1-f's original purpose — dropping
the reproduced baseline into the proven submission path to establish a leaderboard reference — no longer
applies. A leaderboard reference now requires an entrant-authored payload, or S1 exits without one. See
`gate_manifest.yaml → s1.results.threshold_verdicts.packaging`.

## Scoring implementation used by the reference

The local score calculation is implemented in
`taaf/src/tufa-arc-agi-framework/src/taaf/game.py::GameRun._compute_final_score`, documented there as a
mirror of `arc_agi.scorecard.EnvironmentScoreCalculator` v0.9.8:

```python
level_score = min(115.0, (baseline / actions) ** 2 * 100)
game_score = min(weighted_level_mean, completed_weight / total_weight * 100)
```

The square is applied before the per-level cap. The maximum per-level score is therefore 115 on the
implementation's 0–100 scale, or 1.15 on a unit scale—not 132.25 / 1.3225.
