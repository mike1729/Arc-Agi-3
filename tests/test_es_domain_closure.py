import sys
from enum import Enum
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

import es_sources.domain_closure as dc  # noqa: E402
from es_sources.domain_closure import (  # noqa: E402
    ALPHABETS,
    _ObjectsCache,
    candidate_verdict,
    canonical_state_key,
    close_domain,
)
from gi2_forks import encode_grid  # noqa: E402


class _Colour(Enum):
    RED = 3


class _Inner:
    def __init__(self, value):
        self.value = value
        self.back = None  # cycle


class _FakeGame:
    def __init__(self, hidden=0, action="a", count=0):
        self._action = action
        self._action_count = count
        self.hidden = hidden
        self.tag = _Colour.RED
        self.child = _Inner(7)
        self.child.back = self
        self.bag = {2, 1, 3}


def test_state_key_ignores_dead_action_field_but_not_hidden_state():
    assert canonical_state_key(_FakeGame(action="a"), "zero_flag") == canonical_state_key(
        _FakeGame(action="b"), "zero_flag"
    )
    assert canonical_state_key(_FakeGame(hidden=0), "zero_flag") != canonical_state_key(
        _FakeGame(hidden=1), "zero_flag"
    )


def test_state_key_action_count_quotient_modes():
    zero = canonical_state_key(_FakeGame(count=0), "zero_flag")
    one = canonical_state_key(_FakeGame(count=1), "zero_flag")
    two = canonical_state_key(_FakeGame(count=2), "zero_flag")
    assert zero != one
    assert one == two  # zero_flag: any positive count keys identically
    raw_one = canonical_state_key(_FakeGame(count=1), "raw")
    raw_two = canonical_state_key(_FakeGame(count=2), "raw")
    assert raw_one != raw_two


def test_state_key_is_deterministic_across_set_construction_orders():
    a = _FakeGame()
    b = _FakeGame()
    b.bag = {3, 2, 1}
    assert canonical_state_key(a, "zero_flag") == canonical_state_key(b, "zero_flag")


def test_state_key_fails_closed_on_unsupported_types():
    game = _FakeGame()
    game.weird = object()
    with pytest.raises(TypeError, match="unsupported type"):
        canonical_state_key(game, "zero_flag")


# ------------------------------------------------------------------- toy closure


class _GameState(Enum):
    NOT_FINISHED = "NOT_FINISHED"
    WIN = "WIN"


def _toy_grid(pos, level):
    grid = [[0] * 4 for _ in range(4)]
    grid[level][pos] = 3
    return grid


class _ToyResponse:
    def __init__(self, frames, levels):
        self.frame = frames
        self.levels_completed = levels


class _ToyGame:
    """One 3-position corridor per level, two levels; ACTION1 advances, wrap completes.

    Colour 3 marks the walker; reaching position 0 again after a full lap advances
    the level. Level 2 completion wins.
    """

    def __init__(self):
        self._action = None
        self._action_count = 0
        self._state = _GameState.NOT_FINISHED
        self.pos = 0
        self.level = 0
        self.levels_done = 0

    def perform_action(self, action_input, raw=True):
        action_id = int(action_input.id.value)
        self._action = action_input
        self._action_count += 1
        if self._state == _GameState.WIN and action_id != 0:
            return _ToyResponse([], self.levels_done)
        if action_id == 0:
            self.pos = 0
            self._state = _GameState.NOT_FINISHED
            return _ToyResponse([_toy_grid(self.pos, self.level)], self.levels_done)
        if action_id == 1 and self._state == _GameState.NOT_FINISHED:
            self.pos += 1
            if self.pos == 3:
                self.pos = 0
                self.levels_done += 1
                solved = _toy_grid(3 - 1, self.level)  # walker at corridor end
                if self.levels_done == 2:
                    self._state = _GameState.WIN
                    return _ToyResponse([solved], self.levels_done)
                self.level += 1
                return _ToyResponse([solved, _toy_grid(0, self.level)], self.levels_done)
        # every other id: pass turn (no board change)
        return _ToyResponse([_toy_grid(self.pos, self.level)], self.levels_done)


class _ToyDriver:
    def __init__(self, env):
        self.env = env

    def new_game(self):
        return _ToyGame()


def test_toy_domain_closes_and_equivalence_identifies_the_rule(monkeypatch):
    monkeypatch.setattr(dc, "ReplayDriver", _ToyDriver)
    monkeypatch.setattr(dc, "MAX_FRONTIER", 100)
    document = close_domain("tu93", max_edges=2000)
    closure = document["closure"]
    assert closure["achieved"] is True
    assert closure["budget_hit"] is None
    assert closure["completion_edges"] >= 2
    assert closure["levels_reached"] == 2
    # walker positions 0..2 across two levels, plus WIN
    assert closure["states"] >= 6

    cache = _ObjectsCache(document["states"], tuple(document["grid_shape"]))
    eval_objects = {}
    # the true visual rule in this toy: completion <=> the walker sits at column 2
    # (corridor end) — expressible as exactly_one colour-3 with... simplest matching
    # candidate: temporal 'changes' is wrong; use a relational-free probe:
    right_edge = {
        "op": "exists",
        "var": "x",
        "in": {"op": "colour_components", "colour": 3},
        "satisfies": {
            "op": "exists",
            "var": "y",
            "in": {"op": "colour_components", "colour": 3},
            "satisfies": {
                "op": "relation",
                "name": "col_aligned",
                "args": [
                    {"op": "var", "name": "x"},
                    {"op": "var", "name": "y"},
                ],
            },
        },
    }
    verdict = candidate_verdict(right_edge, document, cache, eval_objects)
    assert verdict["equivalent"] is False  # true on every state, not only completions

    never_true = {"op": "empty", "set": {"op": "colour_components", "colour": 3}}
    verdict = candidate_verdict(never_true, document, cache, eval_objects)
    assert verdict["equivalent"] is False
    assert verdict["edges_checked"] >= 1


def test_toy_completion_edges_carry_the_solved_frame(monkeypatch):
    monkeypatch.setattr(dc, "ReplayDriver", _ToyDriver)
    document = close_domain("tu93", max_edges=2000)
    from gi2_forks import decode_grid

    height, width = document["grid_shape"]
    completion_edges = [edge for edge in document["edges"] if edge[4] == "complete"]
    assert completion_edges
    for edge in completion_edges:
        assert edge[5] is not None
        solved = decode_grid(edge[5], width=width, height=height)
        # the walker is at the corridor end on every solved frame
        assert any(row[2] == 3 for row in solved)


def test_unclosed_entry_preserves_the_budget_failure_evidence(monkeypatch):
    monkeypatch.setattr(dc, "ReplayDriver", _ToyDriver)
    document = close_domain("tu93", max_edges=3)  # starved: cannot close
    assert document["closure"]["achieved"] is False
    entry = dc.unclosed_entry("tu93", document, "deadbeef")
    assert entry["closure_achieved"] is False
    assert entry["closure"]["budget_hit"] == "max_edges"
    assert entry["closure"]["states"] >= 1
    assert entry["budgets"]["max_edges"] == 3
    assert entry["alphabet"]["citation"]
    assert all(row["covered_route2"] is False for row in entry["cases"])


def test_alphabet_declarations_cover_the_frozen_corpus():
    assert sorted(ALPHABETS) == ["dc22", "ft09", "ls20", "m0r0", "tu93", "vc33"]
    for env, declaration in ALPHABETS.items():
        handled = set(declaration["handled_keys"])
        passes = set(declaration["pass_ids"])
        assert not handled & passes
        if declaration["handles_click"]:
            assert 6 not in handled and 6 not in passes or env in ("ls20", "tu93")
    assert dc.ACTION_COUNT_KEY_MODE["m0r0"] == "raw"
    assert all(
        mode == "zero_flag"
        for env, mode in dc.ACTION_COUNT_KEY_MODE.items()
        if env != "m0r0"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
