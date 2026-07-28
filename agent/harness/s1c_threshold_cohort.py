"""Aggregate the S1-e breadth run into the S1 threshold cohort — reproducibly.

WHY THIS EXISTS
---------------
`gate_manifest.yaml -> s1.threshold_verdicts` recorded `legal_action_validity` as "349 executed / 355
requested = 0.9831 across 26 games" and `per_action_latency_p50` as "median 139.39 s across 26 games",
against a single `evidence_ref` pointing at `logs/s1c_20260726_164355_s1e-dense-c01.json`. Three
problems, found 2026-07-27:

  1. That path does not exist. The file is at `logs/quarantine/s1c_20260726_164355_s1e-dense-c01.json`
     — a QUARANTINED run (superseded config, MANIFEST.json), and `logs/quarantine/` is untracked. A
     frozen threshold cannot cite evidence that is neither at the stated path nor in the repository.
  2. One chunk file was never the cohort. The verdicts aggregate the whole S1-e breadth run — 27
     tracked `logs/s1c_*s1e*.json` chunk files — and no file said so.
  3. "26 games" is not the validity denominator. 26 is the number of game-runs carrying a
     `per_decision` p50, i.e. the LATENCY sample. The validity figure sums over 32 game-run records
     spanning 18 distinct games (chunked runs repeat a game across files). One number described two
     different cohorts.

The counts themselves are sound and reproduce exactly — see `verify` below. What was missing is the
statement of WHICH game-runs they cover. This script is that statement, executable.

THE ADMISSIBILITY SPLIT — the one substantive finding
------------------------------------------------------
The recorded figures include every game-run record, WITHOUT the S1-E9 admissibility filter that
`s1d_build_corpus.py` applies to the labelling corpus (agent-finished OR consumed the full uniform
budget; early stops are operator kills). 5 of the 32 records are not concluded.

Both cohorts are computed and written, because the choice is a pre-registration matter, not a coding
one. Neither changes a verdict direction:

    all_records   349/355 = 0.9831   p50 median 139.39 s     <- what the manifest recorded
    concluded     344/350 = 0.9829   p50 median 144.66 s     <- S1-E9 admissibility applied
    thresholds        >= 0.95                 <= 225.00 s     both PASS under either

Run:
  .venv/bin/python agent/harness/s1c_threshold_cohort.py --out logs/s1c_threshold_cohort.json
  .venv/bin/python agent/harness/s1c_threshold_cohort.py --verify   # exit 1 if figures moved
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
from pathlib import Path

# The frozen thresholds these figures are compared against (gate_manifest.yaml, S1-E12 for latency).
VALIDITY_THRESHOLD = 0.95
LATENCY_P50_THRESHOLD_S = 225.00

# What the manifest recorded, so drift is caught rather than discovered later.
RECORDED = {"executed": 349, "requested": 355, "latency_p50_median_s": 139.39}


def cohort_files() -> list[str]:
    """The S1-e breadth run, as tracked by git. Tracked-only and glob-defined so the cohort cannot
    quietly acquire an untracked or quarantined file."""
    out = subprocess.check_output(["git", "ls-files", "logs/s1c_*s1e*.json"], text=True)
    return sorted(f for f in out.split() if f)


def aggregate(files: list[str], concluded_only: bool) -> dict:
    requested = executed = 0
    p50s: list[float] = []
    actions: list[int] = []
    decisions: list[int] = []
    records: list[dict] = []

    for f in files:
        data = json.loads(Path(f).read_text())
        for key, g in (data.get("per_game") or {}).items():
            if concluded_only and not g.get("concluded"):
                continue
            lar = g.get("legal_action_reliability") or {}
            req, exe = lar.get("requested_actions"), lar.get("executed_actions")
            if req is not None and exe is not None:
                requested += req
                executed += exe
            lat = g.get("per_action_latency") or {}
            per_dec = lat.get("per_decision") or {}
            if per_dec.get("p50_s") is not None:
                p50s.append(per_dec["p50_s"])
            if lat.get("n_actions"):
                actions.append(lat["n_actions"])
            if per_dec.get("n"):
                decisions.append(per_dec["n"])
            records.append({"pass_key": key, "game": re.sub(r"_p\d+$", "", key), "chunk": f,
                            "concluded": g.get("concluded"), "state": g.get("state"),
                            "requested_actions": req, "executed_actions": exe,
                            "per_decision_p50_s": per_dec.get("p50_s")})

    validity = (executed / requested) if requested else None
    p50_median = round(statistics.median(p50s), 2) if p50s else None
    return {
        "admissibility": ("S1-E9: agent-finished OR consumed the full uniform budget"
                          if concluded_only else
                          "NONE — every game-run record, including runs that stopped early"),
        "n_game_run_records": len(records),
        "n_distinct_games": len({r["game"] for r in records}),
        "n_not_concluded": sum(1 for r in records if not r["concluded"]),
        "legal_action_validity": {
            "executed": executed, "requested": requested,
            "validity": round(validity, 4) if validity is not None else None,
            "threshold": VALIDITY_THRESHOLD,
            "verdict": None if validity is None else ("PASS" if validity >= VALIDITY_THRESHOLD else "FAIL"),
        },
        "per_action_latency_p50": {
            "per_decision_p50_median_s": p50_median,
            "n_game_runs_with_latency": len(p50s),
            "threshold_s": LATENCY_P50_THRESHOLD_S,
            "verdict": None if p50_median is None else
                       ("PASS" if p50_median <= LATENCY_P50_THRESHOLD_S else "FAIL"),
        },
        "scalar_derivation": {
            "median_actions_per_game": statistics.median(actions) if actions else None,
            "median_decisions_per_game": statistics.median(decisions) if decisions else None,
        },
        "game_run_records": sorted(records, key=lambda r: (r["chunk"], r["pass_key"])),
    }


def build(out: Path) -> int:
    files = cohort_files()
    all_records = aggregate(files, concluded_only=False)
    concluded = aggregate(files, concluded_only=True)
    payload = {
        "built": "s1c_threshold_cohort.py",
        "purpose": ("the exact cohort behind s1.threshold_verdicts.legal_action_validity and "
                    ".per_action_latency_p50. Supersedes the single-file evidence_ref, which pointed "
                    "at a quarantined, untracked path."),
        "cohort_definition": ("every game-run record in the tracked S1-e chunk files matched by "
                              "`git ls-files logs/s1c_*s1e*.json`. Chunked runs repeat a game across "
                              "files, so records exceed distinct games; this is the measured unit."),
        "n_chunk_files": len(files),
        "chunk_files": files,
        "cohorts": {"all_records": all_records, "concluded_only": concluded},
        "recorded_in_manifest": RECORDED,
        "reproduces_recorded": (
            all_records["legal_action_validity"]["executed"] == RECORDED["executed"]
            and all_records["legal_action_validity"]["requested"] == RECORDED["requested"]
            and all_records["per_action_latency_p50"]["per_decision_p50_median_s"]
            == RECORDED["latency_p50_median_s"]),
        "note_on_26_games": ("the manifest's '26 games' is the LATENCY sample size "
                             f"({all_records['per_action_latency_p50']['n_game_runs_with_latency']} "
                             "game-runs carry a per_decision p50), not the validity denominator "
                             f"({all_records['n_game_run_records']} records over "
                             f"{all_records['n_distinct_games']} distinct games)."),
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"cohort: {len(files)} tracked chunk files")
    for name in ("all_records", "concluded_only"):
        c = payload["cohorts"][name]
        v, lat = c["legal_action_validity"], c["per_action_latency_p50"]
        print(f"\n  {name}  ({c['n_game_run_records']} records, {c['n_distinct_games']} games, "
              f"{c['n_not_concluded']} not concluded)")
        print(f"     validity  {v['executed']}/{v['requested']} = {v['validity']} "
              f"vs >= {v['threshold']}  -> {v['verdict']}")
        print(f"     latency   p50 median {lat['per_decision_p50_median_s']} s "
              f"(n={lat['n_game_runs_with_latency']}) vs <= {lat['threshold_s']} s -> {lat['verdict']}")
    print(f"\nreproduces the recorded manifest figures: {payload['reproduces_recorded']}")
    print(f"wrote {out}")
    return 0


def verify() -> int:
    """Non-zero exit if the tracked logs no longer produce the recorded figures."""
    got = aggregate(cohort_files(), concluded_only=False)
    v = got["legal_action_validity"]
    lat = got["per_action_latency_p50"]["per_decision_p50_median_s"]
    ok = (v["executed"], v["requested"], lat) == (
        RECORDED["executed"], RECORDED["requested"], RECORDED["latency_p50_median_s"])
    print(f"recorded : {RECORDED['executed']}/{RECORDED['requested']}, "
          f"p50 median {RECORDED['latency_p50_median_s']} s")
    print(f"recomputed: {v['executed']}/{v['requested']}, p50 median {lat} s")
    print("MATCH" if ok else "DRIFT — the manifest figures no longer reproduce")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/s1c_threshold_cohort.json")
    ap.add_argument("--verify", action="store_true",
                    help="recompute and compare against the figures recorded in the manifest")
    args = ap.parse_args()
    return verify() if args.verify else build(Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
