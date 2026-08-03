import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from es_candidates import (  # noqa: E402
    EXPRESSION_DEPTH_BOUND,
    FALSE,
    MAX_CLAUSES,
    TRACTABILITY_LIMIT,
    TRUE,
    UNKNOWN,
    ast_depth,
    calibrate_depth_bound,
    canonicalize,
    dose_observations,
    enumerate_universe,
    gold_equivalent_route1,
    load_gold_encodings,
    observation_eliminates,
    observational_match_set,
    predict_state,
    predict_transition,
    run_dose4,
    select_probe,
    serialize,
    state_observation,
    survivor_curve,
    transition_observation,
)


def _grid(rows, size=6, fill=0):
    grid = [[fill] * size for _ in range(size)]
    for (row, col), value in rows.items():
        grid[row][col] = value
    return grid


def _var(name):
    return {"op": "var", "name": name}


def _colour(value):
    return {"op": "colour_components", "colour": value}


def _pair(q1, q2, c1, c2, relation):
    return {
        "op": q1,
        "var": "x",
        "in": _colour(c1),
        "satisfies": {
            "op": q2,
            "var": "y",
            "in": _colour(c2),
            "satisfies": {"op": "relation", "name": relation, "args": [_var("x"), _var("y")]},
        },
    }


# ------------------------------------------------------------------ canonicalization


def test_alpha_equivalent_asts_share_one_canonical_form():
    with_pg = {
        "op": "exists",
        "var": "p",
        "in": _colour(3),
        "satisfies": {
            "op": "exists",
            "var": "g",
            "in": _colour(5),
            "satisfies": {"op": "relation", "name": "adjacent", "args": [_var("p"), _var("g")]},
        },
    }
    assert serialize(with_pg) == serialize(_pair("exists", "exists", 3, 5, "adjacent"))


def test_symmetric_relation_arguments_are_ordered():
    forward = _pair("exists", "exists", 3, 5, "adjacent")
    swapped = {
        "op": "exists",
        "var": "x",
        "in": _colour(3),
        "satisfies": {
            "op": "exists",
            "var": "y",
            "in": _colour(5),
            "satisfies": {"op": "relation", "name": "adjacent", "args": [_var("y"), _var("x")]},
        },
    }
    assert serialize(forward) == serialize(swapped)


def test_asymmetric_relation_argument_order_is_preserved():
    contains = _pair("exists", "exists", 3, 5, "bbox_contains")
    reversed_args = {
        "op": "exists",
        "var": "x",
        "in": _colour(3),
        "satisfies": {
            "op": "exists",
            "var": "y",
            "in": _colour(5),
            "satisfies": {
                "op": "relation",
                "name": "bbox_contains",
                "args": [_var("y"), _var("x")],
            },
        },
    }
    assert serialize(contains) != serialize(reversed_args)


def test_and_flattens_dedupes_and_sorts():
    a = {"op": "empty", "set": _colour(3)}
    b = {"op": "nonempty", "set": _colour(5)}
    nested = {"op": "and", "args": [{"op": "and", "args": [b, a]}, a]}
    flat = {"op": "and", "args": [a, b]}
    assert serialize(nested) == serialize(flat)
    single = {"op": "and", "args": [a, a]}
    assert serialize(single) == serialize(a)


# ------------------------------------------------------------ golds and calibration


def test_gidsl_golds_translate_and_calibrate_to_the_es_e3_fill():
    calibration = calibrate_depth_bound()
    assert calibration["per_gold_depth"] == {
        "dc22": 4,
        "ft09": 3,
        "ls20": 6,
        "m0r0": 2,
        "tu93": 5,
        "vc33": 6,
    }
    assert calibration["expression_depth_bound"] == EXPRESSION_DEPTH_BOUND == 6
    assert calibration["max_clauses_check"] <= MAX_CLAUSES


def test_gold_encodings_keep_source_semantic_terms():
    golds = load_gold_encodings()
    assert sorted(golds) == ["dc22", "ft09", "ls20", "m0r0", "tu93", "vc33"]
    m0r0 = golds["m0r0"]["canonical"]
    assert m0r0 == {"op": "empty", "set": {"op": "source_set", "name": "active_movers"}}


# ------------------------------------------------------------------------ enumerator
# 0 is background everywhere below (it fills the synthetic grids).


def test_enumerate_universe_size_matches_the_frozen_formula():
    # colours: 3 and 5 unique objects, 7 has two components -> T_all=3, T_rel=2
    grid = _grid({(0, 0): 3, (2, 2): 5, (4, 0): 7, (4, 2): 7})
    generated = enumerate_universe(grid)
    assert generated["terms"]["all_colours"] == [3, 5, 7]
    assert generated["terms"]["unique_object_colours"] == [3, 5]
    # 9*T_all cardinality+temporal, plus relational: sym 4*C(2,2->1 pair)=4, contains
    # ordered 2, all-exists 5 relations * 2 ordered pairs = 10 -> 27 + 16 = 43
    assert generated["universe_size"] == 9 * 3 + (4 + 2) + 10
    assert generated["tractable"] is True
    assert generated["universe_hash"] == enumerate_universe(grid)["universe_hash"]


def test_enumerate_universe_overflow_fails_tractability_not_truncation():
    rows = {}
    for index in range(8):  # eight unique singleton colours
        rows[(0, index)] = index + 1
    for index in range(4):  # four more colours with two components each
        rows[(2, 2 * index)] = 9 + index
        rows[(4, 2 * index + 1)] = 9 + index
    grid = _grid(rows, size=9)
    generated = enumerate_universe(grid)
    # 9*T_all cardinality+temporal; relational over T_rel=8 ordered pairs P=56:
    # exists-exists sym 4*P/2 + contains P, all-exists 5*P -> 8*P = 448
    expected = 9 * 12 + 8 * 8 * 7
    assert generated["universe_size"] == expected
    assert expected > TRACTABILITY_LIMIT
    assert generated["tractable"] is False
    assert generated["universe"] == []


# ------------------------------------------------------------------------- evaluator


def test_cardinality_and_background_collision():
    grid = _grid({(0, 0): 3, (2, 2): 5, (2, 3): 5})
    assert predict_state({"op": "exactly_one", "set": _colour(3)}, grid) == TRUE
    assert predict_state({"op": "empty", "set": _colour(9)}, grid) == TRUE
    assert predict_state({"op": "nonempty", "set": _colour(5)}, grid) == TRUE
    # colour 0 is this state's background: binding is ambiguous
    assert predict_state({"op": "empty", "set": _colour(0)}, grid) == UNKNOWN


def test_temporal_atoms_are_unknown_on_bare_states_and_definite_on_transitions():
    pre = _grid({(0, 0): 3, (4, 4): 5})
    post_moved = _grid({(0, 1): 3, (4, 4): 5})
    gone = _grid({(4, 4): 5})
    atom = {"op": "temporal", "event": "disappears", "set": _colour(3)}
    assert predict_state(atom, pre) == UNKNOWN
    assert predict_transition(atom, pre, gone) == TRUE
    assert predict_transition(atom, pre, post_moved) == TRUE  # no overlap -> no descendant
    changed = {"op": "temporal", "event": "changes", "set": _colour(3)}
    overlap_move = _grid({(0, 0): 3, (0, 1): 3, (4, 4): 5})
    assert predict_transition(changed, pre, overlap_move) == TRUE
    assert predict_transition(changed, pre, pre) == FALSE
    persists = {"op": "temporal", "event": "persists", "set": _colour(5)}
    assert predict_transition(persists, pre, post_moved) == TRUE


def test_split_and_merge_lineage():
    pre = _grid({(0, 0): 3, (0, 1): 3, (0, 2): 3})
    split_post = _grid({(0, 0): 3, (0, 2): 3})
    assert (
        predict_transition({"op": "temporal", "event": "splits", "set": _colour(3)}, pre, split_post)
        == TRUE
    )
    assert (
        predict_transition({"op": "temporal", "event": "merges", "set": _colour(3)}, split_post, pre)
        == TRUE
    )


def test_quantifiers_vacuous_truth_and_unknown_propagation():
    grid = _grid({(0, 0): 3})
    vacuous = _pair("all", "exists", 9, 3, "adjacent")  # colour 9 absent -> empty domain
    assert predict_state(vacuous, grid) == TRUE
    absent_exists = _pair("exists", "exists", 9, 3, "adjacent")
    assert predict_state(absent_exists, grid) == FALSE
    ambiguous = _pair("exists", "exists", 0, 3, "adjacent")  # 0 = background
    assert predict_state(ambiguous, grid) == UNKNOWN


def test_relational_atoms_on_components():
    grid = _grid({(0, 0): 3, (0, 1): 5, (5, 0): 7})
    assert predict_state(_pair("exists", "exists", 3, 5, "adjacent"), grid) == TRUE
    assert predict_state(_pair("exists", "exists", 3, 7, "adjacent"), grid) == FALSE
    assert predict_state(_pair("exists", "exists", 3, 7, "col_aligned"), grid) == TRUE
    assert predict_state(_pair("exists", "exists", 3, 7, "row_aligned"), grid) == FALSE
    big = _grid({(0, 0): 3, (0, 3): 3, (3, 0): 3, (3, 3): 3, (1, 1): 5})
    assert predict_state(_pair("exists", "exists", 3, 5, "bbox_contains"), big) == FALSE
    # each colour-3 cell is its own component; none of their bboxes contains colour 5;
    # but colour 5 at (1,1) is inside no colour-3 bbox either. Build one real container:
    contained = _grid(
        {(0, 0): 3, (0, 1): 3, (0, 2): 3, (1, 0): 3, (1, 2): 3, (2, 0): 3, (2, 1): 3, (2, 2): 3, (1, 1): 5}
    )
    assert predict_state(_pair("exists", "exists", 3, 5, "bbox_contains"), contained) == TRUE


def test_source_semantic_constructs_evaluate_unknown_at_runtime():
    grid = _grid({(0, 0): 3})
    gold_style = {
        "op": "exists",
        "var": "p",
        "in": {"op": "source_set", "name": "players"},
        "satisfies": {"op": "nonempty", "set": _colour(3)},
    }
    assert predict_state(gold_style, grid) == UNKNOWN
    ever_true = {"op": "ever", "condition": {"op": "nonempty", "set": _colour(3)}}
    ever_false = {"op": "ever", "condition": {"op": "empty", "set": _colour(3)}}
    assert predict_state(ever_true, grid) == TRUE
    assert predict_state(ever_false, grid) == UNKNOWN  # never definitely false


# ------------------------------------------------------- observations and survivors


def test_observation_elimination_rules():
    query = _grid({(0, 0): 3, (2, 2): 5})
    true_at_query = {"op": "nonempty", "set": _colour(3)}
    false_at_query = {"op": "empty", "set": _colour(3)}
    appears3 = {"op": "temporal", "event": "appears", "set": _colour(3)}
    obs = state_observation(query, "query")
    assert observation_eliminates(true_at_query, obs) is True
    assert observation_eliminates(false_at_query, obs) is False
    # temporal atoms are unknown on a bare state, so they can never die at DOSE-0
    assert observation_eliminates(appears3, obs) is False

    pre = _grid({(0, 0): 3, (2, 2): 5})
    solved = _grid({(2, 2): 5})  # colour 3 vanished at the completion
    completion = transition_observation(pre, solved, "complete", "DOSE-1")
    assert observation_eliminates({"op": "empty", "set": _colour(3)}, completion) is False
    assert observation_eliminates({"op": "nonempty", "set": _colour(3)}, completion) is True
    non_completion = transition_observation(pre, pre, "non_complete", "DOSE-3.0")
    assert observation_eliminates({"op": "nonempty", "set": _colour(3)}, non_completion) is True
    # ...but the same atom IS definite on a transition: nothing appeared here, so a
    # complete label eliminates it
    assert observation_eliminates(appears3, completion) is True
    # ever(condition false now) stays unknown, and unknown never eliminates
    still_unknown = {"op": "ever", "condition": {"op": "empty", "set": _colour(3)}}
    assert observation_eliminates(still_unknown, non_completion) is False


def test_survivor_curve_is_cumulative_and_monotone():
    query = _grid({(0, 0): 3, (2, 2): 5})
    pre = _grid({(0, 0): 3, (2, 2): 5})
    solved = _grid({(2, 2): 5})
    universe = [
        {"op": "empty", "set": _colour(3)},  # false at query, true at completion
        {"op": "nonempty", "set": _colour(3)},  # true at query -> dies at DOSE-0
        {"op": "temporal", "event": "disappears", "set": _colour(3)},  # unknown/true
        {"op": "empty", "set": _colour(5)},  # false at completion -> dies at DOSE-1
    ]
    doses = {
        "DOSE-0": [state_observation(query, "query")],
        "DOSE-1": [
            state_observation(query, "query"),
            state_observation(pre, "DOSE-1-pre"),
            transition_observation(pre, solved, "complete", "DOSE-1"),
        ],
    }
    curve = survivor_curve(universe, doses)
    assert curve["DOSE-0"] == [0, 2, 3]
    assert curve["DOSE-1"] == [0, 2]


def test_dose_observations_builds_the_nested_prefix_lists():
    query_grid = _grid({(0, 0): 3})
    pre1 = _grid({(1, 1): 3})
    solved1 = _grid({(2, 2): 5})
    pre3 = _grid({(3, 3): 3})
    grids = {
        10: {"settled": query_grid, "solved": None},
        4: {"settled": pre1, "solved": None},
        5: {"settled": None, "solved": solved1},
        7: {"settled": pre3, "solved": None},
        8: {"settled": pre3, "solved": None},
    }
    case = {
        "query": {"pre_state_row": 10},
        "doses": {
            "DOSE-1": {"pre_state_row": 4, "step": 5},
            "DOSE-2": None,
            "DOSE-3": [{"pre_state_row": 7, "step": 8}],
        },
    }
    doses = dose_observations(case, grids)
    assert [o["source"] for o in doses["DOSE-0"]] == ["query"]
    assert [o["source"] for o in doses["DOSE-1"]] == ["query", "DOSE-1-pre", "DOSE-1"]
    assert doses["DOSE-2"] == doses["DOSE-1"]
    assert [o["source"] for o in doses["DOSE-3"]] == [
        "query",
        "DOSE-1-pre",
        "DOSE-1",
        "DOSE-3.0-pre",
        "DOSE-3.0",
    ]
    assert doses["DOSE-3"][:3] == doses["DOSE-2"]


# ----------------------------------------------------------------------- E_i and O_i


def test_route1_gold_equivalence_requires_a_declared_binding():
    gold = load_gold_encodings()["m0r0"]["ast"]
    candidate = {"op": "empty", "set": _colour(10)}
    assert gold_equivalent_route1(candidate, gold, {}) is False
    binding = {"active_movers": _colour(10)}
    assert gold_equivalent_route1(candidate, gold, binding) is True
    assert gold_equivalent_route1({"op": "empty", "set": _colour(9)}, gold, binding) is False


def test_observational_match_set_requires_two_valued_agreement():
    pre = _grid({(0, 0): 3, (2, 2): 5})
    solved = _grid({(2, 2): 5})
    universe = [
        {"op": "empty", "set": _colour(3)},  # matches: false on states, true at completion
        {"op": "temporal", "event": "disappears", "set": _colour(3)},  # unknown on states
        {"op": "empty", "set": _colour(5)},  # wrong at the completion
    ]
    suite = [
        state_observation(pre, "s0"),
        transition_observation(pre, solved, "complete", "t1"),
    ]
    assert observational_match_set(universe, suite) == [0]


# ------------------------------------------------------------------------- DOSE-4


class _FakeHandle:
    """Two actions: action 1 discriminates the survivors, action 2 does not."""

    def __init__(self, settled=None):
        self.settled_grid = settled or _grid({(0, 0): 3, (2, 2): 5})
        self.post_discriminating = _grid({(2, 2): 5})  # colour 3 vanishes
        self.post_null = self.settled_grid

    def reachable_actions(self):
        return [
            {"action_id": 2, "action_data": {}},
            {"action_id": 1, "action_data": {}},
        ]

    def fork(self, action_id, action_data=None):
        post = self.post_discriminating if action_id == 1 else self.post_null
        outcome = {
            "label": "non_complete",
            "completed": False,
            "sequential_continuable": True,
            "eval_grid": post,
        }
        return outcome, _FakeHandle(settled=post)


def test_select_probe_maximin_prefers_the_discriminating_action():
    survivors = [
        {"op": "empty", "set": _colour(3)},
        {"op": "nonempty", "set": _colour(3)},
    ]
    chosen = select_probe(_FakeHandle(), survivors)
    # action 1: predictions split 1/1 -> worst-case reduction 1; action 2: 0/2 -> 0
    assert chosen["action"]["action_id"] == 1
    assert chosen["worst_case_reduction"] == 1


def test_run_dose4_updates_survivors_from_the_observed_label():
    survivors = [
        {"op": "empty", "set": _colour(3)},  # predicts complete on the chosen probe
        {"op": "nonempty", "set": _colour(3)},
    ]
    result = run_dose4(_FakeHandle(), survivors)
    assert result["probe_complete"] is True
    assert len(result["probes"]) == 2
    # probe 1 observed non_complete, so the complete-predicting candidate dies
    assert result["probes"][0]["survivors_after"] == 1
    assert result["survivors"] == [{"op": "nonempty", "set": _colour(3)}]


class _TerminalHandle(_FakeHandle):
    def fork(self, action_id, action_data=None):
        outcome, branch = super().fork(action_id, action_data)
        outcome["sequential_continuable"] = False
        return outcome, branch


def test_run_dose4_sequential_break_is_not_probe_complete():
    result = run_dose4(_TerminalHandle(), [{"op": "empty", "set": _colour(3)}])
    assert len(result["probes"]) == 1
    assert result["probe_complete"] is False


def test_tie_break_prefers_the_smaller_action_id():
    class _TieHandle(_FakeHandle):
        def fork(self, action_id, action_data=None):
            outcome = {
                "label": "non_complete",
                "completed": False,
                "sequential_continuable": True,
                "eval_grid": self.post_null,
            }
            return outcome, _FakeHandle(settled=self.post_null)

    chosen = select_probe(_TieHandle(), [{"op": "empty", "set": _colour(3)}])
    assert chosen["action"]["action_id"] == 1


def test_depth_metric_examples():
    assert ast_depth({"op": "empty", "set": _colour(3)}) == 2
    assert ast_depth(_pair("exists", "exists", 3, 5, "adjacent")) == 4
    assert ast_depth(canonicalize(_pair("all", "exists", 3, 5, "adjacent"))) == 4


def test_state_observation_never_uses_pytest_placeholder():
    # guard: the module must not import pytest or depend on test-only state
    import es_candidates

    assert not hasattr(es_candidates, "pytest")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
