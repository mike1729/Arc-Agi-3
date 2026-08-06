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
OUTPUT = ROOT / "logs/e2_slice3_regraded.json"
FORMAT_VERSION = 1


def targets(level: int) -> dict[str, dict[str, Any]]:
    path = ROOT / "logs/e2_expressibility.json"
    document = json.loads(path.read_text())
    return {
        row["game"]: row
        for row in document["results"]
        if row.get("vocab") == "v2" and row.get("level") == level and row.get("searched")
    }


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
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    target_rows = targets(args.level)
    rows: list[dict[str, Any]] = []
    for seed in args.seeds:
        path = ROOT / f"logs/e2_slice3_seed{seed}.json"
        document = json.loads(path.read_text())
        for cell in document["cells"]:
            row = regrade_cell(cell, target_rows.get(cell["game"]), args.level)
            row["seed"] = seed
            rows.append(row)
            human = row.get("human") or {}
            print(
                f"s{seed} {row['game']:5s} {row['verdict']:12s} "
                f"night={row['night_outcome'] or row['night_status']:14s} "
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

    reachable = [r for r in rows if r["verdict"] not in ("unreachable", "prose_rejected")]
    correct = [r for r in reachable if r["verdict"] == "correct"]
    print(
        f"channel A on the cells that were answerable at all: "
        f"{len(correct)}/{len(reachable)} correct"
    )

    args.out.write_text(
        json.dumps(
            {
                "format_version": FORMAT_VERSION,
                "generated_by": "agent/harness/e2_regrade_slice3.py",
                "note": "notes/e2-slice3.md RUN RESULTS — the night re-graded under the fixed grader",
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
