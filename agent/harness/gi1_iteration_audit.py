#!/usr/bin/env python3
"""Independently audit and summarize the completed GI-1 iteration pass.

This command never queries a model and never selects a champion.  It treats the append-only
raw log as evidence and checks it against the current reviewed packet, prompt, retrieval, and
gold implementations:

* validate the 450-row plan recorded in the log;
* recompute every logged request and compare its canonical SHA-256;
* regenerate both programmatic floors;
* re-score every raw model output against the exact predicate gold;
* report game-balanced metrics and failure breakdowns.

The first run was made under an incomplete implementation freeze.  A clean retrospective audit
can preserve its raw observations for exploratory iteration selection, but it does not rewrite
history or claim that the repaired contract was frozen before those calls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from gi1_experiment_runner import (
    DEFAULT_MEASURED_LOG,
    FLOOR_CONDITIONS,
    MEASURED_CONDITIONS,
    MODEL_CONDITIONS,
    JsonlLog,
    PlanRow,
    _canonical,
    _packet_for,
    _recorded_iteration_plan,
    _request_payload,
)
from gi1_freeze import OUT as FREEZE, require_frozen
from gi1_k4_scorer import load_gold_index, score_raw_output
from gi1_render import assemble
from gi1_retrieval import (
    condition_e_prior,
    condition_f_vote,
    load_or_build_index,
    query,
)

ROOT = Path(__file__).resolve().parents[2]
DRAW = ROOT / "logs/gi1_game_draw.json"
GOLD = ROOT / "logs/gi1_predicate_gold_iteration.json"
OUT = ROOT / "logs/gi1_iteration_audit.json"
FORMAT_VERSION = 1


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True))


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _game_balanced(records: list[dict[str, Any]], metric: str) -> float:
    by_game: dict[str, list[float]] = defaultdict(list)
    for record in records:
        by_game[record["env"]].append(float(record["score"][metric]))
    return _mean(_mean(values) for values in by_game.values())


def _metric_block(records: list[dict[str, Any]], *, model: bool) -> dict[str, Any]:
    block: dict[str, Any] = {
        "n_rows": len(records),
        "n_games": len({record["env"] for record in records}),
        "top1_class_correct": _game_balanced(records, "top1_class_correct"),
        "top3_class_correct": _game_balanced(records, "top3_class_correct"),
    }
    if model:
        block.update(
            {
                "parse_valid": _game_balanced(records, "parse_valid"),
                "top1_field_accuracy": _game_balanced(
                    records, "top1_field_accuracy"
                ),
                "best_top3_field_accuracy": _game_balanced(
                    records, "best_top3_field_accuracy"
                ),
                "top1_predicate_correct": _game_balanced(
                    records, "top1_predicate_correct"
                ),
                "top3_predicate_correct": _game_balanced(
                    records, "top3_predicate_correct"
                ),
            }
        )
    return block


def _summary(latest: dict[str, dict[str, Any]]) -> dict[str, Any]:
    complete = [
        record for record in latest.values() if record.get("status") == "complete"
    ]
    metrics = {}
    for condition in MEASURED_CONDITIONS:
        rows = [record for record in complete if record["condition"] == condition]
        metrics[condition] = _metric_block(
            rows, model=condition in MODEL_CONDITIONS
        )

    checkpoints: dict[str, dict[str, Any]] = {}
    for checkpoint in sorted({record["checkpoint"] for record in complete}):
        checkpoints[checkpoint] = {}
        for condition in MEASURED_CONDITIONS:
            rows = [
                record
                for record in complete
                if record["condition"] == condition
                and record["checkpoint"] == checkpoint
            ]
            checkpoints[checkpoint][condition] = _metric_block(
                rows, model=condition in MODEL_CONDITIONS
            )

    games: dict[str, dict[str, Any]] = {}
    for env in sorted({record["env"] for record in complete}):
        games[env] = {}
        for condition in MEASURED_CONDITIONS:
            rows = [
                record
                for record in complete
                if record["condition"] == condition and record["env"] == env
            ]
            games[env][condition] = _metric_block(
                rows, model=condition in MODEL_CONDITIONS
            )

    parse_problems = Counter()
    field_kinds: dict[str, Counter] = defaultdict(Counter)
    correct_class_hypotheses = 0
    wrong_entity_fields = 0
    for record in complete:
        score = record["score"]
        parse_problems.update(score.get("parse_problems", []))
        hypotheses = score.get("hypotheses", [])
        if hypotheses:
            for field in hypotheses[0]["fields"]:
                field_kinds[field["kind"]]["total"] += 1
                field_kinds[field["kind"]]["correct"] += int(field["correct"])
        for hypothesis in hypotheses:
            if not hypothesis["class_correct"]:
                continue
            correct_class_hypotheses += 1
            wrong_entity_fields += sum(
                not field["correct"]
                for field in hypothesis["fields"]
                if field["kind"] in {"entity", "entity_list"}
            )

    return {
        "metrics": metrics,
        "by_checkpoint": checkpoints,
        "by_game": games,
        "parse_problem_counts": dict(sorted(parse_problems.items())),
        "top1_field_kind_counts": {
            kind: dict(counts) for kind, counts in sorted(field_kinds.items())
        },
        "binding_diagnostics": {
            "correct_class_hypotheses": correct_class_hypotheses,
            "strictly_incorrect_entity_fields": wrong_entity_fields,
        },
    }


def _row_from_record(record: dict[str, Any]) -> PlanRow:
    return PlanRow(
        mode=record["mode"],
        condition=record["condition"],
        env=record["env"],
        guid=record["guid"],
        session_rank=record["session_rank"],
        selection_tier=record["selection_tier"],
        checkpoint=record["checkpoint"],
        checkpoint_step=record["checkpoint_step"],
        ablate_completions=record["ablate_completions"],
        exclusion_reason=record.get("exclusion_reason"),
        contamination=tuple(record.get("contamination", ())),
    )


def audit(
    log_path: Path = DEFAULT_MEASURED_LOG,
    *,
    expected_log_sha256: str | None = None,
    freeze_path: Path = FREEZE,
) -> dict[str, Any]:
    records = JsonlLog(log_path).records()
    draw = json.loads(DRAW.read_text())
    problems: list[str] = []
    try:
        latest = _recorded_iteration_plan(records, draw)
    except ValueError as exc:
        latest = {}
        problems.append(f"recorded plan: {exc}")

    actual_log_sha256 = _sha256_file(log_path)
    if (
        expected_log_sha256 is not None
        and actual_log_sha256 != expected_log_sha256
    ):
        problems.append(
            f"raw log digest {actual_log_sha256} != anchored {expected_log_sha256}"
        )
    if len(records) != 450:
        problems.append(f"raw log has {len(records)} records, expected 450")
    errors = [record for record in records if record.get("status") == "error"]
    if errors:
        problems.append(f"raw log contains {len(errors)} error records")
    modes = {record.get("mode") for record in records}
    if modes != {"measured-iteration"}:
        problems.append(f"raw log modes are {sorted(map(str, modes))}")
    run_freezes = {record.get("freeze_fingerprint") for record in records}
    if len(run_freezes) != 1:
        problems.append(f"raw log has {len(run_freezes)} freeze fingerprints")

    request_hash_mismatches: list[str] = []
    request_regeneration_mismatches: list[str] = []
    score_mismatches: list[str] = []
    floor_output_mismatches: list[str] = []
    row_identity_mismatches: list[str] = []
    gold = load_gold_index()
    library_games = sorted(draw["iteration"] + draw["one_shot"])
    index = load_or_build_index(library_games)

    for record in latest.values():
        row = _row_from_record(record)
        record_id = record["row_id"]
        if row.row_id != record_id:
            row_identity_mismatches.append(record_id)
        if record["status"] == "excluded":
            if "request" in record or "raw_response" in record:
                problems.append(f"excluded row {record_id} contains a model request")
            continue
        if row.condition in MODEL_CONDITIONS:
            logged_request = record.get("request")
            logged_hash = hashlib.sha256(_canonical(logged_request)).hexdigest()
            if logged_hash != record.get("request_sha256"):
                request_hash_mismatches.append(record_id)
            packet = _packet_for(row)
            messages = assemble(
                row.condition,
                packet,
                index=index,
                ablate_completions=False,
                with_image=True,
            )
            regenerated = _request_payload(record["model"], messages)
            if _canonical(regenerated) != _canonical(logged_request):
                request_regeneration_mismatches.append(record_id)
            rescored = _json_value(
                score_raw_output(record.get("raw_output"), gold[row.env]).as_dict()
            )
            if rescored != record.get("score"):
                score_mismatches.append(record_id)
            continue

        packet = _packet_for(row)
        gold_class = draw["primary_class"][row.env]
        if row.condition == "e":
            classes = condition_e_prior(row.env, library_games)
            regenerated_output = {"classes": classes}
        elif row.condition == "f":
            hits, query_type = query(index, packet, ablate_completions=False)
            classes = condition_f_vote(
                index,
                packet,
                library_games,
                ablate_completions=False,
            )
            regenerated_output = {
                "classes": classes,
                "query_type": query_type,
                "retrieved": [
                    {
                        "env": hit["env"],
                        "guid": hit["guid"],
                        "step": hit["step"],
                        "level": hit["level"],
                    }
                    for hit in hits
                ],
            }
        else:  # pragma: no cover - protected by recorded-plan validation
            continue
        regenerated_score = {
            "top1_class_correct": bool(classes and classes[0] == gold_class),
            "top3_class_correct": gold_class in classes,
        }
        if regenerated_output != record.get("raw_output"):
            floor_output_mismatches.append(record_id)
        if regenerated_score != record.get("score"):
            score_mismatches.append(record_id)

    repaired_freeze = require_frozen(freeze_path)
    summary = _summary(latest) if latest else {}
    checks = {
        "recorded_plan_valid": bool(latest),
        "anchored_log_digest_matches": (
            expected_log_sha256 is None
            or actual_log_sha256 == expected_log_sha256
        ),
        "row_identity_mismatches": row_identity_mismatches,
        "request_hash_mismatches": request_hash_mismatches,
        "request_regeneration_mismatches": request_regeneration_mismatches,
        "score_mismatches": score_mismatches,
        "floor_output_mismatches": floor_output_mismatches,
    }
    passed = (
        not problems
        and all(
            not checks[name]
            for name in (
                "row_identity_mismatches",
                "request_hash_mismatches",
                "request_regeneration_mismatches",
                "score_mismatches",
                "floor_output_mismatches",
            )
        )
    )
    return {
        "format_version": FORMAT_VERSION,
        "status": "pass" if passed else "fail",
        "scope": "gi1_iteration_retrospective_integrity_audit",
        "source_log": _display_path(log_path),
        "source_log_sha256": actual_log_sha256,
        "anchored_source_log_sha256": expected_log_sha256,
        "n_log_records": len(records),
        "n_terminal_rows": len(latest),
        "run_freeze_fingerprint": next(iter(run_freezes)) if len(run_freezes) == 1 else None,
        "repaired_freeze_fingerprint": repaired_freeze["contract_fingerprint"],
        "predicate_gold_sha256": _sha256_file(GOLD),
        "retrospective_limitation": (
            "The repaired contract was not the pre-run contract. Passing this audit proves "
            "request and score reproducibility against the reviewed artifacts; it does not "
            "retroactively make the incomplete original freeze pre-registered."
        ),
        "checks": checks,
        "problems": problems,
        **summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=DEFAULT_MEASURED_LOG)
    parser.add_argument("--expected-log-sha256")
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    artifact = audit(
        args.log,
        expected_log_sha256=args.expected_log_sha256,
    )
    if args.write:
        args.output.write_text(json.dumps(artifact, indent=2) + "\n")
        print(
            f"wrote {_display_path(args.output)} — "
            f"{artifact['status']}, {artifact['n_terminal_rows']} rows"
        )
    else:
        print(json.dumps(artifact, indent=2))
    return 0 if artifact["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
