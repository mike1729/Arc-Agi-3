# E1 v2 store — the prefix maps do not replay

**2026-08-05. Read-only audit, zero model calls.** Harness
`agent/harness/e1_prefix_audit.py`, results `logs/e1_prefix_audit.json`. Nothing here
re-derives a prefix or writes into `logs/e1_store_v2/`; the repair is a separate task.

## Why this ran

The E2 probe channel's determinism gate ([`notes/e2-probe-channel.md`](e2-probe-channel.md)
§2) sampled three prefixes per iteration game and found dc22 passing 1/3 and m0r0 0/3 —
replaying a state's recorded prefix from RESET lands on a *different grid* than the store
records for that state. Three samples per game is enough to stop a probe run and not
enough to know the scope. This sweeps every state of every game.

**Scope: 14 of 24 stores are affected, 9 of them severely. Pooled, 46.6% of stored states
have an unsound prefix and at most 37.9% are unrecoverable.** The defect reaches well
outside the six iteration games.

## What a prefix is, and why it can be wrong

`e1_explorer.Explorer.observe` records

    prefix[new] = prefix[source] + [action]

a path **composed** from edges observed at different moments in the run — not a path
anyone walked end to end. Composition is sound only if the settled frame identifies the
state. Where it does not, the composed path is a claim the store never tested, and routing
by RESET + prefix lands somewhere else. E1's own `reset_route` *did* validate the routes it
actually walked; the prefix map contains many it never walked.

## Method

For every state, replay its recorded prefix from RESET and record every grid passed
through. Three quantities:

* **verified** — the state's own prefix lands on the grid it claims. These survive any
  verified re-derivation: a **lower bound** on the keep rate.
* **reached** — the state is the endpoint of *some* walked prefix in the sweep, whether or
  not its own. Also sound, and strictly tighter: a state with a wrong prefix may still sit
  on another state's verified path.
* **unreached** — neither. An **upper bound** on the drop rate; a re-derivation that
  searches harder (BFS over verified edges) may recover some of these. **Wrong — corrected
  in the addendum below. `reached` is a ceiling, not a floor, and it is already achieved.**

`verified` decides on **grid equality**, not hash equality, so hashing conventions cannot
affect it.

## Results

| Game | states | verified | reached | drop ≤ | conflicted edges |
|---|---:|---|---|---|---:|
| cd82 | 1474 | 0.0068 | 0.2775 | 0.7225 | 1 |
| m0r0 | 1339 | 0.0097 | 0.2046 | 0.7954 | 3 |
| ka59 | 1943 | 0.0175 | 0.2048 | 0.7952 | 0 |
| dc22 | 1360 | 0.0206 | 0.3375 | 0.6625 | 0 |
| wa30 | 2474 | 0.0344 | 0.1095 | 0.8905 | 0 |
| sc25 | 600 | 0.0367 | 0.1867 | 0.8133 | 3 |
| g50t | 712 | 0.0463 | 0.4340 | 0.5660 | 43 |
| cn04 | 1884 | 0.0488 | 0.1407 | 0.8593 | 4 |
| sk48 | 322 | 0.0528 | 0.4627 | 0.5373 | 0 |
| bp35 | 1954 | 0.6510 | 0.6781 | 0.3219 | 0 |
| sp80 | 498 | 0.7189 | 0.7189 | 0.2811 | 0 |
| tr87 | 2904 | 0.9583 | 0.9683 | 0.0317 | 0 |
| ar25 | 602 | 0.9668 | 0.9668 | 0.0332 | 0 |
| re86 | 2861 | 0.9685 | 0.9738 | 0.0262 | 0 |
| **clean (10)** | 6690 | **1.0000** | 1.0000 | 0 | 0 |

Clean: ft09, lf52, lp85, ls20, r11l, sb26, su15, tn36, tu93, vc33.

**Pooled: 24 games, 27,521 states — verified 0.5339, reached 0.6215, drop upper bound
0.3785.**

**`conflicted` does not predict the defect.** ka59, dc22, wa30 and sk48 all record zero
conflicted edges and all sit below 6% verified. The explorer only marks an edge conflicted
when it happens to re-test it and sees a different outcome; the routing policy re-tests
almost nothing, so the conflict count measures re-test frequency, not aliasing. Any
reasoning that treated an empty `conflicted` list as evidence of a clean state graph — the
E2 digests did exactly this, printing "ALIAS CONFLICTS: none recorded" for dc22 — is
unsupported.

## Three controls: this is not a measurement artifact

1. **Engine reuse.** The sweep replays many prefixes on one engine, as E1 did. If a game
   accumulated latent state across RESET over a long run, late replays would sit in a
   different context than E1's. Measured against a fresh `new_game()` per replay,
   60-state samples (`--stage controls`):

   | | cd82 | ka59 | dc22 | m0r0 | bp35 |
   |---|---|---|---|---|---|
   | shared engine | 0/60 | 1/60 | 0/60 | 0/60 | 43/60 |
   | fresh game | 0/60 | 1/60 | 0/60 | 0/60 | 43/60 |

   Identical. Reuse is not the cause.

2. **RESET.** If RESET did not restore the origin, every prefix would fail from step zero
   for an uninteresting reason. It restores the stored origin in **all 24 games**.

3. **Hashing.** `e1_explorer._hash` keys on `(level, grid)` and `self.level` is assigned 1
   and never mutated, so every stored digest is a level-1 digest and the `reached` set is
   comparable. `verified` compares grids directly and does not depend on this at all.

## The edges are mostly fine; composing them is not

Replaying every single-action edge out of the origin (`--stage origin-edges`):

| Game | origin edges | reproduce | failures |
|---|---:|---:|---|
| cd82 | 19 | 19 | — |
| ka59 | 14 | 14 | — |
| dc22 | 22 | 22 | — |
| sk48 | 21 | 21 | — |
| bp35 | 11 | 11 | — |
| sp80 | 12 | 12 | — |
| m0r0 | 10 | 7 | 1×A1 diverges, 2×A6 replay no-change |
| sc25 | 17 | 13 | A1, A3 no-change; 2×A6 no-change |
| cn04 | 11 | 8 | 2×A6, 1×A1 diverge |
| g50t | 5 | 3 | A1 no-change, A4 diverges |
| wa30 | 5 | 4 | 1×A1 diverges |

So there are **two distinct defects**, and they need different repairs:

* **cd82, ka59, dc22, sk48, bp35, sp80** — every recorded edge out of the origin
  reproduces, yet the store still collapses by depth 2–3. Pure composition failure: the
  edges are real observations, the paths through them are not. Recoverable by
  re-deriving prefixes with verified walks. *(ar25, re86 and tr87 join this class once the
  check runs on every game rather than the 11 sampled here — see the addendum: composition
  9, single-edge 5, clean 10.)*
* **m0r0, sc25, cn04, g50t, wa30** — single edges out of the origin fail on their own.
  Something about the state is not in the settled frame at all, and no amount of
  re-derivation fixes it; these games need the latent variable identified before their
  graphs mean anything. The recurring signature is an action that replays as *no change*
  where the store recorded a change.

## What is and is not affected

**Unaffected — the evidence.** Every row in `*.transitions.jsonl` was actually executed
and observed at the time, with real pre/post grids. Everything mined from transitions
stands: the E0 rows, the E2 dose curves and floors, the miner-vocabulary results, and the
E2 probe channel's already-answered / unreachable-in-store classifications (all transition
lookups). No published number is retracted by this note.

**Affected — anything that navigates.** Reaching a stored state by its recorded prefix is
unsound on 14 games. That is precisely the operation
[`notes/l1-evidence-first.md`](l1-evidence-first.md) relies on when it says deterministic
replay licenses branch-and-deviate probes. The correct statement is narrower:

> REPLAY-DET holds for **re-executing an action sequence that was walked**. It does not
> hold for **reaching a stored state by a prefix the explorer composed**. Only the second
> is what branch-and-deviate needs, and it must be verified per state before use.

The four games that pass the E2 gate (ft09, ls20, tu93, vc33) are all fully verified, so
the probe-channel run of record used only sound prefixes.

## Consequences

1. **Re-running the probe channel on dc22/m0r0 after repair is not worth it.** Their
   verified-reachable sets are at most 33.75% and 20.46% of the stored states, so probe
   preconditions would be evaluated over a much smaller set and *more* arms would land in
   `unreachable-in-store`, not fewer. The 9 gate-blocked probes would mostly return as
   unreachable.
2. **E1 should record prefixes it walked, not prefixes it composed** — or mark the
   difference. A `verified: bool` per state at write time costs one comparison and would
   have made this visible in the store instead of two months later.
3. **A store needs a coverage/soundness header** before a synthesizer reads it. The E2
   digests asserted a clean state graph from an empty `conflicted` list; the list does not
   support that inference.

## Reproduce

```bash
.venv/bin/python agent/harness/e1_prefix_audit.py --jobs 8
.venv/bin/python agent/harness/e1_prefix_audit.py --stage controls
.venv/bin/python agent/harness/e1_prefix_audit.py --stage origin-edges
```

~7 min wall-clock for the sweep (1.29M engine steps), seconds for the controls. No GPU.

---

## Addendum 2026-08-05 — independently replicated, and one claim above is wrong

The re-derivation session (`agent/harness/e1_prefix_verify.py`, branch
`claude/hopeful-ishizaka-3423e1`) wrote its sweep before seeing this one and reports
**identical numbers**: 27,521 states, verified 0.5339, reached 0.6215, the same ten clean
games, the same nine below 6%, per-game rows matching. Two implementations, one conclusion.

### The `unreached` definition above is wrong

It calls `unreached` an upper bound "a re-derivation that searches harder (BFS over
verified edges) may recover some of". It cannot. **Every walked edge's target is already in
`reached` by construction**, so a search over walked edges cannot leave the set `reached`
already describes — `reached` is a **ceiling**, not a floor. The only search with headroom
uses the *store's* edges, which is composition again and has to be walked to be believed.

Measured, 10 (w) routes per game: 5,975 of the 10,418 lost states have a store route, and
**29 of 110 sampled routes land on their state — all 29 in games that were barely broken**
(ar25 10/10, sp80 9/10, bp35 6/10, wa30 4/10 of 13 candidates). **0 of 70 in the nine
sub-6% games**, which hold 5,489 candidate routes between them. Search-based recovery is
worth building for the mild class and returns nothing on the broken class — the two-class
finding again, from a third direction.

The operative half of the recommendation survives: a re-derivation must keep every state
*any* walk reached, not only self-verifying ones. The corrected maps do exactly that and
land on `reached` per game — verified here independently: `logs/e1_store_v2_verified/`
covers dc22 459/1360 (0.3375), m0r0 274/1339 (0.2046), tu93 1202/1202, and a 40-state
sample of the corrected dc22 and m0r0 prefixes replays **40/40** on each.

### The two-class split is confirmed and extended

The origin-edge stage was folded into their verifier and cross-checked against an
independent signal (whether a stored prefix diverges on its *first* action after RESET).
The two signals **agree on all 24 games**. Final classes: **clean 10 · composition 9 ·
single-edge 5**. The composition class is the six named above **plus ar25, re86 and tr87**;
the single-edge class is exactly m0r0, sc25, cn04, g50t, wa30. Of the 8 failing origin
edges, 6 replay as *no change* where the store recorded one.

### A better aliasing signal than `conflicted` exists

Their walks, with no re-test policy at all, found **333 context-dependent edges** (same
grid, same action, two outcomes in different walk contexts) against E1's 54 recorded
`conflicted`: g50t 93, m0r0 59, sk48 59, cd82 37, dc22 25, ka59 25, cn04 17, wa30 11,
sc25 6, re86 1. Replay is a cheaper and far more sensitive aliasing detector than the
explorer's re-testing — this note's §"`conflicted` does not predict the defect" understated
the case by treating the list only as insensitive.

### `conflicted` is also contaminated, not just insensitive

`e1_explorer` has been fixed (`bc1f03a`): `observe` no longer composes, `perform` maintains
a trail of actions since the last RESET, and the composed form is unreachable. On an A/B at
identical games, policy and budgets, prefixes that replay go 489/3422 → 3983/3983 and
**alias conflicts go 1337 → 59**. Because routing *is* RESET + prefix replay, the old
explorer was replaying paths nobody walked and conflicting the edges where those replays
diverged. So a recorded conflict in the current store is often an artifact of the
bookkeeping bug rather than evidence about the game — sc25 654 → 58 and g50t are the clear
cases. Read `conflicted` in `logs/e1_store_v2/` as neither a lower bound nor a clean signal.

**This does not disturb anything measured in this note.** The audit replays the store as it
stands and reports what it finds; the fix changes what a *future* store would look like, not
what this one does.

### Consequence for the E2 probe channel

dc22's corrected map lands at its 0.3375 ceiling and its prefixes replay, and dc22 is in the
composition class — so the condition
[`notes/e2-probe-channel.md`](e2-probe-channel.md) §11 set for re-running its three
gate-blocked probes is now met. m0r0 is not: 0.2046 coverage, single-edge class, and zero of
its sampled store routes walked.
