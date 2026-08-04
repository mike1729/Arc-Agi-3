#!/usr/bin/env python3
"""E1-pre part 3 — can the explorer's click alphabet reach the L1 completion?

Parts 1 and 2 measure the candidate set against the human's clicks: is the human's node in
the pool (`e1_candidates.py`), and does clicking the node's point do the same thing
(`e1_equiv.py`). Part 2 answers "not always" — r11l 0.218, su15 0.466, tn36's eight
completing clicks 0.000. For those games the two recall numbers stop being informative and
the only question left is the operational one: standing where the human stood, does ANY point
the explorer would have tried complete the level?

METHOD
------
For every L1 ACTION6 that completed the level in the human recording: fork the engine at the
pre-click state and try, one deep copy each,

    candidates   the capped stratified candidate set (default cap 96 — part 1's measured
                 cap, not SS2's 64, which loses completion-path clicks on ft09)
    lattice      the contingent supplement of `notes/e1-explorer.md`: an 8x8 (w) evenly
                 spaced grid of probe points, added only because part 2 showed node-point
                 clicking is not outcome-equivalent on the placement games

and record whether the level advances. The human's own cell is replayed as a CONTROL: if it
does not complete on the fork, the measurement machinery is wrong for that game and its row
is reported as failed control rather than as a result.

Reachability is a strictly weaker and more honest bar than reproducing the human's click: a
different completing click is a win for the explorer.

Run:
  .venv/bin/python agent/harness/e1_reach.py --all --jobs 8 --out logs/e1_reach_all.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from arcengine import ActionInput, GameAction  # noqa: E402

from e1_candidates import cull, segment  # noqa: E402
from gi2_replay import ReplayDriver, _plain_frames, iter_recorded_actions  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    CORPUS,
    EXCLUDED_GAMES,
    EXCLUDED_SESSIONS,
    ITERATION_GAMES,
    ROOT,
)

OUTPUT = ROOT / "logs/e1_reach.json"
FORMAT_VERSION = 1

MEASURED_CAP = 96  # part 1: the smallest swept cap at node recall 1.000 on 17 of 18 games
LATTICE = 8  # (w) notes/e1-explorer.md, contingent background-probe supplement


def lattice_points(height: int, width: int, n: int = LATTICE) -> list[tuple[int, int]]:
    rows = sorted({int((index + 0.5) * height / n) for index in range(n)})
    cols = sorted({int((index + 0.5) * width / n) for index in range(n)})
    return [(row, col) for row in rows for col in cols if row < height and col < width]


def _completes(response: Any, base: int) -> bool:
    levels = response.levels_completed
    if levels is None:
        return str(getattr(response.state, "value", response.state)) == "WIN"
    return int(levels) > base


def _try(driver: ReplayDriver, engine: Any, point: tuple[int, int], base: int) -> bool:
    fork = copy.deepcopy(engine)
    response = driver.perform(
        fork, ActionInput(id=GameAction.from_id(6), data={"y": point[0], "x": point[1]})
    )
    return _completes(response, base)


def check_session_exact(job: tuple[str, str, int]) -> dict[str, Any]:
    """Fork by replaying the prefix from a fresh game — for games where deep copy is not
    faithful (tn36). Quadratic and slow, so it is used only where the control demands it."""
    game, guid, cap = job
    path = CORPUS / game / f"{guid}.recording.jsonl"
    driver = ReplayDriver(game)
    actions = list(iter_recorded_actions(path))

    def probe(index: int, point: tuple[int, int], base: int) -> bool:
        engine, _ = driver.replay_prefix(actions, index)
        response = driver.perform(
            engine,
            ActionInput(id=GameAction.from_id(6), data={"y": point[0], "x": point[1]}),
        )
        return _completes(response, base)

    rows: list[dict[str, Any]] = []
    engine = driver.new_game()
    grid = None
    prev_levels = 0
    engine_levels = 0
    for index, recorded in enumerate(actions):
        target = (recorded.action_data.get("y"), recorded.action_data.get("x"))
        if (
            prev_levels == 0
            and recorded.action_id == 6
            and recorded.levels_completed > prev_levels
            and isinstance(target[0], int)
            and isinstance(target[1], int)
            and grid is not None
            and 0 <= target[0] < len(grid)
            and 0 <= target[1] < len(grid[0])
        ):
            base = engine_levels
            candidates = [node["point"] for node in cull(segment(grid), cap)]
            supplement = [
                point
                for point in lattice_points(len(grid), len(grid[0]))
                if point not in set(candidates)
            ]
            rows.append(
                {
                    "guid": guid,
                    "step": recorded.step,
                    "control": probe(index, target, base),
                    "by_candidates": any(probe(index, p, base) for p in candidates),
                    "by_lattice": any(probe(index, p, base) for p in supplement),
                    "candidates": len(candidates),
                    "lattice": len(supplement),
                }
            )

        response = driver.perform(engine, recorded)
        frames = _plain_frames(response.frame or [])
        if frames:
            grid = frames[-1]
        if response.levels_completed is not None:
            engine_levels = int(response.levels_completed)
        prev_levels = recorded.levels_completed
    return {"game": game, "rows": rows}


def check_session(job: tuple[str, str, int]) -> dict[str, Any]:
    game, guid, cap = job
    path = CORPUS / game / f"{guid}.recording.jsonl"
    driver = ReplayDriver(game)
    engine = driver.new_game()

    rows: list[dict[str, Any]] = []
    grid = None
    prev_levels = 0
    engine_levels = 0
    for recorded in iter_recorded_actions(path):
        target = (recorded.action_data.get("y"), recorded.action_data.get("x"))
        completing = (
            prev_levels == 0
            and recorded.action_id == 6
            and recorded.levels_completed > prev_levels
            and isinstance(target[0], int)
            and isinstance(target[1], int)
            and grid is not None
            and 0 <= target[0] < len(grid)
            and 0 <= target[1] < len(grid[0])
        )

        if completing:
            base = engine_levels
            height, width = len(grid), len(grid[0])
            candidates = [node["point"] for node in cull(segment(grid), cap)]
            supplement = [
                point
                for point in lattice_points(height, width)
                if point not in set(candidates)
            ]
            rows.append(
                {
                    "guid": guid,
                    "step": recorded.step,
                    "control": _try(driver, engine, target, base),
                    "by_candidates": any(
                        _try(driver, engine, point, base) for point in candidates
                    ),
                    "by_lattice": any(
                        _try(driver, engine, point, base) for point in supplement
                    ),
                    "candidates": len(candidates),
                    "lattice": len(supplement),
                }
            )

        response = driver.perform(engine, recorded)
        frames = _plain_frames(response.frame or [])
        if frames:
            grid = frames[-1]
        if response.levels_completed is not None:
            engine_levels = int(response.levels_completed)
        prev_levels = recorded.levels_completed
    return {"game": game, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--cap", type=int, default=MEASURED_CAP)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument(
        "--exact",
        action="store_true",
        help="fork by prefix replay instead of deep copy (use where the control fails)",
    )
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    games = (
        [game for game in ALL_GAMES if game not in EXCLUDED_GAMES]
        if args.all
        else list(args.games)
    )
    jobs = [
        (game, path.name.split(".")[0], args.cap)
        for game in games
        for path in sorted((CORPUS / game).glob("*.recording.jsonl"))
        if (game, path.name.split(".")[0][:8]) not in EXCLUDED_SESSIONS
    ]

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        worker = check_session_exact if args.exact else check_session
        results = list(pool.map(worker, jobs))

    per_game: dict[str, Any] = {}
    print(f"{'game':5s} {'compl':>6s} {'ctrl':>5s} {'cand':>5s} {'+latt':>6s} {'none':>5s}")
    for game in games:
        rows = [row for result in results if result["game"] == game for row in result["rows"]]
        if not rows:
            continue
        valid = [row for row in rows if row["control"]]
        by_cand = sum(1 for row in valid if row["by_candidates"])
        by_either = sum(
            1 for row in valid if row["by_candidates"] or row["by_lattice"]
        )
        per_game[game] = {
            "completing_clicks": len(rows),
            "control_ok": len(valid),
            "reachable_by_candidates": by_cand,
            "reachable_with_lattice": by_either,
            "unreachable": len(valid) - by_either,
            "rate_candidates": by_cand / len(valid) if valid else None,
            "rate_with_lattice": by_either / len(valid) if valid else None,
            "rows": rows,
        }
        cell = per_game[game]
        print(
            f"{game:5s} {len(rows):6d} {len(valid):5d} "
            f"{by_cand:5d} {by_either:6d} {cell['unreachable']:5d}",
            flush=True,
        )

    document = {
        "format_version": FORMAT_VERSION,
        "cap": args.cap,
        "lattice": LATTICE,
        "fork": "prefix_replay" if args.exact else "deep_copy",
        "per_game": per_game,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
