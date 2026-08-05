# E1 prefix repair — walked-path maps to replace the composed prefixes

**2026-08-05. Task note for agent execution. Zero model calls; ~1 h compute, 3–4 h
agent.** The audit half of this is done (`61cda0d`, `logs/e1_prefix_audit.json`: 14 of
24 stores don't fully replay, 9 catastrophically, diverging 1–2 actions from reset);
this task is the repair. Until it ships, branch-and-deviate is licensed only on
individually verified paths, and X3 is blocked on the rotten games.

## Why the fix works

The stores' `graph.json` `prefix` maps were **composed** from edges observed at
different moments — on games with latent state, a composed path is not a walked path.
But the explorer is deterministic and its instrumented rerun (`e2_hidden_state.py`
machinery) reproduces every store **byte-for-byte, 24/24 games**, while logging every
`perform()` including resets. The true walked path to every state is recoverable from
those logs: for each state's first observation, the actions since the last RESET.
RESET verifiably zeroes the known latents (P1 probes, m0r0 and g50t; audit's
`reset_restores_origin`), so RESET + walked path is correct by construction.

## Steps

1. **Rerun with logging** (or reuse existing sidecars in `logs/e2_hidden_state_rerun/`
   where complete): per game, the byte-identical gate must pass — same gate as before;
   a mismatch is a stop-and-report, not a skip.
2. **Extract walked prefixes**: per state, actions since last RESET at first
   observation. Write sidecar maps to `logs/e1_prefix_v2/{game}.json` — **never modify
   `logs/e1_store_v2/`** (frozen). Include per-state path length; report length stats vs
   the old composed prefixes (walked paths will often be longer — that is the price of
   correctness; quantify it).
3. **Validate by fresh replay**: per game, sample ≥ 12 states stratified by depth plus
   every state in the audit's `shallowest_failures`; fresh RESET + walked path; grid
   must match. Acceptance: 100% on sampled states. **Any walked-path replay failure is
   a loud finding** (nondeterminism the whole line assumes away) — report it, do not
   paper over it.
4. **Optional, clean games only** (the 13 with ≥ 95% audit verification): BFS-shortened
   routes over store edges, each individually verified by replay before recording, as a
   `short` variant alongside `walked`. On the rotten 9, do not chain edges at all.
5. Summary JSON committed (`logs/e1_prefix_repair.json`: per game, states covered,
   validation results, length stats); the per-state maps stay local (gitignored dir —
   confirm with `git check-ignore`).

## Consumers to note in the writeup

X3 (live plan execution), any future branch-and-deviate probing, cheap level re-entry
after resets, and the slice-2 latent half-A extension (diverged-vs-verified labels).
State explicitly in the results which games are now fully routable.

## Results — 2026-08-05, `agent/harness/e1_prefix_repair.py`, `logs/e1_prefix_repair.json`

**All 24 games are now fully routable.** 27,521 of 27,521 stored states have a walked route,
and every one of them replays to its stored grid from a fresh game. Zero model calls; 57 s
wall-clock at `--jobs 8`; the store was never opened for writing.

| | before (audit) | after |
|---|---:|---:|
| states with a route that replays | 14,694 / 27,521 (53.4%) | **27,521 / 27,521 (100%)** |
| games fully verified | 10 / 24 | **24 / 24** |

- **Step 1, the gate: passed 24/24 without rerunning.** The existing sidecars in
  `logs/e2_hidden_state_rerun/` are complete, and their `transitions.jsonl` is **byte-identical**
  to the frozen store's for every game (re-checked here, not taken from
  `logs/e2_hidden_state.json`); `performs.jsonl` indices are contiguous `1..N`. Nothing was
  re-explored, so ~1 h of compute was not spent.
- **Step 2, extraction.** The anchor is *a RESET whose observed post digest is the origin*, not
  merely a RESET — RESET restores the level, so after a level clear it would land elsewhere and
  the route would be silently wrong. Measured: every RESET in every game restored the origin
  (e.g. g50t 642/642, sc25 688/688), so **no state was lost to an unanchored episode** in any
  game and coverage is 100% rather than merely high.
- **Step 3, validation, two passes, both 100%.** *Trajectory*: one fresh `new_game()` per
  episode, digest checked at **every** position — 50,877/50,877 positions matched, which
  validates all 27,521 routes rather than a sample. *Sample* (the note's acceptance test, and
  the stricter one — a fresh engine per state): 376 states over 24 games, 12 strata by walked
  depth giving 13–18 states per game (7 in lp85, which has only 7 states), seed 11 (w),
  **376/376 pass**, including **all 70 states in the audit's `shallowest_failures`** (5 each in
  the 14 games that had any). **No walked-path replay failure anywhere** — the nondeterminism the step warned about did not appear.
- **The price of correctness, quantified.** Walked routes are longer than composed ones, but
  the cost is concentrated, not spread: the median walked/composed length ratio is exactly
  **1.0 in 14 of 24 games** (all 10 audit-clean ones plus bp35, sp80, re86, tr87 — where the
  composed prefix was already the walked one). It is paid where the explorer rarely reset —
  sk48 **9.6×** (mean 546 actions/state, 3 RESETs in 3,000 actions), sb26 4.8×, lp85 5.8×,
  ar25 4.1×, sc25 2.6×. Across the nine rotten games the ratio runs 1.21–9.59.
- **Step 4, short routes (13 clean games only).** BFS over non-conflicted store edges,
  every proposal executed before recording: **2,129 proposed, 1,909 verified (89.7%), 220
  rejected**. Biggest wins sb26 (732 routes, −223 actions each), ar25 (584, −109), ls20 (339).
  The rejections are the interesting part: they are **not** spread evenly but sit almost
  entirely in the two clean-but-imperfect games — tr87 121/240 rejected, re86 90/127 — i.e.
  even at a 96–97% audit verified rate, **chaining store edges fails about half the time**.
  This is why nothing is recorded unverified, and why no edge was chained on the rotten nine.

### Fully routable

All 24: ar25, bp35, cd82, cn04, dc22, ft09, g50t, ka59, lf52, lp85, ls20, m0r0, r11l, re86,
sb26, sc25, sk48, sp80, su15, tn36, tr87, tu93, vc33, wa30.

### Consumers

X3 (live plan execution), branch-and-deviate probing, cheap level re-entry after a reset, and
the slice-2 latent half-A extension can now use `logs/e1_prefix_v2/{game}.json` on **any** of
the 24 games. Route form is `new_game(); RESET; <actions>`; prefer `short` where present
(it is verified too), else `walked`. `logs/e1_store_v2/` is unchanged and its `graph.json`
`prefix` map should no longer be used for routing on any game.

### One claim in the audit that this narrows — corrected in place

`e1_prefix_audit.py`'s docstring said `unreached` "is not merely an upper bound on the drop
rate, it is the drop rate", because every walked edge's target is in `reached` by
construction. That holds **for routes re-derived from the store**, which was the audit's
premise, and the flat phrasing was an overclaim. The rerun's `performs` log is outside that
premise — it is the execution record, not the store — and it recovers 100% where the audit's
ceiling was 62.2%. The audit's docstring is now scoped explicitly (same day, no numbers
changed): its per-game measurements stand, and what they bound is the store rather than the
recoverable truth.

### Limitations

Verified against the local deterministic engine (REPLAY-DET) and the frozen v2 store only.
Sample sizes are labelled (w): 12 strata per game (7–18 states after forcing in the audit's
failures), seed 11. The trajectory pass shares one engine per episode; the per-state pass is
what rules out cross-replay contamination, and it agrees.

## Cautions

Concurrent agents (slice-2 bundle finishing, others may start): new files only —
`agent/harness/e1_prefix_repair.py` + outputs; do not edit `e1_explorer.py`,
`e2_hidden_state.py`, or the store; `git status` before commits, stage only own files.
No invented numbers; sample sizes labelled (w).
