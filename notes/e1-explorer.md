# E1 — the L1 explorer: design (exploratory)

> **RUN 2026-08-04 — `notes/e1-outcomes.md`.** Built and run over all 24 games.
> **No game closed; 2 of 24 completed; humans complete all 24 in a median of 13–78 actions.**
> §3's `nearest` routing **never routes** (the state you stand on always has untested
> candidates, so distance 0 always wins) — measured overhead 0.02. A corrected `shallowest`
> arm is reported alongside; the two disagree about the outcome distribution, and depth, not
> coverage, is what produces incidental completions. §4's novelty signal is degenerate as
> written: E0's `changed` layer is `(bool(effect),)` and yields ≤2 values per game, measured.
> The paragraphs below are the design as drafted; read the result note before building on them.
>
> **v2 RERUN same day (spec: "v2 — the rerun" below; result: `notes/e1-outcomes.md` §v2):**
> 4 of 24 completed (lp85 at 43 actions), `closed-unreachable` eliminated, overhead 0.02,
> stored volume median 2,920 test actions/game. The v2 store (`logs/e1_store_v2/`) is the one
> E2 consumes.

**Status: design draft 2026-08-04, lean mode. Working numbers are labelled (w).**
Consumes nothing from Qwen. Produces the evidence stores E2 synthesizes over.

## v2 — the rerun (2026-08-04, after `notes/e1-outcomes.md`)

The run refutes three mechanisms. v2 changes exactly those, keeps the measurement definition,
and re-runs once as a single arm.

1. **The frontier holds tier 1 only: advertised actions + one representative per
   (colour, shape) class** — ≤22 classes measured corpus-wide, so ~27 entries/state against
   v1's ~160. v1's frontier grew ~100 entries per discovered state; testing can never catch up
   (bp35 ended with 238,337 untested; `closed` was unreachable *by construction*). E0's rules
   are class-level, so tier 1 is the information-bearing set. Duplicates + lattice become an
   **on-demand tier 2**: enumerated at a state only when tier 1 is closed there with budget
   remaining, or when a later M-phase directive asks. `closed` splits: **closed-t1** (every
   tier-1 candidate at every reachable state tested) is the achievable milestone and the
   reported one; full closure is not claimed. E1-pre's duplicate/lattice reachability results
   concern *completion-path* clicks — X-phase's job under a goal hypothesis, not blind
   coverage's.
2. **The accidental DFS is adopted deliberately, minus its skew.** Measured, depth wins every
   axis E1 scores: `nearest` 920 states / both completions / overhead 0.02, `shallowest` 44 /
   none / 1.72, and lp85 flips completed→saturated on policy alone. v2 keeps advance-first —
   test where you stand, follow any transition into a *new* state immediately, leave the rest
   on the frontier — and fixes the one-rule-sampler skew: candidate order at each state starts
   at index `state-hash mod n` (deterministic rotation), so class coverage spreads across
   states instead of over-testing the priority-1 candidate everywhere. On local dead-end,
   route to the nearest tier-1 frontier entry, tie-break **deepest** — v1 said shallowest;
   the depth finding reverses it.
3. **`closed-unreachable` requires a conflict-free graph.** g50t/sc25 were declared
   unreachable in both arms while carrying the corpus's heaviest alias-conflict counts
   (394, 224) — the routing graph was shredded by hash under-identification, not by walls.
   v2, parameter-free: frontier unreachable *and* any alias conflicts recorded → drop to
   **walk mode** (continue-from-current-state novelty-greedy, the same fallback already
   specified for REPLAY-DET falsification; the graph keeps recording as M-phase evidence).
   `closed-unreachable` then means unreachable on a graph with no known identity failures.
4. **Novelty = new state hash OR new `moveset` signature**, adopting the run's substitution as
   the definition — the `changed` layer is `(bool(effect),)`, ≤2 values per game measured,
   dead as a signal. Window/threshold stay working numbers; the early-saturation finding is
   partly about them, and the advance-first stream differs — re-read at bring-up.
5. **The store is rebuilt from the single v2 arm.** The "no more evidence than replays"
   reading is an artifact of storing the thin arm (502 median test actions; `nearest` already
   produced 2,784). Public-game volume is moot — replays exist; the number that matters is
   what a hidden game gets from one explorer run, and that is what v2's store measures.

Stands without rerunning: the human reference (all 24 L1s completed, median 13–78 actions) ·
alias concentration on g50t/sc25 · the depth-vs-coverage finding itself · RESET behaving under
engine control. Line-level, unchanged by v2: **22/24 uncompleted at ~100× human budget is the
measured size of the gap M-phase exists to close** — E2's goal-candidate question is now the
gating question of the line.

## What E0's first row changes in this design

From `logs/e0_row_m_all.json` / `e0_row_c_all.json` (24 public games, human replays; full run
2026-08-04):

- **Transfer is layered.** The `changed` layer (which objects react, to what) survives L1→L2 at
  **median 0.985, min 0.762** accuracy-over-covered across 24 games. Exact-effect (`full`)
  prediction does not (median ≈ 0.2, floor 0.0), and its failures are typed: guard-fixable
  dominates ~8 games (tr87 all 848, dc22 884, ka59 695), **census-separable is the largest
  bucket overall** (~10 games: lp85 2918, g50t 1324, sk48 1222), genuinely-novel effects
  concentrate in a minority (m0r0, wa30, sk48-mixed). → **Novelty for the explorer is defined
  on the `changed`-signature layer**, not on exact outcomes: chasing exact-effect novelty means
  chasing a tail that partly doesn't transfer and partly doesn't stabilize even within L1.
- The two weakest `changed`-transfer games (sb26 0.762, ar25 0.776) include a known
  animation-frame game — **settled-frame handling is load-bearing**, not hygiene.
- **Goal grammar is inexpressible for 14/24 games** (row C) — the explorer must not assume the
  goal is recognizable in-flight; incidental completion and completion-event capture are the
  only goal obligations E1 carries. Where the grammar *does* express the goal, within-L1
  survival is 1.0 everywhere and L1→L2 survival is 0.86–1.0 for 8 of 10 games — but **tn36
  (0.5) and tr87 (0.0) show goal templates can be falsified at L2**, so the X phase re-verifies
  the goal template on level entry before committing to it.
- **`reset_level_restore` anomaly (m0r0)** — RESET semantics must be verified per game during
  bring-up, not assumed; the explorer leans on RESET for frontier routing.

## Loop

Skeleton = the ES closure engine (archive: `agent/harness/es_sources/domain_closure.py` — live
arcengine expansion, exact hashing, budgets, ran to 242k states) with three substitutions:
candidate-reduced actions, frontier *routing* instead of breadth-first exhaustion, and
saturation detection. **Step zero of the build: audit the resurrected code for
`copy.deepcopy` engine forking** — unfaithful on tn36 (E1-pre). The explorer itself is immune
by construction (routing is RESET + prefix replay, never engine forking), but any inherited
fork machinery is not.

1. **State identity**: settled-frame exact hash, keyed with level (animation settling per the
   known multi-frame trap). Same (hash, action) → different settled outcome is an **alias
   conflict**, and by REPLAY-DET it is never stochasticity — it means the hash under-identifies
   the true state. In-run policy: (a) re-check settling once (longer settle) before believing
   it; (b) confirmed → the **node is alias-suspect, not just the edge**: all its outbound edges
   leave the routing graph (a degenerate hash is degenerate for every action from it), and the
   conflicted edge stops being retested after 3 (w) attempts; (c) a suspect node's untested
   candidates stay testable **opportunistically** — only when the explorer is already standing
   there — and transitions recorded from suspect nodes carry a provenance tag so the miner can
   condition on prefix. Taint is *not* propagated recursively downstream (that amputates the
   graph on one global hidden bit); downstream unreliability is caught behaviorally by
   step-validated routing instead. Disambiguating the hidden variable is M-phase work; E1
   reports per-game conflict counts — free Alias-family evidence.
2. **Action candidates per state**: advertised ACTION1–5 (+7 where advertised) plus clicks from
   segmentation — one per node (centroid; top-left fallback), children included; segmentation
   tier capped at 64 (w)/state. Culling is a **deterministic pipeline, never a plain size
   sort**: (i) the largest node always (the background/canvas — placement games click *there*;
   size-ascending culls evict it first, exactly backwards); (ii) one representative per
   distinct (color, shape-hash) class, classes admitted in a fixed order — total class area
   desc → member count desc → color index asc → shape-hash lex (w) — so >64 classes evict
   reproducibly; (iii) remaining slots fill smallest-first among duplicates, same tie-breakers.
   E1-pre's recall numbers arbitrate the sort key, not intuition. **Lattice, when E1-pre
   triggers it for a game, is a second tier, not a merge**: up to 64 (w) 8×8 points, deduped
   against segmentation-candidate cells, enumerated with strictly lower test priority — the
   per-tier caps keep object-level candidates intact and the frontier bounded. Full 64×64
   click alphabet is what blew up ES closure; never enumerate it. **Gate: E1-pre runs before
   the explorer does.**

   **MEASURED 2026-08-04 — `notes/e1-pre-recall.md`. Three of this paragraph's values change.**
   Segmentation tier **64 → 96** (64 loses completion-path clicks on ft09). Duplicate fill
   **smallest-first → largest-first**: smallest-first spends the whole leftover budget on
   single-cell dust and costs bp35 0.610 vs 0.986 node recall; nothing is made worse by the
   change. The lattice is **adopted for every game, not triggered per game** — r11l has 2 of 10
   L1 completions reachable only through it. Class admission order (ii) is untested and
   unreachable: distinct (colour, shape) classes never exceed 22 per state in the corpus, so the
   cap only ever binds on duplicates — the order stays as written purely as the determinism
   guarantee for hidden games, which carry no measured class bound. A blanket
   minimum-node-size filter was measured and REJECTED (breaks six games whose humans click
   single pixels).
3. **Frontier policy**: frontier = (state, untested candidate) pairs. Route to the *nearest*
   frontier state: shortest known-graph path over never-conflicted, non-suspect edges from the
   current state, else RESET + replay prefix (deterministic — REPLAY-DET). Tie-break
   shallowest. Prefix replays count against the budget but are **excluded from novelty
   accounting**. On route divergence the edge where observed ≠ expected is marked conflicted
   (attribution may be downstream of the causal edge — acceptable: it removes an
   in-context-unreliable edge either way), so every abort **monotonically shrinks the routable
   graph** — re-planning cannot loop forever. After each new conflict, recompute frontier
   reachability; entries unreachable via clean edges move to a **deferred frontier**, not out
   of the episode. When the clean frontier empties with budget remaining, the router enters
   **suspect mode**: best-effort routes over suspect/conflicted edges, step-validated as
   always, 3 (w) attempts per deferred entry — a suspect bottleneck (door with hidden state)
   must be pushed on, not surrendered to. `closed-unreachable` is declared only when deferred
   entries are unreachable *even via suspect edges* or their attempts are exhausted — it means
   structurally blocked, never merely quarantined. **Divergence on a full RESET-prefix replay
   is a first-class anomaly** — it falsifies REPLAY-DET's determinism for that game (measured
   on only 2 games); report it and drop to continue-from-current-state exploration for that
   game.
4. **Saturation** (definitional, not bolted on): sliding window of 200 (w) **frontier test
   actions** — routing/prefix actions are excluded from the window, or deep graphs would drag
   novelty to zero and fake saturation. Novelty = new `changed`-signatures + new state hashes
   per test action; saturated when novelty < 0.02 (w) over the window while the frontier is
   nonempty; **closed** when the frontier is empty; **closed-unreachable** when the frontier is
   nonempty but every entry is routing-unreachable (coverage incomplete for a structural
   reason — a distinct result, not exhaustion); **completed** on the engine's level-advance
   signal. The **routing-overhead ratio** (routing actions / test actions) is reported per
   game — it prices deploy-time probing and bounds explorer productivity as the graph deepens.
5. **Budgets**: per game 3,000 (w) actions or 20 (w) min wall-clock, whichever first — budget
   exhaustion is reported as saturated-by-budget, distinctly. Bring-up sets per-game working
   budgets from E1-pre's **measured** branching factor (median 7–89 candidates/state + 64
   lattice), not from the cap.
6. **On completion**: record the completing transition + pre-state prominently (the one
   positive goal example), stop. L2 is out of scope for E1.

## Store (the actual product)

Append-only, schema aligned with `rs_transitions.py` so the E0 miner runs on explorer evidence
unchanged: settled before/after frames, action, engine flags, level, timing; state graph
(hashes, edges, test status); segmentation cache; outcome record. This makes E2's dose curve =
E0-miner-on-E1-store at increasing prefixes, and makes human-replay-mined vs explorer-mined
rules directly comparable.

**Provenance is split between facts and judgments.** Transition rows carry only raw facts —
origin state hash, full action-prefix hash since last RESET, step index, route mode
(clean/suspect/opportunistic), settle-retry count. Alias-suspect status is a *graph judgment
that changes mid-run* (a node looks clean until its first conflict), so it is never baked into
rows: a versioned sidecar (`suspect set + conflict records with step indices`) is derived from
the graph, and consumers **join at read time**. The E0 miner runs unchanged (extra fields are
additive); a provenance-aware miner default is include-with-flag; and for M-phase synthesis
the join is the payload, not a filter — an alias conflict plus its prefix-tagged transitions
is exactly the evidence needed to *split* the aliased node on hidden state, which is where
Qwen earns its keep.

## E1-pre — candidate recall diagnostic (zero model calls, runs first)

The cap makes the explorer hostage to segmentation quality; whether the winning clicks even
enter the candidate pool is checkable today from data on disk. For every human L1 ACTION6 in
the replays (six iteration games first, then all 24): segment the pre-click settled frame,
generate the capped candidate set, and score **cell-level recall** (human's exact cell is a
candidate) and **node-level recall** (human's cell falls inside a candidate's node — clicking
anywhere in the node may or may not be equivalent; the gap between the two metrics is the
honest uncertainty). Background clicks are the expected failure class (placement games click
*locations*, not objects). If recall is materially below 1.0 on completion-path clicks, add the
contingent supplement — an 8×8 lattice (w) of background probes — and re-measure before any
explorer run. No invented recall threshold: the measured number decides, game by game.

**RUN 2026-08-04 — result in `notes/e1-pre-recall.md`; the gate passes.** 4,312 L1 clicks over
18 games (six public games contain no L1 click at all). Node recall 1.000 on 17 of 18 at cap 96,
bp35 0.986; every miss is cap-attributable, segmentation never loses a click. The cell/node gap
was resolved rather than reported: forking the engine shows node-point clicking is outcome-
equivalent on 14 games but **not** on r11l (0.218) or su15 (0.466) — the placement games this
section predicted. That did not turn out to matter, because the bar the explorer actually needs
is reachability, and **100 of 100 L1 completions are reachable** from the candidate set (r11l
needs the lattice for 2). Caveat for anything built on fork machinery: `copy.deepcopy` of an
ARCBaseGame is **not** faithful on tn36, so every fork carries a per-click control.

**Split-half control** (`e1_split.py`, sessions by `sha256(guid)` parity): the fill order
replicates — `largest` is selected in both directions — and the adopted pair's held-out recall
is 0.9991 against 1.0000 in-sample. The **cap does not replicate**: selection on half B prefers
192, and the choice is driven almost entirely by bp35. Read the cap as "≥96, 192 if bp35-like
segmentation dust is common on hidden games", not as a measured optimum.

## Measurements (per game, L1, all public games — six iteration games first as bring-up)

outcome {completed | saturated | closed | closed-unreachable | saturated-by-budget} ·
actions-to-outcome · alias-suspect node count · unique
states · transitions recorded · frontier remaining · alias-conflict count · incidental
completion (bool, action index) · wall-clock. Context row: human L1 transition volumes from E0
(137–641) as the evidence-yield reference.

## Non-goals

No LLM calls, no directives (E2's M-loop), no L2 play, no click-coordinate learning, no reuse
of anything mined across games. The explorer must be boring: its job is coverage, capture, and
honest termination.
