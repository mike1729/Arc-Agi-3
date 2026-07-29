# The reference's run-to-run variance, measured — 2026-07-27

The frozen manifest declines to gate on reproduction fidelity partly because *"run-to-run variance is
large and undocumented"* (`gate_manifest.yaml`, `s1.reproduction_fidelity`). That clause was written
from the reference author's own remark, not from a measurement.

It is now measured. **Four complete 25-game runs of the unmodified reference, same Kaggle kernel, same
RTX PRO 6000, same FP8 model, same 132-minute budget, same code.** The only edit anywhere in the series
was `bm.solver.save_request_logs = True` between v1 and v2, which writes log files and touches nothing
in the control path; v2, v3 and v4 are byte-identical in executed source (verified by diffing the
notebook Kaggle actually ran — only comments differ — and by identical `HarnessSolver(...)` reprs).

The variance is not large. It is bigger than most of the effects S1 is trying to measure.

---

## The headline

| | v1 (Jul 26) | v2 (Jul 27) | v3 (Jul 27) | v4 (Jul 27) |
|---|---:|---:|---:|---:|
| **mean score** | **2.19** | **1.14** | **1.60** | **1.52** |
| median score | 0.13 | 0.00 | — | — |
| games clearing ≥1 level | — | 12 / 25 | 15 / 25 | 15 / 25 |
| total actions | 3806 | 3866 | 4776 | 3833 |
| notebook wall-clock | — | 2 h 22 m 49 s | 2 h 22 m 34 s | 2 h 21 m 50 s |

**Across four runs of one configuration the mean score spans 1.14 – 2.19, a 1.9× range.** v1 is the high
outlier; the three logged runs sit at 1.14 / 1.60 / 1.52. Total actions span 3806 – 4776 (1.25×), and
v3 spent 24% more actions than v4 for essentially the same score — so actions and score are only loosely
coupled at this noise level.

Wall-clock is near-constant at ~2 h 22 m, which is the point: **the runs cost the same and produce
different answers.** This is not a throughput or scheduling artifact.

**Two different spans are quoted across these documents; both are correct.** The row above is the
*notebook* wall-clock — the whole kernel, including wheel installs, weight load and vLLM startup. The
`~2 h 12 m` figure used to price quota in the README and in S1-E11/S1-E14 is the *benchmark* span,
`start_time`→`end_time` in `benchmark.json`: v2 2 h 12 m 06 s, v3 2 h 12 m 44 s, v4 2 h 12 m 33 s. The
~10 min difference is setup and teardown. Quote the benchmark span when pricing a run and the notebook
span when pricing a Kaggle session; they are not interchangeable.

## Per game

**Four pairs are now measured, and they disagree by different amounts:**

| pair | changed cleared-level count | identical result |
|---|---:|---:|
| v1 ↔ v2 | **9 / 25 = 36%** | 1 game (`ft09`) |
| v2 ↔ v3 | 5 / 25 = 20% | **0 games** |
| v3 ↔ v4 | 6 / 25 = 24% | **0 games** |
| v2 ↔ v4 | 7 / 25 = 28% | **0 games** |

**The pairwise disagreement rate is 20–36%, centred near 25%.** The 36% first measured was the high end
of the range rather than the typical value, but it remains the conservative number and is the one to
plan against. Note that **no pair among the three logged runs produced a single identical game outcome**
— a lower level-count discordance does not mean the trajectories were closer.

**Across all three logged runs at once, 16 of 25 games (64%) held the same cleared-level count** — so
**9 of 25 (36%) varied somewhere among the three.** No game varied by more than one level. That the
"differs in at least one of three" rate lands on the same 36% as the original pairwise figure is a
coincidence of this sample, not a law; they measure different things.

**v2 ↔ v3 flips:** `ar25` 0→1 · `cd82` 0→1 · `lf52` 1→0 · `m0r0` 0→1 · `s5i5` 0→1. Action counts moved
far more than level counts did on unchanged games — `wa30` 89 → 381 (4.3×), `sk48` 230 → 621 (2.7×),
`bp35` 177 → 496 (2.8×), `tr87` 166 → 55 (0.33×).

**Of the 25 games in v1 ↔ v2, exactly one produced an identical result** (`ft09`: 65 actions, 2 levels).

**9 of 25 games (36%) changed their cleared-level count between v1 and v2:**

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

Note that REPLAY-DET measured the *environment* to be deterministic. Both facts hold: identical action sequences
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

**The direct test now available:** label the v3 episodes with the same protocol as v2 and compare
category frequencies across the two runs. If the ranking is stable, the build order is safe; if it
reorders, the sprint's central output is under-determined and needs replicates. This is a labelling job
on data already on disk. *(v1 cannot take part: it ran with `save_request_logs` at its default `False`,
so it has no reasoning evidence and never will. It contributes to the variance measurement only.)*

**The corpus that supports it exists.** `logs/s1d_corpus_pooled.json` — **75 episodes**, 25 each from
v2, v3 and v4, pooled under S1-E14's configuration-identity rule (all three signatures verified equal).
All 75 are budget-terminated and carry reasoning evidence. This is the corpus size S1-E11 was filed to
obtain, and it puts the pre-registered `blind_rerate.sample_size: 30` at exactly 40% of the corpus.

A detail worth noticing in its shape: the 75 episodes cover **34 distinct (game, level) pairs from 25
games**, because the runs stalled on *different levels*. Only **16 pairs carry all three replicates**;
9 carry two and 9 carry one. The run-to-run variance is visible in the structure of the corpus before
any label is applied — and the comparison must handle the 18 incompletely-replicated pairs explicitly
rather than dropping them, since they are not missing at random: they are the games that varied.

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

- v1: `logs/kaggle-reference/` — kernel `s1b-tufa-duck-reference-measurement` v1, 2026-07-26 07:10 UTC.
  `save_request_logs` at its default `False`; benchmark label `duck-harness-kaggle`. **No reasoning
  evidence**, so it cannot be labelled and contributes to variance only.
- v2: `logs/kaggle_v2/` — same kernel v2, 2026-07-27 11:41 UTC, `save_request_logs = True`, 25 per-game
  request logs (516 MB) — the reasoning evidence v1 lacked. Label `duck-harness-kaggle-logged`.
- v4: `logs/kaggle_v4/` — same kernel v4, ran 2026-07-27 20:14–22:27 (retrieved Jul 28), 486 MB. The deliberate single-pass replicate under
  S1-E14. Verified before use, per the v3 lesson: `n_passes: 1`, 25 game_runs, 25 distinct games, all 25
  ran the full budget (7920.4–7953.1 s), all `gave_up`.
- v3: `logs/kaggle_v3/` — same kernel v3, ran 2026-07-27 17:37–19:50, 588 MB. (An earlier version of
  this line gave "21:58 UTC", which is when the artifacts were *retrieved*, not when the run executed —
  v2's entry above quotes its run start, so the two were not the same quantity.) **Executed source is identical
  to v2** (verified by diffing the notebook Kaggle actually ran: only comments differ) and the
  `HarnessSolver(...)` reprs in the two kernel logs are byte-identical. This run was launched intending
  `n_passes = 3` per S1-E11; the edit was never pushed, so it executed `n_passes = 1` and is a third
  single-pass replicate. **S1-E14 adopts that outcome deliberately** — separate runs bound the
  run-to-run variance S4 actually faces, whereas passes inside one kernel share a session, a server and
  a GPU. Both `run_config.json` files are reconstructed from each run's own log and
  `taaf_setup_env.json`; Kaggle does not emit one.
- statistics: exact binomial sign test, computed inline; per-game comparisons from
  `agent/harness/analyse_reference_run.py` output. Nothing here is a hand-typed number.
