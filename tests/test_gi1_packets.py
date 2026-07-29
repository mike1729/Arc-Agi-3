"""Direct tests for `gi1_packets` — the GI-1 canonical evidence-packet layer.

WHY THIS FILE EXISTS. `gi1_packets.py --selftest` is real coverage but narrow in a way that
matters: it runs on the three ITERATION games (ls20, vc33, m0r0) by design, and it is not
collected by pytest. The two games whose recordings deviate from the default shape — cn04
(no leading RESET line, and the only game with empty `frame` lines) and lf52 (mixed: two
sessions with a leading RESET, one without) — are ONE-SHOT games. So the branches that
handle them had no assertions anywhere. A one-shot game is read once with no iteration
afterwards, which means a packet defect there is found only after the read has already
spent the game.

Two groups, split by what they need:

  - SYNTHETIC tests build recordings on a temporary CORPUS root. They need no replay data
    and cover the guards and error branches that no real session reaches — every `raise` in
    the module, plus the checkpoint-validity boundary.
  - CORPUS tests assert the measured quirks against the real mirror and skip when it is
    absent (mutation sandbox, or a checkout without the replay data).

Run:
  .venv/bin/python -m pytest tests/test_gi1_packets.py -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_packets as P     # noqa: E402

# Resolved at import, before any fixture monkeypatches P.CORPUS.
CORPUS_PRESENT = P.CORPUS.exists() and P.SESSIONS_TABLE.exists() and P.DRAW.exists()
requires_corpus = pytest.mark.skipif(
    not CORPUS_PRESENT, reason="replay corpus not present (mutation sandbox / no mirror)")


# --------------------------------------------------------------------------- synthetic corpus

def _grid(v: int = 0, n: int = 2) -> list:
    """A settled grid. Nothing in the packet layer inspects its size, so these stay small;
    the 64x64 / 0..15 invariants are the selftest's job, against real recordings."""
    return [[v] * n for _ in range(n)]


def _line(action_id, frames, *, levels: int = 0, state: str = "NOT_FINISHED") -> str:
    return json.dumps({"data": {
        "frame": frames,
        "action_input": {"id": action_id, "data": {}},
        "levels_completed": levels,
        "win_levels": 3,
        "available_actions": [1, 2, 3],
        "state": state,
        "full_reset": False,
    }})


@pytest.fixture
def write_recording(tmp_path, monkeypatch):
    """Write a synthetic recording and point the module's CORPUS at it."""
    root = tmp_path / "corpus"
    monkeypatch.setattr(P, "CORPUS", root)

    def write(env: str, guid: str, lines: list[str]) -> None:
        (root / env).mkdir(parents=True, exist_ok=True)
        (root / env / f"{guid}.recording.jsonl").write_text("\n".join(lines) + "\n")

    return write


@pytest.fixture
def _synthetic_draw(tmp_path, monkeypatch):
    """A draw reserving nothing, so selection tests do not depend on the real draw."""
    draw = tmp_path / "draw.json"
    draw.write_text(json.dumps({"iteration": ["aa11"], "reserved": [], "one_shot": []}))
    monkeypatch.setattr(P, "DRAW", draw)
    return draw


def _plain_session(n_steps: int, *, completion_at: int | None = None) -> list[str]:
    """RESET then n_steps-1 actions, optionally incrementing levels_completed at one step."""
    lines, levels = [], 0
    for i in range(1, n_steps + 1):
        if completion_at is not None and i == completion_at:
            levels = 1
        lines.append(_line(0 if i == 1 else 1, [_grid(i % 3)], levels=levels))
    return lines


# --------------------------------------------------------------------------- action id parsing

@pytest.mark.parametrize("raw,expected", [
    (0, 0), (5, 5), (7, 7),
    ("RESET", 0), ("reset", 0), (" ReSeT ", 0),
    ("ACTION5", 5), ("action5", 5), ("ACTION6", 6),
    ("5", 5), ("0", 0),
])
def test_normalize_action_id_accepts_both_spellings(raw, expected):
    assert P.normalize_action_id(raw) == expected


@pytest.mark.parametrize("raw", [True, False])
def test_normalize_action_id_rejects_bool(raw):
    """bool subclasses int, so an unguarded isinstance(raw, int) would silently return
    True as action 1 — the same subclass trap the predicate schema's int fields have."""
    with pytest.raises(ValueError, match="boolean action id"):
        P.normalize_action_id(raw)


@pytest.mark.parametrize("raw", [None, "", "ACTIONX", "ACTION", "wiggle", 3.5, [], {}])
def test_normalize_action_id_rejects_anything_else(raw):
    with pytest.raises(ValueError, match="unrecognized action id"):
        P.normalize_action_id(raw)


# --------------------------------------------------------------------------- load_timeline guards

def test_first_action_line_without_frames_raises(write_recording):
    """Carrying forward on line 1 would mean inventing an initial board; the module's
    docstring commits to raising rather than guessing."""
    write_recording("zz01", "g1", [_line(0, []), _line(1, [_grid(1)])])
    with pytest.raises(ValueError, match="first action line has no frames"):
        P.load_timeline("zz01", "g1")


def test_recording_with_only_a_summary_tail_line_raises(write_recording):
    """Session-summary tail lines carry no `frame` key and are skipped; a file that is
    nothing but tail lines yields no steps and must not produce an empty Timeline."""
    write_recording("zz02", "g1", [json.dumps({"data": {"won": True, "played": 1}})])
    with pytest.raises(ValueError, match="no action lines"):
        P.load_timeline("zz02", "g1")


def test_empty_frame_line_carries_previous_grid_and_records_zero(write_recording):
    """The action happened but no observation came back: keep the previous settled grid so
    the timeline stays continuous, and let n_frames tell the truth about it."""
    write_recording("zz03", "g1", [
        _line(0, [_grid(1)]),
        _line(1, [], state="GAME_OVER"),
        _line(2, [_grid(2)]),
    ])
    tl = P.load_timeline("zz03", "g1")
    assert [s.n_frames for s in tl.steps] == [1, 0, 1]
    assert tl.steps[1].settled == tl.steps[0].settled
    assert tl.steps[2].settled != tl.steps[1].settled


def test_initial_is_post_action_tracks_the_leading_reset(write_recording):
    write_recording("zz04", "with_reset", [_line(0, [_grid()]), _line(1, [_grid(1)])])
    write_recording("zz04", "no_reset", [_line(3, [_grid()]), _line(1, [_grid(1)])])
    assert P.load_timeline("zz04", "with_reset").initial_is_post_action is False
    assert P.load_timeline("zz04", "no_reset").initial_is_post_action is True


# --------------------------------------------------------------------------- checkpoint validity

@pytest.mark.parametrize("completion_at,expect_10,expect_30", [
    (None, 10, 30),     # no completion at all — both offsets stand
    (31, 10, 30),       # first completion after both
    (30, 10, None),     # AT the offset invalidates it: the rule is "at or before"
    (10, None, None),   # at offset 10 — kills 10, and 30 with it
    (5, None, None),
])
def test_zero_completion_offsets_invalidated_at_or_before_first_completion(
        write_recording, completion_at, expect_10, expect_30):
    write_recording("zz05", "g1", _plain_session(40, completion_at=completion_at))
    cps = P.checkpoints(P.load_timeline("zz05", "g1"))
    assert cps["offset:10"] == expect_10
    assert cps["offset:30"] == expect_30


def test_offsets_beyond_the_session_length_are_invalid(write_recording):
    write_recording("zz06", "g1", _plain_session(12))
    cps = P.checkpoints(P.load_timeline("zz06", "g1"))
    assert cps["offset:10"] == 10
    assert cps["offset:30"] is None


def test_offset_survives_a_session_exactly_that_long(write_recording):
    """Boundary: "after 10 recorded action lines" needs a 10th line, not an 11th."""
    write_recording("zz06b", "g1", _plain_session(10))
    assert P.checkpoints(P.load_timeline("zz06b", "g1"))["offset:10"] == 10


def test_absent_completion_anchors_are_none_not_guessed(write_recording):
    write_recording("zz07", "g1", _plain_session(40, completion_at=35))
    cps = P.checkpoints(P.load_timeline("zz07", "g1"))
    assert cps["completion:1"] == 35
    assert cps["completion:2"] is None and cps["completion:3"] is None


# --------------------------------------------------------------------------- the prefix property

def test_packet_is_a_function_of_the_prefix_only(write_recording):
    """The packet may see steps 1..checkpoint and nothing after it — the invariant the
    whole design rests on, since a packet that leaks the future measures nothing."""
    write_recording("zz08", "g1", _plain_session(40, completion_at=12))
    tl = P.load_timeline("zz08", "g1")
    p = P.extract(tl, "offset:10", 10)
    assert p.max_step() == 10
    assert len(p.steps) == 10
    assert p.completions == []          # the completion at 12 is in the future
    assert p.available_actions == tl.steps[9].available_actions

    later = P.extract(tl, "completion:1", 12)
    assert later.max_step() == 12
    assert [c.step_index for c in later.completions] == [12]


def test_completion_on_the_first_line_is_flagged_degenerate(write_recording):
    """No pre-terminal grid exists for it; the module flags rather than backfills."""
    write_recording("zz09", "g1", [_line(0, [_grid(1)], levels=1), _line(1, [_grid(2)])])
    tl = P.load_timeline("zz09", "g1")
    assert tl.completions[0].degenerate is True
    assert tl.completions[0].pre_terminal_settled is None


def test_completion_on_the_second_line_is_not_degenerate(write_recording):
    """The other side of the same boundary: index 2 is the first index at which a board
    before the completing action exists, so it must NOT be flagged degenerate."""
    write_recording("zz09b", "g1", [_line(0, [_grid(1)]), _line(1, [_grid(2)], levels=1)])
    tl = P.load_timeline("zz09b", "g1")
    assert tl.completions[0].degenerate is False
    assert tl.completions[0].pre_terminal_settled == tl.steps[0].settled


def test_pre_terminal_grid_is_the_board_before_the_completing_action(write_recording):
    """And NOT the completing step's own settled grid, which is the next level's board."""
    write_recording("zz10", "g1", [
        _line(0, [_grid(1)]), _line(1, [_grid(2)]), _line(2, [_grid(3)], levels=1)])
    tl = P.load_timeline("zz10", "g1")
    c = tl.completions[0]
    assert c.degenerate is False
    assert c.pre_terminal_settled == tl.steps[1].settled      # board at step 2
    assert c.pre_terminal_settled != tl.steps[2].settled      # not the post-terminal board


# --------------------------------------------------------------------------- reserved-game guard

def test_reserved_guard_refuses_whatever_the_draw_declares(tmp_path, monkeypatch):
    """Guard logic, independent of which games the real draw reserved."""
    draw = tmp_path / "draw.json"
    draw.write_text(json.dumps({"iteration": ["aa11"], "reserved": ["zz99"],
                                "one_shot": []}))
    monkeypatch.setattr(P, "DRAW", draw)
    with pytest.raises(SystemExit, match="RESERVED"):
        P.select_sessions("zz99")


@requires_corpus
def test_the_four_reserved_games_are_refused():
    for env in json.loads(P.DRAW.read_text())["reserved"]:
        with pytest.raises(SystemExit, match="RESERVED"):
            P.select_sessions(env)


@requires_corpus
def test_no_reserved_game_appears_in_the_packet_inventory():
    if not P.INVENTORY_OUT.exists():
        pytest.skip("inventory not generated yet")
    inventory = json.loads(P.INVENTORY_OUT.read_text())["games"]
    reserved = set(json.loads(P.DRAW.read_text())["reserved"])
    assert reserved.isdisjoint(inventory)


# --------------------------------------------------------------------------- measured quirks

@requires_corpus
def test_cn04_sessions_are_all_flagged_post_action():
    """cn04's client records no leading RESET, so its "initial settled board" is really a
    post-action board. Measured 2026-07-29: all three selected sessions open on ACTION3."""
    for sel in P.select_sessions("cn04"):
        tl = P.load_timeline("cn04", sel["guid"])
        assert tl.steps[0].action_id != 0
        assert tl.initial_is_post_action is True


@requires_corpus
def test_initial_is_post_action_is_per_session_not_per_game():
    """lf52 is the mixed case and the reason the flag lives on the Timeline rather than a
    per-game table: two of its selected sessions open on RESET, one does not."""
    flags = {P.load_timeline("lf52", s["guid"]).initial_is_post_action
             for s in P.select_sessions("lf52")}
    assert flags == {True, False}


@requires_corpus
def test_iteration_games_open_on_reset():
    """Control for the two tests above — the flag is not simply always True."""
    for sel in P.select_sessions("ls20"):
        assert P.load_timeline("ls20", sel["guid"]).initial_is_post_action is False


@requires_corpus
def test_cn04_empty_frame_steps_match_what_was_measured():
    """Measured 2026-07-29 across all 21 non-reserved games' selected sessions: empty
    `frame` lists occur in cn04 and nowhere else, always with state GAME_OVER, never on
    the first line, and always carrying the previous settled grid forward."""
    empty = []
    for sel in P.select_sessions("cn04"):
        tl = P.load_timeline("cn04", sel["guid"])
        for step in tl.steps:
            if step.n_frames == 0:
                empty.append(step)
                assert step.state == "GAME_OVER"
                assert step.index > 1
                assert step.settled == tl.steps[step.index - 2].settled
    assert empty, "cn04 no longer carries empty-frame lines — re-measure before relying on it"


@requires_corpus
def test_a_control_game_has_no_empty_frame_steps():
    for sel in P.select_sessions("ls20"):
        tl = P.load_timeline("ls20", sel["guid"])
        assert all(s.n_frames > 0 for s in tl.steps)


# --------------------------------------------------------------------------- session selection

@requires_corpus
def test_selection_is_deterministic_and_ranked():
    first = P.select_sessions("ls20")
    assert [s["guid"] for s in first] == [s["guid"] for s in P.select_sessions("ls20")]
    assert [s["rank"] for s in first] == [0, 1, 2]


def test_selection_falls_back_when_three_high_tier_sessions_do_not_exist(_synthetic_draw):
    """Dead path against today's table — all 63 selected sessions are tier 3 — so it is
    covered synthetically or not at all. `shortfall` exists to be set."""
    table = {"sessions": [
        {"env": "aa11", "guid": "g1", "levels_completed": 3, "total_actions": 100},
        {"env": "aa11", "guid": "g2", "levels_completed": 2, "total_actions": 100},
        {"env": "aa11", "guid": "g3", "levels_completed": 1, "total_actions": 100},
    ]}
    picked = P.select_sessions("aa11", table)
    assert [s["guid"] for s in picked] == ["g1", "g2", "g3"]
    assert [s["tier"] for s in picked] == [1, 1, 1]


def test_selection_orders_by_completions_then_fewer_actions_then_guid(_synthetic_draw):
    table = {"sessions": [
        {"env": "aa11", "guid": "b", "levels_completed": 5, "total_actions": 200},
        {"env": "aa11", "guid": "a", "levels_completed": 5, "total_actions": 200},
        {"env": "aa11", "guid": "c", "levels_completed": 5, "total_actions": 100},
        {"env": "aa11", "guid": "d", "levels_completed": 9, "total_actions": 999},
    ]}
    assert [s["guid"] for s in P.select_sessions("aa11", table)] == ["d", "c", "a"]


def test_exactly_three_eligible_sessions_stay_at_the_high_tier(_synthetic_draw):
    """Boundary: three eligible is enough. Sliding to a lower tier would pick the same
    three sessions but record a tier that says the data was thinner than it is."""
    table = {"sessions": [{"env": "aa11", "guid": g, "levels_completed": 3,
                           "total_actions": 100} for g in ("g1", "g2", "g3")]
             + [{"env": "aa11", "guid": "g4", "levels_completed": 2,
                 "total_actions": 100}]}
    picked = P.select_sessions("aa11", table)
    assert [s["guid"] for s in picked] == ["g1", "g2", "g3"]
    assert [s["tier"] for s in picked] == [3, 3, 3]


# --------------------------------------------------------------------------- game_inventory

def _three_completion_session() -> list[str]:
    return [_line(0, [_grid(1)]), _line(1, [_grid(2)], levels=1),
            _line(1, [_grid(3)], levels=2), _line(1, [_grid(1)], levels=3)]


def test_inventory_reports_no_shortfall_for_three_full_tier_sessions(_synthetic_draw,
                                                                    write_recording):
    for guid in ("g1", "g2", "g3"):
        write_recording("aa11", guid, _three_completion_session())
    table = {"sessions": [{"env": "aa11", "guid": g, "levels_completed": 3,
                           "total_actions": 4} for g in ("g1", "g2", "g3")]}
    inventory = P.game_inventory("aa11", table)
    assert inventory["shortfall"] is False
    assert all(s["streamed_matches_card"] for s in inventory["sessions"])


def test_inventory_flags_shortfall_when_fewer_than_three_sessions_exist(_synthetic_draw,
                                                                       write_recording):
    for guid in ("g1", "g2"):
        write_recording("aa11", guid, _three_completion_session())
    table = {"sessions": [{"env": "aa11", "guid": g, "levels_completed": 3,
                           "total_actions": 4} for g in ("g1", "g2")]}
    assert P.game_inventory("aa11", table)["shortfall"] is True


def test_inventory_reports_a_card_disagreement_rather_than_hiding_it(_synthetic_draw,
                                                                    write_recording):
    """The recording streams 3 completions; the card claims 5. That disagreement is the
    ingest trap the flag exists for, so it must reach the inventory as False."""
    write_recording("aa11", "g1", _three_completion_session())
    table = {"sessions": [{"env": "aa11", "guid": "g1", "levels_completed": 5,
                           "total_actions": 4}]}
    inventory = P.game_inventory("aa11", table)
    assert inventory["sessions"][0]["streamed_matches_card"] is False


# --------------------------------------------------------------------------- delta primitive

def test_settled_delta_reports_every_changed_cell_with_both_values():
    before = [[0, 1], [2, 3]]
    after = [[0, 9], [2, 8]]
    assert P.settled_delta(before, after) == [(0, 1, 1, 9), (1, 1, 3, 8)]
    assert P.settled_delta(before, before) == []
