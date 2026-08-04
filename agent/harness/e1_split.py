#!/usr/bin/env python3
"""E1-pre split-half control — is cap 96 + largest-first fill a property of the generator,
or of this corpus?

`e1_candidates.py` swept (cap x fill) over all 4,161 L1 clicks, adopted the pair that scored
best, and reported that pair's score on the same clicks. That number is in-sample and can only
be an upper estimate. This runs the control E0 carried and E1-pre did not.

PROTOCOL
--------
Sessions split by ``sha256(guid)`` last-hex-digit parity — the fixed
``rs_transitions.split_half`` convention, session-level and never per click, so no game's
sessions leak across the boundary. Then, in BOTH directions:

    select on half A (pooled over games, since the parameter is one global choice)
        -> report node recall on half B, which selection never saw

Pooled selection matches how the parameter is actually used: one cap and one fill order for
every game. Per-game held-out recall under the ADOPTED (96, largest-first) pair is reported
alongside, because that is the number the design note now cites.

The honest comparison is in-sample vs held-out for the SAME pair, and whether selection on a
half recovers the same pair at all. A pair that wins on one half and loses on the other was
fit to noise.

Run:
  .venv/bin/python agent/harness/e1_split.py --all --jobs 8 --out logs/e1_pre_split.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from e1_candidates import CANDIDATE_CAP, cull, segment  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    EXCLUDED_GAMES,
    ITERATION_GAMES,
    ROOT,
    load_game,
)

OUTPUT = ROOT / "logs/e1_pre_split.json"
FORMAT_VERSION = 1

CAPS = (32, 48, 64, 96, 128, 192)
FILLS = ("smallest", "largest")
ADOPTED = (96, "largest")


def _half(guid: str) -> str:
    """rs_transitions.split_half, as a label rather than a partition."""
    return "A" if int(hashlib.sha256(guid.encode()).hexdigest()[-1], 16) % 2 == 0 else "B"


def measure(game: str) -> dict[str, Any]:
    """Per-click hit table over the whole (cap x fill) grid, tagged with its half."""
    clicks = [row for row in load_game(game, max_level=1) if row.action_id == 6]
    rows: list[dict[str, Any]] = []
    for row in clicks:
        target = (row.action_data.get("y"), row.action_data.get("x"))
        if not isinstance(target[0], int) or not isinstance(target[1], int):
            continue
        height = len(row.pre)
        width = len(row.pre[0]) if height else 0
        if not (0 <= target[0] < height and 0 <= target[1] < width):
            continue
        nodes = segment(row.pre)
        owner = next((node for node in nodes if target in node["cells"]), None)
        hits = {}
        for cap in CAPS:
            for fill in FILLS:
                kept = cull(nodes, cap, fill)
                hits[f"{cap}:{fill}"] = owner is not None and id(owner) in {
                    id(node) for node in kept
                }
        rows.append({"half": _half(row.guid), "hits": hits})
    return {"game": game, "rows": rows}


def _recall(rows: list[dict[str, Any]], key: str) -> float | None:
    return sum(1 for row in rows if row["hits"][key]) / len(rows) if rows else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    games = (
        [game for game in ALL_GAMES if game not in EXCLUDED_GAMES]
        if args.all
        else list(args.games)
    )
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = [row for row in pool.map(measure, games) if row["rows"]]

    per_game = {row["game"]: row["rows"] for row in results}
    pooled = [click for rows in per_game.values() for click in rows]
    halves = {half: [c for c in pooled if c["half"] == half] for half in ("A", "B")}
    keys = [f"{cap}:{fill}" for cap in CAPS for fill in FILLS]

    print(f"clicks: A={len(halves['A'])}  B={len(halves['B'])}  total={len(pooled)}")
    print(f"sessions split by sha256(guid) parity; {len(per_game)} games\n")

    # --- selection in both directions ------------------------------------------------
    directions = {}
    for select, holdout in (("A", "B"), ("B", "A")):
        scored = sorted(
            keys,
            # best recall on the selection half; ties to the SMALLER cap, then to the
            # fill order as listed — a tie must not be broken by the held-out number
            key=lambda key: (
                -(_recall(halves[select], key) or 0.0),
                int(key.split(":")[0]),
                FILLS.index(key.split(":")[1]),
            ),
        )
        best = scored[0]
        directions[select] = {
            "selected": best,
            "in_sample": _recall(halves[select], best),
            "held_out": _recall(halves[holdout], best),
            "adopted_in_sample": _recall(halves[select], f"{ADOPTED[0]}:{ADOPTED[1]}"),
            "adopted_held_out": _recall(halves[holdout], f"{ADOPTED[0]}:{ADOPTED[1]}"),
        }
        cell = directions[select]
        print(
            f"select on {select} -> hold out {holdout}:  picked {cell['selected']:>13s}  "
            f"in-sample {cell['in_sample']:.4f}  held-out {cell['held_out']:.4f}"
        )

    adopted_key = f"{ADOPTED[0]}:{ADOPTED[1]}"
    print(
        f"\nadopted {adopted_key}:  full-corpus (in-sample) "
        f"{_recall(pooled, adopted_key):.4f}  |  half A {_recall(halves['A'], adopted_key):.4f}"
        f"  half B {_recall(halves['B'], adopted_key):.4f}"
    )

    # --- per-game held-out recall under the adopted pair ------------------------------
    print(f"\nper-game node recall under adopted {adopted_key}")
    print(f"{'game':5s} {'nA':>5s} {'nB':>5s} {'half A':>8s} {'half B':>8s} {'pooled':>8s}")
    per_game_out = {}
    for game, rows in sorted(per_game.items()):
        left = [row for row in rows if row["half"] == "A"]
        right = [row for row in rows if row["half"] == "B"]
        per_game_out[game] = {
            "n_a": len(left),
            "n_b": len(right),
            "recall_a": _recall(left, adopted_key),
            "recall_b": _recall(right, adopted_key),
            "recall_pooled": _recall(rows, adopted_key),
        }
        cell = per_game_out[game]
        fmt = lambda value: "   n/a  " if value is None else f"{value:8.4f}"  # noqa: E731
        print(
            f"{game:5s} {len(left):5d} {len(right):5d} "
            f"{fmt(cell['recall_a'])} {fmt(cell['recall_b'])} {fmt(cell['recall_pooled'])}"
        )

    document = {
        "format_version": FORMAT_VERSION,
        "adopted": adopted_key,
        "caps": list(CAPS),
        "fills": list(FILLS),
        "clicks": {"A": len(halves["A"]), "B": len(halves["B"])},
        "directions": directions,
        "grid": {
            key: {
                "A": _recall(halves["A"], key),
                "B": _recall(halves["B"], key),
                "pooled": _recall(pooled, key),
            }
            for key in keys
        },
        "per_game": per_game_out,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
