# Miner vocabulary v2 — results

**2026-08-04. Zero model calls.** Executes `notes/miner-vocab-v2.md`. Code
`agent/harness/miner_vocab_v2.py` (arms + regression) · `rs_transitions.py` (mechanism 1) ·
`rs_e0.py` (mechanism 2). Data `logs/miner_vocab_v2.json` · `logs/e2_dose_vocab_v2.json` ·
`logs/e2_dose_scoped.json`. 24 games × 2 vocabularies × 2 modes × 4 scopes.

## Verdicts

| mechanism | verdict |
|---|---|
| 1 — `clicked_adjacent_to:C` | **ADOPTED.** Zero losses anywhere, small gains in a few games, and it moves 217 L1→L2 failures out of the census bucket. Now the default vocabulary |
| 2 — census-scoped firing, effect-local | **REJECTED as specified.** Buys +0.015 accuracy-over-covered for 73% of coverage |
| 2 — census-scoped firing, full constancy | **REJECTED.** Predicted collapse, confirmed and total: coverage 0.000 in 24/24 games, both modes |
| 2 — `present:`-only scope *(post hoc)* | **not adopted; pre-register next.** The variant the abstention causes point at |

`--vocab v1` still reproduces `logs/e0_row_m_all.json` **exactly** — asserted by
`miner_vocab_v2.py --regress`, 144 scored splits, not assumed. Adding a guard feature touches
tier-1 selection, failure classification and separator ordering, so the v1 baseline the v2
deltas are measured against had to be shown unmoved.

## Mechanism 1 — the missing word, measured

The E2 slice's one keepable output was Qwen naming a feature the vocabulary lacks. Built as
specified: for an in-bounds ACTION6, K is the 4-connected same-colour component under the
click (background-coloured K is legitimate), and `clicked_adjacent_to:C` is True iff any cell
of K touches a cell of colour C. Code-only — guards are recomputed at load time, so no store
regenerates and E1 does not rerun.

**On the headline it does nothing.** Human replays, L1→L2, median delta **0.0000**, **24/24
ties**, both modes, both accuracy and coverage. Not one game's transfer accuracy moves.

Where it does move something:

| measurement | v1 → v2 |
|---|---|
| ft09 held-out L1 (within-L1) | 0.845 → **0.8918**, both modes — the game Qwen named |
| sb26 rules mined at L1 | 12 → 13 |
| tier-1 selections, human L1 | 2 of 60 rules, 1 game (sb26) |
| tier-1 selections, **explorer store** | **8 of 23 rules, 4 games** (ft09, lf52, lp85, sb26) |
| explorer-store floor, on-human-L1 | ft09 0.2522 → **0.3017**; sb26 0.5308 → 0.5330 |
| explorer-store floor, on-human-L2 | lf52 0.2011 → 0.2050; lp85 moveset 0.2396 → 0.2505 |

The explorer/human asymmetry is the interesting part: the new feature is selected in **35% of
explorer-store tier-1 rules and 3% of human-replay ones**. The explorer clicks far more
indiscriminately than a human does, so its evidence actually varies the thing the feature
measures. A feature can be dead on human replays and live on the evidence the deployed agent
will actually have.

**Its real effect is on the failure typing.** Nine games reclassify:

| game | v1 fixable / census / unpred | v2 |
|---|---|---|
| tn36 | 21 / 109 / 0 | **82 / 48 / 0** |
| sb26 | 0 / 206 / 0 | **61 / 145 / 0** |
| lf52 | 7 / 211 / 102 | **56 / 169 / 95** |
| r11l | 0 / 214 / 0 | **27 / 187 / 0** |
| cn04 | 35 / 561 / 246 | **73 / 549 / 220** |
| bp35, lp85, m0r0, vc33 | smaller shifts | |
| **total census** | **8588** | **8371** (−2.5%) |

That matters more than the accuracy tie: `guard_fixable` means a repair policy has something
to grab. 217 failures previously typed as "different object census" or "no repair exists"
are now typed as a mechanical precondition on the clicked object.

### Below tier 1's bar — where the feature is strongest and still discarded

Tier 1 selects a feature only if it resolves a key **completely**, so `rules mined` cannot
tell "carries no signal" from "carries more signal than anything else and still falls short".
`key_purity` (new, reported never mined on) measures the latter: the fraction of a key's
transitions landing in a single-effect cell.

Of **175 unresolved keys**, `clicked_adjacent_to:*` is the single best partition feature on
**13** and has non-zero purity on **29**. Median best purity across all features and all
unresolved keys is 0.125.

| game | key | n | best new feature | purity | best overall |
|---|---|---:|---|---:|---:|
| sb26 | A6:0 | 10 | `clicked_adjacent_to:14` | **1.000** | 1.000 |
| ft09 | A6:8 | 70 | `clicked_adjacent_to:4` | **0.643** | 0.643 |
| vc33 | A6:3 | 12 | `clicked_adjacent_to:9` | 0.417 | 1.000 |
| vc33 | A6:0 | 22 | `clicked_adjacent_to:4` | 0.409 | 1.000 |
| r11l | A6:15 | 25 | `clicked_adjacent_to:0` | 0.320 | 0.320 |

ft09's `A6:8` is the case: the new feature is the **best guard in the entire vocabulary** for
that key and tier 1 discards it, because 0.643 is not 1.000.

**And it does not resolve the key it was named for.** Qwen's ft09 diagnosis was about
colour-9 clicks and a colour-12 object. On `A6:9` (n=139, 4 distinct effects) the best feature
is `count:9` at 0.424 purity; `clicked_adjacent_to:5`/`:4` reach 0.122, and every `adj:12:*`
scores 0.000. ft09's unresolved key set is `{A:0, A:4, A6:8, A6:9}` under **both**
vocabularies. The model named a real gap and pointed at the wrong key.

## Mechanism 2 — census-scoped firing

Every census feature constant across a rule's supporters becomes an applicability condition;
outside it the rule **abstains** rather than firing. Medians over 24 games, L1→L2:

| mode | scope | acc_all | acc_covered | coverage | census bucket | abstentions |
|---|---|---:|---:|---:|---:|---:|
| full | none (v1) | 0.1638 | 0.1984 | 0.9739 | 8588 | 282 |
| full | effect_local | 0.0280 | 0.2540 | **0.2423** | 2049 | 14100 |
| full | present_only *(post hoc)* | 0.1437 | 0.2504 | 0.8970 | 7556 | 3939 |
| full | full constancy | 0.0000 | 0.3084 | **0.0000** | 0 | 22113 |
| moveset | none (v1) | 0.1910 | 0.2373 | 0.9739 | 6262 | 271 |
| moveset | effect_local | 0.0157 | 0.4057 | 0.1521 | 1629 | 14534 |
| moveset | present_only *(post hoc)* | 0.1874 | 0.3627 | 0.8958 | 4921 | 4745 |
| moveset | full constancy | 0.0000 | 0.3870 | 0.0000 | 0 | 21931 |

**The mechanism works exactly as designed and the price is not worth paying.** Effect-local
drains the census bucket by 76% (8588 → 2049) and lifts accuracy-over-covered on 14 of 18
comparable games — the surviving predictions really are better. It costs 73 points of
coverage. lp85 is the extreme: census 2918 → **0**, at 3216 abstentions on 3218 L2
transitions. tn36 goes from 0.839 accuracy to 0.000 by abstaining on all 859.

**Full constancy collapses to zero coverage in every game and both modes**, as the note
predicted. That arm was included to show the collapse and it did; it is not a result about
games, it is a result about how little varies inside one level's evidence.

The explorer store separates the two failure modes cleanly: under effect-local scoping, the
**on-human-L1** coverage barely moves (median −0.046) while **on-human-L2** collapses (median
−0.780). Scoping is nearly free within distribution and fatal across a level change — which
is precisely the transfer it was proposed to improve.

### Why it collapses — measured, not guessed

The abstention causes say it in one line: abstentions are overwhelmingly caused by `count:`
**alone**, never by `present:`.

| game | abstentions | count only | count + present | present only |
|---|---:|---:|---:|---:|
| cd82 | 143 | **143** | 0 | 0 |
| bp35 | 637 | **610** | 27 | 0 |
| dc22 | 934 | **834** | 100 | 0 |
| cn04 | 721 | **674** | 47 | 0 |
| ar25 | 596 | **542** | 54 | 0 |

`count:C` demands the exact same *number* of objects of a colour; `present:C` merely demands
the colour exist. L2 almost always changes some count. So the collapse is not about census
scoping — it is about **exact-count equality**.

The post-hoc `present_only` arm isolates that and behaves like a mechanism one would actually
deploy: coverage 0.974 → 0.897 (−0.044 median), accuracy-over-all essentially flat (median
delta **0.0000**, 19 ties / 5 small losses), accuracy-over-covered up on **18 of 24 games and
down on 1** — on the transferable `moveset` layer, 0.2373 → 0.3627.

**Not adopted.** It was generated by this run's own diagnosis, and adopting a variant on the
strength of the pass that suggested it is the failure mode this project has already named
once (tu93's 97.8% rule in `notes/e2-slice.md`). It is the candidate to **pre-register before
the next pass**, with its threshold and target fixed in advance.

## What changed in the repo

- `rs_transitions.guard_features` emits `clicked_adjacent_to:C`; `vocab()` defaults to **v2**.
  `set_vocab` mirrors into the environment because `e2_dose` spawns workers.
- `rs_e0` gains `scope` (`none` default), rule abstention in `_fire`, `abstain_causes`,
  `key_purity`, `guard_families`, and `clicked_adjacent_to` in the mechanical-repair family.
- `e2_slice` admits `clicked_adjacent_to:` proposals and names the feature in the prompt's
  vocabulary — the slice can now represent the rule it asked for. **Not rerun.**
- **Floor file of record moves to `logs/e2_dose_vocab_v2.json`.** `logs/e2_dose.json` is
  retained as the v1 measurement and is reproducible with `--vocab v1`. Dated addendum in
  `notes/e2-dose.md`.

## Limits

- One corpus, one split, no variance estimate. The v2 gains are small enough that a different
  session split could plausibly erase ft09's within-L1 +0.047; the *zero-loss* property is
  the more robust half of the claim.
- `key_purity` is reported, not mined on. Lowering tier 1's all-or-nothing bar is a rule-model
  change and is out of scope here — but it is now the obvious question, and it is a bigger
  lever than either mechanism measured: on 175 unresolved keys the best available feature has
  median purity 0.125, so most keys are not one feature away from resolution in any case.
- The census-scope arms are kept in the code despite rejection. The rejection is a measured
  result a later design will revisit, not a dead end.
