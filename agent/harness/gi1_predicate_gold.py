#!/usr/bin/env python3
"""Validate GI-1's normalized predicate gold.

The gold artifact is deliberately small: one source-grounded predicate template for each of
the six iteration games.  It is not inferred from replay frequency or model output.  Each row
is tied back to the already packet-verified S2 source annotation and to the sole
``self.next_level()`` site in that game's source.

Scope is a gate, not documentation:

* the record set must equal ``logs/gi1_game_draw.json::iteration``;
* reserved and one-shot games are rejected;
* every predicate must validate against ``gi1_predicate_schema``;
* the class, source path, advance line, packet digest, and source digest must reproduce the
  existing S2 annotation.

The artifact is ``frozen`` together with the prompt, schema, parser, scorer, digest, and
retrieval specification before the measured 27B iteration pass.

Run:
  .venv/bin/python agent/harness/gi1_predicate_gold.py --verify

A fresh checkout does not contain the ignored competition sources or S2 label artifact.
Verification reports each missing input as a problem and exits nonzero; it never treats a
partial provenance check as success.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from gi1_predicate_schema import (
    ARC_SYMBOL_NAMES,
    CONDITIONAL_FIELDS,
    PREDICATE_FIELDS,
    validate_hypothesis,
)

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "logs" / "gi1_predicate_gold_iteration.json"
DRAW = ROOT / "logs" / "gi1_game_draw.json"
LABELS = ROOT / "logs" / "s2_goal_predicates_labelled.json"

FORMAT_VERSION = 1
CURRENT_STATUS = "frozen"
TOP_LEVEL_KEYS = {
    "format_version",
    "status",
    "scope",
    "draw_file",
    "labels_file",
    "schema",
    "equivalence_cases",
    "records",
}
RECORD_KEYS = {
    "env",
    "hypothesis",
    "summary",
    "provenance",
}
PROVENANCE_KEYS = {
    "source",
    "source_sha256",
    "advance_line",
    "enclosing_function",
    "primary_label",
    "packet_digest",
    "packet_verified",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def schema_fingerprint() -> str:
    """Fingerprint every table that changes validation or mechanical normalization."""
    contract = {
        "predicate_fields": PREDICATE_FIELDS,
        "conditional_fields": CONDITIONAL_FIELDS,
        "arc_symbol_names": ARC_SYMBOL_NAMES,
    }
    return hashlib.sha256(_canonical(contract)).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _exact_keys(value: Any, expected: set[str], where: str) -> list[str]:
    if not isinstance(value, dict):
        return [f"{where}: expected an object"]
    actual = set(value)
    problems = []
    if missing := expected - actual:
        problems.append(f"{where}: missing keys {sorted(missing)}")
    if extra := actual - expected:
        problems.append(f"{where}: unknown keys {sorted(extra)}")
    return problems


def _safe_source(root: Path, env: str, source: Any) -> tuple[Path | None, list[str]]:
    """Resolve an iteration source without accepting absolute paths or traversal."""
    if not isinstance(source, str):
        return None, ["provenance.source: expected a relative path"]
    rel = PurePosixPath(source)
    expected_prefix = PurePosixPath("data", "environment_files", env)
    if rel.is_absolute() or ".." in rel.parts or rel.parts[:3] != expected_prefix.parts:
        return None, [
            f"provenance.source: {source!r} is outside data/environment_files/{env}/"
        ]
    return root.joinpath(*rel.parts), []


def _next_level_lines(source: str) -> tuple[list[int], str | None]:
    """AST line numbers of direct ``self.next_level()`` calls, or a parse problem."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [], f"source is not valid Python: {exc.msg} at line {exc.lineno}"
    lines = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "next_level"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ]
    return sorted(lines), None


def validate_gold(
    gold: Any,
    draw: Any,
    labels: Any,
    *,
    root: Path = ROOT,
    verify_sources: bool = True,
) -> list[str]:
    """Return every reproducibility or schema problem in a gold artifact."""
    problems = _exact_keys(gold, TOP_LEVEL_KEYS, "gold")
    if not isinstance(gold, dict):
        return problems

    if gold.get("format_version") != FORMAT_VERSION:
        problems.append(
            f"gold.format_version: expected {FORMAT_VERSION}, got "
            f"{gold.get('format_version')!r}"
        )
    if gold.get("status") != CURRENT_STATUS:
        problems.append(
            f"gold.status: expected frozen measurement status {CURRENT_STATUS!r}"
        )
    if gold.get("scope") != "iteration":
        problems.append("gold.scope: must be 'iteration'")
    if gold.get("draw_file") != "logs/gi1_game_draw.json":
        problems.append("gold.draw_file: unexpected source")
    if gold.get("labels_file") != "logs/s2_goal_predicates_labelled.json":
        problems.append("gold.labels_file: unexpected source")

    schema = gold.get("schema")
    if not isinstance(schema, dict) or set(schema) != {"module", "fingerprint"}:
        problems.append("gold.schema: expected exactly module and fingerprint")
    else:
        if schema["module"] != "agent/harness/gi1_predicate_schema.py":
            problems.append("gold.schema.module: unexpected schema source")
        expected_fingerprint = schema_fingerprint()
        if schema["fingerprint"] != expected_fingerprint:
            problems.append(
                "gold.schema.fingerprint: schema drift "
                f"(artifact {schema['fingerprint']!r}, current {expected_fingerprint!r})"
            )

    equivalences = gold.get("equivalence_cases")
    if not isinstance(equivalences, list):
        problems.append("gold.equivalence_cases: expected a list")
    elif equivalences:
        problems.append(
            "gold.equivalence_cases: must remain empty until the enumerated-equivalence "
            "contract is implemented and frozen"
        )

    if not isinstance(draw, dict):
        problems.append("draw: expected an object")
        return problems
    iteration = draw.get("iteration")
    reserved = draw.get("reserved")
    one_shot = draw.get("one_shot")
    primary = draw.get("primary_class")
    if not all(isinstance(bucket, list) for bucket in (iteration, reserved, one_shot)):
        problems.append("draw: iteration, reserved, and one_shot must be lists")
        return problems
    if not isinstance(primary, dict):
        problems.append("draw.primary_class: expected an object")
        return problems
    allowed = set(iteration)
    forbidden = set(reserved) | set(one_shot)
    if allowed & forbidden:
        problems.append("draw: iteration overlaps reserved or one_shot")

    if not isinstance(labels, dict) or not isinstance(labels.get("records"), list):
        problems.append("labels.records: expected a list")
        return problems
    labelled: dict[str, dict] = {}
    for label_index, label_record in enumerate(labels["records"]):
        if not isinstance(label_record, dict):
            continue
        label_env = label_record.get("env")
        if not isinstance(label_env, str) or label_env not in allowed:
            continue
        if label_env in labelled:
            problems.append(
                f"labels.records[{label_index}].env: duplicate iteration game {label_env}"
            )
            continue
        labelled[label_env] = label_record

    records = gold.get("records")
    if not isinstance(records, list):
        problems.append("gold.records: expected a list")
        return problems

    seen: set[str] = set()
    for index, record in enumerate(records):
        where = f"gold.records[{index}]"
        problems.extend(_exact_keys(record, RECORD_KEYS, where))
        if not isinstance(record, dict):
            continue
        env = record.get("env")
        if not isinstance(env, str):
            problems.append(f"{where}.env: expected text")
            continue
        if env in seen:
            problems.append(f"{where}.env: duplicate game {env}")
        seen.add(env)
        if env not in allowed:
            bucket = "forbidden reserved/one-shot" if env in forbidden else "outside draw"
            problems.append(f"{where}.env: {env} is {bucket}")

        hypothesis = record.get("hypothesis")
        for issue in validate_hypothesis(hypothesis):
            problems.append(f"{where}.hypothesis: {issue}")
        hypothesis_class = hypothesis.get("class") if isinstance(hypothesis, dict) else None
        draw_class = primary.get(env)
        if not isinstance(draw_class, str):
            problems.append(f"{where}: draw.primary_class has no class for {env}")
        elif hypothesis_class != draw_class:
            problems.append(
                f"{where}.hypothesis.class: {hypothesis_class!r} != "
                f"draw primary {draw_class!r}"
            )
        if not isinstance(record.get("summary"), str) or not record["summary"].strip():
            problems.append(f"{where}.summary: expected non-empty audit text")

        provenance = record.get("provenance")
        problems.extend(_exact_keys(provenance, PROVENANCE_KEYS, f"{where}.provenance"))
        source_record = labelled.get(env)
        if not isinstance(provenance, dict) or source_record is None:
            if source_record is None:
                problems.append(f"{where}: no unique S2 source annotation for {env}")
            continue
        source_label = source_record.get("label")
        if not isinstance(source_label, dict):
            problems.append(f"{where}: malformed S2 label for {env}")
            continue
        source_class = source_label.get("primary")
        if not isinstance(source_class, str):
            problems.append(f"{where}: S2 source annotation has no primary class for {env}")
        else:
            if hypothesis_class != source_class:
                problems.append(
                    f"{where}.hypothesis.class: {hypothesis_class!r} != "
                    f"S2 primary {source_class!r}"
                )
            if isinstance(draw_class, str) and draw_class != source_class:
                problems.append(
                    f"{where}: draw primary {draw_class!r} != S2 primary {source_class!r}"
                )

        expected = {
            "source": source_record.get("source"),
            "advance_line": source_record.get("advance_line"),
            "enclosing_function": source_record.get("enclosing_function"),
            "primary_label": source_label.get("primary"),
            "packet_digest": source_label.get("packet_digest"),
            "packet_verified": source_label.get("packet_verified"),
        }
        for name, wanted in expected.items():
            if provenance.get(name) != wanted:
                problems.append(
                    f"{where}.provenance.{name}: {provenance.get(name)!r} != "
                    f"S2 annotation {wanted!r}"
                )

        source_path, source_problems = _safe_source(root, env, provenance.get("source"))
        problems.extend(f"{where}.{issue}" for issue in source_problems)
        if not verify_sources or source_path is None:
            continue
        if not source_path.is_file():
            problems.append(f"{where}.provenance.source: file not found: {source_path}")
            continue
        try:
            actual_digest = _sha256(source_path)
        except OSError as exc:
            problems.append(f"{where}.provenance.source: cannot read bytes: {exc}")
            continue
        if provenance.get("source_sha256") != actual_digest:
            problems.append(
                f"{where}.provenance.source_sha256: source drift "
                f"(artifact {provenance.get('source_sha256')!r}, current {actual_digest!r})"
            )
        line = provenance.get("advance_line")
        try:
            source_text = source_path.read_text()
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(
                f"{where}.provenance.source: cannot read as UTF-8 Python: {exc}"
            )
            continue
        transition_lines, parse_problem = _next_level_lines(source_text)
        if parse_problem:
            problems.append(f"{where}.provenance.source: {parse_problem}")
        elif (
            isinstance(line, bool)
            or not isinstance(line, int)
            or transition_lines != [line]
        ):
            problems.append(
                f"{where}.provenance.advance_line: expected the sole self.next_level() "
                f"site, found lines {transition_lines}"
            )

    missing = allowed - seen
    extra = seen - allowed
    if missing:
        problems.append(f"gold.records: missing iteration games {sorted(missing)}")
    if extra:
        problems.append(f"gold.records: contains non-iteration games {sorted(extra)}")
    return problems


def verify(
    gold_path: Path = GOLD,
    draw_path: Path = DRAW,
    labels_path: Path = LABELS,
    *,
    root: Path = ROOT,
) -> list[str]:
    inputs = {}
    problems = []
    for name, path in (
        ("gold", gold_path),
        ("draw", draw_path),
        ("labels", labels_path),
    ):
        try:
            inputs[name] = json.loads(path.read_text())
        except FileNotFoundError:
            problems.append(f"{name}: required input not found: {path}")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"{name}: cannot read {path}: {exc}")
    if problems:
        return problems
    return validate_gold(
        inputs["gold"],
        inputs["draw"],
        inputs["labels"],
        root=root,
        verify_sources=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true", help="verify the checked-in artifact")
    args = parser.parse_args()
    if not args.verify:
        parser.error("use --verify; gold annotations are reviewed data, not generated output")
    problems = verify()
    if problems:
        print(f"GI-1 iteration predicate gold FAILED — {len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("GI-1 iteration predicate gold OK — 6 source-grounded predicates, no taint")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
