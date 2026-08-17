# Slice 4 design — vision-grounded goal inference with executed probes (Qwen3.8)

**2026-08-17. DRAFT for operator iteration — nothing here is pinned.** Response to the
five gaps that closed night 1 (`notes/qwen-3.8-night1.md`, deviation 14). One sentence
of intent: stop grading correlation on stale evidence, and start measuring whether the
model can identify the causal objective, know when it can't, and buy the missing bit
with an experiment it designs — with the improved 3.8 vision tower carrying the board.

## The five fixes, numbered to match the review

1. **FB fires only on a real counterexample.** Gate: a store false-positive or a
   solved-board false-negative must exist and render; otherwise the cell is F-only and
   the record says why. dc22/ft09-style empty-counterexample turns become impossible.
   (Their night-1 FB results and runtime are discarded, as ruled.)
2. **The record builds from the best evidence we hold: `e1_store_v3`** (grouped
   performs, confirmation ledgers, conflict records — the census shows what v2's digest
   never saw), plus the completion captures and positives already in use. Build item:
   digest v5 = v4's structure over v3's store, with a measured content diff (what does
   v5 show that v4 could not — reported, not assumed).
3. **Three-tier grading; the role's bar is tier 3, not tier 1.**
   - **T1 — separator (mechanical, kept, relabelled "correlation"):** two-direction
     grade on replay states. Necessary, never sufficient. ls20's 9/9 lives here.
   - **T2 — source audit (per cell, standard):** is the stated objective the causal
     one, including the source-required constraint components (shape / colour /
     rotation / relation), labels-only read as always.
   - **T3 — discrimination (new, the success bar):** the predicate/free-form must
     survive states where correlate and objective diverge — from the counterfactual
     set (below) and from the model's own executed probes. Goal understanding =
     T1 ∧ T2 ∧ T3; T1 alone is recorded as correlation discovery.
4. **The proposed test action is executed.** Ambiguity is declared honestly — the
   separator enumerator's surviving candidate set (4–323 per game) IS the ambiguity —
   and the loop closes: model states rival goals + a discriminating action from a named
   reachable state → harness executes it via REPLAY-DET branch-and-deviate (verified
   routes exist for all 24 games) → outcome recorded → one revision turn → re-grade.
   Budget ≤3 probes/cell (w). Scored on: did the executed probe's outcome distinguish
   the rivals, and did the revision converge toward the survivor.
5. **Conclusions stay configuration-tagged.** Night 1 closed (27B, 8-bit, text-only,
   low). Slice 4 opens the vision configs; each night's verdict names its tuple
   (quant, modality, effort, caps). No "Qwen3.8 can't" without the tuple.

## The vision arm

- **Input:** rendered board PNGs (the taaf reference stack's renderer/format — the
  reference agent already shipped image + segmentation and its instructions treat the
  image as the primary view; we adopt that precedent instead of inventing a format)
  for: initial board, causal-episode keyframes, completion contrast (solved vs
  last-incomplete), and probe outcomes. The letter-grid text renders — the bulk of the
  40k-token prompts — are REPLACED by images in the vision arms; the structured causal
  record (entities, rules, histories, contrasts) stays text.
- **Serving:** direct `mlx_vlm.generate` — never its server (the July lesson stands).
  0.6.7 installed vs 0.6.8-made conversions: the gate decides; upgrade only on failure.
- **Why this could move what text did not:** night 1's failure shapes were identical
  across generations on identical text records — evidence the record, not the model,
  drives the attractors. Vision changes the record's carrier; per-frame token cost
  drops (image tokens vs ~2.9 chars/token letter grids), freeing budget for more
  contrasts per cell.

## Bring-up gate, vision edition (no number trusted before it)

1. Thinking probe through `mlx_vlm` with an image attached: template opens `<think>`,
   no prefill (generation-region check), substantive, closed, answer present — AND the
   answer must reference visible content (a read-back check: name the colour at a
   marked cell).
2. Board-fidelity probe: can the model read exact cell values from our rendered PNG at
   the chosen scale? Sweep 2–3 render scales; pick the cheapest that passes read-back
   ≥ threshold (w — set at gate from the sweep, recorded).
3. Image token accounting: measured tokens/frame at the pinned scale; caps redefined as
   text-budget + image-count and re-asserted per cell.
4. Effort ladder + budget probe **per config**: fleet-calibrated (the night-1 lesson:
   never one cell) — dry-run all cells, probe the two largest, cap = max-closure ×1.25.
5. Envelope: prefill/decode with images in context; the wall model that schedules the
   night comes from these numbers, not from night 1's text envelope.

## Arms and first night (proposal — operator decides)

| arm | record | modality | games | seeds |
|---|---|---|---|---|
| T (control) | digest v5 (v3 store), text boards | text | 4 (dc22, ls20, ft09, sp80) | 1 |
| V | digest v5, boards as images | text+vision | same 4 | 1 |

Same games, same seed, same grader — the night answers "does the carrier change the
answer" as a matched contrast, not coverage. Second night extends the winning arm to
8 games × 2 seeds with probes-executed scoring. Effort: low + medium if the gate's
fleet calibration prices medium inside the window (night-1 caps say low ≈ 31.4k text;
vision counts unknown until gate).

## What stands, what is discarded (from night 1)

Stands: closure ladder + fleet spread, envelope numbers, instrument fixes (FB
history-prefill, missing-observation regrader), failure-shape isomorphism, ls20 as
correlation-discovery exhibit. Discarded: dc22/ft09 FB results and runtime; any
"3.8 can't" phrasing without the configuration tuple.

## Pinned decisions (operator, 2026-08-17)

1. **First night = the 4-game matched T-vs-V contrast** (dc22, ls20, ft09, sp80 ×
   seed 1, both carriers). Coverage extends the winner on night 2.
2. **Low + medium if it fits** — the gate fleet-calibrates both; medium runs only if
   its measured cap prices inside the window.
3. **Success bar = T1 ∧ T2 ∧ T3, probes required.** T1-only results are recorded as
   correlation discovery, never as goal understanding.
4. **Mini-S1 waits until slice 4 reads out** — one question in flight at a time. The
   LB actor signal stays recorded, not acted on.

## Build order (day work; GPU only at the gate)

1. **Vision instrument first (riskiest):** direct `mlx_vlm.generate` path + vision
   thinking probe with read-back (`e2_probe_vlm.py`) — decides the 0.6.7-vs-0.6.8
   question and whether thinking survives image context, before anything depends on it.
2. Board→PNG renderer on the taaf format + fidelity-sweep assets.
3. Small fixes: FB counterexample gate · `_s4` trace tags.
4. **Digest v5 over `e1_store_v3`** with the measured v5-vs-v4 content diff.
5. **Probe-execution loop**: ambiguity = enumerator's surviving separators; REPLAY-DET
   branch-and-deviate executes the model's discriminating action; ≤3 probes/cell (w);
   revision turn; discrimination scoring.
6. Counterfactual set for T3 (correlate-vs-objective divergence states, from source
   audit + constructed boards).
7. Gate night: fidelity scale sweep · image token accounting · fleet effort
   calibration (low + medium) · envelope → wall model → caps pinned → night 1.

## Cautions carried forward

PUBLISHING (rendered boards in prompts/traces — local only) · trace tags get a run
suffix (`_s4…`) so completion reruns never overwrite · configuration column in every
table · working numbers (w) until the gate measures them.
