#!/usr/bin/env python3
"""E1-pre — click-candidate recall diagnostic (zero model calls).

The E1 explorer reaches ACTION6 through a capped, segmentation-derived candidate set
(`notes/e1-explorer.md` SS2). That makes the whole explorer hostage to one untested
assumption: that the clicks worth making are *in the pool*. This measures it on data
already on disk — every human L1 ACTION6 in the replay corpus, scored against the
candidate set the explorer would have generated from the same pre-click settled frame.

TWO METRICS, REPORTED APART
---------------------------
    cell recall   the human's exact (y, x) IS a generated candidate point
    node recall   the human's (y, x) falls inside some candidate's component

Clicking anywhere inside a node may or may not be equivalent to clicking where the human
clicked — the engine decides, and this diagnostic does not know. The gap between the two
numbers is that uncertainty, stated rather than assumed away in either direction.

SEGMENTATION
------------
4-connected same-colour components of the pre-click settled frame, via
``gi2_observation.componentize`` — the same segmentation E0 used, with one deliberate
difference: background-coloured components are KEPT. ``es_candidates._Objects`` drops
them because a background region is not an object; but placement games click *locations*,
and the canvas is exactly where. Nested components are included by construction (flat
connected-component labelling gives an enclosed region its own node).

Candidate point per node: the centroid cell if the centroid lies inside the node, else its
top-left-most cell. The fallback matters for rings and L-shapes, whose centroid is a hole.

CULLING (SS2, cap 64)
---------------------
Stratified, never a plain size sort: one representative per distinct (colour, shape) class,
plus the largest node unconditionally, then remaining slots to class-duplicates. A size-
ascending cull would evict the canvas first, which is backwards.

SS2 specifies the duplicate fill as smallest-first. MEASURED, and changed: smallest-first
spends the entire leftover budget on single-cell dust, which is what actually costs bp35 its
recall (0.610 — 91.8% of its components are one cell, while its human targets have median
size 21). Filling largest-first instead keeps every distinct class (so a legitimate 1-cell
target still enters as its class representative — 15-20% of human clicks on ka59, su15, r11l,
ar25 land on one) and spends the remainder on objects rather than dust: bp35 0.610 -> 0.986
at cap 96, with no game made worse. A blanket minimum-node-size filter was measured too and
REJECTED: it fixes bp35 and breaks six games whose humans click single pixels.

``fill="smallest"`` reproduces the SS2 rule for comparison.

Where representatives ALONE exceed the cap, the cap is binding on classes and the retained
set is largest-node-first then size-descending. Every miss is attributed — background,
cap-culled, or absent from segmentation — because the three have different fixes and only
one of them (cap) is a knob.

NO THRESHOLD IS PRE-REGISTERED. The measured number decides, game by game.

Run:
  .venv/bin/python agent/harness/e1_candidates.py --jobs 6
  .venv/bin/python agent/harness/e1_candidates.py --games <all 24> --out logs/e1_pre_all.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from es_questions import modal_color  # noqa: E402
from gi2_observation import componentize  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    EXCLUDED_GAMES,
    ITERATION_GAMES,
    ROOT,
    load_game,
)

OUTPUT = ROOT / "logs/e1_pre.json"
FORMAT_VERSION = 1

CANDIDATE_CAP = 64  # (w) notes/e1-explorer.md SS2


# ======================================================================================
# Segmentation -> candidates
# ======================================================================================


def _shape_key(cells: frozenset) -> tuple:
    top = min(row for row, _ in cells)
    left = min(col for _, col in cells)
    return tuple(sorted((row - top, col - left) for row, col in cells))


def _point(cells: frozenset) -> tuple[int, int]:
    """Centroid if it lands inside the node, else the top-left-most cell."""
    rows = [row for row, _ in cells]
    cols = [col for _, col in cells]
    centre = (round(sum(rows) / len(rows)), round(sum(cols) / len(cols)))
    if centre in cells:
        return centre
    return min(cells)


def segment(grid: list) -> list[dict[str, Any]]:
    background = modal_color(grid)
    nodes = []
    for component in componentize(grid):
        cells = frozenset(component.cells)
        nodes.append(
            {
                "colour": int(component.color),
                "cells": cells,
                "size": len(cells),
                "point": _point(cells),
                "shape": _shape_key(cells),
                "background": int(component.color) == background,
            }
        )
    return nodes


def cull(
    nodes: list[dict[str, Any]], cap: int = CANDIDATE_CAP, fill: str = "largest"
) -> list[dict[str, Any]]:
    """Stratified over-cap culling. Returns the retained nodes."""
    if len(nodes) <= cap:
        return list(nodes)

    order = {id(node): index for index, node in enumerate(nodes)}
    classes: dict[tuple, list[dict[str, Any]]] = {}
    for node in nodes:
        classes.setdefault((node["colour"], node["shape"]), []).append(node)

    # one representative per class: the top-left-most member, deterministically
    reps = [
        min(members, key=lambda node: (min(node["cells"]), order[id(node)]))
        for members in classes.values()
    ]
    largest = max(nodes, key=lambda node: (node["size"], -order[id(node)]))

    kept: list[dict[str, Any]] = [largest]
    kept_ids = {id(largest)}

    if len(reps) + (0 if id(largest) in {id(r) for r in reps} else 1) > cap:
        # the cap binds on CLASSES, not on duplicates — keep the biggest classes
        for node in sorted(reps, key=lambda node: (-node["size"], order[id(node)])):
            if len(kept) >= cap:
                break
            if id(node) not in kept_ids:
                kept.append(node)
                kept_ids.add(id(node))
        return kept

    for node in sorted(reps, key=lambda node: order[id(node)]):
        if id(node) not in kept_ids:
            kept.append(node)
            kept_ids.add(id(node))

    duplicates = [node for node in nodes if id(node) not in kept_ids]
    sign = 1 if fill == "smallest" else -1
    for node in sorted(duplicates, key=lambda node: (sign * node["size"], order[id(node)])):
        if len(kept) >= cap:
            break
        kept.append(node)
        kept_ids.add(id(node))
    return kept


# ======================================================================================
# Scoring
# ======================================================================================


def _completing_sessions(transitions: list) -> set[str]:
    return {row.guid for row in transitions if row.completed}


def score_game(job: tuple[str, tuple[int, ...]]) -> dict[str, Any]:
    game, caps = job
    transitions = load_game(game, max_level=1)
    completing = _completing_sessions(transitions)
    clicks = [row for row in transitions if row.action_id == 6]

    rows: list[dict[str, Any]] = []
    node_counts: list[int] = []
    sweep: dict[int, list[dict[str, bool]]] = {cap: [] for cap in caps}
    kept_counts: dict[int, list[int]] = {cap: [] for cap in caps}
    for row in clicks:
        target_row, target_col = row.action_data.get("y"), row.action_data.get("x")
        if not isinstance(target_row, int) or not isinstance(target_col, int):
            continue
        height = len(row.pre)
        width = len(row.pre[0]) if height else 0
        if not (0 <= target_row < height and 0 <= target_col < width):
            continue

        nodes = segment(row.pre)
        node_counts.append(len(nodes))
        owner = next(
            (node for node in nodes if (target_row, target_col) in node["cells"]), None
        )

        primary: dict[str, Any] = {}
        for cap in caps:
            kept = cull(nodes, cap)
            kept_ids = {id(node) for node in kept}
            kept_counts[cap].append(len(kept))
            hits = {
                "cell_hit": any(
                    node["point"] == (target_row, target_col) for node in kept
                ),
                "node_hit": owner is not None and id(owner) in kept_ids,
            }
            sweep[cap].append(hits)
            if cap == CANDIDATE_CAP:
                primary = hits

        if primary.get("node_hit"):
            miss = None
        elif owner is None:
            miss = "unsegmented"  # cannot happen with flat labelling; recorded if it does
        elif len(nodes) > CANDIDATE_CAP:
            miss = "cap_culled"
        else:
            miss = "absent"

        rows.append(
            {
                "guid": row.guid,
                "step": row.step,
                "cell_hit": primary.get("cell_hit", False),
                "node_hit": primary.get("node_hit", False),
                "miss": miss,
                "background": bool(row.guards.get("click_on_background")),
                "on_path": row.guid in completing,
                "completing": row.completed,
                "nodes": len(nodes),
                "target_node_size": owner["size"] if owner else None,
            }
        )

    def recall(subset: list[dict[str, Any]], field: str) -> float | None:
        return (
            sum(1 for r in subset if r[field]) / len(subset) if subset else None
        )

    on_path = [r for r in rows if r["on_path"]]
    foreground = [r for r in rows if not r["background"]]
    background = [r for r in rows if r["background"]]
    completing_clicks = [r for r in rows if r["completing"]]

    return {
        "game": game,
        "clicks": len(rows),
        "sessions_completing_l1": len(completing),
        "cell_recall": recall(rows, "cell_hit"),
        "node_recall": recall(rows, "node_hit"),
        "cell_recall_on_path": recall(on_path, "cell_hit"),
        "node_recall_on_path": recall(on_path, "node_hit"),
        "cell_recall_foreground": recall(foreground, "cell_hit"),
        "node_recall_foreground": recall(foreground, "node_hit"),
        "cell_recall_background": recall(background, "cell_hit"),
        "node_recall_background": recall(background, "node_hit"),
        "completing_clicks": len(completing_clicks),
        "cell_recall_completing": recall(completing_clicks, "cell_hit"),
        "node_recall_completing": recall(completing_clicks, "node_hit"),
        "on_path_clicks": len(on_path),
        "background_clicks": len(background),
        "miss_split": dict(Counter(r["miss"] for r in rows if r["miss"])),
        "nodes_median": statistics.median(node_counts) if node_counts else None,
        "nodes_max": max(node_counts) if node_counts else None,
        "over_cap_states": sum(1 for r in rows if r["nodes"] > CANDIDATE_CAP),
        # cap sweep: recall bought against branching factor paid, per candidate cap
        "sweep": {
            str(cap): {
                "cell_recall": (
                    sum(1 for h in sweep[cap] if h["cell_hit"]) / len(sweep[cap])
                    if sweep[cap]
                    else None
                ),
                "node_recall": (
                    sum(1 for h in sweep[cap] if h["node_hit"]) / len(sweep[cap])
                    if sweep[cap]
                    else None
                ),
                "candidates_median": (
                    statistics.median(kept_counts[cap]) if kept_counts[cap] else None
                ),
            }
            for cap in caps
        },
    }


def _fmt(value: float | None) -> str:
    return " n/a " if value is None else f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--all", action="store_true", help="every game E0 measured")
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument(
        "--caps",
        type=int,
        nargs="*",
        default=[32, 64, 96, 128, 192, 256],
        help="candidate caps to sweep; the SS2 cap of 64 drives the printed columns",
    )
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    games = (
        [game for game in ALL_GAMES if game not in EXCLUDED_GAMES]
        if args.all
        else list(args.games)
    )
    caps = tuple(sorted(set(args.caps) | {CANDIDATE_CAP}))

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(score_game, [(game, caps) for game in games]))

    print(
        f"{'game':5s} {'clicks':>7s} {'cell':>6s} {'node':>6s} | "
        f"{'fg-cell':>7s} {'fg-node':>7s} | {'bg':>6s} {'bg-node':>7s} | "
        f"{'nodes':>6s} {'>cap':>5s}"
    )
    for row in results:
        print(
            f"{row['game']:5s} {row['clicks']:7d} "
            f"{_fmt(row['cell_recall'])} {_fmt(row['node_recall'])} | "
            f"{_fmt(row['cell_recall_foreground'])} {_fmt(row['node_recall_foreground'])} | "
            f"{row['background_clicks']:6d} {_fmt(row['node_recall_background'])} | "
            f"{str(row['nodes_median']):>6s} {row['over_cap_states']:5d}",
            flush=True,
        )

    measured = [row for row in results if row["clicks"]]
    if measured:
        print("\ncap sweep — node recall (median candidates/state)")
        print("game  " + "".join(f"{cap:>16d}" for cap in caps))
        for row in measured:
            cells = "".join(
                f"{row['sweep'][str(cap)]['node_recall']:>10.3f}"
                f" ({row['sweep'][str(cap)]['candidates_median']:.0f})".rjust(6)
                for cap in caps
            )
            print(f"{row['game']:5s} {cells}", flush=True)

    document = {
        "format_version": FORMAT_VERSION,
        "candidate_cap": CANDIDATE_CAP,
        "caps_swept": list(caps),
        "games": {row["game"]: row for row in results},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
