#!/usr/bin/env python3
"""A3 runtime for finite GIDSL generation, evaluation, and mechanical scoring.

This module contains no game IDs, source tags, or answer-key vocabulary.  It operates on
observable set handles and object facts supplied by the A2/A3 registry.
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from typing import Any, Iterable

from gi2_gidsl import (
    BOOLEAN_OPS,
    CLASS_SKELETONS,
    COMPARATORS,
    EVENTS,
    RELATIONS,
    validate_hypothesis,
)


def _json_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def canonicalize_ast(node: Any) -> Any:
    """Apply only the four canonicalizations frozen in the GI-2 design."""
    counter = itertools.count()

    def visit(value: Any, bindings: dict[str, str]) -> Any:
        if isinstance(value, list):
            return [visit(item, bindings) for item in value]
        if not isinstance(value, dict):
            return value
        op = value.get("op")
        if op in {"all", "exists"}:
            canonical_var = f"v{next(counter)}"
            nested = dict(bindings)
            nested[str(value["var"])] = canonical_var
            return {
                "op": op,
                "var": canonical_var,
                "in": visit(value["in"], bindings),
                "satisfies": visit(value["satisfies"], nested),
            }
        if op == "var":
            return {"op": "var", "name": bindings.get(str(value["name"]), value["name"])}
        if op in BOOLEAN_OPS:
            args = []
            for child in value["args"]:
                canonical = visit(child, bindings)
                if isinstance(canonical, dict) and canonical.get("op") == op:
                    args.extend(canonical["args"])
                else:
                    args.append(canonical)
            return {"op": op, "args": sorted(args, key=_json_key)}
        if op == "relation":
            args = [visit(item, bindings) for item in value["args"]]
            if RELATIONS[value["name"]]["symmetric"]:
                args.sort(key=_json_key)
            return {"op": "relation", "name": value["name"], "args": args}
        return {
            key: visit(child, bindings) if key != "op" else child
            for key, child in value.items()
        }

    return visit(node, {})


def _resolved_sets(node: Any, extensions: dict[str, Iterable[str]]) -> Any:
    if isinstance(node, list):
        return [_resolved_sets(item, extensions) for item in node]
    if not isinstance(node, dict):
        return node
    if node.get("op") == "set":
        name = node["name"]
        if name not in extensions:
            raise KeyError(f"missing extension for set handle {name!r}")
        return {"op": "set_extension", "members": sorted(set(extensions[name]))}
    return {key: _resolved_sets(value, extensions) for key, value in node.items()}


@dataclass(frozen=True)
class GroundingScore:
    class_correct: bool
    structure_correct: bool
    grounded_predicate_correct: bool


def score_grounded(
    predicted: dict[str, Any],
    gold: dict[str, Any],
    *,
    predicted_extensions: dict[str, Iterable[str]],
    gold_extensions: dict[str, Iterable[str]],
) -> GroundingScore:
    predicted_problems = validate_hypothesis(
        predicted.get("class"), predicted.get("skeleton"), predicted.get("ast")
    )
    gold_problems = validate_hypothesis(
        gold.get("class"), gold.get("skeleton"), gold.get("ast")
    )
    if predicted_problems:
        raise ValueError("invalid predicted hypothesis: " + "; ".join(predicted_problems))
    if gold_problems:
        raise ValueError("invalid gold hypothesis: " + "; ".join(gold_problems))
    predicted_canonical = canonicalize_ast(predicted["ast"])
    gold_canonical = canonicalize_ast(gold["ast"])
    structure_correct = predicted_canonical == gold_canonical
    predicted_grounded = canonicalize_ast(
        _resolved_sets(predicted["ast"], predicted_extensions)
    )
    gold_grounded = canonicalize_ast(_resolved_sets(gold["ast"], gold_extensions))
    return GroundingScore(
        class_correct=predicted["class"] == gold["class"],
        structure_correct=structure_correct,
        grounded_predicate_correct=(
            predicted["class"] == gold["class"]
            and predicted["skeleton"] == gold["skeleton"]
            and predicted_grounded == gold_grounded
        ),
    )


def legacy_class(hypothesis: dict[str, Any]) -> str:
    class_name = hypothesis.get("class")
    if class_name not in CLASS_SKELETONS:
        raise ValueError(f"unknown GIDSL class {class_name!r}")
    return str(class_name)


def _set(name: str) -> dict[str, str]:
    return {"op": "set", "name": name}


def _var(name: str) -> dict[str, str]:
    return {"op": "var", "name": name}


def _relation(name: str, left: Any, right: Any) -> dict[str, Any]:
    return {"op": "relation", "name": name, "args": [left, right]}


def generate_finite_candidates(
    *,
    set_handles: Iterable[str],
    relations: Iterable[str] = RELATIONS,
    events: Iterable[str] = EVENTS,
    class_order: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Instantiate every frozen skeleton over supplied observable handles.

    The prior may order ``class_order`` but cannot remove classes: missing classes are
    appended in normative table order.
    """
    sets = sorted(set(set_handles))
    relation_names = [name for name in sorted(set(relations)) if name in RELATIONS]
    event_names = [name for name in sorted(set(events)) if name in EVENTS]
    ordered_classes = []
    for name in list(class_order or []) + list(CLASS_SKELETONS):
        if name in CLASS_SKELETONS and name not in ordered_classes:
            ordered_classes.append(name)
    candidates: dict[str, dict[str, Any]] = {}

    def add(class_name: str, skeleton: str, ast: dict[str, Any]) -> None:
        hypothesis = {"class": class_name, "skeleton": skeleton, "ast": ast}
        problems = validate_hypothesis(class_name, skeleton, ast)
        if problems:
            raise ValueError("; ".join(problems))
        key = _json_key(
            {
                "class": class_name,
                "skeleton": skeleton,
                "ast": canonicalize_ast(ast),
            }
        )
        candidates.setdefault(key, hypothesis)

    for class_name in ordered_classes:
        for skeleton in CLASS_SKELETONS[class_name]["skeletons"]:
            for left, right in itertools.permutations(sets, 2):
                relation_nodes = []
                for relation in relation_names:
                    relation_nodes.append(_relation(relation, _var("x"), _var("y")))
                    if relation == "flanks":
                        relation_nodes.append(
                            _relation(
                                relation,
                                _var("y"),
                                {"op": "support_of", "object": _var("x")},
                            )
                        )
                for relation_node in relation_nodes:
                    if skeleton in {"exists_exists_relation", "all_exists_relation"}:
                        outer = "exists" if skeleton.startswith("exists") else "all"
                        add(
                            class_name,
                            skeleton,
                            {
                                "op": outer,
                                "var": "x",
                                "in": _set(left),
                                "satisfies": {
                                    "op": "exists",
                                    "var": "y",
                                    "in": _set(right),
                                    "satisfies": relation_node,
                                },
                            },
                        )
                    elif skeleton == "nonempty_and_all_exists_relation":
                        add(
                            class_name,
                            skeleton,
                            {
                                "op": "and",
                                "args": [
                                    {"op": "nonempty", "set": _set(left)},
                                    {
                                        "op": "all",
                                        "var": "x",
                                        "in": _set(left),
                                        "satisfies": {
                                            "op": "exists",
                                            "var": "y",
                                            "in": _set(right),
                                            "satisfies": relation_node,
                                        },
                                    },
                                ],
                            },
                        )
                    elif skeleton == "action_and_condition":
                        add(
                            class_name,
                            skeleton,
                            {
                                "op": "action_and_condition",
                                "action": "observed_action",
                                "condition": {
                                    "op": "exists",
                                    "var": "x",
                                    "in": _set(left),
                                    "satisfies": {
                                        "op": "exists",
                                        "var": "y",
                                        "in": _set(right),
                                        "satisfies": relation_node,
                                    },
                                },
                            },
                        )
                max_boolean = CLASS_SKELETONS[class_name]["max_boolean_arity"]
                for arity in range(2, min(len(relation_nodes), max_boolean) + 1):
                    for relation_args in itertools.combinations(relation_nodes, arity):
                        conjunction = {"op": "and", "args": list(relation_args)}
                        if skeleton == "all_exists_conjunction":
                            add(
                                class_name,
                                skeleton,
                                {
                                    "op": "all",
                                    "var": "x",
                                    "in": _set(left),
                                    "satisfies": {
                                        "op": "exists",
                                        "var": "y",
                                        "in": _set(right),
                                        "satisfies": conjunction,
                                    },
                                },
                            )
                        elif skeleton == "all_ever_exists_conjunction":
                            add(
                                class_name,
                                skeleton,
                                {
                                    "op": "all",
                                    "var": "y",
                                    "in": _set(left),
                                    "satisfies": {
                                        "op": "ever",
                                        "condition": {
                                            "op": "exists",
                                            "var": "x",
                                            "in": _set(right),
                                            "satisfies": conjunction,
                                        },
                                    },
                                },
                            )
            if skeleton == "empty_set":
                for name in sets:
                    add(class_name, skeleton, {"op": "empty", "set": _set(name)})
            elif skeleton == "all_event":
                for name, event in itertools.product(sets, event_names):
                    add(
                        class_name,
                        skeleton,
                        {
                            "op": "all",
                            "var": "x",
                            "in": _set(name),
                            "satisfies": {
                                "op": "event",
                                "name": event,
                                "args": [_var("x")],
                            },
                        },
                    )
            elif skeleton == "all_local_template":
                for name in sets:
                    add(
                        class_name,
                        skeleton,
                        {
                            "op": "all",
                            "var": "x",
                            "in": _set(name),
                            "satisfies": {
                                "op": "local_template_match",
                                "clue": _var("x"),
                                "neighborhood": "eight_neighbors",
                                "zero_rule": "same_color",
                                "nonzero_rule": "different_color",
                            },
                        },
                    )
            elif skeleton == "event":
                for event in event_names:
                    add(
                        class_name,
                        skeleton,
                        {"op": "event", "name": event, "args": [_set(sets[0])]}
                        if sets
                        else {"op": "event", "name": event, "args": []},
                    )
            elif skeleton == "count_compare":
                for name, comparator in itertools.product(sets, COMPARATORS):
                    add(
                        class_name,
                        skeleton,
                        {
                            "op": "count_compare",
                            "set": _set(name),
                            "comparator": comparator,
                            "target": 0,
                        },
                    )
            elif skeleton == "accumulated_compare":
                for event, comparator in itertools.product(event_names, COMPARATORS):
                    add(
                        class_name,
                        skeleton,
                        {
                            "op": "accumulated_compare",
                            "event": event,
                            "comparator": comparator,
                            "target": 1,
                        },
                    )
            elif skeleton == "ordered_events":
                cap = CLASS_SKELETONS[class_name]["max_sequence_arity"]
                for arity in range(2, min(len(event_names), cap) + 1):
                    for sequence in itertools.permutations(event_names, arity):
                        add(
                            class_name,
                            skeleton,
                            {"op": "ordered_events", "events": list(sequence)},
                        )
    return list(candidates.values())


def _compare(left: int, comparator: str, right: int) -> bool:
    return {
        "eq": left == right,
        "ne": left != right,
        "lt": left < right,
        "le": left <= right,
        "gt": left > right,
        "ge": left >= right,
    }[comparator]


def evaluate_ast(
    node: dict[str, Any],
    *,
    sets: dict[str, list[str]],
    objects: dict[str, dict[str, Any]],
    events: dict[str, set[str]] | None = None,
    bindings: dict[str, str] | None = None,
) -> bool | list[str] | str:
    """Evaluate the observable subset of GIDSL against one registry state."""
    bindings = dict(bindings or {})
    events = events or {}
    op = node["op"]
    if op == "set":
        return list(sets.get(node["name"], []))
    if op == "var":
        return bindings[node["name"]]
    if op == "support_of":
        object_id = evaluate_ast(
            node["object"], sets=sets, objects=objects, events=events, bindings=bindings
        )
        return objects[str(object_id)].get("support")
    if op in {"all", "exists"}:
        members = evaluate_ast(
            node["in"], sets=sets, objects=objects, events=events, bindings=bindings
        )
        if not isinstance(members, list):
            raise ValueError(f"{op}.in did not evaluate to a set")
        values = []
        for member in members:
            nested = dict(bindings)
            nested[node["var"]] = member
            values.append(
                bool(
                    evaluate_ast(
                        node["satisfies"],
                        sets=sets,
                        objects=objects,
                        events=events,
                        bindings=nested,
                    )
                )
            )
        return all(values) if op == "all" else any(values)
    if op in BOOLEAN_OPS:
        values = [
            bool(
                evaluate_ast(
                    child,
                    sets=sets,
                    objects=objects,
                    events=events,
                    bindings=bindings,
                )
            )
            for child in node["args"]
        ]
        return all(values) if op == "and" else any(values)
    if op in {"empty", "nonempty"}:
        members = evaluate_ast(
            node["set"], sets=sets, objects=objects, events=events, bindings=bindings
        )
        return (len(members) == 0) == (op == "empty")
    if op == "count_compare":
        members = evaluate_ast(
            node["set"], sets=sets, objects=objects, events=events, bindings=bindings
        )
        return _compare(len(members), node["comparator"], node["target"])
    if op == "relation":
        left_id = evaluate_ast(
            node["args"][0], sets=sets, objects=objects, events=events, bindings=bindings
        )
        right_id = evaluate_ast(
            node["args"][1], sets=sets, objects=objects, events=events, bindings=bindings
        )
        left, right = objects[str(left_id)], objects[str(right_id)]
        name = node["name"]
        left_cells = {tuple(cell) for cell in left.get("cells", [])}
        right_cells = {tuple(cell) for cell in right.get("cells", [])}
        if name == "overlapping":
            return bool(left_cells & right_cells)
        if name == "adjacent":
            return any(
                (row + drow, col + dcol) in right_cells
                for row, col in left_cells
                for drow, dcol in ((-1, 0), (1, 0), (0, -1), (0, 1))
            )
        if name == "same_color":
            return set(left.get("colors", [])) == set(right.get("colors", []))
        if name == "same_lateral_coordinate":
            return left.get("centroid", [None, None])[1] == right.get(
                "centroid", [None, None]
            )[1]
        # These relations require explicit observable facts from A2 rather than inference
        # from names.
        return str(right_id) in set(left.get("relations", {}).get(name, []))
    if op == "event":
        arguments = [
            evaluate_ast(
                argument,
                sets=sets,
                objects=objects,
                events=events,
                bindings=bindings,
            )
            for argument in node["args"]
        ]
        return all(str(argument) in events.get(node["name"], set()) for argument in arguments)
    if op == "local_template_match":
        clue = evaluate_ast(
            node["clue"], sets=sets, objects=objects, events=events, bindings=bindings
        )
        return bool(objects[str(clue)].get("local_template_match", False))
    if op == "ever":
        # The registry supplies the mechanically accumulated truth of the nested condition.
        return bool(node.get("observed_ever", False))
    raise NotImplementedError(f"observable evaluator does not implement {op!r}")
