# `notebooks/` — the Kaggle reference kernel

Tracked so the run configuration is versioned alongside the results it produced. The repository is
private permanently (see [`PUBLISHING.md`](../PUBLISHING.md)).

## NEVER copy this to the clean publication repository

`s1b-tufa-duck-reference-measurement.ipynb` is **substantially third-party**. Cells 0–11 and 13–16 came
with the Tufa Labs TAAF deployment bundle, which carries **no declared licence**. Only **cell 12**, the
customization hook, is entrant-authored.

If a future paper needs to describe this run, re-derive the description from
[`paper/methods/s1-failure-labelling-and-variance.md`](../paper/methods/s1-failure-labelling-and-variance.md)
and from cell 12 alone. Do not copy the notebook.

`kernel-metadata.json` is entrant-authored configuration and is safe, though it names third-party dataset
sources.

## Version history

| version | date | change | result |
|---|---|---|---|
| 1 | 2026-07-26 | reference unmodified | 25 episodes, **no reasoning logs** — `save_request_logs` left at its default `False` |
| 2 | 2026-07-27 | `save_request_logs = True` | 25 episodes with reasoning; also the second replicate that measured the variance floor |
| 3 | 2026-07-27 | *intended* `n_passes = 3` (S1-E11) — **the edit never reached Kaggle** | **executed `n_passes = 1`.** A third single-pass replicate: 25 episodes with reasoning, 588 MB |
| 4 | 2026-07-27 | `n_passes = 1`, pinned deliberately (S1-E14) | **landed** — 25 episodes, ran 20:14–22:27, retrieved Jul 28. The third labellable run; v2+v3+v4 pool to **75 episodes**, verified equal-signature |

Run dates in this table are when the kernel **executed** (`benchmark.json` `start_time`), not when its
output was downloaded — the two differ by hours for v3 and v4 and were briefly conflated across this
file and [`notes/s1-reference-variance.md`](../notes/s1-reference-variance.md).

**Version 3 is the one to understand before touching this notebook.** It was launched to execute
S1-E11's three-pass corpus and did not. What is verifiable from the artifacts: `kaggle kernels pull`
returns source containing `bm.n_passes = 1` with no S1-E11 comment block; the downloaded
`benchmark.json` records `n_passes: 1` with 25 `game_runs`; and only `_p0` request logs exist. The local
notebook at the time held `bm.n_passes = 3`. The edit was made on one side and never pushed to the
other before launch.

**The failure was silent in every way that matters.** The kernel reported `COMPLETE`, ran its expected
~2 h, and produced 588 MB of perfectly good data. Nothing about the run *looks* wrong. A monitor named
after the intended run reported "3-PASS RUN FINISHED" purely because that is what it had been told to
watch for.

> **Before assuming a pushed change took effect, check `n_passes` (or whatever you changed) in the
> downloaded `benchmark.json`.** Kernel status is not evidence that the kernel you edited is the kernel
> that ran. `kaggle kernels pull` into a scratch directory and diff against the local copy — that is the
> only check that distinguishes the two.

S1-E14 then adopted repeated single-pass runs as the *intended* mechanism, on the argument that they
bound the run-to-run variance S4 actually faces while passes inside one kernel share a session, a vLLM
server and a GPU. So `bm.n_passes = 1` in cell 14 is now deliberate and load-bearing: it is what keeps
runs 2, 3 and 4 configuration-identical and therefore poolable into one corpus. The cell carries a
comment saying so, and changing it back would break the pooling premise, not just the pass count.

Versions 1↔2 and 2↔3 are the paired replicates behind
[`notes/s1-reference-variance.md`](../notes/s1-reference-variance.md): same kernel, same accelerator,
same model, same budget, disagreeing on **36%** and **20%** of games respectively.

**Local/remote drift, recorded:** remote version 4 carries a comment citing "S1-E13" where the erratum
is in fact S1-E14 — the id was corrected locally after the push, and re-pushing to fix a comment would
have spent another 2 h of quota. Executable code is unaffected; it syncs on the next legitimate push.

## Runtime

25 games at concurrency 28, 7920 s per game — one run ≈ 2 h 12 m. Under S1-E14 the corpus is built from
repeated single-pass runs rather than one multi-pass kernel, so each run costs ~2 h 12 m of quota and a
run lost to a session limit costs one replicate rather than the corpus.
