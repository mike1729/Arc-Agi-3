#!/usr/bin/env python3
"""GI-2 all-frame trace extraction and the A0 frame-structure experiment.

GI-1 intentionally reduced every action response to ``frame[-1]``.  GI-2 instead preserves
every returned frame and assigns roles mechanically:

* an ordinary action: earlier frames are ``intermediate`` and the last is ``settled``;
* a non-final completion: earlier frames are ``intermediate``, ``frame[-2]`` is
  ``solved_terminal``, and ``frame[-1]`` is ``next_level_initial``;
* a final ``WIN`` completion: earlier frames are ``intermediate`` and ``frame[-1]`` is
  ``solved_terminal``.

The module streams recordings.  Loading all frames from a long human session as Python lists
would use hundreds of megabytes and is unnecessary for both A0 and later trajectory passes.

Run:
  .venv/bin/python agent/harness/gi2_traces.py --validate
  .venv/bin/python agent/harness/gi2_traces.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data/human_replays/kaggle_mirror/public_games-dataset"
SESSIONS = ROOT / "logs/s2_replay_sessions.json"
DRAW = ROOT / "logs/gi1_game_draw.json"
OUTPUT = ROOT / "logs/gi2_frame_validation.json"

FORMAT_VERSION = 1
GRID_SIZE = 64
CELL_MIN = 0
CELL_MAX = 15
EXPECTED_GAMES = 6
EXPECTED_SESSIONS = 18
EXPECTED_COMPLETIONS = 123
ROLE_INTERMEDIATE = "intermediate"
ROLE_SETTLED = "settled"
ROLE_SOLVED_TERMINAL = "solved_terminal"
ROLE_NEXT_LEVEL_INITIAL = "next_level_initial"
FRAME_ROLES = {
    ROLE_INTERMEDIATE,
    ROLE_SETTLED,
    ROLE_SOLVED_TERMINAL,
    ROLE_NEXT_LEVEL_INITIAL,
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _grid_digest(grid: list) -> str:
    return hashlib.sha256(_canonical(grid)).hexdigest()


def normalize_action_id(raw: Any) -> int:
    if isinstance(raw, bool):
        raise ValueError(f"boolean action id: {raw!r}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        text = raw.strip().upper()
        if text == "RESET":
            return 0
        if text.startswith("ACTION") and text[6:].isdigit():
            return int(text[6:])
        if text.isdigit():
            return int(text)
    raise ValueError(f"unrecognized action id: {raw!r}")


def selected_sessions(
    env: str,
    sessions_doc: dict[str, Any],
    draw_doc: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reproduce the accepted three-session rule without importing frozen GI-1 code."""
    iteration = draw_doc.get("iteration")
    reserved = draw_doc.get("reserved")
    if not isinstance(iteration, list) or not isinstance(reserved, list):
        raise ValueError("draw must contain iteration and reserved lists")
    if env in reserved:
        raise ValueError(f"{env} is reserved")
    if env not in iteration:
        raise ValueError(f"{env} is outside the iteration slice")
    rows = [
        row for row in sessions_doc.get("sessions", [])
        if isinstance(row, dict) and row.get("env") == env
    ]
    rows.sort(
        key=lambda row: (
            -int(row.get("levels_completed", 0)),
            int(row.get("total_actions", 0)),
            str(row.get("guid", "")),
        )
    )
    for tier in (3, 2, 1):
        eligible = [row for row in rows if int(row.get("levels_completed", 0)) >= tier]
        if len(eligible) >= 3 or tier == 1:
            return [
                {
                    "guid": str(row["guid"]),
                    "levels_completed": int(row["levels_completed"]),
                    "total_actions": int(row["total_actions"]),
                    "action_lines": int(row["action_lines"]),
                    "line_delta": int(row["line_delta"]),
                    "tier": tier,
                    "rank": rank,
                }
                for rank, row in enumerate(eligible[:3])
            ]
    return []


@dataclass(frozen=True)
class TraceFrame:
    index: int
    role: str
    grid: list


@dataclass(frozen=True)
class TraceStep:
    index: int
    action_id: int
    action_data: dict[str, Any]
    levels_completed: int
    state: str
    available_actions: tuple[int, ...]
    full_reset: bool
    frames: tuple[TraceFrame, ...]
    completion_increment: int

    @property
    def is_completion(self) -> bool:
        return self.completion_increment > 0

    @property
    def solved_terminal(self) -> TraceFrame | None:
        return next(
            (frame for frame in self.frames if frame.role == ROLE_SOLVED_TERMINAL),
            None,
        )

    @property
    def next_level_initial(self) -> TraceFrame | None:
        return next(
            (frame for frame in self.frames if frame.role == ROLE_NEXT_LEVEL_INITIAL),
            None,
        )


def frame_roles(*, state: str, n_frames: int, completion_increment: int) -> tuple[str, ...]:
    """Return one role per frame or raise when the completion rule is not applicable."""
    if n_frames < 0:
        raise ValueError("n_frames cannot be negative")
    if completion_increment < 0:
        raise ValueError("levels_completed cannot decrease")
    if completion_increment:
        if state == "WIN":
            if n_frames < 1:
                raise ValueError("WIN completion returned no frames")
            return (ROLE_INTERMEDIATE,) * (n_frames - 1) + (ROLE_SOLVED_TERMINAL,)
        if n_frames < 2:
            raise ValueError("non-WIN completion needs terminal and next-level frames")
        return (
            (ROLE_INTERMEDIATE,) * (n_frames - 2)
            + (ROLE_SOLVED_TERMINAL, ROLE_NEXT_LEVEL_INITIAL)
        )
    if n_frames == 0:
        return ()
    return (ROLE_INTERMEDIATE,) * (n_frames - 1) + (ROLE_SETTLED,)


def _validate_grid(grid: Any, where: str) -> None:
    if not isinstance(grid, list) or len(grid) != GRID_SIZE:
        raise ValueError(f"{where}: grid is not {GRID_SIZE} rows")
    for row_index, row in enumerate(grid):
        if not isinstance(row, list) or len(row) != GRID_SIZE:
            raise ValueError(f"{where}: row {row_index} is not {GRID_SIZE} cells")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < CELL_MIN
            or value > CELL_MAX
            for value in row
        ):
            raise ValueError(f"{where}: row {row_index} has a cell outside 0..15")


def iter_trace(path: Path) -> Iterator[TraceStep]:
    """Stream action rows from one recording while preserving every returned frame."""
    previous_levels = 0
    step_index = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            row = json.loads(line)
            data = row.get("data")
            if not isinstance(data, dict) or "frame" not in data:
                continue
            step_index += 1
            raw_frames = data["frame"]
            if not isinstance(raw_frames, list):
                raise ValueError(f"{path}:{line_number}: frame must be a list")
            levels = int(data.get("levels_completed") or 0)
            increment = levels - previous_levels
            state = str(data.get("state"))
            roles = frame_roles(
                state=state,
                n_frames=len(raw_frames),
                completion_increment=increment,
            )
            frames = []
            for frame_index, (grid, role) in enumerate(zip(raw_frames, roles)):
                _validate_grid(grid, f"{path}:{line_number}:frame[{frame_index}]")
                frames.append(TraceFrame(index=frame_index, role=role, grid=grid))
            action = data.get("action_input") or {}
            action_data = dict(action.get("data") or {})
            action_data.pop("game_id", None)
            available = tuple(
                normalize_action_id(item) for item in (data.get("available_actions") or [])
            )
            yield TraceStep(
                index=step_index,
                action_id=normalize_action_id(action.get("id")),
                action_data=action_data,
                levels_completed=levels,
                state=state,
                available_actions=available,
                full_reset=bool(data.get("full_reset")),
                frames=tuple(frames),
                completion_increment=increment,
            )
            previous_levels = levels
    if step_index == 0:
        raise ValueError(f"{path}: no action rows")


def _session_audit(env: str, selected: dict[str, Any]) -> dict[str, Any]:
    guid = selected["guid"]
    path = CORPUS / env / f"{guid}.recording.jsonl"
    structures: Counter[str] = Counter()
    completions = []
    actions = 0
    last_levels = 0
    leading_reset = None
    for step in iter_trace(path):
        actions += 1
        if leading_reset is None:
            leading_reset = step.action_id == 0
        last_levels = step.levels_completed
        if not step.is_completion:
            continue
        if step.completion_increment != 1:
            raise ValueError(
                f"{env}/{guid}: completion at step {step.index} increments by "
                f"{step.completion_increment}"
            )
        terminal = step.solved_terminal
        if terminal is None:
            raise ValueError(f"{env}/{guid}: completion at step {step.index} has no terminal")
        next_initial = step.next_level_initial
        structure = f"{step.state}:{len(step.frames)}"
        structures[structure] += 1
        completions.append(
            {
                "step": step.index,
                "level": step.levels_completed,
                "state": step.state,
                "n_frames": len(step.frames),
                "roles": [frame.role for frame in step.frames],
                "terminal_frame_sha256": _grid_digest(terminal.grid),
                "next_level_frame_sha256": (
                    _grid_digest(next_initial.grid) if next_initial is not None else None
                ),
            }
        )
    if actions != selected["action_lines"]:
        raise ValueError(
            f"{env}/{guid}: streamed {actions} action rows != "
            f"selected {selected['action_lines']}"
        )
    if actions - selected["total_actions"] != selected["line_delta"]:
        raise ValueError(f"{env}/{guid}: action-card line_delta does not reproduce")
    if last_levels != selected["levels_completed"]:
        raise ValueError(
            f"{env}/{guid}: streamed {last_levels} completions != "
            f"selected {selected['levels_completed']}"
        )
    return {
        **selected,
        "recording": str(path.relative_to(ROOT)),
        "recording_sha256": _sha256(path),
        "leading_reset": leading_reset,
        "completion_structures": dict(sorted(structures.items())),
        "completions": completions,
    }


def build_validation() -> dict[str, Any]:
    sessions_doc = json.loads(SESSIONS.read_text())
    draw_doc = json.loads(DRAW.read_text())
    games = []
    total_sessions = 0
    total_completions = 0
    structures: Counter[str] = Counter()
    for env in draw_doc["iteration"]:
        rows = []
        for selected in selected_sessions(env, sessions_doc, draw_doc):
            audited = _session_audit(env, selected)
            rows.append(audited)
            total_sessions += 1
            total_completions += len(audited["completions"])
            structures.update(audited["completion_structures"])
        games.append(
            {
                "env": env,
                "n_sessions": len(rows),
                "n_completions": sum(len(row["completions"]) for row in rows),
                "sessions": rows,
            }
        )
    if len(games) != EXPECTED_GAMES:
        raise ValueError(f"expected {EXPECTED_GAMES} iteration games, got {len(games)}")
    if total_sessions != EXPECTED_SESSIONS:
        raise ValueError(f"expected {EXPECTED_SESSIONS} sessions, got {total_sessions}")
    if total_completions != EXPECTED_COMPLETIONS:
        raise ValueError(
            f"expected {EXPECTED_COMPLETIONS} completions, got {total_completions}"
        )
    return {
        "format_version": FORMAT_VERSION,
        "status": "a0_measured",
        "scope": "iteration",
        "rule": {
            "win": "terminal=frame[-1]",
            "non_win_completion": "terminal=frame[-2]; next_level=frame[-1]",
            "earlier_frames": ROLE_INTERMEDIATE,
        },
        "inputs": {
            "draw": str(DRAW.relative_to(ROOT)),
            "draw_sha256": _sha256(DRAW),
            "sessions": str(SESSIONS.relative_to(ROOT)),
            "sessions_sha256": _sha256(SESSIONS),
        },
        "totals": {
            "games": len(games),
            "sessions": total_sessions,
            "completions": total_completions,
            "completion_structures": dict(sorted(structures.items())),
        },
        "games": games,
    }


def verify_validation(document: Any) -> list[str]:
    problems = []
    if not isinstance(document, dict):
        return ["artifact: expected an object"]
    if document.get("format_version") != FORMAT_VERSION:
        problems.append("artifact.format_version: unexpected")
    if document.get("scope") != "iteration":
        problems.append("artifact.scope: expected iteration")
    totals = document.get("totals")
    expected = {
        "games": EXPECTED_GAMES,
        "sessions": EXPECTED_SESSIONS,
        "completions": EXPECTED_COMPLETIONS,
    }
    if not isinstance(totals, dict):
        problems.append("artifact.totals: expected an object")
    else:
        for name, value in expected.items():
            if totals.get(name) != value:
                problems.append(f"artifact.totals.{name}: expected {value}")
    inputs = document.get("inputs")
    for name, path in (("draw", DRAW), ("sessions", SESSIONS)):
        if not isinstance(inputs, dict) or inputs.get(f"{name}_sha256") != _sha256(path):
            problems.append(f"artifact.inputs.{name}_sha256: input drift")
    games = document.get("games")
    if not isinstance(games, list) or len(games) != EXPECTED_GAMES:
        problems.append(f"artifact.games: expected {EXPECTED_GAMES} rows")
    else:
        seen: set[str] = set()
        counted_sessions = counted_completions = 0
        for game_index, game in enumerate(games):
            if not isinstance(game, dict):
                problems.append(f"artifact.games[{game_index}]: expected an object")
                continue
            env = game.get("env")
            if not isinstance(env, str) or env in seen:
                problems.append(f"artifact.games[{game_index}].env: invalid or duplicate")
                continue
            seen.add(env)
            rows = game.get("sessions")
            if not isinstance(rows, list):
                problems.append(f"artifact.games[{game_index}].sessions: expected a list")
                continue
            counted_sessions += len(rows)
            for row in rows:
                if not isinstance(row, dict):
                    problems.append(f"artifact.games[{game_index}].sessions: invalid row")
                    continue
                recording = ROOT / str(row.get("recording", ""))
                if not recording.is_file():
                    problems.append(f"{env}/{row.get('guid')}: recording missing")
                elif row.get("recording_sha256") != _sha256(recording):
                    problems.append(f"{env}/{row.get('guid')}: recording digest drift")
                completions = row.get("completions")
                if not isinstance(completions, list):
                    problems.append(f"{env}/{row.get('guid')}: completions must be a list")
                    continue
                counted_completions += len(completions)
                for completion in completions:
                    roles = completion.get("roles") if isinstance(completion, dict) else None
                    if (
                        not isinstance(roles, list)
                        or not roles
                        or any(role not in FRAME_ROLES for role in roles)
                        or roles.count(ROLE_SOLVED_TERMINAL) != 1
                    ):
                        problems.append(
                            f"{env}/{row.get('guid')}: invalid completion frame roles"
                        )
        if counted_sessions != EXPECTED_SESSIONS:
            problems.append(f"artifact.games: counted {counted_sessions} sessions")
        if counted_completions != EXPECTED_COMPLETIONS:
            problems.append(f"artifact.games: counted {counted_completions} completions")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.validate:
        document = build_validation()
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        totals = document["totals"]
        print(
            "GI-2 frame validation OK — "
            f"{totals['games']} games, {totals['sessions']} sessions, "
            f"{totals['completions']} completions"
        )
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            document = json.loads(OUTPUT.read_text())
            problems = verify_validation(document)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print(f"GI-2 frame validation FAILED — {len(problems)} problem(s)")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 frame validation artifact OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
