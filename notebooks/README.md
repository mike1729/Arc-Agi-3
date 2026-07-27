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
| 3 | 2026-07-27 | `n_passes = 3` (S1-E11) | up to 75 episodes — makes the pre-registered `sample_size: 30` achievable |

Versions 1 and 2 are the paired replicates behind
[`notes/s1-reference-variance.md`](../notes/s1-reference-variance.md): same kernel, same accelerator,
same model, same budget, and they disagreed on 9 of 25 games.

## Runtime

25 games at concurrency 28, 7920 s per game. One pass ≈ 2 h 12 m; three passes ≈ 6 h 40 m, since 75
game-runs is three batches of 28. Each game-run is independent, so a session cut short still leaves the
completed passes usable.
