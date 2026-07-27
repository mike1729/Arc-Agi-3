# `logs/` — S1 evidence, and what may leave this repository

Most of `logs/` is gitignored. The small measurement JSONs are the exception: they are tracked because
they are otherwise **the only copy** of S1's evidence, and this remote is private
(see [`PUBLISHING.md`](../PUBLISHING.md)).

## Why the exception exists

932 MB of run artifacts sit on one machine. The reference runs cannot be reproduced — the agent samples
at `temperature 0.6` with **no seed**, so a rerun is a different result, not the same one (measured:
`notes/s1-reference-variance.md`). A lost Kaggle run is 2 h 12 m of GPU quota *and* a data point that no
longer exists. The derived JSONs are small, so they are versioned; the raw artifacts are not.

**Still unbacked, and the real exposure:**

| | size | reproducible? |
|---|---:|---|
| `kaggle_v2/` (25 per-game request logs) | 516 MB | no — stochastic, 2 h 12 m |
| `kaggle-reference/` (v1) | — | no — stochastic, and its kernel version is superseded |
| `runs/` (29 local run dirs) | 230 MB | no — same reason, 45 min each |
| `quarantine/` | 164 MB | n/a — discarded runs, kept for provenance |

Too large for git. These need an off-machine target that is **not public**.

## Screen for the clean publication repository

`PUBLISHING.md` lists `logs/` as **check first**: run artifacts embed reference prompts and model
output, and the publication repository must contain only entrant-authored work. Screened 2026-07-27 by
scanning every tracked JSON for `evidence` / `reasoning` / `content` / `tool_code` / `prompt` /
`messages` keys.

### Do NOT copy — contains reference model reasoning verbatim

| file | why |
|---|---|
| `s1d_corpus.json` | `evidence` holds the reference's reasoning text and tool code per episode |
| `s1d_corpus_phase1.json` | same |
| `s1d_episodes_kaggle_reference.json` | same |

Frequencies and per-episode *statistics* derived from these are entrant-authored and safe; the
`evidence` payloads are not. If the corpus is needed in the clean repo, strip `evidence` and republish
the numeric fields only.

### Derived from reference runs, but carries no reference text

| file | what it is |
|---|---|
| `solutions_reference.json` | action IDs and coordinates for cleared levels |

No prompts or model output — action sequences are environment-space measurements. Judgement call rather
than a clean pass: it is a record of what the reference *did*, so treat it as derived and decide
deliberately rather than copying by default.

### Safe — our own measurements

`concurrency_sweep*.json`, `r1_determinism.json`, `r2_*.json`, `s1_run_summary.json`, `s1e_*_state.json`,
`s2_arc_conventions.json` — harness state and our own instrumentation output.

## Not tracked, deliberately

`s1e_state_PRE-D13_discarded.json` — superseded by the D13 fix; kept locally for provenance, excluded
from the repository so it cannot be mistaken for live state.
