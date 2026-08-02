#!/usr/bin/env python3
"""GI-2 exhaustive completion-state forks for the five A1-fidelity games.

Each selected session is replayed once.  Immediately before every recorded completing action,
the engine state is deep-copied for each legal simple action and each deterministic MOUSE
representative from the A2 registry.  The recorded completing action itself is excluded.

The artifact stores outcomes, compact delta signatures, and lossless run-length encoded grids.
The grids are required by A3's predicate verifier; they avoid re-running thousands of paid
fork branches while keeping the artifact substantially smaller than nested 64x64 arrays.
vc33 is present as an explicit positive-only row because A1 frame fidelity failed for all
three sessions.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import copy
import hashlib
import json
import zlib
from pathlib import Path
from typing import Any

from arcengine import ActionInput, GameAction

from gi2_observation import Tracker, effect_signature
from gi2_replay import ReplayDriver, _plain_frames, iter_recorded_actions
from gi2_traces import CORPUS, DRAW, ROOT, SESSIONS, frame_roles, selected_sessions

REPLAY_FIDELITY = ROOT / "logs/gi2_replay_fidelity.json"
OBSERVATION = ROOT / "logs/gi2_observation_catalogue.json"
OUTPUT = ROOT / "logs/gi2_fork_table.json"
FORMAT_VERSION = 3


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def encode_grid(grid: list) -> str:
    flat = bytes(int(value) for row in grid for value in row)
    return base64.b85encode(zlib.compress(flat, level=9)).decode("ascii")


def decode_grid(payload: str, *, width: int = 64, height: int = 64) -> list[list[int]]:
    flat = list(zlib.decompress(base64.b85decode(payload.encode("ascii"))))
    if len(flat) != width * height:
        raise ValueError(f"RLE expands to {len(flat)} cells, expected {width * height}")
    return [flat[offset : offset + width] for offset in range(0, len(flat), width)]


def _decode_v2_grid(runs: list[list[int]]) -> list[list[int]]:
    flat = [
        value
        for run in runs
        for value in [int(run[0])] * int(run[1])
    ]
    if len(flat) != 64 * 64:
        raise ValueError(f"v2 RLE expands to {len(flat)} cells")
    return [flat[offset : offset + 64] for offset in range(0, len(flat), 64)]


def compact_v2(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("format_version") != 2:
        raise ValueError("compact input must be fork-table format v2")
    for game in document["games"]:
        for session in game["sessions"]:
            for completion in session["completions"]:
                completion["pre_grid_rle"] = encode_grid(
                    _decode_v2_grid(completion["pre_grid_rle"])
                )
                for fork in completion["forks"]:
                    if fork["terminal_grid_rle"] is not None:
                        fork["terminal_grid_rle"] = encode_grid(
                            _decode_v2_grid(fork["terminal_grid_rle"])
                        )
    document["format_version"] = FORMAT_VERSION
    document["grid_encoding"] = "zlib(level=9)+base85 over 4096 uint8 palette values"
    return document


def _terminal_grid(response, completed: bool) -> list | None:
    frames = _plain_frames(response.frame or [])
    if not frames:
        return None
    state = str(getattr(response.state, "value", response.state))
    if completed and state != "WIN":
        return frames[-2] if len(frames) >= 2 else None
    return frames[-1]


def _candidate_actions(
    available: tuple[int, ...],
    representatives: list[tuple[int, int]],
    recorded,
) -> list[dict[str, Any]]:
    candidates = []
    for action_id in sorted(set(available)):
        if action_id == 0:
            continue
        if action_id == 6:
            for row, col in representatives:
                data = {"x": col, "y": row}
                if recorded.action_id == 6 and recorded.action_data == data:
                    continue
                candidates.append({"action_id": 6, "action_data": data})
        else:
            if recorded.action_id == action_id and not recorded.action_data:
                continue
            candidates.append({"action_id": action_id, "action_data": {}})
    return candidates


def fork_session(env: str, selected: dict[str, Any]) -> dict[str, Any]:
    path = CORPUS / env / f"{selected['guid']}.recording.jsonl"
    actions = list(iter_recorded_actions(path))
    driver = ReplayDriver(env)
    game = driver.new_game()
    tracker = Tracker()
    previous_grid = None
    previous_observation = None
    previous_available: tuple[int, ...] = ()
    previous_levels = 0
    completion_rows = []

    for action in actions:
        is_recorded_completion = action.levels_completed > previous_levels
        if is_recorded_completion:
            if previous_grid is None or previous_observation is None:
                raise ValueError(f"{env}/{selected['guid']}: completion lacks pre-state")
            candidates = _candidate_actions(
                previous_available,
                previous_observation.mouse_representatives,
                action,
            )
            outcomes = []
            for candidate in candidates:
                branch = copy.deepcopy(game)
                response = driver.perform(
                    branch,
                    ActionInput(
                        id=GameAction.from_id(candidate["action_id"]),
                        data=candidate["action_data"],
                    ),
                )
                completed = int(response.levels_completed or 0) > previous_levels
                terminal = _terminal_grid(response, completed)
                if terminal is None:
                    signature = None
                    changed_cells = None
                else:
                    branch_tracker = copy.deepcopy(tracker)
                    observation = branch_tracker.update(
                        terminal,
                        previous_grid=previous_grid,
                        action_id=candidate["action_id"],
                        action_data=candidate["action_data"],
                    )
                    signature = effect_signature(observation, completed=completed)
                    changed_cells = sum(
                        left != right
                        for left_row, right_row in zip(previous_grid, terminal)
                        for left, right in zip(left_row, right_row)
                    )
                outcomes.append(
                    {
                        **candidate,
                        "completed": completed,
                        "state": str(getattr(response.state, "value", response.state)),
                        "levels_completed": int(response.levels_completed or 0),
                        "changed_cells": changed_cells,
                        "effect": signature,
                        "terminal_grid_rle": (
                            encode_grid(terminal) if terminal is not None else None
                        ),
                    }
                )
            completion_rows.append(
                {
                    "step": action.step,
                    "level": action.levels_completed,
                    "recorded_action": {
                        "action_id": action.action_id,
                        "action_data": action.action_data,
                    },
                    "available_actions": previous_available,
                    "n_handles": len(previous_observation.handles),
                    "n_groups": len(previous_observation.groups),
                    "n_mouse_representatives": len(
                        previous_observation.mouse_representatives
                    ),
                    "pre_grid_rle": encode_grid(previous_grid),
                    "forks": outcomes,
                }
            )

        response = driver.perform(game, action)
        replayed_frames = _plain_frames(response.frame or [])
        roles = frame_roles(
            state=action.state,
            n_frames=len(action.frames),
            completion_increment=action.levels_completed - previous_levels,
        )
        for grid, role in zip(replayed_frames, roles):
            if role not in {"settled", "solved_terminal", "next_level_initial"}:
                continue
            if role == "next_level_initial":
                tracker.reset_level()
                previous_grid = None
            previous_observation = tracker.update(
                grid,
                previous_grid=previous_grid,
                action_id=action.action_id,
                action_data=action.action_data,
            )
            previous_grid = grid
        previous_available = tuple(
            int(getattr(item, "value", item)) for item in (response.available_actions or [])
        )
        # ft09's local source advertises only MOUSE while the exact recording advertises all
        # six actions.  Fork candidates reproduce the deployment-visible recording contract.
        if action.available_actions:
            previous_available = action.available_actions
        previous_levels = action.levels_completed

    return {
        **selected,
        "recording": str(path.relative_to(ROOT)),
        "completions": completion_rows,
        "n_forks": sum(len(row["forks"]) for row in completion_rows),
        "n_negative": sum(
            not fork["completed"] for row in completion_rows for fork in row["forks"]
        ),
        "n_alternative_positive": sum(
            fork["completed"] for row in completion_rows for fork in row["forks"]
        ),
    }


def _fork_args(args):
    return fork_session(*args)


def build(jobs: int = 1) -> dict[str, Any]:
    draw = json.loads(DRAW.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())
    fidelity = json.loads(REPLAY_FIDELITY.read_text())
    eligible = {
        game["env"] for game in fidelity["games"] if game["frame_fidelity"]
    }
    work = [
        (env, selected)
        for env in draw["iteration"]
        if env in eligible
        for selected in selected_sessions(env, sessions_doc, draw)
    ]
    if jobs < 1:
        raise ValueError("jobs must be positive")
    if jobs == 1:
        rows = [_fork_args(item) for item in work]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
            rows = list(pool.map(_fork_args, work))
    games = []
    for env in draw["iteration"]:
        game_rows = sorted(
            [row for row in rows if f"/{env}/" in row["recording"]],
            key=lambda row: row["rank"],
        )
        games.append(
            {
                "env": env,
                "fork_eligible": env in eligible,
                "reason": None if env in eligible else "A1 frame fidelity failed",
                "sessions": game_rows,
                "n_forks": sum(row["n_forks"] for row in game_rows),
                "n_negative": sum(row["n_negative"] for row in game_rows),
                "n_alternative_positive": sum(
                    row["n_alternative_positive"] for row in game_rows
                ),
            }
        )
    return {
        "format_version": FORMAT_VERSION,
        "grid_encoding": "zlib(level=9)+base85 over 4096 uint8 palette values",
        "status": "a2_measured",
        "scope": "iteration",
        "inputs": {
            "replay_fidelity_sha256": _sha256(REPLAY_FIDELITY),
            "observation_sha256": _sha256(OBSERVATION),
        },
        "games": games,
        "totals": {
            "fork_eligible_games": len(eligible),
            "completion_states": sum(
                len(row["completions"]) for row in rows
            ),
            "forks": sum(row["n_forks"] for row in rows),
            "negative": sum(row["n_negative"] for row in rows),
            "alternative_positive": sum(
                row["n_alternative_positive"] for row in rows
            ),
        },
    }


def verify(document: Any) -> list[str]:
    problems = []
    if not isinstance(document, dict):
        return ["artifact: expected object"]
    if document.get("format_version") != FORMAT_VERSION:
        problems.append("format_version mismatch")
    inputs = document.get("inputs", {})
    for name, path in (
        ("replay_fidelity", REPLAY_FIDELITY),
        ("observation", OBSERVATION),
    ):
        if not path.is_file():
            problems.append(f"{name}: input missing")
        elif inputs.get(f"{name}_sha256") != _sha256(path):
            problems.append(f"{name}: digest drift")
    games = document.get("games")
    if not isinstance(games, list) or len(games) != 6:
        return problems + ["games: expected six rows"]
    completion_states = forks = negative = alternative_positive = 0
    try:
        for game in games:
            for session in game.get("sessions", []):
                for completion in session.get("completions", []):
                    completion_states += 1
                    decode_grid(completion["pre_grid_rle"])
                    for fork in completion["forks"]:
                        forks += 1
                        negative += not fork["completed"]
                        alternative_positive += bool(fork["completed"])
                        if fork["terminal_grid_rle"] is not None:
                            decode_grid(fork["terminal_grid_rle"])
    except (KeyError, TypeError, ValueError, zlib.error) as exc:
        problems.append(f"grid payload: {exc}")
    expected = {
        "completion_states": completion_states,
        "forks": forks,
        "negative": negative,
        "alternative_positive": alternative_positive,
    }
    totals = document.get("totals", {})
    for name, value in expected.items():
        if totals.get(name) != value:
            problems.append(f"totals.{name}: expected {value}, got {totals.get(name)}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--compact-v2", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    if args.compact_v2:
        document = compact_v2(json.loads(OUTPUT.read_text()))
        OUTPUT.write_text(json.dumps(document, separators=(",", ":")) + "\n")
        print(f"compacted {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            problems = verify(json.loads(OUTPUT.read_text()))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print("GI-2 fork table FAILED")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 fork table OK")
        return 0
    if args.measure:
        document = build(args.jobs)
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        print(json.dumps(document["totals"], indent=2))
        for game in document["games"]:
            print(
                f"{game['env']}: eligible={game['fork_eligible']} "
                f"forks={game['n_forks']} negatives={game['n_negative']} "
                f"alt_positive={game['n_alternative_positive']}"
            )
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
