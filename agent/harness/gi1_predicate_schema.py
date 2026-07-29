#!/usr/bin/env python3
"""GI-1 structured predicate schema — ONE source of truth for three consumers:

  1. the (b)-(d) prompt (gi1_render embeds the per-class field guide);
  2. the normalized parameter-gold annotation (built on this schema, iteration slice first);
  3. the mechanical K4 scorer (field-wise comparison of hypothesis vs gold).

Free-text `parameter_sketch` was rejected in review: it cannot be scored field-wise and would
reintroduce open-ended rating into the primary verdict. Instead every hypothesis carries a
`predicate` object whose fields depend on its class, per the table below.

Mechanical comparison, by field type:
  - enum fields   — case-insensitive match on both sides;
  - int fields    — exact match (bool is not an int here, despite subclassing it);
  - entity fields — normalized token match: ARC colour symbols expanded by their
    case-sensitive legend name, ordinary words lowercased, and TOKEN ORDER PRESERVED.
    near-misses go ONLY to the frozen enumerated-equivalence list, every invocation logged
    (notes/design-pivot.md §4.3).

⚠ DEV-UNFROZEN: field names and enums freeze together with the parameter-gold layer, before
the 27B-8bit iteration pass. Until then they may change on iteration-slice evidence only.
"""

from __future__ import annotations

# field spec: name -> ("enum", [...]) | ("int",) | ("entity",) | ("entity_list",)
PREDICATE_FIELDS: dict[str, dict[str, tuple]] = {
    "state_relations": {
        "subject": ("entity",),
        "relation": ("enum", ["adjacent", "contained", "aligned", "overlapping",
                              "touching", "connected", "on", "other"]),
        "object": ("entity",),
    },
    "quantified_object_conditions": {
        "subject": ("entity",),
        "quantifier": ("enum", ["all", "some", "none", "exactly_n"]),
        "n": ("int",),          # null unless quantifier == exactly_n — see CONDITIONAL_FIELDS
        "condition": ("entity",),
    },
    "counts": {
        "counted": ("entity",),
        "comparator": ("enum", ["at_least", "exactly", "at_most"]),
        "target_count": ("int",),
    },
    "region_membership": {
        "subject": ("entity",),
        "region": ("entity",),
        "membership": ("enum", ["inside", "outside"]),
    },
    "symmetry_and_template_match": {
        "scope": ("entity",),
        "pattern": ("entity",),
    },
    "all_instances_transformed": {
        "subject": ("entity",),
        "transformation": ("entity",),
    },
    "event_occurrence": {
        "event": ("entity",),
    },
    "ordered_event_programs": {
        "events_in_order": ("entity_list",),
    },
    "action_conditioned_terminal_triggers": {
        # Model-facing names, mirroring gi1_digest._ENGINE_TO_MODEL. UNDO (ACTION7) is
        # included because the rendered history can show it: measured 13 occurrences across
        # bp35, lf52 and sk48 — all one-shot games, where a rejected parse is unrecoverable.
        "action": ("enum", ["UP", "DOWN", "LEFT", "RIGHT", "SPACE", "MOUSE", "RESET",
                            "UNDO"]),
        "condition": ("entity",),
    },
    "cumulative_counters": {
        "quantity": ("entity",),
        "comparator": ("enum", ["at_least", "exactly", "at_most"]),
        "threshold": ("int",),
    },
}


# ARC colour symbols are CASE-BEARING. The vendored legend
# (inference/utils/grid_utils.ARC_COLOR_LEGEND, checked in selftest) maps 16 distinct
# characters to 16 distinct colours, and FIVE pairs differ only by case:
#   W/w white/light gray · g/G gray/dark gray · B/b black/blue · P/p pink/purple ·
#   R/r red/dark red
# Case-folding a bare symbol therefore merges two colours. Symbols are expanded to their
# legend name BEFORE folding; tokens longer than one character are ordinary English words
# with no case-bearing meaning and are folded normally. Expansion also makes the symbol and
# its English name compare equal ("B square" == "black square"), which is the equivalence
# we do want.
ARC_SYMBOL_NAMES = {
    "W": "white",     "w": "light gray", "g": "gray",     "G": "dark gray",
    "c": "charcoal",  "B": "black",      "M": "magenta",  "P": "pink",
    "R": "red",       "b": "blue",       "S": "sky blue", "Y": "yellow",
    "O": "orange",    "r": "dark red",   "N": "light green", "p": "purple",
}


def normalize_entity(text) -> str:
    """The mechanical normal form for entity fields.

    ORDER-PRESERVING by design. "red becomes blue" and "blue becomes red" are different
    predicates, as are "player reaches target" and "target reaches player"; sorting tokens
    made them compare equal, which manufactures K4 credit out of a reversed relation.
    Word-order variants of the *same* phrase ("blue square" / "square, blue") are near-misses
    and route to the frozen enumerated-equivalence list, which is logged on every invocation
    — the design's declared place for judgement, and the reason this function does not need
    to guess.

    Invariant to punctuation, whitespace, and the case of ordinary words. Deliberately NOT
    invariant to the case of a bare ARC colour symbol.
    """
    out = []
    for tok in "".join(ch if ch.isalnum() else " " for ch in str(text)).split():
        if tok in ARC_SYMBOL_NAMES:
            out.extend(ARC_SYMBOL_NAMES[tok].split())
        else:
            out.append(tok.lower())
    return " ".join(out)


# Fields whose presence depends on another field's value: field -> (controller, value).
# The dependency is BICONDITIONAL — present exactly when the controller holds that value —
# and the controller is compared case-insensitively, the same way the enum check compares it.
# A case-sensitive dependency against a case-insensitive enum silently disagrees with itself:
# "EXACTLY_N" passed the enum and then failed to trigger the requirement.
CONDITIONAL_FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "quantified_object_conditions": {"n": ("quantifier", "exactly_n")},
}


def _entity_problem(v) -> str | None:
    """Why `v` is not usable as an entity value, or None if it is.

    An entity must be human-readable text: it is what the scorer normalizes and what the
    equivalence list adjudicates. A dict, list, number or blank string cannot be either, so
    it is a parse failure to surface now rather than a silent mismatch at scoring time."""
    if not isinstance(v, str):
        return f"expected a short text description, got {type(v).__name__}"
    if not v.strip():
        return "empty string"
    return None


def _field_problems(cls: str, name: str, spec: tuple, v) -> list[str]:
    """Type problems with one present (non-null) field value."""
    kind = spec[0]
    if kind == "enum":
        if str(v).strip().lower() not in [str(a).lower() for a in spec[1]]:
            return [f"{cls}.{name}: {v!r} not in {spec[1]}"]
    elif kind == "int":
        # bool subclasses int, so `isinstance(True, int)` is True: True would otherwise pass
        # as a count and compare equal to 1 in the scorer.
        if isinstance(v, bool) or not isinstance(v, int):
            return [f"{cls}.{name}: not an integer"]
    elif kind == "entity":
        p = _entity_problem(v)
        if p:
            return [f"{cls}.{name}: {p}"]
    elif kind == "entity_list":
        if not isinstance(v, list) or not v:
            return [f"{cls}.{name}: not a non-empty list"]
        return [f"{cls}.{name}[{i}]: {p}"
                for i, element in enumerate(v)
                if (p := _entity_problem(element))]
    return []


def validate_hypothesis(hyp) -> list[str]:
    """Structural problems with one hypothesis (empty list = well-formed).

    Used by the output parser now and the K4 scorer later — same rules by construction.
    TOTAL by contract: the input is model-generated JSON, so any shape must come back as a
    validation error. Raising here would abort a measurement call over one malformed entry
    of a top-three set and lose the other two."""
    if not isinstance(hyp, dict):
        return [f"hypothesis must be an object, got {type(hyp).__name__}"]
    problems = []
    cls = hyp.get("class")
    # `cls in PREDICATE_FIELDS` hashes cls, and model JSON can carry a list or an object there —
    # which would raise TypeError and lose the other two hypotheses of the top-three set, the
    # exact failure the totality contract above exists to prevent.
    if not isinstance(cls, str) or cls not in PREDICATE_FIELDS:
        return [f"unknown class {cls!r}"]
    pred = hyp.get("predicate")
    if not isinstance(pred, dict):
        return ["missing predicate object"]
    conditional = CONDITIONAL_FIELDS.get(cls, {})
    for name, spec in PREDICATE_FIELDS[cls].items():
        v = pred.get(name)
        if name in conditional:
            controller, required = conditional[name]
            got = pred.get(controller)
            active = isinstance(got, str) and got.strip().lower() == required
            if v is None:
                if active:
                    problems.append(f"{cls}.{name}: required when {controller} is {required}")
                continue
            if not active:
                problems.append(f"{cls}.{name}: {v!r} given but {controller} is {got!r}, "
                                f"not {required}")
                continue
        elif v is None:
            problems.append(f"{cls}.{name}: missing")
            continue
        problems.extend(_field_problems(cls, name, spec, v))
    extra = set(pred) - set(PREDICATE_FIELDS[cls])
    if extra:
        problems.append(f"{cls}: unknown fields {sorted(extra)}")
    return problems


def render_field_guide() -> str:
    """The per-class field table embedded in the (b)-(d) prompt.

    CONDITIONAL FIELDS ARE ANNOTATED, and that is not cosmetic. The validator enforces the
    dependency in both directions, so a guide that says "n: integer" under a heading demanding
    exactly the fields of the class instructs the model to emit `n` for `all` — which the parser
    then refuses. A hypothesis rejected for obeying the prompt is a scoring artefact, not a model
    failure, and every one of them would land on quantified_object_conditions: common enough to
    move champion selection and K4 rather than just add noise."""
    lines = ["Per-class predicate fields (your `predicate` object must contain exactly the "
             "fields of its class; a field marked null-unless is omitted or null otherwise):"]
    for cls, fields in PREDICATE_FIELDS.items():
        conditional = CONDITIONAL_FIELDS.get(cls, {})
        parts = []
        for name, spec in fields.items():
            if spec[0] == "enum":
                part = f'{name} ∈ {{{", ".join(spec[1])}}}'
            elif spec[0] == "int":
                part = f"{name}: integer"
            elif spec[0] == "entity_list":
                part = f"{name}: ordered list of short entity descriptions"
            else:
                part = f"{name}: short concrete description (objects by color/shape/role)"
            if name in conditional:
                controller, required = conditional[name]
                part += f" (null unless {controller} is {required})"
            parts.append(part)
        lines.append(f"- {cls}: " + " · ".join(parts))
    return "\n".join(lines)


def selftest() -> int:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from s2_apply_labels import TAXONOMY
    failures = []
    if set(PREDICATE_FIELDS) != set(TAXONOMY):
        failures.append(f"schema/codebook drift: {set(PREDICATE_FIELDS) ^ set(TAXONOMY)}")
    good = {"class": "counts",
            "predicate": {"counted": "yellow 2x2 blocks", "comparator": "exactly",
                          "target_count": 4}}
    if validate_hypothesis(good):
        failures.append(f"valid hypothesis rejected: {validate_hypothesis(good)}")
    bad = {"class": "counts", "predicate": {"counted": "x", "comparator": "roughly",
                                            "target_count": "four"}}
    if len(validate_hypothesis(bad)) != 2:
        failures.append(f"bad hypothesis under-flagged: {validate_hypothesis(bad)}")
    # --- conditional `n`: biconditional, and case-insensitive like the enum it depends on
    def quant(quantifier, n):
        return validate_hypothesis({"class": "quantified_object_conditions",
                                    "predicate": {"subject": "red squares",
                                                  "quantifier": quantifier, "n": n,
                                                  "condition": "turned blue"}})
    for quantifier, n, want_ok, label in [
            ("all", None, True, "n=None with quantifier != exactly_n"),
            ("exactly_n", 3, True, "n=3 with quantifier == exactly_n"),
            ("EXACTLY_N", 3, True, "n=3 with upper-case quantifier"),
            ("exactly_n", None, False, "n=None while quantifier == exactly_n"),
            ("EXACTLY_N", None, False, "n=None while quantifier == EXACTLY_N"),
            ("all", 5, False, "n=5 while quantifier != exactly_n")]:
        got_ok = not quant(quantifier, n)
        if got_ok != want_ok:
            failures.append(f"conditional n: {label} — "
                            f"{'accepted' if got_ok else 'rejected'}, expected the opposite")

    # --- total by contract: model JSON of any shape returns errors, never raises
    for junk in (None, [], "x", 7, {"class": "counts", "predicate": None}):
        try:
            out = validate_hypothesis(junk)
        except Exception as exc:                                    # noqa: BLE001
            failures.append(f"validate_hypothesis({junk!r}) raised {type(exc).__name__}")
            continue
        if not (isinstance(out, list) and out):
            failures.append(f"validate_hypothesis({junk!r}) returned {out!r}, "
                            "expected a non-empty problem list")

    # --- entity normalization: invariant where it should be, strict where it must be
    if normalize_entity("Blue 2x2 Square") != normalize_entity("blue,  2X2  square!"):
        failures.append("normalization not punctuation/case invariant on ordinary words")
    for a, b in [("red becomes blue", "blue becomes red"),
                 ("player reaches target", "target reaches player")]:
        if normalize_entity(a) == normalize_entity(b):
            failures.append(f"order collapse: {a!r} == {b!r}")
    seen = {}
    for ch, name in ARC_SYMBOL_NAMES.items():
        got = normalize_entity(ch)
        if got in seen:
            failures.append(f"ARC symbols {seen[got]!r} and {ch!r} both normalize to {got!r}")
        seen[got] = ch
        if got != name:
            failures.append(f"ARC symbol {ch!r} -> {got!r}, expected {name!r}")
    if normalize_entity("B square") != normalize_entity("black square"):
        failures.append("ARC symbol not equivalent to its own legend name")

    # --- enum case-insensitivity, both directions
    for value in ("UP", "up", " Up "):
        probs = validate_hypothesis({"class": "action_conditioned_terminal_triggers",
                                     "predicate": {"action": value, "condition": "x"}})
        if probs:
            failures.append(f"action={value!r} rejected: {probs}")

    # --- structural strictness (each of these silently passed before)
    for label, pred in [("entity=dict", {"counted": {"a": 1}, "comparator": "exactly",
                                         "target_count": 4}),
                        ("entity=list", {"counted": [1], "comparator": "exactly",
                                         "target_count": 4}),
                        ("entity=number", {"counted": 7, "comparator": "exactly",
                                           "target_count": 4}),
                        ("entity=blank", {"counted": "   ", "comparator": "exactly",
                                          "target_count": 4}),
                        ("int=bool", {"counted": "x", "comparator": "exactly",
                                      "target_count": True})]:
        if not validate_hypothesis({"class": "counts", "predicate": pred}):
            failures.append(f"malformed value accepted: {label}")
    if not validate_hypothesis({"class": "ordered_event_programs",
                                "predicate": {"events_in_order": ["ok", "", {"a": 1}]}}):
        failures.append("entity_list elements not validated")

    # --- the colour table must not drift from the vendored legend
    try:
        vendor = Path(__file__).resolve().parents[2] / "agent/reference/taaf/src/ARC3-Inference"
        if str(vendor) not in sys.path:
            sys.path.insert(0, str(vendor))
        from inference.utils.grid_utils import (ARC_COLOR_CHARS,  # noqa: E402
                                                ARC_COLOR_LEGEND)
        if list(ARC_SYMBOL_NAMES) != list(ARC_COLOR_CHARS):
            failures.append("ARC_SYMBOL_NAMES keys drifted from vendored ARC_COLOR_CHARS")
        legend = dict(part.strip().split("=", 1)
                      for part in ARC_COLOR_LEGEND.split(","))
        if legend != ARC_SYMBOL_NAMES:
            failures.append(f"ARC_SYMBOL_NAMES drifted from vendored legend: "
                            f"{set(legend.items()) ^ set(ARC_SYMBOL_NAMES.items())}")
    except ImportError:
        print("  (note: vendored grid_utils not importable — legend drift check skipped)")

    if failures:
        print(f"SELFTEST FAILED — {len(failures)}:")
        for f in failures:
            print("  " + f)
        return 1
    print("predicate-schema selftest OK: codebook aligned, validation + normalization behave")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
