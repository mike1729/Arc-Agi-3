"""Tests for the GI-2 all-frame extractor and A0 frame audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))
import gi2_traces as T  # noqa: E402

requires_corpus = pytest.mark.skipif(
    not T.CORPUS.exists() or not T.OUTPUT.exists(),
    reason="human replay corpus or measured A0 artifact absent",
)


def _grid(value: int) -> list[list[int]]:
    return [[value] * T.GRID_SIZE for _ in range(T.GRID_SIZE)]


def _row(
    frames: list,
    *,
    action=1,
    levels=0,
    state="NOT_FINISHED",
    data=None,
) -> str:
    return json.dumps(
        {
            "data": {
                "frame": frames,
                "action_input": {"id": action, "data": data or {}},
                "levels_completed": levels,
                "state": state,
                "available_actions": [1, "ACTION6"],
                "full_reset": action == 0,
            }
        }
    )


@pytest.mark.parametrize(
    "state,n_frames,increment,expected",
    [
        ("NOT_FINISHED", 1, 0, (T.ROLE_SETTLED,)),
        (
            "NOT_FINISHED",
            3,
            0,
            (T.ROLE_INTERMEDIATE, T.ROLE_INTERMEDIATE, T.ROLE_SETTLED),
        ),
        (
            "NOT_FINISHED",
            2,
            1,
            (T.ROLE_SOLVED_TERMINAL, T.ROLE_NEXT_LEVEL_INITIAL),
        ),
        (
            "NOT_FINISHED",
            4,
            1,
            (
                T.ROLE_INTERMEDIATE,
                T.ROLE_INTERMEDIATE,
                T.ROLE_SOLVED_TERMINAL,
                T.ROLE_NEXT_LEVEL_INITIAL,
            ),
        ),
        (
            "WIN",
            3,
            1,
            (T.ROLE_INTERMEDIATE, T.ROLE_INTERMEDIATE, T.ROLE_SOLVED_TERMINAL),
        ),
        ("GAME_OVER", 0, 0, ()),
    ],
)
def test_frame_roles_cover_ordinary_completion_animation_and_win(
    state, n_frames, increment, expected
):
    assert T.frame_roles(
        state=state, n_frames=n_frames, completion_increment=increment
    ) == expected


@pytest.mark.parametrize(
    "state,n_frames,increment,message",
    [
        ("WIN", 0, 1, "WIN completion returned no frames"),
        ("NOT_FINISHED", 1, 1, "needs terminal and next-level"),
        ("NOT_FINISHED", 1, -1, "cannot decrease"),
        ("NOT_FINISHED", -1, 0, "cannot be negative"),
    ],
)
def test_frame_roles_reject_invalid_completion_shapes(
    state, n_frames, increment, message
):
    with pytest.raises(ValueError, match=message):
        T.frame_roles(
            state=state, n_frames=n_frames, completion_increment=increment
        )


def test_iter_trace_preserves_every_frame_and_assigns_terminal_roles(tmp_path):
    recording = tmp_path / "session.recording.jsonl"
    recording.write_text(
        "\n".join(
            [
                _row([_grid(0)], action=0),
                _row([_grid(1), _grid(2)], levels=1),
                _row(
                    [_grid(3), _grid(4), _grid(5)],
                    levels=2,
                    state="WIN",
                    data={"game_id": "ignored", "x": 4, "y": 5},
                ),
                json.dumps({"data": {"won": 1}}),
            ]
        )
        + "\n"
    )
    steps = list(T.iter_trace(recording))
    assert len(steps) == 3
    assert [frame.role for frame in steps[1].frames] == [
        T.ROLE_SOLVED_TERMINAL,
        T.ROLE_NEXT_LEVEL_INITIAL,
    ]
    assert steps[1].solved_terminal.grid == _grid(1)
    assert steps[1].next_level_initial.grid == _grid(2)
    assert [frame.role for frame in steps[2].frames] == [
        T.ROLE_INTERMEDIATE,
        T.ROLE_INTERMEDIATE,
        T.ROLE_SOLVED_TERMINAL,
    ]
    assert steps[2].action_data == {"x": 4, "y": 5}
    assert steps[2].available_actions == (1, 6)


def test_iter_trace_rejects_out_of_range_grid_cell(tmp_path):
    recording = tmp_path / "bad.recording.jsonl"
    bad = _grid(0)
    bad[2][3] = 16
    recording.write_text(_row([bad]) + "\n")
    with pytest.raises(ValueError, match="outside 0..15"):
        list(T.iter_trace(recording))


def test_selected_sessions_reproduces_tier_and_order():
    draw = {"iteration": ["aa11"], "reserved": ["rr11"]}
    rows = {
        "sessions": [
            {
                "env": "aa11",
                "guid": guid,
                "levels_completed": levels,
                "total_actions": actions,
                "action_lines": actions + 1,
                "line_delta": 1,
            }
            for guid, levels, actions in [
                ("slow", 4, 20),
                ("best", 4, 10),
                ("second", 3, 8),
                ("low", 2, 1),
            ]
        ]
    }
    selected = T.selected_sessions("aa11", rows, draw)
    assert [row["guid"] for row in selected] == ["best", "slow", "second"]
    assert {row["tier"] for row in selected} == {3}
    with pytest.raises(ValueError, match="reserved"):
        T.selected_sessions("rr11", rows, draw)


@pytest.mark.parametrize(
    "raw,expected",
    [("RESET", 0), (" reset ", 0), ("5", 5), (5, 5), ("ACTION6", 6)],
)
def test_normalize_action_id_accepts_every_recorded_spelling(raw, expected):
    assert T.normalize_action_id(raw) == expected


@pytest.mark.parametrize("raw", [True, False])
def test_normalize_action_id_rejects_booleans(raw):
    with pytest.raises(ValueError, match="boolean"):
        T.normalize_action_id(raw)


def test_selected_sessions_rejects_malformed_draw_and_outside_game():
    sessions = {"sessions": []}
    with pytest.raises(ValueError, match="must contain"):
        T.selected_sessions("aa11", sessions, {"iteration": None, "reserved": []})
    with pytest.raises(ValueError, match="outside"):
        T.selected_sessions(
            "aa11", sessions, {"iteration": ["bb22"], "reserved": []}
        )


def test_iter_trace_rejects_non_list_frames_and_recording_without_actions(tmp_path):
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text(json.dumps({"data": {"frame": {}}}) + "\n")
    with pytest.raises(ValueError, match="frame must be a list"):
        list(T.iter_trace(malformed))
    empty = tmp_path / "empty.jsonl"
    empty.write_text(json.dumps({"data": {"won": 1}}) + "\n")
    with pytest.raises(ValueError, match="no action rows"):
        list(T.iter_trace(empty))


@pytest.mark.parametrize(
    "grid,message",
    [
        ({}, "grid is not"),
        ([[0] * T.GRID_SIZE for _ in range(T.GRID_SIZE - 1)], "grid is not"),
        ([[0] * (T.GRID_SIZE - 1)] + [[0] * T.GRID_SIZE for _ in range(T.GRID_SIZE - 1)],
         "row 0 is not"),
    ],
)
def test_iter_trace_rejects_malformed_grid_shapes(tmp_path, grid, message):
    recording = tmp_path / "bad-shape.jsonl"
    recording.write_text(_row([grid]) + "\n")
    with pytest.raises(ValueError, match=message):
        list(T.iter_trace(recording))


def _minimal_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    draw = tmp_path / "draw.json"
    sessions = tmp_path / "sessions.json"
    draw.write_text("{}")
    sessions.write_text("{}")
    monkeypatch.setattr(T, "DRAW", draw)
    monkeypatch.setattr(T, "SESSIONS", sessions)
    games = []
    for game_index in range(T.EXPECTED_GAMES):
        rows = []
        for session_index in range(3):
            recording = tmp_path / f"g{game_index}s{session_index}.jsonl"
            recording.write_text("{}")
            completions = [
                {
                    "roles": [T.ROLE_SOLVED_TERMINAL],
                }
                for _ in range(7 if game_index >= 2 else 6)
            ]
            # 6 + 6 + 7 + 7 + 7 + 7 = 40, so expand the first row below to 123 total.
            rows.append(
                {
                    "guid": f"s{session_index}",
                    "recording": recording.name,
                    "recording_sha256": T._sha256(recording),
                    "completions": completions,
                }
            )
        games.append({"env": f"g{game_index}", "sessions": rows})
    current = sum(len(row["completions"]) for game in games for row in game["sessions"])
    games[0]["sessions"][0]["completions"].extend(
        {"roles": [T.ROLE_SOLVED_TERMINAL]}
        for _ in range(T.EXPECTED_COMPLETIONS - current)
    )
    return {
        "format_version": T.FORMAT_VERSION,
        "scope": "iteration",
        "inputs": {
            "draw_sha256": T._sha256(draw),
            "sessions_sha256": T._sha256(sessions),
        },
        "totals": {
            "games": T.EXPECTED_GAMES,
            "sessions": T.EXPECTED_SESSIONS,
            "completions": T.EXPECTED_COMPLETIONS,
        },
        "games": games,
    }


def test_verify_validation_rejects_non_object():
    assert T.verify_validation(None) == ["artifact: expected an object"]


@pytest.mark.parametrize(
    "mutation,fragment",
    [
        (lambda d: d["games"].__setitem__(0, None), "expected an object"),
        (lambda d: d["games"][1].__setitem__("env", d["games"][0]["env"]), "duplicate"),
        (lambda d: d["games"][0].__setitem__("sessions", None), "expected a list"),
        (lambda d: d["games"][0]["sessions"].__setitem__(0, None), "invalid row"),
        (
            lambda d: d["games"][0]["sessions"][0].__setitem__("completions", None),
            "completions must be a list",
        ),
    ],
)
def test_verify_validation_rejects_malformed_nested_rows(
    tmp_path, monkeypatch, mutation, fragment
):
    document = _minimal_artifact(tmp_path, monkeypatch)
    mutation(document)
    assert any(fragment in problem for problem in T.verify_validation(document))


def test_session_audit_checks_action_rows_line_delta_levels_and_completion_shape(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(T, "ROOT", tmp_path)
    monkeypatch.setattr(T, "CORPUS", tmp_path)
    env, guid = "aa11", "g"
    directory = tmp_path / env
    directory.mkdir()
    recording = directory / f"{guid}.recording.jsonl"
    recording.write_text(_row([_grid(0)], action=0) + "\n")
    selected = {
        "guid": guid,
        "rank": 0,
        "tier": 1,
        "levels_completed": 0,
        "total_actions": 0,
        "action_lines": 1,
        "line_delta": 1,
    }
    assert T._session_audit(env, selected)["leading_reset"] is True
    with pytest.raises(ValueError, match="action rows"):
        T._session_audit(env, {**selected, "action_lines": 2})
    with pytest.raises(ValueError, match="line_delta"):
        T._session_audit(env, {**selected, "line_delta": 0})
    with pytest.raises(ValueError, match="streamed 0 completions"):
        T._session_audit(env, {**selected, "levels_completed": 1})

    no_terminal = T.TraceStep(
        index=1,
        action_id=1,
        action_data={},
        levels_completed=1,
        state="NOT_FINISHED",
        available_actions=(),
        full_reset=False,
        frames=(),
        completion_increment=1,
    )
    monkeypatch.setattr(T, "iter_trace", lambda _: iter([no_terminal]))
    with pytest.raises(ValueError, match="has no terminal"):
        T._session_audit(
            env,
            {
                **selected,
                "levels_completed": 1,
                "total_actions": 1,
                "line_delta": 0,
            },
        )
    jump = T.TraceStep(
        **{**no_terminal.__dict__, "completion_increment": 2, "levels_completed": 2}
    )
    monkeypatch.setattr(T, "iter_trace", lambda _: iter([jump]))
    with pytest.raises(ValueError, match="increments by 2"):
        T._session_audit(
            env,
            {
                **selected,
                "levels_completed": 2,
                "total_actions": 1,
                "line_delta": 0,
            },
        )


@pytest.mark.parametrize("mode", ["games", "sessions", "completions"])
def test_build_validation_enforces_declared_experiment_size(
    tmp_path, monkeypatch, mode
):
    draw = tmp_path / "draw.json"
    sessions = tmp_path / "sessions.json"
    games = ["a", "b", "c", "d", "e", "f"]
    draw.write_text(json.dumps({"iteration": games, "reserved": []}))
    sessions.write_text(json.dumps({"sessions": []}))
    monkeypatch.setattr(T, "DRAW", draw)
    monkeypatch.setattr(T, "SESSIONS", sessions)
    monkeypatch.setattr(
        T,
        "selected_sessions",
        lambda env, sessions_doc, draw_doc: [{"guid": f"{env}-{i}"} for i in range(3)],
    )
    completions = 7
    monkeypatch.setattr(
        T,
        "_session_audit",
        lambda env, selected: {
            **selected,
            "completion_structures": {},
            "completions": [{}] * completions,
        },
    )
    if mode == "games":
        draw.write_text(json.dumps({"iteration": games[:-1], "reserved": []}))
    elif mode == "sessions":
        monkeypatch.setattr(
            T,
            "selected_sessions",
            lambda env, sessions_doc, draw_doc: [{"guid": f"{env}-0"}],
        )
    else:
        monkeypatch.setattr(T, "EXPECTED_COMPLETIONS", 123)
    with pytest.raises(ValueError, match=f"expected .* {mode}"):
        T.build_validation()


@requires_corpus
def test_measured_frame_artifact_reproduces_all_18_sessions_and_123_completions():
    document = json.loads(T.OUTPUT.read_text())
    assert T.verify_validation(document) == []
    assert document["totals"]["games"] == 6
    assert document["totals"]["sessions"] == 18
    assert document["totals"]["completions"] == 123
    assert document["totals"]["completion_structures"] == {
        "NOT_FINISHED:14": 15,
        "NOT_FINISHED:2": 81,
        "NOT_FINISHED:9": 9,
        "WIN:1": 15,
        "WIN:13": 3,
    }
