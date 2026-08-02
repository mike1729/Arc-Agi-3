"""Tests for the read-only GI-1 iteration integrity audit."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

VENDOR = ROOT / "agent/reference/taaf/src/ARC3-Inference"
if not (VENDOR / "inference/agent/prompts.py").exists():
    A = None
else:
    import gi1_iteration_audit as A  # noqa: E402

pytestmark = pytest.mark.skipif(A is None, reason="audit needs vendored reference prompts")


def _record(row_id: str, *, status: str = "excluded") -> dict:
    value = {
        "mode": "measured-iteration",
        "condition": "b",
        "env": "aa11",
        "guid": row_id,
        "session_rank": 0,
        "selection_tier": 3,
        "checkpoint": "offset:10",
        "checkpoint_step": None if status == "excluded" else 10,
        "ablate_completions": False,
        "model": "/models/Qwen3.6-27B-8bit",
        "freeze_fingerprint": "old-freeze",
        "status": status,
    }
    if status == "excluded":
        value["exclusion_reason"] = "invalid_checkpoint"
    value["row_id"] = A.PlanRow(
        mode=value["mode"],
        condition=value["condition"],
        env=value["env"],
        guid=value["guid"],
        session_rank=value["session_rank"],
        selection_tier=value["selection_tier"],
        checkpoint=value["checkpoint"],
        checkpoint_step=value["checkpoint_step"],
        ablate_completions=value["ablate_completions"],
        exclusion_reason=value.get("exclusion_reason"),
    ).row_id
    return value


def _audit_fixture(tmp_path: Path, monkeypatch):
    draw_path = tmp_path / "draw.json"
    draw_path.write_text(
        json.dumps(
            {
                "iteration": ["aa11"],
                "one_shot": [],
                "reserved": [],
                "primary_class": {"aa11": "counts"},
            }
        )
    )
    gold_path = tmp_path / "gold.json"
    gold_path.write_text('{"answer":"reviewed"}\n')
    records = [_record(f"excluded-{index}") for index in range(449)]
    model = _record("model", status="complete")
    messages = [{"role": "user", "content": "packet"}]
    payload = A._request_payload(model["model"], messages)
    model.update(
        {
            "request": payload,
            "request_sha256": hashlib.sha256(A._canonical(payload)).hexdigest(),
            "raw_output": "answer",
            "score": {
                "parse_valid": True,
                "parse_problems": [],
                "top1_class_correct": True,
                "top3_class_correct": True,
                "top1_predicate_correct": True,
                "top3_predicate_correct": True,
                "top1_fields_correct": 1,
                "top1_fields_total": 1,
                "top1_field_accuracy": 1.0,
                "best_top3_fields_correct": 1,
                "best_top3_fields_total": 1,
                "best_top3_field_accuracy": 1.0,
                "hypotheses": [],
            },
        }
    )
    records.append(model)
    log_path = tmp_path / "raw.jsonl"
    log_path.write_text("".join(json.dumps(record) + "\n" for record in records))

    monkeypatch.setattr(A, "DRAW", draw_path)
    monkeypatch.setattr(A, "GOLD", gold_path)
    monkeypatch.setattr(
        A,
        "_recorded_iteration_plan",
        lambda rows, draw: {record["row_id"]: record for record in rows},
    )
    monkeypatch.setattr(A, "load_gold_index", lambda: {"aa11": {}})
    monkeypatch.setattr(A, "load_or_build_index", lambda games: [])
    monkeypatch.setattr(A, "_packet_for", lambda row: object())
    monkeypatch.setattr(A, "assemble", lambda *args, **kwargs: messages)
    monkeypatch.setattr(
        A,
        "score_raw_output",
        lambda raw, gold: SimpleNamespace(as_dict=lambda: model["score"]),
    )
    monkeypatch.setattr(
        A,
        "require_frozen",
        lambda path: {"contract_fingerprint": "repaired-freeze"},
    )
    return log_path, model


def test_audit_reproduces_requests_and_scores_without_querying_a_model(
    tmp_path, monkeypatch
):
    log_path, _ = _audit_fixture(tmp_path, monkeypatch)
    digest = hashlib.sha256(log_path.read_bytes()).hexdigest()
    artifact = A.audit(log_path, expected_log_sha256=digest, freeze_path=tmp_path)
    assert artifact["status"] == "pass"
    assert artifact["n_log_records"] == 450
    assert artifact["run_freeze_fingerprint"] == "old-freeze"
    assert artifact["checks"]["request_regeneration_mismatches"] == []
    assert artifact["checks"]["score_mismatches"] == []
    assert artifact["metrics"]["b"]["top1_predicate_correct"] == 1.0


def test_audit_catches_request_and_score_drift(tmp_path, monkeypatch):
    log_path, model = _audit_fixture(tmp_path, monkeypatch)
    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    rows[-1]["request"]["messages"][0]["content"] = "tampered"
    rows[-1]["score"]["top1_predicate_correct"] = False
    log_path.write_text("".join(json.dumps(record) + "\n" for record in rows))
    artifact = A.audit(log_path, freeze_path=tmp_path)
    assert artifact["status"] == "fail"
    assert artifact["checks"]["request_hash_mismatches"] == [model["row_id"]]
    assert artifact["checks"]["request_regeneration_mismatches"] == [model["row_id"]]
    assert artifact["checks"]["score_mismatches"] == [model["row_id"]]


def test_audit_refuses_missing_model_request(tmp_path, monkeypatch):
    log_path, model = _audit_fixture(tmp_path, monkeypatch)
    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    del rows[-1]["request"]
    log_path.write_text("".join(json.dumps(record) + "\n" for record in rows))
    artifact = A.audit(log_path, freeze_path=tmp_path)
    assert artifact["status"] == "fail"
    assert artifact["checks"]["request_hash_mismatches"] == [model["row_id"]]


def test_audit_regenerates_both_programmatic_floors(tmp_path, monkeypatch):
    log_path, _ = _audit_fixture(tmp_path, monkeypatch)
    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    for index, condition in enumerate(("e", "f")):
        record = rows[index]
        record.update(
            {
                "condition": condition,
                "checkpoint_step": 10,
                "status": "complete",
                "model": None,
            }
        )
        record.pop("exclusion_reason")
        record["row_id"] = A.PlanRow(
            mode=record["mode"],
            condition=condition,
            env=record["env"],
            guid=record["guid"],
            session_rank=record["session_rank"],
            selection_tier=record["selection_tier"],
            checkpoint=record["checkpoint"],
            checkpoint_step=10,
            ablate_completions=False,
        ).row_id
    rows[0]["raw_output"] = {"classes": ["counts"]}
    rows[0]["score"] = {
        "top1_class_correct": True,
        "top3_class_correct": True,
    }
    rows[1]["raw_output"] = {
        "classes": ["counts"],
        "query_type": "state",
        "retrieved": [{"env": "bb22", "guid": "g", "step": 3, "level": 1}],
    }
    rows[1]["score"] = {
        "top1_class_correct": True,
        "top3_class_correct": True,
    }
    log_path.write_text("".join(json.dumps(record) + "\n" for record in rows))
    monkeypatch.setattr(A, "condition_e_prior", lambda env, games: ["counts"])
    monkeypatch.setattr(A, "condition_f_vote", lambda *args, **kwargs: ["counts"])
    monkeypatch.setattr(
        A,
        "query",
        lambda *args, **kwargs: (
            [{"env": "bb22", "guid": "g", "step": 3, "level": 1}],
            "state",
        ),
    )
    clean = A.audit(log_path, freeze_path=tmp_path)
    assert clean["status"] == "pass"
    assert clean["checks"]["floor_output_mismatches"] == []
    rows[0]["raw_output"]["classes"] = ["event_occurrence"]
    rows[1]["score"]["top1_class_correct"] = False
    log_path.write_text("".join(json.dumps(record) + "\n" for record in rows))
    drift = A.audit(log_path, freeze_path=tmp_path)
    assert rows[0]["row_id"] in drift["checks"]["floor_output_mismatches"]
    assert rows[1]["row_id"] in drift["checks"]["score_mismatches"]


def test_audit_distinguishes_unanchored_matching_and_wrong_log_digests(
    tmp_path, monkeypatch
):
    log_path, _ = _audit_fixture(tmp_path, monkeypatch)
    unanchored = A.audit(log_path, freeze_path=tmp_path)
    assert unanchored["checks"]["anchored_log_digest_matches"] is True
    wrong = A.audit(
        log_path,
        expected_log_sha256="0" * 64,
        freeze_path=tmp_path,
    )
    assert wrong["checks"]["anchored_log_digest_matches"] is False
    assert wrong["status"] == "fail"


def test_summary_keeps_invalid_parse_rows_in_the_denominator():
    score = {
        "parse_valid": False,
        "parse_problems": ["invalid JSON"],
        "top1_class_correct": False,
        "top3_class_correct": False,
        "top1_predicate_correct": False,
        "top3_predicate_correct": False,
        "top1_field_accuracy": 0.0,
        "best_top3_field_accuracy": 0.0,
        "hypotheses": [],
    }
    latest = {
        "x": {
            "row_id": "x",
            "status": "complete",
            "condition": "b",
            "env": "aa11",
            "checkpoint": "offset:10",
            "score": score,
        }
    }
    summary = A._summary(latest)
    assert summary["metrics"]["b"]["n_rows"] == 1
    assert summary["metrics"]["b"]["parse_valid"] == 0.0
    assert summary["parse_problem_counts"] == {"invalid JSON": 1}


def test_summary_slices_conditions_games_checkpoints_and_binding_fields():
    def record(row_id, condition, env, checkpoint, correct):
        score = {
            "parse_valid": True,
            "parse_problems": [],
            "top1_class_correct": correct,
            "top3_class_correct": correct,
            "top1_predicate_correct": False,
            "top3_predicate_correct": False,
            "top1_field_accuracy": 0.5 if correct else 0.0,
            "best_top3_field_accuracy": 0.5 if correct else 0.0,
            "hypotheses": [
                {
                    "class_correct": correct,
                    "fields": [
                        {
                            "kind": "entity",
                            "correct": False,
                        }
                    ],
                }
            ],
        }
        return {
            "row_id": row_id,
            "status": "complete",
            "condition": condition,
            "env": env,
            "checkpoint": checkpoint,
            "score": score,
        }

    latest = {
        "a": record("a", "b", "aa11", "offset:10", True),
        "b": record("b", "c", "bb22", "completion:1", False),
    }
    summary = A._summary(latest)
    assert summary["metrics"]["b"]["top3_class_correct"] == 1.0
    assert summary["metrics"]["c"]["top3_class_correct"] == 0.0
    assert summary["by_checkpoint"]["offset:10"]["b"]["n_rows"] == 1
    assert summary["by_checkpoint"]["completion:1"]["c"]["n_rows"] == 1
    assert summary["by_game"]["aa11"]["b"]["n_rows"] == 1
    assert summary["by_game"]["bb22"]["c"]["n_rows"] == 1
    assert summary["top1_field_kind_counts"]["entity"] == {
        "total": 2,
        "correct": 0,
    }
    assert summary["binding_diagnostics"] == {
        "correct_class_hypotheses": 1,
        "strictly_incorrect_entity_fields": 1,
    }
