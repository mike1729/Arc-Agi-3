#!/usr/bin/env python3
"""Normative finite GIDSL v1 specification and six-game A0 iteration gold.

GIDSL is represented as strict JSON ASTs.  The *validator* is recursive because ASTs are
nested data, but the *language* is not an open recursive grammar: every hypothesis names one
of the finite class-specific skeletons below, and each skeleton has frozen depth and arity
caps.  A3 may instantiate these skeletons over extracted handles; it may not invent shapes.

The A0 candidate counts are structural instantiations over each gold row's declared authoring
vocabulary.  They establish that the frozen grammar is finite.  They are not A3's realized
handle-grounded counts, which must be measured separately.

Run:
  .venv/bin/python agent/harness/gi2_gidsl.py --build
  .venv/bin/python agent/harness/gi2_gidsl.py --verify
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DRAW = ROOT / "logs/gi1_game_draw.json"
GI1_GOLD = ROOT / "logs/gi1_predicate_gold_iteration.json"
SPEC_OUTPUT = ROOT / "logs/gi2_gidsl_v1_spec.json"
GOLD_OUTPUT = ROOT / "logs/gi2_gidsl_gold_iteration.json"

FORMAT_VERSION = 1
GIDSL_VERSION = "1.0"
NAME = re.compile(r"^[a-z][a-z0-9_]*$")
QUANTIFIERS = {"all", "exists"}
BOOLEAN_OPS = {"and", "or"}
COMPARATORS = {"eq", "ne", "lt", "le", "gt", "ge"}
RELATIONS = {
    "overlapping": {"arity": 2, "symmetric": True},
    "adjacent": {"arity": 2, "symmetric": True},
    "inside": {"arity": 2, "symmetric": False},
    "same_color": {"arity": 2, "symmetric": True},
    "same_lateral_coordinate": {"arity": 2, "symmetric": True},
    "matches_required_attributes": {"arity": 2, "symmetric": False},
    "flanks": {"arity": 2, "symmetric": False},
}
EVENTS = {
    "transformed": {"arity": 1},
    "occurred": {"arity": 1},
}
CANONICALIZATIONS = [
    "alpha_rename_bound_variables",
    "flatten_and_sort_associative_and_or",
    "order_arguments_of_symmetric_relations",
    "compare_sets_extensionally_by_member_handle",
]

# Caps cover the iteration gold while bounding all ten legacy classes.  Classes absent from
# the six-game iteration slice still receive finite skeletons; A3 may discover that a cap is
# not expressive enough, but changing it then is a declared GIDSL version change.
CLASS_SKELETONS: dict[str, dict[str, Any]] = {
    "state_relations": {
        "skeletons": ["exists_exists_relation", "all_ever_exists_conjunction"],
        "max_ast_depth": 7,
        "max_quantifier_depth": 2,
        "max_boolean_arity": 2,
        "max_relation_arity": 2,
        "max_sequence_arity": 0,
    },
    "quantified_object_conditions": {
        "skeletons": [
            "nonempty_and_all_exists_relation",
            "all_exists_conjunction",
        ],
        "max_ast_depth": 6,
        "max_quantifier_depth": 2,
        "max_boolean_arity": 3,
        "max_relation_arity": 2,
        "max_sequence_arity": 0,
    },
    "counts": {
        "skeletons": ["count_compare"],
        "max_ast_depth": 2,
        "max_quantifier_depth": 0,
        "max_boolean_arity": 1,
        "max_relation_arity": 0,
        "max_sequence_arity": 0,
    },
    "region_membership": {
        "skeletons": ["all_exists_relation", "exists_exists_relation"],
        "max_ast_depth": 5,
        "max_quantifier_depth": 2,
        "max_boolean_arity": 1,
        "max_relation_arity": 2,
        "max_sequence_arity": 0,
    },
    "symmetry_and_template_match": {
        "skeletons": ["all_local_template"],
        "max_ast_depth": 3,
        "max_quantifier_depth": 1,
        "max_boolean_arity": 1,
        "max_relation_arity": 0,
        "max_sequence_arity": 0,
    },
    "all_instances_transformed": {
        "skeletons": ["empty_set", "all_event"],
        "max_ast_depth": 3,
        "max_quantifier_depth": 1,
        "max_boolean_arity": 1,
        "max_relation_arity": 0,
        "max_sequence_arity": 0,
    },
    "event_occurrence": {
        "skeletons": ["event"],
        "max_ast_depth": 2,
        "max_quantifier_depth": 0,
        "max_boolean_arity": 1,
        "max_relation_arity": 0,
        "max_sequence_arity": 0,
    },
    "ordered_event_programs": {
        "skeletons": ["ordered_events"],
        "max_ast_depth": 2,
        "max_quantifier_depth": 0,
        "max_boolean_arity": 1,
        "max_relation_arity": 0,
        "max_sequence_arity": 4,
    },
    "action_conditioned_terminal_triggers": {
        "skeletons": ["action_and_condition"],
        "max_ast_depth": 6,
        "max_quantifier_depth": 2,
        "max_boolean_arity": 2,
        "max_relation_arity": 2,
        "max_sequence_arity": 0,
    },
    "cumulative_counters": {
        "skeletons": ["accumulated_compare"],
        "max_ast_depth": 2,
        "max_quantifier_depth": 0,
        "max_boolean_arity": 1,
        "max_relation_arity": 0,
        "max_sequence_arity": 0,
    },
}

GOLD_ROWS: list[dict[str, Any]] = [
    {
        "env": "dc22",
        "class": "state_relations",
        "skeleton": "exists_exists_relation",
        "ast": {
            "op": "exists",
            "var": "p",
            "in": {"op": "set", "name": "players"},
            "satisfies": {
                "op": "exists",
                "var": "g",
                "in": {"op": "set", "name": "goal_tiles"},
                "satisfies": {
                    "op": "relation",
                    "name": "overlapping",
                    "args": [{"op": "var", "name": "p"}, {"op": "var", "name": "g"}],
                },
            },
        },
        "vocabulary": {
            "sets": ["players", "goal_tiles"],
            "relations": ["overlapping"],
            "events": [],
            "neighborhoods": [],
            "template_rules": [],
        },
        "summary": "A player overlaps a goal tile.",
    },
    {
        "env": "ft09",
        "class": "symmetry_and_template_match",
        "skeleton": "all_local_template",
        "ast": {
            "op": "all",
            "var": "c",
            "in": {"op": "set", "name": "clues"},
            "satisfies": {
                "op": "local_template_match",
                "clue": {"op": "var", "name": "c"},
                "neighborhood": "eight_neighbors",
                "zero_rule": "same_color",
                "nonzero_rule": "different_color",
            },
        },
        "vocabulary": {
            "sets": ["clues"],
            "relations": [],
            "events": [],
            "neighborhoods": ["eight_neighbors"],
            "template_rules": ["same_color", "different_color"],
        },
        "summary": (
            "Every clue's eight neighboring cells match its 3x3 conditional color template."
        ),
    },
    {
        "env": "ls20",
        "class": "state_relations",
        "skeleton": "all_ever_exists_conjunction",
        "ast": {
            "op": "all",
            "var": "g",
            "in": {"op": "set", "name": "goal_tiles"},
            "satisfies": {
                "op": "ever",
                "condition": {
                    "op": "exists",
                    "var": "a",
                    "in": {"op": "set", "name": "avatars"},
                    "satisfies": {
                        "op": "and",
                        "args": [
                            {
                                "op": "relation",
                                "name": "overlapping",
                                "args": [
                                    {"op": "var", "name": "a"},
                                    {"op": "var", "name": "g"},
                                ],
                            },
                            {
                                "op": "relation",
                                "name": "matches_required_attributes",
                                "args": [
                                    {"op": "var", "name": "a"},
                                    {"op": "var", "name": "g"},
                                ],
                            },
                        ],
                    },
                },
            },
        },
        "vocabulary": {
            "sets": ["goal_tiles", "avatars"],
            "relations": ["overlapping", "matches_required_attributes"],
            "events": [],
            "neighborhoods": [],
            "template_rules": [],
        },
        "summary": "Every goal has been latched by an avatar with its required attributes.",
    },
    {
        "env": "m0r0",
        "class": "all_instances_transformed",
        "skeleton": "empty_set",
        "ast": {"op": "empty", "set": {"op": "set", "name": "active_movers"}},
        "vocabulary": {
            "sets": ["active_movers"],
            "relations": [],
            "events": ["transformed"],
            "neighborhoods": [],
            "template_rules": [],
        },
        "summary": "No active mover remains after pair-merging transformations.",
    },
    {
        "env": "tu93",
        "class": "quantified_object_conditions",
        "skeleton": "nonempty_and_all_exists_relation",
        "ast": {
            "op": "and",
            "args": [
                {"op": "nonempty", "set": {"op": "set", "name": "movers"}},
                {
                    "op": "all",
                    "var": "m",
                    "in": {"op": "set", "name": "movers"},
                    "satisfies": {
                        "op": "exists",
                        "var": "e",
                        "in": {"op": "set", "name": "exits"},
                        "satisfies": {
                            "op": "relation",
                            "name": "overlapping",
                            "args": [
                                {"op": "var", "name": "m"},
                                {"op": "var", "name": "e"},
                            ],
                        },
                    },
                },
            ],
        },
        "vocabulary": {
            "sets": ["movers", "exits"],
            "relations": ["overlapping"],
            "events": [],
            "neighborhoods": [],
            "template_rules": [],
        },
        "summary": "The mover set is nonempty and every mover overlaps an exit.",
    },
    {
        "env": "vc33",
        "class": "quantified_object_conditions",
        "skeleton": "all_exists_conjunction",
        "ast": {
            "op": "all",
            "var": "i",
            "in": {"op": "set", "name": "falling_items"},
            "satisfies": {
                "op": "exists",
                "var": "r",
                "in": {"op": "set", "name": "receptacles"},
                "satisfies": {
                    "op": "and",
                    "args": [
                        {
                            "op": "relation",
                            "name": "same_color",
                            "args": [
                                {"op": "var", "name": "i"},
                                {"op": "var", "name": "r"},
                            ],
                        },
                        {
                            "op": "relation",
                            "name": "same_lateral_coordinate",
                            "args": [
                                {"op": "var", "name": "i"},
                                {"op": "var", "name": "r"},
                            ],
                        },
                        {
                            "op": "relation",
                            "name": "flanks",
                            "args": [
                                {"op": "var", "name": "r"},
                                {
                                    "op": "support_of",
                                    "object": {"op": "var", "name": "i"},
                                },
                            ],
                        },
                    ],
                },
            },
        },
        "vocabulary": {
            "sets": ["falling_items", "receptacles"],
            "relations": [
                "same_color",
                "same_lateral_coordinate",
                "flanks",
            ],
            "events": [],
            "neighborhoods": [],
            "template_rules": [],
        },
        "summary": (
            "Every falling item has a same-color, laterally aligned receptacle whose wall "
            "flanks that item's support."
        ),
    },
]

PROVENANCE = {
    "dc22": ("data/environment_files/dc22/fdcac232/dc22.py", 10860),
    "ft09": ("data/environment_files/ft09/0d8bbf25/ft09.py", 2405),
    "ls20": ("data/environment_files/ls20/9607627b/ls20.py", 1957),
    "m0r0": ("data/environment_files/m0r0/492f87ba/m0r0.py", 849),
    "tu93": ("data/environment_files/tu93/0768757b/tu93.py", 1242),
    "vc33": ("data/environment_files/vc33/5430563c/vc33.py", 2104),
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _name(value: Any, where: str, problems: list[str]) -> None:
    if not isinstance(value, str) or NAME.fullmatch(value) is None:
        problems.append(f"{where}: expected a snake-case name")


def _validate_node(
    node: Any,
    *,
    where: str,
    bound: frozenset[str],
    problems: list[str],
) -> None:
    if not isinstance(node, dict):
        problems.append(f"{where}: expected an AST object")
        return
    op = node.get("op")
    if not isinstance(op, str):
        problems.append(f"{where}.op: expected text")
        return
    if op == "set":
        if set(node) != {"op", "name"}:
            problems.append(f"{where}: set node keys must be op,name")
        _name(node.get("name"), f"{where}.name", problems)
    elif op == "var":
        if set(node) != {"op", "name"}:
            problems.append(f"{where}: var node keys must be op,name")
        name = node.get("name")
        _name(name, f"{where}.name", problems)
        if isinstance(name, str) and name not in bound:
            problems.append(f"{where}.name: unbound variable {name!r}")
    elif op in QUANTIFIERS:
        if set(node) != {"op", "var", "in", "satisfies"}:
            problems.append(f"{where}: {op} keys must be op,var,in,satisfies")
        var = node.get("var")
        _name(var, f"{where}.var", problems)
        _validate_node(node.get("in"), where=f"{where}.in", bound=bound, problems=problems)
        nested = bound | ({var} if isinstance(var, str) else set())
        _validate_node(
            node.get("satisfies"),
            where=f"{where}.satisfies",
            bound=frozenset(nested),
            problems=problems,
        )
    elif op in BOOLEAN_OPS:
        if set(node) != {"op", "args"}:
            problems.append(f"{where}: {op} keys must be op,args")
        args = node.get("args")
        if not isinstance(args, list) or len(args) < 2:
            problems.append(f"{where}.args: expected at least two nodes")
        else:
            for index, arg in enumerate(args):
                _validate_node(
                    arg, where=f"{where}.args[{index}]", bound=bound, problems=problems
                )
    elif op == "relation":
        if set(node) != {"op", "name", "args"}:
            problems.append(f"{where}: relation keys must be op,name,args")
        relation = node.get("name")
        if relation not in RELATIONS:
            problems.append(f"{where}.name: unknown relation {relation!r}")
        args = node.get("args")
        expected = RELATIONS.get(relation, {}).get("arity")
        if not isinstance(args, list) or len(args) != expected:
            problems.append(f"{where}.args: expected arity {expected}")
        elif isinstance(args, list):
            for index, arg in enumerate(args):
                _validate_node(
                    arg, where=f"{where}.args[{index}]", bound=bound, problems=problems
                )
    elif op in {"empty", "nonempty"}:
        if set(node) != {"op", "set"}:
            problems.append(f"{where}: {op} keys must be op,set")
        _validate_node(node.get("set"), where=f"{where}.set", bound=bound, problems=problems)
    elif op == "support_of":
        if set(node) != {"op", "object"}:
            problems.append(f"{where}: support_of keys must be op,object")
        _validate_node(
            node.get("object"), where=f"{where}.object", bound=bound, problems=problems
        )
    elif op == "ever":
        if set(node) != {"op", "condition"}:
            problems.append(f"{where}: ever keys must be op,condition")
        _validate_node(
            node.get("condition"),
            where=f"{where}.condition",
            bound=bound,
            problems=problems,
        )
    elif op == "event":
        if set(node) != {"op", "name", "args"}:
            problems.append(f"{where}: event keys must be op,name,args")
        event = node.get("name")
        if event not in EVENTS:
            problems.append(f"{where}.name: unknown event {event!r}")
        args = node.get("args")
        expected = EVENTS.get(event, {}).get("arity")
        if not isinstance(args, list) or len(args) != expected:
            problems.append(f"{where}.args: expected arity {expected}")
        elif isinstance(args, list):
            for index, arg in enumerate(args):
                _validate_node(
                    arg, where=f"{where}.args[{index}]", bound=bound, problems=problems
                )
    elif op == "local_template_match":
        expected_keys = {"op", "clue", "neighborhood", "zero_rule", "nonzero_rule"}
        if set(node) != expected_keys:
            problems.append(f"{where}: local_template_match has unexpected keys")
        _validate_node(
            node.get("clue"), where=f"{where}.clue", bound=bound, problems=problems
        )
        if node.get("neighborhood") != "eight_neighbors":
            problems.append(f"{where}.neighborhood: expected eight_neighbors")
        if node.get("zero_rule") != "same_color":
            problems.append(f"{where}.zero_rule: expected same_color")
        if node.get("nonzero_rule") != "different_color":
            problems.append(f"{where}.nonzero_rule: expected different_color")
    elif op == "count_compare":
        if set(node) != {"op", "set", "comparator", "target"}:
            problems.append(f"{where}: count_compare has unexpected keys")
        _validate_node(node.get("set"), where=f"{where}.set", bound=bound, problems=problems)
        if node.get("comparator") not in COMPARATORS:
            problems.append(f"{where}.comparator: unknown comparator")
        target = node.get("target")
        if isinstance(target, bool) or not isinstance(target, int) or target < 0:
            problems.append(f"{where}.target: expected a nonnegative integer")
    elif op == "ordered_events":
        if set(node) != {"op", "events"}:
            problems.append(f"{where}: ordered_events keys must be op,events")
        events = node.get("events")
        if not isinstance(events, list) or len(events) < 2:
            problems.append(f"{where}.events: expected at least two event names")
        elif any(event not in EVENTS for event in events):
            problems.append(f"{where}.events: unknown event")
    elif op == "action_and_condition":
        if set(node) != {"op", "action", "condition"}:
            problems.append(f"{where}: action_and_condition has unexpected keys")
        _name(node.get("action"), f"{where}.action", problems)
        _validate_node(
            node.get("condition"),
            where=f"{where}.condition",
            bound=bound,
            problems=problems,
        )
    elif op == "accumulated_compare":
        if set(node) != {"op", "event", "comparator", "target"}:
            problems.append(f"{where}: accumulated_compare has unexpected keys")
        if node.get("event") not in EVENTS:
            problems.append(f"{where}.event: unknown event")
        if node.get("comparator") not in COMPARATORS:
            problems.append(f"{where}.comparator: unknown comparator")
        target = node.get("target")
        if isinstance(target, bool) or not isinstance(target, int) or target < 0:
            problems.append(f"{where}.target: expected a nonnegative integer")
    else:
        problems.append(f"{where}.op: unknown operator {op!r}")


def ast_stats(node: Any) -> dict[str, int]:
    stats = {
        "nodes": 0,
        "max_ast_depth": 0,
        "max_quantifier_depth": 0,
        "max_boolean_arity": 0,
        "max_relation_arity": 0,
        "max_sequence_arity": 0,
    }

    def visit(value: Any, depth: int, quantifier_depth: int) -> None:
        if isinstance(value, dict) and isinstance(value.get("op"), str):
            stats["nodes"] += 1
            stats["max_ast_depth"] = max(stats["max_ast_depth"], depth)
            op = value["op"]
            qdepth = quantifier_depth + (1 if op in QUANTIFIERS else 0)
            stats["max_quantifier_depth"] = max(stats["max_quantifier_depth"], qdepth)
            if op in BOOLEAN_OPS and isinstance(value.get("args"), list):
                stats["max_boolean_arity"] = max(
                    stats["max_boolean_arity"], len(value["args"])
                )
            if op == "relation" and isinstance(value.get("args"), list):
                stats["max_relation_arity"] = max(
                    stats["max_relation_arity"], len(value["args"])
                )
            if op == "ordered_events" and isinstance(value.get("events"), list):
                stats["max_sequence_arity"] = max(
                    stats["max_sequence_arity"], len(value["events"])
                )
            for key, child in value.items():
                if key != "op":
                    visit(child, depth + 1, qdepth)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth, quantifier_depth)

    visit(node, 1, 0)
    return stats


def _matches_skeleton(skeleton: str, ast_node: dict[str, Any]) -> bool:
    op = ast_node.get("op")
    satisfies = ast_node.get("satisfies")
    if skeleton == "exists_exists_relation":
        return (
            op == "exists"
            and isinstance(satisfies, dict)
            and satisfies.get("op") == "exists"
            and isinstance(satisfies.get("satisfies"), dict)
            and satisfies["satisfies"].get("op") == "relation"
        )
    if skeleton == "all_exists_relation":
        return (
            op == "all"
            and isinstance(satisfies, dict)
            and satisfies.get("op") == "exists"
            and isinstance(satisfies.get("satisfies"), dict)
            and satisfies["satisfies"].get("op") == "relation"
        )
    if skeleton == "all_event":
        return op == "all" and isinstance(satisfies, dict) and satisfies.get("op") == "event"
    if skeleton == "all_ever_exists_conjunction":
        condition = satisfies.get("condition") if isinstance(satisfies, dict) else None
        nested = condition.get("satisfies") if isinstance(condition, dict) else None
        return (
            op == "all"
            and isinstance(satisfies, dict)
            and satisfies.get("op") == "ever"
            and isinstance(condition, dict)
            and condition.get("op") == "exists"
            and isinstance(nested, dict)
            and nested.get("op") == "and"
        )
    if skeleton == "all_local_template":
        return (
            op == "all"
            and isinstance(satisfies, dict)
            and satisfies.get("op") == "local_template_match"
        )
    if skeleton == "empty_set":
        return op == "empty"
    if skeleton == "nonempty_and_all_exists_relation":
        args = ast_node.get("args")
        return (
            op == "and"
            and isinstance(args, list)
            and len(args) == 2
            and isinstance(args[0], dict)
            and args[0].get("op") == "nonempty"
            and isinstance(args[1], dict)
            and _matches_skeleton("all_exists_relation", args[1])
        )
    if skeleton == "all_exists_conjunction":
        return (
            op == "all"
            and isinstance(satisfies, dict)
            and satisfies.get("op") == "exists"
            and isinstance(satisfies.get("satisfies"), dict)
            and satisfies["satisfies"].get("op") == "and"
        )
    return op == {
        "count_compare": "count_compare",
        "event": "event",
        "ordered_events": "ordered_events",
        "action_and_condition": "action_and_condition",
        "accumulated_compare": "accumulated_compare",
    }.get(skeleton)


def validate_hypothesis(
    class_name: Any,
    skeleton: Any,
    ast_node: Any,
) -> list[str]:
    problems: list[str] = []
    class_spec = CLASS_SKELETONS.get(class_name)
    if class_spec is None:
        return [f"class: unknown class {class_name!r}"]
    if skeleton not in class_spec["skeletons"]:
        problems.append(f"skeleton: {skeleton!r} is not allowed for {class_name}")
    _validate_node(ast_node, where="ast", bound=frozenset(), problems=problems)
    if isinstance(ast_node, dict) and isinstance(skeleton, str):
        if not _matches_skeleton(skeleton, ast_node):
            problems.append(f"ast: does not match skeleton {skeleton}")
        stats = ast_stats(ast_node)
        for cap_name in (
            "max_ast_depth",
            "max_quantifier_depth",
            "max_boolean_arity",
            "max_relation_arity",
            "max_sequence_arity",
        ):
            if stats[cap_name] > class_spec[cap_name]:
                problems.append(
                    f"ast: {cap_name} {stats[cap_name]} exceeds cap {class_spec[cap_name]}"
                )
    return problems


def structural_candidate_count(row: dict[str, Any]) -> int:
    """Finite A0 authoring-vocabulary count, not the later handle-grounded A3 count."""
    cls = row["class"]
    vocab = row["vocabulary"]
    sets = len(vocab["sets"])
    relations = len(vocab["relations"])
    events = len(vocab["events"])
    ordered_pairs = sets * max(sets - 1, 0)
    counts = 0
    for skeleton in CLASS_SKELETONS[cls]["skeletons"]:
        if skeleton in {"exists_exists_relation", "all_exists_relation"}:
            counts += ordered_pairs * relations
        elif skeleton == "all_event":
            counts += sets * events
        elif skeleton == "all_ever_exists_conjunction":
            max_arity = CLASS_SKELETONS[cls]["max_boolean_arity"]
            conjunctions = sum(
                math.comb(relations, arity)
                for arity in range(2, min(relations, max_arity) + 1)
            )
            counts += ordered_pairs * conjunctions
        elif skeleton == "nonempty_and_all_exists_relation":
            counts += ordered_pairs * relations
        elif skeleton == "all_exists_conjunction":
            max_arity = CLASS_SKELETONS[cls]["max_boolean_arity"]
            conjunctions = sum(
                math.comb(relations, arity)
                for arity in range(2, min(relations, max_arity) + 1)
            )
            counts += ordered_pairs * conjunctions
        elif skeleton == "all_local_template":
            counts += (
                sets
                * len(vocab["neighborhoods"])
                * int("same_color" in vocab["template_rules"])
                * int("different_color" in vocab["template_rules"])
            )
        elif skeleton == "empty_set":
            counts += sets
        elif skeleton == "count_compare":
            counts += sets * len(COMPARATORS)
        elif skeleton == "event":
            counts += events
        elif skeleton == "ordered_events":
            cap = CLASS_SKELETONS[cls]["max_sequence_arity"]
            counts += sum(
                math.perm(events, arity)
                for arity in range(2, min(events, cap) + 1)
            )
        elif skeleton == "action_and_condition":
            counts += ordered_pairs * relations
        elif skeleton == "accumulated_compare":
            counts += events * len(COMPARATORS)
    return counts


def _spec_document() -> dict[str, Any]:
    iteration_caps = []
    for row in GOLD_ROWS:
        stats = ast_stats(row["ast"])
        iteration_caps.append(
            {
                "env": row["env"],
                "class": row["class"],
                "gold_skeleton": row["skeleton"],
                "gold_ast": stats,
                "structural_candidate_count": structural_candidate_count(row),
                "count_basis": "declared authoring vocabulary; realized A3 count pending",
            }
        )
    return {
        "format_version": FORMAT_VERSION,
        "status": "a0_frozen",
        "gidsl_version": GIDSL_VERSION,
        "representation": "strict JSON AST",
        "finite_grammar": True,
        "canonicalizations": CANONICALIZATIONS,
        "operators": {
            "quantifiers": sorted(QUANTIFIERS),
            "boolean": sorted(BOOLEAN_OPS),
            "comparators": sorted(COMPARATORS),
            "relations": RELATIONS,
            "events": EVENTS,
            "terminals": ["set", "var"],
            "special": [
                "empty",
                "nonempty",
                "support_of",
                "ever",
                "local_template_match",
                "count_compare",
                "ordered_events",
                "action_and_condition",
                "accumulated_compare",
            ],
        },
        "classes": CLASS_SKELETONS,
        "iteration_caps": iteration_caps,
    }


def _gold_document(spec: dict[str, Any]) -> dict[str, Any]:
    draw = json.loads(DRAW.read_text())
    gi1 = json.loads(GI1_GOLD.read_text())
    gi1_by_env = {record["env"]: record for record in gi1["records"]}
    records = []
    for row in GOLD_ROWS:
        env = row["env"]
        source_name, advance_line = PROVENANCE[env]
        source = ROOT / source_name
        gi1_record = gi1_by_env[env]
        records.append(
            {
                **row,
                "provenance": {
                    "source": source_name,
                    "source_sha256": _sha256(source),
                    "advance_line": advance_line,
                    "gi1_class": gi1_record["hypothesis"]["class"],
                    "gi1_gold_sha256": _sha256(GI1_GOLD),
                },
            }
        )
    return {
        "format_version": FORMAT_VERSION,
        "status": "a0_frozen",
        "scope": "iteration",
        "gidsl_version": GIDSL_VERSION,
        "spec": str(SPEC_OUTPUT.relative_to(ROOT)),
        "spec_fingerprint": hashlib.sha256(_canonical(spec)).hexdigest(),
        "draw": str(DRAW.relative_to(ROOT)),
        "draw_sha256": _sha256(DRAW),
        "records": records,
    }


def build_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    spec = _spec_document()
    gold = _gold_document(spec)
    return spec, gold


def verify_artifacts(spec: Any, gold: Any) -> list[str]:
    problems = []
    expected_spec, expected_gold = build_artifacts()
    if spec != expected_spec:
        problems.append("GIDSL spec differs from the normative module")
    if gold != expected_gold:
        problems.append("GIDSL gold differs from the normative module or source provenance")
    if not isinstance(gold, dict) or not isinstance(gold.get("records"), list):
        return problems + ["gold.records: expected a list"]
    draw = json.loads(DRAW.read_text())
    primary = draw.get("primary_class")
    records = gold["records"]
    envs = [record.get("env") for record in records if isinstance(record, dict)]
    if envs != draw["iteration"]:
        problems.append("gold.records: must match iteration draw order exactly")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            problems.append(f"gold.records[{index}]: expected an object")
            continue
        for issue in validate_hypothesis(
            record.get("class"), record.get("skeleton"), record.get("ast")
        ):
            problems.append(f"gold.records[{index}]: {issue}")
        env = record.get("env")
        if not isinstance(primary, dict) or record.get("class") != primary.get(env):
            problems.append(f"gold.records[{index}].class: differs from the frozen draw")
        provenance = record.get("provenance")
        if not isinstance(provenance, dict):
            problems.append(f"gold.records[{index}].provenance: expected an object")
        else:
            source_text = provenance.get("source")
            expected_prefix = f"data/environment_files/{env}/"
            if (
                not isinstance(source_text, str)
                or not source_text.startswith(expected_prefix)
                or ".." in Path(source_text).parts
            ):
                problems.append(f"gold.records[{index}].provenance.source: unsafe path")
            else:
                source = ROOT / source_text
                try:
                    text = source.read_text(encoding="utf-8")
                    tree = ast.parse(text)
                    next_lines = sorted(
                        node.lineno
                        for node in ast.walk(tree)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "next_level"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "self"
                    )
                    if next_lines != [provenance.get("advance_line")]:
                        problems.append(
                            f"gold.records[{index}].provenance.advance_line: "
                            f"expected sole next_level site {next_lines}"
                        )
                    if provenance.get("source_sha256") != _sha256(source):
                        problems.append(
                            f"gold.records[{index}].provenance.source_sha256: drift"
                        )
                except (OSError, UnicodeError, SyntaxError) as exc:
                    problems.append(
                        f"gold.records[{index}].provenance.source: cannot inspect: {exc}"
                    )
        vocab = record.get("vocabulary")
        if not isinstance(vocab, dict):
            problems.append(f"gold.records[{index}].vocabulary: expected an object")
            continue
        used_sets = {
            node["name"]
            for node in _walk(record["ast"])
            if node.get("op") == "set" and isinstance(node.get("name"), str)
        }
        if not used_sets <= set(vocab.get("sets", [])):
            problems.append(f"gold.records[{index}]: AST uses undeclared sets")
    return problems


def _walk(value: Any):
    if isinstance(value, dict):
        if "op" in value:
            yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.build:
        spec, gold = build_artifacts()
        SPEC_OUTPUT.write_text(json.dumps(spec, indent=2) + "\n")
        GOLD_OUTPUT.write_text(json.dumps(gold, indent=2) + "\n")
        print(
            "GIDSL v1 A0 artifacts built — "
            f"{len(spec['classes'])} class contracts, {len(gold['records'])} gold predicates"
        )
        for row in spec["iteration_caps"]:
            print(
                f"  {row['env']}: {row['gold_skeleton']}, "
                f"{row['gold_ast']['nodes']} nodes, "
                f"{row['structural_candidate_count']} structural candidates"
            )
        return 0
    if args.verify:
        try:
            spec = json.loads(SPEC_OUTPUT.read_text())
            gold = json.loads(GOLD_OUTPUT.read_text())
            problems = verify_artifacts(spec, gold)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print(f"GIDSL v1 A0 verification FAILED — {len(problems)} problem(s)")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GIDSL v1 A0 spec and iteration gold OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
