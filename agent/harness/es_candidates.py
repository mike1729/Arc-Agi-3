#!/usr/bin/env python3
"""ES-IDENT candidate machinery: frozen grammar, enumerator, evaluator, equivalence.

Implements the governing note SS3.1-SS3.4 mechanics under the frozen numeric authority
``gate_manifest.yaml -> es`` (2026-08-03): ``grammar.max_clauses = 2``,
``grammar.tractability_limit_candidates = 512``, strong three-valued logic, and the
``expression_depth_bound`` calibration rule whose mechanical fill is recorded as erratum
ES-E3. Scope of this module: the hypothesis-universe side only — AST schema, gold
encodings, depth calibration, evidence-blind enumeration, three-valued evaluation,
survivor sets, the gold-blind DOSE-4 probe selector, and the E_i/O_i machinery.
Scoring, gates, and DOSE-* selection belong to ``es_screen.py`` after the ES-IDENT
freeze (SS6.2 step 1).

Two universes share one AST schema (SS3.1):

  * The SCHEMA covers every construct needed to encode the six authored golds with
    source-semantic terms permitted (``source_set`` terms; ``ever``,
    ``local_template_match``, ``support_of``; the gold relation names). This satisfies
    "the source schema itself must be capable of encoding every gold before freeze".
    Source-semantic constructs never enter a visual or deployable arm: at runtime the
    visual evaluator returns ``unknown`` for them.
  * The VISUAL universe ``U_i`` is instantiated per case from the DOSE-0 query state
    only, from four exhaustive skeleton families over colour-component terms. Its
    generation function receives nothing but one grid; universes are hashed before any
    gold or completion label is joined.

Implementation determinizations (recorded here, uniform across games, fixed before any
survivor set is computed; the ES-IDENT freeze pins this file's hash):

  * Background = modal colour of the evaluated state, ties to the smaller value
    (identical to ``es_questions.pre_state_complexity``; GI-2 R-1 convention), applied
    state-locally at every evaluation.
  * A visual term ``colour_components(v)`` denotes the 4-connected components of colour
    ``v`` on the evaluated state (``gi2_observation.componentize``). If ``v`` equals
    that state's background, the binding is ambiguous and the term evaluates
    ``unknown`` (SS3.1: missing or ambiguous state-local binding yields ``unknown``).
  * Terms enter ``U_i`` for every non-background colour present at DOSE-0. Relational
    skeletons additionally require both operand colours to denote a UNIQUE object at
    DOSE-0 (exactly one component) — SS3.1's "a term must denote a unique object or
    explicit set"; the pairwise-relation reading of a many-component colour is left out
    of the bounded universe. Worst realized case bound: 9*T_all + 8*T_rel*(T_rel-1)
    = 366 candidates at the measured maxima T_all=14, T_rel=6.
  * Visual relations: ``adjacent`` (some cell pair 4-adjacent between the two objects),
    ``bbox_overlap``, ``bbox_contains`` (bounding box of the first argument contains the
    second's), ``row_aligned``/``col_aligned`` (bounding-box interval overlap on the
    rows/columns axis; same predicate as ``es_sources.state_access.mechanical_relations``).
    Mask overlap/containment between distinct rendered colours is structurally false on
    a composited grid and is therefore not part of the visual relation vocabulary.
  * Temporal atoms evaluate on a transition via forward-only lineage inside that
    transition (SS3.1): a post-component descends from a pre-component iff same colour
    and cell-set intersection. ``appears``: some post-member with no ancestor;
    ``disappears``: some pre-member with no descendant; ``changes``: some matched pair
    with different cell sets; ``persists``: nonempty pre-membership and every pre-member
    has a descendant; ``splits``: some pre-member with >= 2 descendants; ``merges``:
    some post-member with >= 2 ancestors. On a bare state observation they evaluate
    ``unknown``.
  * A transition's evaluation state is its settled post-frame: ``solved_terminal`` for a
    completion, the settled last frame otherwise; the pre-state is the prior settled
    frame (the ``es_questions`` convention). Candidate prediction on a transition =
    evaluate the candidate with the post-frame as state and pre->post as temporal
    context; ``true`` predicts ``complete``, ``false`` predicts ``non_complete``.
  * Observations per dose. DOSE-0: the query state with label non-complete — a candidate
    definitely true there is eliminated. Each evidence transition contributes its
    labelled transition observation and its pre-state's implicit non-terminal state
    observation. ``unknown`` never eliminates and never confirms.
  * Survivor sets are computed cumulatively over the nested dose observation lists, so
    monotonicity holds by construction and is asserted, never repaired.
  * DOSE-4 (SS3.3): greedy-sequential two-probe maximin. For each reachable action the
    source simulator forks the state to obtain the settled/solved post-frame; every
    survivor predicts that transition; ``V_y(a) = {c: pred_c(a) in {y, unknown}}``. The
    selector maximizes ``|V| - max(|V_complete|, |V_non_complete|)`` with frozen
    tie-breaks (smaller action_id, then (y, x) for ACTION6, then the sha256 of the
    canonical action encoding), executes the chosen action, updates state and survivors
    from the OBSERVED engine label, and repeats once. Engine labels of unchosen forks
    never enter selection; the selector never reads which candidate is gold. If probe 1
    completes, terminates, or resets, the sequential branch ends (``probe_complete``
    false) — no root restore.
  * E_i (SS3.2) route 1: identical canonical AST after the frozen semantics-preserving
    normalizations — n-ary ``and`` flattening + canonical argument ordering, symmetric-
    relation argument ordering, de Bruijn variable renaming, and substitution of a
    source-semantic term by a visual term under a per-game adapter-declared binding
    proof (``TermBinding``). Route 2: exact extensional equality over a declared
    exhaustive finite semantic domain — the checker requires PROVEN closure of the
    enumerated domain; a bounded, non-closed suite never yields membership. No binding
    or domain is declared in this file; adapters declare them with proof records, and an
    empty declaration set makes coverage read false rather than inventing equivalence.
  * O_i (SS3.2): candidates two-valued and equal to the engine label on every point of
    the frozen bounded observational suite = all frame-bearing transitions of the case's
    OWN session (session-atomic) plus the DOSE-0 state observation. Reported separately;
    never the coverage target.

Run:
  .venv/bin/python agent/harness/es_candidates.py --calibrate      # gold depth table
  .venv/bin/python agent/harness/es_candidates.py --bring-up --jobs 6
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent/harness"))

from es_questions import modal_color  # noqa: E402
from gi2_observation import componentize  # noqa: E402
from gi2_traces import CORPUS, iter_trace  # noqa: E402

GIDSL_GOLD = ROOT / "logs/gi2_gidsl_gold_iteration.json"
INVENTORY = ROOT / "logs/es_inventory.json"
BRINGUP_OUTPUT = ROOT / "logs/es_candidates_bringup.json"

TRUE, FALSE, UNKNOWN = "true", "false", "unknown"

# --- frozen numeric mirrors of gate_manifest.yaml -> es (authority: the manifest) ----
MAX_CLAUSES = 2
TRACTABILITY_LIMIT = 512
# grammar.expression_depth_bound: rule frozen 2026-08-03; value is the ES-E3 mechanical
# fill = max over the six authored golds of the minimal schema-encoding depth under
# ``ast_depth`` below. ``--calibrate`` recomputes it; tests assert the fill.
EXPRESSION_DEPTH_BOUND = 6

VISUAL_RELATIONS = (
    "adjacent",
    "bbox_overlap",
    "bbox_contains",
    "row_aligned",
    "col_aligned",
)
SYMMETRIC_RELATIONS = frozenset(
    {"adjacent", "bbox_overlap", "row_aligned", "col_aligned"}
)
TEMPORAL_EVENTS = ("appears", "disappears", "changes", "persists", "splits", "merges")
CARDINALITY_FORMS = ("empty", "nonempty", "exactly_one")

# Source-semantic constructs: schema-only (gold encodings and the labelled ceiling arm).
GOLD_RELATIONS = (
    "overlapping",
    "same_color",
    "same_lateral_coordinate",
    "flanks",
    "matches_required_attributes",
)

GRAMMAR_SPEC: dict[str, Any] = {
    "grammar_version": 1,
    "max_clauses": MAX_CLAUSES,
    "tractability_limit_candidates": TRACTABILITY_LIMIT,
    "expression_depth_bound": EXPRESSION_DEPTH_BOUND,
    "logic": "strong_three_valued",
    "background_rule": "modal_colour_ties_to_smaller_value_state_local",
    "component_rule": "orthogonal_4_connected_same_colour",
    "visual_terms": "colour_components per DOSE-0 non-background colour; relational "
    "operands require a unique DOSE-0 object",
    "visual_relations": list(VISUAL_RELATIONS),
    "temporal_events": list(TEMPORAL_EVENTS),
    "cardinality_forms": list(CARDINALITY_FORMS),
    "relational_quantifier_shapes": ["exists_exists", "all_exists"],
    "lineage_rule": "same_colour_cell_overlap_forward_only_within_transition",
    "schema_only_ops": ["ever", "local_template_match", "source_set", "support_of"],
    "gold_relations": list(GOLD_RELATIONS),
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


GRAMMAR_SPEC_HASH = _sha256(_canonical_bytes(GRAMMAR_SPEC))


# ====================================================================================
# AST: canonicalization, serialization, depth
# ====================================================================================


def canonicalize(node: dict[str, Any]) -> dict[str, Any]:
    """Frozen semantics-preserving normal form (SS3.2 route-1 normalizations n1-n3).

    De Bruijn renaming runs FIRST so that argument ordering never depends on authored
    variable names; alpha-equivalent ASTs therefore share one canonical form."""
    return _normalize(_rename_vars(node, {}))


def _normalize(node: dict[str, Any]) -> dict[str, Any]:
    op = node["op"]
    if op == "and":
        args = []
        for arg in node["args"]:
            normalized = _normalize(arg)
            if normalized["op"] == "and":
                args.extend(normalized["args"])
            else:
                args.append(normalized)
        unique = {json.dumps(a, sort_keys=True): a for a in args}
        ordered = [unique[key] for key in sorted(unique)]
        if len(ordered) == 1:
            return ordered[0]
        return {"op": "and", "args": ordered}
    if op in {"exists", "all"}:
        return {
            "op": op,
            "var": node["var"],
            "in": _normalize(node["in"]),
            "satisfies": _normalize(node["satisfies"]),
        }
    if op in {"empty", "nonempty", "exactly_one"}:
        return {"op": op, "set": _normalize(node["set"])}
    if op == "temporal":
        return {"op": "temporal", "event": node["event"], "set": _normalize(node["set"])}
    if op == "ever":
        return {"op": "ever", "condition": _normalize(node["condition"])}
    if op == "relation":
        args = [_normalize(arg) for arg in node["args"]]
        if node["name"] in SYMMETRIC_RELATIONS or node["name"] in {
            "overlapping",
            "same_color",
            "same_lateral_coordinate",
        }:
            args = sorted(args, key=lambda a: json.dumps(a, sort_keys=True))
        return {"op": "relation", "name": node["name"], "args": args}
    if op == "local_template_match":
        return {
            "op": op,
            "clue": _normalize(node["clue"]),
            "neighborhood": node["neighborhood"],
            "zero_rule": node["zero_rule"],
            "nonzero_rule": node["nonzero_rule"],
        }
    if op == "support_of":
        return {"op": "support_of", "object": _normalize(node["object"])}
    if op in {"var", "source_set", "colour_components"}:
        return dict(node)
    raise ValueError(f"unknown AST op: {op}")


def _rename_vars(node: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    op = node["op"]
    if op in {"exists", "all"}:
        inner = dict(scope)
        inner[node["var"]] = f"v{len(scope) + 1}"
        return {
            "op": op,
            "var": inner[node["var"]],
            "in": _rename_vars(node["in"], scope),
            "satisfies": _rename_vars(node["satisfies"], inner),
        }
    if op == "var":
        name = scope.get(node["name"])
        if name is None:
            raise ValueError(f"unbound variable {node['name']}")
        return {"op": "var", "name": name}
    out: dict[str, Any] = {}
    for key, value in node.items():
        if isinstance(value, dict):
            out[key] = _rename_vars(value, scope)
        elif isinstance(value, list):
            out[key] = [
                _rename_vars(item, scope) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            out[key] = value
    return out


def serialize(node: dict[str, Any]) -> str:
    return json.dumps(canonicalize(node), sort_keys=True, separators=(",", ":"))


def ast_hash(node: dict[str, Any]) -> str:
    return _sha256(serialize(node).encode())


def ast_depth(node: dict[str, Any]) -> int:
    """Frozen depth metric: every AST dict node counts one level, leaves count one."""
    children = []
    for value in node.values():
        if isinstance(value, dict):
            children.append(ast_depth(value))
        elif isinstance(value, list):
            children.extend(ast_depth(item) for item in value if isinstance(item, dict))
    return 1 + max(children, default=0)


def clause_count(node: dict[str, Any]) -> int:
    return len(node["args"]) if node["op"] == "and" else 1


# ====================================================================================
# Gold encodings: mechanical GIDSL -> ES schema translation
# ====================================================================================


def translate_gidsl(node: dict[str, Any]) -> dict[str, Any]:
    """One-to-one translation of a GIDSL gold AST into the ES schema."""
    op = node["op"]
    if op in {"exists", "all"}:
        return {
            "op": op,
            "var": node["var"],
            "in": translate_gidsl(node["in"]),
            "satisfies": translate_gidsl(node["satisfies"]),
        }
    if op == "set":
        return {"op": "source_set", "name": node["name"]}
    if op in {"empty", "nonempty"}:
        return {"op": op, "set": translate_gidsl(node["set"])}
    if op == "and":
        return {"op": "and", "args": [translate_gidsl(arg) for arg in node["args"]]}
    if op == "ever":
        return {"op": "ever", "condition": translate_gidsl(node["condition"])}
    if op == "relation":
        return {
            "op": "relation",
            "name": node["name"],
            "args": [translate_gidsl(arg) for arg in node["args"]],
        }
    if op == "local_template_match":
        return {
            "op": "local_template_match",
            "clue": translate_gidsl(node["clue"]),
            "neighborhood": node["neighborhood"],
            "zero_rule": node["zero_rule"],
            "nonzero_rule": node["nonzero_rule"],
        }
    if op == "support_of":
        return {"op": "support_of", "object": translate_gidsl(node["object"])}
    if op == "var":
        return {"op": "var", "name": node["name"]}
    raise ValueError(f"untranslatable GIDSL op: {op}")


def load_gold_encodings() -> dict[str, dict[str, Any]]:
    doc = json.loads(GIDSL_GOLD.read_text())
    out: dict[str, dict[str, Any]] = {}
    for record in doc["records"]:
        ast = translate_gidsl(record["ast"])
        out[record["env"]] = {
            "env": record["env"],
            "ast": ast,
            "canonical": canonicalize(ast),
            "depth": ast_depth(ast),
            "clauses": clause_count(ast),
            "summary": record["summary"],
            "gidsl_source_sha256": record["provenance"]["source_sha256"],
        }
    return out


def calibrate_depth_bound() -> dict[str, Any]:
    """The ES-E3 rule: minimal uniform depth admitting every gold schema encoding."""
    golds = load_gold_encodings()
    depths = {env: gold["depth"] for env, gold in sorted(golds.items())}
    return {
        "per_gold_depth": depths,
        "expression_depth_bound": max(depths.values()),
        "max_clauses_check": max(gold["clauses"] for gold in golds.values()),
        "depth_metric": "ast_depth: one level per AST dict node, leaves count one",
    }


# ====================================================================================
# Visual universe enumeration (evidence-blind; input = one DOSE-0 grid)
# ====================================================================================


def _colour_term(colour: int) -> dict[str, Any]:
    return {"op": "colour_components", "colour": int(colour)}


def dose0_terms(grid: list) -> dict[str, Any]:
    """Term inventory of one query state: all colours and unique-object colours."""
    background = modal_color(grid)
    counts: dict[int, int] = {}
    for component in componentize(grid):
        if component.color != background:
            counts[component.color] = counts.get(component.color, 0) + 1
    return {
        "background": background,
        "all_colours": sorted(counts),
        "unique_object_colours": sorted(c for c, n in counts.items() if n == 1),
        "component_counts": {str(c): counts[c] for c in sorted(counts)},
    }


def enumerate_universe(grid: list) -> dict[str, Any]:
    """Exhaustive bounded U_i from one DOSE-0 grid; hashed before any gold join."""
    terms = dose0_terms(grid)
    all_colours = terms["all_colours"]
    unique_colours = terms["unique_object_colours"]

    candidates: list[dict[str, Any]] = []
    for form in CARDINALITY_FORMS:
        candidates.extend({"op": form, "set": _colour_term(c)} for c in all_colours)
    for event in TEMPORAL_EVENTS:
        candidates.extend(
            {"op": "temporal", "event": event, "set": _colour_term(c)}
            for c in all_colours
        )

    def _pair(quantifiers: tuple[str, str], c1: int, c2: int, relation: str) -> dict:
        return {
            "op": quantifiers[0],
            "var": "x",
            "in": _colour_term(c1),
            "satisfies": {
                "op": quantifiers[1],
                "var": "y",
                "in": _colour_term(c2),
                "satisfies": {
                    "op": "relation",
                    "name": relation,
                    "args": [{"op": "var", "name": "x"}, {"op": "var", "name": "y"}],
                },
            },
        }

    for relation in VISUAL_RELATIONS:
        symmetric = relation in SYMMETRIC_RELATIONS
        for i, c1 in enumerate(unique_colours):
            for c2 in unique_colours[i + 1 :] if symmetric else unique_colours:
                if c1 == c2:
                    continue
                candidates.append(_pair(("exists", "exists"), c1, c2, relation))
    for relation in VISUAL_RELATIONS:
        for c1 in unique_colours:
            for c2 in unique_colours:
                if c1 == c2:
                    continue
                candidates.append(_pair(("all", "exists"), c1, c2, relation))

    seen: dict[str, dict[str, Any]] = {}
    universe: list[dict[str, Any]] = []
    for candidate in candidates:
        key = serialize(candidate)
        if key in seen:
            continue
        seen[key] = candidate
        universe.append(candidate)

    for candidate in universe:
        depth = ast_depth(candidate)
        if depth > EXPRESSION_DEPTH_BOUND or clause_count(candidate) > MAX_CLAUSES:
            raise ValueError(
                f"enumerated candidate violates frozen bounds (depth {depth}): "
                f"{serialize(candidate)}"
            )

    tractable = len(universe) <= TRACTABILITY_LIMIT
    universe_hash = _sha256(
        _canonical_bytes(
            {
                "grammar_spec_hash": GRAMMAR_SPEC_HASH,
                "terms": terms,
                "candidates": [serialize(c) for c in universe],
            }
        )
    )
    return {
        "terms": terms,
        "universe": universe if tractable else [],
        "universe_size": len(universe),
        "tractable": tractable,
        "universe_hash": universe_hash,
    }


# ====================================================================================
# Three-valued evaluator
# ====================================================================================


class _Objects:
    """Per-grid component cache keyed by colour, with the state-local background."""

    def __init__(self, grid: list):
        self.background = modal_color(grid)
        self.by_colour: dict[int, list[dict[str, Any]]] = {}
        for component in componentize(grid):
            if component.color == self.background:
                continue
            cells = frozenset(component.cells)
            rows = [row for row, _ in cells]
            cols = [col for _, col in cells]
            self.by_colour.setdefault(component.color, []).append(
                {
                    "colour": component.color,
                    "cells": cells,
                    "bbox": (min(rows), min(cols), max(rows), max(cols)),
                }
            )

    def members(self, colour: int) -> list[dict[str, Any]] | None:
        """None = ambiguous binding (colour is this state's background)."""
        if colour == self.background:
            return None
        return self.by_colour.get(colour, [])


def _tri_not_true(value: str) -> bool:
    return value != TRUE


def _relation_holds(name: str, a: dict[str, Any], b: dict[str, Any]) -> bool:
    ar1, ac1, ar2, ac2 = a["bbox"]
    br1, bc1, br2, bc2 = b["bbox"]
    if name == "adjacent":
        return any(
            (row + dr, col + dc) in b["cells"]
            for row, col in a["cells"]
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))
        )
    if name == "bbox_overlap":
        return ar1 <= br2 and br1 <= ar2 and ac1 <= bc2 and bc1 <= ac2
    if name == "bbox_contains":
        return ar1 <= br1 and ac1 <= bc1 and br2 <= ar2 and bc2 <= ac2
    if name == "row_aligned":
        return ar1 <= br2 and br1 <= ar2
    if name == "col_aligned":
        return ac1 <= bc2 and bc1 <= ac2
    raise ValueError(f"not a visual relation: {name}")


def _lineage(
    pre: list[dict[str, Any]], post: list[dict[str, Any]]
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    descendants: dict[int, list[int]] = {i: [] for i in range(len(pre))}
    ancestors: dict[int, list[int]] = {j: [] for j in range(len(post))}
    for i, before in enumerate(pre):
        for j, after in enumerate(post):
            if before["cells"] & after["cells"]:
                descendants[i].append(j)
                ancestors[j].append(i)
    return descendants, ancestors


def _eval_temporal(
    event: str, colour: int, context: dict[str, Any]
) -> str:
    pre_objects: _Objects | None = context.get("pre_objects")
    post_objects: _Objects = context["objects"]
    if pre_objects is None:
        return UNKNOWN
    pre = pre_objects.members(colour)
    post = post_objects.members(colour)
    if pre is None or post is None:
        return UNKNOWN
    descendants, ancestors = _lineage(pre, post)
    if event == "appears":
        return TRUE if any(not a for a in ancestors.values()) else FALSE
    if event == "disappears":
        return TRUE if any(not d for d in descendants.values()) else FALSE
    if event == "changes":
        return (
            TRUE
            if any(
                pre[i]["cells"] != post[j]["cells"]
                for i, js in descendants.items()
                for j in js
            )
            else FALSE
        )
    if event == "persists":
        return TRUE if pre and all(descendants[i] for i in descendants) else FALSE
    if event == "splits":
        return TRUE if any(len(js) >= 2 for js in descendants.values()) else FALSE
    if event == "merges":
        return TRUE if any(len(js) >= 2 for js in ancestors.values()) else FALSE
    raise ValueError(f"unknown temporal event: {event}")


def evaluate(node: dict[str, Any], context: dict[str, Any]) -> str:
    """Strong three-valued evaluation against {objects, pre_objects?, bindings?}."""
    op = node["op"]
    objects: _Objects = context["objects"]

    if op == "and":
        values = [evaluate(arg, context) for arg in node["args"]]
        if FALSE in values:
            return FALSE
        return UNKNOWN if UNKNOWN in values else TRUE
    if op in {"empty", "nonempty", "exactly_one"}:
        members = _term_members(node["set"], context)
        if members is None:
            return UNKNOWN
        count = len(members)
        if op == "empty":
            return TRUE if count == 0 else FALSE
        if op == "nonempty":
            return TRUE if count > 0 else FALSE
        return TRUE if count == 1 else FALSE
    if op == "temporal":
        term = node["set"]
        if term["op"] != "colour_components":
            return UNKNOWN
        return _eval_temporal(node["event"], term["colour"], context)
    if op in {"exists", "all"}:
        members = _term_members(node["in"], context)
        if members is None:
            return UNKNOWN
        values = []
        for member in members:
            inner = dict(context)
            inner["scope"] = dict(context.get("scope", {}))
            inner["scope"][node["var"]] = member
            values.append(evaluate(node["satisfies"], inner))
        if op == "exists":
            if TRUE in values:
                return TRUE
            return UNKNOWN if UNKNOWN in values else FALSE
        if FALSE in values:
            return FALSE
        return UNKNOWN if UNKNOWN in values else TRUE
    if op == "relation":
        if node["name"] not in VISUAL_RELATIONS:
            return UNKNOWN  # source-semantic relation: schema/ceiling only
        resolved = []
        for arg in node["args"]:
            if arg["op"] != "var":
                return UNKNOWN
            member = context.get("scope", {}).get(arg["name"])
            if member is None:
                return UNKNOWN
            resolved.append(member)
        return TRUE if _relation_holds(node["name"], *resolved) else FALSE
    if op == "ever":
        # Sound within-transition reading: witnessed true now => true; never false.
        value = evaluate(node["condition"], context)
        return TRUE if value == TRUE else UNKNOWN
    if op in {"local_template_match", "source_set", "support_of", "var"}:
        return UNKNOWN
    _ = objects
    raise ValueError(f"unknown AST op: {op}")


def _term_members(
    term: dict[str, Any], context: dict[str, Any]
) -> list[dict[str, Any]] | None:
    if term["op"] == "colour_components":
        return context["objects"].members(term["colour"])
    if term["op"] == "source_set":
        bindings = context.get("bindings") or {}
        bound = bindings.get(term["name"])
        if bound is None:
            return None
        return _term_members(bound, context)
    return None


def predict_state(candidate: dict[str, Any], grid: list) -> str:
    return evaluate(candidate, {"objects": _Objects(grid)})


def predict_transition(candidate: dict[str, Any], pre_grid: list, post_grid: list) -> str:
    return evaluate(
        candidate, {"objects": _Objects(post_grid), "pre_objects": _Objects(pre_grid)}
    )


# ====================================================================================
# Observations and survivor sets
# ====================================================================================


def state_observation(grid: list, source: str) -> dict[str, Any]:
    return {"kind": "state", "grid": grid, "label": "non_complete", "source": source}


def transition_observation(
    pre_grid: list, post_grid: list, label: str, source: str
) -> dict[str, Any]:
    return {
        "kind": "transition",
        "pre_grid": pre_grid,
        "post_grid": post_grid,
        "label": label,
        "source": source,
    }


def observation_eliminates(candidate: dict[str, Any], observation: dict[str, Any]) -> bool:
    """Only a definite contradiction eliminates (SS3.4)."""
    if observation["kind"] == "state":
        return not _tri_not_true(predict_state(candidate, observation["grid"]))
    value = predict_transition(
        candidate, observation["pre_grid"], observation["post_grid"]
    )
    if observation["label"] == "complete":
        return value == FALSE
    if observation["label"] == "non_complete":
        return value == TRUE
    raise ValueError(f"unlabelled observation: {observation['label']}")


def dose_observations(case: dict[str, Any], grids: dict[int, dict[str, list]]) -> dict[str, list]:
    """Nested per-dose observation lists for one inventory case row."""

    def _settled(step: int) -> list:
        return grids[step]["settled"]

    def _solved(step: int) -> list:
        return grids[step]["solved"]

    query_grid = _settled(case["query"]["pre_state_row"])
    doses: dict[str, list] = {"DOSE-0": [state_observation(query_grid, "query")]}
    added: list[dict[str, Any]] = []
    for key, label in (("DOSE-1", "complete"), ("DOSE-2", "complete")):
        entry = case["doses"][key]
        additions = []
        if entry is not None:
            pre = _settled(entry["pre_state_row"])
            additions = [
                state_observation(pre, f"{key}-pre"),
                transition_observation(pre, _solved(entry["step"]), label, key),
            ]
        added = added + additions
        doses[key] = list(doses["DOSE-0"]) + list(added)
    dose3 = []
    for index, entry in enumerate(case["doses"]["DOSE-3"]):
        pre = _settled(entry["pre_state_row"])
        dose3.extend(
            [
                state_observation(pre, f"DOSE-3.{index}-pre"),
                transition_observation(
                    pre, _settled(entry["step"]), "non_complete", f"DOSE-3.{index}"
                ),
            ]
        )
    doses["DOSE-3"] = doses["DOSE-2"] + dose3
    return doses


def survivor_curve(
    universe: list[dict[str, Any]], doses: dict[str, list]
) -> dict[str, list[int]]:
    """Cumulative survivor indices per dose; monotone by construction, asserted anyway."""
    order = [key for key in ("DOSE-0", "DOSE-1", "DOSE-2", "DOSE-3") if key in doses]
    survivors = list(range(len(universe)))
    consumed: list[dict[str, Any]] = []
    curve: dict[str, list[int]] = {}
    for key in order:
        new_observations = doses[key][len(consumed) :]
        consumed.extend(new_observations)
        survivors = [
            index
            for index in survivors
            if not any(
                observation_eliminates(universe[index], observation)
                for observation in new_observations
            )
        ]
        curve[key] = list(survivors)
    sizes = [len(curve[key]) for key in order]
    if any(late > early for early, late in zip(sizes, sizes[1:])):
        raise AssertionError(f"survivor curve is not monotone: {sizes}")
    return curve


# ====================================================================================
# DOSE-4: gold-blind greedy-sequential two-probe maximin selector
# ====================================================================================


def _action_sort_key(action: dict[str, Any]) -> tuple:
    data = action.get("action_data") or {}
    return (
        int(action["action_id"]),
        int(data.get("y", -1)),
        int(data.get("x", -1)),
        _sha256(_canonical_bytes(action)),
    )


def select_probe(
    handle: Any, survivors: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """One maximin probe from a StateHandle; returns the chosen fork or None."""
    evaluated = []
    for action in sorted(handle.reachable_actions(), key=_action_sort_key):
        outcome, branch = handle.fork(action["action_id"], action["action_data"])
        eval_grid = outcome.get("eval_grid") or branch.settled_grid
        complete_side = non_complete_side = 0
        for candidate in survivors:
            value = predict_transition(candidate, handle.settled_grid, eval_grid)
            if value in {TRUE, UNKNOWN}:
                complete_side += 1
            if value in {FALSE, UNKNOWN}:
                non_complete_side += 1
        reduction = len(survivors) - max(complete_side, non_complete_side)
        evaluated.append(
            {
                "action": action,
                "outcome": outcome,
                "branch": branch,
                "eval_grid": eval_grid,
                "worst_case_reduction": reduction,
            }
        )
    if not evaluated:
        return None
    return min(
        evaluated,
        key=lambda entry: (
            -entry["worst_case_reduction"],
            _action_sort_key(entry["action"]),
        ),
    )


def run_dose4(
    handle: Any, survivors: list[dict[str, Any]]
) -> dict[str, Any]:
    """Two greedy-sequential probes (SS3.3); engine labels update the survivor set."""
    probes: list[dict[str, Any]] = []
    current_handle = handle
    current = list(survivors)
    probe_complete = True
    for _ in range(2):
        chosen = select_probe(current_handle, current)
        if chosen is None:
            probe_complete = False
            break
        label = chosen["outcome"]["label"]
        observation = transition_observation(
            current_handle.settled_grid, chosen["eval_grid"], label, "DOSE-4"
        )
        current = [
            candidate
            for candidate in current
            if not observation_eliminates(candidate, observation)
        ]
        probes.append(
            {
                "action": chosen["action"],
                "label": label,
                "worst_case_reduction": chosen["worst_case_reduction"],
                "survivors_after": len(current),
            }
        )
        if not chosen["outcome"]["sequential_continuable"]:
            probe_complete = len(probes) == 2
            break
        current_handle = chosen["branch"]
    else:
        probe_complete = len(probes) == 2
    if len(probes) < 2:
        probe_complete = False
    return {"probes": probes, "probe_complete": probe_complete, "survivors": current}


# ====================================================================================
# E_i / O_i
# ====================================================================================


def substitute_bindings(
    node: dict[str, Any], bindings: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if node["op"] == "source_set":
        return dict(bindings[node["name"]]) if node["name"] in bindings else dict(node)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if isinstance(value, dict):
            out[key] = substitute_bindings(value, bindings)
        elif isinstance(value, list):
            out[key] = [
                substitute_bindings(item, bindings) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            out[key] = value
    return out


def gold_equivalent_route1(
    candidate: dict[str, Any],
    gold_ast: dict[str, Any],
    bindings: dict[str, dict[str, Any]],
) -> bool:
    """Route 1: canonical AST identity after normalizations + declared term bindings."""
    return serialize(candidate) == serialize(substitute_bindings(gold_ast, bindings))


def observational_match_set(
    universe: list[dict[str, Any]], suite: list[dict[str, Any]]
) -> list[int]:
    """O_i: two-valued and equal to the engine label on every suite point."""
    matched = []
    for index, candidate in enumerate(universe):
        ok = True
        for observation in suite:
            if observation["kind"] == "state":
                value = predict_state(candidate, observation["grid"])
                expected = FALSE
            else:
                value = predict_transition(
                    candidate, observation["pre_grid"], observation["post_grid"]
                )
                expected = TRUE if observation["label"] == "complete" else FALSE
            if value == UNKNOWN or value != expected:
                ok = False
                break
        if ok:
            matched.append(index)
    return matched


# ====================================================================================
# Bring-up: machinery validation over the frozen inventory (no gold join, no E_i)
# ====================================================================================


def _session_grids(env: str, guid: str, steps: set[int]) -> dict[int, dict[str, list]]:
    grids: dict[int, dict[str, list]] = {}
    for step in iter_trace(CORPUS / env / f"{guid}.recording.jsonl"):
        if step.index not in steps or not step.frames:
            continue
        solved = step.solved_terminal
        grids[step.index] = {
            "settled": step.frames[-1].grid,
            "solved": solved.grid if solved is not None else None,
        }
    missing = steps - set(grids)
    if missing:
        raise ValueError(f"{env}:{guid}: no frames for steps {sorted(missing)}")
    return grids


def _bringup_worker(job: dict[str, Any]) -> dict[str, Any]:
    env, guid = job["env"], job["guid"]
    steps: set[int] = set()
    for case in job["cases"]:
        steps.add(case["query"]["pre_state_row"])
        for key in ("DOSE-1", "DOSE-2"):
            entry = case["doses"][key]
            if entry is not None:
                steps.update({entry["pre_state_row"], entry["step"]})
        for entry in case["doses"]["DOSE-3"]:
            steps.update({entry["pre_state_row"], entry["step"]})
    grids = _session_grids(env, guid, steps)

    rows = []
    for case in job["cases"]:
        query_grid = grids[case["query"]["pre_state_row"]]["settled"]
        generated = enumerate_universe(query_grid)
        row: dict[str, Any] = {
            "case_id": case["case_id"],
            "env": env,
            "role": case["role"],
            "universe_size": generated["universe_size"],
            "universe_hash": generated["universe_hash"],
            "tractable": generated["tractable"],
            "terms": generated["terms"],
            "passive_complete": case["availability"]["passive_complete"],
        }
        if generated["tractable"] and case["availability"]["passive_complete"]:
            doses = dose_observations(case, grids)
            curve = survivor_curve(generated["universe"], doses)
            row["survivors"] = {key: len(indices) for key, indices in curve.items()}
        rows.append(row)
    return {"env": env, "guid": guid, "rows": rows}


def bring_up(jobs: int) -> dict[str, Any]:
    inventory = json.loads(INVENTORY.read_text())
    by_session: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for case in inventory["cases"]:
        by_session.setdefault((case["env"], case["guid"]), []).append(case)
    jobs_list = [
        {"env": env, "guid": guid, "cases": sorted(cases, key=lambda c: c["query"]["step"])}
        for (env, guid), cases in sorted(by_session.items())
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        chunks = list(pool.map(_bringup_worker, jobs_list))

    rows = [row for chunk in chunks for row in chunk["rows"]]
    per_game: dict[str, Any] = {}
    for row in rows:
        game = per_game.setdefault(
            row["env"],
            {"cases": 0, "tractable": 0, "max_universe": 0, "min_universe": None},
        )
        game["cases"] += 1
        game["tractable"] += bool(row["tractable"])
        game["max_universe"] = max(game["max_universe"], row["universe_size"])
        game["min_universe"] = (
            row["universe_size"]
            if game["min_universe"] is None
            else min(game["min_universe"], row["universe_size"])
        )
    document = {
        "format_version": 1,
        "generated_by": "agent/harness/es_candidates.py --bring-up",
        "grammar_spec": GRAMMAR_SPEC,
        "grammar_spec_hash": GRAMMAR_SPEC_HASH,
        "depth_calibration": calibrate_depth_bound(),
        "inputs": {"logs/es_inventory.json": inventory["fingerprint"]},
        "per_game": per_game,
        "rows": sorted(rows, key=lambda r: r["case_id"]),
        "totals": {
            "cases": len(rows),
            "tractable": sum(1 for r in rows if r["tractable"]),
            "scored_passive_complete": sum(1 for r in rows if "survivors" in r),
        },
    }
    payload = _canonical_bytes(document)
    document["fingerprint"] = _sha256(payload)
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibrate", action="store_true", help="print gold depth table")
    parser.add_argument("--bring-up", action="store_true", help="run machinery bring-up")
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()

    if args.calibrate:
        calibration = calibrate_depth_bound()
        print(json.dumps(calibration, indent=1, sort_keys=True))
        bound = calibration["expression_depth_bound"]
        if bound != EXPRESSION_DEPTH_BOUND:
            print(
                f"MISMATCH: calibrated bound {bound} != module constant "
                f"{EXPRESSION_DEPTH_BOUND} (ES-E3)"
            )
            return 1
        print(f"expression_depth_bound = {bound} (matches ES-E3 fill)")
        return 0

    if args.bring_up:
        document = bring_up(args.jobs)
        BRINGUP_OUTPUT.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
        totals = document["totals"]
        print(
            f"cases {totals['cases']}: tractable {totals['tractable']}, scored "
            f"passive-complete curves {totals['scored_passive_complete']}"
        )
        for env, game in sorted(document["per_game"].items()):
            print(
                f"  {env}: universes {game['min_universe']}..{game['max_universe']}, "
                f"tractable {game['tractable']}/{game['cases']}"
            )
        print(f"wrote {BRINGUP_OUTPUT.relative_to(ROOT)}")
        return 0

    parser.error("choose --calibrate or --bring-up")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
