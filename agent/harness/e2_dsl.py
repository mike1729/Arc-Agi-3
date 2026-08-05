#!/usr/bin/env python3
"""E2 slice-2 expression DSL — two small grammars, both parse-or-reject.

`notes/e2-slice2.md` (design) and `notes/e2-slice2-build.md` (build order, sub-task 1). Zero
model calls. This module is the shared substrate of slice 2: channel A's goal predicates,
the prior-library control that channel A is scored against, and channel B's latent
definitions all speak these two grammars, and nothing else is accepted.

WHY A GRAMMAR AT ALL
--------------------
Slice 1 and 1.1 scored prose goals at zero because nothing could evaluate them, and the
hidden-state task then spent its hours discovering that one prose sentence ("a hidden action
counter whose parity drives a mode switch") hides at least four distinct operational
readings — count since when, counting what, mod what, reset included or not. Slice 2 makes
the model do that disambiguation itself. A proposal that does not parse is recorded
`prose_rejected` and is never repaired into something scoreable: repairing it would score the
repairer.

THE PREDICATE GRAMMAR — deliberately row-C's expressiveness, plus exactly what the priors need
---------------------------------------------------------------------------------------------
The control (the prior library, sub-task 2) and the channel MUST share expressiveness, or the
comparison is rigged in whichever direction the asymmetry runs. So the predicate grammar is
pinned to the frozen row-C visual grammar (`es_candidates`, hash-asserted below) and extended
only by what the five stock prior shapes provably need:

    row-C, reproduced exactly     empty/nonempty/exactly_one(cN) · the six temporal events ·
                                  `exists x in cA: exists y in cB: R(x, y)` and
                                  `all x in cA: exists y in cB: R(x, y)` over the five frozen
                                  visual relations · `and` of at most two top-level clauses
    added for the prior shapes    count comparisons (`count(cN) = k`, `>= k`, and
                                  `count(cA) = count(cB)`) and the `same_shape` relation
                                  (cell sets equal up to translation — "copy the displayed
                                  template", "align the two matching objects")

Nothing else. Co-location and "all X satisfy R(Y)" are already row-C's `adjacent`/
`bbox_overlap` and its `all_exists` skeleton; colour matching is already carried by the
colour-indexed terms. The extension is two constructs wide and that is the whole of it.

One further widening, recorded because it is easy to miss: a relation's two arguments may
be written in either order (`bbox_contains(y, x)` as well as `bbox_contains(x, y)`). Row C
fixes the skeleton at `R(x, y)` and reaches the reverse of an asymmetric relation by
swapping the two operand COLOURS, which is a different predicate once the quantifier order
is `all`/`exists` — so "every X inside some Y" is expressible here and is not in the
enumerated row-C universe. It is needed by the `every X into/onto its Y` prior shape, and
the widening applies to the channel and to its control identically.

Evaluation is strong three-valued, and it AGREES WITH `rs_completion` on every predicate
row-C can express — asserted by property test over the real universes, not assumed:

    .venv/bin/python agent/harness/e2_dsl.py --selftest

The evaluator here is a separate ~50-line recursion rather than a call into
`es_candidates.evaluate`, because that function returns `unknown` for any relation outside
its frozen five and would therefore swallow `same_shape` SILENTLY rather than raise. The
cost of the duplication is one property test; the cost of the silent swallow would be a
scored channel whose shape predicates all evaluate `unknown`. Every leaf-level semantic
(components, background, lineage, the five relations) is still imported, never restated.

THE COUNTER GRAMMAR — every operational reading spelled out in the surface syntax
--------------------------------------------------------------------------------
    base       actions_total
               actions_since_reset[reset_excluded] | actions_since_reset[reset_included]
               actions_of(<id>)_total
               actions_of(<id>)_since_reset[reset_excluded|reset_included]
    transform  (none) | `mod k` for 2 <= k <= 8 | `>= n`

The RESET convention is not a default and not a footnote: `since_reset` does not parse
without it. `reset_included` counts the RESET action itself as one action of the episode,
which is the `c2_episode_incl` convention control from `notes/e2-hidden-state.md`;
`reset_excluded` is `c2_episode`. The counters are computed AT THE PRE-STATE — the number of
actions the environment executed BEFORE the action being predicted — identically on the store
side and the human side, which is the convention `e2_hidden_state.py` established and this
module reproduces rather than re-derives (`--selftest` asserts the reproduction).

Run:
  .venv/bin/python agent/harness/e2_dsl.py --selftest
  .venv/bin/python agent/harness/e2_dsl.py --grammar        # the text the prompt prints
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = __import__("pathlib").Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import es_candidates as ec  # noqa: E402
from es_candidates import _Objects, _eval_temporal, _relation_holds  # noqa: E402

TRUE, FALSE, UNKNOWN = ec.TRUE, ec.FALSE, ec.UNKNOWN

# The predicate grammar is pinned to the frozen row-C grammar. If that hash moves, the
# alignment claim above is void and this module must be re-read, not re-hashed.
EXPECTED_GRAMMAR_HASH = "49c0cc3e4abc74186edbc65665f65fd68e1faa7e9e3678d58ce53346cb0b2a6b"

CARDINALITY = ec.CARDINALITY_FORMS  # empty, nonempty, exactly_one
TEMPORAL = ec.TEMPORAL_EVENTS
VISUAL_RELATIONS = ec.VISUAL_RELATIONS
EXTENSION_RELATIONS = ("same_shape",)
RELATIONS = tuple(VISUAL_RELATIONS) + EXTENSION_RELATIONS
SYMMETRIC = frozenset(ec.SYMMETRIC_RELATIONS) | {"same_shape"}

MAX_CLAUSES = ec.MAX_CLAUSES  # 2 — the frozen row-C bound, inherited not chosen
MAX_MODULUS = 8  # (w) the note's bound on `mod k`


class DSLError(ValueError):
    """A proposal that does not parse. Recorded, counted, never repaired."""


# ======================================================================================
# Predicate grammar — surface syntax
# ======================================================================================

_TERM = re.compile(r"^c(\d+)$")
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
_CALL = re.compile(r"^([a-z_]+)\((.*)\)$", re.S)
_COUNT = re.compile(r"^count\(\s*c(\d+)\s*\)$")
_QUANT = re.compile(
    r"^(exists|all)\s+([A-Za-z_][A-Za-z_0-9]*)\s+in\s+(c\d+)\s*:\s*(.+)$", re.S
)


def _term(text: str) -> dict[str, Any]:
    match = _TERM.match(text.strip())
    if not match:
        raise DSLError(f"not a colour term: {text.strip()!r} (expected e.g. c3)")
    return {"op": "colour_components", "colour": int(match.group(1))}


def _split_top(text: str, separator: str) -> list[str]:
    """Split on `separator` at paren depth zero."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise DSLError("unbalanced parentheses")
        # `separator` carries its own surrounding spaces (" and "), so it is already
        # word-bounded; testing the neighbouring characters as well would reject the very
        # thing it is meant to split.
        if depth == 0 and text.startswith(separator, index):
            parts.append("".join(current))
            current = []
            index += len(separator)
            continue
        current.append(char)
        index += 1
    if depth:
        raise DSLError("unbalanced parentheses")
    parts.append("".join(current))
    return [part.strip() for part in parts]


def parse_predicate(text: str) -> dict[str, Any]:
    """Surface syntax -> AST, or raise DSLError. Never partially accepts."""
    if not isinstance(text, str) or not text.strip():
        raise DSLError("empty predicate")
    clauses = [part for part in _split_top(text.strip(), " and ") if part]
    if len(clauses) > MAX_CLAUSES:
        raise DSLError(
            f"{len(clauses)} top-level clauses; the frozen bound is {MAX_CLAUSES}"
        )
    parsed = [_parse_clause(clause) for clause in clauses]
    if len(parsed) == 1:
        return parsed[0]
    return {"op": "and", "args": parsed}


def _parse_clause(text: str) -> dict[str, Any]:
    text = text.strip()
    while text.startswith("(") and text.endswith(")") and len(_split_top(text, " and ")) == 1:
        inner = text[1:-1].strip()
        try:
            _split_top(inner, " and ")
        except DSLError:
            break
        text = inner
    quant = _QUANT.match(text)
    if quant:
        return _parse_quantified(quant)
    if text.startswith("count("):
        return _parse_count(text)
    call = _CALL.match(text)
    if not call:
        raise DSLError(f"not a clause: {text!r}")
    name, argument = call.group(1), call.group(2).strip()
    if name in CARDINALITY:
        return {"op": name, "set": _term(argument)}
    if name in TEMPORAL:
        return {"op": "temporal", "event": name, "set": _term(argument)}
    raise DSLError(
        f"unknown predicate form {name!r}; expected one of "
        f"{', '.join(sorted(set(CARDINALITY) | set(TEMPORAL)))}, count(...), exists, all"
    )


def _parse_count(text: str) -> dict[str, Any]:
    for symbol in (">=", "="):
        parts = _split_top(text, symbol)
        if len(parts) == 2:
            left_text, right_text = parts
            break
        if len(parts) > 2:
            raise DSLError(f"more than one comparison in {text!r}")
    else:
        raise DSLError(f"count comparison needs `=` or `>=`: {text!r}")
    left = _COUNT.match(left_text.strip())
    if not left:
        raise DSLError(f"left of a count comparison must be count(cN): {left_text!r}")
    node: dict[str, Any] = {
        "op": "count_cmp",
        "cmp": symbol,
        "left": {"op": "colour_components", "colour": int(left.group(1))},
    }
    right_text = right_text.strip()
    right = _COUNT.match(right_text)
    if right:
        if symbol != "=":
            raise DSLError("count-to-count comparison supports `=` only")
        node["right"] = {"op": "colour_components", "colour": int(right.group(1))}
        return node
    if not re.fullmatch(r"\d+", right_text):
        raise DSLError(f"right of a count comparison must be an integer or count(cN): {right_text!r}")
    node["right"] = int(right_text)
    return node


def _parse_quantified(match: re.Match) -> dict[str, Any]:
    outer_op, outer_var, outer_term, rest = match.groups()
    inner = _QUANT.match(rest.strip())
    if not inner:
        raise DSLError(
            "a quantified predicate must be `<exists|all> x in cA: exists y in cB: R(x, y)`"
        )
    inner_op, inner_var, inner_term, body = inner.groups()
    if inner_op != "exists":
        raise DSLError(
            "the inner quantifier must be `exists` — row-C's universe has exactly the "
            "exists/exists and all/exists skeletons and the grammars are pinned together"
        )
    if outer_var == inner_var:
        raise DSLError(f"the two quantifiers reuse the variable {outer_var!r}")
    call = _CALL.match(body.strip())
    if not call:
        raise DSLError(f"not a relation: {body.strip()!r}")
    name, arguments = call.group(1), [a.strip() for a in call.group(2).split(",")]
    if name not in RELATIONS:
        raise DSLError(
            f"unknown relation {name!r}; the vocabulary is {', '.join(RELATIONS)}"
        )
    if len(arguments) != 2:
        raise DSLError(f"relation {name} takes exactly two arguments")
    for argument in arguments:
        if not _IDENT.match(argument):
            raise DSLError(f"relation arguments must be the bound variables: {argument!r}")
        if argument not in (outer_var, inner_var):
            raise DSLError(f"unbound variable {argument!r}")
    return {
        "op": outer_op,
        "var": outer_var,
        "in": _term(outer_term),
        "satisfies": {
            "op": "exists",
            "var": inner_var,
            "in": _term(inner_term),
            "satisfies": {
                "op": "relation",
                "name": name,
                "args": [{"op": "var", "name": argument} for argument in arguments],
            },
        },
    }


# ======================================================================================
# Predicate grammar — unparse and normal form
# ======================================================================================


def unparse(node: dict[str, Any]) -> str:
    op = node["op"]
    if op == "and":
        return " and ".join(unparse(arg) for arg in node["args"])
    if op in CARDINALITY:
        return f"{op}({_unparse_term(node['set'])})"
    if op == "temporal":
        return f"{node['event']}({_unparse_term(node['set'])})"
    if op == "count_cmp":
        right = node["right"]
        right_text = (
            str(right) if isinstance(right, int) else f"count({_unparse_term(right)})"
        )
        return f"count({_unparse_term(node['left'])}) {node['cmp']} {right_text}"
    if op in ("exists", "all"):
        inner = node["satisfies"]
        relation = inner["satisfies"]
        arguments = ", ".join(argument["name"] for argument in relation["args"])
        return (
            f"{op} {node['var']} in {_unparse_term(node['in'])}: "
            f"exists {inner['var']} in {_unparse_term(inner['in'])}: "
            f"{relation['name']}({arguments})"
        )
    raise DSLError(f"cannot unparse op {op!r}")


def _unparse_term(term: dict[str, Any]) -> str:
    if term["op"] != "colour_components":
        raise DSLError(f"cannot unparse term {term!r}")
    return f"c{term['colour']}"


def normalize(node: dict[str, Any]) -> dict[str, Any]:
    """Semantics-preserving normal form, so two spellings of one predicate dedupe.

    Mirrors the frozen row-C normalizations that apply to this grammar's shapes — `and`
    flattening with sorted unique arguments, symmetric-relation argument ordering, and
    de Bruijn variable renaming to x/y — and adds the obvious one for the extension:
    `count(cA) = count(cB)` orders its two terms. It does NOT call
    `es_candidates.canonicalize`, which raises on the extension ops; agreement with it on
    row-C shapes is asserted by `--selftest`, not asserted here in prose.
    """
    op = node["op"]
    if op == "and":
        args = []
        for argument in node["args"]:
            normalized = normalize(argument)
            args.extend(normalized["args"] if normalized["op"] == "and" else [normalized])
        unique = {unparse(argument): argument for argument in args}
        ordered = [unique[key] for key in sorted(unique)]
        return ordered[0] if len(ordered) == 1 else {"op": "and", "args": ordered}
    if op == "count_cmp":
        out = dict(node)
        if isinstance(node["right"], dict) and node["cmp"] == "=":
            left, right = node["left"], node["right"]
            if right["colour"] < left["colour"]:
                out["left"], out["right"] = right, left
        return out
    if op in ("exists", "all"):
        inner = node["satisfies"]
        relation = inner["satisfies"]
        names = {node["var"]: "x", inner["var"]: "y"}
        args = [{"op": "var", "name": names[a["name"]]} for a in relation["args"]]
        if relation["name"] in SYMMETRIC:
            args = sorted(args, key=lambda a: a["name"])
        return {
            "op": op,
            "var": "x",
            "in": dict(node["in"]),
            "satisfies": {
                "op": "exists",
                "var": "y",
                "in": dict(inner["in"]),
                "satisfies": {
                    "op": "relation",
                    "name": relation["name"],
                    "args": args,
                },
            },
        }
    return dict(node)


def canonical(text_or_node: str | dict[str, Any]) -> str:
    node = (
        parse_predicate(text_or_node)
        if isinstance(text_or_node, str)
        else text_or_node
    )
    return unparse(normalize(node))


# ======================================================================================
# Predicate evaluation — strong three-valued, agreeing with row-C where row-C speaks
# ======================================================================================


def _members(term: dict[str, Any], objects: _Objects) -> list[dict[str, Any]] | None:
    """None = ambiguous binding (the colour is this state's background) — row-C's rule."""
    if term["op"] != "colour_components":
        return None
    return objects.members(term["colour"])


def _shape(member: dict[str, Any]) -> frozenset:
    rows = [row for row, _ in member["cells"]]
    cols = [col for _, col in member["cells"]]
    top, left = min(rows), min(cols)
    return frozenset((row - top, col - left) for row, col in member["cells"])


def _holds(name: str, a: dict[str, Any], b: dict[str, Any]) -> bool:
    if name == "same_shape":
        return _shape(a) == _shape(b)
    return _relation_holds(name, a, b)


def evaluate(node: dict[str, Any], context: dict[str, Any]) -> str:
    """Evaluate against {objects, pre_objects?, scope?} — the row-C context shape."""
    op = node["op"]
    objects: _Objects = context["objects"]

    if op == "and":
        values = [evaluate(argument, context) for argument in node["args"]]
        if FALSE in values:
            return FALSE
        return UNKNOWN if UNKNOWN in values else TRUE
    if op in CARDINALITY:
        members = _members(node["set"], objects)
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
    if op == "count_cmp":
        left = _members(node["left"], objects)
        if left is None:
            return UNKNOWN
        right = node["right"]
        if isinstance(right, dict):
            other = _members(right, objects)
            if other is None:
                return UNKNOWN
            return TRUE if len(left) == len(other) else FALSE
        if node["cmp"] == "=":
            return TRUE if len(left) == right else FALSE
        return TRUE if len(left) >= right else FALSE
    if op in ("exists", "all"):
        members = _members(node["in"], objects)
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
        resolved = []
        for argument in node["args"]:
            if argument["op"] != "var":
                return UNKNOWN
            member = context.get("scope", {}).get(argument["name"])
            if member is None:
                return UNKNOWN
            resolved.append(member)
        return TRUE if _holds(node["name"], *resolved) else FALSE
    raise DSLError(f"cannot evaluate op {op!r}")


def predict_transition(node: dict[str, Any], pre_grid: list, post_grid: list) -> str:
    """Row-C's transition reading: evaluate on the post frame with pre->post as context."""
    return evaluate(
        node, {"objects": _Objects(post_grid), "pre_objects": _Objects(pre_grid)}
    )


def consistent_with(
    node: dict[str, Any], transitions: list, *, cache: Any = None
) -> dict[str, Any]:
    """Row-C survivorship over a transition list: definite-and-wrong kills.

    Identical semantics to `rs_completion.survivors` / `score` — `unknown` neither
    eliminates nor confirms, and a candidate that is never definite anywhere is `vacuous`,
    not `survived`. Returns the three-way outcome plus its counts, because collapsing
    vacuous into survived is exactly the failure row C was written to avoid.
    """
    definite_correct = 0
    contradicted_at = None
    for index, transition in enumerate(transitions):
        if cache is not None:
            context = cache.context(transition.pre, transition.post)
            value = evaluate(node, context)
        else:
            value = predict_transition(node, transition.pre, transition.post)
        if value == UNKNOWN:
            continue
        truth = TRUE if transition.completed else FALSE
        if value != truth:
            contradicted_at = index
            break
        definite_correct += 1
    if contradicted_at is not None:
        outcome = "falsified"
    elif definite_correct:
        outcome = "survived"
    else:
        outcome = "vacuous"
    return {
        "outcome": outcome,
        "definite_correct": definite_correct,
        "contradicted_at": contradicted_at,
        "positives_matched": sum(
            1
            for transition in transitions
            if transition.completed
            and predict_transition(node, transition.pre, transition.post) == TRUE
        )
        if outcome != "falsified"
        else 0,
    }


# ======================================================================================
# Counter grammar
# ======================================================================================

_COUNTER = re.compile(
    r"^(?P<base>actions_total"
    r"|actions_since_reset\[(?P<flag>reset_excluded|reset_included)\]"
    r"|actions_of\((?P<id>\d+)\)_total"
    r"|actions_of\((?P<id2>\d+)\)_since_reset\[(?P<flag2>reset_excluded|reset_included)\])"
    r"(?:\s+(?P<transform>mod\s+\d+|>=\s*\d+))?$"
)


def parse_counter(text: str) -> dict[str, Any]:
    """Surface syntax -> counter AST, or raise DSLError."""
    if not isinstance(text, str) or not text.strip():
        raise DSLError("empty counter definition")
    match = _COUNTER.fullmatch(" ".join(text.split()))
    if not match:
        raise DSLError(
            f"not a counter expression: {text.strip()!r}. The grammar is "
            f"`<base>[ mod k| >= n]` with base one of actions_total, "
            f"actions_since_reset[reset_excluded|reset_included], actions_of(<id>)_total, "
            f"actions_of(<id>)_since_reset[reset_excluded|reset_included]"
        )
    action_id = match.group("id") or match.group("id2")
    flag = match.group("flag") or match.group("flag2")
    node: dict[str, Any] = {
        "op": "counter",
        "scope": "total" if match.group("base").endswith("_total") or match.group("base") == "actions_total" else "since_reset",
        "action_id": int(action_id) if action_id is not None else None,
        "reset_counted": None if flag is None else (flag == "reset_included"),
        "transform": None,
        "k": None,
    }
    transform = match.group("transform")
    if transform:
        if transform.startswith("mod"):
            k = int(transform.split()[-1])
            if not 2 <= k <= MAX_MODULUS:
                raise DSLError(f"modulus {k} outside the frozen range 2..{MAX_MODULUS}")
            node["transform"], node["k"] = "mod", k
        else:
            node["transform"] = "ge"
            node["k"] = int(transform.replace(">=", "").strip())
    return node


def unparse_counter(node: dict[str, Any]) -> str:
    if node["action_id"] is None:
        base = "actions"
    else:
        base = f"actions_of({node['action_id']})"
    if node["scope"] == "total":
        base = "actions_total" if node["action_id"] is None else f"{base}_total"
    else:
        flag = "reset_included" if node["reset_counted"] else "reset_excluded"
        base = (
            f"actions_since_reset[{flag}]"
            if node["action_id"] is None
            else f"{base}_since_reset[{flag}]"
        )
    if node["transform"] == "mod":
        return f"{base} mod {node['k']}"
    if node["transform"] == "ge":
        return f"{base} >= {node['k']}"
    return base


class CounterStream:
    """Running counts over one action stream, read AT THE PRE-STATE of each action.

    Convention, identical on both sides and identical to `e2_hidden_state.py`: the value for
    a transition is the number of actions the environment executed BEFORE the action being
    predicted. Environment creation is an implicit RESET, which is what makes the
    since-reset counts defined for every row rather than only after the first explicit one.

    `observe()` is called once per framed response row in stream order — RESETs and
    zero-frame rows included — because that is what `rs_transitions.iter_session_transitions`
    counts, and a counter that indexed only the framed transitions would silently disagree
    with the human side by exactly the number of RESETs.
    """

    def __init__(self) -> None:
        self.total = 0  # actions executed so far
        self.last_reset = 0  # 1-indexed stream position of the last RESET
        self.per_id: dict[int, int] = {}
        self.per_id_since_reset: dict[int, int] = {}
        self.reset_seen = False

    def counters(self) -> dict[str, Any]:
        """The raw counts AT THE PRE-STATE of the next action to be observed."""
        step = self.total + 1  # the 1-indexed stream position of that next action
        return {
            "total": step - 1,
            "since_reset_excluded": (step - 1) - self.last_reset,
            "since_reset_included": step - self.last_reset,
            "per_id_total": dict(self.per_id),
            "per_id_since_reset_excluded": dict(self.per_id_since_reset),
            # the RESET itself, counted as one action of the episode
            "per_id_since_reset_included": {
                **self.per_id_since_reset,
                **({0: self.per_id_since_reset.get(0, 0) + 1} if self.reset_seen else {}),
            },
        }

    def observe(self, action_id: int) -> None:
        self.total += 1
        self.per_id[action_id] = self.per_id.get(action_id, 0) + 1
        if action_id == 0:
            self.last_reset = self.total
            self.per_id_since_reset = {}
            self.reset_seen = True
        else:
            self.per_id_since_reset[action_id] = (
                self.per_id_since_reset.get(action_id, 0) + 1
            )


def counter_value(node: dict[str, Any], counters: dict[str, Any]) -> Any:
    """One counter expression's feature value, or None if it is not computable here.

    None is never defaulted into a number: a defaulted guard is a fabricated one, and
    `e2_hidden_state.inject` omits an arm it cannot compute for exactly that reason.
    """
    if node["action_id"] is None:
        if node["scope"] == "total":
            base = counters.get("total")
        else:
            key = (
                "since_reset_included"
                if node["reset_counted"]
                else "since_reset_excluded"
            )
            base = counters.get(key)
    else:
        if node["scope"] == "total":
            table = counters.get("per_id_total")
        else:
            table = counters.get(
                "per_id_since_reset_included"
                if node["reset_counted"]
                else "per_id_since_reset_excluded"
            )
        base = None if table is None else int(table.get(node["action_id"], 0))
    if base is None:
        return None
    if node["transform"] == "mod":
        return base % node["k"]
    if node["transform"] == "ge":
        return base >= node["k"]
    return base


# ======================================================================================
# Extraction-side rejection
# ======================================================================================


def classify_predicate(text: Any) -> dict[str, Any]:
    return _classify(text, parse_predicate, unparse, "predicate")


def classify_counter(text: Any) -> dict[str, Any]:
    return _classify(text, parse_counter, unparse_counter, "counter")


def _classify(text: Any, parse, render, kind: str) -> dict[str, Any]:
    """`{status: parsed|prose_rejected, ...}` — a scored category, not an error path."""
    if not isinstance(text, str) or not text.strip():
        return {"status": "prose_rejected", "kind": kind, "text": text, "reason": "empty"}
    try:
        node = parse(text)
    except DSLError as error:
        return {
            "status": "prose_rejected",
            "kind": kind,
            "text": text,
            "reason": str(error),
        }
    return {
        "status": "parsed",
        "kind": kind,
        "text": text,
        "ast": node,
        "canonical": canonical(node) if kind == "predicate" else render(node),
    }


# ======================================================================================
# The grammar text the prompt prints (one source, so prompt and parser cannot drift)
# ======================================================================================

PREDICATE_GRAMMAR_TEXT = f"""A PREDICATE is written in this grammar and nothing else. `cN` means "the objects of
colour N" (4-connected same-colour components, measured against the state's background).

  empty(cN) | nonempty(cN) | exactly_one(cN)      how many objects of that colour exist
  count(cN) = k | count(cN) >= k | count(cA) = count(cB)
  appears(cN) | disappears(cN) | changes(cN) | persists(cN) | splits(cN) | merges(cN)
  exists x in cA: exists y in cB: R(x, y)
  all x in cA: exists y in cB: R(x, y)
  <clause> and <clause>                            at most {MAX_CLAUSES} clauses in total

R is one of: {', '.join(RELATIONS)}.
  adjacent        some cell of x is 4-adjacent to some cell of y
  bbox_overlap    their bounding boxes intersect
  bbox_contains   x's bounding box contains y's
  row_aligned     their row intervals overlap; col_aligned likewise for columns
  same_shape      their cell sets are equal up to translation

Examples of well-formed predicates:
  empty(c4)
  count(c7) = 3
  all x in c2: exists y in c9: bbox_overlap(x, y)
  exists x in c3: exists y in c3: same_shape(x, y) and empty(c8)

Anything that does not parse in this grammar scores zero and is recorded as rejected.
Do not write prose. Do not invent relations, negation, "or", or arithmetic."""

COUNTER_GRAMMAR_TEXT = f"""A LATENT DEFINITION is a counter expression in this grammar and nothing else:

  <base>                     the count, as an integer
  <base> mod k               k between 2 and {MAX_MODULUS}
  <base> >= n                a threshold, true or false

where <base> is exactly one of:
  actions_total                                   every action since the game was created
  actions_since_reset[reset_excluded]             actions since the last RESET, NOT counting
                                                  the RESET action itself
  actions_since_reset[reset_included]             the same, counting the RESET as one action
  actions_of(<id>)_total                          actions with that action id (0=RESET,
                                                  1-5 simple, 6 click, 7 undo)
  actions_of(<id>)_since_reset[reset_excluded]
  actions_of(<id>)_since_reset[reset_included]

The RESET convention is NOT optional and there is no default: `actions_since_reset` without
one of the two bracketed flags does not parse. Examples:
  actions_since_reset[reset_excluded] mod 2
  actions_total mod 4
  actions_of(6)_since_reset[reset_excluded] >= 3

Anything that does not parse in this grammar scores zero and is recorded as rejected."""


# ======================================================================================
# Self-test — the two acceptance checks of sub-task 1
# ======================================================================================


def _selftest_predicates(games: list[str]) -> dict[str, Any]:
    """AGREEMENT: on every row-C-expressible predicate, over the real universes.

    For each game: enumerate the frozen row-C universe from the store's first pre-frame,
    render every candidate through this module's unparse, re-parse it, and check (a) the
    round trip is stable and (b) this evaluator returns exactly what `es_candidates.evaluate`
    (the function `rs_completion` predicts with) returns, on every store transition.
    """
    from e2_dose import load_store  # noqa: PLC0415

    rows = []
    for game in games:
        store, post_missing = load_store(game)
        if not store:
            rows.append({"game": game, "skipped": "empty store"})
            continue
        universe = ec.enumerate_universe(store[0].pre)
        if not universe["tractable"]:
            rows.append({"game": game, "skipped": "universe intractable"})
            continue
        sample = [t for t in store if t.step not in post_missing][:60]
        contexts = [
            {"objects": _Objects(t.post), "pre_objects": _Objects(t.pre)} for t in sample
        ]
        roundtrip = mismatches = compared = 0
        first_mismatch = None
        for candidate in universe["universe"]:
            text = unparse(candidate)
            reparsed = parse_predicate(text)
            if unparse(reparsed) != text:
                roundtrip += 1
                continue
            if ec.serialize(reparsed) != ec.serialize(candidate):
                roundtrip += 1
                continue
            for context in contexts:
                compared += 1
                mine = evaluate(reparsed, context)
                theirs = ec.evaluate(candidate, context)
                if mine != theirs:
                    mismatches += 1
                    if first_mismatch is None:
                        first_mismatch = {"predicate": text, "dsl": mine, "row_c": theirs}
        rows.append(
            {
                "game": game,
                "universe_size": universe["universe_size"],
                "contexts": len(contexts),
                "evaluations_compared": compared,
                "roundtrip_failures": roundtrip,
                "evaluation_mismatches": mismatches,
                "first_mismatch": first_mismatch,
            }
        )
    ok = all(
        row.get("roundtrip_failures", 0) == 0 and row.get("evaluation_mismatches", 0) == 0
        for row in rows
    )
    return {"passed": ok, "games": rows}


def _selftest_counters(game: str = "m0r0") -> dict[str, Any]:
    """REPRODUCTION: the counter DSL rebuilds the committed hidden-state arms exactly.

    `e2_hidden_state.human_counters` is the authority for the human side; this compares the
    DSL's value for every transition against `arm_values`' value for the arm it claims to
    reproduce, byte for byte, and reports the first disagreement rather than a rate.
    """
    from e2_hidden_state import arm_values, human_counters  # noqa: PLC0415
    from rs_transitions import CORPUS, EXCLUDED_SESSIONS, load_game  # noqa: PLC0415
    from gi2_traces import normalize_action_id  # noqa: PLC0415

    equivalences = {
        "c1_global": "actions_total mod 2",
        "c1_global_m3": "actions_total mod 3",
        "c1_global_m4": "actions_total mod 4",
        "c2_episode": "actions_since_reset[reset_excluded] mod 2",
        "c2_episode_m3": "actions_since_reset[reset_excluded] mod 3",
        "c2_episode_m4": "actions_since_reset[reset_excluded] mod 4",
        "c2_episode_incl": "actions_since_reset[reset_included] mod 2",
    }

    # Rebuild the human-side counters through CounterStream, then check they equal the
    # committed table row for row before any arm is compared.
    table = human_counters(game)
    mine: dict[tuple[str, int], dict[str, Any]] = {}
    for path in sorted((CORPUS / game).glob("*.recording.jsonl")):
        guid = path.name.split(".")[0]
        if (game, guid[:8]) in EXCLUDED_SESSIONS:
            continue
        stream = CounterStream()
        step = 0
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                data = json.loads(line).get("data")
                if not isinstance(data, dict) or "frame" not in data:
                    continue
                step += 1
                action = data.get("action_input") or {}
                try:
                    action_id = normalize_action_id(action.get("id"))
                except ValueError:
                    action_id = -1
                mine[(guid, step)] = stream.counters()
                stream.observe(action_id)

    raw_mismatch = None
    for key, committed in table.items():
        ours = mine.get(key)
        if ours is None:
            raw_mismatch = {"key": list(key), "reason": "missing from CounterStream"}
            break
        if (
            ours["total"] != committed["global"]
            or ours["since_reset_excluded"] != committed["episode"]
            or ours["since_reset_included"] != committed["episode_incl"]
        ):
            raw_mismatch = {"key": list(key), "ours": ours, "committed": committed}
            break

    human = load_game(game, max_level=2)
    arm_mismatches: dict[str, Any] = {}
    compared = 0
    for transition in human:
        committed = table.get((transition.guid, transition.step))
        ours = mine.get((transition.guid, transition.step))
        if committed is None or ours is None:
            continue
        expected = arm_values(committed, transition.step)
        for arm, expression in equivalences.items():
            if arm not in expected:
                continue
            compared += 1
            value = counter_value(parse_counter(expression), ours)
            if value != expected[arm] and arm not in arm_mismatches:
                arm_mismatches[arm] = {
                    "guid": transition.guid,
                    "step": transition.step,
                    "dsl": value,
                    "arm": expected[arm],
                }
    return {
        "passed": raw_mismatch is None and not arm_mismatches,
        "game": game,
        "raw_counter_mismatch": raw_mismatch,
        "transitions_compared": len(human),
        "arm_values_compared": compared,
        "arm_mismatches": arm_mismatches,
        "equivalences": equivalences,
    }


def _selftest_rejection() -> dict[str, Any]:
    """The grammars must REJECT what slice 1 accepted as prose, and nothing they should take."""
    must_reject = [
        "the level completes when all the blue blocks are gone",
        "empty(c4) or empty(c5)",
        "not empty(c4)",
        "count(c4) > 3",
        "empty(c4) and nonempty(c5) and empty(c6)",
        "exists x in c3: all y in c5: adjacent(x, y)",
        "exists x in c3: exists y in c5: touches(x, y)",
        "all x in c3: exists y in c5: adjacent(x, z)",
        "empty(blue)",
    ]
    must_accept = [
        "empty(c4)",
        "nonempty(c0) and exactly_one(c9)",
        "count(c7) = 3",
        "count(c7) >= 1",
        "count(c2) = count(c5)",
        "persists(c1)",
        "all x in c2: exists y in c9: bbox_overlap(x, y)",
        "exists x in c3: exists y in c3: same_shape(x, y)",
    ]
    counters_reject = [
        "a hidden counter whose parity drives a mode switch",
        "actions_since_reset mod 2",  # no RESET convention -> rejected, by design
        "actions_total mod 9",
        "actions_total / 2",
        "actions_of(6) mod 2",  # no scope -> rejected
    ]
    counters_accept = [
        "actions_total",
        "actions_total mod 2",
        "actions_since_reset[reset_excluded] mod 2",
        "actions_since_reset[reset_included] mod 2",
        "actions_of(6)_total >= 3",
        "actions_of(1)_since_reset[reset_excluded] mod 8",
    ]
    wrong: list[str] = []
    for text in must_reject:
        if classify_predicate(text)["status"] != "prose_rejected":
            wrong.append(f"predicate wrongly accepted: {text!r}")
    for text in must_accept:
        outcome = classify_predicate(text)
        if outcome["status"] != "parsed":
            wrong.append(f"predicate wrongly rejected: {text!r} ({outcome['reason']})")
    for text in counters_reject:
        if classify_counter(text)["status"] != "prose_rejected":
            wrong.append(f"counter wrongly accepted: {text!r}")
    for text in counters_accept:
        outcome = classify_counter(text)
        if outcome["status"] != "parsed":
            wrong.append(f"counter wrongly rejected: {text!r} ({outcome['reason']})")
    return {
        "passed": not wrong,
        "checked": len(must_reject) + len(must_accept) + len(counters_reject) + len(counters_accept),
        "failures": wrong,
    }


SLICE2_GAMES = ("dc22", "ft09", "ls20", "m0r0", "tu93", "vc33", "sp80", "lf52")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--grammar", action="store_true", help="print the prompt text")
    parser.add_argument("--games", nargs="*", default=list(SLICE2_GAMES))
    parser.add_argument("--parse", nargs="*", help="parse predicates from the command line")
    parser.add_argument("--parse-counter", nargs="*", dest="parse_counter")
    args = parser.parse_args()

    if args.grammar:
        print(PREDICATE_GRAMMAR_TEXT)
        print()
        print(COUNTER_GRAMMAR_TEXT)
        return 0
    if args.parse:
        for text in args.parse:
            print(json.dumps(classify_predicate(text), indent=1, sort_keys=True))
        return 0
    if args.parse_counter:
        for text in args.parse_counter:
            print(json.dumps(classify_counter(text), indent=1, sort_keys=True))
        return 0
    if not args.selftest:
        parser.error("nothing to do; pass --selftest, --grammar, --parse or --parse-counter")

    if ec.GRAMMAR_SPEC_HASH != EXPECTED_GRAMMAR_HASH:
        raise SystemExit(
            f"row-C grammar hash mismatch: {ec.GRAMMAR_SPEC_HASH} != {EXPECTED_GRAMMAR_HASH}"
        )

    rejection = _selftest_rejection()
    print(
        f"rejection: {'PASS' if rejection['passed'] else 'FAIL'} "
        f"({rejection['checked']} cases)",
        flush=True,
    )
    for failure in rejection["failures"]:
        print(f"  {failure}", flush=True)

    predicates = _selftest_predicates(args.games)
    for row in predicates["games"]:
        if "skipped" in row:
            print(f"  {row['game']:5s} skipped: {row['skipped']}", flush=True)
            continue
        print(
            f"  {row['game']:5s} universe={row['universe_size']:4d} "
            f"evaluations={row['evaluations_compared']:6d} "
            f"roundtrip_failures={row['roundtrip_failures']} "
            f"mismatches={row['evaluation_mismatches']}",
            flush=True,
        )
    print(f"predicate agreement with row C: {'PASS' if predicates['passed'] else 'FAIL'}")

    counters = _selftest_counters()
    print(
        f"counter reproduction on {counters['game']}: "
        f"{'PASS' if counters['passed'] else 'FAIL'} "
        f"({counters['arm_values_compared']} arm values over "
        f"{counters['transitions_compared']} transitions)",
        flush=True,
    )
    if not counters["passed"]:
        print(json.dumps(counters, indent=1, sort_keys=True, default=str))

    passed = rejection["passed"] and predicates["passed"] and counters["passed"]
    print(f"\nSELFTEST {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
