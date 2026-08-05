#!/usr/bin/env python3
"""E2 slice 3, build item 0 — capture what winning actually looks like.

`notes/e2-slice3.md`. The one live-engine step in an otherwise zero-model build day.

THE GAP THIS CLOSES
-------------------
This project has never retained a single completion frame. Measured: sp80 and lf52 are the
only two protocol games whose explorer store holds a level completion, and in BOTH the
explorer hashed the level-advance frame without adding it to `states.json`, so
`e2_dose.load_store` substitutes the PRE frame as a placeholder. Every downstream consumer
inherits the hole — the prior library reports `positives_evaluable: 0` on all eight games,
slice 2's channel A was decided on negative evidence alone, and slice 3 was about to ask the
model what completion looks like while never having looked itself.

The engine returned 20 frames at sp80's completing action and 27 at lf52's. Only the COUNT
was kept. This module re-executes those actions and keeps everything.

WHY THIS IS SOUND, AND WHERE IT WOULD NOT BE
--------------------------------------------
The engine is deterministic and `notes/e1-prefix-repair.md` produced VERIFIED walked routes
for every stored state — `new_game(); RESET; <actions>` reproduces it. So the capture is a
replay of something the explorer really walked, not a new episode.

The gate makes that a check rather than an assumption: before the completing action is
issued, the replayed grid must equal the grid the store recorded for that state, CELL FOR
CELL. Grids are compared directly against `logs/e1_store_v2/*.states.json` rather than by
digest, so the check cannot pass through a hash convention that happens to agree. A game
whose gate fails is reported failed and captures nothing; it is never "captured with a
warning".

Local-only by construction: `logs/e1_completions/` matches the `/logs/*/*` rule in
`.gitignore`, and these files are full competition-game frames. PUBLISHING.md — they never
enter a commit.

Run:
  .venv/bin/python agent/harness/e3_completion_capture.py
  .venv/bin/python agent/harness/e3_completion_capture.py --games sp80 lf52
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

from gi2_traces import frame_roles  # noqa: E402
from rs_transitions import ROOT  # noqa: E402

STORE = ROOT / "logs/e1_store_v2"
PREFIX = ROOT / "logs/e1_prefix_v2"
OUTPUT = ROOT / "logs/e1_completions"
FORMAT_VERSION = 1

# sp80 and lf52 are the two protocol games with a stored completion; lp85 and r11l are
# captured for the record — the same defect exists there and the capture is cheap.
GAMES = ("sp80", "lf52", "lp85", "r11l")

RESET_ACTION = (0, None, None)


class Engine:
    """Fresh-game driver. One `new_game()` per capture; never shared across a claim."""

    def __init__(self, game: str):
        from arcengine import ActionInput, GameAction  # noqa: PLC0415
        from gi2_replay import ReplayDriver, _plain_frames  # noqa: PLC0415

        self._input = ActionInput
        self._action = GameAction
        self._frames = _plain_frames
        self.driver = ReplayDriver(game)

    def new(self):
        return self.driver.new_game()

    def perform(self, handle, action: tuple) -> Any:
        action_id, row, col = action
        return self.driver.perform(
            handle,
            self._input(
                id=self._action.from_id(action_id),
                data={} if row is None else {"y": row, "x": col},
            ),
        )

    def frames(self, response: Any) -> list:
        return self._frames(response.frame or [])


def completing_row(game: str) -> dict[str, Any] | None:
    rows = [
        json.loads(line)
        for line in (STORE / f"{game}.transitions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    completions = [row for row in rows if row.get("completed")]
    return completions[0] if completions else None


def capture(game: str) -> dict[str, Any]:
    row = completing_row(game)
    if row is None:
        return {"game": game, "captured": False, "reason": "no completion in this store"}

    states = json.loads((STORE / f"{game}.states.json").read_text())
    expected_pre = states.get(row["pre"])
    if expected_pre is None:
        return {"game": game, "captured": False, "reason": "pre-state grid not in the store"}

    prefix = json.loads((PREFIX / f"{game}.json").read_text())
    route = (prefix.get("routes") or {}).get(row["pre"])
    if route is None:
        return {
            "game": game,
            "captured": False,
            "reason": "no verified walked route to the completing pre-state",
        }
    walked = [tuple(action) for action in route["walked"]]

    engine = Engine(game)
    handle = engine.new()
    engine.perform(handle, RESET_ACTION)
    grid = None
    for action in walked:
        response = engine.perform(handle, action)
        frames = engine.frames(response)
        grid = frames[-1] if frames else None

    # THE GATE. Cell for cell against the stored grid, not against a digest of it.
    if grid != expected_pre:
        differing = (
            None
            if grid is None
            else sum(
                left != right
                for left_row, right_row in zip(grid, expected_pre)
                for left, right in zip(left_row, right_row)
            )
        )
        return {
            "game": game,
            "captured": False,
            "reason": "route did not reproduce the recorded pre-state",
            "route_actions": len(walked),
            "differing_cells": differing,
        }

    action = tuple(row["action"])
    response = engine.perform(handle, action)
    frames = engine.frames(response)
    levels = int(getattr(response, "levels_completed", 0) or 0)
    state = str(getattr(response, "state", ""))
    state_text = state.rsplit(".", 1)[-1]
    try:
        roles = list(frame_roles(state=state_text, n_frames=len(frames), completion_increment=1))
    except ValueError as error:
        roles = []
        role_error = str(error)
    else:
        role_error = None

    return {
        "game": game,
        "captured": True,
        "gate": {
            "route_actions": len(walked),
            "pre_state_reproduced": True,
            "route_form": prefix.get("route_form"),
        },
        "store": {
            "step": row["step"],
            "action": list(action),
            "frames_recorded_by_explorer": row.get("frames"),
            "level": row.get("level"),
        },
        "completion": {
            "action": list(action),
            "frames_returned": len(frames),
            "roles": roles,
            "role_error": role_error,
            "levels_completed": levels,
            "state": state_text,
            "win_levels": int(getattr(response, "win_levels", 0) or 0),
            "full_reset": bool(getattr(response, "full_reset", False)),
            "available_actions": [
                int(getattr(item, "value", item))
                for item in (getattr(response, "available_actions", None) or [])
            ],
        },
        # The grids. Local-only, and the reason this file never enters a commit.
        "last_incomplete_frame": expected_pre,
        "frames": frames,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(GAMES))
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    summary = []
    for game in args.games:
        try:
            row = capture(game)
        except Exception as error:  # noqa: BLE001 — a failed capture is a result, not a crash
            row = {"game": game, "captured": False, "reason": f"{type(error).__name__}: {error}"}
        if row["captured"]:
            (args.out / f"{game}.json").write_text(
                json.dumps({"format_version": FORMAT_VERSION, **row}, indent=1)
            )
            completion = row["completion"]
            print(
                f"{game:5s} captured: {completion['frames_returned']} frames "
                f"(explorer recorded {row['store']['frames_recorded_by_explorer']}), "
                f"state={completion['state']}, roles="
                f"{'/'.join(sorted(set(completion['roles']))) or 'none'}, "
                f"route={row['gate']['route_actions']} actions",
                flush=True,
            )
        else:
            print(f"{game:5s} NOT captured: {row['reason']}", flush=True)
        summary.append({k: v for k, v in row.items() if k not in ("frames", "last_incomplete_frame")})

    (args.out / "index.json").write_text(
        json.dumps(
            {
                "format_version": FORMAT_VERSION,
                "generated_by": "agent/harness/e3_completion_capture.py",
                "note": "notes/e2-slice3.md build item 0",
                "games": summary,
            },
            indent=1,
        )
    )
    print(f"\nwrote {args.out}/ ({sum(1 for r in summary if r['captured'])} captured)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
