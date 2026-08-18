# Slice-4 Qwen calibration log

## v1 — candidate 9ccb5418, 2026-08-18 — FAIL (preserved, no salvage)

Eleven-call development calibration under protocol `r4-qwen-calibration-v1`
(commit `77374c8`, pinned Q8 MLX checkpoint, official thinking sampler, `xhigh`,
`preserve_thinking=true`, 32,768-token ceiling, dev sentinels base_seed=4).
Sealed artifacts: run `logs/s4_qwen_calibration_runs/9ccb5418…` (read-only),
terminal receipt status `FAIL`, `RESULT.json`
sha256 `ef37ab3765d0aee4aa6dae73ad72d22dde3c209619b3de2cfec75bfdff512b21`.

Mechanical outcomes:

- same-seed raw output byte-identical (call 4 vs call 1);
- different seed changed raw bytes on the same high-entropy prompt (call 5);
- 11/11 calls closed their reasoning and stopped naturally; zero truncation;
- 10/11 calls schema-valid; pairs SAa331b4 and SAd8b356 passed the paired
  no-regression check on both sides;
- pair SAb05416's preserved-reasoning call listed hypothesis probabilities
  `[0.4, 0.25, 0.15, 0.2]` — one adjacent inversion in the tail — which the v1
  validator treated as fatal (`hypotheses are not ranked by descending
  probability`), producing `malformed_schema` and failing the pair.

**Interpretation (recorded per operator decision, 2026-08-18):** preserved
reasoning produced one probability-order compliance failure. Runtime calibration
passed. This does not demonstrate degraded game understanding or goal
inference. The v1 candidate cannot authorize a freeze, and it also provides no
basis for rejecting Qwen's goal-inference capability. Under the frozen validator
and preregistration the rule is not retroactively waived, the answer is not
reordered, and no single call is rerun.

Diagnostic observation retained for the record (not a v2 change): the preserved
call's prose shows the model bound probe action id `2` to ledger label `A2`
(ids are 0-indexed; id 2 = A3) and reconciled the resulting surprise with a
"hidden heading" theory. The id↔label mapping is not declared in any
model-visible text. Parked with the other rehearsal hardenings pending an
explicit operator decision; none applied in v2.

## v2 — protocol `r4-qwen-calibration-v2`, 2026-08-18

Contract change (operator-decreed), committed before any generation:

- fatal, unchanged: missing fields, invalid types, probabilities outside
  `[0,1]`, total probability above 1;
- non-descending list order is now `ranking_compliance=false` — a nonfatal
  per-call diagnostic recorded in traces and receipts;
- the raw answer is never sorted or modified;
- where ranking matters, ranked original indices are derived with the key
  `(-probability, original_index)` (`s4_run.ranked_hypothesis_indices`);
- active-probe scoring reads `predictions_by_hypothesis` at the two
  highest-probability original indices (`score_active_interaction`,
  sentinel result format v4);
- structurally valid unordered answers are admitted into blind
  goal/constraint/plan adjudication.

Sampler, `xhigh` effort, preserved thinking, token budgets, and the Kaggle
zero-budget are unchanged. No temperature, entropy, reasoning-effort, or Kaggle
experiment is licensed by the v1 event.

Fresh development fixture seed, derived mechanically with zero discretion:
first 8 bytes of the sealed v1 `RESULT.json` sha256, big-endian, mod 2^63 →
**base_seed 8014062316348813028**. Dev sentinels regenerate under this seed and
all eleven calls rerun as a new candidate.

## v2 run + review → protocol v3, 2026-08-18

Operator review of the v2 implementation requested changes before any freeze
authority; the v2 run (candidate `9e584efe…`, seed 8014062316348813028)
continues to termination as immutable diagnostic evidence only. Findings and
fixes, all under `r4-qwen-calibration-v3`:

1. **[P1] Runner/grader parity.** The production grader still rejected
   non-descending hypothesis order and classified such answers malformed —
   recreating the v1 false failure at pilot/ceiling grading. Fixed: the
   grader's `validate_answer` accepts unordered lists; its raw-trace reparse
   rederives `ranking_compliance` and requires trace equality. Parity is now
   regression-tested (identical acceptance and diagnostics on unordered,
   ordered, out-of-range, and over-sum payloads).
2. **[P1] Seed authority enforced, not documented.** New mechanical chain:
   `required_next_seed` = genesis 4 with no terminal predecessor, else
   sha256(latest sealed terminal artifact — bound RESULT.json, or the receipt
   after a crash)[:8] mod 2^63. `--run` derives the seed and refuses
   `--base-seed`; the candidate embeds its `seed_authority` record; hard
   validation recomputes it, requires the candidate to be the **latest**
   terminal attempt (superseded/shopped candidates refused), and pins the
   fixture root to the seed-addressed path. The chain reproduces the v2 seed
   from v1's sealed result exactly.
3. **[P1] Synthetic action mapping declared.** Every sentinel prompt now
   carries `ACTION_MAPPING_NOTE`: "id k denotes ledger action A(k+1); id 0 =
   A1 … id 4 = A5; click is always null here." (This changes model-visible
   carrier bytes; fixtures regenerate under the new seed regardless.)
4. **[P2] `ranking_compliance` sealed end-to-end.** Sentinel call receipts
   (`_call_binding`), sentinel trace-equality and raw-projection checks, and
   the grader's round-trace reparse all record/require the diagnostic
   (sentinel result format v5).
5. **[P2] Integration tests.** Added: top-two-original-indices selection where
   the subset {1,2} differs from positional {0,1}; runner/grader parity; seed
   chain genesis/successor/crash/tamper; superseded-candidate refusal.
6. **[P2] Immutable fixture roots.** Development fixtures now generate into
   seed-addressed append-only roots `logs/s4_sentinel_fixtures/dev-<seed>/`,
   never moved. Archive map for the legacy path era: candidate `608c9bd0`
   (crash) ran against the 8px fixtures now at
   `logs/s4_sentinel_dev.stale-20260818`; v1 `9ccb5418` against the 16px
   seed-4 fixtures now at `logs/s4_sentinel_dev.v1-seed4-20260818`; v2
   `9e584efe` against `logs/s4_sentinel_dev`, which stays in place at its
   manifest-bound path.

v3 seed: derived from the sealed v2 terminal artifact once it exists, via the
enforced chain — no manual choice remains anywhere in the path. Sampler,
xhigh, preserved thinking, budgets, KAGGLE_EVAL_BUDGET=0 all unchanged; no
per-call salvage.
