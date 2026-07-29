"""Direct tests for the strict GI-1 condition (b)-(d) JSON parser."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_output_parser as P  # noqa: E402


def _hyp(rank: int, cls: str = "counts", predicate: dict | None = None) -> dict:
    return {
        "rank": rank,
        "class": cls,
        "predicate": predicate
        if predicate is not None
        else {"counted": "blue blocks", "comparator": "exactly", "target_count": 2},
        "evidence_for": f"support for rank {rank}",
        "evidence_against": f"gap for rank {rank}",
    }


def _value() -> dict:
    return {
        "hypotheses": [_hyp(1), _hyp(2), _hyp(3)],
        "discriminating_probe": "press UP once and compare the two predictions",
    }


def _parse(value=None):
    return P.parse_model_output(json.dumps(_value() if value is None else value))


def test_exact_prompt_shape_parses():
    result = _parse()
    assert result.ok
    assert result.problems == ()
    assert result.value == _value()


def test_surrounding_json_whitespace_is_allowed():
    result = P.parse_model_output("\n\t " + json.dumps(_value()) + "  \r\n")
    assert result.ok


@pytest.mark.parametrize("junk", [None, 7, [], {}, b"{}"])
def test_non_text_output_is_a_parse_failure_not_an_exception(junk):
    result = P.parse_model_output(junk)
    assert not result.ok
    assert result.value is None
    assert result.problems and "expected text" in result.problems[0]


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "{",
        "```json\n{}\n```",
        "Here is the answer: {}",
        "{} trailing prose",
        "{} {}",
        '{"hypotheses": NaN, "discriminating_probe": "x"}',
        '{"hypotheses": Infinity, "discriminating_probe": "x"}',
    ],
)
def test_non_strict_json_is_rejected_without_repair(raw):
    result = P.parse_model_output(raw)
    assert not result.ok
    assert result.value is None
    assert "invalid strict JSON" in result.problems[0]


def test_json_decoder_recursion_failure_is_reported_not_raised(monkeypatch):
    def recurse(*args, **kwargs):
        raise RecursionError("decoder nesting limit")

    monkeypatch.setattr(P.json, "loads", recurse)
    result = P.parse_model_output("{}")
    assert not result.ok
    assert "invalid strict JSON" in result.problems[0]


def test_duplicate_top_level_key_is_rejected_instead_of_last_wins():
    raw = (
        '{"hypotheses": [], "hypotheses": [], '
        '"discriminating_probe": "probe"}'
    )
    result = P.parse_model_output(raw)
    assert not result.ok
    assert "duplicate key 'hypotheses'" in result.problems[0]


def test_duplicate_nested_predicate_key_is_rejected():
    raw = json.dumps(_value()).replace(
        '"target_count": 2', '"target_count": 2, "target_count": 3', 1
    )
    result = P.parse_model_output(raw)
    assert not result.ok
    assert "duplicate key 'target_count'" in result.problems[0]


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (lambda value: value.pop("discriminating_probe"), "missing keys"),
        (lambda value: value.update({"commentary": "no"}), "unknown keys"),
    ],
)
def test_top_level_keys_are_exact(mutation, fragment):
    value = _value()
    mutation(value)
    result = _parse(value)
    assert not result.ok
    assert any(fragment in problem for problem in result.problems)


def test_top_level_must_be_an_object():
    result = _parse([])
    assert not result.ok
    assert result.problems == ("output: expected an object",)


@pytest.mark.parametrize("hypotheses", [None, {}, "three"])
def test_hypotheses_must_be_a_list(hypotheses):
    value = _value()
    value["hypotheses"] = hypotheses
    result = _parse(value)
    assert not result.ok
    assert "output.hypotheses: expected a list" in result.problems


@pytest.mark.parametrize("count", [0, 1, 2, 4])
def test_exactly_three_hypotheses_are_required(count):
    value = _value()
    value["hypotheses"] = [_hyp(i + 1) for i in range(count)]
    result = _parse(value)
    assert not result.ok
    assert any("expected exactly 3" in problem for problem in result.problems)


def test_each_hypothesis_must_be_an_object():
    value = _value()
    value["hypotheses"][1] = None
    result = _parse(value)
    assert not result.ok
    assert "output.hypotheses[1]: expected an object" in result.problems


@pytest.mark.parametrize(
    ("mutation", "fragment"),
    [
        (lambda hypothesis: hypothesis.pop("evidence_for"), "missing keys"),
        (lambda hypothesis: hypothesis.update({"confidence": 0.9}), "unknown keys"),
    ],
)
def test_hypothesis_keys_are_exact(mutation, fragment):
    value = _value()
    mutation(value["hypotheses"][0])
    result = _parse(value)
    assert not result.ok
    assert any(fragment in problem for problem in result.problems)


@pytest.mark.parametrize("rank", [None, "1", 1.0, True])
def test_rank_must_be_an_integer_not_bool(rank):
    value = _value()
    value["hypotheses"][0]["rank"] = rank
    result = _parse(value)
    assert not result.ok
    assert any("rank: expected integer 1" in problem for problem in result.problems)


def test_ranks_must_match_list_order():
    value = _value()
    value["hypotheses"][0]["rank"] = 2
    value["hypotheses"][1]["rank"] = 1
    result = _parse(value)
    assert not result.ok
    assert any("expected 1 in list order" in problem for problem in result.problems)
    assert any("expected 2 in list order" in problem for problem in result.problems)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("evidence_for", None),
        ("evidence_for", "   "),
        ("evidence_against", []),
        ("evidence_against", ""),
    ],
)
def test_evidence_fields_are_nonempty_text(field, value):
    output = _value()
    output["hypotheses"][0][field] = value
    result = _parse(output)
    assert not result.ok
    assert any(field in problem for problem in result.problems)


@pytest.mark.parametrize("probe", [None, 4, [], "", " \n "])
def test_discriminating_probe_is_nonempty_text(probe):
    value = _value()
    value["discriminating_probe"] = probe
    result = _parse(value)
    assert not result.ok
    assert any("discriminating_probe" in problem for problem in result.problems)


def test_unknown_class_is_rejected_by_the_shared_schema():
    value = _value()
    value["hypotheses"][0]["class"] = "made_up"
    result = _parse(value)
    assert not result.ok
    assert any("unknown class" in problem for problem in result.problems)


def test_malformed_predicate_is_rejected_by_the_shared_schema():
    value = _value()
    value["hypotheses"][0]["predicate"]["target_count"] = "two"
    result = _parse(value)
    assert not result.ok
    assert any("not an integer" in problem for problem in result.problems)


def test_three_binding_alternatives_may_share_a_class():
    """Top-three means hypotheses, not necessarily three distinct coarse classes."""
    value = _value()
    for rank, hypothesis in enumerate(value["hypotheses"], 1):
        hypothesis["predicate"]["target_count"] = rank
    assert _parse(value).ok


def test_inactive_conditional_field_may_be_omitted():
    value = _value()
    quant = {
        "subject": "movers",
        "quantifier": "all",
        "condition": "on exits",
    }
    value["hypotheses"][0] = _hyp(1, "quantified_object_conditions", quant)
    assert _parse(value).ok
