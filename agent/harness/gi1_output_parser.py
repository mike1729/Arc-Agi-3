#!/usr/bin/env python3
"""Strict parser for GI-1 conditions (b)-(d) model output.

The prompt asks for JSON only.  "Strict" here means the measurement accepts exactly that
contract rather than repairing common model output:

* no Markdown fence, prefix, suffix, trailing JSON value, NaN, or Infinity;
* no duplicate key at any nesting depth (``json.loads`` otherwise keeps the last value);
* exactly two top-level keys;
* exactly three hypothesis objects, in list order, ranked 1/2/3;
* exactly the five declared keys per hypothesis;
* non-empty evidence and probe text;
* every ``class``/``predicate`` pair valid under ``gi1_predicate_schema``.

The parser is total over arbitrary model output.  It returns problems rather than raising, and
returns no value when any problem exists.  The K4 scorer treats that invalid result as an
incorrect prediction, never as a row to exclude.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from gi1_predicate_schema import validate_hypothesis

TOP_LEVEL_KEYS = {"hypotheses", "discriminating_probe"}
HYPOTHESIS_KEYS = {
    "rank",
    "class",
    "predicate",
    "evidence_for",
    "evidence_against",
}
N_HYPOTHESES = 3


class _DuplicateKey(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise _DuplicateKey(f"duplicate key {key!r}")
        out[key] = value
    return out


def _reject_nonfinite(token: str) -> None:
    raise ValueError(f"non-finite number {token}")


@dataclass(frozen=True)
class ParseResult:
    value: dict[str, Any] | None
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.value is not None and not self.problems


def _key_problems(value: Any, expected: set[str], where: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{where}: expected an object"]
    problems = []
    if missing := expected - set(value):
        problems.append(f"{where}: missing keys {sorted(missing)}")
    if extra := set(value) - expected:
        problems.append(f"{where}: unknown keys {sorted(extra)}")
    return problems


def _nonempty_text(value: Any, where: str) -> list[str]:
    if not isinstance(value, str):
        return [f"{where}: expected text"]
    if not value.strip():
        return [f"{where}: empty text"]
    return []


def validate_decoded_output(value: Any) -> tuple[str, ...]:
    """Validate an already-decoded value against the output envelope."""
    problems = _key_problems(value, TOP_LEVEL_KEYS, "output")
    if not isinstance(value, dict):
        return tuple(problems)

    hypotheses = value.get("hypotheses")
    if not isinstance(hypotheses, list):
        problems.append("output.hypotheses: expected a list")
    else:
        if len(hypotheses) != N_HYPOTHESES:
            problems.append(
                f"output.hypotheses: expected exactly {N_HYPOTHESES}, "
                f"got {len(hypotheses)}"
            )
        for index, hypothesis in enumerate(hypotheses):
            where = f"output.hypotheses[{index}]"
            problems.extend(_key_problems(hypothesis, HYPOTHESIS_KEYS, where))
            if not isinstance(hypothesis, dict):
                continue
            expected_rank = index + 1
            rank = hypothesis.get("rank")
            if isinstance(rank, bool) or not isinstance(rank, int):
                problems.append(f"{where}.rank: expected integer {expected_rank}")
            elif rank != expected_rank:
                problems.append(
                    f"{where}.rank: expected {expected_rank} in list order, got {rank}"
                )
            candidate = {
                "class": hypothesis.get("class"),
                "predicate": hypothesis.get("predicate"),
            }
            for issue in validate_hypothesis(candidate):
                problems.append(f"{where}: {issue}")
            problems.extend(
                _nonempty_text(hypothesis.get("evidence_for"), f"{where}.evidence_for")
            )
            problems.extend(
                _nonempty_text(
                    hypothesis.get("evidence_against"), f"{where}.evidence_against"
                )
            )

    problems.extend(
        _nonempty_text(
            value.get("discriminating_probe"), "output.discriminating_probe"
        )
    )
    return tuple(problems)


def parse_model_output(raw: Any) -> ParseResult:
    """Parse one model response without repair or exceptions."""
    if not isinstance(raw, str):
        return ParseResult(None, (f"output: expected text, got {type(raw).__name__}",))
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, _DuplicateKey, ValueError, RecursionError) as exc:
        return ParseResult(None, (f"output: invalid strict JSON: {exc}",))

    problems = validate_decoded_output(value)
    if problems:
        return ParseResult(None, problems)
    return ParseResult(value, ())
