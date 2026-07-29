"""Direct tests for `gi1_predicate_schema` — the GI-1 structured predicate schema.

WHY THIS FILE EXISTS. `gi1_predicate_schema.py --selftest` is real coverage but narrow in a
way that matters, and it is not collected by pytest. It validates a clean hypothesis for
THREE of the ten classes (`counts`, `quantified_object_conditions`,
`action_conditioned_terminal_triggers`); the other seven have no passing example anywhere,
so a field could be renamed in `PREDICATE_FIELDS` and nothing would notice. Of the 28 enum
values across the six enum fields, exactly four are ever passed through the validator —
`exactly`, `all`, `exactly_n`, `UP`. The remaining 24 are strings that have never been
compared against anything.

That is the wrong shape of coverage for this module in particular. The schema is the ONE
source of truth for three consumers that never run together: the (b)-(d) prompt embeds it,
the parameter-gold annotation is built on it, and the K4 scorer compares against it
field-wise. A value the prompt advertises but the validator rejects does not crash — it
silently costs K4 credit on every hypothesis that takes the prompt at its word. And the
header marks the whole table DEV-UNFROZEN until the parameter-gold layer freezes, which
means the names and enums are still moving while all three consumers read them.

Two groups, split by what they need:

  - SYNTHETIC tests build small dicts and need nothing on disk. That is nearly the whole
    file, and it covers every class, every enum value, the conditional-field biconditional,
    the totality contract, and the normalization invariants.
  - VENDOR tests read the ARC colour legend from `agent/reference/` and skip when it is
    absent (mutation sandbox, or a checkout without the vendored tree). The skip is decided
    at import time, before any test runs.

Run:
  .venv/bin/python -m pytest tests/test_gi1_predicate_schema.py -q
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_predicate_schema as S     # noqa: E402
from s2_apply_labels import TAXONOMY  # noqa: E402

# The vendored ARC3-Inference tree is NOT copied into the mutation sandbox, so this is
# resolved once at import and every test that needs it is skipped rather than errored.
# The path is removed again straight away: that tree has several importable top-level
# directories (`scripts`, `viewer`, `configs`) and, left on sys.path, they would shadow
# same-named modules for every other test file sharing the pytest session.
VENDOR = ROOT / "agent" / "reference" / "taaf" / "src" / "ARC3-Inference"
ARC_COLOR_CHARS = ARC_COLOR_LEGEND = None
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))
    try:
        from inference.utils.grid_utils import (ARC_COLOR_CHARS,  # noqa: E402
                                                ARC_COLOR_LEGEND)
    except ImportError:                                             # pragma: no cover
        pass
    finally:
        sys.path.remove(str(VENDOR))

requires_vendor = pytest.mark.skipif(
    ARC_COLOR_CHARS is None,
    reason="vendored ARC3-Inference not present (mutation sandbox / no reference tree)")


# --------------------------------------------------------------------------- valid examples

# One clean hypothesis per class. Kept as a table rather than inline literals because the
# enum, conditional, missing-field and extra-field tests all mutate a copy of it: a class
# added to PREDICATE_FIELDS without an example here fails
# `test_every_class_in_the_schema_has_a_valid_example`, and then everything downstream of it.
VALID: dict[str, dict] = {
    "state_relations": {
        "subject": "red key", "relation": "adjacent", "object": "blue door"},
    "quantified_object_conditions": {
        "subject": "green tiles", "quantifier": "all", "n": None,
        "condition": "lit up"},
    "counts": {
        "counted": "yellow 2x2 blocks", "comparator": "exactly", "target_count": 4},
    "region_membership": {
        "subject": "the player", "region": "the goal box", "membership": "inside"},
    "symmetry_and_template_match": {
        "scope": "the left half", "pattern": "mirror of the right half"},
    "all_instances_transformed": {
        "subject": "grey cells", "transformation": "turned magenta"},
    "event_occurrence": {
        "event": "the door opens"},
    "ordered_event_programs": {
        "events_in_order": ["press the red switch", "press the blue switch", "step out"]},
    "action_conditioned_terminal_triggers": {
        "action": "SPACE", "condition": "standing on the switch"},
    "cumulative_counters": {
        "quantity": "coins collected", "comparator": "at_least", "threshold": 3},
}

ENUM_FIELDS = [(cls, name, spec[1])
               for cls, fields in S.PREDICATE_FIELDS.items()
               for name, spec in fields.items() if spec[0] == "enum"]
ENUM_VALUES = [(cls, name, value) for cls, name, values in ENUM_FIELDS for value in values]
ENTITY_FIELDS = [(cls, name)
                 for cls, fields in S.PREDICATE_FIELDS.items()
                 for name, spec in fields.items() if spec[0] == "entity"]
INT_FIELDS = [(cls, name)
              for cls, fields in S.PREDICATE_FIELDS.items()
              for name, spec in fields.items() if spec[0] == "int"]
REQUIRED_FIELDS = [(cls, name)
                   for cls, fields in S.PREDICATE_FIELDS.items()
                   for name in fields
                   if name not in S.CONDITIONAL_FIELDS.get(cls, {})]


def _hyp(cls: str, **overrides) -> dict:
    """A valid hypothesis for `cls` with fields replaced. `None` sets the field to null;
    use `_without` to remove a key entirely — the schema treats those the same, but only
    one of them is what a model actually emits."""
    pred = copy.deepcopy(VALID[cls])
    pred.update(overrides)
    return {"class": cls, "predicate": pred}


def _without(cls: str, name: str) -> dict:
    hyp = _hyp(cls)
    hyp["predicate"].pop(name)
    return hyp


def _set_enum(cls: str, name: str, value) -> dict:
    """Set an enum field, keeping any field conditional on it consistent. Driven off
    CONDITIONAL_FIELDS so a second conditional field needs no change here."""
    hyp = _hyp(cls, **{name: value})
    for dependent, (controller, required) in S.CONDITIONAL_FIELDS.get(cls, {}).items():
        if controller == name:
            active = str(value).strip().lower() == required
            hyp["predicate"][dependent] = 2 if active else None
    return hyp


def test_every_class_in_the_schema_has_a_valid_example():
    """The guard for this whole file: the tables below are only as complete as VALID is."""
    assert set(VALID) == set(S.PREDICATE_FIELDS)


@pytest.mark.parametrize("cls", sorted(VALID))
def test_a_well_formed_hypothesis_of_every_class_validates_clean(cls):
    assert S.validate_hypothesis(_hyp(cls)) == []


@pytest.mark.parametrize("cls", sorted(VALID))
def test_every_valid_example_carries_exactly_its_class_fields(cls):
    """VALID must not accidentally validate by omitting an optional-looking field — the
    example is also what the enum and strictness tests build on."""
    assert set(VALID[cls]) == set(S.PREDICATE_FIELDS[cls])


def test_the_schema_classes_are_the_codebook_classes():
    """`s2_apply_labels.TAXONOMY` is the codebook the labels were applied under. If the two
    drift, hypotheses are being scored against classes nothing was ever labelled with."""
    assert set(S.PREDICATE_FIELDS) == set(TAXONOMY)


# --------------------------------------------------------------------------- missing / extra

@pytest.mark.parametrize("cls,name", REQUIRED_FIELDS)
def test_every_unconditional_field_is_reported_when_absent(cls, name):
    assert f"{cls}.{name}: missing" in S.validate_hypothesis(_without(cls, name))


@pytest.mark.parametrize("cls,name", REQUIRED_FIELDS)
def test_an_explicit_null_is_reported_the_same_as_an_absent_field(cls, name):
    """Models emit both. A null that passed while an omission failed would make the parser's
    verdict depend on the model's JSON habits rather than on the content."""
    assert f"{cls}.{name}: missing" in S.validate_hypothesis(_hyp(cls, **{name: None}))


def test_an_empty_predicate_reports_every_field_it_is_missing():
    problems = S.validate_hypothesis({"class": "counts", "predicate": {}})
    assert sorted(problems) == ["counts.comparator: missing", "counts.counted: missing",
                                "counts.target_count: missing"]


@pytest.mark.parametrize("cls", sorted(VALID))
def test_an_unknown_field_is_reported_for_every_class(cls):
    problems = S.validate_hypothesis(_hyp(cls, parameter_sketch="free text, rejected in review"))
    assert [p for p in problems if "unknown fields ['parameter_sketch']" in p]


def test_unknown_fields_are_reported_together_and_sorted():
    problems = S.validate_hypothesis(_hyp("counts", zeta=1, alpha=2))
    assert problems == ["counts: unknown fields ['alpha', 'zeta']"]


def test_an_unknown_field_does_not_mask_a_missing_one():
    """Two independent defects in one predicate; reporting only the first sends the model
    round the loop twice on a one-shot budget."""
    hyp = _hyp("counts", zeta=1)
    hyp["predicate"].pop("counted")
    assert S.validate_hypothesis(hyp) == ["counts.counted: missing",
                                          "counts: unknown fields ['zeta']"]


@pytest.mark.parametrize("cls", ["", "Counts", "COUNTS", "outside_taxonomy", "counts ",
                                 None, 7])
def test_an_unrecognized_class_is_refused(cls):
    """Class names are matched exactly — unlike enum VALUES, which fold case. A near-miss
    must not be silently mapped onto a real class."""
    problems = S.validate_hypothesis({"class": cls, "predicate": VALID["counts"]})
    assert problems == [f"unknown class {cls!r}"]


@pytest.mark.parametrize("pred", [None, "counted=blocks", ["counted"], 7, True])
def test_a_predicate_that_is_not_an_object_is_refused(pred):
    assert S.validate_hypothesis({"class": "counts", "predicate": pred}) == [
        "missing predicate object"]


def test_a_hypothesis_with_no_predicate_key_at_all_is_refused():
    assert S.validate_hypothesis({"class": "counts"}) == ["missing predicate object"]


# --------------------------------------------------------------------------- enum values

@pytest.mark.parametrize("cls,name,value", ENUM_VALUES)
def test_every_advertised_enum_value_is_accepted(cls, name, value):
    """Every value the field guide prints, passed through the validator that reads the same
    table. These are two different code paths over one constant and they must agree."""
    assert S.validate_hypothesis(_set_enum(cls, name, value)) == []


@pytest.mark.parametrize("cls,name,value", ENUM_VALUES)
@pytest.mark.parametrize("spell", [str.upper, str.lower, str.title,
                                   lambda v: f"  {v}  "])
def test_enum_values_are_matched_case_insensitively_and_stripped(cls, name, value, spell):
    assert S.validate_hypothesis(_set_enum(cls, name, spell(value))) == []


@pytest.mark.parametrize("cls,name,values", ENUM_FIELDS)
def test_a_value_outside_the_enum_is_refused(cls, name, values):
    problems = S.validate_hypothesis(_set_enum(cls, name, "vaguely_thereabouts"))
    assert f"{cls}.{name}: 'vaguely_thereabouts' not in {values}" in problems


@pytest.mark.parametrize("cls,name,values", ENUM_FIELDS)
def test_a_non_string_enum_value_is_refused_rather_than_coerced(cls, name, values):
    """`str(v).lower()` would happily accept anything whose repr matched; nothing in these
    enums looks like a number, so a number is a parse failure, not a value."""
    assert f"{cls}.{name}: 3 not in {values}" in S.validate_hypothesis(
        _set_enum(cls, name, 3))


@pytest.mark.parametrize("value", ["UP", "DOWN", "LEFT", "RIGHT", "SPACE", "MOUSE",
                                   "RESET", "UNDO"])
def test_the_action_enum_still_carries_the_full_model_facing_action_set(value):
    """Pinned against the enum list rather than derived from it. UNDO in particular is there
    because the rendered history can show it in three one-shot games, where a rejected parse
    cannot be retried — dropping it from the table must fail here, not in the field."""
    assert value in S.PREDICATE_FIELDS["action_conditioned_terminal_triggers"]["action"][1]


# --------------------------------------------------------------------------- conditional `n`

def _quant(quantifier, n):
    return S.validate_hypothesis({"class": "quantified_object_conditions",
                                  "predicate": {"subject": "red squares",
                                                "quantifier": quantifier, "n": n,
                                                "condition": "turned blue"}})


@pytest.mark.parametrize("quantifier,n", [("exactly_n", 3), ("EXACTLY_N", 3),
                                          ("Exactly_N", 3), (" exactly_n ", 3)])
def test_n_is_accepted_when_the_quantifier_asks_for_it_in_any_case(quantifier, n):
    """The dependency folds case the same way the enum check does. A case-sensitive
    dependency against a case-insensitive enum disagrees with itself: `EXACTLY_N` passes the
    enum and then fails to trigger the requirement."""
    assert _quant(quantifier, n) == []


@pytest.mark.parametrize("quantifier", ["exactly_n", "EXACTLY_N", "Exactly_N"])
def test_a_null_n_is_refused_when_the_quantifier_asks_for_it(quantifier):
    assert _quant(quantifier, None) == [
        "quantified_object_conditions.n: required when quantifier is exactly_n"]


@pytest.mark.parametrize("quantifier", ["all", "some", "none"])
def test_a_null_n_is_correct_for_every_other_quantifier(quantifier):
    assert _quant(quantifier, None) == []


@pytest.mark.parametrize("quantifier", ["all", "some", "none", "ALL"])
def test_an_n_given_alongside_another_quantifier_is_refused(quantifier):
    """The other half of the biconditional. `all` with `n=5` is not a harmless extra field —
    it is a hypothesis whose two halves disagree, and the scorer would compare `n`."""
    problems = _quant(quantifier, 5)
    assert problems == [f"quantified_object_conditions.n: 5 given but quantifier is "
                        f"{quantifier!r}, not exactly_n"]


def test_omitting_n_entirely_is_the_same_as_a_null_n():
    assert S.validate_hypothesis({"class": "quantified_object_conditions",
                                  "predicate": {"subject": "a", "quantifier": "all",
                                                "condition": "b"}}) == []
    assert S.validate_hypothesis({"class": "quantified_object_conditions",
                                  "predicate": {"subject": "a", "quantifier": "exactly_n",
                                                "condition": "b"}}) == [
        "quantified_object_conditions.n: required when quantifier is exactly_n"]


def test_a_present_n_is_still_type_checked_when_the_quantifier_activates_it():
    """The conditional branch must fall through to the int check, not return early."""
    assert _quant("exactly_n", "three") == ["quantified_object_conditions.n: not an integer"]


def test_an_unusable_quantifier_reports_both_the_enum_and_the_dependency():
    problems = _quant("roughly", 3)
    assert len(problems) == 2
    assert any("not in ['all', 'some', 'none', 'exactly_n']" in p for p in problems)
    assert any("given but quantifier is 'roughly'" in p for p in problems)


def test_the_only_conditional_field_is_the_one_the_tests_above_cover():
    """CONDITIONAL_FIELDS is unfrozen. A second entry needs its own biconditional tests, so
    it fails here rather than arriving untested."""
    assert S.CONDITIONAL_FIELDS == {
        "quantified_object_conditions": {"n": ("quantifier", "exactly_n")}}


# --------------------------------------------------------------------------- totality

@pytest.mark.parametrize("junk", [None, [], "x", 7, 3.5, True, (), set(),
                                  {"class": "counts", "predicate": None}])
def test_model_json_of_any_shape_returns_problems_and_never_raises(junk):
    """TOTAL by contract. The input is model-generated JSON and a hypothesis arrives as one
    of a top-three set: raising would abort the measurement call and lose the other two. An
    exception here IS the failure — it does not need asserting separately."""
    problems = S.validate_hypothesis(junk)
    assert isinstance(problems, list) and problems


@pytest.mark.parametrize("cls", [[], {}, ["counts"], {"name": "counts"}])
def test_an_unhashable_class_value_is_reported_rather_than_raising(cls):
    """A dict membership test hashes its left operand, so an unhashable `class` straight from
    model JSON raised TypeError and took the other two hypotheses of the set down with it."""
    assert S.validate_hypothesis({"class": cls, "predicate": {}})


# --------------------------------------------------------------------------- colour symbols

@pytest.mark.parametrize("symbol,name", sorted(S.ARC_SYMBOL_NAMES.items()))
def test_every_arc_symbol_normalizes_to_its_legend_name(symbol, name):
    assert S.normalize_entity(symbol) == name


def test_the_sixteen_arc_symbols_stay_sixteen_distinct_colours():
    """Case-folding a bare symbol merges five pairs of colours. This is the assertion that
    catches a `.lower()` added anywhere upstream of the expansion."""
    normalized = [S.normalize_entity(ch) for ch in S.ARC_SYMBOL_NAMES]
    assert len(set(normalized)) == 16


@pytest.mark.parametrize("upper,upper_name,lower,lower_name", [
    ("W", "white", "w", "light gray"),
    ("G", "dark gray", "g", "gray"),
    ("B", "black", "b", "blue"),
    ("P", "pink", "p", "purple"),
    ("R", "red", "r", "dark red"),
])
def test_the_five_case_bearing_pairs_do_not_collapse(upper, upper_name, lower, lower_name):
    """Spelled out rather than looped over the table, so renaming a colour IN the table
    cannot quietly make this test agree with itself."""
    assert S.normalize_entity(upper) == upper_name
    assert S.normalize_entity(lower) == lower_name
    assert S.normalize_entity(upper) != S.normalize_entity(lower)


@pytest.mark.parametrize("symbol,name", sorted(S.ARC_SYMBOL_NAMES.items()))
def test_a_bare_symbol_compares_equal_to_its_english_name(symbol, name):
    """The equivalence we DO want: "B square" == "black square", so a model that writes the
    grid character and a gold that writes the colour word score the same."""
    assert S.normalize_entity(f"{symbol} square") == S.normalize_entity(f"{name} square")


def test_a_multi_character_token_is_folded_even_where_it_shares_a_symbols_letter():
    """Only single-character tokens are case-bearing; "RED" is an ordinary English word and
    must not be treated as the symbol `R`."""
    assert S.normalize_entity("RED block") == S.normalize_entity("red block")
    assert S.normalize_entity("Blue") == S.normalize_entity("blue") == "blue"
    assert S.normalize_entity("R block") != S.normalize_entity("r block")


# --------------------------------------------------------------------------- normalization

@pytest.mark.parametrize("a,b", [
    ("red becomes blue", "blue becomes red"),
    ("player reaches target", "target reaches player"),
    ("R becomes b", "b becomes R"),
    ("key opens door", "door opens key"),
])
def test_token_order_is_preserved_so_a_reversed_relation_does_not_score(a, b):
    """Sorting the tokens made these compare equal, which manufactures K4 credit out of a
    reversed relation — the exact direction of error a scorer must never have."""
    assert S.normalize_entity(a) != S.normalize_entity(b)


@pytest.mark.parametrize("a,b", [
    ("Blue 2x2 Square", "blue,  2X2  square!"),
    ("the PLAYER", "  the player  "),
    ("red-key", "red key"),
    ("moves left; then up", "moves left then up"),
])
def test_punctuation_whitespace_and_ordinary_word_case_are_invariant(a, b):
    assert S.normalize_entity(a) == S.normalize_entity(b)


def test_a_word_order_variant_of_the_same_phrase_is_left_as_a_near_miss():
    """Not a bug: "blue square" / "square, blue" route to the frozen enumerated-equivalence
    list, which is logged on every invocation. Guessing here would remove the judgement from
    the place the design put it."""
    assert S.normalize_entity("blue square") != S.normalize_entity("square, blue")


@pytest.mark.parametrize("value,expected", [(7, "7"), (None, "none"), (["W", "b"], "white blue")])
def test_normalization_coerces_rather_than_raising_on_non_text(value, expected):
    """It is called on both sides of a K4 comparison, including on gold that predates a
    schema change; a raise there loses the whole item."""
    assert S.normalize_entity(value) == expected


# --------------------------------------------------------------------------- type strictness

@pytest.mark.parametrize("bad,fragment", [
    ({"a": 1}, "expected a short text description, got dict"),
    (["a"], "expected a short text description, got list"),
    (7, "expected a short text description, got int"),
    (3.5, "expected a short text description, got float"),
    (True, "expected a short text description, got bool"),
    ("", "empty string"),
    ("   ", "empty string"),
    ("\t\n", "empty string"),
])
def test_an_entity_that_is_not_readable_text_is_refused(bad, fragment):
    """An entity is what the scorer normalizes and what the equivalence list adjudicates.
    A dict or a number can be neither, so it is a parse failure now rather than a silent
    mismatch at scoring time."""
    problems = S.validate_hypothesis(_hyp("counts", counted=bad))
    assert problems == [f"counts.counted: {fragment}"]


@pytest.mark.parametrize("cls,name", ENTITY_FIELDS)
def test_every_entity_field_in_the_schema_rejects_a_structured_value(cls, name):
    problems = S.validate_hypothesis(_hyp(cls, **{name: {"a": 1}}))
    assert f"{cls}.{name}: expected a short text description, got dict" in problems


def _int_hyp(cls: str, name: str, value) -> dict:
    """An otherwise-valid hypothesis carrying `value` in an int field. A conditional int
    needs its controller switched on first, or it is skipped before it is ever typed."""
    overrides = {name: value}
    for dependent, (controller, required) in S.CONDITIONAL_FIELDS.get(cls, {}).items():
        if dependent == name:
            overrides[controller] = required
    return _hyp(cls, **overrides)


@pytest.mark.parametrize("cls,name", INT_FIELDS)
@pytest.mark.parametrize("bad", [True, False])
def test_every_int_field_rejects_a_bool(cls, name, bad):
    """bool subclasses int, so an unguarded `isinstance(v, int)` accepts True as a count and
    compares equal to 1 in the scorer — the same subclass trap `gi1_packets` has in
    `normalize_action_id`."""
    assert f"{cls}.{name}: not an integer" in S.validate_hypothesis(
        _int_hyp(cls, name, bad))


@pytest.mark.parametrize("cls,name", INT_FIELDS)
@pytest.mark.parametrize("bad", ["four", "4", 4.0, ["4"], {"n": 4}])
def test_every_int_field_rejects_a_non_integer(cls, name, bad):
    """"4" is the one that matters: a JSON-quoted count reads correctly to a human and
    compares unequal to 4 in a field-wise scorer."""
    assert f"{cls}.{name}: not an integer" in S.validate_hypothesis(
        _int_hyp(cls, name, bad))


@pytest.mark.parametrize("cls,name", INT_FIELDS)
@pytest.mark.parametrize("good", [0, -1, 4, 10 ** 6])
def test_every_int_field_accepts_a_plain_integer(cls, name, good):
    assert S.validate_hypothesis(_int_hyp(cls, name, good)) == []


@pytest.mark.parametrize("bad", ["press red", {"0": "press red"}, 7, True,
                                 ("press red",), []])
def test_an_ordered_program_that_is_not_a_non_empty_list_is_refused(bad):
    """A tuple is included deliberately: JSON cannot produce one, but the gold layer is
    Python and an ordered sequence that is not a `list` must not slip through."""
    assert S.validate_hypothesis(_hyp("ordered_event_programs", events_in_order=bad)) == [
        "ordered_event_programs.events_in_order: not a non-empty list"]


def test_bad_elements_of_an_ordered_program_are_reported_with_their_index():
    """The index is the whole point — "one of your events is malformed" is not actionable
    against a list the model has to reissue."""
    problems = S.validate_hypothesis(_hyp(
        "ordered_event_programs", events_in_order=["press red", "", {"a": 1}, 3, "step out"]))
    assert problems == [
        "ordered_event_programs.events_in_order[1]: empty string",
        "ordered_event_programs.events_in_order[2]: expected a short text description, got dict",
        "ordered_event_programs.events_in_order[3]: expected a short text description, got int",
    ]


def test_a_single_element_ordered_program_is_accepted():
    """Boundary: non-empty means one, not two. An ordering of one event is degenerate but
    well-formed, and rejecting it would push the model to invent a second."""
    assert S.validate_hypothesis(_hyp("ordered_event_programs",
                                      events_in_order=["press red"])) == []


# --------------------------------------------------------------------------- field guide

def _guide_line(cls: str) -> str:
    """The guide's line for one class. Asserting against the whole guide would let a value
    printed under a DIFFERENT class satisfy the check — and the two comparator fields carry
    identical value sets, so that is not a hypothetical."""
    return next(ln for ln in S.render_field_guide().splitlines()
                if ln.startswith(f"- {cls}:"))


@pytest.mark.parametrize("cls", sorted(S.PREDICATE_FIELDS))
def test_the_field_guide_names_every_class(cls):
    assert _guide_line(cls)


@pytest.mark.parametrize("cls,name,value", ENUM_VALUES)
def test_the_field_guide_prints_every_enum_value_the_validator_accepts(cls, name, value):
    """The prompt and the validator read one table by construction. This asserts they still
    do — a value dropped from the guide is a value the model never learns it may use, and a
    value present in the guide but not the enum is one the parser will reject."""
    assert value in _guide_line(cls)


@pytest.mark.parametrize("cls,name", ENTITY_FIELDS + INT_FIELDS)
def test_the_field_guide_names_every_non_enum_field(cls, name):
    assert name in _guide_line(cls)


@pytest.mark.parametrize("cls", sorted(S.PREDICATE_FIELDS))
def test_the_field_guide_lists_a_class_exactly_once(cls):
    lines = [ln for ln in S.render_field_guide().splitlines() if ln.startswith(f"- {cls}:")]
    assert len(lines) == 1


def test_the_field_guide_tells_the_model_the_field_set_is_exact():
    """The extra-field check refuses anything outside the class's fields, so the guide has
    to say so — otherwise the parser rejects a hypothesis the prompt permitted."""
    assert "exactly the fields of its class" in S.render_field_guide()


@pytest.mark.parametrize("cls,name,controller,required", [
    (cls, name, controller, required)
    for cls, fields in S.CONDITIONAL_FIELDS.items()
    for name, (controller, required) in fields.items()])
def test_the_guide_states_the_condition_for_every_conditional_field(cls, name, controller,
                                                                   required):
    """The prompt and the validator have to agree about when a field may appear. The guide's
    heading demands exactly the fields of the class, so an unannotated `n: integer` instructs
    the model to emit n for `all` — which the validator then refuses. That rejection is a
    scoring artefact rather than a model failure, and it lands entirely on one class, which is
    how it would reach champion selection and K4 instead of averaging out."""
    assert f"null unless {controller} is {required}" in _guide_line(cls)


def test_a_hypothesis_built_by_obeying_the_guide_is_accepted_for_every_quantifier():
    """The round trip the test above only implies: follow the annotation literally for each
    value of the controlling enum and the validator must accept the result."""
    for quantifier in S.PREDICATE_FIELDS["quantified_object_conditions"]["quantifier"][1]:
        predicate = {"subject": "red squares", "quantifier": quantifier,
                     "condition": "turned blue"}
        if quantifier == "exactly_n":
            predicate["n"] = 3
        assert S.validate_hypothesis({"class": "quantified_object_conditions",
                                      "predicate": predicate}) == []


def test_the_guide_describes_an_ordered_program_as_a_sequence_not_a_single_entity():
    """`events_in_order` is the only entity_list field in the codebook and it is what carries
    the Order goal family. Described like a plain entity, the model emits one string where the
    validator demands a list, and the hypothesis is refused for a fault of the prompt. The
    assertion is on the distinction, not the wording, which is still DEV-UNFROZEN."""
    listish = _guide_line("ordered_event_programs")
    entityish = _guide_line("event_occurrence")
    assert "list" in listish
    assert "list" not in entityish


# --------------------------------------------------------------------------- vendored legend

@requires_vendor
def test_the_symbol_table_keys_match_the_vendored_char_order():
    assert "".join(S.ARC_SYMBOL_NAMES) == ARC_COLOR_CHARS


@requires_vendor
def test_the_symbol_table_matches_the_vendored_legend_exactly():
    """The legend is what the grid renderer actually prints to the model. If this table
    drifts from it, every colour entity is normalized to the wrong name and the drift is
    invisible — nothing crashes, K4 just quietly stops matching."""
    legend = dict(part.strip().split("=", 1) for part in ARC_COLOR_LEGEND.split(","))
    assert legend == S.ARC_SYMBOL_NAMES
