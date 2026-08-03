# VP Freeze-1 measurement results

**Run status: VP1 complete; VP2 not run by frozen routing.**

The measurement ran from 2026-08-03 04:35:07 UTC to 07:09:49 UTC against the local
`Qwen3.6-27B-8bit` MLX model. All 288 VP1 rows completed, row IDs are unique, every row carries
freeze fingerprint `bf4543598bb385ec12ca378958348526160ce3358ab7db198ab46098db450868`,
and there were zero request errors. The frozen runner selected I-8 among the failing visual
arms, then stopped before VP2 because no pure-image arm passed VP1. The generated results JSON
uses `status: in_progress` to mean the full VP1→VP2 suite did not complete; operationally this
is a **terminal routed stop**, not an interrupted run.

Question fingerprint:
`836544fc50061c469a069469a1cfb69d0eb0407a0f2237537d735d46442624c8`.

## VP1 results

Metrics are six-game macros. None of the six arms passed the VP1 gates.

| arm | first-pass valid | marked | patch cell | patch exact | pixel band | component band | lookup | pass |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| I-4 | 1.000 | 0.129 | 0.389 | 0.125 | 0.458 | 0.104 | 0.260 | no |
| I-8 | 0.958 | 0.296 | 0.255 | 0.104 | 0.542 | 0.208 | 0.354 | no |
| I-16 | 0.979 | 0.438 | 0.243 | 0.104 | 0.542 | 0.188 | 0.344 | no |
| I-A | 0.833 | 0.821 | 0.782 | 0.667 | 0.208 | 0.250 | 0.490 | no |
| I-H | 0.812 | 0.750 | 0.743 | 0.646 | 0.458 | 0.271 | 0.375 | no |
| I-C | 0.979 | 0.704 | 0.336 | 0.042 | 0.562 | 0.167 | 0.292 | no |

The visual-route result is decisive. Pure images recover neither marked local state nor the
3×3 patch reliably, and every pure arm has zero or near-zero exact-patch performance relative
to the 0.70 gate. Increasing scale helps marked-cell accuracy (I-4 0.129 → I-16 0.438) but does
not rescue patch transcription or component counting. I-A and I-H are materially better on
marked cells and patch transcription, showing that explicit text contributes useful local
binding, but both remain far below the global count gates. I-C's crop ceiling improves marked
cells but not patches, so the failure is not explained by whole-board resolution alone.

The deterministic 90% hierarchical bootstrap intervals are recorded in
`logs/vp_results.json`. Even the upper interval endpoints for pure-image marked accuracy
(I-4 0.210, I-8 0.392, I-16 0.538) and patch-cell accuracy (0.546, 0.374, 0.397) remain far
below their gates.

## Cost and score-run viability

| arm | mean input tokens | latency p50 (s) | latency p95 (s) |
|---|---:|---:|---:|
| I-4 | 533 | 94.2 | 115.2 |
| I-8 | 933 | 148.2 | 178.7 |
| I-16 | 2,568 | 157.5 | 180.5 |
| I-A | 18,299 | 158.7 | 180.4 |
| I-H | 20,488 | 121.0 | 176.6 |
| I-C | 1,176 | 52.8 | 77.3 |

These local latencies were measured at concurrency four and are not the exact FP8/vLLM
deployment calibration. They nevertheless reinforce the routing decision: the only arms with
meaningfully better local detail consume roughly 18–20k input tokens per request, while the
pure-image route fails perception outright. The target-stack 48-call calibration is therefore
not licensed by Freeze 1.

## Routing conclusion

- VP1 visual route: **fail**.
- VP2 pixel/change screen: **not run** (frozen gate).
- VP2-S semantic bridge: **not run** (frozen gate).
- Palette-permutation add-on: **not run** (no passing champion).
- Score-run integration: **forbidden by Freeze 1**.
- Next action: do not reopen VP3/VP4 or advisor integration from this result. If perception is
  revisited, it requires a separately justified new freeze rather than tuning these arms on
  the observed failures.

Artifacts:

- `logs/vp_freeze.json` — immutable implementation/question manifest.
- `logs/vp_questions.json` — emitted frozen question set.
- `logs/vp_raw.jsonl` — append-only local raw responses and primary scores (workspace-local).
- `logs/vp_results.json` — scored summaries and hierarchical intervals.
