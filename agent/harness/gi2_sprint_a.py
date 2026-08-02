#!/usr/bin/env python3
"""Assemble the GI-2 Sprint A representability and grounded-set ambiguity read.

This read is deliberately staged.  It first measures whether the source-authored entities
have exact observable object/group handles and whether generic observable feature selectors
can recover their extensions.  Predicate identifiability is scored only when the A2 fork
table contains lossless verifier grids (format v2).
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any

from gi2_gidsl import CLASS_SKELETONS, RELATIONS
from gi2_traces import ROOT

GROUNDING = ROOT / "logs/gi2_grounding_annotations_iteration.json"
GOLD = ROOT / "logs/gi2_gidsl_gold_iteration.json"
FORKS = ROOT / "logs/gi2_fork_table.json"
OUTPUT = ROOT / "logs/gi2_sprint_a_results.json"
FORMAT_VERSION = 1
FEATURES = ("kind", "colors", "shapes", "pixels", "bbox_size", "role")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _feature_value(obj: dict[str, Any], feature: str) -> Any:
    if feature == "bbox_size":
        top, left, bottom, right = obj["bbox"]
        return [bottom - top + 1, right - left + 1]
    return obj[feature]


def _frozen(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def descriptor_registry(states: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    for state in states:
        for obj in state["observable_registry"]:
            for arity in (1, 2):
                for names in itertools.combinations(FEATURES, arity):
                    terms = [
                        {"feature": name, "value": _feature_value(obj, name)}
                        for name in names
                    ]
                    key = _frozen(terms)
                    definitions[key] = {"terms": terms}

    signatures: dict[str, dict[str, Any]] = {}
    for definition in definitions.values():
        extensions = []
        for state in states:
            members = sorted(
                obj["id"]
                for obj in state["observable_registry"]
                if all(
                    _feature_value(obj, term["feature"]) == term["value"]
                    for term in definition["terms"]
                )
            )
            extensions.append(members)
        if not any(extensions):
            continue
        signature = _frozen(extensions)
        candidate = {
            "id": "s" + hashlib.sha256(signature.encode()).hexdigest()[:12],
            "terms": definition["terms"],
            "extensions": extensions,
            "complexity": len(definition["terms"]),
        }
        incumbent = signatures.get(signature)
        if incumbent is None or (
            candidate["complexity"],
            _frozen(candidate["terms"]),
        ) < (
            incumbent["complexity"],
            _frozen(incumbent["terms"]),
        ):
            signatures[signature] = candidate
    return sorted(
        signatures.values(),
        key=lambda item: (item["complexity"], _frozen(item["terms"]), item["id"]),
    )


def _gold_matches(
    descriptors: list[dict[str, Any]],
    states: list[dict[str, Any]],
    set_name: str,
    indexes: list[int] | None = None,
) -> list[dict[str, Any]]:
    indexes = indexes if indexes is not None else list(range(len(states)))
    return [
        descriptor
        for descriptor in descriptors
        if all(
            descriptor["extensions"][index]
            == sorted(states[index]["gold_extensions"].get(set_name, []))
            for index in indexes
        )
    ]


def _realized_candidate_count(class_name: str, n_sets: int) -> int:
    ordered_pairs = n_sets * max(n_sets - 1, 0)
    # flanks has a direct and support_of instantiation.
    relation_nodes = len(RELATIONS) + int("flanks" in RELATIONS)
    if class_name == "state_relations":
        return ordered_pairs * (
            relation_nodes + math.comb(relation_nodes, 2)
        )
    if class_name == "quantified_object_conditions":
        return ordered_pairs * (
            relation_nodes
            + math.comb(relation_nodes, 2)
            + math.comb(relation_nodes, 3)
        )
    if class_name == "symmetry_and_template_match":
        return n_sets
    if class_name == "all_instances_transformed":
        return n_sets * (1 + 2)
    # This keeps absent iteration classes finite if the draw changes.
    return ordered_pairs * relation_nodes + n_sets


def _session_curve(
    descriptors: list[dict[str, Any]],
    states: list[dict[str, Any]],
    set_names: list[str],
) -> list[dict[str, Any]]:
    by_session: dict[str, list[int]] = {}
    for index, state in enumerate(states):
        by_session.setdefault(state["_session"], []).append(index)
    curve = []
    for completions in (1, 2, 3):
        assignments = []
        for indexes in by_session.values():
            selected = indexes[:completions]
            if len(selected) < completions:
                continue
            count = 1
            for set_name in set_names:
                count *= len(_gold_matches(descriptors, states, set_name, selected))
            assignments.append(count)
        curve.append(
            {
                "completions": completions,
                "per_session_grounding_assignments": assignments,
                "median": (
                    sorted(assignments)[len(assignments) // 2] if assignments else None
                ),
            }
        )
    return curve


def build() -> dict[str, Any]:
    grounding = json.loads(GROUNDING.read_text())
    gold_rows = {row["env"]: row for row in json.loads(GOLD.read_text())["records"]}
    forks = json.loads(FORKS.read_text())
    representable_total = sum(
        game["representable"] for game in grounding["games"]
    )
    games = []
    for game in grounding["games"]:
        env = game["env"]
        registry_sizes = [
            state["observable_registry"]
            for session in game["sessions"]
            for state in session["completion_states"]
        ]
        games.append(
            {
                "env": env,
                "entity_handle_representable": game["representable"],
                "representable": game["representable"],
                "sets": game["sets"],
                "checkpoint_registry": {
                    "states": len(registry_sizes),
                    "atomic_min": min(
                        item["atomic_handles"] for item in registry_sizes
                    ),
                    "atomic_max": max(
                        item["atomic_handles"] for item in registry_sizes
                    ),
                    "group_min": min(item["group_handles"] for item in registry_sizes),
                    "group_max": max(item["group_handles"] for item in registry_sizes),
                },
                "gold_class": gold_rows[env]["class"],
                "realized_candidate_count": None,
                "gold_rank": None,
                "grounding_ambiguity_curve": None,
                "trajectory_identifiable": None,
                "fork_oracle_identifiable": None,
            }
        )
    fork_v2 = forks.get("format_version") == 3 and all(
        "pre_grid_rle" in completion
        for game in forks.get("games", [])
        for session in game.get("sessions", [])
        for completion in session.get("completions", [])
    )
    return {
        "format_version": FORMAT_VERSION,
        "status": "sprint_a_halted_at_representability",
        "scope": "iteration",
        "inputs": {
            "grounding_sha256": _sha256(GROUNDING),
            "gold_sha256": _sha256(GOLD),
            "forks_sha256": _sha256(FORKS),
        },
        "planned_descriptor_language": {
            "features": list(FEATURES),
            "max_conjunction": 2,
            "deduplication": "extensional over annotated completion states",
            "executed": False,
            "reason": "predeclared 5/6 representability gate failed first",
        },
        "games": games,
        "gates": {
            "representability": {
                "passed": representable_total >= 5,
                "games": representable_total,
                "required": 5,
            },
            "trajectory_identifiability": {
                "passed": None,
                "reason": "not run after predeclared representability stop",
                "required": 4,
            },
            "fork_oracle_identifiability": {
                "passed": None,
                "reason": "not run after predeclared representability stop",
                "fork_verifier_grids_ready": fork_v2,
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.measure:
        document = build()
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        for game in document["games"]:
            print(
                f"{game['env']}: representable={game['representable']} "
                f"atomic={game['checkpoint_registry']['atomic_min']}-"
                f"{game['checkpoint_registry']['atomic_max']} "
                f"groups={game['checkpoint_registry']['group_min']}-"
                f"{game['checkpoint_registry']['group_max']}"
            )
        print(json.dumps(document["gates"], indent=2))
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            current = json.loads(OUTPUT.read_text())
            expected = build()
            problems = [] if current == expected else ["artifact differs from rebuild"]
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print("GI-2 Sprint A FAILED")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 Sprint A OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
