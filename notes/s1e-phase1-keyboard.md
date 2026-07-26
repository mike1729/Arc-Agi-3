# S1-e phase 1 — keyboard games, concurrency 2, 2026-07-27

Six keyboard games (no ACTION6 at reset), concurrency 2, 45-minute uniform budget, Qwen3.6-27B MLX
4-bit. All six concluded under S1-E9 — every one ran its full budget (2700.8–2700.9 s), so all are
admissible and all are **right-censored at 2700 s**.

Reference column is the Kaggle run of the unmodified reference at FP8, 132-minute budget.

| game | local actions | local levels | L1 human baseline | local ratio | ref actions | ref levels |
|---|---:|---:|---:|---:|---:|---:|
| `g50t` | 5 | 0 | 78 | 0.06× | 89 | 0 |
| `ls20` | 39 | 0 | 22 | 1.77× | 142 | 0 |
| `re86` | 48 | 0 | 26 | 1.85× | 251 | **2** |
| `tr87` | 7 | 0 | 54 | 0.13× | 85 | 0 |
| `tu93` | **153** | 0 | 19 | **8.05×** | 125 | **1** |
| `wa30` | 28 | 0 | 71 | 0.39× | 255 | 0 |

**Local cleared 0 levels; the reference cleared 3.** Local spent 280 actions against the reference's
947 — 30%, most of which is the 45-minute budget against the reference's 132.

## The finding: the substitution's effect is game-dependent, which is H5's actual question

`ls20` and `tu93` disagree, and both are keyboard games run under identical settings:

- **`ls20`** — local 39 actions, reference 142, neither clears level 1. Local ran at ~80% of the
  reference's actions/minute. Same outcome, same failure, less volume. Here the 4-bit substitution
  looks benign.
- **`tu93`** — the reference **cleared level 1** and then stalled on level 2 having spent only 6
  actions. Local spent **153 actions, all on level 1, and never cleared it** — 8.05× the 19-action
  human baseline. Not slower progress: a different failure mode, high action volume with no
  advancement.

H5 predicts that quantisation and model substitution shift *which* failures dominate, not merely their
magnitude, and its refutation condition is that rankings agree in ordering across models. These two
games alone show the effect is not uniform, so a single game cannot settle H5 in either direction —
which is itself the reason the breadth run exists.

This also corrects a reading I offered from `ls20` alone earlier in the evening ("local tracks the
reference"). It tracks it on `ls20`. It does not on `tu93`.

## Bimodal action volume, and what it means for labelling

The ratios split cleanly rather than spreading: **0.06×, 0.13×, 0.39×** against **1.77×, 1.85×,
8.05×**. Nothing lands between 0.39 and 1.77.

The low group is not "efficient" — no level was cleared, so those games *failed while barely acting*.
`g50t` at 5 actions is the extreme, and its cause is known: a single non-convergent generation ran to
the 16384-token cap producing 49 KB of coherent maze analysis and zero tool calls, consuming an
estimated 15–20 of its 45 minutes.

For S1-d this matters: `g50t` (5 actions) and `tr87` (7) carry almost no behavioural evidence whatever
their reasoning logs hold. An episode can be admissible under S1-E9 and still be too thin to rate on
categories defined over action sequences. That is a distinct axis from admissibility and should be
recorded per episode rather than discovered at labelling time.

## Health

No read timeouts across the phase. One `finish_reason: length` in six games — `g50t`'s non-convergent
generation, analysed separately in `notes/s1-measurements.md` and distinct from the D13 truncation
class. All other generations finished on `tool_calls`.

## Caveats that bound every number above

- **Censored at 2700 s.** The reference's are censored at 7920 s. Action counts are therefore not
  directly comparable; rates and outcomes are.
- **Concurrency 2 vs the reference's 32.** `re86` is being re-run at concurrency 1 in phase 2 as a
  controlled A/B on exactly this, since it showed the largest local/reference gap.
- **Zero levels cleared means the level-band stratification (S1-E2, rank on L2+) has nothing to rank
  on from this phase.** Every episode is L1. If phase 2's click games also clear nothing, the L2+ band
  will be empty and the ranking rule cannot be applied to local data at all — only to the reference
  corpus, which carries no reasoning evidence. That would be a live problem for S1-d, and it is worth
  watching rather than discovering at the end.

---

## The `re86` concurrency A/B — concurrency 2 was not the problem

Run at concurrency 1, same model, same 45-minute budget, same config; concurrency the only variable.
This is the controlled test the earlier concurrency-4 comparison could not be, because that one moved
concurrency and action class together.

| | concurrency 2 | concurrency 1 |
|---|---:|---:|
| actions | **48** | **36** (−25%) |
| generations | 28 | 40 (+43%) |
| actions per generation | 1.71 | **0.90** (−47%) |
| median completion tokens | 520 | 632 |
| max completion tokens | 1850 | 2356 |
| levels cleared | 0 | 0 |

**Concurrency 1 produced fewer actions, not more.** Undividing the accelerator did exactly what it
should to *throughput* — 43% more generations — and the game still went backwards, because each
generation committed roughly half as many actions.

The generations also got longer (median 520 → 632 tokens, max 1850 → 2356). With more compute per
request the model reasons further per turn and commits fewer actions per turn, and the second effect is
larger than the first. Actions are what the score is computed from; generations are not.

**Consequences.**

1. The hypothesis that `re86` suffered from concurrency 2 is **refuted**. Its gap to the reference
   (48 actions and 0 levels against 251 and 2) is not a concurrency artifact.
2. By extension, concurrency 2 is not the reason the other keyboard games underperformed, so the
   phase-1 numbers stand as measured.
3. **This questions the phase-2 design.** All 19 ACTION6 games are scheduled at concurrency 1 on the
   reasoning that long-generation games need the whole accelerator. That reasoning predicted more
   actions and the one measurement available says the opposite — for a keyboard game. Whether it
   transfers to ACTION6 games is untested, and assuming it does would repeat the original error in
   mirror image. Worth an equivalent A/B on one click game before spending 14 h on the assumption.

Recorded as measurement, not acted on: changing phase 2 mid-run is a scheduling decision for the
operator, and the run is producing admissible episodes either way.
