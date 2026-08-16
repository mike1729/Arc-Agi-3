#!/usr/bin/env python3
"""Re-grade the slice-3 night under the fixed grader. Zero model calls.

`notes/e2-slice3.md` → RUN RESULTS. The night's verdicts were produced by a grader with
three defects the readout then found: it graded one direction on six of eight games, it
reported a binary where the answer was a rate, and it graded against perfection on games
whose answer may not exist in the grammar. All three are fixed
(`e2_positives`, `dsl.contradiction_scan`, `e2_expressibility`), and the night's answers are
still on disk — so the corrected verdict is computable without spending another GPU hour.

This re-grades the PREDICATE the model actually wrote, character for character, from
`logs/e2_slice3_seed{1,2}.json`. Nothing is re-parsed leniently and nothing is repaired: a
cell recorded `prose_rejected` stays rejected.

Run:
  .venv/bin/python agent/harness/e2_regrade_slice3.py
  # 3.8 night (notes/qwen-3.8-night1.md):
  .venv/bin/python agent/harness/e2_regrade_slice3.py --results "logs/e2_slice38_seed{seed}.json"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_dsl as dsl  # noqa: E402
import e2_expressibility as expr  # noqa: E402
import e2_positives as positives  # noqa: E402

ROOT = positives.ROOT
RESULTS_TEMPLATE = "logs/e2_slice3_seed{seed}.json"
FORMAT_VERSION = 1


def targets(level: int) -> dict[str, dict[str, Any]]:
    path = ROOT / "logs/e2_expressibility.json"
    document = json.loads(path.read_text())
    return {
        row["game"]: row
        for row in document["results"]
        if row.get("vocab") == "v2" and row.get("level") == level and row.get("searched")
    }


# Cells the night never answered — over-cap skips, thinking voids, unparsed extractions
# (all end `e2_slice.run_cell` before channel A exists). Missing observations, never model
# failures: they join no denominator, and a night with them is smaller, not worse.
MISSING_OBSERVATION = ("skipped", "void", "unparsed", "no_answer")


def regrade_cell(cell: dict[str, Any], target: dict[str, Any] | None, level: int) -> dict[str, Any]:
    game = cell["game"]
    channel = cell.get("channel_a") or {}
    written = (channel.get("predicate") or {}).get("text")
    out: dict[str, Any] = {
        "game": game,
        "as_written": written,
        "night_status": channel.get("status"),
        "night_outcome": (channel.get("store_consistency") or {}).get("outcome"),
        "free_form": ((channel.get("free_form") or {}).get("text") or "")[:200],
    }
    if not channel:
        night = str(cell.get("outcome") or cell.get("skipped") or "")
        if cell.get("skipped"):
            out["verdict"] = "skipped"
        elif night.startswith("VOID"):
            out["verdict"] = "void"
        elif night == "unparsed extraction":
            out["verdict"] = "unparsed"
        else:
            out["verdict"] = "no_answer"
        out["status"] = "absent"
        out["night_outcome"] = night or "no channel_a in cell"
        out["missing_observation"] = True
        return out
    parsed = dsl.classify_predicate(written)
    if parsed["status"] != "parsed":
        out["status"] = "prose_rejected"
        out["verdict"] = "prose_rejected"
        return out

    graded = positives.grade(parsed["ast"], game, level=level)
    out["status"] = "parsed"
    out["canonical"] = parsed["canonical"]
    out["human"] = {
        "positives": graded["positive"]["rows"],
        "fires_at": graded["positive"]["correct"],
        "positive_unknown": graded["positive"]["unknown"],
        "negatives_decidable": graded["negative"]["evaluable"],
        "false_positives": graded["negative"]["wrong"],
        "negative_error_rate": graded["negative"]["error_rate"],
        "holds_at_every_completion": graded["holds_at_every_completion"],
        "fires_only_at_completions": graded["fires_only_at_completions"],
    }
    if target is None:
        out["verdict"] = "no_target"
        return out
    out["target"] = {
        "expressible": target["expressible"],
        "simplest": (target.get("simplest") or {}).get("predicate"),
        "separators": target["separators"],
        "best_rate": 0.0
        if target["expressible"]
        else (target.get("closest_miss") or {}).get("contradiction_rate"),
    }
    if not target["expressible"]:
        # The model cannot be scored wrong for failing to write something the grammar
        # cannot state. This verdict is the one the night's binary could not produce.
        out["verdict"] = "unreachable"
    elif graded["holds_at_every_completion"] and graded["fires_only_at_completions"]:
        out["verdict"] = "correct"
    elif graded["positive"]["correct"] == 0:
        # Fires on no solved board at all. The vacuous failure the one-directional grader
        # scored as `survived`.
        out["verdict"] = "vacuous"
    else:
        out["verdict"] = "wrong"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, nargs="*", default=[1, 2])
    parser.add_argument("--level", type=int, default=1)
    parser.add_argument(
        "--results",
        default=RESULTS_TEMPLATE,
        help="input path template, repo-relative; {seed} fills per seed "
        "(the 3.8 night reads logs/e2_slice38_seed{seed}.json)",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    # The default output moves with the results it grades: a 3.8 regrade left on the 3.6
    # default path would overwrite committed 3.6 measurement data — the same collision
    # `e2_slice.py` already paid for once (2026-08-05, recovered from git).
    if args.out is None:
        if "_seed{seed}.json" not in args.results:
            parser.error("--results has no '_seed{seed}.json' suffix; pass --out explicitly")
        args.out = ROOT / args.results.replace("_seed{seed}.json", "_regraded.json")

    target_rows = targets(args.level)
    rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        path = ROOT / args.results.format(seed=seed)
        document = json.loads(path.read_text())
        for cell in document["cells"]:
            row = regrade_cell(cell, target_rows.get(cell["game"]), args.level)
            row["seed"] = seed
            rows.append(row)
            human = row.get("human") or {}
            print(
                f"s{seed} {row['game']:5s} {row['verdict']:12s} "
                f"night={row['night_outcome'] or row['night_status'] or '—':14s} "
                f"fires at {human.get('fires_at', '-')}/{human.get('positives', '-')} solved boards, "
                f"{human.get('false_positives', '-')} false positives "
                f"({human.get('negative_error_rate')})",
                flush=True,
            )
            if row.get("target") and not row["target"]["expressible"]:
                print("        (no predicate in the grammar separates this game)", flush=True)

    tally: dict[str, int] = {}
    for row in rows:
        tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1
    print("\n" + "  ".join(f"{k}={v}" for k, v in sorted(tally.items())))

    missing = [r for r in rows if r["verdict"] in MISSING_OBSERVATION]
    reachable = [
        r
        for r in rows
        if r["verdict"] not in ("unreachable", "prose_rejected") + MISSING_OBSERVATION
    ]
    correct = [r for r in reachable if r["verdict"] == "correct"]
    print(
        f"channel A on the cells that were answerable at all: "
        f"{len(correct)}/{len(reachable)} correct"
    )
    if missing:
        print(
            f"missing observations (skipped/void/unparsed): {len(missing)} of {len(rows)} "
            f"cells — absent from every denominator; the night is smaller, not worse"
        )

    args.out.write_text(
        json.dumps(
            {
                "format_version": FORMAT_VERSION,
                "generated_by": "agent/harness/e2_regrade_slice3.py",
                "note": "notes/e2-slice3.md RUN RESULTS — the night re-graded under the fixed grader",
                "results": args.results,
                "level": args.level,
                "corpus": "human_replays (positives and negatives); the night graded negatives on the explorer store",
                "tally": tally,
                "cells": rows,
            },
            indent=1,
        )
        + "\n"
    )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
