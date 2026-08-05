# E1 store v3 — making the store able to disagree with itself

**2026-08-05. Zero model calls, ~4 min compute.** Follow-up to
[`notes/e2-hidden-state.md`](e2-hidden-state.md), which found a real hidden in-episode action
counter in four games and then found that the evidence store had thrown the evidence away.

## The defect

`Explorer.record()` was reachable only from `test()`, and `test()` pops each candidate from a
state's frontier exactly once. A repeated `(pre, action)` row was therefore **unreachable by
construction**, and every aliasing census over `logs/e1_store_v2` read zero on all 24 games.
That reads as "no hidden state" and actually means "no ability to see any". Routing actions —
which *do* re-execute known edges, and which supplied every conflict the explorer ever caught —
were not recorded at all.

E2 had to reconstruct the missing evidence with a bespoke instrumented rerun and an active
probe. The store should have carried it.

## The fix — three changes, two of them free

1. **`performs.jsonl`** — every action, routing included, with pre/post digests and a `source`
   tag (`boot` / `test` / `walk` / `reset` / `confirm`). Costs nothing; routing was already
   happening (sc25: 46% of the budget) and we were discarding it.
2. **`episode_step` on every row** — the in-episode action count at the pre-state. Without it a
   repeat is uninterpretable: same count tests one thing, different counts test another. Also
   added to `transitions.jsonl` alongside `source`.
3. **`--confirm-budget N`** — an opt-in post-loop pass, **off by default**, that spends N extra
   actions deliberately re-observing already-tested edges **at a different in-episode count**.
   This is the only part that costs actions, and it is the only part that produces aliasing
   evidence on purpose rather than by accident.

Why (3) is needed at all: routing repeats are nearly free and nearly useless on their own,
because RESET + prefix replay reproduces the *same* count the edge was first seen at. It tests
determinism, not aliasing. The only way to get an aliasing observation is to reach the board by
a route of a different **length**, which is what the confirmation pass does — value-first
(edges already known to disagree), then cheapest-route-first, every instance RESET-rooted and
digest-checked before the target action fires.

### Additivity, verified

With `--confirm-budget 0` the trajectory is unchanged. All 24 games re-run and compared against
`logs/e1_store_v2`: **transitions identical on the pre-existing field set, states identical,
graph identical** — with two exceptions, both diagnosed and neither caused by this change:

- **`graph["conflicted"]` differed in ORDER only.** It was serialized straight from a `set` of
  tuples containing strings, so its order followed `PYTHONHASHSEED` and varied between two runs
  of a byte-identical trajectory. The graph file was falsely non-reproducible, and any replay
  gate comparing it would have read a real divergence. **Now sorted** (`suspect` already was).
- **`states.json` has one extra entry on the four games that complete L1** (lf52, lp85, r11l,
  sp80): the completion frame. Current code retains it (`3b17e18`, "the store's one positive
  goal example"); `logs/e1_store_v2` was generated 2026-08-04 14:59, *before* that commit
  landed. **So the store of record predates the code on main and is not reproducible from it.**
  `e2_dose.load_store`'s `post_missing` machinery exists to paper over exactly this. Not fixed
  here — v2 is the floor of record for existing numbers and is left alone — but recorded, and
  E2's earlier "24/24 gates pass" claim was transitions-only and did not compare states.

## What the fixed store sees — `logs/e1_store_v3`

Full run, `--confirm-budget 300` ((w), 10% of the 3000-action main budget).
Census: `logs/e1_store_v3_census.json`, `--stage store_census`.

| | v2 (before) | v3 (after) |
|---|---:|---:|
| games with any repeated `(pre, action)` row | **0** | **14** |
| games with detected aliasing in the transitions log | **0** | **10** |
| aliased groups, total | **0** | **240** |

Per game, aliased groups in the transitions log: cd82 55, ka59 52, dc22 43, m0r0 28, cn04 19,
wa30 15, tr87 12, g50t 8, sc25 7, sk48 1.

**This more than doubles the list of games known to carry hidden state.** E2 found four
(m0r0, cn04, g50t, sc25) and only because routing happened to stumble into them; six more —
cd82, ka59, dc22, wa30, tr87, sk48 — were invisible to the old store and are now first-class
evidence. The counter effect that E2 needed a dedicated probe to establish is now visible in
the store directly: m0r0's origin under ACTION1 gives `a6bba1fd` at count 1 and `b79fe5d1` at
count 0, recorded as two rows with their counts attached.

Cost: 1103 confirmations attempted, **743 landed**, 240 disagreed. Budget spent is 250–300
actions per game, ~8–10% on top of the main run.

### Three honest limits

- **360 of 1103 confirmation routes diverged** — the route did not land on the state it was
  built from. That is the same defect E2 found in `graph["prefix"]`: chained edges recorded at
  different counts do not compose. The divergences are recorded rather than retried, and they
  are evidence in their own right.
- **10 games got zero confirmations, for two different reasons.** Four completed L1 (the pass
  is skipped after a completion). The other six — bp35, ls20, re86, tn36, tu93, vc33 — have
  **no state reachable at two different path lengths at all** within radius 12: their graphs
  are acyclic there, you can never return to a board you have left. That is not a coverage gap
  so much as a fact about those games — if a board cannot be revisited, it cannot be revisited
  at a different count, and this class of aliasing is unobservable *and* irrelevant for them.
- **Same-count disagreements exist and are not non-determinism.** g50t has 4 groups where the
  board and the in-episode count both match and the outcome differs — and each variant is
  highly reproducible (one group holds 33 identical repeats of the minority outcome). That is a
  *further* latent beyond `(board, count)`, and it matches E2's independent finding that g50t
  fails the same-length route control on 5 of 48 probe targets. The census reports the two
  cases separately for exactly this reason.

## Consequences

- `logs/e1_store_v2` stays the floor of record; nothing downstream is invalidated and no
  existing number moves. `logs/e1_store_v3` is the store to build on.
- The claim "20 of 24 games show no aliasing" is dead. It was an artifact of the instrument,
  and the corrected instrument finds hidden state in **10 of 24** with a 300-action probe
  budget — a lower bound, not a census, since six games cannot be probed this way at all.
- E2's half B is unaffected and was not re-run: the counter still buys nothing in the current
  rule model, and knowing it is present in ten games rather than four does not change that.
  What changes is that a future rule model that *wants* this feature can now be trained and
  tested on evidence that contains it.
