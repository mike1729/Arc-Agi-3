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

## Cautions

Concurrent agents (slice-2 bundle finishing, others may start): new files only —
`agent/harness/e1_prefix_repair.py` + outputs; do not edit `e1_explorer.py`,
`e2_hidden_state.py`, or the store; `git status` before commits, stage only own files.
No invented numbers; sample sizes labelled (w).
