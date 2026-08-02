#!/usr/bin/env python3
"""Resumable GI-1 iteration experiment runner.

This runner owns four operational concerns and no scientific treatment logic:

* deterministic E1 checkpoint scheduling over the six iteration games;
* condition execution for model arms (b-d) and programmatic floors (e-f);
* append-only logging of the exact request, raw API response, raw assistant text, and score;
* exclusion of invalid checkpoints and E3 completion-ablation contamination before rendering.

Model-role separation is enforced:

* ``moe-debug`` accepts only Qwen3.6-35B-A3B-4bit and iteration games.  Its logs are never
  accepted by champion selection.
* ``measured-iteration`` accepts only Qwen3.6-27B-8bit, requires the implementation-freeze
  manifest to verify, fixes conditions to (b)-(f), and uses the frozen generation mapping.

Raw JSONL is resumable.  Completed and excluded row IDs are skipped; error attempts are retained
and retried.  An interrupted request has no terminal record and is therefore retried.  The
completion-ablation pass has a distinct default log, and champion selection reads the recorded
row plan rather than reconstructing exclusions from mutable replay data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from gi1_freeze import (
    DEVELOPMENT_MODEL_BASENAME,
    MEASURED_GENERATION,
    MEASUREMENT_MODEL_BASENAME,
    OUT as FREEZE,
    require_frozen,
)
from gi1_k4_scorer import load_gold_index, score_raw_output
from gi1_packets import checkpoints, extract, load_timeline, select_sessions
from gi1_render import ablation_contamination, assemble
from gi1_retrieval import (
    condition_e_prior,
    condition_f_vote,
    load_or_build_index,
    query,
)

ROOT = Path(__file__).resolve().parents[2]
DRAW = ROOT / "logs/gi1_game_draw.json"
DEFAULT_DEBUG_LOG = ROOT / "logs/gi1_moe_debug.jsonl"
DEFAULT_MEASURED_LOG = ROOT / "logs/gi1_iteration_27b_raw.jsonl"
DEFAULT_ABLATION_LOG = ROOT / "logs/gi1_iteration_e3_ablation_raw.jsonl"
CHAMPION_OUT = ROOT / "logs/gi1_champion.json"

MODEL_CONDITIONS = ("b", "c", "d")
FLOOR_CONDITIONS = ("e", "f")
MEASURED_CONDITIONS = MODEL_CONDITIONS + FLOOR_CONDITIONS
NORMAL_CHECKPOINTS = ("offset:10", "offset:30", "completion:1", "completion:2", "completion:3")
ABLATION_CHECKPOINTS = ("completion:1", "completion:2", "completion:3")
FORMAT_VERSION = 1


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_log_path(
    *,
    mode: str,
    ablate_completions: bool,
    explicit: Path | None,
) -> Path:
    if explicit is not None:
        log_path = explicit
    elif mode == "moe-debug":
        log_path = DEFAULT_DEBUG_LOG
    elif ablate_completions:
        log_path = DEFAULT_ABLATION_LOG
    else:
        log_path = DEFAULT_MEASURED_LOG
    if (
        ablate_completions
        and log_path.resolve() == DEFAULT_MEASURED_LOG.resolve()
    ):
        raise ValueError(
            "completion ablation cannot write the normal measured log; "
            f"use {DEFAULT_ABLATION_LOG.relative_to(ROOT)} or another explicit path"
        )
    return log_path


@dataclass(frozen=True)
class PlanRow:
    mode: str
    condition: str
    env: str
    guid: str
    session_rank: int
    selection_tier: int
    checkpoint: str
    checkpoint_step: int | None
    ablate_completions: bool
    exclusion_reason: str | None = None
    contamination: tuple[dict[str, Any], ...] = ()

    @property
    def row_id(self) -> str:
        identity = {
            "format_version": FORMAT_VERSION,
            "mode": self.mode,
            "condition": self.condition,
            "env": self.env,
            "guid": self.guid,
            "checkpoint": self.checkpoint,
            "checkpoint_step": self.checkpoint_step,
            "ablate_completions": self.ablate_completions,
        }
        return _sha256_bytes(_canonical(identity))[:24]


def _draw(path: Path = DRAW) -> dict[str, Any]:
    value = json.loads(path.read_text())
    required = {"iteration", "one_shot", "reserved", "primary_class"}
    if not isinstance(value, dict) or not required <= set(value):
        raise ValueError("game draw is missing required buckets or primary classes")
    buckets = [value[name] for name in ("iteration", "one_shot", "reserved")]
    if any(not isinstance(bucket, list) for bucket in buckets):
        raise ValueError("game draw buckets must be lists")
    if set(value["iteration"]) & (set(value["one_shot"]) | set(value["reserved"])):
        raise ValueError("iteration games overlap another draw bucket")
    return value


def plan_rows(
    *,
    mode: str,
    conditions: Iterable[str],
    ablate_completions: bool = False,
    games: Iterable[str] | None = None,
    draw: dict[str, Any] | None = None,
) -> list[PlanRow]:
    """Build the deterministic row plan; exclusions are records, not silent drops."""
    draw = draw or _draw()
    iteration = tuple(draw["iteration"])
    selected_games = tuple(sorted(games if games is not None else iteration))
    outside = set(selected_games) - set(iteration)
    if outside:
        raise ValueError(f"runner may open iteration games only: {sorted(outside)}")
    condition_order = tuple(conditions)
    allowed = set(MEASURED_CONDITIONS)
    if not condition_order or len(condition_order) != len(set(condition_order)):
        raise ValueError("conditions must be a non-empty unique sequence")
    if set(condition_order) - allowed:
        raise ValueError(f"unknown conditions: {sorted(set(condition_order) - allowed)}")
    if ablate_completions and set(condition_order) - {"d", "f"}:
        raise ValueError("completion-content ablation is defined only for conditions d and f")
    checkpoint_order = ABLATION_CHECKPOINTS if ablate_completions else NORMAL_CHECKPOINTS

    out: list[PlanRow] = []
    for env in selected_games:
        sessions = select_sessions(env)
        for session in sessions:
            timeline = load_timeline(env, session["guid"])
            available = checkpoints(timeline)
            for checkpoint in checkpoint_order:
                step = available[checkpoint]
                if step is None:
                    for condition in condition_order:
                        out.append(
                            PlanRow(
                                mode=mode,
                                condition=condition,
                                env=env,
                                guid=session["guid"],
                                session_rank=session["rank"],
                                selection_tier=session["tier"],
                                checkpoint=checkpoint,
                                checkpoint_step=None,
                                ablate_completions=ablate_completions,
                                exclusion_reason="invalid_checkpoint",
                            )
                        )
                    continue
                packet = extract(timeline, checkpoint, step)
                contamination = (
                    tuple(ablation_contamination(packet))
                    if ablate_completions
                    else ()
                )
                for condition in condition_order:
                    out.append(
                        PlanRow(
                            mode=mode,
                            condition=condition,
                            env=env,
                            guid=session["guid"],
                            session_rank=session["rank"],
                            selection_tier=session["tier"],
                            checkpoint=checkpoint,
                            checkpoint_step=step,
                            ablate_completions=ablate_completions,
                            exclusion_reason=(
                                "completion_ablation_contamination"
                                if contamination
                                else None
                            ),
                            contamination=contamination,
                        )
                    )
    ids = [row.row_id for row in out]
    if len(ids) != len(set(ids)):
        raise ValueError("row plan contains duplicate identities")
    return out


class JsonlLog:
    """Thread-safe, durable JSONL append with resume-state validation."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open() as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{self.path}:{line_number}: invalid JSONL: {exc}"
                    ) from exc
                if not isinstance(value, dict) or not isinstance(value.get("row_id"), str):
                    raise ValueError(
                        f"{self.path}:{line_number}: record has no text row_id"
                    )
                records.append(value)
        return records

    def terminal_ids(self) -> set[str]:
        return {
            record["row_id"]
            for record in self.records()
            if record.get("status") in {"complete", "excluded"}
        }

    def attempt_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.records():
            row_id = record["row_id"]
            counts[row_id] = counts.get(row_id, 0) + 1
        return counts

    def append(self, value: dict[str, Any]) -> None:
        encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.path.open("a") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())


def _row_base(
    row: PlanRow,
    *,
    model: str | None,
    freeze_fingerprint: str | None,
    attempt: int,
) -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "row_id": row.row_id,
        "recorded_at": _utc_now(),
        "attempt": attempt,
        "mode": row.mode,
        "condition": row.condition,
        "env": row.env,
        "guid": row.guid,
        "session_rank": row.session_rank,
        "selection_tier": row.selection_tier,
        "checkpoint": row.checkpoint,
        "checkpoint_step": row.checkpoint_step,
        "ablate_completions": row.ablate_completions,
        "model": model,
        "freeze_fingerprint": freeze_fingerprint,
    }


def _packet_for(row: PlanRow):
    if row.checkpoint_step is None:
        raise ValueError("excluded checkpoint has no packet")
    timeline = load_timeline(row.env, row.guid)
    return extract(timeline, row.checkpoint, row.checkpoint_step)


def _request_payload(model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        **MEASURED_GENERATION,
    }


def call_chat(
    *,
    base_url: str,
    payload: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], float]:
    body = _canonical(payload)
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except (OSError, urllib.error.URLError) as exc:
        raise RuntimeError(f"model request failed: {exc}") from exc
    elapsed = time.monotonic() - started
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"model response is not UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("model response must be a JSON object")
    return value, elapsed


def _assistant_text(response: dict[str, Any]) -> Any:
    try:
        return response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def execute_row(
    row: PlanRow,
    *,
    model: str | None,
    base_url: str,
    timeout: float,
    index: list[dict[str, Any]],
    library_games: list[str],
    primary_classes: dict[str, str],
    gold: dict[str, dict[str, Any]],
    freeze_fingerprint: str | None,
    attempt: int,
    chat=call_chat,
) -> dict[str, Any]:
    base = _row_base(
        row,
        model=model,
        freeze_fingerprint=freeze_fingerprint,
        attempt=attempt,
    )
    if row.exclusion_reason is not None:
        return {
            **base,
            "status": "excluded",
            "exclusion_reason": row.exclusion_reason,
            "contamination": list(row.contamination),
        }
    packet = _packet_for(row)
    gold_class = primary_classes[row.env]

    if row.condition == "e":
        classes = condition_e_prior(row.env, library_games)
        return {
            **base,
            "status": "complete",
            "raw_output": {"classes": classes},
            "score": {
                "top1_class_correct": bool(classes and classes[0] == gold_class),
                "top3_class_correct": gold_class in classes,
            },
        }
    if row.condition == "f":
        hits, query_type = query(
            index,
            packet,
            ablate_completions=row.ablate_completions,
        )
        classes = condition_f_vote(
            index,
            packet,
            library_games,
            ablate_completions=row.ablate_completions,
        )
        return {
            **base,
            "status": "complete",
            "raw_output": {
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
            },
            "score": {
                "top1_class_correct": bool(classes and classes[0] == gold_class),
                "top3_class_correct": gold_class in classes,
            },
        }
    if row.condition not in MODEL_CONDITIONS:
        raise ValueError(f"unimplemented condition {row.condition}")
    if model is None:
        raise ValueError(f"condition {row.condition} requires a model")
    messages = assemble(
        row.condition,
        packet,
        index=index,
        ablate_completions=row.ablate_completions,
        with_image=True,
    )
    payload = _request_payload(model, messages)
    response, elapsed = chat(base_url=base_url, payload=payload, timeout=timeout)
    raw_text = _assistant_text(response)
    score = score_raw_output(raw_text, gold[row.env]).as_dict()
    return {
        **base,
        "status": "complete",
        "request": payload,
        "request_sha256": _sha256_bytes(_canonical(payload)),
        "raw_response": response,
        "raw_output": raw_text,
        "elapsed_seconds": elapsed,
        "score": score,
    }


def _assert_mode(
    *,
    mode: str,
    model: str,
    conditions: tuple[str, ...],
    ablate_completions: bool,
    freeze_path: Path,
) -> str | None:
    basename = Path(model).name
    if mode == "moe-debug":
        if basename != DEVELOPMENT_MODEL_BASENAME:
            raise ValueError(
                f"moe-debug requires {DEVELOPMENT_MODEL_BASENAME}, got {basename}"
            )
        if set(conditions) - set(MODEL_CONDITIONS):
            raise ValueError("MoE development may run prompt conditions b-d only")
        return None
    if mode != "measured-iteration":
        raise ValueError(f"unknown mode {mode}")
    if basename != MEASUREMENT_MODEL_BASENAME:
        raise ValueError(
            f"measured-iteration requires {MEASUREMENT_MODEL_BASENAME}, got {basename}"
        )
    expected = ("d", "f") if ablate_completions else MEASURED_CONDITIONS
    if conditions != expected:
        raise ValueError(
            f"measured-iteration conditions are fixed to {expected}, got {conditions}"
        )
    return require_frozen(freeze_path)["contract_fingerprint"]


def _validate_existing_log(
    records: list[dict[str, Any]],
    *,
    mode: str,
    model: str,
    freeze_fingerprint: str | None,
) -> None:
    for offset, record in enumerate(records, start=1):
        if record.get("mode") != mode:
            raise ValueError(f"existing log row {offset} belongs to {record.get('mode')!r}")
        condition = record.get("condition")
        expected_model = model if condition in MODEL_CONDITIONS else None
        if record.get("model") != expected_model:
            raise ValueError(f"existing log row {offset} has a different model")
        if record.get("freeze_fingerprint") != freeze_fingerprint:
            raise ValueError(f"existing log row {offset} has a different freeze")


def run(
    *,
    mode: str,
    model: str,
    base_url: str,
    log_path: Path,
    conditions: tuple[str, ...],
    ablate_completions: bool,
    games: tuple[str, ...] | None,
    timeout: float,
    concurrency: int,
    limit_model_calls: int | None,
    freeze_path: Path = FREEZE,
    continue_on_error: bool = False,
    rebuild_index: bool = False,
) -> dict[str, int]:
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    if limit_model_calls is not None and limit_model_calls < 1:
        raise ValueError("limit_model_calls must be positive")
    freeze_fingerprint = _assert_mode(
        mode=mode,
        model=model,
        conditions=conditions,
        ablate_completions=ablate_completions,
        freeze_path=freeze_path,
    )
    draw = _draw()
    rows = plan_rows(
        mode=mode,
        conditions=conditions,
        ablate_completions=ablate_completions,
        games=games,
        draw=draw,
    )
    logger = JsonlLog(log_path)
    existing = logger.records()
    _validate_existing_log(
        existing,
        mode=mode,
        model=model,
        freeze_fingerprint=freeze_fingerprint,
    )
    terminal = {
        record["row_id"]
        for record in existing
        if record.get("status") in {"complete", "excluded"}
    }
    attempts = logger.attempt_counts()
    pending = [row for row in rows if row.row_id not in terminal]

    library_games = sorted(draw["iteration"] + draw["one_shot"])
    index = load_or_build_index(library_games, rebuild=rebuild_index)
    primary = draw["primary_class"]
    gold = load_gold_index()

    if limit_model_calls is not None:
        admitted = 0
        limited = []
        for row in pending:
            if row.condition in MODEL_CONDITIONS and row.exclusion_reason is None:
                if admitted >= limit_model_calls:
                    continue
                admitted += 1
            limited.append(row)
        pending = limited

    summary = {
        "planned": len(rows),
        "already_terminal": len(terminal & {row.row_id for row in rows}),
        "complete": 0,
        "excluded": 0,
        "error": 0,
    }

    def one(row: PlanRow) -> tuple[PlanRow, dict[str, Any]]:
        attempt = attempts.get(row.row_id, 0) + 1
        try:
            result = execute_row(
                row,
                model=model if row.condition in MODEL_CONDITIONS else None,
                base_url=base_url,
                timeout=timeout,
                index=index,
                library_games=library_games,
                primary_classes=primary,
                gold=gold,
                freeze_fingerprint=freeze_fingerprint,
                attempt=attempt,
            )
        except Exception as exc:
            result = {
                **_row_base(
                    row,
                    model=model if row.condition in MODEL_CONDITIONS else None,
                    freeze_fingerprint=freeze_fingerprint,
                    attempt=attempt,
                ),
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        return row, result

    # Exclusions and floors are cheap and deterministic.  Execute them serially so model
    # concurrency is reserved exclusively for calls that can overlap on the inference server.
    model_rows = []
    for row in pending:
        if row.exclusion_reason is not None or row.condition in FLOOR_CONDITIONS:
            _, result = one(row)
            logger.append(result)
            summary[result["status"]] += 1
        else:
            model_rows.append(row)

    fatal: tuple[PlanRow, dict[str, Any]] | None = None
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(one, row): row for row in model_rows}
        for future in as_completed(futures):
            if future.cancelled():
                continue
            row, result = future.result()
            logger.append(result)
            summary[result["status"]] += 1
            if (
                result["status"] == "error"
                and not continue_on_error
                and fatal is None
            ):
                fatal = (row, result)
                for other in futures:
                    other.cancel()
                # Keep draining already-running futures.  Their paid-for responses must be
                # appended before the fail-fast error reaches the caller.
    if fatal is not None:
        row, result = fatal
        raise RuntimeError(
            f"{row.row_id} {row.env}/{row.guid} {row.checkpoint} "
            f"condition {row.condition}: {result['error']}"
        )
    return summary


def _latest_terminal(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest = {}
    for record in records:
        if record.get("status") in {"complete", "excluded"}:
            latest[record["row_id"]] = record
    return latest


def _recorded_iteration_plan(
    records: list[dict[str, Any]],
    draw: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Validate and return the terminal plan recorded by the measured run.

    Selection must not reopen replay data to decide which rows count.  The append log already
    records every valid and excluded checkpoint, so it is the authoritative measured plan.
    """
    terminal_records = [
        record
        for record in records
        if record.get("status") in {"complete", "excluded"}
    ]
    terminal_ids = [record.get("row_id") for record in terminal_records]
    if len(terminal_ids) != len(set(terminal_ids)):
        raise ValueError("measured log contains duplicate terminal row IDs")
    latest = _latest_terminal(terminal_records)
    if not latest:
        raise ValueError("measured log contains no terminal rows")

    iteration = draw.get("iteration")
    if (
        not isinstance(iteration, list)
        or any(not isinstance(env, str) for env in iteration)
        or len(iteration) != len(set(iteration))
    ):
        raise ValueError("frozen draw has invalid iteration membership")
    expected_games = set(iteration)
    actual_games = {record.get("env") for record in terminal_records}
    if actual_games != expected_games:
        raise ValueError(
            "recorded plan game membership differs from frozen draw: "
            f"missing={sorted(expected_games - actual_games)}, "
            f"extra={sorted(actual_games - expected_games)}"
        )
    if any(record.get("ablate_completions") is not False for record in terminal_records):
        raise ValueError("normal measured log contains completion-ablation rows")

    slots: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    for record in terminal_records:
        condition = record.get("condition")
        if condition not in MEASURED_CONDITIONS:
            raise ValueError(f"recorded plan contains unknown condition {condition!r}")
        checkpoint = record.get("checkpoint")
        if checkpoint not in NORMAL_CHECKPOINTS:
            raise ValueError(f"recorded plan contains unknown checkpoint {checkpoint!r}")
        slot = (
            record.get("env"),
            record.get("guid"),
            record.get("session_rank"),
            record.get("selection_tier"),
            checkpoint,
            record.get("checkpoint_step"),
        )
        arms = slots.setdefault(slot, {})
        if condition in arms:
            raise ValueError(f"recorded plan repeats condition {condition} in a row slot")
        arms[condition] = record

    expected_conditions = set(MEASURED_CONDITIONS)
    for slot, arms in slots.items():
        if set(arms) != expected_conditions:
            raise ValueError(
                f"recorded plan slot {slot!r} has conditions {sorted(arms)}, "
                f"expected {sorted(expected_conditions)}"
            )
        statuses = {record["status"] for record in arms.values()}
        if len(statuses) != 1:
            raise ValueError(f"recorded plan slot {slot!r} disagrees on inclusion")
        status = next(iter(statuses))
        if status == "excluded":
            reasons = {record.get("exclusion_reason") for record in arms.values()}
            if reasons != {"invalid_checkpoint"} or slot[-1] is not None:
                raise ValueError(f"recorded plan slot {slot!r} has invalid exclusion")
        elif isinstance(slot[-1], bool) or not isinstance(slot[-1], int):
            raise ValueError(f"recorded plan slot {slot!r} has no integer checkpoint step")

    for env in iteration:
        env_slots = [slot for slot in slots if slot[0] == env]
        sessions = {(slot[1], slot[2], slot[3]) for slot in env_slots}
        if len(sessions) != 3:
            raise ValueError(f"recorded plan game {env} has {len(sessions)} sessions, expected 3")
        for session in sessions:
            checkpoints_seen = {
                slot[4] for slot in env_slots if slot[1:4] == session
            }
            if checkpoints_seen != set(NORMAL_CHECKPOINTS):
                raise ValueError(
                    f"recorded plan game {env} session {session[0]} has checkpoints "
                    f"{sorted(checkpoints_seen)}"
                )
    return latest


def select_champion(
    log_path: Path = DEFAULT_MEASURED_LOG,
    *,
    output_path: Path = CHAMPION_OUT,
    freeze_path: Path = FREEZE,
) -> dict[str, Any]:
    freeze = require_frozen(freeze_path)
    draw = _draw()
    records = JsonlLog(log_path).records()
    for offset, record in enumerate(records, start=1):
        if record.get("mode") != "measured-iteration":
            raise ValueError(f"measured log row {offset} belongs to another mode")
        if record.get("freeze_fingerprint") != freeze["contract_fingerprint"]:
            raise ValueError(f"measured log row {offset} belongs to another freeze")
        if record.get("condition") in MODEL_CONDITIONS:
            if Path(str(record.get("model"))).name != MEASUREMENT_MODEL_BASENAME:
                raise ValueError("measured log contains a non-measurement model")
        elif record.get("model") is not None:
            raise ValueError("programmatic floor row unexpectedly names a model")
    latest = _recorded_iteration_plan(records, draw)

    metrics: dict[str, dict[str, float]] = {}
    for condition in MODEL_CONDITIONS:
        by_game: dict[str, list[dict[str, Any]]] = {env: [] for env in draw["iteration"]}
        for record in latest.values():
            if record.get("condition") != condition:
                continue
            if record.get("status") == "excluded":
                continue
            by_game[record["env"]].append(record["score"])
        if any(not scores for scores in by_game.values()):
            raise ValueError(f"condition {condition} has an empty game in champion scoring")

        def game_balanced(name: str) -> float:
            game_means = [
                sum(float(score[name]) for score in scores) / len(scores)
                for scores in by_game.values()
            ]
            return sum(game_means) / len(game_means)

        metrics[condition] = {
            "mean_top1_field_accuracy": game_balanced("top1_field_accuracy"),
            "mean_top1_predicate_correct": game_balanced("top1_predicate_correct"),
            "mean_top3_class_correct": game_balanced("top3_class_correct"),
            "n_complete_rows": float(sum(len(scores) for scores in by_game.values())),
            "n_games": float(len(by_game)),
        }

    order = sorted(
        MODEL_CONDITIONS,
        key=lambda condition: (
            -metrics[condition]["mean_top1_field_accuracy"],
            -metrics[condition]["mean_top1_predicate_correct"],
            -metrics[condition]["mean_top3_class_correct"],
            condition,
        ),
    )
    artifact = {
        "format_version": FORMAT_VERSION,
        "status": "frozen",
        "scope": "gi1_iteration",
        "champion": order[0],
        "selection_rule": [
            "game-balanced mean top-one field accuracy",
            "game-balanced exact top-one predicate correctness",
            "game-balanced top-three class accuracy",
            "condition ID lexical tie-break",
        ],
        "ranking": order,
        "metrics": metrics,
        "implementation_freeze_fingerprint": freeze["contract_fingerprint"],
        "source_log": str(log_path.relative_to(ROOT)),
        "source_log_sha256": _sha256_file(log_path),
    }
    output_path.write_text(json.dumps(artifact, indent=2) + "\n")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("moe-debug", "measured-iteration"),
    )
    parser.add_argument("--model")
    parser.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--log", type=Path)
    parser.add_argument("--conditions", nargs="+", choices=MEASURED_CONDITIONS)
    parser.add_argument("--ablate-completions", action="store_true")
    parser.add_argument("--game", action="append")
    parser.add_argument("--timeout", type=float, default=2400)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--limit-model-calls", type=int)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--select-champion", action="store_true")
    args = parser.parse_args()

    if args.select_champion:
        artifact = select_champion(args.log or DEFAULT_MEASURED_LOG)
        print(
            f"champion ({artifact['champion']}) frozen in "
            f"{CHAMPION_OUT.relative_to(ROOT)}"
        )
        return 0
    if args.mode is None or args.model is None:
        parser.error("--mode and --model are required unless --select-champion is used")
    default_conditions = (
        MODEL_CONDITIONS if args.mode == "moe-debug" else MEASURED_CONDITIONS
    )
    conditions = tuple(args.conditions or default_conditions)
    try:
        log_path = _resolve_log_path(
            mode=args.mode,
            ablate_completions=args.ablate_completions,
            explicit=args.log,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.dry_run:
        freeze_fingerprint = _assert_mode(
            mode=args.mode,
            model=args.model,
            conditions=conditions,
            ablate_completions=args.ablate_completions,
            freeze_path=FREEZE,
        )
        rows = plan_rows(
            mode=args.mode,
            conditions=conditions,
            ablate_completions=args.ablate_completions,
            games=tuple(args.game) if args.game else None,
        )
        print(
            json.dumps(
                {
                    "rows": len(rows),
                    "model_calls": sum(
                        row.condition in MODEL_CONDITIONS
                        and row.exclusion_reason is None
                        for row in rows
                    ),
                    "excluded": sum(row.exclusion_reason is not None for row in rows),
                    "freeze_fingerprint": freeze_fingerprint,
                },
                indent=2,
            )
        )
        return 0
    summary = run(
        mode=args.mode,
        model=args.model,
        base_url=args.base_url,
        log_path=log_path,
        conditions=conditions,
        ablate_completions=args.ablate_completions,
        games=tuple(args.game) if args.game else None,
        timeout=args.timeout,
        concurrency=args.concurrency,
        limit_model_calls=args.limit_model_calls,
        continue_on_error=args.continue_on_error,
        rebuild_index=args.rebuild_index,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
