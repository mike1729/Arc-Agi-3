#!/usr/bin/env python3
"""E1-pre part 2 — is a centroid click equivalent to the human's exact cell?

`e1_candidates.py` reports two recall numbers that differ by an order of magnitude: the
human's exact cell is rarely a generated candidate (cell recall 0.04-0.38), while the human's
NODE almost always is (node recall 1.000 at cap 96 on 17 of 18 games). Which number governs
the explorer depends entirely on whether clicking a node's candidate point does the same
thing as clicking where the human clicked. `notes/e1-explorer.md` calls that gap "the honest
uncertainty" and reports it. It does not have to stay uncertain: the engine can be asked.

METHOD
------
Replay each session through the frozen source. At every L1 ACTION6 whose target cell is NOT
already the candidate point, deep-copy the live engine, issue ACTION6 at the candidate point
of the node containing the human's cell, and compare the outcome against the human's actual
one. Then perform the human's real action on the original engine and continue — so each
session costs one pass plus one forked action per click, not a quadratic re-replay.

Equivalence is judged on the SETTLED outcome — last frame, state, levels_completed — because
that is what E0's transition convention reads and what the explorer's state identity hashes.
All-frame equality is reported alongside it: a substitution that agrees on the settled state
but differs in animation is equivalent for every purpose the explorer has.

Clicks whose cell already IS the candidate point are counted as equivalent-by-identity and
reported apart, so the headline rate cannot be inflated by them.

Only games that pass role-bearing engine truth are measured — the exclusions in
`rs_transitions` apply unchanged.

Run:
  .venv/bin/python agent/harness/e1_equiv.py --all --jobs 8 --out logs/e1_equiv_all.json
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

from e1_candidates import segment  # noqa: E402
from gi2_replay import ReplayDriver, _plain_frames, iter_recorded_actions  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    CORPUS,
    EXCLUDED_GAMES,
    EXCLUDED_SESSIONS,
    ITERATION_GAMES,
    ROOT,
)

OUTPUT = ROOT / "logs/e1_equiv.json"
FORMAT_VERSION = 1


def _settled(frames: list, state: Any, levels: Any) -> tuple:
    plain = _plain_frames(frames or [])
    return (
        plain[-1] if plain else None,
        str(getattr(state, "value", state)),
        int(levels or 0),
    )


def check_session(job: tuple[str, str]) -> dict[str, Any]:
    game, guid = job
    path = CORPUS / game / f"{guid}.recording.jsonl"
    driver = ReplayDriver(game)
    engine = driver.new_game()

    rows: list[dict[str, Any]] = []
    grid = None  # the previous response's settled frame — E0's `pre`
    prev_levels = 0
    for recorded in iter_recorded_actions(path):
        target = (recorded.action_data.get("y"), recorded.action_data.get("x"))
        probe = (
            prev_levels == 0  # played at L1
            and recorded.action_id == 6
            and isinstance(target[0], int)
            and isinstance(target[1], int)
            and grid is not None
            and 0 <= target[0] < len(grid)
            and 0 <= target[1] < len(grid[0])
        )

        fork = control = None
        owner = None
        if probe:
            owner = next(
                (node for node in segment(grid) if target in node["cells"]), None
            )
            if owner is not None and owner["point"] != target:
                # copy BEFORE the real action mutates the engine. The second copy is the
                # CONTROL: deep-copying an ARCBaseGame is not guaranteed faithful (tn36
                # diverges once its state has accumulated), so every measured click proves
                # its own fork first — the recorded action on a copy must reproduce the
                # recorded action on the engine, or the click is not measurable.
                fork = copy.deepcopy(engine)
                control = copy.deepcopy(engine)

        response = driver.perform(engine, recorded)

        if probe:
            if owner is None:
                rows.append({"kind": "no_node"})
            elif fork is None:
                rows.append({"kind": "identity"})
            elif _plain_frames(
                driver.perform(control, recorded).frame or []
            ) != _plain_frames(response.frame or []):
                rows.append({"kind": "copy_unfaithful"})
            else:
                alternative = driver.perform(
                    fork,
                    ActionInput(
                        id=GameAction.from_id(6),
                        data={"y": owner["point"][0], "x": owner["point"][1]},
                    ),
                )
                rows.append(
                    {
                        "kind": "substituted",
                        "settled_equal": _settled(
                            alternative.frame, alternative.state, alternative.levels_completed
                        )
                        == _settled(response.frame, response.state, response.levels_completed),
                        "all_frames_equal": _plain_frames(alternative.frame or [])
                        == _plain_frames(response.frame or []),
                        "node_size": owner["size"],
                        "completing": recorded.levels_completed > prev_levels,
                    }
                )

        frames = _plain_frames(response.frame or [])
        if frames:
            grid = frames[-1]
        # Level bookkeeping comes from the RECORDING, never from the engine: the local
        # engine's `levels_completed` does not track the client's, and reading it here
        # silently promoted every click in a session to L1.
        prev_levels = recorded.levels_completed
    return {"game": game, "guid": guid, "rows": rows}


def score(results: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for result in results for row in result["rows"]]
    substituted = [row for row in rows if row["kind"] == "substituted"]
    completing = [row for row in substituted if row["completing"]]
    settled = sum(1 for row in substituted if row["settled_equal"])
    frames = sum(1 for row in substituted if row["all_frames_equal"])
    return {
        "clicks": len(rows),
        "identity": sum(1 for row in rows if row["kind"] == "identity"),
        "no_node": sum(1 for row in rows if row["kind"] == "no_node"),
        "copy_unfaithful": sum(1 for row in rows if row["kind"] == "copy_unfaithful"),
        "substituted": len(substituted),
        "settled_equivalent": settled,
        "settled_rate": settled / len(substituted) if substituted else None,
        "all_frames_equal": frames,
        "all_frames_rate": frames / len(substituted) if substituted else None,
        "completing_substituted": len(completing),
        "completing_settled_rate": (
            sum(1 for row in completing if row["settled_equal"]) / len(completing)
            if completing
            else None
        ),
    }


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
    jobs = [
        (game, path.name.split(".")[0])
        for game in games
        for path in sorted((CORPUS / game).glob("*.recording.jsonl"))
        if (game, path.name.split(".")[0][:8]) not in EXCLUDED_SESSIONS
    ]

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(check_session, jobs))

    per_game: dict[str, Any] = {}
    for game in games:
        rows = [result for result in results if result["game"] == game]
        per_game[game] = score(rows)

    print(
        f"{'game':5s} {'subst':>7s} {'ident':>6s} {'unfaith':>8s} {'settled':>8s} "
        f"{'frames':>7s} {'completing':>11s}"
    )
    for game in games:
        cell = per_game[game]
        if not cell["clicks"]:
            continue
        rate = cell["settled_rate"]
        frames = cell["all_frames_rate"]
        done = cell["completing_settled_rate"]
        print(
            f"{game:5s} {cell['substituted']:7d} {cell['identity']:6d} "
            f"{cell['copy_unfaithful']:8d} "
            f"{'  n/a  ' if rate is None else f'{rate:8.3f}'} "
            f"{'  n/a ' if frames is None else f'{frames:7.3f}'} "
            f"{'  n/a' if done is None else f'{done:8.3f}'}"
            f" ({cell['completing_substituted']})",
            flush=True,
        )

    document = {"format_version": FORMAT_VERSION, "per_game": per_game}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
