# SHiP-JEPA-X

ARC Prize 2026 / ARC-AGI-3 — JEPA-style latent world models for interactive reasoning.

> ## ⛔ THIS REPOSITORY IS NEVER MADE PUBLIC
>
> It contains a third-party snapshot with **no declared licence** (`agent/reference/`). When
> entrant-authored work must be open-sourced, publish a **new, clean repository** built from scratch —
> do not flip this one to public, and do not import its history.
>
> **Deleting the directory is not enough: git history counts as redistribution.**
>
> See **[PUBLISHING.md](PUBLISHING.md)** before publishing anything.

## Layout

| path | contents | publishable |
|---|---|---|
| `agent/harness/` | our measurement, labelling and run tooling | yes |
| `agent/reference/` | vendored third-party snapshot | **never** |
| `agent/work/` | throwaway working copy, rebuilt from reference + patches | **never** |
| `agent/patches/` | our deviations as patch files | check — quotes reference source |
| `gate_manifest.yaml` | pre-registration; append-only, dated errata | yes |
| `notes/` | verification record, reference freeze, measurements, close-out | yes |
| `paper/` | hypotheses, related work, methods, script-generated figures | yes |
| `data/`, `logs/` | competition env files; run artifacts | **never** / check |

## Orientation

- `gate_manifest.yaml` — what was pre-registered, and every dated erratum since
- `notes/s1-reference-freeze.md` — which baseline was frozen and why
- `notes/s1-measurements.md` — what has been measured, and what was withdrawn
- `paper/hypotheses.md` — hypotheses with their refutation conditions
