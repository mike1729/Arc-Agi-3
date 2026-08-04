# E2 variance arm — slice 1 rerun at seeds 1 and 2 (overnight)

**Task note 2026-08-04, lean mode. Self-contained; execute without further context.**
Qwen generation, ~3.6 h per seed; run overnight, unattended.

---

## ⚠ REPURPOSED 2026-08-04 late — this is now SLICE 1.1, the display-repair test

The autopsy (`notes/e2-trace-autopsy.md` §Results) landed before launch and explains
slice 1's failure **deterministically**: 59/84 proposals rest on reading the digest's
one-example row as a group constant, 55/84 on overriding the miner's unevidenced
no-separation assertion, and 5 of the 6 full-dose digests showed zero resolved rules
(majority-tier suppression; ft09/full — the one surviving cell — is the exception).
Rerunning slice 1 verbatim would measure the stability of diagnosed artifacts. The night
instead tests the autopsy's causal claims: **same protocol, only the digest/prompt
repaired** per its four recommendations.

**Already applied in the worktree** (on top of the seed patch; compile + digest renders
inspected):

1. Value SET per feature per effect group replaces the one-example row, with explicit
   "READ THE VALUE SETS LITERALLY" semantics (rec 1 — removes the 59/84 mechanism).
2. Every unresolved key ends with a NO-SEPARATION WITNESS: the best single feature shown
   failing on concrete counts, and the prompt says to treat these as constraints, not
   claims to argue with (rec 2 — removes the 55/84 mechanism).
3. The guard grammar is stated — `feature = literal`, equality only, no negation/
   threshold/combination (rec 3 — removes the 10 untestable-value deaths).
4. Each rule must state its support count and its refuter; extraction schema carries
   `support_claim` and `refuter` (rec 4 — logged, not used in verification).
5. The all-majority full-dose display now says so honestly instead of "none".

**Unchanged, deliberately:** worktree pinned at `25b44ce` with **v1 vocabulary** — vocab
v2 was adopted on main today (`notes/e2-dose.md` addendum), but tonight isolates ONE
variable (the display repair); v2 enters slice 2. Zero-tolerance verification unchanged.
Seeds, budgets, launch command, copy-back: all as below.

**Morning readout replaces the one below:**

1. Instrument: verdict pass count per seed (expect 12/12).
2. **The causal test:** per cell, do the traces still read example rows as constants or
   argue with the assertion? (The value-set display makes the first impossible to state;
   quote any recurrence.) Proposed / rejected / verified counts vs slice 1's 84/2/9.
3. Overfit check on every dose-125 survivor (`e2_overfit.py`) — the honest
   survives-full-evidence count, vs slice 1's 1/82.
4. `support_claim` vs measured support per proposal (is self-scoring calibrated?), and
   whether refuters are real observations.
5. Union deltas vs the **v1 floors** (in-worktree, comparable); ft09's cells additionally
   read against the v2 floor (0.3017 on-human-L1, `logs/e2_dose_vocab_v2.json`).
6. Goal/hidden-state/probe channels: any movement vs the autopsy's labels (2 correct
   goals / m0r0 hidden-state hit / 8 discriminating probes).
7. Verdict sentence: does repairing the display change what Qwen can contribute, or does
   failure persist through new mechanisms?

---

## What and why

E2 slice 1 (`notes/e2-slice.md`, commit `faa40ee`) is one sampled draw (seed 20260804,
temp 0.6): every limits section says a second seed could move every count. Two of its
findings are already being acted on — the 1-of-82-survives-full-evidence count and ft09's
missing-vocabulary diagnosis (now a build task, `notes/miner-vocab-v2.md`). This arm reruns
the identical protocol at 2 fresh seeds to measure whether those findings are stable or
luck. **Nothing about the protocol changes.** Deliverable = the cross-seed comparison.

## Pre-flight — ALREADY DONE, do not redo (2026-08-04 evening)

- Worktree `/Users/michal/Workspace/ship-variance`, detached at `25b44ce` — the slice-1
  code state. **Why pinned:** the main tree's `rs_e0.py`/`rs_transitions.py` are mid-rewrite
  (vocab v2); floors and verification must be byte-comparable to slice 1.
- Symlinks into the worktree: `data/` and `logs/e1_store_v2` (both gitignored, needed at
  load time).
- Seed patch applied **in the worktree only** (uncommitted there): `--seed` flag threaded
  through both phases; traces tagged `{game}_{dose}_s{seed}.think.json` (slice-1's
  committed traces cannot be overwritten); output defaults to `logs/e2_slice_seed{N}.json`
  with the seed recorded inside. Compile + `--dry-run` verified.
- The stray `mlx_vlm` server is killed; the 28 GB model has the machine to itself.

## Launch

```
cd /Users/michal/Workspace/ship-variance && nohup caffeinate -i sh -c \
  'for s in 1 2; do /Users/michal/Workspace/SHiP-JEPA-X/.venv/bin/python \
   agent/harness/e2_slice.py --seed $s >> logs/night_run.log 2>&1; done' \
  >> logs/night_run.log 2>&1 &
```

- `caffeinate -i` prevents idle sleep; `nohup … &` survives the launching session.
- Seeds are **1 and 2**. NEVER 20260804 (that is slice 1's draw). A third seed is allowed
  only if both finish with night left (~3.6 h each).
- Nothing else may load a model while this runs (RAM).
- If a seed crashes: rerun that seed whole — per-seed outputs are self-contained and
  overwrite their own files only. The JSON is written incrementally after every cell, so
  partial progress is inspectable in `logs/night_run.log` and the seed file.

## Morning readout (the deliverable — a results section appended to this note)

1. **Instrument:** thinking-verdict pass count per seed (expect 12/12; any void reported
   with its trace).
2. **Cross-seed table:** per cell — proposed / parse-rejected / verified, seed 20260804
   (from `logs/e2_slice.json`) vs seeds 1 and 2.
3. **Overfit check on every dose-125 survivor** (worktree `agent/harness/e2_overfit.py`,
   zero model calls): the honest survives-full-evidence count per seed. This is the number
   that decides stability of "1 of 82".
4. **ft09 reproducibility:** parse-rejection reasons per seed, and whether the trace again
   names a per-component adjacency gap — quote the trace verbatim if so. This decides
   whether the vocab-v2 feature rests on one draw or a stable diagnosis.
5. **Union-delta spread** on human L2 across seeds, and any high-support/low-contradiction
   kills à la tu93 (312/7) — collected as measured inputs to the slice-2 repair-bar
   decision, not judged here.
6. **Two verdict sentences:** is 1-of-82 stable? is the vocabulary diagnosis reproducible?

## Copy-back and cleanup (after the readout)

- Copy `logs/e2_slice_seed1.json`, `logs/e2_slice_seed2.json`, and all `*_s1.*`/`*_s2.*`
  trace files from the worktree into the main repo's `logs/` (the existing
  `e2_slice_traces` gitignore exception covers them).
- Apply the seed patch to the main repo's `e2_slice.py` (both day agents leave that file
  untouched) and commit patch + results + this note's results section together.
- `git worktree remove /Users/michal/Workspace/ship-variance` (force if the night log
  should not be kept; copy `night_run.log` first if a crash needs diagnosing).

## Non-goals

Protocol, prompt, budget or model changes · any interaction with the vocab-v2 or autopsy
tasks · conclusions beyond the seed comparison · running against the main tree.
