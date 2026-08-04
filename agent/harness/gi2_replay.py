#!/usr/bin/env python3
"""GI-2 A1 local replay, all-frame fidelity, and reusable fork execution.

The driver executes the frozen local game source directly through
``ARCBaseGame.perform_action(..., raw=True)``.  This is the same engine path used by
``LocalEnvironmentWrapper`` without wrapper-generated GUIDs or recording side effects.

A1's gate is exact equality of every returned frame for all 18 selected iteration sessions.
State, score, available actions, and reset flags are reported too, but only frame equality
controls whether a game may supply negative forks: remote/local reset metadata is not assumed
to be identical.

Run:
  env MPLCONFIGDIR=/private/tmp/ship-jepa-mpl \
    .venv/bin/python agent/harness/gi2_replay.py --measure --jobs 6
  .venv/bin/python agent/harness/gi2_replay.py --verify
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import hashlib
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from arcengine import ARCBaseGame, ActionInput, FrameDataRaw, GameAction

from gi2_replay_freeze import OUTPUT as REPLAY_FREEZE
from gi2_traces import CORPUS, DRAW, ROOT, SESSIONS, normalize_action_id, selected_sessions

ENVIRONMENTS = ROOT / "data/environment_files"
OUTPUT = ROOT / "logs/gi2_replay_fidelity.json"
FORMAT_VERSION = 1
EXPECTED_GAMES = 6
EXPECTED_SESSIONS = 18


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _state_text(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _plain_frames(frames: Iterable[Any]) -> list:
    return [frame.tolist() if hasattr(frame, "tolist") else frame for frame in frames]


def _frames_digest(frames: list) -> str:
    return hashlib.sha256(_canonical(frames)).hexdigest()


@dataclass(frozen=True)
class RecordedAction:
    step: int
    action_id: int
    action_data: dict[str, Any]
    frames: list
    state: str
    levels_completed: int
    win_levels: int
    available_actions: tuple[int, ...]
    full_reset: bool

    def input(self) -> ActionInput:
        return ActionInput(id=GameAction.from_id(self.action_id), data=dict(self.action_data))


def iter_recorded_actions(path: Path) -> Iterator[RecordedAction]:
    step = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            data = json.loads(line).get("data")
            if not isinstance(data, dict) or "frame" not in data:
                continue
            step += 1
            action = data.get("action_input") or {}
            action_data = dict(action.get("data") or {})
            action_data.pop("game_id", None)
            yield RecordedAction(
                step=step,
                action_id=normalize_action_id(action.get("id")),
                action_data=action_data,
                frames=data["frame"],
                state=str(data.get("state")),
                levels_completed=int(data.get("levels_completed") or 0),
                win_levels=int(data.get("win_levels") or 0),
                available_actions=tuple(
                    normalize_action_id(item)
                    for item in (data.get("available_actions") or [])
                ),
                full_reset=bool(data.get("full_reset")),
            )
    if step == 0:
        raise ValueError(f"{path}: no action rows")


def _game_source(env: str) -> Path:
    versions = sorted(path for path in (ENVIRONMENTS / env).iterdir() if path.is_dir())
    if len(versions) != 1:
        raise ValueError(f"{env}: expected one frozen environment version")
    source = versions[0] / f"{env}.py"
    if not source.is_file():
        raise ValueError(f"{env}: game source missing")
    return source


def load_game_class(env: str) -> type[ARCBaseGame]:
    """Execute one frozen source and return its sole ARCBaseGame subclass."""
    source = _game_source(env)
    module_name = f"gi2_replay_{env}_{source.parent.name}"
    spec = importlib.util.spec_from_loader(module_name, loader=None)
    if spec is None:
        raise ValueError(f"{env}: could not create module spec")
    module = importlib.util.module_from_spec(spec)
    code = source.read_text(encoding="utf-8")
    exec(compile(code, str(source), "exec"), module.__dict__)
    classes = [
        value
        for value in module.__dict__.values()
        if isinstance(value, type)
        and value is not ARCBaseGame
        and issubclass(value, ARCBaseGame)
    ]
    if len(classes) != 1:
        raise ValueError(f"{env}: expected exactly one ARCBaseGame subclass")
    return classes[0]


class ReplayDriver:
    """Fresh-game replay and single-action forks for one environment."""

    def __init__(self, env: str):
        self.env = env
        self.game_class = load_game_class(env)

    def new_game(self) -> ARCBaseGame:
        return self.game_class()

    @staticmethod
    def perform(game: ARCBaseGame, action: RecordedAction | ActionInput) -> FrameDataRaw:
        action_input = action.input() if isinstance(action, RecordedAction) else action
        return game.perform_action(action_input, raw=True)  # type: ignore[return-value]

    def replay_prefix(
        self, actions: Iterable[RecordedAction], count: int
    ) -> tuple[ARCBaseGame, list[FrameDataRaw]]:
        if count < 0:
            raise ValueError("prefix count cannot be negative")
        game = self.new_game()
        responses = []
        for index, action in enumerate(actions):
            if index >= count:
                break
            responses.append(self.perform(game, action))
        if len(responses) != count:
            raise ValueError(f"requested prefix {count}, recording supplied {len(responses)}")
        return game, responses

    def fork(
        self,
        actions: list[RecordedAction],
        *,
        before_step: int,
        action_id: int,
        action_data: dict[str, Any] | None = None,
    ) -> FrameDataRaw:
        """Replay actions before 1-based ``before_step``, then execute one alternative."""
        if before_step < 1 or before_step > len(actions):
            raise ValueError("before_step outside recording")
        game, _ = self.replay_prefix(actions, before_step - 1)
        alternative = ActionInput(
            id=GameAction.from_id(action_id),
            data=dict(action_data or {}),
        )
        return self.perform(game, alternative)


def compare_response(recorded: RecordedAction, replayed: FrameDataRaw) -> dict[str, Any]:
    got_frames = _plain_frames(replayed.frame or [])
    frame_match = got_frames == recorded.frames
    metadata = {
        "state": _state_text(replayed.state) == recorded.state,
        "levels_completed": int(replayed.levels_completed or 0) == recorded.levels_completed,
        "win_levels": int(replayed.win_levels or 0) == recorded.win_levels,
        "available_actions": tuple(
            int(getattr(item, "value", item)) for item in (replayed.available_actions or [])
        )
        == recorded.available_actions,
        "full_reset": bool(replayed.full_reset) == recorded.full_reset,
    }
    first_frame_difference = None
    if not frame_match:
        limit = min(len(got_frames), len(recorded.frames))
        for frame_index in range(limit):
            if got_frames[frame_index] != recorded.frames[frame_index]:
                changed = sum(
                    left != right
                    for left_row, right_row in zip(
                        got_frames[frame_index], recorded.frames[frame_index]
                    )
                    for left, right in zip(left_row, right_row)
                )
                first_frame_difference = {
                    "frame_index": frame_index,
                    "changed_cells": changed,
                    "replayed_sha256": _frames_digest([got_frames[frame_index]]),
                    "recorded_sha256": _frames_digest([recorded.frames[frame_index]]),
                }
                break
        if first_frame_difference is None:
            first_frame_difference = {
                "frame_count": {
                    "replayed": len(got_frames),
                    "recorded": len(recorded.frames),
                }
            }
    return {
        "frames": frame_match,
        "metadata": metadata,
        "replayed_frame_digest": _frames_digest(got_frames),
        "recorded_frame_digest": _frames_digest(recorded.frames),
        "first_frame_difference": first_frame_difference,
    }


def measure_session(env: str, selected: dict[str, Any]) -> dict[str, Any]:
    path = CORPUS / env / f"{selected['guid']}.recording.jsonl"
    actions = list(iter_recorded_actions(path))
    driver = ReplayDriver(env)
    game = driver.new_game()
    first_frame_divergence = None
    metadata_mismatches: dict[str, int] = {}
    frame_sequence = hashlib.sha256()
    replayed_sequence = hashlib.sha256()
    for action in actions:
        response = driver.perform(game, action)
        comparison = compare_response(action, response)
        frame_sequence.update(comparison["recorded_frame_digest"].encode())
        replayed_sequence.update(comparison["replayed_frame_digest"].encode())
        if not comparison["frames"] and first_frame_divergence is None:
            first_frame_divergence = {
                "step": action.step,
                "action_id": action.action_id,
                "detail": comparison["first_frame_difference"],
            }
        for field, matched in comparison["metadata"].items():
            if not matched:
                metadata_mismatches[field] = metadata_mismatches.get(field, 0) + 1
    return {
        **selected,
        "recording": str(path.relative_to(ROOT)),
        "recording_sha256": _sha256(path),
        "action_rows": len(actions),
        "frame_fidelity": first_frame_divergence is None,
        "first_frame_divergence": first_frame_divergence,
        "recorded_frame_sequence_sha256": frame_sequence.hexdigest(),
        "replayed_frame_sequence_sha256": replayed_sequence.hexdigest(),
        "metadata_mismatches": metadata_mismatches,
    }


def measure_all(jobs: int = 1) -> dict[str, Any]:
    draw = json.loads(DRAW.read_text())
    sessions = json.loads(SESSIONS.read_text())
    work = [
        (env, selected)
        for env in draw["iteration"]
        for selected in selected_sessions(env, sessions, draw)
    ]
    if len(work) != EXPECTED_SESSIONS:
        raise ValueError(f"expected {EXPECTED_SESSIONS} selected sessions, got {len(work)}")
    if jobs < 1:
        raise ValueError("jobs must be positive")
    results = []
    if jobs == 1:
        results = [measure_session(env, selected) for env, selected in work]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {
                pool.submit(measure_session, env, selected): (env, selected["guid"])
                for env, selected in work
            }
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
    results.sort(key=lambda row: (row["recording"].split("/")[3], row["rank"]))
    by_game = []
    for env in draw["iteration"]:
        rows = [row for row in results if f"/{env}/" in row["recording"]]
        by_game.append(
            {
                "env": env,
                "frame_fidelity": bool(rows) and all(row["frame_fidelity"] for row in rows),
                "sessions": rows,
                "metadata_mismatches": {
                    key: sum(row["metadata_mismatches"].get(key, 0) for row in rows)
                    for key in sorted(
                        {
                            key
                            for row in rows
                            for key in row["metadata_mismatches"]
                        }
                    )
                },
            }
        )
    return {
        "format_version": FORMAT_VERSION,
        "status": "a1_measured",
        "scope": "iteration",
        "inputs": {
            "replay_freeze": str(REPLAY_FREEZE.relative_to(ROOT)),
            "replay_freeze_sha256": _sha256(REPLAY_FREEZE),
            "draw_sha256": _sha256(DRAW),
            "sessions_sha256": _sha256(SESSIONS),
        },
        "totals": {
            "games": len(by_game),
            "sessions": len(results),
            "frame_fidelity_games": sum(game["frame_fidelity"] for game in by_game),
            "frame_fidelity_sessions": sum(row["frame_fidelity"] for row in results),
            "action_rows": sum(row["action_rows"] for row in results),
        },
        "games": by_game,
    }


def verify(document: Any) -> list[str]:
    problems = []
    if not isinstance(document, dict):
        return ["artifact: expected an object"]
    if document.get("format_version") != FORMAT_VERSION:
        problems.append("artifact.format_version: unexpected")
    inputs = document.get("inputs")
    for name, path in (
        ("replay_freeze", REPLAY_FREEZE),
        ("draw", DRAW),
        ("sessions", SESSIONS),
    ):
        if not path.is_file():
            problems.append(f"{name}: input missing")
        elif not isinstance(inputs, dict) or inputs.get(f"{name}_sha256") != _sha256(path):
            problems.append(f"artifact.inputs.{name}_sha256: drift")
    games = document.get("games")
    if not isinstance(games, list) or len(games) != EXPECTED_GAMES:
        problems.append(f"artifact.games: expected {EXPECTED_GAMES}")
        return problems
    sessions = [row for game in games for row in game.get("sessions", [])]
    if len(sessions) != EXPECTED_SESSIONS:
        problems.append(f"artifact.games: expected {EXPECTED_SESSIONS} sessions")
    for game in games:
        rows = game.get("sessions")
        if not isinstance(rows, list) or len(rows) != 3:
            problems.append(f"{game.get('env')}: expected three sessions")
            continue
        if game.get("frame_fidelity") != all(row.get("frame_fidelity") for row in rows):
            problems.append(f"{game.get('env')}: aggregate fidelity mismatch")
        for row in rows:
            recording = ROOT / str(row.get("recording", ""))
            if not recording.is_file():
                problems.append(f"{game.get('env')}/{row.get('guid')}: recording missing")
            elif row.get("recording_sha256") != _sha256(recording):
                problems.append(f"{game.get('env')}/{row.get('guid')}: recording drift")
    totals = document.get("totals")
    if not isinstance(totals, dict):
        problems.append("artifact.totals: expected an object")
    else:
        if totals.get("games") != len(games):
            problems.append("artifact.totals.games: mismatch")
        if totals.get("sessions") != len(sessions):
            problems.append("artifact.totals.sessions: mismatch")
        if totals.get("frame_fidelity_games") != sum(
            bool(game.get("frame_fidelity")) for game in games
        ):
            problems.append("artifact.totals.frame_fidelity_games: mismatch")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    if args.measure:
        document = measure_all(args.jobs)
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        totals = document["totals"]
        print(
            "GI-2 replay fidelity measured — "
            f"{totals['frame_fidelity_games']}/{totals['games']} games, "
            f"{totals['frame_fidelity_sessions']}/{totals['sessions']} sessions, "
            f"{totals['action_rows']} action rows exact"
        )
        for game in document["games"]:
            print(
                f"  {game['env']}: {'PASS' if game['frame_fidelity'] else 'FAIL'} "
                f"metadata_mismatches={game['metadata_mismatches']}"
            )
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            document = json.loads(OUTPUT.read_text())
            problems = verify(document)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print(f"GI-2 replay fidelity FAILED — {len(problems)} problem(s)")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 replay fidelity artifact OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
