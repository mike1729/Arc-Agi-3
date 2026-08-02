"""Tests for GI-1 scheduling, execution, raw logging, and champion selection."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

VENDOR = ROOT / "agent/reference/taaf/src/ARC3-Inference"
REQUIRED_VENDOR = (
    VENDOR / "inference/agent/prompts.py",
    VENDOR / "inference/utils/grid_utils.py",
    VENDOR / "inference/utils/segmentation.py",
)
MISSING_VENDOR = [path for path in REQUIRED_VENDOR if not path.exists()]
if MISSING_VENDOR:  # pragma: no cover - guarded for clean publishable checkouts
    R = None
    IMPORT_ERROR = FileNotFoundError(
        "missing vendored reference files: " + ", ".join(map(str, MISSING_VENDOR))
    )
else:
    import gi1_experiment_runner as R  # noqa: E402

    IMPORT_ERROR = None

pytestmark = pytest.mark.skipif(
    R is None,
    reason=f"gi1 runner needs the vendored reference tree: {IMPORT_ERROR}",
)


def _draw(iteration=("aa11",)):
    return {
        "iteration": list(iteration),
        "one_shot": ["bb22"],
        "reserved": ["rr00"],
        "primary_class": {
            "aa11": "counts",
            "bb22": "state_relations",
            "rr00": "event_occurrence",
        },
    }


def _patch_schedule(monkeypatch, *, contamination=()):
    monkeypatch.setattr(
        R,
        "select_sessions",
        lambda env: [{"guid": f"{env}-s", "rank": 0, "tier": 3}],
    )
    monkeypatch.setattr(R, "load_timeline", lambda env, guid: (env, guid))
    monkeypatch.setattr(
        R,
        "checkpoints",
        lambda timeline: {
            "offset:10": None,
            "offset:30": 30,
            "completion:1": 40,
            "completion:2": 50,
            "completion:3": 60,
        },
    )
    monkeypatch.setattr(
        R,
        "extract",
        lambda timeline, checkpoint, step: SimpleNamespace(
            env=timeline[0], checkpoint=checkpoint, step=step
        ),
    )
    monkeypatch.setattr(
        R, "ablation_contamination", lambda packet: list(contamination)
    )


def _row(condition="b", *, excluded=None, ablation=False):
    return R.PlanRow(
        mode="moe-debug",
        condition=condition,
        env="aa11",
        guid="session",
        session_rank=0,
        selection_tier=3,
        checkpoint="completion:1",
        checkpoint_step=10,
        ablate_completions=ablation,
        exclusion_reason=excluded,
    )


def test_plan_rejects_non_iteration_games(monkeypatch):
    _patch_schedule(monkeypatch)
    with pytest.raises(ValueError, match="iteration games only.*bb22"):
        R.plan_rows(
            mode="moe-debug",
            conditions=("b",),
            games=("bb22",),
            draw=_draw(),
        )


@pytest.mark.parametrize(
    ("value", "needle"),
    [
        ([], "missing required"),
        ({"iteration": [], "one_shot": [], "reserved": []}, "missing required"),
        (
            {
                "iteration": "aa11",
                "one_shot": [],
                "reserved": [],
                "primary_class": {},
            },
            "buckets must be lists",
        ),
        (
            {
                "iteration": ["aa11"],
                "one_shot": ["aa11"],
                "reserved": [],
                "primary_class": {},
            },
            "overlap",
        ),
    ],
)
def test_draw_rejects_malformed_or_overlapping_buckets(tmp_path, value, needle):
    path = tmp_path / "draw.json"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match=needle):
        R._draw(path)


@pytest.mark.parametrize("conditions", [(), ("b", "b"), ("z",)])
def test_plan_rejects_empty_duplicate_or_unknown_conditions(monkeypatch, conditions):
    _patch_schedule(monkeypatch)
    with pytest.raises(ValueError, match="conditions|unknown"):
        R.plan_rows(
            mode="moe-debug",
            conditions=conditions,
            draw=_draw(),
        )


def test_plan_refuses_duplicate_row_identities(monkeypatch):
    _patch_schedule(monkeypatch)
    monkeypatch.setattr(R.PlanRow, "row_id", property(lambda self: "same"))
    with pytest.raises(ValueError, match="duplicate identities"):
        R.plan_rows(
            mode="moe-debug",
            conditions=("b", "c"),
            draw=_draw(),
        )


def test_plan_records_invalid_checkpoints_instead_of_silently_dropping(monkeypatch):
    _patch_schedule(monkeypatch)
    rows = R.plan_rows(
        mode="moe-debug",
        conditions=("b", "c"),
        draw=_draw(),
    )
    invalid = [row for row in rows if row.checkpoint == "offset:10"]
    assert len(invalid) == 2
    assert {row.exclusion_reason for row in invalid} == {"invalid_checkpoint"}
    assert {row.checkpoint_step for row in invalid} == {None}


def test_normal_plan_does_not_apply_ablation_contamination(monkeypatch):
    _patch_schedule(monkeypatch, contamination=({"slot": "initial_frame"},))
    rows = R.plan_rows(
        mode="moe-debug",
        conditions=("d",),
        draw=_draw(),
    )
    completion = next(row for row in rows if row.checkpoint == "completion:1")
    assert completion.exclusion_reason is None
    assert completion.contamination == ()


def test_ablation_contamination_excludes_every_arm_before_execution(monkeypatch):
    leak = {"level": 1, "slot": "initial_frame", "step": 1}
    _patch_schedule(monkeypatch, contamination=(leak,))
    rows = R.plan_rows(
        mode="measured-iteration",
        conditions=("d", "f"),
        ablate_completions=True,
        draw=_draw(),
    )
    assert {row.checkpoint for row in rows} == set(R.ABLATION_CHECKPOINTS)
    assert all(row.exclusion_reason == "completion_ablation_contamination" for row in rows)
    assert all(row.contamination == (leak,) for row in rows)


def test_ablation_refuses_conditions_whose_treatment_is_undefined(monkeypatch):
    _patch_schedule(monkeypatch)
    with pytest.raises(ValueError, match="only for conditions d and f"):
        R.plan_rows(
            mode="measured-iteration",
            conditions=("c", "d"),
            ablate_completions=True,
            draw=_draw(),
        )


def test_row_id_is_stable_but_changes_with_the_treatment():
    first = _row()
    same = _row()
    ablated = _row(ablation=True)
    assert first.row_id == same.row_id
    assert first.row_id != ablated.row_id
    assert len(first.row_id) == 24


def test_excluded_row_never_builds_a_packet_or_prompt(monkeypatch):
    monkeypatch.setattr(
        R, "_packet_for", lambda row: (_ for _ in ()).throw(AssertionError("leak"))
    )
    result = R.execute_row(
        _row(excluded="completion_ablation_contamination"),
        model="/models/Qwen3.6-35B-A3B-4bit",
        base_url="http://unused/v1",
        timeout=1,
        index=[],
        library_games=[],
        primary_classes={},
        gold={},
        freeze_fingerprint=None,
        attempt=1,
    )
    assert result["status"] == "excluded"
    assert result["exclusion_reason"] == "completion_ablation_contamination"
    assert "request" not in result


def test_packet_builder_refuses_an_invalid_checkpoint_row():
    with pytest.raises(ValueError, match="has no packet"):
        R._packet_for(
            R.PlanRow(
                mode="moe-debug",
                condition="b",
                env="aa11",
                guid="s",
                session_rank=0,
                selection_tier=3,
                checkpoint="offset:10",
                checkpoint_step=None,
                ablate_completions=False,
            )
        )


def test_model_execution_logs_exact_request_raw_response_output_and_score(monkeypatch):
    packet = object()
    messages = [{"role": "user", "content": "packet"}]
    response = {
        "choices": [{"message": {"content": '{"hypotheses":[]}'}}],
        "usage": {"completion_tokens": 7},
    }
    seen = {}

    monkeypatch.setattr(R, "_packet_for", lambda row: packet)
    monkeypatch.setattr(R, "assemble", lambda *args, **kwargs: messages)
    monkeypatch.setattr(
        R,
        "score_raw_output",
        lambda raw, gold: SimpleNamespace(
            as_dict=lambda: {"parse_valid": False, "top1_field_accuracy": 0.0}
        ),
    )

    def chat(**kwargs):
        seen.update(kwargs)
        return response, 1.25

    result = R.execute_row(
        _row("b"),
        model="/models/Qwen3.6-35B-A3B-4bit",
        base_url="http://model/v1",
        timeout=9,
        index=[],
        library_games=["aa11"],
        primary_classes={"aa11": "counts"},
        gold={"aa11": {"class": "counts", "predicate": {}}},
        freeze_fingerprint=None,
        attempt=2,
        chat=chat,
    )
    assert seen["base_url"] == "http://model/v1"
    assert seen["timeout"] == 9
    assert seen["payload"] == result["request"]
    assert result["request"]["messages"] is messages
    assert result["request"]["temperature"] == 0
    assert result["request"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert result["raw_response"] is response
    assert result["raw_output"] == '{"hypotheses":[]}'
    assert result["score"]["parse_valid"] is False
    assert result["elapsed_seconds"] == 1.25
    assert result["attempt"] == 2
    assert len(result["request_sha256"]) == 64


def test_missing_assistant_content_is_scored_as_raw_none(monkeypatch):
    seen = {}
    monkeypatch.setattr(R, "_packet_for", lambda row: object())
    monkeypatch.setattr(R, "assemble", lambda *args, **kwargs: [])

    def score(raw, gold):
        seen["raw"] = raw
        return SimpleNamespace(as_dict=lambda: {"parse_valid": False})

    monkeypatch.setattr(R, "score_raw_output", score)
    result = R.execute_row(
        _row("c"),
        model="/models/Qwen3.6-35B-A3B-4bit",
        base_url="http://unused/v1",
        timeout=1,
        index=[],
        library_games=[],
        primary_classes={"aa11": "counts"},
        gold={"aa11": {}},
        freeze_fingerprint=None,
        attempt=1,
        chat=lambda **kwargs: ({"choices": []}, 0.1),
    )
    assert seen["raw"] is None
    assert result["status"] == "complete"


def test_model_condition_requires_a_model(monkeypatch):
    monkeypatch.setattr(R, "_packet_for", lambda row: object())
    with pytest.raises(ValueError, match="requires a model"):
        R.execute_row(
            _row("b"),
            model=None,
            base_url="",
            timeout=1,
            index=[],
            library_games=[],
            primary_classes={"aa11": "counts"},
            gold={"aa11": {}},
            freeze_fingerprint=None,
            attempt=1,
        )


def test_execute_row_refuses_an_unknown_condition(monkeypatch):
    monkeypatch.setattr(R, "_packet_for", lambda row: object())
    bad = R.PlanRow(**{**_row("b").__dict__, "condition": "z"})
    with pytest.raises(ValueError, match="unimplemented condition"):
        R.execute_row(
            bad,
            model="/models/Qwen3.6-35B-A3B-4bit",
            base_url="",
            timeout=1,
            index=[],
            library_games=[],
            primary_classes={"aa11": "counts"},
            gold={"aa11": {}},
            freeze_fingerprint=None,
            attempt=1,
        )


def test_condition_e_logs_vote_and_class_scores(monkeypatch):
    monkeypatch.setattr(R, "_packet_for", lambda row: object())
    monkeypatch.setattr(
        R, "condition_e_prior", lambda env, library: ["counts", "state_relations"]
    )
    result = R.execute_row(
        _row("e"),
        model=None,
        base_url="",
        timeout=1,
        index=[],
        library_games=["aa11", "bb22"],
        primary_classes={"aa11": "counts"},
        gold={},
        freeze_fingerprint="freeze",
        attempt=1,
    )
    assert result["raw_output"]["classes"][0] == "counts"
    assert result["score"] == {
        "top1_class_correct": True,
        "top3_class_correct": True,
    }
    assert result["model"] is None


def test_condition_f_logs_query_provenance_and_vote(monkeypatch):
    monkeypatch.setattr(R, "_packet_for", lambda row: object())
    monkeypatch.setattr(
        R,
        "query",
        lambda index, packet, ablate_completions: (
            [{"env": "bb22", "guid": "g", "step": 4, "level": 1}],
            "terminal",
        ),
    )
    monkeypatch.setattr(
        R,
        "condition_f_vote",
        lambda index, packet, library, ablate_completions: [
            "state_relations",
            "counts",
        ],
    )
    result = R.execute_row(
        _row("f"),
        model=None,
        base_url="",
        timeout=1,
        index=[],
        library_games=["aa11", "bb22"],
        primary_classes={"aa11": "counts"},
        gold={},
        freeze_fingerprint="freeze",
        attempt=1,
    )
    assert result["raw_output"]["query_type"] == "terminal"
    assert result["raw_output"]["retrieved"] == [
        {"env": "bb22", "guid": "g", "step": 4, "level": 1}
    ]
    assert not result["score"]["top1_class_correct"]
    assert result["score"]["top3_class_correct"]


def test_jsonl_log_round_trips_unicode_and_finds_terminal_ids(tmp_path):
    log = R.JsonlLog(tmp_path / "run.jsonl")
    log.append({"row_id": "a", "status": "error", "error": "ż"})
    log.append({"row_id": "a", "status": "complete", "raw_output": "✓"})
    log.append({"row_id": "b", "status": "excluded"})
    assert [record["error"] for record in log.records() if "error" in record] == ["ż"]
    assert log.terminal_ids() == {"a", "b"}
    assert log.attempt_counts() == {"a": 2, "b": 1}


def test_jsonl_log_refuses_a_truncated_or_malformed_line(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text('{"row_id":"a"}\n{"row_id"')
    with pytest.raises(ValueError, match="invalid JSONL"):
        R.JsonlLog(path).records()


def test_jsonl_log_missing_file_is_an_empty_resume_state(tmp_path):
    assert R.JsonlLog(tmp_path / "absent.jsonl").records() == []


def test_jsonl_log_ignores_blank_lines_but_refuses_missing_row_id(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text("\n  \n" + json.dumps({"status": "complete"}) + "\n")
    with pytest.raises(ValueError, match="no text row_id"):
        R.JsonlLog(path).records()


def test_call_chat_refuses_a_non_object_response(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"[]"

    monkeypatch.setattr(R.urllib.request, "urlopen", lambda request, timeout: Response())
    with pytest.raises(RuntimeError, match="must be a JSON object"):
        R.call_chat(base_url="http://model/v1", payload={}, timeout=1)


def test_mode_guard_keeps_moe_out_of_measurement(monkeypatch, tmp_path):
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    with pytest.raises(ValueError, match="measured-iteration requires.*27B-8bit"):
        R._assert_mode(
            mode="measured-iteration",
            model="/models/Qwen3.6-35B-A3B-4bit",
            conditions=R.MEASURED_CONDITIONS,
            ablate_completions=False,
            freeze_path=tmp_path / "freeze.json",
        )


def test_mode_guard_keeps_wrong_models_and_floor_arms_out_of_moe(tmp_path):
    with pytest.raises(ValueError, match="moe-debug requires"):
        R._assert_mode(
            mode="moe-debug",
            model="/models/Qwen3.6-27B-8bit",
            conditions=("b",),
            ablate_completions=False,
            freeze_path=tmp_path,
        )
    with pytest.raises(ValueError, match="prompt conditions b-d only"):
        R._assert_mode(
            mode="moe-debug",
            model="/models/Qwen3.6-35B-A3B-4bit",
            conditions=("b", "e"),
            ablate_completions=False,
            freeze_path=tmp_path,
        )


def test_mode_guard_refuses_unknown_mode(tmp_path):
    with pytest.raises(ValueError, match="unknown mode"):
        R._assert_mode(
            mode="other",
            model="/models/Qwen3.6-27B-8bit",
            conditions=R.MEASURED_CONDITIONS,
            ablate_completions=False,
            freeze_path=tmp_path,
        )


def test_mode_guard_requires_exact_measured_conditions(monkeypatch, tmp_path):
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    with pytest.raises(ValueError, match="conditions are fixed"):
        R._assert_mode(
            mode="measured-iteration",
            model="/models/Qwen3.6-27B-8bit",
            conditions=("b", "c", "d"),
            ablate_completions=False,
            freeze_path=tmp_path / "freeze.json",
        )


def test_mode_guard_returns_the_verified_freeze(monkeypatch, tmp_path):
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    assert (
        R._assert_mode(
            mode="measured-iteration",
            model="/models/Qwen3.6-27B-8bit",
            conditions=R.MEASURED_CONDITIONS,
            ablate_completions=False,
            freeze_path=tmp_path / "freeze.json",
        )
        == "freeze"
    )


def test_existing_log_refuses_cross_mode_or_cross_model_rows():
    base = {
        "condition": "b",
        "mode": "moe-debug",
        "model": "/models/Qwen3.6-35B-A3B-4bit",
        "freeze_fingerprint": None,
    }
    R._validate_existing_log(
        [base],
        mode="moe-debug",
        model="/models/Qwen3.6-35B-A3B-4bit",
        freeze_fingerprint=None,
    )
    with pytest.raises(ValueError, match="belongs to"):
        R._validate_existing_log(
            [{**base, "mode": "measured-iteration"}],
            mode="moe-debug",
            model=base["model"],
            freeze_fingerprint=None,
        )
    with pytest.raises(ValueError, match="different model"):
        R._validate_existing_log(
            [{**base, "model": "/models/wrong"}],
            mode="moe-debug",
            model=base["model"],
            freeze_fingerprint=None,
        )
    with pytest.raises(ValueError, match="different freeze"):
        R._validate_existing_log(
            [{**base, "freeze_fingerprint": "old"}],
            mode="moe-debug",
            model=base["model"],
            freeze_fingerprint=None,
        )


def _run_row(condition: str, checkpoint: str, step: int, *, excluded=None):
    return R.PlanRow(
        mode="moe-debug",
        condition=condition,
        env="aa11",
        guid="s",
        session_rank=0,
        selection_tier=3,
        checkpoint=checkpoint,
        checkpoint_step=step,
        ablate_completions=False,
        exclusion_reason=excluded,
    )


def _patch_run_dependencies(monkeypatch, rows, execute):
    monkeypatch.setattr(R, "_assert_mode", lambda **kwargs: None)
    monkeypatch.setattr(R, "_draw", lambda: _draw())
    monkeypatch.setattr(R, "plan_rows", lambda **kwargs: rows)
    monkeypatch.setattr(R, "load_or_build_index", lambda games, rebuild=False: [])
    monkeypatch.setattr(R, "load_gold_index", lambda: {})
    monkeypatch.setattr(R, "execute_row", execute)


def _run_args(tmp_path, **overrides):
    args = {
        "mode": "moe-debug",
        "model": "/models/Qwen3.6-35B-A3B-4bit",
        "base_url": "http://unused/v1",
        "log_path": tmp_path / "run.jsonl",
        "conditions": ("b",),
        "ablate_completions": False,
        "games": None,
        "timeout": 1,
        "concurrency": 1,
        "limit_model_calls": None,
    }
    args.update(overrides)
    return args


def test_run_validates_concurrency_and_limit_before_loading_data(tmp_path):
    with pytest.raises(ValueError, match="concurrency"):
        R.run(**_run_args(tmp_path, concurrency=0))
    with pytest.raises(ValueError, match="limit_model_calls"):
        R.run(**_run_args(tmp_path, limit_model_calls=0))


def test_run_applies_exact_model_call_limit_and_keeps_exclusions_serial(
    tmp_path, monkeypatch
):
    rows = [
        _run_row("b", "offset:10", 10),
        _run_row("b", "offset:30", 30),
        _run_row("b", "completion:1", 40),
        _run_row("b", "completion:2", None, excluded="invalid_checkpoint"),
    ]
    calls = []

    def execute(row, **kwargs):
        calls.append((row.checkpoint, threading.current_thread().name))
        return {
            "row_id": row.row_id,
            "mode": row.mode,
            "condition": row.condition,
            "model": kwargs["model"],
            "freeze_fingerprint": None,
            "status": "excluded" if row.exclusion_reason else "complete",
        }

    _patch_run_dependencies(monkeypatch, rows, execute)
    summary = R.run(**_run_args(tmp_path, limit_model_calls=1))
    assert {checkpoint for checkpoint, _ in calls} == {
        "offset:10",
        "completion:2",
    }
    exclusion_thread = next(name for checkpoint, name in calls if checkpoint == "completion:2")
    model_threads = [name for checkpoint, name in calls if checkpoint != "completion:2"]
    assert exclusion_thread == threading.current_thread().name
    assert all(name != exclusion_thread for name in model_threads)
    assert summary["complete"] == 1
    assert summary["excluded"] == 1


def test_run_is_fail_fast_on_a_model_error_by_default(tmp_path, monkeypatch):
    rows = [_run_row("b", "offset:10", 10)]

    def execute(row, **kwargs):
        raise RuntimeError("endpoint down")

    _patch_run_dependencies(monkeypatch, rows, execute)
    with pytest.raises(RuntimeError, match="endpoint down"):
        R.run(**_run_args(tmp_path))
    record = R.JsonlLog(tmp_path / "run.jsonl").records()[0]
    assert record["status"] == "error"
    assert record["error_type"] == "RuntimeError"


def test_fail_fast_still_logs_paid_for_inflight_successes(tmp_path, monkeypatch):
    rows = [
        _run_row("b", "offset:10", 10),
        _run_row("b", "offset:30", 30),
    ]
    both_started = threading.Barrier(2)

    def execute(row, **kwargs):
        both_started.wait(timeout=2)
        if row.checkpoint == "offset:10":
            raise RuntimeError("endpoint down")
        time.sleep(0.02)
        return {
            "row_id": row.row_id,
            "mode": row.mode,
            "condition": row.condition,
            "model": kwargs["model"],
            "freeze_fingerprint": None,
            "status": "complete",
        }

    _patch_run_dependencies(monkeypatch, rows, execute)
    with pytest.raises(RuntimeError, match="endpoint down"):
        R.run(**_run_args(tmp_path, concurrency=2))
    records = R.JsonlLog(tmp_path / "run.jsonl").records()
    assert {record["status"] for record in records} == {"error", "complete"}
    assert len(records) == 2


def test_fail_fast_ignores_futures_cancelled_before_they_start(tmp_path, monkeypatch):
    rows = [
        _run_row("b", f"completion:{index}", index)
        for index in range(1, 11)
    ]

    def execute(row, **kwargs):
        if row.checkpoint == "completion:1":
            raise RuntimeError("first call failed")
        time.sleep(0.2)
        return {
            "row_id": row.row_id,
            "mode": row.mode,
            "condition": row.condition,
            "model": kwargs["model"],
            "freeze_fingerprint": None,
            "status": "complete",
        }

    _patch_run_dependencies(monkeypatch, rows, execute)
    with pytest.raises(RuntimeError, match="first call failed"):
        R.run(**_run_args(tmp_path, concurrency=1))
    records = R.JsonlLog(tmp_path / "run.jsonl").records()
    assert records[0]["status"] == "error"
    assert len(records) < len(rows)


def test_completion_ablation_has_a_separate_default_log():
    assert (
        R._resolve_log_path(
            mode="measured-iteration",
            ablate_completions=True,
            explicit=None,
        )
        == R.DEFAULT_ABLATION_LOG
    )
    assert R.DEFAULT_ABLATION_LOG != R.DEFAULT_MEASURED_LOG


def test_completion_ablation_refuses_the_normal_measured_log():
    with pytest.raises(ValueError, match="cannot write the normal measured log"):
        R._resolve_log_path(
            mode="measured-iteration",
            ablate_completions=True,
            explicit=R.DEFAULT_MEASURED_LOG,
        )


def _recorded_plan_fixture():
    rows = []
    for env in ("aa11", "bb22"):
        for rank in range(3):
            guid = f"{env}-s{rank}"
            for checkpoint_index, checkpoint in enumerate(R.NORMAL_CHECKPOINTS):
                step = 10 * (checkpoint_index + 1)
                excluded = checkpoint == "offset:10" and rank == 0
                for condition in R.MEASURED_CONDITIONS:
                    row = R.PlanRow(
                        mode="measured-iteration",
                        condition=condition,
                        env=env,
                        guid=guid,
                        session_rank=rank,
                        selection_tier=3,
                        checkpoint=checkpoint,
                        checkpoint_step=None if excluded else step,
                        ablate_completions=False,
                        exclusion_reason="invalid_checkpoint" if excluded else None,
                    )
                    record = {
                        **row.__dict__,
                        "row_id": row.row_id,
                        "status": "excluded" if excluded else "complete",
                    }
                    if excluded:
                        record["exclusion_reason"] = "invalid_checkpoint"
                    rows.append(record)
    return rows


def test_recorded_plan_is_authoritative_and_requires_matched_arms():
    rows = _recorded_plan_fixture()
    draw = _draw(iteration=("aa11", "bb22"))
    latest = R._recorded_iteration_plan(rows, draw)
    assert len(latest) == 2 * 3 * 5 * 5
    rows.pop()
    with pytest.raises(ValueError, match="has conditions"):
        R._recorded_iteration_plan(rows, draw)


def test_recorded_plan_rejects_ablation_rows_before_selection():
    rows = _recorded_plan_fixture()
    rows[0]["ablate_completions"] = True
    with pytest.raises(ValueError, match="completion-ablation"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))


def test_recorded_plan_rejects_duplicate_terminal_row_ids():
    rows = _recorded_plan_fixture()
    rows[1]["row_id"] = rows[0]["row_id"]
    with pytest.raises(ValueError, match="duplicate terminal row IDs"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))


@pytest.mark.parametrize("iteration", ["aa11", ["aa11", "aa11"], ["aa11", 7]])
def test_recorded_plan_rejects_invalid_frozen_iteration_membership(iteration):
    draw = _draw()
    draw["iteration"] = iteration
    with pytest.raises(ValueError, match="invalid iteration membership"):
        R._recorded_iteration_plan(_recorded_plan_fixture(), draw)


def test_recorded_plan_rejects_unknown_condition_and_checkpoint():
    rows = _recorded_plan_fixture()
    rows[0]["condition"] = "z"
    with pytest.raises(ValueError, match="unknown condition"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))
    rows = _recorded_plan_fixture()
    rows[0]["checkpoint"] = "completion:99"
    with pytest.raises(ValueError, match="unknown checkpoint"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))


def test_recorded_plan_rejects_a_repeated_condition_inside_one_slot():
    rows = _recorded_plan_fixture()
    rows[1]["condition"] = rows[0]["condition"]
    rows[1]["row_id"] = "unique-for-this-test"
    with pytest.raises(ValueError, match="repeats condition"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))


def test_recorded_plan_rejects_bad_exclusion_reason_and_noninteger_step():
    rows = _recorded_plan_fixture()
    slot = [
        row
        for row in rows
        if row["env"] == "aa11"
        and row["guid"] == "aa11-s0"
        and row["checkpoint"] == "offset:10"
    ]
    for row in slot:
        row["exclusion_reason"] = "other"
    with pytest.raises(ValueError, match="invalid exclusion"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))

    rows = _recorded_plan_fixture()
    slot = [
        row
        for row in rows
        if row["env"] == "aa11"
        and row["guid"] == "aa11-s1"
        and row["checkpoint"] == "offset:30"
    ]
    for row in slot:
        row["checkpoint_step"] = True
    with pytest.raises(ValueError, match="no integer checkpoint step"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))


def test_recorded_plan_names_the_game_with_the_wrong_session_count():
    rows = [
        row
        for row in _recorded_plan_fixture()
        if not (row["env"] == "aa11" and row["guid"] == "aa11-s2")
    ]
    with pytest.raises(ValueError, match="game aa11 has 2 sessions"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))


def test_recorded_plan_rejects_a_missing_checkpoint_even_when_slot_count_matches():
    rows = _recorded_plan_fixture()
    changed = [
        row
        for row in rows
        if row["env"] == "aa11"
        and row["guid"] == "aa11-s0"
        and row["checkpoint"] == "completion:3"
    ]
    for index, row in enumerate(changed):
        row["checkpoint"] = "completion:2"
        row["checkpoint_step"] = 999
        row["row_id"] = f"replacement-{index}"
    with pytest.raises(ValueError, match="has checkpoints"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))


def test_recorded_plan_does_not_reopen_replay_data(monkeypatch):
    rows = _recorded_plan_fixture()
    monkeypatch.setattr(
        R,
        "plan_rows",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("reopened replay")),
    )
    assert R._recorded_iteration_plan(
        rows, _draw(iteration=("aa11", "bb22"))
    )


def test_champion_selection_is_game_balanced_and_freezes_the_winner(
    tmp_path, monkeypatch
):
    conditions = R.MEASURED_CONDITIONS
    rows = []
    for env in ("aa11", "bb22"):
        for condition in conditions:
            rows.append(
                R.PlanRow(
                    mode="measured-iteration",
                    condition=condition,
                    env=env,
                    guid=f"{env}-s",
                    session_rank=0,
                    selection_tier=3,
                    checkpoint="completion:1",
                    checkpoint_step=10,
                    ablate_completions=False,
                )
            )
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    monkeypatch.setattr(
        R,
        "_draw",
        lambda path=R.DRAW: {
            "iteration": ["aa11", "bb22"],
            "one_shot": [],
            "reserved": [],
            "primary_class": {},
        },
    )
    monkeypatch.setattr(
        R,
        "_recorded_iteration_plan",
        lambda records, draw: {record["row_id"]: record for record in records},
    )
    monkeypatch.setattr(R, "ROOT", tmp_path)

    # c wins on the primary metric. b wins exact predicate and d wins class, proving the
    # declared lexicographic order is actually applied.
    metric = {
        "b": (0.4, 1.0, 0.5),
        "c": (0.7, 0.0, 0.0),
        "d": (0.6, 0.0, 1.0),
    }
    log_path = tmp_path / "raw.jsonl"
    log = R.JsonlLog(log_path)
    for row in rows:
        record = {
            "row_id": row.row_id,
            "env": row.env,
            "mode": "measured-iteration",
            "condition": row.condition,
            "model": (
                "/models/Qwen3.6-27B-8bit"
                if row.condition in R.MODEL_CONDITIONS
                else None
            ),
            "freeze_fingerprint": "freeze",
            "status": "complete",
        }
        if row.condition in R.MODEL_CONDITIONS:
            field, predicate, cls = metric[row.condition]
            record["score"] = {
                "top1_field_accuracy": field,
                "top1_predicate_correct": predicate,
                "top3_class_correct": cls,
            }
        log.append(record)
    output = tmp_path / "champion.json"
    artifact = R.select_champion(log_path, output_path=output, freeze_path=tmp_path)
    assert artifact["champion"] == "c"
    assert artifact["ranking"] == ["c", "d", "b"]
    assert artifact["metrics"]["c"]["mean_top1_field_accuracy"] == 0.7
    assert len(artifact["source_log_sha256"]) == 64
    assert json.loads(output.read_text()) == artifact


def test_champion_selection_omits_recorded_exclusions_from_metrics(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    monkeypatch.setattr(
        R,
        "_draw",
        lambda path=R.DRAW: {
            "iteration": ["aa11"],
            "one_shot": [],
            "reserved": [],
            "primary_class": {},
        },
    )
    records = []
    for condition in R.MODEL_CONDITIONS:
        records.append(
            {
                "row_id": f"{condition}-excluded",
                "env": "aa11",
                "mode": "measured-iteration",
                "condition": condition,
                "model": "/models/Qwen3.6-27B-8bit",
                "freeze_fingerprint": "freeze",
                "status": "excluded",
            }
        )
        records.append(
            {
                "row_id": f"{condition}-complete",
                "env": "aa11",
                "mode": "measured-iteration",
                "condition": condition,
                "model": "/models/Qwen3.6-27B-8bit",
                "freeze_fingerprint": "freeze",
                "status": "complete",
                "score": {
                    "top1_field_accuracy": 0.5,
                    "top1_predicate_correct": False,
                    "top3_class_correct": True,
                },
            }
        )
    monkeypatch.setattr(
        R,
        "_recorded_iteration_plan",
        lambda logged, draw: {record["row_id"]: record for record in logged},
    )
    monkeypatch.setattr(R, "ROOT", tmp_path)
    log = R.JsonlLog(tmp_path / "raw.jsonl")
    for record in records:
        log.append(record)
    artifact = R.select_champion(
        log.path,
        output_path=tmp_path / "champion.json",
        freeze_path=tmp_path,
    )
    assert artifact["metrics"]["b"]["n_complete_rows"] == 1.0


def test_champion_selection_refuses_an_incomplete_pass(tmp_path, monkeypatch):
    row = R.PlanRow(
        mode="measured-iteration",
        condition="b",
        env="aa11",
        guid="s",
        session_rank=0,
        selection_tier=3,
        checkpoint="completion:1",
        checkpoint_step=10,
        ablate_completions=False,
    )
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    monkeypatch.setattr(R, "_draw", lambda path=R.DRAW: _draw())
    monkeypatch.setattr(R, "plan_rows", lambda **kwargs: [row])
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    with pytest.raises(ValueError, match="no terminal rows"):
        R.select_champion(empty, output_path=tmp_path / "champion.json")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"mode": "moe-debug"}, "another mode"),
        ({"freeze_fingerprint": "old"}, "another freeze"),
        ({"model": "/models/Qwen3.6-35B-A3B-4bit"}, "non-measurement model"),
    ],
)
def test_champion_refuses_tainted_model_records(
    tmp_path, monkeypatch, changes, message
):
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    monkeypatch.setattr(
        R,
        "_draw",
        lambda path=R.DRAW: {
            "iteration": ["aa11"],
            "one_shot": [],
            "reserved": [],
            "primary_class": {},
        },
    )
    monkeypatch.setattr(R, "plan_rows", lambda **kwargs: [])
    record = {
        "row_id": "x",
        "mode": "measured-iteration",
        "condition": "b",
        "model": "/models/Qwen3.6-27B-8bit",
        "freeze_fingerprint": "freeze",
        "status": "error",
        **changes,
    }
    log = R.JsonlLog(tmp_path / "raw.jsonl")
    log.append(record)
    with pytest.raises(ValueError, match=message):
        R.select_champion(log.path, output_path=tmp_path / "champion.json")


def test_champion_refuses_a_floor_row_that_names_a_model(tmp_path, monkeypatch):
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    monkeypatch.setattr(
        R,
        "_draw",
        lambda path=R.DRAW: {
            "iteration": ["aa11"],
            "one_shot": [],
            "reserved": [],
            "primary_class": {},
        },
    )
    monkeypatch.setattr(R, "plan_rows", lambda **kwargs: [])
    log = R.JsonlLog(tmp_path / "raw.jsonl")
    log.append(
        {
            "row_id": "x",
            "mode": "measured-iteration",
            "condition": "e",
            "model": "/models/Qwen3.6-27B-8bit",
            "freeze_fingerprint": "freeze",
            "status": "error",
        }
    )
    with pytest.raises(ValueError, match="floor row unexpectedly names a model"):
        R.select_champion(log.path, output_path=tmp_path / "champion.json")


def test_champion_refuses_unexpected_terminal_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    monkeypatch.setattr(
        R,
        "_draw",
        lambda path=R.DRAW: {
            "iteration": ["aa11"],
            "one_shot": [],
            "reserved": [],
            "primary_class": {},
        },
    )
    monkeypatch.setattr(R, "plan_rows", lambda **kwargs: [])
    log = R.JsonlLog(tmp_path / "raw.jsonl")
    log.append(
        {
            "row_id": "extra",
            "mode": "measured-iteration",
            "condition": "e",
            "model": None,
            "freeze_fingerprint": "freeze",
            "status": "complete",
        }
    )
    with pytest.raises(ValueError, match="game membership"):
        R.select_champion(log.path, output_path=tmp_path / "champion.json")


def test_champion_refuses_a_valid_row_recorded_as_excluded(tmp_path, monkeypatch):
    rows = _recorded_plan_fixture()
    target = next(
        record
        for record in rows
        if record["condition"] == "b"
        and record["env"] == "aa11"
        and record["checkpoint"] == "completion:1"
    )
    target["status"] = "excluded"
    target["exclusion_reason"] = "invalid_checkpoint"
    with pytest.raises(ValueError, match="disagrees on inclusion"):
        R._recorded_iteration_plan(rows, _draw(iteration=("aa11", "bb22")))


def test_champion_refuses_an_iteration_game_with_no_scored_rows(tmp_path, monkeypatch):
    rows = [
        R.PlanRow(
            mode="measured-iteration",
            condition=condition,
            env="aa11",
            guid="s",
            session_rank=0,
            selection_tier=3,
            checkpoint="completion:1",
            checkpoint_step=10,
            ablate_completions=False,
        )
        for condition in R.MEASURED_CONDITIONS
    ]
    monkeypatch.setattr(
        R, "require_frozen", lambda path: {"contract_fingerprint": "freeze"}
    )
    monkeypatch.setattr(
        R,
        "_draw",
        lambda path=R.DRAW: {
            "iteration": ["aa11", "bb22"],
            "one_shot": [],
            "reserved": [],
            "primary_class": {},
        },
    )
    monkeypatch.setattr(R, "plan_rows", lambda **kwargs: rows)
    monkeypatch.setattr(
        R,
        "_recorded_iteration_plan",
        lambda records, draw: {record["row_id"]: record for record in records},
    )
    log = R.JsonlLog(tmp_path / "raw.jsonl")
    for row in rows:
        record = {
            "row_id": row.row_id,
            "env": row.env,
            "mode": row.mode,
            "condition": row.condition,
            "model": (
                "/models/Qwen3.6-27B-8bit"
                if row.condition in R.MODEL_CONDITIONS
                else None
            ),
            "freeze_fingerprint": "freeze",
            "status": "complete",
        }
        if row.condition in R.MODEL_CONDITIONS:
            record["score"] = {
                "top1_field_accuracy": 0,
                "top1_predicate_correct": False,
                "top3_class_correct": False,
            }
        log.append(record)
    with pytest.raises(ValueError, match="empty game"):
        R.select_champion(log.path, output_path=tmp_path / "champion.json")
