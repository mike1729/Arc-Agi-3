# Slice 2 — night-run dispatch note

**2026-08-05. Task note for the run agent. GPU night: 16 model calls ≈ 5 h, plus
pre-flight and morning readout.** Protocol of record: `notes/e2-slice2.md` (with all
same-day amendments). Build of record: the `e2-slice2-build.md` bundle — **do not
launch until its four sub-task commits are on main and its "Done means" holds.**

## Pre-flight (in order; abort on any failure)

1. **Build acceptance**: the bundle's four checks pass (DSL property-tests · prior
   library runs on all 8 games · latent verifier reproduces the m0r0 verdict from a
   spec · digests render with `--help` clean). Run them, don't trust the commit
   messages.
2. **Channel-D check**: read `notes/e2-regrade.md`'s result section. Rule request in
   or out follows its conditional; **record which digest variant is live** in the run
   log. If the re-grade hasn't run, the default (out) stands.
3. **Render all 16 digests** (8 games × seeds share digests — render the 8, note
   counts), record char lengths vs the pre-v3 baseline (dc22/full was 28,742).
   **If the largest digest grew beyond ~40k chars, run one think-budget probe call**
   on it first (the `notes/think-budget-recheck.md` protocol, ~20 min): if the think
   block closes inside 16,384 total generation, proceed; if not, stop and report — do
   not raise the budget unilaterally.
4. **Eyeball three digests** (dc22/full, m0r0/full, one small) — coverage ledger,
   inert inventory, negative-evidence lines, invariants, schemas all present and sane.
5. **Pin a worktree** — the slice-1.1 lesson; main churns with concurrent agents:
   `git worktree add /Users/michal/Workspace/ship-slice2 <run-commit>`, symlink `data`
   and `logs/e1_store_v2` into it, confirm the floor files exist (they are committed).
   Record the pinned commit hash in the run log.
6. **Verify the CLI**: `--seed`, `--out`, game list (six + sp80 + lf52), full dose
   only. Outputs `logs/e2_slice2_seed{1,2}.json`, traces tagged `_s2r1`/`_s2r2` (any
   unambiguous tag; record it).

## Launch

Model `~/models/mlx/Qwen3.6-27B-8bit`, direct `mlx_lm`, `enable_thinking=True`, temp
0.6 / top_p 0.95, `THINK_BUDGET = 16384`, two-phase decode, **first token never
constrained**. Seeds **1 and 2** (never 20260804). `nohup` + `caffeinate -i`, both
seeds sequentially, log to `logs/slice2_night.log`. ~18 min/cell measured → ~5 h.

Per-call mechanical thinking verdict as always; an unclosed think block **voids the
cell** — log it, continue the run, report the count. Do not rerun voided cells
mid-night; rerun at the end only if wall-clock allows.

## Morning readout (append results to `notes/e2-slice2.md`)

Exactly the pre-committed comparisons — directions, not thresholds:

1. **Channel A**: games where the model's predicate is store-consistent ∧
   source-correct ∧ the prior library's is not (adjudication vs source: labels only,
   autopsy rubric, note the single-reader caveat). Plus the three diagnostic counts:
   self-refuting refuters · test-action executability (via the probe-executor
   machinery) · contradiction-respect.
2. **Channel B**: latents accepted (beat all 5 random controls on half B; half A where
   measurable; the optional divergence extension if the verifier implements it). Every
   `prose_rejected` item listed verbatim and adjudicated garbage vs
   coherent-but-out-of-grammar — never pooled.
3. **Channel C**: targeting rate vs the measured failure typing; the implementation
   queue (top distinct proposals) recorded for the follow-up task.
4. **Instrument**: verdicts passed / voided; think-length distribution; wall per cell.
5. **One verdict sentence per channel**: alive or dead, each stated against its
   control.

Then: copy outputs and traces back to main, commit (stage only this run's files —
other agents are live), `git worktree remove`, and update the one-line channel-D
conditional in `notes/e2-slice2.md` if the re-grade resolved it.

## Cautions

- PUBLISHING.md: adjudication reads game source freely; committed text carries
  labels/paraphrases only.
- No invented numbers; working choices labelled (w).
- The night runs on **v2 floors** regardless of the conjunction-tier task's state —
  comparability with slices 1/1.1 governs (`notes/miner-conjunction-tier.md`
  non-coupling section).
- If anything in pre-flight smells wrong, the night waits — a failed submission-grade
  run costs a day; a delayed one costs an evening.
