# THINK_BUDGET recheck against the lifted-cap digests

**2026-08-05. Task note for agent execution. Model task — Qwen3.6-27B-8bit, ~1 h GPU.**
Small and self-contained: an instrument check, not a slice.

## What and why

The slice-1.1 follow-up lifted `MAX_FEATURES_PER_GROUP` (commit `e116357`), growing
digests **+29–51%** (dc22/125: 11,760 → 17,741 chars). `THINK_BUDGET = 16384` in
`e2_slice.py` was calibrated before that and **never re-checked**: on 3.6-8bit a 5k
budget produced an unclosed think block and a voided call, so an under-budget run against
longer prompts would silently void cells in any future slice. This measures whether 16k
still closes, before anything model-side is scheduled on the repaired digest.

Secondary (free): first-ever model contact with the lifted-cap digest — a qualitative
read on whether the full feature lists get used. **n=3; no conclusions about
contribution from this task** — instrument verdicts and length distributions only.

## Instrument rules (unchanged, non-negotiable)

Qwen3.6-27B-8bit (`~/models/mlx/Qwen3.6-27B-8bit`) · direct `mlx_lm`, never a server ·
template rendered with `enable_thinking=True` · **never constrain the first decoded
token** · per-call trace logged · mechanical thinking verdict per call (open/closed/
substantive/no-prefill); an unclosed think block is itself a datum here, not just a void.

## Protocol

1. Render the current digests for all 12 slice cells (`e2_slice.py` machinery as on
   main; no code changes). Record char lengths; pick the **3 longest**.
2. For each of the 3: run the phase-1 think call exactly as the slice would (same
   prompt, same sampling, temp 0.6, seed 1), `max_tokens = THINK_BUDGET` (16384).
3. Record per call: think chars/tokens, closed or not, tokens remaining at close,
   answer present, wall time, prefill + generation tok/s (the +30–50% prompt growth
   also moves the slice feasibility arithmetic — re-derive minutes/call).
4. If any think block is unclosed at 16,384: rerun that digest once at 24k (w) to get
   the actual closing length. Report; do NOT silently change `THINK_BUDGET`.

## Deliverable

Append results here: per-call table (digest, chars, think length, closed?, headroom,
tok/s), the re-derived minutes-per-call, and one recommendation line: keep 16384 / raise
to a measured value (state the observed max + headroom arithmetic — measured, not
invented). The slice-2 design consumes the recommendation; this task changes no code.

## Cautions

- Two other agents are live in the tree: modify **nothing** — this task writes only
  `logs/think_budget_recheck.json`, traces under `logs/e2_slice_traces/` with a
  `_tbcheck` tag, and this note's results section. `git status` before commit; stage
  only those.
- If the m0r0 digest is among the 3 longest, remember its hidden-state lines are the
  live channel — do not read anything about channel quality from one call.
- Seeds: 1 (and 2 only if a rerun is needed) — **never 20260804**.

## Estimate

3 renders + 3 calls at ~15–25 min/call ≈ **1–1.5 h wall**, one GPU slot. Can run today;
does not conflict with the three zero-model tasks.
