#!/usr/bin/env python3
"""E2 slice 3 — the controlled dual-history probe. Block 5 exists only if this succeeds.

`notes/e2-slice3.md` rev 2, block 5's optional path; the P2 method of
`notes/e2-hidden-state.md`. Live game contact, zero model calls.

WHY THIS IS NOT OPTIONAL AFTER ALL — the measurement that forced it
--------------------------------------------------------------------
Rev 2 holds block 5 to strict semantics — identical visible board, same action, different
outcome — and reports the availability census as "m0r0 3, the other seven zero", from the
`conflicted` list in `logs/e1_store_v2/*.graph.json`.

Checked before building on it: **the store retains only one outcome for each of those three
pairs.** For every m0r0 conflict, `graph.json`'s own `edges` hold exactly ONE post state, the
transitions log holds exactly one row, and `conflict_records` carries only `{state, action,
step}` — no second board. The passive census over the transitions log is 0 repeated / 0
aliased on all twelve games checked, which `notes/e2-hidden-state.md` already recorded for
m0r0 and g50t.

So the flag says a conflict was seen live; the evidence of what the other outcome WAS does
not exist in the frozen store. Block 5 is unrenderable from stored data on all eight
slice-3 games, m0r0 included, and rendering the one retained outcome twice would be a
fabrication of exactly the kind the exhibit is meant to expose.

This module produces the missing half, or proves it is not there:

    route A   the verified walked route to the flagged state
    route B   the same route plus a CYCLE that returns to the same state digest — a
              different history reaching the same board
    then      the flagged action from each, and a cell-for-cell comparison of the results

GATE: both routes must reproduce the flagged board exactly before the action is issued. If
they do not, nothing is claimed and nothing is rendered — the exhibit's entire content is
"the boards were identical", so an unverified board makes the exhibit meaningless.

Either outcome is a result. Different outcomes give slice 3 a real alias exhibit and
channel B a concrete thing to explain. Identical outcomes say the live conflict flag was a
routing artifact — which `notes/e1-prefix-audit.md` already suspects of this list in both
directions — and block 5 stays absent, honestly.

Run:
  .venv/bin/python agent/harness/e2_alias_probe.py --games m0r0
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from e3_completion_capture import RESET_ACTION, Engine  # noqa: E402
from rs_transitions import ROOT  # noqa: E402

STORE = ROOT / "logs/e1_store_v2"
PREFIX = ROOT / "logs/e1_prefix_v2"
OUTPUT = ROOT / "logs/e1_alias_probe"
FORMAT_VERSION = 1

# The only slice-3 game whose graph flags any conflict at all (measured: m0r0 3; dc22, ft09,
# ls20, tu93, vc33, sp80, lf52 all zero). g50t/cn04/sc25/cd82 have flags and are outside the
# protocol set; they are probeable with the same machinery if a later note wants them.
GAMES = ("m0r0",)

MAX_CYCLE = 6  # (w) a short cycle keeps route B close to route A in everything but length


def shortest_cycle(edges: list, target: str, limit: int = MAX_CYCLE) -> list | None:
    """The shortest non-empty action sequence that leaves `target` and returns to it.

    Breadth-first over the recorded edge relation, so every step of the cycle is a
    transition the explorer actually walked. A cycle invented out of the action space would
    not be evidence about this game's recorded behaviour.
    """
    outgoing: dict[str, list[tuple[tuple, str]]] = {}
    for pre, action, post in edges:
        outgoing.setdefault(pre, []).append((tuple(action), post))

    queue: deque[tuple[str, list]] = deque()
    for action, post in outgoing.get(target, []):
        queue.append((post, [action]))
    seen = {target}
    while queue:
        state, path = queue.popleft()
        if state == target:
            return path
        if len(path) >= limit or state in seen:
            continue
        seen.add(state)
        for action, post in outgoing.get(state, []):
            queue.append((post, path + [action]))
    return None


def run_route(engine: Engine, actions: list) -> Any:
    handle = engine.new()
    # The RESET frame IS the board for a zero-length route — m0r0's flagged origin state is
    # reached by RESET and nothing else, and dropping this made its two probes report "did
    # not reproduce the board" when the route was simply empty.
    reset_frames = engine.frames(engine.perform(handle, RESET_ACTION))
    grid = reset_frames[-1] if reset_frames else None
    for action in actions:
        frames = engine.frames(engine.perform(handle, tuple(action)))
        grid = frames[-1] if frames else None
    return handle, grid


def probe_game(game: str) -> dict[str, Any]:
    graph = json.loads((STORE / f"{game}.graph.json").read_text())
    states = json.loads((STORE / f"{game}.states.json").read_text())
    prefix = json.loads((PREFIX / f"{game}.json").read_text())
    routes = prefix.get("routes") or {}

    results = []
    engine = Engine(game)
    for digest, action in graph.get("conflicted", []):
        action = tuple(action)
        board = states.get(digest)
        row: dict[str, Any] = {"state": digest, "action": list(action)}
        if board is None:
            row["probed"] = False
            row["reason"] = "flagged state is not in states.json"
            results.append(row)
            continue

        route_a = [tuple(a) for a in (routes.get(digest) or {}).get("walked", [])]
        if digest != graph["origin"] and not route_a:
            row["probed"] = False
            row["reason"] = "no verified walked route to the flagged state"
            results.append(row)
            continue
        cycle = shortest_cycle(graph["edges"], digest)
        if cycle is None:
            row["probed"] = False
            row["reason"] = f"no recorded cycle of length <= {MAX_CYCLE} returns to this state"
            results.append(row)
            continue
        route_b = route_a + [tuple(a) for a in cycle]

        handle_a, grid_a = run_route(engine, route_a)
        handle_b, grid_b = run_route(engine, route_b)
        row["routes"] = {"a_actions": len(route_a), "b_actions": len(route_b), "cycle": [list(a) for a in cycle]}
        # THE GATE. Both histories must land on the flagged board, cell for cell.
        row["gate"] = {
            "a_reproduces_board": grid_a == board,
            "b_reproduces_board": grid_b == board,
        }
        if not (grid_a == board and grid_b == board):
            row["probed"] = False
            row["reason"] = "one or both routes did not reproduce the flagged board"
            results.append(row)
            continue

        after_a = engine.frames(engine.perform(handle_a, action))
        after_b = engine.frames(engine.perform(handle_b, action))
        final_a = after_a[-1] if after_a else None
        final_b = after_b[-1] if after_b else None
        differing = (
            None
            if final_a is None or final_b is None
            else sum(
                left != right
                for left_row, right_row in zip(final_a, final_b)
                for left, right in zip(left_row, right_row)
            )
        )
        row.update(
            {
                "probed": True,
                "frames_a": len(after_a),
                "frames_b": len(after_b),
                "outcomes_differ": final_a != final_b,
                "differing_cells": differing,
                "board": board,
                "after_a": final_a,
                "after_b": final_b,
            }
        )
        results.append(row)
    return {"game": game, "flagged": len(graph.get("conflicted", [])), "probes": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(GAMES))
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for game in args.games:
        row = probe_game(game)
        (args.out / f"{game}.json").write_text(
            json.dumps({"format_version": FORMAT_VERSION, **row}, indent=1)
        )
        usable = [p for p in row["probes"] if p.get("probed") and p.get("outcomes_differ")]
        print(f"{game}: {row['flagged']} flagged pairs", flush=True)
        for probe in row["probes"]:
            if not probe.get("probed"):
                print(f"   {probe['state'][:8]} {probe['action']}: NOT PROBED — {probe['reason']}")
                continue
            print(
                f"   {probe['state'][:8]} {probe['action']}: routes "
                f"{probe['routes']['a_actions']} vs {probe['routes']['b_actions']} actions, "
                f"both reproduced the board; outcomes "
                + (
                    f"DIFFER in {probe['differing_cells']} cells"
                    if probe["outcomes_differ"]
                    else "are IDENTICAL"
                )
            )
        print(f"   usable alias exhibits: {len(usable)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
