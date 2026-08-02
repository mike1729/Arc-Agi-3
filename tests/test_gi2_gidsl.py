"""Tests for the finite GIDSL v1 contract and iteration gold."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))
import gi2_gidsl as G  # noqa: E402

requires_sources = pytest.mark.skipif(
    not G.GOLD_OUTPUT.exists()
    or not all((ROOT / source).exists() for source, _ in G.PROVENANCE.values()),
    reason="A0 gold or ignored environment sources absent",
)


def _row(env: str) -> dict:
    return copy.deepcopy(next(row for row in G.GOLD_ROWS if row["env"] == env))


def test_all_ten_legacy_classes_have_finite_nonempty_skeleton_contracts():
    assert len(G.CLASS_SKELETONS) == 10
    for class_name, contract in G.CLASS_SKELETONS.items():
        assert contract["skeletons"], class_name
        assert contract["max_ast_depth"] > 0
        assert contract["max_quantifier_depth"] >= 0
        assert contract["max_boolean_arity"] >= 0
        assert contract["max_relation_arity"] >= 0
        assert contract["max_sequence_arity"] >= 0


@pytest.mark.parametrize("env", [row["env"] for row in G.GOLD_ROWS])
def test_every_iteration_gold_ast_matches_its_skeleton_and_caps(env):
    row = _row(env)
    assert G.validate_hypothesis(row["class"], row["skeleton"], row["ast"]) == []
    stats = G.ast_stats(row["ast"])
    contract = G.CLASS_SKELETONS[row["class"]]
    for cap in (
        "max_ast_depth",
        "max_quantifier_depth",
        "max_boolean_arity",
        "max_relation_arity",
        "max_sequence_arity",
    ):
        assert stats[cap] <= contract[cap]


def test_unbound_variable_is_rejected():
    row = _row("dc22")
    row["ast"]["satisfies"]["satisfies"]["args"][0]["name"] = "unknown"
    assert any(
        "unbound variable" in issue
        for issue in G.validate_hypothesis(row["class"], row["skeleton"], row["ast"])
    )


@pytest.mark.parametrize(
    "class_name,skeleton,ast_node,fragment",
    [
        ("not_a_class", "empty_set", {"op": "empty", "set": {"op": "set", "name": "x"}},
         "unknown class"),
        ("all_instances_transformed", "empty_set", None, "expected an AST object"),
        ("all_instances_transformed", "empty_set", {"op": None}, "expected text"),
    ],
)
def test_validator_rejects_unknown_class_and_non_ast_nodes(
    class_name, skeleton, ast_node, fragment
):
    assert any(
        fragment in problem
        for problem in G.validate_hypothesis(class_name, skeleton, ast_node)
    )


def test_unknown_relation_and_wrong_arity_are_both_rejected():
    row = _row("dc22")
    relation = row["ast"]["satisfies"]["satisfies"]
    relation["name"] = "narratively_related"
    relation["args"].append({"op": "var", "name": "g"})
    problems = G.validate_hypothesis(row["class"], row["skeleton"], row["ast"])
    assert any("unknown relation" in problem for problem in problems)
    assert any("expected arity" in problem for problem in problems)


def test_skeleton_mismatch_is_rejected_even_when_ast_operators_are_individually_valid():
    row = _row("m0r0")
    problems = G.validate_hypothesis(
        row["class"], "all_event", row["ast"]
    )
    assert "ast: does not match skeleton all_event" in problems


def test_all_event_skeleton_remains_available_for_transformation_classes():
    ast_node = {
        "op": "all",
        "var": "x",
        "in": {"op": "set", "name": "objects"},
        "satisfies": {
            "op": "event",
            "name": "transformed",
            "args": [{"op": "var", "name": "x"}],
        },
    }
    assert G.validate_hypothesis(
        "all_instances_transformed", "all_event", ast_node
    ) == []


def test_vc33_is_the_three_way_conjunction_that_sets_the_boolean_cap():
    row = _row("vc33")
    assert G.ast_stats(row["ast"])["max_boolean_arity"] == 3
    row["ast"]["satisfies"]["satisfies"]["args"].append(
        copy.deepcopy(row["ast"]["satisfies"]["satisfies"]["args"][0])
    )
    assert any(
        "max_boolean_arity 4 exceeds cap 3" in problem
        for problem in G.validate_hypothesis(row["class"], row["skeleton"], row["ast"])
    )


def test_complex_iteration_goals_are_composed_not_hidden_in_game_specific_names():
    ls20 = _row("ls20")
    vc33 = _row("vc33")
    ls_ops = {node["op"] for node in G._walk(ls20["ast"])}
    vc_ops = {node["op"] for node in G._walk(vc33["ast"])}
    vc_relations = {
        node["name"]
        for node in G._walk(vc33["ast"])
        if node.get("op") == "relation"
    }
    assert {"ever", "exists", "and", "relation"} <= ls_ops
    assert "support_of" in vc_ops
    assert "flanks" in vc_relations
    assert "latched_with_required_avatar" not in G.EVENTS
    assert "receptacle_flanks_support" not in G.RELATIONS


def test_structural_candidate_counts_are_finite_and_reproduce_cap_table():
    spec = G._spec_document()
    measured = {
        row["env"]: row["structural_candidate_count"]
        for row in spec["iteration_caps"]
    }
    assert measured == {
        "dc22": 2,
        "ft09": 1,
        "ls20": 6,
        "m0r0": 2,
        "tu93": 2,
        "vc33": 14,
    }
    assert all(count > 0 for count in measured.values())


@requires_sources
def test_checked_in_spec_and_gold_reproduce_normative_module_and_source_sites():
    spec = json.loads(G.SPEC_OUTPUT.read_text())
    gold = json.loads(G.GOLD_OUTPUT.read_text())
    assert G.verify_artifacts(spec, gold) == []
    assert [row["env"] for row in gold["records"]] == [
        "dc22",
        "ft09",
        "ls20",
        "m0r0",
        "tu93",
        "vc33",
    ]


@requires_sources
def test_gold_verifier_rejects_a_valid_but_wrong_class():
    spec = json.loads(G.SPEC_OUTPUT.read_text())
    gold = json.loads(G.GOLD_OUTPUT.read_text())
    gold["records"][0]["class"] = "region_membership"
    gold["records"][0]["skeleton"] = "exists_exists_relation"
    problems = G.verify_artifacts(spec, gold)
    assert any("differs from the normative module" in problem for problem in problems)
    assert any("differs from the frozen draw" in problem for problem in problems)


def test_artifact_verifier_rejects_non_gold_object_and_malformed_rows(
    tmp_path, monkeypatch
):
    draw = tmp_path / "draw.json"
    draw.write_text(
        json.dumps(
            {
                "iteration": ["dc22"],
                "primary_class": {"dc22": "state_relations"},
            }
        )
    )
    monkeypatch.setattr(G, "DRAW", draw)
    spec = {}

    gold = {"records": [None]}
    monkeypatch.setattr(G, "build_artifacts", lambda: (spec, copy.deepcopy(gold)))
    assert any("expected an object" in p for p in G.verify_artifacts(spec, gold))

    row = _row("dc22")
    row["provenance"] = {"source": "../unsafe"}
    row["vocabulary"] = None
    gold = {"records": [row]}
    monkeypatch.setattr(G, "build_artifacts", lambda: (spec, copy.deepcopy(gold)))
    problems = G.verify_artifacts(spec, gold)
    assert any("vocabulary: expected an object" in p for p in problems)

    assert "gold.records: expected a list" in G.verify_artifacts(spec, None)
