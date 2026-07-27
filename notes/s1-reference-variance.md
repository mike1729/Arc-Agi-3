# The reference's run-to-run variance, measured — 2026-07-27

The frozen manifest declines to gate on reproduction fidelity partly because *"run-to-run variance is
large and undocumented"* (`gate_manifest.yaml`, `s1.reproduction_fidelity`). That clause was written
from the reference author's own remark, not from a measurement.

It is now measured. **Two complete 25-game runs of the unmodified reference, same Kaggle kernel, same
RTX PRO 6000, same FP8 model, same 132-minute budget, same code.** The only edit between them was
`bm.solver.save_request_logs = True`, which writes log files and touches nothing in the control path.

The variance is not large. It is bigger than most of the effects S1 is trying to measure.

---

## The headline

| | v1 (Jul 26) | v2 (Jul 27) |
|---|---:|---:|
| **mean score** | **2.19** | **1.14** |
| median score | 0.13 | 0.00 |
| total levels cleared | 18 | 15 |
| total actions | 3806 | 3866 |
| duration | 2 h 12 m 42 s | 2 h 12 m 6 s |

**The primary metric halved.** Total actions moved 1.6% and wall-clock moved 36 seconds, so this is not
a throughput or scheduling artifact — the agent did the same amount of work and got a substantially
different score.

## Per game

Of 25 games, **exactly one produced an identical result** (`ft09`: 65 actions, 2 levels, both runs).

**9 of 25 games (36%) changed their cleared-level count:**

| game | v1 | v2 | | game | v1 | v2 |
|---|---:|---:|---|---|---:|---:|
| `ar25` | 1 | 0 | | `sc25` | 1 | 0 |
| `dc22` | 1 | 0 | | `tn36` | 1 | **0** |
| `s5i5` | 1 | 0 | | `tu93` | 1 | 2 |
| `ka59` | 0 | 1 | | `vc33` | **2** | **1** |
| `lf52` | 0 | 1 | | | | |

**8 of 25 games (32%) changed their action count by more than 2× in one direction or the other** —
`bp35`, `cn04`, `dc22`, `g50t`, `lf52`, `ls20`, `tn36`, `wa30`. The extremes: `lf52` 69 → 394 actions
(5.7×), `dc22` 183 → 31 (0.17×). The *median* ratio is 0.99, so there is no systematic drift; the
distribution is simply wide.

## Why — it is by design, not a defect

`agent/reference/taaf/src/ARC3-Inference/inference/agent/tool_agent.py:145`

```
_LOCAL_ANALYZER_TEMPERATURE = _get_env_float("LOCAL_ANALYZER_TEMPERATURE", 0.6)
_LOCAL_ANALYZER_TOP_P       = _get_env_float("LOCAL_ANALYZER_TOP_P", 0.95)
_LOCAL_ANALYZER_SEED        = _get_env_int("LOCAL_ANALYZER_SEED", -1)
```

Temperature 0.6, top-p 0.95, **seed −1 — no seed at all.** Every generation is an independent sample,
each one steers the next through the conversation history, and a single divergent early turn changes
the whole trajectory. The agent is a chaotic system by construction. `LOCAL_ANALYZER_SEED` is a settable
env var, so a seeded replicate is available if a future experiment wants one.

Note that R1 measured the *environment* to be deterministic. Both facts hold: identical action sequences
replay identically, and the agent does not produce identical action sequences.

---

## What this invalidates

### The 8-bit quantisation arm does not reach significance

The arm ran one 45-minute run per game per precision on 8 games. Result: 8-bit cleared a level on 3,
4-bit on 0, with no game where 4-bit cleared and 8-bit did not. As a paired comparison that is **3
discordant pairs, all in one direction**, and the exact sign test gives

> **p = 0.25** (two-sided). One direction out of 3 is simply not rare.

Worse, the *rate* of discordance is uninformative: 3 of 8 games (37.5%) disagreed between the arms,
against 9 of 25 (36%) for the reference **disagreeing with itself**. The two arms differ about as much
as one configuration differs from a rerun of itself.

The sign test needs **6 discordant pairs all one way for p < 0.05**, or 5 for p = 0.0625. With a ~37%
discordance rate that implies roughly **16 paired games**, or fewer games with replicates.

**This does not say 8-bit is no better than 4-bit.** It says this experiment cannot tell, and the
result I was assembling through the day — "8-bit clears 3, 4-bit clears 0" — was being read as stronger
than a p = 0.25 finding.

### What survives in the quantisation arm

Not everything falls. The claims resting on *within-run* statistics have many samples per run and are
far less exposed:

- **Acting rate** — 8-bit 25–32% across games, 4-bit 12–50%. Tens to hundreds of generations per
  measurement, not one binary outcome.
- **Actions per generation** — `tn36` 0.12 → 0.45.
- **Generations are equal across arms** (33 / 31 / 30 on `tn36`), so compute was never the variable.
  This is a strong claim: it is a near-identical count, not a difference needing significance.

The distinction is exactly the one to keep: **per-episode outcomes are single Bernoulli draws from a
high-variance process; per-generation rates are means over many draws.**

### The S1-d corpus and the build order inherit this

This is the consequential part, and it is not about quantisation.

S1-E2 ranks the build order on **failure frequencies** derived from the labelled corpus. Every episode
in that corpus is one sample of a process where 36% of games change their level outcome on rerun. A
frequency ranking over single samples of such a process is noisy in a way nothing in the labelling
protocol corrects — blind re-rating (S1-E7) measures *rater* agreement, not *run* variance, so it
cannot detect this at all.

Two things soften it, and neither dissolves it:

1. Failure *categories* may be more stable than level outcomes. A game can fail at 31 or 394 actions
   and still fail the same way. **Untested** — and testable, because v1 and v2 give 25 paired episodes.
2. The ranking aggregates across ~25 games, so per-game noise partly averages out. Whether it averages
   out *enough* to order the top categories depends on how separated they are, which is measurable
   from the corpus rather than assumable.

**The direct test now available:** label the v2 episodes with the same protocol as v1 and compare
category frequencies. If the ranking is stable across two runs of the same agent, the build order is
safe; if it reorders, the sprint's central output is under-determined and needs replicates. This is a
labelling job on data already on disk, and it uses the request logs v2 was rerun to obtain.

---

## What to change

- **Never report a per-episode outcome difference from single runs again.** The noise floor for
  "cleared / did not clear" is ~36% discordance.
- **Prefer within-run rate statistics** where a question can be posed that way.
- **Price replication into any future arm.** ~16 paired games, or 8 games × 2 seeds, for a sign test
  with any power. At 45 min/game that is 12 h per arm — a real cost, and cheaper than a wrong build
  order.
- **`LOCAL_ANALYZER_SEED` is settable.** Fixing it removes generation noise but not the underlying
  fragility, and a seeded run answers a narrower question ("is this trajectory better") than the one
  S1 asks ("is this configuration better"). Prefer replicates over seed-pinning for configuration
  comparisons.

## Provenance

- v1: `logs/kaggle-reference/` — kernel `s1b-tufa-duck-reference-measurement` v1, 2026-07-26 07:10 UTC
- v2: `logs/kaggle_v2/` — same kernel v2, 2026-07-27 11:41 UTC, `save_request_logs = True`, 25 per-game
  request logs (516 MB) — the reasoning evidence v1 lacked
- statistics: exact binomial sign test, computed inline; nothing here is a hand-typed number
