#!/usr/bin/env python3
"""Diagnostic identifiability pass over the four grounded iteration games.

EXPLORATORY AND NON-FUNDING.  Commissioned by the operator on 2026-07-30 after Sprint A's
predeclared 5/6 representability gate failed.  The Sprint A gate verdict is unchanged; this
pass answers one routing question: where strict grounding holds (dc22, m0r0, tu93, vc33),
does the propose-and-verify chain identify the gold predicate from the recorded evidence?

Measured stages:

1. descriptor ambiguity curves in the planned language (six features, conjunctions of at
   most two, extensional deduplication) — over adjacency-composite registries, not the dense
   local compaction: the forensics measured that dense enumeration (3,948–5,809 groups per
   state) is not a usable vocabulary, and it is also computationally impractical here;
2. gold-descriptor selection under history-free verification features;
3. gold-candidate verification on recorded solved frames, sampled trajectory frames, and the
   replayed fork branches (negatives must be false, alternative positives must be true);
4. a structure sweep with sets fixed to the gold descriptors: every finite GIDSL candidate
   over those handles, ranked by trajectory discrimination — the programmatic analogue of
   Sprint B's oracle-objects arm.

Declared limits are recorded in the artifact.

Run:
  .venv/bin/python -u agent/harness/gi2_diag_identifiability.py --measure
  .venv/bin/python -u agent/harness/gi2_diag_identifiability.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from gi2_forks import decode_grid
from gi2_gidsl_runtime import canonicalize_ast, evaluate_ast, generate_finite_candidates
from gi2_observation import Tracker
from gi2_sprint_a import _gold_matches, _session_curve, descriptor_registry
from gi2_traces import CORPUS, DRAW, ROOT, SESSIONS, iter_trace, selected_sessions

GROUNDING = ROOT / "logs/gi2_grounding_annotations_iteration.json"
GOLD = ROOT / "logs/gi2_gidsl_gold_iteration.json"
FORKS = ROOT / "logs/gi2_fork_table.json"
SPRINT = ROOT / "logs/gi2_sprint_a_results.json"
OUTPUT = ROOT / "logs/gi2_diagnostic_identifiability.json"
FORMAT_VERSION = 1
VERIFICATION_FEATURES = ("kind", "colors", "shapes", "pixels", "bbox_size")
TRAJECTORY_CAP_PER_SESSION = 40
GRID = 64


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _feature_value(obj: dict[str, Any], feature: str) -> Any:
    if feature == "bbox_size":
        top, left, bottom, right = obj["bbox"]
        return [bottom - top + 1, right - left + 1]
    return obj[feature]


def _background(grid: list) -> int:
    return Counter(
        grid[row][col] for row in range(GRID) for col in range(GRID)
    ).most_common(1)[0][0]


def _atomic_objects(observation: Any) -> list[dict[str, Any]]:
    objects = []
    for handle in observation.handles:
        component = handle.component
        objects.append(
            {
                "id": handle.track_id,
                "kind": "atomic",
                "members": [handle.track_id],
                "colors": [component.color],
                "shapes": [component.shape],
                "pixels": component.pixels,
                "bbox": list(component.bbox),
                "centroid": list(component.centroid),
                "cells": [list(cell) for cell in sorted(component.cells)],
                "role": handle.role,
            }
        )
    return objects


def _composite_groups(
    observation: Any, background: int
) -> list[dict[str, Any]]:
    """Adjacency-connected multicolor composites over non-background components.

    This is the generative rule the Sprint A forensics measured to reproduce the failing
    ft09 clues exactly, applied here as the group vocabulary; the dense local compaction it
    replaces produced 3,948-5,809 groups per state.
    """
    handles = [
        handle
        for handle in observation.handles
        if handle.component.color != background
    ]
    parent = list(range(len(handles)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    cell_sets = [frozenset(handle.component.cells) for handle in handles]
    boxes = [handle.component.bbox for handle in handles]
    adjacent_pairs: list[tuple[int, int]] = []
    for i in range(len(handles)):
        top_i, left_i, bottom_i, right_i = boxes[i]
        for j in range(i + 1, len(handles)):
            top_j, left_j, bottom_j, right_j = boxes[j]
            if (
                top_j > bottom_i + 1
                or top_i > bottom_j + 1
                or left_j > right_i + 1
                or left_i > right_j + 1
            ):
                continue
            small, large = sorted((cell_sets[i], cell_sets[j]), key=len)
            if any(
                (row + drow, col + dcol) in large
                for row, col in small
                for drow, dcol in ((-1, 0), (1, 0), (0, -1), (0, 1))
            ):
                union(i, j)
                adjacent_pairs.append((i, j))
    clusters: dict[int, list[int]] = {}
    for index in range(len(handles)):
        clusters.setdefault(find(index), []).append(index)
    # Both granularities: adjacent pairs (the shape of every artifact gold group) and
    # maximal clusters.  Pairs are needed because transitive adjacency merges distinct
    # touching objects — e.g. a mover standing on an exit — past the gold pair.
    member_lists = [list(pair) for pair in adjacent_pairs] + [
        members for members in clusters.values() if len(members) >= 2
    ]
    groups = []
    seen_ids: set[str] = set()
    for members in member_lists:
        member_handles = [handles[index] for index in members]
        ids = sorted(handle.track_id for handle in member_handles)
        group_id = "g:" + "+".join(ids)
        if group_id in seen_ids:
            continue
        seen_ids.add(group_id)
        cells = set()
        for handle in member_handles:
            cells |= handle.component.cells
        rows = [row for row, _ in cells]
        cols = [col for _, col in cells]
        groups.append(
            {
                "id": "g:" + "+".join(ids),
                "kind": "group",
                "members": ids,
                "colors": sorted({h.component.color for h in member_handles}),
                "shapes": sorted(h.component.shape for h in member_handles),
                "pixels": len(cells),
                "bbox": [min(rows), min(cols), max(rows), max(cols)],
                "centroid": [
                    sum(rows) / len(rows),
                    sum(cols) / len(cols),
                ],
                "cells": [list(cell) for cell in sorted(cells)],
                "role": sorted({h.role for h in member_handles}),
            }
        )
    return sorted(groups, key=lambda group: group["id"])


def _registry(
    observation: Any, grid: list, *, include_groups: bool
) -> list[dict[str, Any]]:
    objects = _atomic_objects(observation)
    if include_groups:
        objects += _composite_groups(observation, _background(grid))
    return objects


def _state(registry: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "registry": registry,
        "objects": {
            obj["id"]: {
                "cells": obj["cells"],
                "colors": obj["colors"],
                "centroid": obj["centroid"],
            }
            for obj in registry
        },
    }


def _extension(terms: list[dict[str, Any]], registry: list[dict[str, Any]]) -> list[str]:
    return sorted(
        obj["id"]
        for obj in registry
        if all(_feature_value(obj, term["feature"]) == term["value"] for term in terms)
    )


def rebuild_states(env: str, *, include_groups: bool) -> dict[str, Any]:
    """Recording-driven registries: completion pre-states, solved states, trajectory sample."""
    draw = json.loads(DRAW.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())
    pre_states: list[dict[str, Any]] = []
    solved: list[dict[str, Any]] = []
    trajectory: list[dict[str, Any]] = []
    for selected in selected_sessions(env, sessions_doc, draw):
        path = CORPUS / env / f"{selected['guid']}.recording.jsonl"
        tracker = Tracker()
        previous_grid = None
        observation = None
        pending: list[tuple[Any, list]] = []
        for step in iter_trace(path):
            if step.is_completion:
                if observation is None:
                    raise ValueError(f"{env}: completion without pre-state")
                pre_states.append(
                    {
                        "_session": selected["guid"],
                        "observable_registry": _registry(
                            observation, previous_grid, include_groups=True
                        ),
                    }
                )
            for frame in step.frames:
                if frame.role not in {"settled", "solved_terminal", "next_level_initial"}:
                    continue
                if frame.role == "next_level_initial":
                    tracker.reset_level()
                    previous_grid = None
                observation = tracker.update(
                    frame.grid,
                    previous_grid=previous_grid,
                    action_id=step.action_id,
                    action_data=step.action_data,
                )
                previous_grid = frame.grid
                if frame.role == "solved_terminal":
                    solved.append(
                        _state(
                            _registry(
                                observation, frame.grid, include_groups=include_groups
                            )
                        )
                    )
                elif frame.role == "settled" and not step.is_completion:
                    pending.append((observation, frame.grid))
        stride = max(1, -(-len(pending) // TRAJECTORY_CAP_PER_SESSION))
        for index in range(0, len(pending), stride):
            pending_observation, pending_grid = pending[index]
            trajectory.append(
                _state(
                    _registry(
                        pending_observation, pending_grid, include_groups=include_groups
                    )
                )
            )
    return {"pre_states": pre_states, "solved": solved, "trajectory": trajectory}


def iter_fork_states(
    env: str, forks_doc: dict[str, Any], *, include_groups: bool
) -> Iterator[tuple[bool, dict[str, Any]]]:
    """Yield (completed, state) per replayed fork, streaming to bound memory."""
    game = next(item for item in forks_doc["games"] if item["env"] == env)
    if not game.get("fork_eligible"):
        return
    for session in game["sessions"]:
        for completion in session["completions"]:
            pre_grid = decode_grid(completion["pre_grid_rle"])
            for fork in completion["forks"]:
                if fork["terminal_grid_rle"] is None:
                    continue
                grid = decode_grid(fork["terminal_grid_rle"])
                observation = Tracker().update(
                    grid,
                    previous_grid=pre_grid,
                    action_id=fork["action_id"],
                    action_data=fork.get("action_data") or {},
                )
                yield (
                    bool(fork["completed"]),
                    _state(_registry(observation, grid, include_groups=include_groups)),
                )


def fork_counts(env: str, forks_doc: dict[str, Any]) -> dict[str, int]:
    game = next(item for item in forks_doc["games"] if item["env"] == env)
    skipped = sum(
        1
        for session in game.get("sessions", [])
        for completion in session["completions"]
        for fork in completion["forks"]
        if fork["terminal_grid_rle"] is None
    ) if game.get("fork_eligible") else 0
    return {
        "negatives": game.get("n_negative", 0),
        "alternative_positives": game.get("n_alternative_positive", 0),
        "skipped_null_grids": skipped,
    }


def _attach_gold_extensions(
    env: str, pre_states: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Align artifact gold extensions per session prefix; return annotated states only.

    vc33's annotations stop at its replay divergence, so the artifact holds a prefix of the
    recorded completions.  The assertion that every artifact gold id exists in the rebuilt
    adjacency-composite registry is the self-check that the composite vocabulary reproduces
    the gold groups.
    """
    grounding = json.loads(GROUNDING.read_text())
    game = next(item for item in grounding["games"] if item["env"] == env)
    by_session: dict[str, list[dict[str, Any]]] = {}
    for state in pre_states:
        by_session.setdefault(state["_session"], []).append(state)
    annotated = []
    for session in game["sessions"]:
        rebuilt = by_session.get(session["guid"], [])
        recorded = session["completion_states"]
        if len(recorded) > len(rebuilt):
            raise ValueError(
                f"{env}/{session['guid']}: artifact has {len(recorded)} states, "
                f"rebuilt only {len(rebuilt)}"
            )
        for rebuilt_state, artifact_state in zip(rebuilt, recorded):
            ids = {obj["id"] for obj in rebuilt_state["observable_registry"]}
            for set_name, extension in artifact_state["gold_extensions"].items():
                missing = [item for item in extension if item not in ids]
                if missing:
                    raise ValueError(
                        f"{env}: adjacency-composite registry lacks gold ids "
                        f"{missing[:3]}"
                    )
            rebuilt_state["gold_extensions"] = artifact_state["gold_extensions"]
            annotated.append(rebuilt_state)
    return annotated


def _weakened_gold(record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Drop relation conjuncts that the observable evaluator cannot ground (vc33 flanks)."""
    evaluable = {"overlapping", "adjacent", "same_color", "same_lateral_coordinate"}

    def used_relations(node: Any) -> set[str]:
        if isinstance(node, dict):
            names = set()
            if node.get("op") == "relation":
                names.add(node["name"])
            for value in node.values():
                names |= used_relations(value)
            return names
        if isinstance(node, list):
            names = set()
            for item in node:
                names |= used_relations(item)
            return names
        return set()

    def prune(node: Any) -> Any:
        if isinstance(node, dict):
            if node.get("op") == "and":
                kept = [
                    prune(child)
                    for child in node["args"]
                    if not (
                        child.get("op") == "relation"
                        and child["name"] not in evaluable
                    )
                ]
                if len(kept) == 1:
                    return kept[0]
                return {"op": "and", "args": kept}
            return {
                key: prune(value) if key != "op" else value
                for key, value in node.items()
            }
        if isinstance(node, list):
            return [prune(item) for item in node]
        return node

    if used_relations(record["ast"]) <= evaluable:
        return record["ast"], False
    return prune(record["ast"]), True


def _candidate_key(candidate: dict[str, Any]) -> str:
    return json.dumps(
        {
            "class": candidate["class"],
            "skeleton": candidate["skeleton"],
            "ast": canonicalize_ast(candidate["ast"]),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _holds(
    candidate_ast: dict[str, Any],
    state: dict[str, Any],
    set_terms: dict[str, list[dict[str, Any]]],
) -> bool:
    if "sets" not in state:
        state["sets"] = {
            name: _extension(terms, state["registry"])
            for name, terms in set_terms.items()
        }
    try:
        return bool(
            evaluate_ast(
                candidate_ast, sets=state["sets"], objects=state["objects"], events={}
            )
        )
    except (NotImplementedError, KeyError, TypeError):
        # Declared limit: skeletons outside the observable subset (ordered_events,
        # accumulated_compare, action_and_condition) and relations whose facts A2 does not
        # supply (flanks/support_of) evaluate as false and therefore never survive.
        return False


def diagnose_game(env: str, forks_doc: dict[str, Any]) -> dict[str, Any]:
    gold_record = next(
        row for row in json.loads(GOLD.read_text())["records"] if row["env"] == env
    )
    grounding = json.loads(GROUNDING.read_text())
    grounding_game = next(item for item in grounding["games"] if item["env"] == env)
    include_groups = any(
        item.startswith("g:")
        for session in grounding_game["sessions"]
        for state in session["completion_states"]
        for extension in state["gold_extensions"].values()
        for item in extension
    )
    print(f"[{env}] rebuilding states (groups_in_evaluation={include_groups})", flush=True)
    states = rebuild_states(env, include_groups=include_groups)
    annotated = _attach_gold_extensions(env, states["pre_states"])
    print(
        f"[{env}] pre={len(states['pre_states'])} annotated={len(annotated)} "
        f"solved={len(states['solved'])} trajectory={len(states['trajectory'])}",
        flush=True,
    )

    planned = descriptor_registry(annotated)
    planned_curve = _session_curve(
        planned, annotated, gold_record["vocabulary"]["sets"]
    )
    verification_descriptors = [
        descriptor
        for descriptor in planned
        if all(
            term["feature"] in VERIFICATION_FEATURES for term in descriptor["terms"]
        )
    ]
    gold_descriptors: dict[str, Any] = {}
    for set_name in gold_record["vocabulary"]["sets"]:
        matches = _gold_matches(verification_descriptors, annotated, set_name)
        gold_descriptors[set_name] = (
            {
                "terms": matches[0]["terms"],
                "complexity": matches[0]["complexity"],
                "n_matching_descriptors": len(matches),
            }
            if matches
            else None
        )
    print(
        f"[{env}] descriptors={len(planned)} gold_matched="
        f"{ {name: bool(value) for name, value in gold_descriptors.items()} }",
        flush=True,
    )

    counts = fork_counts(env, forks_doc)
    result: dict[str, Any] = {
        "env": env,
        "gold_class": gold_record["class"],
        "planned_descriptor_curve": planned_curve,
        "gold_descriptors": gold_descriptors,
        "state_counts": {
            "completion_pre_states": len(states["pre_states"]),
            "annotated_pre_states": len(annotated),
            "solved": len(states["solved"]),
            "trajectory_sampled": len(states["trajectory"]),
            "fork_negatives": counts["negatives"],
            "fork_alternative_positives": counts["alternative_positives"],
            "fork_skipped_null_grids": counts["skipped_null_grids"],
        },
    }
    if any(value is None for value in gold_descriptors.values()):
        result["gold_candidate"] = None
        result["reason"] = "gold set has no verification-feature descriptor"
        return result

    set_terms = {
        name: descriptor["terms"] for name, descriptor in gold_descriptors.items()
    }
    gold_ast, weakened = _weakened_gold(gold_record)
    candidates = generate_finite_candidates(set_handles=set_terms)
    gold_key = _candidate_key(
        {
            "class": gold_record["class"],
            "skeleton": gold_record["skeleton"],
            "ast": gold_ast,
        }
    )
    keyed = [(candidate, _candidate_key(candidate)) for candidate in candidates]
    gold_in_space = any(key == gold_key for _, key in keyed)

    alive: dict[str, dict[str, Any]] = {
        key: {"candidate": candidate, "key": key} for candidate, key in keyed
    }
    for state in states["solved"]:
        alive = {
            key: row
            for key, row in alive.items()
            if _holds(row["candidate"]["ast"], state, set_terms)
        }
    print(
        f"[{env}] candidates={len(keyed)} true_at_all_solved={len(alive)}",
        flush=True,
    )
    gold_solved = gold_key in alive
    gold_candidate_ast = gold_ast

    for row in alive.values():
        satisfied = sum(
            _holds(row["candidate"]["ast"], state, set_terms)
            for state in states["trajectory"]
        )
        row["trajectory_rate"] = (
            satisfied / len(states["trajectory"]) if states["trajectory"] else None
        )
        row["complexity"] = len(row["key"])
        row["negatives_true"] = 0
        row["alternative_positives_true"] = 0
        row["alternative_positives_total"] = 0
    gold_trajectory_rate = (
        (
            sum(
                _holds(gold_candidate_ast, state, set_terms)
                for state in states["trajectory"]
            )
            / len(states["trajectory"])
        )
        if states["trajectory"] and not gold_solved
        else (alive.get(gold_key, {}).get("trajectory_rate"))
    )

    gold_fork = {"negatives_true": 0, "negatives_total": 0, "positives_true": 0, "positives_total": 0}
    n_forks_seen = 0
    for completed, state in iter_fork_states(
        env, forks_doc, include_groups=include_groups
    ):
        n_forks_seen += 1
        if n_forks_seen % 1000 == 0:
            print(f"[{env}] fork {n_forks_seen}", flush=True)
        gold_true = _holds(gold_candidate_ast, state, set_terms)
        if completed:
            gold_fork["positives_total"] += 1
            gold_fork["positives_true"] += gold_true
        else:
            gold_fork["negatives_total"] += 1
            gold_fork["negatives_true"] += gold_true
        for row in alive.values():
            if row["key"] == gold_key:
                continue
            holds = _holds(row["candidate"]["ast"], state, set_terms)
            if completed:
                row["alternative_positives_total"] += 1
                row["alternative_positives_true"] += holds
            else:
                row["negatives_true"] += holds
    if gold_key in alive:
        alive[gold_key]["negatives_true"] = gold_fork["negatives_true"]
        alive[gold_key]["alternative_positives_true"] = gold_fork["positives_true"]
        alive[gold_key]["alternative_positives_total"] = gold_fork["positives_total"]

    def survivors(fork_arm: bool) -> list[dict[str, Any]]:
        kept = []
        for row in alive.values():
            if row["trajectory_rate"] is None or row["trajectory_rate"] >= 1.0:
                continue
            if fork_arm and (
                row["negatives_true"] > 0
                or row["alternative_positives_true"]
                < row["alternative_positives_total"]
            ):
                continue
            kept.append(row)
        return sorted(
            kept,
            key=lambda row: (row["trajectory_rate"], row["complexity"], row["key"]),
        )

    def arm_report(fork_arm: bool) -> dict[str, Any] | None:
        if fork_arm and n_forks_seen == 0:
            return None
        ranked = survivors(fork_arm)
        rank = next(
            (
                index + 1
                for index, row in enumerate(ranked)
                if row["key"] == gold_key
            ),
            None,
        )
        return {
            "survivors": len(ranked),
            "gold_survives": rank is not None,
            "gold_rank": rank,
            "top": [
                {
                    "class": row["candidate"]["class"],
                    "skeleton": row["candidate"]["skeleton"],
                    "trajectory_rate": row["trajectory_rate"],
                    "is_gold": row["key"] == gold_key,
                }
                for row in ranked[:5]
            ],
        }

    result["gold_candidate"] = {
        "weakened_for_evaluability": weakened,
        "found_in_candidate_space": gold_in_space,
        "solved_all_true": gold_solved,
        "trajectory_rate": gold_trajectory_rate,
        "fork_negatives_true": gold_fork["negatives_true"],
        "fork_negatives_total": gold_fork["negatives_total"],
        "fork_alternative_positives_true": gold_fork["positives_true"],
        "fork_alternative_positives_total": gold_fork["positives_total"],
    }
    result["candidates_evaluated"] = len(keyed)
    result["candidates_true_at_all_solved"] = len(alive)
    result["arms"] = {
        "trajectory_only": arm_report(False),
        "trajectory_plus_forks": arm_report(True),
    }
    return result


def build() -> dict[str, Any]:
    sprint = json.loads(SPRINT.read_text())
    grounded = [game["env"] for game in sprint["games"] if game["representable"]]
    forks_doc = json.loads(FORKS.read_text())
    return {
        "format_version": FORMAT_VERSION,
        "status": "exploratory_diagnostic",
        "non_funding_note": (
            "Commissioned by the operator after the Sprint A representability stop. "
            "The 5/6 gate verdict is unchanged; no one-shot game is touched; no model "
            "calls are made."
        ),
        "scope": "iteration, grounded games only",
        "inputs": {
            "grounding_sha256": _sha256(GROUNDING),
            "gold_sha256": _sha256(GOLD),
            "forks_sha256": _sha256(FORKS),
            "sprint_sha256": _sha256(SPRINT),
        },
        "declared_limits": [
            "cross-set version space unmeasured (A3 proper after remediation)",
            "role excluded from verification descriptors",
            "event/ever/ordered/accumulated/action-conditioned skeletons and "
            "flanks/support facts are outside the observable subset; they evaluate as "
            "false and cannot survive",
            "trajectory sampled at deterministic stride, cap "
            f"{TRAJECTORY_CAP_PER_SESSION}/session",
            "vc33 positive-only; gold weakened by dropping flanks",
            "group vocabulary is adjacency composites at two granularities — adjacent "
            "pairs and maximal clusters — validated against artifact gold ids at attach "
            "time; not the halted plan's dense local compaction",
            "groups constructed only where gold extensions are group-shaped "
            "(tu93, vc33)",
        ],
        "games": [diagnose_game(env, forks_doc) for env in grounded],
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
            gold = game.get("gold_candidate")
            arms = game.get("arms") or {}
            print(
                f"{game['env']}: solved_true={gold and gold['solved_all_true']} "
                f"trajectory_rank={(arms.get('trajectory_only') or {}).get('gold_rank')} "
                f"fork_rank={(arms.get('trajectory_plus_forks') or {}).get('gold_rank')}",
                flush=True,
            )
        print(f"wrote {OUTPUT.relative_to(ROOT)}", flush=True)
        return 0
    if args.verify:
        try:
            current = json.loads(OUTPUT.read_text())
            problems = [] if current == build() else ["artifact differs from rebuild"]
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print("GI-2 diagnostic identifiability FAILED")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 diagnostic identifiability OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
