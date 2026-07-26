# PUBLISHING POLICY — read before making anything public

**Decision, 2026-07-26. This repository is never made public.**

When entrant-authored work has to be open-sourced — which competition prize eligibility requires — it is
published as a **new, clean repository**, built from scratch and containing only our own code. This
repository stays private permanently.

---

## Why

`agent/reference/` contains a third-party snapshot with **no declared licence**: the Tufa Labs TAAF
source bundle (`kaggle datasets metadata` returns `licenses: []` for it and for the associated weights
and wheelhouse datasets). We retain it because retaining a snapshot in a **private** repository for local
measurement is not redistribution. Publishing it would be.

The reproduction is a **local measurement vehicle only** — never shipped, never submitted, never
published (`gate_manifest.yaml → s1.results.threshold_verdicts.license_third_party`).

## The trap this policy exists to avoid

**Deleting the directory is not sufficient. Git history counts as redistribution.**

`agent/reference/taaf/` is committed. Making this repository public would distribute it **even if the
directory were deleted in the tip commit**, because every prior commit still contains it. Any of the
following would leak it:

- flipping this repository to public
- pushing this repository's history to a public remote
- opening a PR from this repository to a public one
- publishing a fork, mirror, or archive of it
- attaching a repository bundle or tarball to anything public

## What to do instead

1. Create a **new repository**.
2. Copy in only **entrant-authored** work — our harness, instrumentation, analysis scripts, notes,
   manifest, and paper material.
3. Do **not** copy `agent/reference/`, `agent/work/`, `data/`, or `logs/`, and do **not** import this
   repository's history.
4. Licence the new repository per bucket 1: **CC0 / MIT-0**.
5. Re-derive anything that referenced vendored paths so the new repository stands alone.

## What is safe to publish

| | |
|---|---|
| our harness and analysis scripts (`agent/harness/`) | **safe** — entrant-authored |
| `gate_manifest.yaml`, `notes/`, `paper/` | **safe** — entrant-authored |
| `agent/patches/` | **check first** — patches quote reference source in context lines |
| `agent/reference/` | **NEVER** |
| `agent/work/` | **NEVER** — built from the reference |
| `data/` | **NEVER** — competition environment files |
| `logs/` | **check first** — run artifacts embed reference prompts and model output |

`agent/patches/` and `logs/` are the easy mistakes: both look like our own work and both contain
reference-derived material.

---

*Cross-referenced from `README.md`, `agent/reference/README.md`,
`gate_manifest.yaml → s1.results.threshold_verdicts.license_third_party`, and
`notes/s1-reference-freeze.md` §4.*
