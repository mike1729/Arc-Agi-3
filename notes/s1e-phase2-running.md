# S1-e phase 2 — concurrency 1, running notes (2026-07-27)

Live log, updated as games conclude. Summary written when the phase completes.

## The keyboard/click split used all evening is too coarse

I have been treating games as keyboard (no ACTION6) versus click (ACTION6 present). The measured
`actions_at_reset` supports a three-way split, and the middle group was being mislabelled:

| class | n | definition | can batch simple actions? |
|---|---:|---|---|
| keyboard | 6 | no ACTION6 | yes |
| **mixed** | **12** | ACTION6 **and** simple actions | **yes** |
| pure-ACTION6 | 7 | only ACTION6 (`[6]`, or `[6,7]`) | no |

Pure-ACTION6: `ft09`, `lp85`, `r11l`, `s5i5`, `su15`, `tn36`, `vc33`.

The distinction is mechanical. The agent commits actions by calling `action(actions=[...])`, so a game
exposing simple actions can commit several per generation. A pure-ACTION6 game must reason out a
coordinate for every action, which is why its actions-per-generation is an order of magnitude lower.
This is what separated `cn04` (mixed, batching freely) from `tn36` (pure, 0.12 actions/generation) in
the same phase under identical settings.

**What this does NOT explain.** Class does not predict action volume. Phase-1 keyboard games alone span
5 to 153 actions:

```
g50t 5   tr87 7   wa30 28   re86 36/48   ls20 39   tu93 153
```

So batching capability is a real structural property and a real driver of actions-per-generation, but it
is not the dominant term in how many actions a game actually produces. `g50t` could batch and managed 5.
Anything that treats the class as a predictor of volume is over-reading it — including my own earlier
framing that click games under-produce *because* they are click games.

Consequence for scheduling: the earlier phase split put 19 games in one bucket on a binary that merges
12 batching games with 7 non-batching ones. If concurrency is ever revisited, the three-way split is the
one to reason about.

## Action density by class, at concurrency 1 (8 games)

| class | n | median generations | median actions/gen |
|---|---:|---:|---:|
| keyboard | 1 | 40 | **0.90** |
| mixed | 4 | 50 | **0.62** |
| pure-ACTION6 | 3 | 33 | **0.18** |

The ordering is clean and it is the batching mechanism, not compute: mixed games obtain the MOST
generations of any class (median 50 in 45 minutes) and still convert them at 0.62 actions each, while
pure-ACTION6 games get the fewest generations and convert at 0.18. Per-generation conversion, not
generation throughput, is what separates the classes.

## The concurrency question, with the numbers I have

The only direct A/B is `re86`: **48 actions at concurrency 2 versus 36 at concurrency 1**, despite 43%
more generations at concurrency 1. Concurrency 2 is better on *both* axes for that game — more actions
per game, and two games running at once, so roughly double the throughput per wall-clock hour.

Extrapolating that to mixed and pure-ACTION6 games is **not** supported by measurement, and assuming it
transfers is the same inference error that produced the original concurrency-4 confound. What can be
said:

- generation throughput at concurrency 1 is not the binding constraint for any class — mixed games
  already get 50 generations per 45 minutes and still produce few actions
- so the mechanism by which concurrency 1 was supposed to help (more compute per request → more
  progress) is the one the `re86` A/B measured and found inverted

**A decisive test costs 45 minutes.** Re-run one mixed game (`lf52`, 16 actions at concurrency 1) and
one pure-ACTION6 game (`tn36`, 4 actions) together at concurrency 2. That pairs both untested classes
against their own concurrency-1 results in a single chunk. Duplicate (game, level) episodes are handled
by explicit selection in `s1d_build_corpus.py`, so re-running does not corrupt the corpus.

If concurrency 2 wins, the remaining games halve in wall-clock.

## Concluded so far

| game | class | actions | levels |
|---|---|---:|---:|
| `re86` | keyboard (A/B rerun) | 36 | 0 |
| `tn36` | pure-ACTION6 | 4 | 0 |
| `lf52` | mixed | 16 | 0 |

Zero levels cleared in phase 2 so far. The L2+ band is still empty across all local data, so the S1-E2
rank-on-L2+ rule remains inapplicable locally — see the phase-1 note. `lp85` and `vc33`, the two games
that cleared level 1 locally under superseded configs, are both pure-ACTION6 and are still queued.
