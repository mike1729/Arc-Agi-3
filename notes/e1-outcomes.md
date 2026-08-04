# E1 — the L1 explorer: outcome distribution

**2026-08-04. Zero model calls.** The measurement `notes/l1-evidence-first.md` defines as E1:
on L1 of each game, `{completed | saturated | closed | closed-unreachable |
saturated-by-budget}` × actions-to-outcome, plus incidental-completion rate. 24 public games
(s5i5 excluded, RS-E5). Budget 3,000 actions or 20 min per game — the action budget binds
everywhere; the wall budget never does (max 73 s).

Code `agent/harness/e1_explorer.py` · outcomes `logs/e1_outcomes.json` (shallowest) and
`logs/e1_outcomes_nearest.json` · store `logs/e1_store/` (22 MB, gitignored).

## Headline

**No game closed. Two of 24 completed. Humans complete all 24, in a median of 13–78 actions.**

| | `nearest` (§3 as written) | `shallowest` (corrected) |
|---|---:|---:|
| completed | **2** | **0** |
| closed | 0 | 0 |
| closed-unreachable | 2 | 2 |
| saturated | 8 | 10 |
| saturated-by-budget | 12 | 12 |
| routing overhead, median | 0.02 | **1.72** |
| test actions, median | 2,784 | 502 |
| unique states, median | 920 | 44 |
| alias conflicts | 634 over 4 games | 117 over 8 games |

Completions: **lp85 at 140 actions** and **m0r0 at 2,418**, both under `nearest` only.

The human reference, from the same corpus (E0's replays, L1 only): **every one of the 24 games
is completed by human players**, median actions-to-completion 13 (vc33) to 78 (g50t), median
across games ≈ 30. So the explorer is not marginally behind competent play on L1 — it fails to
finish 22 of 24 levels that humans finish in about thirty actions, using a hundred times the
budget.

## Two policies, because §3 as written never routes

§3 says "route to the *nearest* frontier state." Implemented literally, the nearest frontier
state is **always the one you are standing on**: you just arrived there by testing a candidate,
it is new, and all of its candidates are untested. Distance 0 always wins. The explorer
therefore never routes — it walks depth-first forever, testing exactly one action per state.
Measured routing overhead 0.02, i.e. 2 routing actions per 100 tests, against a metric the note
introduces specifically to "price deploy-time probing."

`shallowest` is the corrected arm: take the frontier entry at the shallowest state, routing back
to it. That is the ES closure skeleton with routing substituted for exhaustion, and it is what
the routing-overhead metric presupposes. Both arms are reported because the difference is a
result, not an implementation detail.

**The policies disagree about the thing E1 measures.** `nearest` reaches 920 states and
completes 2 games; `shallowest` reaches 44 states and completes none. Depth finds level
completions; breadth does not. Under identical budgets, policy alone flips lp85 from completed
at 140 actions to saturated at 243 with 277 frontier entries still untested.

That is the first real design finding: **incidental completion is a property of depth, and
thorough local coverage actively suppresses it.** An explorer built for evidence quality gets
fewer completions than one built badly.

## Saturation fires early, and it fires on games that were winnable

`saturated` (10 games under `shallowest`) means novelty fell below 0.02 over a 200-test window
while the frontier was still non-empty. lp85 is the clean case: it saturates at 243 actions,
and the same game under the other policy completes at 140. Saturation is not detecting that
there is nothing left to learn; it is detecting that the *local neighbourhood* has stopped
yielding, which is exactly what breadth-first coverage guarantees will happen.

12 further games never saturate at all — they exhaust the 3,000-action budget first.
**`closed` was never reached by any game under either policy**, and cannot be: the frontier
grows by ~100 candidates per newly discovered state, so it outruns testing by two orders of
magnitude. Under `nearest`, bp35 ends with 238,337 untested frontier entries.

## What replicates across policies

**g50t and sc25 are `closed-unreachable` in both arms.** Frontier non-empty, no entry routable
even in suspect mode. Both have the corpus's heaviest alias-conflict counts (g50t 224 and sc25
394 under `nearest`), so the routing graph is being shredded by hash under-identification
rather than by a structural wall. That is a genuine per-game property, not a policy artifact.

**Alias conflicts are real and concentrated.** 634 conflicts over 4 games (`nearest`), 117 over
8 (`shallowest`). Under REPLAY-DET these cannot be stochasticity, so each one is a settled-frame
hash that under-identifies the true state — free Alias-family evidence, as the note predicted,
and the first direct measurement of hidden state in these games. No `reset_not_origin` anomaly
fired in either arm: RESET returned to the origin state everywhere, so the m0r0
`reset_level_restore` behaviour E0 found in the recordings did not recur under engine control.

## Deviation — the novelty signal, and why

The note defines novelty on "the `changed`-signature layer". In E0's vocabulary
(`rs_e0.abstract`) `changed` is `(bool(effect),)` — **two values**. Measured: 15 games produced
exactly 2 distinct `changed` signatures over the whole run and 9 produced 1. A novelty counter
on that layer saturates after roughly two actions.

Novelty here is therefore **a new state hash OR a new `moveset` signature** — `moveset` being
`{(kind, colour)}`, which is what the note's gloss "which objects react, to what" actually
describes. Both component counts are in the output. Moveset signatures per game range 3 (g50t,
lp85) to 40 (r11l).

## Limits

- **Two policies, one seed, no repeats.** Nothing here has a variance estimate.
- The 3,000-action and 200/0.02 saturation parameters are the note's working defaults, carried
  unchanged. The saturation finding above is partly a finding about that threshold.
- `nearest`'s two completions are n=2. The claim "depth completes, breadth does not" rests on
  them plus the lp85 within-game flip.
- The store was written from the `shallowest` arm only — the arm with **fewer** test actions
  (median 502 vs 2,784). If E2's dose curve wants volume, it should be rebuilt from `nearest`,
  or from a policy that is neither.
- No L2 play, per the note's scope. Nothing here says whether a model mined from this store
  clears anything.

## What this hands to E2

`logs/e1_store/<game>.{states.json,transitions.jsonl,graph.json}` — settled grids by hash,
transitions with effect signatures and route provenance, and the state graph with its conflict
and suspect sets. Schema-aligned with `rs_transitions` so the E0 miner runs over it unchanged.

The uncomfortable input to E2 is the volume: median 502 transitions per game from the stored
arm, against 137–641 human L1 transitions per game in E0. The explorer produces **about as much
evidence as the human replays already sitting on disk**, and worse evidence in one specific
respect — humans reach the completion, so their traces contain the positive goal example that
22 of these 24 runs never saw.

## v2 rerun (2026-08-04, same day — policy per the design note's v2 section)

Code `e1_explorer.py --policy v2` (now the default) · outcomes `logs/e1_outcomes_v2.json` ·
store `logs/e1_store_v2/` (268 MB, gitignored, single-disk).

| | v1 `nearest` | v1 `shallowest` | **v2** |
|---|---:|---:|---:|
| completed | 2 | 0 | **4** |
| closed-unreachable | 2 | 2 | **0** |
| saturated | 8 | 10 | 3 |
| saturated-by-budget | 12 | 12 | 17 |
| routing overhead, median | 0.02 | 1.72 | **0.02** |
| test actions, median | 2,784 | 502 | **2,920** |
| unique states, median | 920 | 44 | **969** |

Completions: **lp85 43 · r11l 135 · lf52 149 · sp80 1106** — twice v1's best arm, and lp85
lands inside the human 13–78 band. r11l completed **without the lattice** (tier 1 holds no
lattice points and tier 2 never materialized there): the human completions needed lattice
clicks, the explorer found a different path — reachability and point-imitation come apart in
both directions.

What the three v2 mechanisms did:

- **Advance-first + rotation** delivers depth at breadth prices: routing overhead median 0.02
  (v1's corrected arm paid 1.72), test-action share ≈ 97%, stored volume median 2,920/game —
  5–20× the human corpus. The v1 volume critique was an artifact of storing the thin arm, as
  suspected.
- **Walk mode replaces the false abort.** g50t never even needed it — with conflicted edges
  quarantined per-edge and targets rotated by failed attempts, clean routing survived 43
  distinct conflicted edges (654 conflict *events*; the gap is walk()-traversal re-counting,
  both numbers now reported). sc25 entered walk mode at action 1,979. Both ran to budget with
  full stores instead of aborting as `closed-unreachable`; that outcome now occurs zero times.
- **The tier machinery fired exactly once and worked**: ft09 closed tier 1 at action 18 (its
  initial reach is 9 states), materialized tier 2 (duplicates + lattice) for those states, and
  then saturated honestly at 1,401. Everywhere else `closed-t1` was never reached — even a
  ~27/state frontier outruns 3,000 actions when discovery keeps paying.

The structural finding the rerun adds: **state-hash novelty is inexhaustible in roughly half
the corpus.** 17 of 24 games end the budget with window novelty 0.14–0.98 (re86 and tr87 at
0.98 discover a new state on essentially every test action — 2,861 and 2,904 states). Only
ft09/su15/vc33 saturate. Whether those state floods carry rule information or are hash churn
(counters, animation residue) is exactly what E2's dose curve reads off this store.

Limits: single run per game, same working thresholds as v1 (window 200 / 0.02 / budget
3,000), completions n=4. The v1 arms were not re-run; their rows are the 2026-08-04 morning
measurements.
