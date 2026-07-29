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
| `kaggle_v3/` (25 per-game request logs) | 588 MB | no — stochastic, 2 h 12 m |
| `kaggle_v4/` (25 per-game request logs) | 486 MB | no — stochastic, 2 h 12 m |
| `kaggle-reference/` (v1) | 948 KB | no — stochastic, and its kernel version is superseded |
| `runs/` (29 local run dirs) | 225 MB | no — same reason, 45 min each |
| `quarantine/` | 164 MB | n/a — discarded runs, kept for provenance |

**≈2.0 GB total, not 932 MB** — v3 and v4 added ~1.07 GB after this table was first written, and each is
a replicate that cannot be regenerated. The three Kaggle runs are jointly the S1-E14 pooled corpus: lose
one and the 75-episode corpus becomes a 50-episode corpus, and `sample_size: 30` stops being the 40%
sample the erratum argues for.

Too large for git. These need an off-machine target that is **not public**.

## Screen for the clean publication repository

`PUBLISHING.md` lists `logs/` as **check first**: run artifacts embed reference prompts and model
output, and the publication repository must contain only entrant-authored work. Re-screened 2026-07-28
by counting `evidence.reasoning_by_step` excerpts in every `logs/*.json` that is tracked or matches
`s1d_corpus*`; the 2026-07-27 screen predates the S1-E14 corpora and missed all three.

### Do NOT copy — contains reference model reasoning verbatim

| file | excerpts | why |
|---|---:|---|
| `s1d_corpus_pooled.json` | 4,185 | v2+v3+v4 evidence packets — the largest concentration of reference output in the repository |
| `s1d_corpus_refv2.json` | 1,494 | **tracked in git**, so it ships by default unless excluded deliberately |
| `s1d_labels_v3v4_pass1/*.json` | 177 | label `evidence` quotes the reference's reasoning; tracked as the only record of 50 first-pass labels |
| `s1d_labels_v2_pass1.json` | 25 | same, for v2 |
| `s1d_labels_rerate_pass2.json` | 30 | same, for the blind re-rate's second pass. **Tracked** — the only record of those 30 ratings, and the gate result cannot be re-verified without them |
| `s1d_rerate_draw.json`, `s1d_rerate_pass2.json` | 30 each | **NOT tracked** (`.gitignore`) — ~5 MB apiece of full evidence packets, the same material `s1d_corpus_pooled.json` already holds. Rebuilt by `agent/harness/s1d_rerate_rebuild.py`; `--verify` checks the rebuild against the SHA-256s the promoted gate recorded |
| `s1d_corpus.json` | 520 | `evidence` holds the reference's reasoning text and tool code per episode |
| `s1d_corpus_phase1.json` | 144 | same |
| `s1d_episodes_kaggle_reference.json` | — | same |

These are the sharpest case in the repository: they are produced by *our* scripts, sit under names that
read like analysis output, and one is tracked — every signal says entrant-authored. The reasoning text is
carried deliberately, because the labelling categories are defined on it and an evidence packet stripped
of it cannot be re-rated. **Regenerate the count rather than trusting this table**, since any corpus
rebuild changes it:

```bash
.venv/bin/python - <<'PY'
import json, glob
for f in sorted(glob.glob('logs/*.json')):
    try:
        d = json.load(open(f))
    except Exception:
        continue
    if not isinstance(d, dict):          # some logs are top-level lists
        continue
    n = sum(len(v) for e in (d.get('episodes') or [])
            for v in ((e.get('evidence') or {}).get('reasoning_by_step') or {}).values())
    if n:
        print(f'{n:6d}  {f}')
PY
```

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

`concurrency_sweep*.json`, `replay_determinism.json`, `reset_accounting*.json`, `s1_run_summary.json`, `s1e_*_state.json`,
`s2_arc_conventions.json` — harness state and our own instrumentation output.

## Not tracked, deliberately

`s1e_state_PRE-D13_discarded.json` — superseded by the DEV-13 fix; kept locally for provenance, excluded
from the repository so it cannot be mistaken for live state.
