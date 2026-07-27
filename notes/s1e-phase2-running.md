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

## Concluded so far

| game | class | actions | levels |
|---|---|---:|---:|
| `re86` | keyboard (A/B rerun) | 36 | 0 |
| `tn36` | pure-ACTION6 | 4 | 0 |
| `lf52` | mixed | 16 | 0 |

Zero levels cleared in phase 2 so far. The L2+ band is still empty across all local data, so the S1-E2
rank-on-L2+ rule remains inapplicable locally — see the phase-1 note. `lp85` and `vc33`, the two games
that cleared level 1 locally under superseded configs, are both pure-ACTION6 and are still queued.
