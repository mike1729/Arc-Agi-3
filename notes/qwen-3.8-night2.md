# Night 2 — slice-4 chain (2026-08-17 → 08-18)

Operator order (verbatim, 23:00): gold + final preregistration/ceiling → six test suites +
renderer self-test + probe smokes → commit clean tree → rebuild recaptures and packets →
gate-night calibration → final fresh v2.2 probe PASS → `--freeze` → 16 Qwen pilot cells →
prepare four transcript-matched P comparator cells → run comparator → grade. Calibration is
folded into recertification per the same message; if it changes any budget/code/config the
loop repeats tests → commit → rebuild → recertify. Ceiling: `kind="model"`, same pinned
Qwen3.8-27B-8bit checkpoint, P arm only, seed 2, descriptive-only (no closure).

Running log; timestamps are start-of-stage, local (CEST).

## 23:05 — pre-registration validated

`notes/qwen-3.8-slice4-pilot-preregistration.json` (operator-written) validates against
`s4_grade.normalize_preregistration` with the live blind map: 20 expected cells
(16 Qwen T/V/O/P × {ls20, ft09, m0r0, sp80} + 4 ceiling P, all seed 2), budgets fill to the
runner constants exactly, `missing_reruns=1`, `game_pass_min_seeds=1`, plan budgets
mechanical (ft09 34 = 2×17, sp80 22 = 2×11, ls20/m0r0 150 fallback), Stage-B closure
thresholds auto-filled (inert in Stage A). Blind IDs are salt-deterministic
(`BLIND_SALT` in s4_packet.py), so rebuilds cannot invalidate the frozen matrix.

## 23:05 — tests green

86 passed + 22 subtests across the six suites; `s4_render.py --selftest` PASS.

## 23:10 — stale abort marker: resolved, no action

`logs/s4_observation_log/kaggle_v4/ABORTED.txt` survives from the first export attempt
(free-text `RIGHT` rejection, later fixed by the censused label set). Both s4_packet and
s4_grade already handle exactly this: the marker is admitted iff it *predates* the cutoff
manifest (mtime check) and is then recorded as `present_but_superseded` with its sha256.
Verified: marker 1786980157 < manifest 1786980213. Nothing to clean.

## 23:15–23:55 — sealed gold written and mechanically verified

`logs/s4_sealed/gold/{ls20,ft09,m0r0,sp80}.json` — paraphrase, constraints, counterfactual
boards, operator-familiarity record. Method, per game:

1. **Source read** (`data/environment_files/<g>/<ver>/<g>.py`) for the L1 mechanism and win
   condition — mechanism only, per the standing rule that source reads don't give
   signatures.
2. **Enumeration**: L1 completion boards from the human corpus via the established
   `e2_positives` machinery (dedup by post grid), L1 negatives likewise; initial boards
   from the normalized Kaggle export.
3. **Bidirectional mechanical verification**: each game's constraint set implemented as a
   board predicate and evaluated over the full corpus —

   | game | completions (true) | negatives (false) |
   |---|---|---|
   | ls20 | 9/9 | 469/469 |
   | ft09 | 4/4 | 456/456 |
   | m0r0 | 11/11 | 332/332 |
   | sp80 | 8/8 | 301/301 |

   Zero misfires in either direction.
4. **Counterfactuals are observed boards only** (no hand construction): the completion post
   (true), the same session's pre-board one action earlier (false, near-miss), the initial
   export board (false, vacuity killer), and for m0r0 additionally the observed
   touching-but-not-fused negative `0e1adaaf/23` (false — two adjacent pieces form one
   50-cell connected region; fusion leaves 25 — kills "single connected blob" readings and
   the night-1 always-true attractor class). Every `objective_holds` label asserted equal
   to the verified predicate at write time.

Win conditions as read + verified (the one-line versions):
- **ls20 L1**: avatar upright (rotation 0: colour-12 cap on top) standing exactly in the
  walled pocket (rows 10–14, cols 34–38); shape/colour already match from start; preview
  glyph absorbed. Start rotation 270; one rotator-tile touch suffices.
- **ft09 L1**: ring of 8 cells around the printed tile: unmarked sides (NW,W,E,SW) toggled
  to 8 (= tile centre), marked sides (N,NE,S,SE) left 9. All start 9; 32-click budget.
- **m0r0 L1**: two mirror-moving pieces brought onto the same cell → fuse (25 colour-10
  cells vs 50 whenever separate, even touching). 150-action budget.
- **sp80 L1**: pour settles with both targets water-captured (11→13) and zero water on the
  ground bar (no 14 in rows 60–63). 30 placement steps, 4 pour attempts.

Verification artifacts: scratchpad `gold_verify.py` + `write_gold.py`,
`gold_verify_summary.json`, `gold_write_report.json`. Gold sha256s (grader's
`snapshot_gold`): ft09 b761aec92ba6…, ls20 8b9418834405…, m0r0 5b4beb49f748…,
sp80 734c7c6375a3…. The familiarity fields are factual development-exposure records
written by the night agent (flagged in the morning summary — they seal at freeze without
operator review, per the overnight order; Stage A model ceiling makes them
non-closure-bearing).

## 00:00 — committed 5a09167; rebuilds green

Overhaul + prereg + night log committed (clean tree). Recaptures rebuilt v2, all four
games 100% verified (ls20 3000/3000, ft09 1699/1699, m0r0 3250/3250, sp80 1106/1106).
Packets rebuilt, 10 pages × 3 carriers each, initial visual tokens raw 3,991–5,197 /
overlay 4,376–6,128 — inside the 6,448 cap. Blind map regenerated byte-identical
(salt-deterministic).

## 00:05 — fresh probe certification launched

`e2_probe_vlm.py --out logs/e2_probe_vlm_38_8bit.json --force --max-tokens 12000
--packet-max-tokens 16000` on the committed tree. Budget calibration is folded into
this run per the operator order (packet-scale + production-sampler stability panels).

## 00:10–00:50 — ceiling executor written: `agent/harness/s4_ceiling.py`

The runner accepts only `--role qwen`; ceiling cells enter through the grader's
transcript-matched pathway (`--prepare-ceiling` → ceiling_input artifact →
executor → execution trace + answers document). The executor had to exist **before**
the freeze: the grader requires the ceiling document's git state to be the frozen
commit with a clean tree, so nothing new can be added after `--freeze`. Contract
implemented from `validate_run_document` / `validate_model_ceiling_execution_trace` /
`enforce_ceiling_matches`:

- delivers each cell's `evidence.user_messages` **verbatim** through the runner's own
  `ask_chat` (identical template invariants, production sampler, xhigh, budget 20,000)
  with image-byte SHA verification before send;
- seeds: `seed_for(2, "<blind>_r0")`, asserted equal to the grader's
  `generation_seed` derivation; round tag `<blind>_P_s2_r0` so
  `validate_cell_provenance` passes;
- writes 0o444 raw execution artifacts + trace bound to `ceiling_spec_sha256` and the
  ceiling_input sha; answers document mirrors the runner format (role=ceiling,
  budgets, frozen manifest + certificate identity checks via the runner's own
  `verify_certificate`);
- self-verifies through `grade.validate_run_document` + `collect_attempts` before
  reporting success — a document the grader would refuse never reports PASS.

Serving-config honesty gate: the frozen ceiling_spec's serving_config (xhigh, temp 1.0
/ top-p 0.95 / top-k 20, 20,000 out, mlx-vlm runtime) is checked against the actual
runtime constants at startup — the spec must describe reality, not merely name it.
