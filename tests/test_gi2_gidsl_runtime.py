import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from gi2_gidsl import GOLD_ROWS  # noqa: E402
from gi2_gidsl_runtime import (  # noqa: E402
    canonicalize_ast,
    evaluate_ast,
    generate_finite_candidates,
    score_grounded,
)


def test_canonicalization_alpha_boolean_and_symmetric():
    left = {
        "op": "exists",
        "var": "person",
        "in": {"op": "set", "name": "players"},
        "satisfies": {
            "op": "and",
            "args": [
                {
                    "op": "relation",
                    "name": "overlapping",
                    "args": [
                        {"op": "var", "name": "person"},
                        {"op": "var", "name": "person"},
                    ],
                },
                {"op": "and", "args": [{"op": "nonempty", "set": {"op": "set", "name": "players"}}, {"op": "nonempty", "set": {"op": "set", "name": "goals"}}]},
            ],
        },
    }
    right = {
        "op": "exists",
        "var": "x",
        "in": {"op": "set", "name": "players"},
        "satisfies": {
            "op": "and",
            "args": [
                {"op": "nonempty", "set": {"op": "set", "name": "goals"}},
                {
                    "op": "relation",
                    "name": "overlapping",
                    "args": [
                        {"op": "var", "name": "x"},
                        {"op": "var", "name": "x"},
                    ],
                },
                {"op": "nonempty", "set": {"op": "set", "name": "players"}},
            ],
        },
    }
    assert canonicalize_ast(left) == canonicalize_ast(right)


@pytest.mark.parametrize("row", GOLD_ROWS, ids=lambda row: row["env"])
def test_generator_contains_every_iteration_gold(row):
    candidates = generate_finite_candidates(
        set_handles=row["vocabulary"]["sets"],
        relations=row["vocabulary"]["relations"],
        events=row["vocabulary"]["events"],
    )
    expected = canonicalize_ast(row["ast"])
    assert any(
        candidate["class"] == row["class"]
        and candidate["skeleton"] == row["skeleton"]
        and canonicalize_ast(candidate["ast"]) == expected
        for candidate in candidates
    )


def test_prior_orders_but_does_not_filter_classes():
    candidates = generate_finite_candidates(
        set_handles=["a", "b"],
        relations=["overlapping"],
        class_order=["counts"],
    )
    classes = [candidate["class"] for candidate in candidates]
    assert classes[0] == "counts"
    assert set(classes) == set(__import__("gi2_gidsl").CLASS_SKELETONS)


def test_grounding_score_uses_extensional_set_equality():
    gold = GOLD_ROWS[0]
    predicted = {
        **gold,
        "ast": {
            "op": "exists",
            "var": "x",
            "in": {"op": "set", "name": "controlled"},
            "satisfies": {
                "op": "exists",
                "var": "y",
                "in": {"op": "set", "name": "targets"},
                "satisfies": {
                    "op": "relation",
                    "name": "overlapping",
                    "args": [
                        {"op": "var", "name": "y"},
                        {"op": "var", "name": "x"},
                    ],
                },
            },
        },
    }
    score = score_grounded(
        predicted,
        gold,
        predicted_extensions={"controlled": ["o1"], "targets": ["o2"]},
        gold_extensions={"players": ["o1"], "goal_tiles": ["o2"]},
    )
    assert score.class_correct
    assert not score.structure_correct
    assert score.grounded_predicate_correct


def test_observable_evaluator_relations_and_quantifiers():
    ast = GOLD_ROWS[0]["ast"]
    assert evaluate_ast(
        ast,
        sets={"players": ["p"], "goal_tiles": ["g"]},
        objects={
            "p": {"cells": [[1, 1]], "colors": [9], "centroid": [1, 1]},
            "g": {"cells": [[1, 1]], "colors": [11], "centroid": [1, 1]},
        },
    )
    assert not evaluate_ast(
        ast,
        sets={"players": ["p"], "goal_tiles": ["g"]},
        objects={
            "p": {"cells": [[1, 1]], "colors": [9], "centroid": [1, 1]},
            "g": {"cells": [[2, 2]], "colors": [11], "centroid": [2, 2]},
        },
    )
