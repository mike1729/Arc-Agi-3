#!/usr/bin/env python3
"""Mechanical GI-1 K4 scorer over strict condition (b)-(d) output.

Entity comparison uses ``normalize_entity`` from the shared predicate schema; enums compare
case-insensitively; integers compare exactly; entity lists compare element-by-element in
order.  Conditional fields are scored only when active in gold (for example ``n`` only when
the gold quantifier is ``exactly_n``).

An actionable predicate is correct only when its class and every scored gold field are
correct.  Because exact free-text entity equality is deliberately conservative, the scorer
also promotes top-one and best-top-three field accuracy to first-class outputs; those provide
the graded binding signal without pretending a partial predicate is actionable.  Invalid model
JSON produces a normal score with every outcome and field count false/zero and the parse
problems attached: it remains in the denominator.

No semantic equivalence is guessed.  The current gold artifact has an empty, deliberately
unimplemented equivalence list; a non-empty list is refused as configuration drift rather
than silently ignored.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from gi1_output_parser import (
    ParseResult,
    parse_model_output,
    validate_decoded_output,
)
from gi1_predicate_gold import (
    CURRENT_STATUS,
    DRAW,
    FORMAT_VERSION,
    GOLD,
    RECORD_KEYS,
    TOP_LEVEL_KEYS,
    schema_fingerprint,
)
from gi1_predicate_schema import (
    CONDITIONAL_FIELDS,
    PREDICATE_FIELDS,
    normalize_entity,
    validate_hypothesis,
)

SUPPORTED_FIELD_KINDS = {"enum", "int", "entity", "entity_list"}
SCHEMA_FIELD_KINDS = {
    spec[0] for fields in PREDICATE_FIELDS.values() for spec in fields.values()
}
assert SCHEMA_FIELD_KINDS == SUPPORTED_FIELD_KINDS, (
    "K4 scorer field-kind coverage drift: "
    f"schema={sorted(SCHEMA_FIELD_KINDS)}, scorer={sorted(SUPPORTED_FIELD_KINDS)}"
)


@dataclass(frozen=True)
class FieldScore:
    name: str
    kind: str
    candidate: Any
    gold: Any
    correct: bool


@dataclass(frozen=True)
class HypothesisScore:
    rank: int
    candidate_class: str
    gold_class: str
    class_correct: bool
    fields: tuple[FieldScore, ...]
    fields_correct: int
    fields_total: int
    predicate_correct: bool


@dataclass(frozen=True)
class K4Score:
    parse_valid: bool
    parse_problems: tuple[str, ...]
    top1_class_correct: bool
    top3_class_correct: bool
    top1_predicate_correct: bool
    top3_predicate_correct: bool
    top1_fields_correct: int
    top1_fields_total: int
    top1_field_accuracy: float
    best_top3_fields_correct: int
    best_top3_fields_total: int
    best_top3_field_accuracy: float
    hypotheses: tuple[HypothesisScore, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _active_fields(cls: str, predicate: dict[str, Any]) -> list[str]:
    active = []
    conditional = CONDITIONAL_FIELDS.get(cls, {})
    for name in PREDICATE_FIELDS[cls]:
        if name not in conditional:
            active.append(name)
            continue
        controller, required = conditional[name]
        got = predicate.get(controller)
        if isinstance(got, str) and got.strip().lower() == required.lower():
            active.append(name)
    return active


def _field_equal(spec: tuple, candidate: Any, gold: Any) -> bool:
    kind = spec[0]
    if kind == "enum":
        return (
            isinstance(candidate, str)
            and isinstance(gold, str)
            and candidate.strip().lower() == gold.strip().lower()
        )
    if kind == "int":
        return (
            not isinstance(candidate, bool)
            and not isinstance(gold, bool)
            and isinstance(candidate, int)
            and isinstance(gold, int)
            and candidate == gold
        )
    if kind == "entity":
        return (
            isinstance(candidate, str)
            and isinstance(gold, str)
            and normalize_entity(candidate) == normalize_entity(gold)
        )
    if kind == "entity_list":
        return (
            isinstance(candidate, list)
            and isinstance(gold, list)
            and len(candidate) == len(gold)
            and all(
                isinstance(left, str)
                and isinstance(right, str)
                and normalize_entity(left) == normalize_entity(right)
                for left, right in zip(candidate, gold)
            )
        )
    raise ValueError(f"unsupported predicate field kind {kind!r}")


def score_hypothesis(
    candidate: dict[str, Any],
    gold: dict[str, Any],
    *,
    rank: int,
) -> HypothesisScore:
    """Score one already-validated candidate against one validated gold hypothesis."""
    candidate_problems = validate_hypothesis(candidate)
    gold_problems = validate_hypothesis(gold)
    if candidate_problems:
        raise ValueError(f"candidate is not schema-valid: {candidate_problems}")
    if gold_problems:
        raise ValueError(f"gold is not schema-valid: {gold_problems}")

    candidate_class = candidate["class"]
    gold_class = gold["class"]
    class_correct = candidate_class == gold_class
    fields = []
    for name in _active_fields(gold_class, gold["predicate"]):
        spec = PREDICATE_FIELDS[gold_class][name]
        candidate_value = (
            candidate["predicate"].get(name) if class_correct else None
        )
        gold_value = gold["predicate"].get(name)
        fields.append(
            FieldScore(
                name=name,
                kind=spec[0],
                candidate=candidate_value,
                gold=gold_value,
                correct=class_correct
                and _field_equal(spec, candidate_value, gold_value),
            )
        )
    fields_correct = sum(field.correct for field in fields)
    predicate_correct = class_correct and fields_correct == len(fields)
    return HypothesisScore(
        rank=rank,
        candidate_class=candidate_class,
        gold_class=gold_class,
        class_correct=class_correct,
        fields=tuple(fields),
        fields_correct=fields_correct,
        fields_total=len(fields),
        predicate_correct=predicate_correct,
    )


def score_parsed_output(parsed: ParseResult, gold: dict[str, Any]) -> K4Score:
    """Score a parser result. Invalid output is an all-false observed outcome."""
    gold_problems = validate_hypothesis(gold)
    if gold_problems:
        raise ValueError(f"gold is not schema-valid: {gold_problems}")
    fields_total = len(_active_fields(gold["class"], gold["predicate"]))
    if not parsed.ok:
        return K4Score(
            parse_valid=False,
            parse_problems=parsed.problems,
            top1_class_correct=False,
            top3_class_correct=False,
            top1_predicate_correct=False,
            top3_predicate_correct=False,
            top1_fields_correct=0,
            top1_fields_total=fields_total,
            top1_field_accuracy=0.0,
            best_top3_fields_correct=0,
            best_top3_fields_total=fields_total,
            best_top3_field_accuracy=0.0,
            hypotheses=(),
        )

    assert parsed.value is not None
    shape_problems = validate_decoded_output(parsed.value)
    if shape_problems:
        raise ValueError(f"inconsistent ParseResult: {list(shape_problems)}")
    hypotheses = tuple(
        score_hypothesis(
            {"class": item["class"], "predicate": item["predicate"]},
            gold,
            rank=item["rank"],
        )
        for item in parsed.value["hypotheses"]
    )
    top1 = hypotheses[0]
    best = max(hypotheses, key=lambda item: item.fields_correct)
    return K4Score(
        parse_valid=True,
        parse_problems=(),
        top1_class_correct=top1.class_correct,
        top3_class_correct=any(item.class_correct for item in hypotheses),
        top1_predicate_correct=top1.predicate_correct,
        top3_predicate_correct=any(item.predicate_correct for item in hypotheses),
        top1_fields_correct=top1.fields_correct,
        top1_fields_total=top1.fields_total,
        top1_field_accuracy=top1.fields_correct / top1.fields_total,
        best_top3_fields_correct=best.fields_correct,
        best_top3_fields_total=best.fields_total,
        best_top3_field_accuracy=best.fields_correct / best.fields_total,
        hypotheses=hypotheses,
    )


def score_raw_output(raw: Any, gold: dict[str, Any]) -> K4Score:
    return score_parsed_output(parse_model_output(raw), gold)


def load_gold_index(
    path: Path = GOLD,
    *,
    draw_path: Path = DRAW,
) -> dict[str, dict[str, Any]]:
    """Load a publishable scoring layer; source provenance is verified separately.

    This loader intentionally accepts exactly the state that ``validate_gold`` accepts now:
    ``dev_unfrozen`` iteration gold.  The freeze change must widen both together.  Draw
    membership is checked here even though source provenance is checked elsewhere, so a
    scoring caller cannot accidentally admit a reserved or one-shot game.
    """
    try:
        artifact = json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load predicate gold {path}: {exc}") from exc
    if not isinstance(artifact, dict):
        raise ValueError("predicate gold must be an object")
    if set(artifact) != TOP_LEVEL_KEYS:
        raise ValueError("predicate-gold top-level keys do not match the artifact contract")
    if artifact.get("format_version") != FORMAT_VERSION:
        raise ValueError("predicate-gold format version does not match the scorer")
    if artifact.get("status") != CURRENT_STATUS:
        raise ValueError("predicate-gold status does not match the scorer")
    if artifact.get("scope") != "iteration":
        raise ValueError("predicate-gold scope must be iteration")
    schema = artifact.get("schema")
    if (
        not isinstance(schema, dict)
        or set(schema) != {"module", "fingerprint"}
        or schema.get("module") != "agent/harness/gi1_predicate_schema.py"
        or schema.get("fingerprint") != schema_fingerprint()
    ):
        raise ValueError("predicate-gold schema fingerprint does not match the scorer")
    equivalences = artifact.get("equivalence_cases")
    if equivalences != []:
        raise ValueError(
            "predicate-gold equivalence_cases must remain empty until equivalence "
            "adjudication and scoring are implemented"
        )
    records = artifact.get("records")
    if not isinstance(records, list):
        raise ValueError("predicate gold records must be a list")
    index = {}
    for offset, record in enumerate(records):
        if (
            not isinstance(record, dict)
            or set(record) != RECORD_KEYS
            or not isinstance(record.get("env"), str)
        ):
            raise ValueError(f"predicate gold record {offset} has no text env")
        env = record["env"]
        if env in index:
            raise ValueError(f"duplicate predicate gold game {env}")
        hypothesis = record.get("hypothesis")
        problems = validate_hypothesis(hypothesis)
        if problems:
            raise ValueError(f"predicate gold {env} is invalid: {problems}")
        index[env] = hypothesis
    if not index:
        raise ValueError("predicate gold contains no records")
    try:
        draw = json.loads(draw_path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load game draw {draw_path}: {exc}") from exc
    if not isinstance(draw, dict) or not isinstance(draw.get("iteration"), list):
        raise ValueError("game draw must contain an iteration list")
    expected_games = draw["iteration"]
    if (
        any(not isinstance(env, str) for env in expected_games)
        or len(expected_games) != len(set(expected_games))
    ):
        raise ValueError("game draw iteration membership must be unique text game IDs")
    if set(index) != set(expected_games):
        raise ValueError(
            "predicate-gold games do not equal draw iteration membership: "
            f"missing={sorted(set(expected_games) - set(index))}, "
            f"extra={sorted(set(index) - set(expected_games))}"
        )
    return index
