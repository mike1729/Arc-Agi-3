#!/usr/bin/env python3
"""Bounded, development-only Qwen3.8 serving/reasoning calibration.

This is deliberately not another model-selection experiment.  It exercises the
one production sampler on the three procedural *development* active sentinels:

* three ordinary pre-probe calls;
* one same-process, same-prompt, same-seed repeat;
* one different-seed call on that same high-entropy structured prompt; and
* matched-seed stripped-history/preserved-reasoning post-probe pairs for all
  three fixtures.

The inventory is exactly eleven calls.  The serving run never opens stored
semantic gold or uses semantic judgments, never touches confirmation/freeze
artifacts, never invokes Kaggle, and never changes temperature/top-p.  ``--plan``
is a no-model dry run.  ``--run`` creates a new append-only run directory
containing read-only serving traces and a read-only result manifest.  A 49,152-
token truncation escalation is recorded as an explicitly manual, predeclared
option; this harness never launches it.

After a mechanically valid run, a separate one-shot workflow can create a
condition-blind semantic worksheet for the six post-probe answers, accept one
hash-bound human judgment artifact, and derive a strict paired operational
no-regression result.  This is deliberately an operational safeguard over only
three pairs, not a statistical non-inferiority claim.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_probe_vlm as probe  # noqa: E402
import s4_ledgers as ledgers  # noqa: E402
import s4_run as srun  # noqa: E402
import s4_sentinels as sentinels  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FORMAT_VERSION = 1
PROTOCOL_VERSION = "r4-qwen-calibration-v1"
CALL_BUDGET = 11
ANSWER_TOKENS = 32_768
MANUAL_TRUNCATION_TOKENS = 49_152
OUTPUT_ROOT = ROOT / "logs/s4_qwen_calibration_runs"
ATTEMPT_ROOT = ROOT / "logs/s4_qwen_calibration_attempts"
SEMANTIC_FORMAT_VERSION = 1
SEMANTIC_PROTOCOL_VERSION = "r4-qwen-calibration-semantic-v1"
SEMANTIC_OUTPUT_ROOT = ROOT / "logs/s4_qwen_calibration_semantic"
SEMANTIC_ATTEMPT_ROOT = ROOT / "logs/s4_qwen_calibration_semantic_attempts"
SEMANTIC_COMPONENTS = (
    "goal_constraints_complete", "plan_executable", "joint_complete",
)
SEMANTIC_BLIND_ATTESTATION = {
    "explicit_condition_labels_unavailable": True,
    "source_calibration_result_unavailable": True,
    "blinding_key_unavailable": True,
    "single_pass_without_other_verdicts": True,
}
SEMANTIC_RUBRIC = {
    "goal_correct_in_kind": (
        "true only when the stated objective is the same causal kind as the "
        "reference objective"
    ),
    "constraints_by_item": (
        "credit an item only when the answer states it as necessary; partial or "
        "merely correlated descriptions receive no credit"
    ),
    "plan_executable": (
        "copy the displayed independently derived replay pass: exact replay from "
        "the fixed reset, without repair, must complete within the action budget"
    ),
    "judgment_rule": (
        "judge every anonymous sample once without source results, hidden "
        "mapping material, or another judgment"
    ),
}
CRITICAL_SCRIPTS = (
    "agent/harness/e2_probe_vlm.py",
    "agent/harness/s4_delta.py",
    "agent/harness/s4_ledgers.py",
    "agent/harness/s4_qwen_calibration.py",
    "agent/harness/s4_render.py",
    "agent/harness/s4_run.py",
    "agent/harness/s4_sentinels.py",
)
OFFICIAL_THINKING_SAMPLER = {
    "temperature": 1.0,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 0.0,
    "repetition_penalty": 1.0,
}


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _load_json(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file(), f"missing {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read {label} {path}: {exc}") from exc
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _parse_utc(value: Any, label: str) -> _dt.datetime:
    require(isinstance(value, str) and value.strip(), f"{label} must be a timestamp")
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{label} is not ISO-8601: {value!r}") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() == _dt.timedelta(0),
            f"{label} must include an explicit UTC offset")
    return parsed


def _require_read_only(path: Path, label: str) -> None:
    require(path.stat().st_mode & 0o222 == 0,
            f"{label} is not read-only: {path}")


def _atomic_create_json(path: Path, value: Any) -> None:
    """Create one durable read-only JSON artifact; replacement is forbidden."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=1, sort_keys=True, default=str) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RuntimeError(f"append-only artifact already exists: {path}") from exc
    path.chmod(0o444)


def _atomic_create_bytes(path: Path, payload: bytes) -> None:
    """Seal exact caller-supplied bytes once; malformed JSON still consumes."""
    require(isinstance(payload, bytes), "append-only byte payload must be bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RuntimeError(f"append-only artifact already exists: {path}") from exc
    path.chmod(0o444)


def _different_seed(base_seed: int, variant_id: str) -> int:
    raw = hashlib.sha256(
        f"{PROTOCOL_VERSION}:different-seed:{base_seed}:{variant_id}".encode()
    ).digest()
    candidate = int.from_bytes(raw[:8], "big")
    ordinary = sentinels.sentinel_call_seed(
        "dev", variant_id, sentinels.ACTIVE_ARM, "pre", base_seed,
    )
    return candidate if candidate != ordinary else candidate ^ 1


def development_variants(base_seed: int) -> list[dict[str, Any]]:
    """Return only non-gold identifiers needed to preregister the call plan."""
    require(type(base_seed) is int and 0 <= base_seed < 2 ** 63,
            "base_seed must be a non-negative JSON integer")
    rows: list[dict[str, Any]] = []
    for index in range(sentinels.ACTIVE_VARIANTS):
        fixture = sentinels.build_active_variant("dev", index, base_seed)
        rows.append({"index": index, "variant_id": fixture["variant_id"]})
    return rows


def build_call_plan(base_seed: int) -> list[dict[str, Any]]:
    """The complete immutable 11-call design, without loading a model/assets."""
    variants = development_variants(base_seed)
    plan: list[dict[str, Any]] = []

    def add(row: dict[str, Any], role: str, seed: int, history: str) -> None:
        tag = f"qcal_{row['variant_id']}_{role}"
        plan.append({
            "order": len(plan) + 1,
            "tag": tag,
            "variant_index": row["index"],
            "variant_id": row["variant_id"],
            "role": role,
            "history_condition": history,
            "seed": seed,
        })

    # All three production-form pre-probe calls are recorded before the
    # reproducibility controls, so the latter cannot select a fixture by outcome.
    for row in variants:
        seed = sentinels.sentinel_call_seed(
            "dev", row["variant_id"], sentinels.ACTIVE_ARM, "pre", base_seed,
        )
        add(row, "pre_primary", seed, "none")
    first = variants[0]
    first_seed = plan[0]["seed"]
    add(first, "pre_same_seed_repeat", first_seed, "none")
    add(first, "pre_different_seed", _different_seed(base_seed, first["variant_id"]),
        "none")

    # Counterbalance pair order while retaining the exact same seed within each
    # pair.  This guards against a simple warm-state/order explanation.
    for row in variants:
        post_seed = sentinels.sentinel_call_seed(
            "dev", row["variant_id"], sentinels.ACTIVE_ARM, "post", base_seed,
        )
        conditions = ("stripped", "preserved") if row["index"] % 2 == 0 \
            else ("preserved", "stripped")
        for condition in conditions:
            add(row, f"post_{condition}", post_seed, condition)

    require(len(plan) == CALL_BUDGET, "internal calibration call-budget drift")
    require([row["order"] for row in plan] == list(range(1, CALL_BUDGET + 1)),
            "calibration call order is not contiguous")
    require(len({row["tag"] for row in plan}) == CALL_BUDGET,
            "calibration tags are not unique")
    return plan


def plan_document(base_seed: int) -> dict[str, Any]:
    require(probe.PRODUCTION_SAMPLER == OFFICIAL_THINKING_SAMPLER,
            "production sampler is not the pinned official thinking sampler")
    require(probe.REASONING_EFFORT == "xhigh",
            "calibration requires production reasoning_effort=xhigh")
    require(probe.PRESERVE_THINKING is True,
            "calibration requires preserve_thinking=true")
    require(srun.MAX_ANSWER_TOKENS == ANSWER_TOKENS,
            "runner answer-token budget differs from calibration")
    return {
        "format_version": FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "mode": "development_only",
        "base_seed": base_seed,
        "call_budget": CALL_BUDGET,
        "answer_tokens": ANSWER_TOKENS,
        "sampler": copy.deepcopy(OFFICIAL_THINKING_SAMPLER),
        "reasoning_effort": "xhigh",
        "preserve_thinking": True,
        "native_context_tokens": srun.NATIVE_CONTEXT_TOKENS,
        "call_plan": build_call_plan(base_seed),
        "constraints": {
            "kaggle_gpu_hours": 0,
            "kaggle_submissions": 0,
            "temperature_or_top_p_grid": False,
            "confirmation_or_freeze_artifacts": False,
            "semantic_gold_consulted": False,
            "automatic_retry_or_repair": False,
        },
        "truncation_escalation": {
            "automatic": False,
            "eligible_only_if_completeness": "truncated",
            "max_tokens": MANUAL_TRUNCATION_TOKENS,
            "maximum_extra_attempts_per_exact_call": 1,
            "effect": (
                "manual escalation invalidates a 32768 production budget choice; "
                "change code, rerun tests, rebuild packets, and recalibrate before freeze"
            ),
        },
        "different_seed_check": {
            "prompt": "first active sentinel pre-probe structured goal-inference prompt",
            "high_entropy_reason": (
                "multiple ranked causal hypotheses, free-form evidence, a probe, "
                "retrieval requests, and an executable plan are generated"
            ),
            "rule": "identical raw bytes at the different seed fail calibration",
        },
    }


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def assert_development_paths(fixture_root: Path, output_root: Path) -> None:
    sealed = sentinels.SEALED_R4.resolve()
    require(not _is_within(fixture_root, sealed),
            "calibration refuses sealed/confirmation fixture paths")
    require(not _is_within(output_root, sealed),
            "calibration refuses sealed/freeze output paths")
    require(not _is_within(output_root, fixture_root)
            and not _is_within(fixture_root, output_root),
            "fixture and output roots must be disjoint")


def verify_development_assets(
    fixture_root: Path, *, base_seed: int,
) -> tuple[dict[str, Any], Path]:
    """Verify the dev model-visible asset side without opening semantic gold."""
    manifest_path = fixture_root / "sentinel_manifest.json"
    manifest = sentinels.load_manifest(manifest_path)
    require(manifest.get("format_version") == sentinels.FORMAT_VERSION
            and manifest.get("protocol_version") == sentinels.PROTOCOL_VERSION,
            "development sentinel manifest version mismatch")
    require(manifest.get("namespace") == "dev" and manifest.get("base_seed") == base_seed,
            "calibration accepts only the requested development namespace/seed")
    require(manifest.get("generator_sha256") == sha256_file(Path(sentinels.__file__)),
            "development fixtures were not built by the live sentinel generator")
    active = manifest.get("active")
    expected = development_variants(base_seed)
    require(isinstance(active, list) and len(active) == len(expected),
            "development active-sentinel inventory is incomplete")
    require([row.get("variant_id") for row in active]
            == [row["variant_id"] for row in expected],
            "development active-sentinel identifiers drifted")
    asset_files = manifest.get("asset_files")
    require(isinstance(asset_files, dict) and asset_files,
            "development manifest lacks model-visible asset hashes")
    assets_root = (fixture_root / "assets").resolve()
    for relative, expected_sha in asset_files.items():
        require(isinstance(relative, str) and Path(relative).parts[0] == "assets"
                and _is_within(fixture_root / relative, assets_root),
                f"unsafe development asset path: {relative!r}")
        path = fixture_root / relative
        require(path.is_file() and sha256_file(path) == expected_sha,
                f"development asset drift: {relative}")
    for record in active:
        relative = record.get("carrier_file")
        require(isinstance(relative, str) and relative in asset_files,
                f"{record.get('variant_id')}: active carrier is not asset-bound")
    actual_asset_names = {
        str(path.relative_to(fixture_root))
        for path in (fixture_root / "assets").rglob("*") if path.is_file()
    }
    require(actual_asset_names == set(asset_files),
            "development model-visible asset inventory has missing/extra files")

    # Regenerate only the three model-visible active carriers into a private
    # staging root and compare bytes.  This proves the dev manifest is genuine
    # generator output without opening any semantic gold file.
    with tempfile.TemporaryDirectory(prefix="s4-qcal-active-audit-") as temporary:
        staging = Path(temporary)
        generated_assets = staging / "assets"
        generated_assets.mkdir()
        for index, expected_row in enumerate(expected):
            fixture = sentinels.build_active_variant("dev", index, base_seed)
            visible = sentinels.render_active_assets(fixture, generated_assets)
            carrier_relative = str(
                (generated_assets / fixture["variant_id"] / "active_carrier.json")
                .relative_to(staging)
            )
            actual_row = active[index]
            require(actual_row.get("variant_id") == fixture["variant_id"]
                    and actual_row.get("carrier_file") == carrier_relative
                    and actual_row.get("probe_pool")
                    == [row["start_state_id"] for row in visible["probe_pool"]],
                    f"{fixture['variant_id']}: active manifest is not canonical")
        for generated in generated_assets.rglob("*"):
            if not generated.is_file():
                continue
            relative = str(generated.relative_to(staging))
            require(asset_files.get(relative) == sha256_file(generated),
                    f"development active carrier differs from generator: {relative}")
    # Deliberately do not read gold_file/gold_files.  Their presence in the
    # sentinel manifest cannot influence these serving checks or their verdict.
    return manifest, manifest_path


def _stable_checkpoint_identity(fingerprint: dict[str, Any]) -> dict[str, Any]:
    """Remove observation-time metadata while retaining every serving byte hash."""
    stable = copy.deepcopy(fingerprint)
    stable.pop("command", None)
    stable.pop("timestamp_utc", None)
    stable["model_path"] = str(Path(stable["model_path"]).resolve())
    return stable


def build_candidate_contract(
    *, model: Path, base_seed: int, fixture_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], Path, dict[str, Any]]:
    """Bind one clean candidate before any generation or output-path choice."""
    require(fixture_root.resolve() == sentinels.DEV_ROOT.resolve(),
            "hard calibration accepts only the canonical development fixture root")
    manifest, manifest_path = verify_development_assets(
        fixture_root, base_seed=base_seed,
    )
    git = probe.capture_git_state()
    require(set(git) == {"commit", "dirty", "status"}
            and isinstance(git.get("commit"), str) and len(git["commit"]) == 40
            and git.get("dirty") is False and git.get("status") == [],
            f"calibration requires a clean committed worktree: {git}")
    fingerprint = probe.fingerprint(model, git_state=git)
    stable_checkpoint = _stable_checkpoint_identity(fingerprint)
    plan = plan_document(base_seed)
    scripts = {relative: sha256_file(ROOT / relative) for relative in CRITICAL_SCRIPTS}
    core = {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_qwen_calibration_candidate",
        "protocol_version": PROTOCOL_VERSION,
        "git": git,
        "critical_scripts": scripts,
        "checkpoint_identity": stable_checkpoint,
        "development_manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": sha256_file(manifest_path),
            "namespace": "dev",
            "base_seed": base_seed,
            "generator_sha256": manifest["generator_sha256"],
            "asset_inventory_sha256": canonical_sha256(manifest["asset_files"]),
        },
        "plan_sha256": canonical_sha256(plan),
        "request_prompt_sha256": hashlib.sha256(srun.REQUEST.encode()).hexdigest(),
        "sampler": copy.deepcopy(OFFICIAL_THINKING_SAMPLER),
        "reasoning_effort": "xhigh",
        "preserve_thinking": True,
        "answer_tokens": ANSWER_TOKENS,
        "native_context_tokens": srun.NATIVE_CONTEXT_TOKENS,
        "kaggle_submissions": 0,
    }
    serving_identity = {
        "scope": "pinned local checkpoint conversion, not the BF16 model family",
        "verified_shards": True,
        "checkpoint_sha256": stable_checkpoint["checkpoint_sha256"],
        "candidate_checkpoint_identity_sha256": canonical_sha256(stable_checkpoint),
    }
    return core, manifest, manifest_path, serving_identity


def reserve_candidate_attempt(
    candidate_core: dict[str, Any], *, output_root: Path,
    attempt_root: Path = ATTEMPT_ROOT,
) -> dict[str, Any]:
    """Atomically consume attempt 0 for this exact clean candidate.

    ``candidate_id`` excludes paths and timestamps, so changing the output
    directory or launching concurrently cannot buy another sample.  A changed
    clean commit/checkpoint/dev manifest instead creates a scientifically new
    candidate with a different ID.
    """
    candidate_id = canonical_sha256(candidate_core)
    run_dir = (output_root / candidate_id).resolve()
    result_path = run_dir / "RESULT.json"
    reservation_path = (attempt_root / f"{candidate_id}.reservation.json").resolve()
    receipt_path = (attempt_root / f"{candidate_id}.receipt.json").resolve()
    require(not run_dir.exists() and not receipt_path.exists(),
            "candidate run/receipt already exists; attempt 0 is consumed")
    core = {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_qwen_calibration_reservation",
        "protocol_version": PROTOCOL_VERSION,
        "candidate_id": candidate_id,
        "candidate": copy.deepcopy(candidate_core),
        "attempt": 0,
        "run_dir": str(run_dir),
        "output_path": str(result_path),
        "reserved_utc": _utc_now(),
        "rule": (
            "atomic creation consumes this candidate's only full calibration "
            "attempt; crash, FAIL, alternate output path, or concurrent launch "
            "cannot be retried at the same candidate identity"
        ),
    }
    artifact = {**core, "reservation_id": canonical_sha256(core)}
    _atomic_create_json(reservation_path, artifact)
    return {
        "candidate_id": candidate_id,
        "reservation_path": str(reservation_path),
        "reservation_sha256": sha256_file(reservation_path),
        "reservation_id": artifact["reservation_id"],
        "receipt_path": str(receipt_path),
        "run_dir": str(run_dir),
        "output_path": str(result_path),
    }


def finalize_candidate_receipt(
    binding: dict[str, Any], *, status: str,
    result_path: Path | None, traces: list[dict[str, Any]],
    error: str | None = None,
) -> dict[str, str]:
    require(status in {"PASS", "FAIL", "EXCEPTION"},
            f"invalid calibration terminal status {status!r}")
    reservation_path = Path(binding["reservation_path"])
    require(reservation_path.is_file()
            and sha256_file(reservation_path) == binding["reservation_sha256"],
            "candidate reservation drifted before terminal receipt")
    reservation = _load_json(reservation_path, "calibration reservation")
    require(reservation.get("reservation_id") == binding["reservation_id"],
            "candidate reservation identity drifted")
    result_binding = None
    if result_path is not None:
        require(result_path.is_file(), "terminal calibration result is missing")
        result_binding = {"path": str(result_path.resolve()),
                          "sha256": sha256_file(result_path)}
    core = {
        "format_version": FORMAT_VERSION,
        "artifact_type": "s4_qwen_calibration_receipt",
        "protocol_version": PROTOCOL_VERSION,
        "candidate_id": binding["candidate_id"],
        "attempt": 0,
        "reservation": {
            "path": str(reservation_path.resolve()),
            "sha256": binding["reservation_sha256"],
            "reservation_id": binding["reservation_id"],
        },
        "status": status,
        "result": result_binding,
        "traces": copy.deepcopy(traces),
        "error": error,
        "finished_utc": _utc_now(),
    }
    artifact = {**core, "receipt_id": canonical_sha256(core)}
    receipt_path = Path(binding["receipt_path"])
    _atomic_create_json(receipt_path, artifact)
    return {
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_id": artifact["receipt_id"],
    }


def stripped_history(assistant_history: dict[str, Any]) -> dict[str, Any]:
    """Remove only hidden reasoning; retain the exact visible assistant answer."""
    require(assistant_history.get("role") == "assistant"
            and isinstance(assistant_history.get("content"), str)
            and isinstance(assistant_history.get("reasoning_content"), str),
            "pre-probe assistant-history receipt is incomplete")
    return {"role": "assistant", "content": assistant_history["content"]}


def _call_receipt(
    row: dict[str, Any], record: dict[str, Any], payload: dict[str, Any] | None,
    run_dir: Path,
) -> dict[str, Any]:
    trace_path = Path(str(record.get("trace_path", "")))
    require(trace_path.is_file() and trace_path.parent.resolve() == run_dir.resolve(),
            f"{row['tag']}: serving trace escaped the calibration run")
    trace_sha = sha256_file(trace_path)
    require(record.get("trace_sha256") == trace_sha,
            f"{row['tag']}: serving trace hash mismatch")
    require(record.get("tag") == row["tag"] and record.get("seed") == row["seed"],
            f"{row['tag']}: serving receipt differs from call plan")
    require(record.get("sampler") == OFFICIAL_THINKING_SAMPLER
            and record.get("reasoning_effort") == "xhigh"
            and record.get("preserve_thinking") is True
            and record.get("max_tokens") == ANSWER_TOKENS,
            f"{row['tag']}: non-production serving parameters")
    raw = record.get("raw_response")
    require(isinstance(raw, str), f"{row['tag']}: raw response is absent")
    messages = copy.deepcopy(record.get("messages"))
    require(isinstance(messages, list), f"{row['tag']}: message receipt is absent")
    reasoning_chars = 0
    for message in messages:
        if isinstance(message, dict) and "reasoning_content" in message:
            reasoning = message.pop("reasoning_content")
            require(isinstance(reasoning, str),
                    f"{row['tag']}: reasoning_content is not text")
            reasoning_chars += len(reasoning)
    return {
        **copy.deepcopy(row),
        "trace": {"path": str(trace_path), "sha256": trace_sha},
        "raw_response_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "prompt_sha256": record.get("prompt_sha256"),
        "messages_sha256": record.get("messages_sha256"),
        "messages_without_reasoning_sha256": hashlib.sha256(json.dumps(
            messages, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest(),
        "history_reasoning_chars": reasoning_chars,
        "image_sha256s": [item.get("sha256") for item in record.get("images", [])],
        "completeness": record.get("completeness"),
        "payload_present": payload is not None and record.get("payload_present") is True,
        "schema_errors": copy.deepcopy(record.get("schema_errors")),
        "finish_reason": record.get("finish_reason"),
        "expanded_prompt_tokens": record.get("expanded_prompt_tokens"),
        "output_tokens": record.get("output_tokens"),
    }


def evaluate_calibration(
    call_plan: list[dict[str, Any]], receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Mechanical serving verdict only; causal-goal answers remain blind."""
    require(len(call_plan) == CALL_BUDGET and len(receipts) == CALL_BUDGET,
            "calibration requires exactly eleven planned and observed calls")
    expected = {row["tag"]: row for row in call_plan}
    actual = {row.get("tag"): row for row in receipts}
    require(len(actual) == CALL_BUDGET and set(actual) == set(expected),
            "calibration receipt inventory differs from the plan")
    for tag, planned in expected.items():
        observed = actual[tag]
        require(observed.get("seed") == planned["seed"]
                and observed.get("variant_id") == planned["variant_id"]
                and observed.get("role") == planned["role"],
                f"calibration receipt {tag} changed its planned binding")

    primary = next(row for row in receipts if row["role"] == "pre_primary"
                   and row["variant_index"] == 0)
    repeat = next(row for row in receipts if row["role"] == "pre_same_seed_repeat")
    different = next(row for row in receipts if row["role"] == "pre_different_seed")

    def same_input(left: dict[str, Any], right: dict[str, Any]) -> bool:
        return all(left.get(key) == right.get(key) for key in (
            "prompt_sha256", "messages_sha256", "image_sha256s",
        ))

    reproducible = (
        primary["seed"] == repeat["seed"]
        and same_input(primary, repeat)
        and primary.get("raw_response_sha256") == repeat.get("raw_response_sha256")
    )
    different_seed_live = (
        primary["seed"] != different["seed"]
        and same_input(primary, different)
        and primary.get("raw_response_sha256") != different.get("raw_response_sha256")
    )

    variant_ids = sorted({row["variant_id"] for row in call_plan})
    require(len(variant_ids) == sentinels.ACTIVE_VARIANTS,
            "calibration plan must contain exactly three active fixtures")
    pair_checks: list[dict[str, Any]] = []
    for variant_id in variant_ids:
        stripped = next(row for row in receipts
                        if row["variant_id"] == variant_id
                        and row["role"] == "post_stripped")
        preserved = next(row for row in receipts
                         if row["variant_id"] == variant_id
                         and row["role"] == "post_preserved")
        matched = stripped["seed"] == preserved["seed"]
        no_completeness_regression = (
            stripped.get("completeness") != "complete"
            or preserved.get("completeness") == "complete"
        )
        no_schema_regression = (
            not stripped.get("payload_present") or preserved.get("payload_present") is True
        )
        matched_context_except_reasoning = (
            stripped.get("messages_without_reasoning_sha256")
            == preserved.get("messages_without_reasoning_sha256")
            and stripped.get("image_sha256s") == preserved.get("image_sha256s")
            and stripped.get("history_reasoning_chars") == 0
            and type(preserved.get("history_reasoning_chars")) is int
            and preserved["history_reasoning_chars"] > 0
        )
        pair_checks.append({
            "variant_id": variant_id,
            "matched_seed": matched,
            "matched_context_except_reasoning": matched_context_except_reasoning,
            "no_completeness_regression": no_completeness_regression,
            "no_schema_regression": no_schema_regression,
            "pass": (matched and matched_context_except_reasoning
                     and no_completeness_regression and no_schema_regression),
        })

    truncated = [row["tag"] for row in receipts
                 if row.get("completeness") == "truncated"]
    all_complete = all(row.get("completeness") == "complete" for row in receipts)
    all_schema_valid = all(row.get("payload_present") is True
                           and not row.get("schema_errors") for row in receipts)
    passed = (
        reproducible and different_seed_live and not truncated
        and all_complete and all_schema_valid
        and len(pair_checks) == sentinels.ACTIVE_VARIANTS
        and all(row["pass"] for row in pair_checks)
    )
    return {
        "status": "PASS" if passed else "FAIL",
        "pass": passed,
        "same_seed_raw_reproducible": reproducible,
        "different_seed_raw_changed": different_seed_live,
        "all_calls_complete": all_complete,
        "all_calls_schema_valid": all_schema_valid,
        "reasoning_history_pairs": pair_checks,
        "truncated_call_tags": truncated,
        "manual_truncation_escalation": {
            "eligible_call_tags": truncated,
            "automatic": False,
            "max_tokens": MANUAL_TRUNCATION_TOKENS,
            "maximum_extra_attempts_per_exact_call": 1,
        },
        "semantic_goal_scoring": "NOT_PERFORMED_BY_THIS_HARNESS",
    }


def _trace_receipt_projection(
    row: dict[str, Any], trace: dict[str, Any], *, run_dir: Path,
    serving_identity: dict[str, Any], asset_files: dict[str, str], fixture_root: Path,
) -> dict[str, Any]:
    tag = row["tag"]
    trace_binding = row.get("trace") or {}
    trace_path = Path(str(trace_binding.get("path", ""))).resolve()
    require(trace_path == (run_dir / f"{tag}.trace.json").resolve()
            and trace_path.is_file()
            and sha256_file(trace_path) == trace_binding.get("sha256"),
            f"{tag}: fixed serving-trace binding is invalid")
    _require_read_only(trace_path, f"{tag} trace")
    require(trace.get("tag") == tag and trace.get("trace_tag") == tag
            and trace.get("seed") == row["seed"],
            f"{tag}: trace call identity drift")
    round_index, round_kind, text_cap = _round_kind(row["role"])
    require(trace.get("round_index") == round_index
            and trace.get("round_kind") == round_kind
            and trace.get("input_text_token_cap") == text_cap,
            f"{tag}: trace round/text-cap drift")
    require(trace.get("sampler") == OFFICIAL_THINKING_SAMPLER
            and trace.get("reasoning_effort") == "xhigh"
            and trace.get("preserve_thinking") is True
            and trace.get("max_tokens") == ANSWER_TOKENS
            and trace.get("native_context_tokens") == srun.NATIVE_CONTEXT_TOKENS
            and trace.get("serving_identity") == serving_identity,
            f"{tag}: trace serving parameters drift")

    messages = trace.get("messages")
    require(isinstance(messages, list), f"{tag}: trace messages are absent")
    messages_sha = canonical_sha256(messages)
    require(trace.get("messages_sha256") == messages_sha
            and row.get("messages_sha256") == messages_sha,
            f"{tag}: message receipt drift")
    projected_messages = copy.deepcopy(messages)
    reasoning_chars = 0
    for message in projected_messages:
        if isinstance(message, dict) and "reasoning_content" in message:
            reasoning = message.pop("reasoning_content")
            require(isinstance(reasoning, str),
                    f"{tag}: reasoning_content is not text")
            reasoning_chars += len(reasoning)
    require(row.get("messages_without_reasoning_sha256")
            == canonical_sha256(projected_messages)
            and row.get("history_reasoning_chars") == reasoning_chars,
            f"{tag}: reasoning-history projection drift")
    prompt = trace.get("prompt")
    require(isinstance(prompt, str)
            and hashlib.sha256(prompt.encode()).hexdigest()
            == trace.get("prompt_sha256") == row.get("prompt_sha256"),
            f"{tag}: serialized prompt receipt drift")

    image_sha256s: list[str] = []
    images = trace.get("images")
    require(isinstance(images, list), f"{tag}: trace image inventory is absent")
    for image in images:
        require(isinstance(image, dict) and isinstance(image.get("path"), str),
                f"{tag}: malformed image receipt")
        path = Path(image["path"]).resolve()
        try:
            relative = str(path.relative_to(fixture_root.resolve()))
        except ValueError as exc:
            raise RuntimeError(f"{tag}: image escaped development fixtures: {path}") from exc
        require(relative in asset_files and path.is_file()
                and sha256_file(path) == asset_files[relative] == image.get("sha256"),
                f"{tag}: image is not bound to the development asset manifest")
        image_sha256s.append(image["sha256"])
    require(row.get("image_sha256s") == image_sha256s,
            f"{tag}: result image projection drift")
    grid = trace.get("image_grid_thw")
    require(isinstance(grid, list) and len(grid) == len(images),
            f"{tag}: processor image-grid inventory drift")
    visual_tokens = 0
    for grid_row in grid:
        require(isinstance(grid_row, list) and len(grid_row) == 3
                and all(type(value) is int and value > 0 for value in grid_row),
                f"{tag}: invalid processor image grid")
        merged = grid_row[0] * grid_row[1] * grid_row[2]
        require(merged % 4 == 0, f"{tag}: non-integral visual-token grid")
        visual_tokens += merged // 4
    expanded = trace.get("expanded_prompt_tokens")
    derived = trace.get("derived_text_tokens")
    require(type(expanded) is int and type(derived) is int
            and expanded == derived + visual_tokens
            and trace.get("visual_tokens") == visual_tokens
            and derived <= text_cap
            and expanded + ANSWER_TOKENS <= srun.NATIVE_CONTEXT_TOKENS,
            f"{tag}: token/context accounting drift")

    raw = trace.get("raw")
    require(isinstance(raw, str) and raw == trace.get("raw_response"),
            f"{tag}: exact raw output is absent")
    full = "<think>" + raw
    closed = "</think>" in full
    think = full.split("<think>", 1)[-1].split("</think>", 1)[0]
    answer = full.split("</think>", 1)[-1].strip() if closed else ""
    parsed = srun.extract_final_json(answer) if closed else None
    schema_errors = srun.validate_answer(parsed) if parsed is not None else []
    payload = parsed if parsed is not None and not schema_errors else None
    stats = trace.get("stats")
    require(isinstance(stats, dict), f"{tag}: generation stats are absent")
    completeness = probe.classify_completion(
        stats.get("finish_reason"), stats.get("generation_tokens"),
        ANSWER_TOKENS, closed, parsed,
    )
    if completeness == "complete" and schema_errors:
        completeness = "malformed_schema"
    prompt_match = stats.get("prompt_tokens") == expanded
    token_match = (
        stats.get("total_tokens")
        == stats.get("prompt_tokens") + stats.get("generation_tokens")
        if type(stats.get("prompt_tokens")) is int
        and type(stats.get("generation_tokens")) is int else False
    )
    require(trace.get("generator_prompt_tokens") == stats.get("prompt_tokens")
            and trace.get("input_tokens") == stats.get("prompt_tokens")
            and trace.get("output_tokens") == stats.get("generation_tokens")
            and trace.get("finish_reason") == stats.get("finish_reason"),
            f"{tag}: generation-stat projection drift")
    require(trace.get("completion_contains_close") is closed
            and trace.get("think") == think and trace.get("answer") == answer
            and trace.get("parsed_payload") == parsed
            and trace.get("schema_errors") == schema_errors
            and trace.get("payload_present") is (payload is not None)
            and trace.get("completeness") == completeness
            and trace.get("prompt_tokens_match") is prompt_match is True
            and trace.get("token_accounting_match") is token_match is True
            and trace.get("assistant_history") == {
                "role": "assistant", "content": answer,
                "reasoning_content": think,
            }, f"{tag}: trace is not an exact projection of raw generation")
    projection = {
        **copy.deepcopy({key: row[key] for key in (
            "order", "tag", "variant_index", "variant_id", "role",
            "history_condition", "seed",
        )}),
        "trace": copy.deepcopy(trace_binding),
        "raw_response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "prompt_sha256": trace["prompt_sha256"],
        "messages_sha256": messages_sha,
        "messages_without_reasoning_sha256": canonical_sha256(projected_messages),
        "history_reasoning_chars": reasoning_chars,
        "image_sha256s": image_sha256s,
        "completeness": completeness,
        "payload_present": payload is not None,
        "schema_errors": schema_errors,
        "finish_reason": trace.get("finish_reason"),
        "expanded_prompt_tokens": expanded,
        "output_tokens": trace.get("output_tokens"),
    }
    require(projection == row, f"{tag}: result call receipt differs from trace")
    return projection


def _valid_payload_from_trace(trace: dict[str, Any]) -> dict[str, Any] | None:
    raw = trace.get("raw")
    require(isinstance(raw, str), "trace raw completion is absent")
    full = "<think>" + raw
    if "</think>" not in full:
        return None
    answer = full.split("</think>", 1)[-1].strip()
    parsed = srun.extract_final_json(answer)
    return parsed if parsed is not None and not srun.validate_answer(parsed) else None


def _validate_exact_call_contexts(
    *, plan: list[dict[str, Any]], trace_by_tag: dict[str, dict[str, Any]],
    manifest: dict[str, Any], fixture_root: Path, base_seed: int,
) -> None:
    """Rebuild all eleven model inputs; result artifacts cannot inject gold/text."""
    active = manifest.get("active")
    require(isinstance(active, list) and len(active) == sentinels.ACTIVE_VARIANTS,
            "development manifest lacks three active carrier records")
    by_id = {record.get("variant_id"): record for record in active}
    for variant in development_variants(base_seed):
        variant_id = variant["variant_id"]
        record = by_id.get(variant_id)
        require(isinstance(record, dict),
                f"development manifest lacks active fixture {variant_id}")
        fixture = sentinels.build_active_variant("dev", variant["index"], base_seed)
        fixture.pop("gold", None)
        initial_messages, initial_images, carrier = sentinels._active_initial_turn(  # noqa: SLF001
            fixture_root, record, fixture,
        )
        primary_row = next(row for row in plan
                           if row["variant_id"] == variant_id
                           and row["role"] == "pre_primary")
        primary_trace = trace_by_tag[primary_row["tag"]]
        primary_payload = _valid_payload_from_trace(primary_trace)
        for row in (item for item in plan
                    if item["variant_id"] == variant_id
                    and item["role"].startswith("pre_")):
            trace = trace_by_tag[row["tag"]]
            require(trace.get("messages") == initial_messages
                    and [Path(image["path"]).resolve()
                         for image in trace.get("images", [])]
                    == [path.resolve() for path in initial_images],
                    f"{row['tag']}: pre-probe context differs from dev carrier")
        carrier_path = fixture_root / record["carrier_file"]
        feedback, feedback_images, _audit = sentinels._active_probe_feedback(  # noqa: SLF001
            fixture, carrier, primary_payload, carrier_path,
        )
        assistant_history = primary_trace.get("assistant_history")
        require(isinstance(assistant_history, dict),
                f"{variant_id}: primary assistant history is absent")
        for row in (item for item in plan
                    if item["variant_id"] == variant_id
                    and item["role"].startswith("post_")):
            history = (copy.deepcopy(assistant_history)
                       if row["history_condition"] == "preserved"
                       else stripped_history(assistant_history))
            expected_messages = copy.deepcopy(initial_messages)
            expected_messages.append(history)
            expected_messages.append({"role": "user", "content": feedback})
            expected_images = list(initial_images) + list(feedback_images)
            trace = trace_by_tag[row["tag"]]
            require(trace.get("messages") == expected_messages
                    and [Path(image["path"]).resolve()
                         for image in trace.get("images", [])]
                    == [path.resolve() for path in expected_images],
                    f"{row['tag']}: post-probe context differs beyond reasoning condition")


def validate_calibration_result(
    result_path: Path, *, model: Path | None = None,
    fixture_root: Path = sentinels.DEV_ROOT,
    attempt_root: Path = ATTEMPT_ROOT,
    require_live_environment: bool = True,
) -> dict[str, Any]:
    """Fail-closed pre-freeze authority for one immutable calibration attempt.

    A hard freeze caller passes ``model`` and leaves ``require_live_environment``
    true.  The false setting exists solely for no-model unit tests of already
    bound artifacts.
    """
    resolved_result = result_path.resolve()
    result = _load_json(resolved_result, "calibration result")
    _require_read_only(resolved_result, "calibration result")
    require(result.get("format_version") == FORMAT_VERSION
            and result.get("protocol_version") == PROTOCOL_VERSION
            and result.get("artifact_type")
            == "s4_qwen_development_calibration_result",
            "calibration result version/type mismatch")
    candidate = result.get("candidate")
    require(isinstance(candidate, dict), "calibration result lacks candidate binding")
    require(set(candidate) == {
        "format_version", "artifact_type", "protocol_version", "git",
        "critical_scripts", "checkpoint_identity", "development_manifest",
        "plan_sha256", "request_prompt_sha256", "sampler", "reasoning_effort",
        "preserve_thinking", "answer_tokens", "native_context_tokens",
        "kaggle_submissions",
    } and candidate.get("format_version") == FORMAT_VERSION
        and candidate.get("artifact_type") == "s4_qwen_calibration_candidate"
        and candidate.get("protocol_version") == PROTOCOL_VERSION,
        "calibration candidate schema/type is invalid")
    candidate_id = canonical_sha256(candidate)
    require(result.get("candidate_id") == candidate_id,
            "calibration candidate digest is invalid")
    reservation_path = (attempt_root / f"{candidate_id}.reservation.json").resolve()
    receipt_path = (attempt_root / f"{candidate_id}.receipt.json").resolve()
    require(Path(str(result.get("reservation_path", ""))).resolve() == reservation_path
            and Path(str(result.get("expected_receipt_path", ""))).resolve() == receipt_path,
            "result substituted non-fixed reservation/receipt paths")
    require(reservation_path.is_file() and receipt_path.is_file(),
            "one-shot calibration reservation/receipt is missing")
    _require_read_only(reservation_path, "calibration reservation")
    _require_read_only(receipt_path, "calibration receipt")
    reservation = _load_json(reservation_path, "calibration reservation")
    reservation_core = {key: value for key, value in reservation.items()
                        if key != "reservation_id"}
    expected_reservation_keys = {
        "format_version", "artifact_type", "protocol_version", "candidate_id",
        "candidate", "attempt", "run_dir", "output_path", "reserved_utc",
        "rule", "reservation_id",
    }
    require(set(reservation) == expected_reservation_keys
            and reservation.get("artifact_type")
            == "s4_qwen_calibration_reservation"
            and reservation.get("candidate_id") == candidate_id
            and reservation.get("candidate") == candidate
            and reservation.get("attempt") == 0
            and reservation.get("reservation_id")
            == canonical_sha256(reservation_core) == result.get("reservation_id")
            and sha256_file(reservation_path) == result.get("reservation_sha256"),
            "calibration reservation schema/content binding is invalid")
    run_dir = Path(str(reservation.get("run_dir", ""))).resolve()
    require(resolved_result == Path(str(reservation.get("output_path", ""))).resolve()
            and resolved_result.parent == run_dir and run_dir.is_dir()
            and run_dir.stat().st_mode & 0o222 == 0,
            "calibration result/run directory differs from its reservation")

    plan = plan_document(candidate["development_manifest"]["base_seed"])
    require(set(result) == set(plan) | {
        "artifact_type", "created_utc", "candidate_id", "candidate",
        "reservation_path", "reservation_sha256", "reservation_id",
        "expected_receipt_path", "script_sha256",
        "sentinel_generator_sha256", "development_asset_manifest",
        "serving_identity", "run_dir", "completed_utc", "calls",
        "evaluation", "gold_access",
    }, "calibration result has missing/unknown fields")
    require(result.get("call_plan") == plan["call_plan"]
            and candidate.get("plan_sha256") == canonical_sha256(plan)
            and candidate.get("sampler") == OFFICIAL_THINKING_SAMPLER
            and candidate.get("reasoning_effort") == "xhigh"
            and candidate.get("preserve_thinking") is True
            and candidate.get("answer_tokens") == ANSWER_TOKENS
            and candidate.get("native_context_tokens") == srun.NATIVE_CONTEXT_TOKENS
            and candidate.get("request_prompt_sha256")
            == hashlib.sha256(srun.REQUEST.encode()).hexdigest()
            and candidate.get("kaggle_submissions") == 0,
            "calibration candidate plan/serving contract drift")
    require(candidate.get("critical_scripts") == {
        relative: sha256_file(ROOT / relative) for relative in CRITICAL_SCRIPTS
    }, "calibration candidate code differs from the live pre-freeze code")

    manifest, manifest_path = verify_development_assets(
        fixture_root, base_seed=plan["base_seed"],
    )
    manifest_binding = candidate.get("development_manifest") or {}
    require(fixture_root.resolve() == sentinels.DEV_ROOT.resolve()
            and manifest_path.resolve()
            == Path(str(manifest_binding.get("path", ""))).resolve()
            and sha256_file(manifest_path) == manifest_binding.get("sha256")
            and manifest_binding.get("namespace") == "dev"
            and manifest_binding.get("generator_sha256") == manifest["generator_sha256"]
            and manifest_binding.get("asset_inventory_sha256")
            == canonical_sha256(manifest["asset_files"]),
            "calibration development-manifest binding drift")
    require(result.get("development_asset_manifest") == {
        "path": str(manifest_path.resolve()), "sha256": sha256_file(manifest_path),
    } and result.get("script_sha256") == sha256_file(Path(__file__))
        and result.get("sentinel_generator_sha256")
        == sha256_file(Path(sentinels.__file__))
        and Path(str(result.get("run_dir", ""))).resolve() == run_dir,
        "result script/generator/dev-manifest/run binding drift")
    git = candidate.get("git")
    require(isinstance(git, dict) and git.get("dirty") is False
            and git.get("status") == [] and isinstance(git.get("commit"), str),
            "calibration candidate is not bound to a clean commit")
    checkpoint = candidate.get("checkpoint_identity")
    require(isinstance(checkpoint, dict) and checkpoint.get("git") == git,
            "calibration checkpoint/git binding is incomplete")
    if require_live_environment:
        require(model is not None,
                "hard calibration validation requires the live model path")
        require(probe.capture_git_state() == git,
                "live clean git state differs from the calibration candidate")
        live_checkpoint = _stable_checkpoint_identity(
            probe.fingerprint(model, git_state=git)
        )
        require(live_checkpoint == checkpoint,
                "live checkpoint/runtime differs from calibration candidate")
    expected_serving_identity = {
        "scope": "pinned local checkpoint conversion, not the BF16 model family",
        "verified_shards": True,
        "checkpoint_sha256": checkpoint.get("checkpoint_sha256"),
        "candidate_checkpoint_identity_sha256": canonical_sha256(checkpoint),
    }
    require(result.get("serving_identity") == expected_serving_identity,
            "result serving identity differs from candidate checkpoint")

    calls = result.get("calls")
    require(isinstance(calls, list) and len(calls) == CALL_BUDGET,
            "result lacks the exact eleven-call inventory")
    projections: list[dict[str, Any]] = []
    trace_by_tag: dict[str, dict[str, Any]] = {}
    for planned, row in zip(plan["call_plan"], calls):
        require(all(row.get(key) == planned[key] for key in planned),
                f"call order/binding drift at {planned['tag']}")
        trace_path = Path(str((row.get("trace") or {}).get("path", "")))
        trace = _load_json(trace_path, f"trace {planned['tag']}")
        trace_by_tag[planned["tag"]] = trace
        projections.append(_trace_receipt_projection(
            row, trace, run_dir=run_dir,
            serving_identity=expected_serving_identity,
            asset_files=manifest["asset_files"], fixture_root=fixture_root,
        ))
    _validate_exact_call_contexts(
        plan=plan["call_plan"], trace_by_tag=trace_by_tag,
        manifest=manifest, fixture_root=fixture_root,
        base_seed=plan["base_seed"],
    )
    evaluation = evaluate_calibration(plan["call_plan"], projections)
    require(result.get("evaluation") == evaluation and evaluation["pass"] is True,
            "calibration mechanical verdict is not an independently derived PASS")
    require(result.get("gold_access") == {
        "semantic_gold_consulted": False,
        "gold_files_opened_by_calibration_harness": False,
        "semantic_adjudication": "separate blind process required",
    }, "calibration result makes an invalid gold-access claim")

    expected_files = {"STARTED.json", "RESULT.json"} | {
        f"{row['tag']}.trace.json" for row in plan["call_plan"]
    }
    require({path.name for path in run_dir.iterdir() if path.is_file()} == expected_files,
            "calibration run directory has missing/extra artifacts")
    started_path = run_dir / "STARTED.json"
    _require_read_only(started_path, "calibration STARTED")
    started = _load_json(started_path, "calibration STARTED")
    require(started.get("artifact_type")
            == "s4_qwen_development_calibration_started"
            and started.get("candidate_id") == candidate_id
            and started.get("candidate") == candidate
            and started.get("reservation_id") == reservation["reservation_id"]
            and started.get("call_plan") == plan["call_plan"],
            "STARTED artifact differs from candidate/reservation/plan")

    receipt = _load_json(receipt_path, "calibration receipt")
    require(set(receipt) == {
        "format_version", "artifact_type", "protocol_version", "candidate_id",
        "attempt", "reservation", "status", "result", "traces", "error",
        "finished_utc", "receipt_id",
    }, "calibration receipt has missing/unknown fields")
    receipt_core = {key: value for key, value in receipt.items() if key != "receipt_id"}
    require(receipt.get("artifact_type") == "s4_qwen_calibration_receipt"
            and receipt.get("candidate_id") == candidate_id
            and receipt.get("attempt") == 0
            and receipt.get("status") == "PASS"
            and receipt.get("reservation") == {
                "path": str(reservation_path),
                "sha256": sha256_file(reservation_path),
                "reservation_id": reservation["reservation_id"],
            }
            and receipt.get("result") == {
                "path": str(resolved_result), "sha256": sha256_file(resolved_result),
            }
            and receipt.get("traces") == [row["trace"] for row in calls]
            and receipt.get("error") is None
            and receipt.get("receipt_id") == canonical_sha256(receipt_core),
            "terminal calibration receipt is invalid or non-PASS")
    reservation_time = _parse_utc(reservation["reserved_utc"], "reservation time")
    started_time = _parse_utc(result["created_utc"], "calibration start time")
    completed_time = _parse_utc(result["completed_utc"], "calibration completion time")
    receipt_time = _parse_utc(receipt["finished_utc"], "receipt finish time")
    require(reservation_time <= started_time <= completed_time <= receipt_time,
            "calibration reservation/start/completion/receipt chronology is invalid")
    return {
        "candidate_id": candidate_id,
        "git_commit": git["commit"],
        "checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "development_manifest_sha256": manifest_binding["sha256"],
        "plan_sha256": candidate["plan_sha256"],
        "result_path": str(resolved_result),
        "result_sha256": sha256_file(resolved_result),
        "reservation_path": str(reservation_path),
        "reservation_sha256": sha256_file(reservation_path),
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256_file(receipt_path),
        "status": "PASS",
    }


# ------------------------------------------------------- blind semantic follow-up


def _semantic_key_commitment(blinding_key: bytes) -> str:
    require(isinstance(blinding_key, bytes) and len(blinding_key) >= 32,
            "semantic blinding key must contain at least 32 bytes")
    return hashlib.sha256(blinding_key).hexdigest()


def _semantic_hmac(blinding_key: bytes, *parts: Any) -> str:
    _semantic_key_commitment(blinding_key)
    payload = "\x00".join(
        [SEMANTIC_PROTOCOL_VERSION, *(str(part) for part in parts)]
    ).encode("utf-8")
    return hmac.new(blinding_key, payload, hashlib.sha256).hexdigest()


def _semantic_source_rows(
    calibration_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Reopen and independently parse the exact six post-probe traces."""
    rows: list[dict[str, Any]] = []
    calls = calibration_result.get("calls")
    require(isinstance(calls, list), "calibration result lacks call receipts")
    for call in calls:
        if not isinstance(call, dict) or not str(call.get("role", "")).startswith("post_"):
            continue
        trace_binding = call.get("trace") or {}
        trace_path = Path(str(trace_binding.get("path", ""))).resolve()
        require(trace_path.is_file()
                and sha256_file(trace_path) == trace_binding.get("sha256"),
                "semantic source trace binding is invalid")
        trace = _load_json(trace_path, "semantic source trace")
        raw = trace.get("raw")
        require(isinstance(raw, str) and raw == trace.get("raw_response"),
                "semantic source trace has no exact raw response")
        full = "<think>" + raw
        require("</think>" in full,
                "semantic source response has no closed reasoning section")
        answer = full.split("</think>", 1)[-1].strip()
        payload = srun.extract_final_json(answer)
        require(payload is not None and not srun.validate_answer(payload)
                and trace.get("parsed_payload") == payload
                and trace.get("payload_present") is True,
                "semantic source response is not an independently parsed valid payload")
        require(call.get("raw_response_sha256")
                == hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "semantic source raw-response digest drift")
        rows.append({
            "variant_index": call.get("variant_index"),
            "variant_id": call.get("variant_id"),
            "role": call.get("role"),
            "history_condition": call.get("history_condition"),
            "tag": call.get("tag"),
            "trace_path": str(trace_path),
            "trace_sha256": trace_binding.get("sha256"),
            "raw_response_sha256": call.get("raw_response_sha256"),
            "parsed_payload_sha256": canonical_sha256(payload),
            "payload": payload,
        })
    require(len(rows) == 2 * sentinels.ACTIVE_VARIANTS,
            "semantic adjudication requires exactly six post-probe traces")
    require(all(type(row["variant_index"]) is int
                and isinstance(row["variant_id"], str) for row in rows),
            "semantic source variant bindings are malformed")
    for variant_index in range(sentinels.ACTIVE_VARIANTS):
        pair = [row for row in rows if row["variant_index"] == variant_index]
        require(len(pair) == 2
                and {row["role"] for row in pair}
                == {"post_stripped", "post_preserved"}
                and {row["history_condition"] for row in pair}
                == {"stripped", "preserved"}
                and len({row["variant_id"] for row in pair}) == 1,
                f"semantic source pair {variant_index} is not the exact matched pair")
    require(len({row["trace_sha256"] for row in rows}) == len(rows),
            "semantic source traces are not unique")
    return rows


def _semantic_model_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_best_goal": copy.deepcopy(payload["best_goal"]),
        "model_hypotheses": copy.deepcopy(payload["hypotheses"]),
        "model_goal_directed_plan": copy.deepcopy(payload["goal_directed_plan"]),
    }


def _semantic_plan_budget(fixture: dict[str, Any]) -> int:
    optimal = sentinels._route(  # noqa: SLF001
        fixture["layout"], ["zone_a", "zone_b"],
    )
    require(optimal, "semantic fixture has no reference completion route")
    return 2 * len(optimal)


def _replay_semantic_plan(
    fixture: dict[str, Any], plan: Any, *, action_budget: int,
) -> dict[str, Any]:
    """Replay from the fixed reset without repair, using the Axis-5 budget rule."""
    require(type(action_budget) is int and action_budget > 0,
            "semantic plan action budget must be positive")
    actions, schema_error = [], None
    if not isinstance(plan, list):
        schema_error = "plan is not a list"
    else:
        for index, step in enumerate(plan):
            action = step.get("action") if isinstance(step, dict) else None
            if not isinstance(step, dict) or set(step) != {"action"} \
                    or not isinstance(action, dict) \
                    or set(action) != {"id", "click"}:
                schema_error = f"step {index} has invalid action schema"
                break
            action_id = action.get("id")
            click = action.get("click")
            # Synthetic sentinels expose A1..A5 through the pilot schema as
            # ids 0..4.  They have no click action.  Do not reuse the real-game
            # id verbatim: id 0 means synthetic A1, not synthetic A0.
            if type(action_id) is not int or not 0 <= action_id <= 4 \
                    or click is not None:
                schema_error = f"step {index} has invalid action/click values"
                break
            actions.append(f"A{action_id + 1}")
    completed_at: int | None = None
    if schema_error is None:
        game = sentinels.ChargeOrderGame(fixture["layout"])
        for index, action in enumerate(actions[:action_budget], start=1):
            row = game.step(action)
            if row["completed"]:
                completed_at = index
                break
    return {
        "start_state": "fresh deterministic reset",
        "action_budget": action_budget,
        "submitted_actions": len(actions),
        "executed_actions": min(len(actions), action_budget),
        "schema_error": schema_error,
        "completed_at_action": completed_at,
        "pass": schema_error is None and completed_at is not None,
        "silent_repair": False,
    }


def _assert_semantic_blindness(
    worksheet: dict[str, Any], source_rows: list[dict[str, Any]],
) -> None:
    # The model may naturally use words such as "preserved" when describing
    # game state.  Blindness constrains harness metadata, not answer prose.
    # Redact every model/reference semantic field before checking labels, call
    # tags, paths, and source-only schema keys.
    structural = copy.deepcopy(worksheet)
    for pair in structural.get("pairs", []):
        reference = pair.get("reference") if isinstance(pair, dict) else None
        if isinstance(reference, dict):
            reference["true_goal"] = "<reference-content>"
            reference["necessary_constraints"] = ["<reference-content>"]
        for sample in pair.get("samples", []) if isinstance(pair, dict) else []:
            if not isinstance(sample, dict):
                continue
            for key in (
                "model_best_goal", "model_hypotheses", "model_goal_directed_plan",
            ):
                sample[key] = "<model-content>"
    serialized = json.dumps(
        structural, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).casefold()
    for forbidden in (
        '"stripped"', '"preserved"', '"history_condition"', '"trace_path"',
        '"tag"', '"role"', '"order"',
    ):
        require(forbidden not in serialized,
                f"blind semantic worksheet leaks condition label {forbidden!r}")
    for row in source_rows:
        for forbidden in (row["tag"], row["trace_path"]):
            require(str(forbidden).casefold() not in serialized,
                    "blind semantic worksheet leaks a call tag or trace path")


def _build_blind_semantic_document(
    *, calibration_result_path: Path, calibration_result: dict[str, Any],
    calibration_binding: dict[str, Any], blinding_key: bytes,
    created_utc: str,
) -> dict[str, Any]:
    source_rows = _semantic_source_rows(calibration_result)
    base_seed = calibration_result["candidate"]["development_manifest"]["base_seed"]
    pairs: list[tuple[str, dict[str, Any]]] = []
    for variant_index in range(sentinels.ACTIVE_VARIANTS):
        pair_rows = [row for row in source_rows
                     if row["variant_index"] == variant_index]
        fixture = sentinels.build_active_variant("dev", variant_index, base_seed)
        require({row["variant_id"] for row in pair_rows} == {fixture["variant_id"]},
                "semantic fixture regeneration changed a variant identity")
        action_budget = _semantic_plan_budget(fixture)
        pair_id = "QP" + _semantic_hmac(
            blinding_key, calibration_binding["candidate_id"],
            "pair", fixture["variant_id"],
        )[:20]
        samples: list[tuple[str, dict[str, Any]]] = []
        for row in pair_rows:
            sample_id = "QS" + _semantic_hmac(
                blinding_key, calibration_binding["candidate_id"],
                "sample", row["trace_sha256"],
            )[:20]
            sample = {
                "sample_id": sample_id,
                "trace_sha256": row["trace_sha256"],
                "raw_response_sha256": row["raw_response_sha256"],
                "parsed_payload_sha256": row["parsed_payload_sha256"],
                **_semantic_model_fields(row["payload"]),
                "mechanical_plan_replay": _replay_semantic_plan(
                    fixture, row["payload"]["goal_directed_plan"],
                    action_budget=action_budget,
                ),
                "verdict": {
                    "goal_correct_in_kind": None,
                    "constraints_by_item": [None, None],
                    "plan_executable": None,
                },
            }
            order = _semantic_hmac(
                blinding_key, calibration_binding["candidate_id"],
                "sample-order", row["trace_sha256"],
            )
            samples.append((order, sample))
        samples.sort(key=lambda item: item[0])
        gold = fixture["gold"]
        pair = {
            "pair_id": pair_id,
            "reference": {
                "true_goal": gold["true_goal"],
                "necessary_constraints": copy.deepcopy(gold["constraints"]),
                "plan_start_state": "fresh deterministic reset",
                "plan_action_budget": action_budget,
            },
            "samples": [sample for _order, sample in samples],
        }
        pair_order = _semantic_hmac(
            blinding_key, calibration_binding["candidate_id"],
            "pair-order", fixture["variant_id"],
        )
        pairs.append((pair_order, pair))
    pairs.sort(key=lambda item: item[0])
    worksheet = {
        "format_version": SEMANTIC_FORMAT_VERSION,
        "protocol_version": SEMANTIC_PROTOCOL_VERSION,
        "artifact_type": "s4_qwen_calibration_blind_semantic_worksheet",
        "created_utc": created_utc,
        "calibration_source": {
            "candidate_id": calibration_binding["candidate_id"],
            "result_sha256": sha256_file(calibration_result_path),
            "mechanical_status": calibration_binding["status"],
        },
        "blinding": {
            "method": "HMAC-SHA256 opaque identifiers and keyed permutation",
            "key_commitment_sha256": _semantic_key_commitment(blinding_key),
            "explicit_labels_present": False,
            "source_tags_or_paths_present": False,
        },
        "rubric": copy.deepcopy(SEMANTIC_RUBRIC),
        "pairs": [pair for _order, pair in pairs],
    }
    _assert_semantic_blindness(worksheet, source_rows)
    return worksheet


def reserve_semantic_attempt(
    calibration_binding: dict[str, Any], *, calibration_result_path: Path,
    blinding_key: bytes, output_root: Path = SEMANTIC_OUTPUT_ROOT,
    attempt_root: Path = SEMANTIC_ATTEMPT_ROOT,
) -> dict[str, str]:
    """Consume the only semantic-adjudication attempt for one calibration."""
    candidate_id = calibration_binding["candidate_id"]
    run_dir = (output_root / candidate_id).resolve()
    reservation_path = (attempt_root / f"{candidate_id}.reservation.json").resolve()
    receipt_path = (attempt_root / f"{candidate_id}.receipt.json").resolve()
    require(not run_dir.exists() and not reservation_path.exists()
            and not receipt_path.exists(),
            "semantic adjudication attempt 0 is already consumed")
    core = {
        "format_version": SEMANTIC_FORMAT_VERSION,
        "protocol_version": SEMANTIC_PROTOCOL_VERSION,
        "artifact_type": "s4_qwen_calibration_semantic_reservation",
        "candidate_id": candidate_id,
        "attempt": 0,
        "calibration_result": {
            "path": str(calibration_result_path.resolve()),
            "sha256": sha256_file(calibration_result_path),
        },
        "blinding_key_commitment_sha256": _semantic_key_commitment(blinding_key),
        "run_dir": str(run_dir),
        "worksheet_path": str(run_dir / "BLIND_WORKSHEET.json"),
        "judgments_path": str(run_dir / "JUDGMENTS.json"),
        "result_path": str(run_dir / "SEMANTIC_RESULT.json"),
        "reserved_utc": _utc_now(),
        "rule": (
            "attempt 0 is consumed before worksheet creation; alternate keys, "
            "paths, adjudicators, failures, and crashes cannot create a retry"
        ),
    }
    artifact = {**core, "reservation_id": canonical_sha256(core)}
    _atomic_create_json(reservation_path, artifact)
    return {
        "candidate_id": candidate_id,
        "reservation_path": str(reservation_path),
        "reservation_sha256": sha256_file(reservation_path),
        "reservation_id": artifact["reservation_id"],
        "receipt_path": str(receipt_path),
        "run_dir": str(run_dir),
        "worksheet_path": artifact["worksheet_path"],
        "judgments_path": artifact["judgments_path"],
        "result_path": artifact["result_path"],
    }


def create_blind_semantic_worksheet(
    calibration_result_path: Path, *, blinding_key: bytes,
    model: Path | None = None, fixture_root: Path = sentinels.DEV_ROOT,
    calibration_attempt_root: Path = ATTEMPT_ROOT,
    output_root: Path = SEMANTIC_OUTPUT_ROOT,
    semantic_attempt_root: Path = SEMANTIC_ATTEMPT_ROOT,
    require_live_environment: bool = True,
) -> tuple[dict[str, Any], Path]:
    """Create the only anonymous six-answer worksheet for this candidate."""
    require(not _is_within(output_root, sentinels.SEALED_R4),
            "semantic development artifacts may not enter the sealed r4 tree")
    binding = validate_calibration_result(
        calibration_result_path, model=model, fixture_root=fixture_root,
        attempt_root=calibration_attempt_root,
        require_live_environment=require_live_environment,
    )
    result = _load_json(calibration_result_path, "calibration result")
    output_root.mkdir(parents=True, exist_ok=True)
    reservation = reserve_semantic_attempt(
        binding, calibration_result_path=calibration_result_path,
        blinding_key=blinding_key, output_root=output_root,
        attempt_root=semantic_attempt_root,
    )
    run_dir = Path(reservation["run_dir"])
    run_dir.mkdir(parents=False, exist_ok=False)
    created = _utc_now()
    require(_parse_utc(result["completed_utc"], "calibration completion time")
            <= _parse_utc(created, "semantic worksheet creation time"),
            "semantic worksheet predates calibration completion")
    worksheet = _build_blind_semantic_document(
        calibration_result_path=calibration_result_path,
        calibration_result=result, calibration_binding=binding,
        blinding_key=blinding_key, created_utc=created,
    )
    path = Path(reservation["worksheet_path"])
    _atomic_create_json(path, worksheet)
    return worksheet, path


def _worksheet_samples(worksheet: dict[str, Any]) -> list[dict[str, Any]]:
    pairs = worksheet.get("pairs")
    require(isinstance(pairs, list) and len(pairs) == sentinels.ACTIVE_VARIANTS,
            "semantic worksheet must contain exactly three pairs")
    samples: list[dict[str, Any]] = []
    for pair in pairs:
        require(isinstance(pair, dict) and set(pair) == {
            "pair_id", "reference", "samples",
        }, "semantic worksheet pair schema is invalid")
        require(isinstance(pair.get("samples"), list)
                and len(pair["samples"]) == 2,
                "each semantic worksheet pair needs two samples")
        samples.extend(pair["samples"])
    return samples


def _validate_semantic_worksheet(
    worksheet: dict[str, Any], *, worksheet_path: Path,
    calibration_result_path: Path, calibration_result: dict[str, Any],
    calibration_binding: dict[str, Any], blinding_key: bytes | None = None,
) -> list[dict[str, Any]]:
    require(set(worksheet) == {
        "format_version", "protocol_version", "artifact_type", "created_utc",
        "calibration_source", "blinding", "rubric", "pairs",
    }, "semantic worksheet top-level schema is invalid")
    require(worksheet.get("format_version") == SEMANTIC_FORMAT_VERSION
            and worksheet.get("protocol_version") == SEMANTIC_PROTOCOL_VERSION
            and worksheet.get("artifact_type")
            == "s4_qwen_calibration_blind_semantic_worksheet",
            "semantic worksheet version/type mismatch")
    source = worksheet.get("calibration_source")
    require(source == {
        "candidate_id": calibration_binding["candidate_id"],
        "result_sha256": sha256_file(calibration_result_path),
        "mechanical_status": "PASS",
    }, "semantic worksheet calibration-source binding drift")
    require(worksheet.get("rubric") == SEMANTIC_RUBRIC,
            "semantic worksheet scoring rubric drift")
    blinding = worksheet.get("blinding")
    require(isinstance(blinding, dict)
            and blinding.get("method")
            == "HMAC-SHA256 opaque identifiers and keyed permutation"
            and blinding.get("explicit_labels_present") is False
            and blinding.get("source_tags_or_paths_present") is False
            and isinstance(blinding.get("key_commitment_sha256"), str)
            and len(blinding["key_commitment_sha256"]) == 64,
            "semantic worksheet blinding contract is invalid")
    if blinding_key is not None:
        require(blinding["key_commitment_sha256"]
                == _semantic_key_commitment(blinding_key),
                "semantic worksheet blinding key commitment mismatch")
    source_rows = _semantic_source_rows(calibration_result)
    _assert_semantic_blindness(worksheet, source_rows)
    samples = _worksheet_samples(worksheet)
    require(len(samples) == 2 * sentinels.ACTIVE_VARIANTS,
            "semantic worksheet sample count drift")
    sample_ids = [sample.get("sample_id") if isinstance(sample, dict) else None
                  for sample in samples]
    pair_ids = [pair.get("pair_id") if isinstance(pair, dict) else None
                for pair in worksheet["pairs"]]
    require(all(isinstance(value, str) and len(value) == 22
                and value.startswith("QS") for value in sample_ids)
            and len(set(sample_ids)) == len(sample_ids),
            "semantic worksheet sample identifiers are malformed or duplicated")
    require(all(isinstance(value, str) and len(value) == 22
                and value.startswith("QP") for value in pair_ids)
            and len(set(pair_ids)) == len(pair_ids),
            "semantic worksheet pair identifiers are malformed or duplicated")
    by_trace = {row["trace_sha256"]: row for row in source_rows}
    observed_traces: set[str] = set()
    base_seed = calibration_result["candidate"]["development_manifest"]["base_seed"]
    joined: list[dict[str, Any]] = []
    for pair in worksheet["pairs"]:
        pair_rows: list[dict[str, Any]] = []
        for sample in pair["samples"]:
            require(isinstance(sample, dict) and set(sample) == {
                "sample_id", "trace_sha256", "raw_response_sha256",
                "parsed_payload_sha256", "model_best_goal", "model_hypotheses",
                "model_goal_directed_plan", "mechanical_plan_replay", "verdict",
            }, "semantic worksheet sample schema is invalid")
            trace_sha = sample.get("trace_sha256")
            require(trace_sha in by_trace and trace_sha not in observed_traces,
                    "semantic worksheet substituted or duplicated a trace")
            observed_traces.add(trace_sha)
            row = by_trace[trace_sha]
            row_fixture = sentinels.build_active_variant(
                "dev", row["variant_index"], base_seed,
            )
            row_budget = _semantic_plan_budget(row_fixture)
            require(sample["raw_response_sha256"] == row["raw_response_sha256"]
                    and sample["parsed_payload_sha256"]
                    == row["parsed_payload_sha256"]
                    and {key: sample[key] for key in (
                        "model_best_goal", "model_hypotheses",
                        "model_goal_directed_plan",
                    )} == _semantic_model_fields(row["payload"])
                    and sample["mechanical_plan_replay"] == _replay_semantic_plan(
                        row_fixture,
                        row["payload"]["goal_directed_plan"],
                        action_budget=row_budget,
                    )
                    and sample["verdict"] == {
                        "goal_correct_in_kind": None,
                        "constraints_by_item": [None, None],
                        "plan_executable": None,
                    }, "semantic worksheet answer projection drift")
            if blinding_key is not None:
                expected_id = "QS" + _semantic_hmac(
                    blinding_key, calibration_binding["candidate_id"],
                    "sample", trace_sha,
                )[:20]
                require(sample["sample_id"] == expected_id,
                        "semantic sample HMAC identity drift")
            pair_rows.append(row)
            joined.append({"pair_id": pair["pair_id"], "sample": sample, "row": row})
        require(len({row["variant_index"] for row in pair_rows}) == 1
                and {row["role"] for row in pair_rows}
                == {"post_stripped", "post_preserved"},
                "semantic worksheet pair does not join the exact matched outputs")
        variant_index = pair_rows[0]["variant_index"]
        fixture = sentinels.build_active_variant("dev", variant_index, base_seed)
        gold = fixture["gold"]
        require(pair["reference"] == {
            "true_goal": gold["true_goal"],
            "necessary_constraints": gold["constraints"],
            "plan_start_state": "fresh deterministic reset",
            "plan_action_budget": _semantic_plan_budget(fixture),
        }, "semantic worksheet reference/rubric fixture drift")
        if blinding_key is not None:
            expected_pair_id = "QP" + _semantic_hmac(
                blinding_key, calibration_binding["candidate_id"],
                "pair", fixture["variant_id"],
            )[:20]
            require(pair["pair_id"] == expected_pair_id,
                    "semantic pair HMAC identity drift")
    require(observed_traces == set(by_trace),
            "semantic worksheet does not contain the exact six source traces")
    completed = _parse_utc(calibration_result["completed_utc"],
                           "calibration completion time")
    created = _parse_utc(worksheet["created_utc"], "semantic worksheet creation time")
    require(completed <= created,
            "semantic worksheet predates calibration completion")
    if blinding_key is not None:
        expected = _build_blind_semantic_document(
            calibration_result_path=calibration_result_path,
            calibration_result=calibration_result,
            calibration_binding=calibration_binding,
            blinding_key=blinding_key,
            created_utc=worksheet["created_utc"],
        )
        require(worksheet == expected,
                "semantic worksheet HMAC identities or permutation drift")
    _require_read_only(worksheet_path, "semantic worksheet")
    return joined


def _validate_semantic_judgments(
    judgments: dict[str, Any], *, worksheet_path: Path,
    sample_ids: set[str], worksheet_created_utc: str,
) -> dict[str, dict[str, Any]]:
    require(set(judgments) == {
        "format_version", "protocol_version", "artifact_type", "adjudicator",
        "adjudicated_utc", "blind_worksheet_sha256", "blind_attestation",
        "verdicts",
    }, "semantic judgments top-level schema is invalid")
    require(judgments.get("format_version") == SEMANTIC_FORMAT_VERSION
            and judgments.get("protocol_version") == SEMANTIC_PROTOCOL_VERSION
            and judgments.get("artifact_type")
            == "s4_qwen_calibration_blind_semantic_judgments",
            "semantic judgments version/type mismatch")
    require(isinstance(judgments.get("adjudicator"), str)
            and judgments["adjudicator"].strip(),
            "semantic judgments require an identified adjudicator")
    require(judgments.get("blind_worksheet_sha256") == sha256_file(worksheet_path),
            "semantic judgments are not bound to the exact blind worksheet")
    require(judgments.get("blind_attestation") == SEMANTIC_BLIND_ATTESTATION,
            "semantic adjudicator blindness attestation is incomplete")
    require(_parse_utc(worksheet_created_utc, "worksheet creation time")
            <= _parse_utc(judgments.get("adjudicated_utc"), "adjudication time"),
            "semantic judgment predates its worksheet")
    verdicts = judgments.get("verdicts")
    require(isinstance(verdicts, dict) and set(verdicts) == sample_ids,
            "semantic judgment sample inventory differs from the worksheet")
    for sample_id, verdict in verdicts.items():
        require(isinstance(verdict, dict) and set(verdict) == {
            "goal_correct_in_kind", "constraints_by_item", "plan_executable",
        }, f"semantic verdict {sample_id} has invalid fields")
        require(type(verdict["goal_correct_in_kind"]) is bool
                and type(verdict["plan_executable"]) is bool
                and isinstance(verdict["constraints_by_item"], list)
                and len(verdict["constraints_by_item"]) == 2
                and all(type(value) is bool
                        for value in verdict["constraints_by_item"]),
                f"semantic verdict {sample_id} is incomplete or non-boolean")
    return verdicts


def _derive_semantic_result(
    worksheet: dict[str, Any], judgments: dict[str, Any],
    joined: list[dict[str, Any]], *, calibration_result: dict[str, Any],
) -> dict[str, Any]:
    verdicts = judgments["verdicts"]
    base_seed = calibration_result["candidate"]["development_manifest"]["base_seed"]
    pair_summaries: list[dict[str, Any]] = []
    for pair in worksheet["pairs"]:
        entries = [item for item in joined if item["pair_id"] == pair["pair_id"]]
        outputs: dict[str, Any] = {}
        for item in entries:
            row = item["row"]
            condition = row["history_condition"]
            require(condition in {"stripped", "preserved"},
                    "semantic rejoin has an unknown condition")
            verdict = verdicts[item["sample"]["sample_id"]]
            fixture = sentinels.build_active_variant(
                "dev", row["variant_index"], base_seed,
            )
            replay = _replay_semantic_plan(
                fixture, item["sample"]["model_goal_directed_plan"],
                action_budget=pair["reference"]["plan_action_budget"],
            )
            require(verdict["plan_executable"] is replay["pass"],
                    "human executable-plan verdict differs from exact replay")
            goal_complete = (
                verdict["goal_correct_in_kind"]
                and all(verdict["constraints_by_item"])
            )
            outputs[condition] = {
                "sample_id": item["sample"]["sample_id"],
                "trace_sha256": row["trace_sha256"],
                "human_verdict": copy.deepcopy(verdict),
                "plan_replay": replay,
                "components": {
                    "goal_constraints_complete": goal_complete,
                    "plan_executable": replay["pass"],
                    "joint_complete": goal_complete and replay["pass"],
                },
            }
        require(set(outputs) == {"stripped", "preserved"},
                "semantic pair rejoin is incomplete")
        comparisons = {
            component: {
                "stripped": outputs["stripped"]["components"][component],
                "preserved": outputs["preserved"]["components"][component],
                "no_regression": (
                    int(outputs["preserved"]["components"][component])
                    >= int(outputs["stripped"]["components"][component])
                ),
            }
            for component in SEMANTIC_COMPONENTS
        }
        pair_summaries.append({
            "pair_id": pair["pair_id"],
            "outputs": outputs,
            "comparisons": comparisons,
            "pass": all(value["no_regression"] for value in comparisons.values()),
        })
    component_counts = {
        component: {
            condition: sum(
                int(pair["outputs"][condition]["components"][component])
                for pair in pair_summaries
            )
            for condition in ("stripped", "preserved")
        }
        for component in SEMANTIC_COMPONENTS
    }
    passed = all(pair["pass"] for pair in pair_summaries)
    return {
        "status": "PASS" if passed else "FAIL",
        "pass": passed,
        "definition": {
            "kind": "strict paired operational no-regression",
            "statistical_non_inferiority_claim": False,
            "pairs": sentinels.ACTIVE_VARIANTS,
            "rule": (
                "for every pair and every component, the anonymous output later "
                "rejoined to preserved history must score at least the matched "
                "output rejoined to stripped history"
            ),
            "components": list(SEMANTIC_COMPONENTS),
        },
        "pairs": pair_summaries,
        "component_pass_counts": component_counts,
    }


def _semantic_reservation(
    candidate_id: str, *, semantic_attempt_root: Path,
) -> tuple[dict[str, Any], Path, Path]:
    reservation_path = (
        semantic_attempt_root / f"{candidate_id}.reservation.json"
    ).resolve()
    receipt_path = (
        semantic_attempt_root / f"{candidate_id}.receipt.json"
    ).resolve()
    reservation = _load_json(reservation_path, "semantic reservation")
    _require_read_only(reservation_path, "semantic reservation")
    require(set(reservation) == {
        "format_version", "protocol_version", "artifact_type", "candidate_id",
        "attempt", "calibration_result", "blinding_key_commitment_sha256",
        "run_dir", "worksheet_path", "judgments_path", "result_path",
        "reserved_utc", "rule", "reservation_id",
    }, "semantic reservation schema is invalid")
    core = {key: value for key, value in reservation.items()
            if key != "reservation_id"}
    require(reservation.get("artifact_type")
            == "s4_qwen_calibration_semantic_reservation"
            and reservation.get("format_version") == SEMANTIC_FORMAT_VERSION
            and reservation.get("protocol_version") == SEMANTIC_PROTOCOL_VERSION
            and reservation.get("candidate_id") == candidate_id
            and reservation.get("attempt") == 0
            and reservation.get("reservation_id") == canonical_sha256(core),
            "semantic reservation binding is invalid")
    run_dir = Path(str(reservation.get("run_dir", ""))).resolve()
    require(Path(str(reservation.get("worksheet_path", ""))).resolve()
            == run_dir / "BLIND_WORKSHEET.json"
            and Path(str(reservation.get("judgments_path", ""))).resolve()
            == run_dir / "JUDGMENTS.json"
            and Path(str(reservation.get("result_path", ""))).resolve()
            == run_dir / "SEMANTIC_RESULT.json"
            and isinstance(reservation.get("blinding_key_commitment_sha256"), str)
            and len(reservation["blinding_key_commitment_sha256"]) == 64,
            "semantic reservation fixed paths/key commitment are invalid")
    return reservation, reservation_path, receipt_path


def _semantic_reservation_binding(
    reservation: dict[str, Any], reservation_path: Path,
) -> dict[str, str]:
    return {
        "path": str(reservation_path.resolve()),
        "sha256": sha256_file(reservation_path),
        "reservation_id": reservation["reservation_id"],
    }


def _semantic_file_binding(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    require(path.is_file(), f"semantic terminal artifact is missing: {path}")
    return {"path": str(path.resolve()), "sha256": sha256_file(path)}


def _write_semantic_terminal_receipt(
    *, candidate_id: str, reservation: dict[str, Any],
    reservation_path: Path, receipt_path: Path, status: str,
    judgments_path: Path | None, result_path: Path | None,
    error: BaseException | None,
) -> dict[str, Any]:
    require(status in {"PASS", "FAIL", "EXCEPTION"},
            f"invalid semantic terminal status {status!r}")
    error_record = None if error is None else {
        "type": type(error).__name__, "message": str(error),
    }
    core = {
        "format_version": SEMANTIC_FORMAT_VERSION,
        "protocol_version": SEMANTIC_PROTOCOL_VERSION,
        "artifact_type": "s4_qwen_calibration_semantic_receipt",
        "candidate_id": candidate_id,
        "attempt": 0,
        "reservation": _semantic_reservation_binding(
            reservation, reservation_path,
        ),
        "judgments": _semantic_file_binding(judgments_path),
        "result": _semantic_file_binding(result_path),
        "status": status,
        "error": error_record,
        "finished_utc": _utc_now(),
    }
    receipt = {**core, "receipt_id": canonical_sha256(core)}
    _atomic_create_json(receipt_path, receipt)
    return receipt


def _seal_semantic_run_dir(run_dir: Path) -> None:
    if not run_dir.is_dir():
        return
    for path in run_dir.iterdir():
        if path.is_file():
            path.chmod(0o444)
    run_dir.chmod(0o555)


def finalize_blind_semantic_adjudication(
    calibration_result_path: Path, worksheet_path: Path, judgments_source: Path,
    *, blinding_key: bytes, model: Path | None = None,
    fixture_root: Path = sentinels.DEV_ROOT,
    calibration_attempt_root: Path = ATTEMPT_ROOT,
    semantic_attempt_root: Path = SEMANTIC_ATTEMPT_ROOT,
    require_live_environment: bool = True,
) -> tuple[dict[str, Any], Path]:
    """Seal exact judgment bytes first, then terminate attempt 0 exactly once."""
    # Read only the candidate identity needed to find its already-reserved
    # semantic attempt.  All authoritative calibration validation happens only
    # after the submitted judgment bytes have been sealed.
    calibration_result = _load_json(calibration_result_path, "calibration result")
    candidate = calibration_result.get("candidate")
    require(isinstance(candidate, dict),
            "calibration result lacks the semantic reservation candidate")
    candidate_id = canonical_sha256(candidate)
    reservation, reservation_path, receipt_path = _semantic_reservation(
        candidate_id, semantic_attempt_root=semantic_attempt_root,
    )
    run_dir = Path(reservation["run_dir"]).resolve()
    fixed_worksheet = Path(reservation["worksheet_path"]).resolve()
    fixed_judgments = Path(reservation["judgments_path"]).resolve()
    final_path = Path(reservation["result_path"]).resolve()
    consumed = fixed_judgments.exists() or final_path.exists() or receipt_path.exists()
    if consumed:
        error = RuntimeError(
            "semantic adjudication attempt 0 is already consumed; retry and "
            "alternate adjudicator paths are forbidden"
        )
        if not receipt_path.exists():
            _write_semantic_terminal_receipt(
                candidate_id=candidate_id, reservation=reservation,
                reservation_path=reservation_path, receipt_path=receipt_path,
                status="EXCEPTION",
                judgments_path=fixed_judgments if fixed_judgments.is_file() else None,
                result_path=final_path if final_path.is_file() else None,
                error=error,
            )
        _seal_semantic_run_dir(run_dir)
        raise error

    try:
        # This exact byte copy is the point of no return.  It precedes JSON,
        # identity, key, worksheet, verdict, replay, and chronology validation.
        # Therefore malformed or adversarial input cannot be replaced after it
        # learns why it failed.
        _atomic_create_bytes(fixed_judgments, judgments_source.read_bytes())
        binding = validate_calibration_result(
            calibration_result_path, model=model, fixture_root=fixture_root,
            attempt_root=calibration_attempt_root,
            require_live_environment=require_live_environment,
        )
        require(binding["candidate_id"] == candidate_id,
                "semantic reservation candidate differs from hard calibration")
        require(worksheet_path.resolve() == fixed_worksheet
                and fixed_worksheet.is_file(),
                "semantic finalization substituted the fixed blind worksheet")
        require(reservation["calibration_result"] == {
            "path": str(calibration_result_path.resolve()),
            "sha256": sha256_file(calibration_result_path),
        } and reservation["blinding_key_commitment_sha256"]
                == _semantic_key_commitment(blinding_key),
                "semantic reservation source/key binding drift")
        worksheet = _load_json(fixed_worksheet, "blind semantic worksheet")
        joined = _validate_semantic_worksheet(
            worksheet, worksheet_path=fixed_worksheet,
            calibration_result_path=calibration_result_path,
            calibration_result=calibration_result, calibration_binding=binding,
            blinding_key=blinding_key,
        )
        judgments = _load_json(fixed_judgments, "sealed semantic judgments")
        sample_ids = {item["sample"]["sample_id"] for item in joined}
        _validate_semantic_judgments(
            judgments, worksheet_path=fixed_worksheet, sample_ids=sample_ids,
            worksheet_created_utc=worksheet["created_utc"],
        )
        operational = _derive_semantic_result(
            worksheet, judgments, joined, calibration_result=calibration_result,
        )
        finalized_utc = _utc_now()
        require(_parse_utc(judgments["adjudicated_utc"], "adjudication time")
                <= _parse_utc(finalized_utc, "semantic finalization time"),
                "semantic finalization predates human adjudication")
        result = {
            "format_version": SEMANTIC_FORMAT_VERSION,
            "protocol_version": SEMANTIC_PROTOCOL_VERSION,
            "artifact_type": "s4_qwen_calibration_semantic_result",
            "candidate_id": binding["candidate_id"],
            "created_utc": finalized_utc,
            "calibration_result": {
                "path": str(calibration_result_path.resolve()),
                "sha256": sha256_file(calibration_result_path),
            },
            "reservation": _semantic_reservation_binding(
                reservation, reservation_path,
            ),
            "blind_worksheet": {
                "path": str(fixed_worksheet),
                "sha256": sha256_file(fixed_worksheet),
            },
            "human_judgments": {
                "path": str(fixed_judgments),
                "sha256": sha256_file(fixed_judgments),
                "adjudicator": judgments["adjudicator"],
                "adjudicated_utc": judgments["adjudicated_utc"],
            },
            "operational_non_inferiority": operational,
        }
        _atomic_create_json(final_path, result)
        _write_semantic_terminal_receipt(
            candidate_id=candidate_id, reservation=reservation,
            reservation_path=reservation_path, receipt_path=receipt_path,
            status=operational["status"], judgments_path=fixed_judgments,
            result_path=final_path, error=None,
        )
        _seal_semantic_run_dir(run_dir)
        return result, final_path
    except BaseException as exc:
        if not receipt_path.exists():
            _write_semantic_terminal_receipt(
                candidate_id=candidate_id, reservation=reservation,
                reservation_path=reservation_path, receipt_path=receipt_path,
                status="FAIL" if isinstance(exc, RuntimeError) else "EXCEPTION",
                judgments_path=(
                    fixed_judgments if fixed_judgments.is_file() else None
                ),
                result_path=final_path if final_path.is_file() else None,
                error=exc,
            )
        _seal_semantic_run_dir(run_dir)
        raise


def validate_semantic_adjudication(
    semantic_result_path: Path, *, calibration_result_path: Path,
    blinding_key: bytes, model: Path | None = None,
    fixture_root: Path = sentinels.DEV_ROOT,
    calibration_attempt_root: Path = ATTEMPT_ROOT,
    semantic_attempt_root: Path = SEMANTIC_ATTEMPT_ROOT,
    require_live_environment: bool = True, require_pass: bool = True,
) -> dict[str, Any]:
    """Independently rederive the human-bound operational no-regression result."""
    binding = validate_calibration_result(
        calibration_result_path, model=model, fixture_root=fixture_root,
        attempt_root=calibration_attempt_root,
        require_live_environment=require_live_environment,
    )
    calibration_result = _load_json(calibration_result_path, "calibration result")
    reservation, reservation_path, receipt_path = _semantic_reservation(
        binding["candidate_id"], semantic_attempt_root=semantic_attempt_root,
    )
    key_commitment = _semantic_key_commitment(blinding_key)
    require(reservation["blinding_key_commitment_sha256"] == key_commitment,
            "semantic hard validation blinding key mismatch")
    final_path = Path(reservation["result_path"]).resolve()
    worksheet_path = Path(reservation["worksheet_path"]).resolve()
    judgments_path = Path(reservation["judgments_path"]).resolve()
    run_dir = Path(reservation["run_dir"]).resolve()
    require(reservation.get("calibration_result") == {
        "path": str(calibration_result_path.resolve()),
        "sha256": sha256_file(calibration_result_path),
    }, "semantic reservation calibration-result binding drift")
    require(semantic_result_path.resolve() == final_path
            and final_path.is_file() and worksheet_path.is_file()
            and judgments_path.is_file() and receipt_path.is_file(),
            "semantic authority inventory is incomplete or substituted")
    for path, label in (
        (final_path, "semantic result"),
        (worksheet_path, "semantic worksheet"),
        (judgments_path, "semantic judgments"),
        (receipt_path, "semantic receipt"),
    ):
        _require_read_only(path, label)
    require(run_dir.stat().st_mode & 0o222 == 0
            and {path.name for path in run_dir.iterdir() if path.is_file()} == {
                "BLIND_WORKSHEET.json", "JUDGMENTS.json", "SEMANTIC_RESULT.json",
            }, "semantic run directory is not a sealed exact artifact inventory")
    final = _load_json(final_path, "semantic result")
    worksheet = _load_json(worksheet_path, "semantic worksheet")
    judgments = _load_json(judgments_path, "semantic judgments")
    joined = _validate_semantic_worksheet(
        worksheet, worksheet_path=worksheet_path,
        calibration_result_path=calibration_result_path,
        calibration_result=calibration_result, calibration_binding=binding,
        blinding_key=blinding_key,
    )
    sample_ids = {item["sample"]["sample_id"] for item in joined}
    _validate_semantic_judgments(
        judgments, worksheet_path=worksheet_path, sample_ids=sample_ids,
        worksheet_created_utc=worksheet["created_utc"],
    )
    operational = _derive_semantic_result(
        worksheet, judgments, joined, calibration_result=calibration_result,
    )
    expected = {
        "format_version": SEMANTIC_FORMAT_VERSION,
        "protocol_version": SEMANTIC_PROTOCOL_VERSION,
        "artifact_type": "s4_qwen_calibration_semantic_result",
        "candidate_id": binding["candidate_id"],
        "created_utc": final.get("created_utc"),
        "calibration_result": {
            "path": str(calibration_result_path.resolve()),
            "sha256": sha256_file(calibration_result_path),
        },
        "reservation": {
            "path": str(reservation_path),
            "sha256": sha256_file(reservation_path),
            "reservation_id": reservation["reservation_id"],
        },
        "blind_worksheet": {
            "path": str(worksheet_path), "sha256": sha256_file(worksheet_path),
        },
        "human_judgments": {
            "path": str(judgments_path), "sha256": sha256_file(judgments_path),
            "adjudicator": judgments["adjudicator"],
            "adjudicated_utc": judgments["adjudicated_utc"],
        },
        "operational_non_inferiority": operational,
    }
    require(final == expected, "semantic final result is not independently derived")
    receipt = _load_json(receipt_path, "semantic receipt")
    require(set(receipt) == {
        "format_version", "protocol_version", "artifact_type", "candidate_id",
        "attempt", "reservation", "judgments", "result", "status", "error",
        "finished_utc", "receipt_id",
    }, "semantic receipt schema is invalid")
    receipt_core = {key: value for key, value in receipt.items()
                    if key != "receipt_id"}
    require(receipt.get("artifact_type")
            == "s4_qwen_calibration_semantic_receipt"
            and receipt.get("candidate_id") == binding["candidate_id"]
            and receipt.get("attempt") == 0
            and receipt.get("reservation") == final["reservation"]
            and receipt.get("judgments") == {
                "path": str(judgments_path),
                "sha256": sha256_file(judgments_path),
            }
            and receipt.get("result") == {
                "path": str(final_path), "sha256": sha256_file(final_path),
            }
            and receipt.get("status") == operational["status"]
            and receipt.get("error") is None
            and receipt.get("receipt_id") == canonical_sha256(receipt_core),
            "semantic terminal receipt is invalid")
    chronology = [
        _parse_utc(calibration_result["completed_utc"], "calibration completion"),
        _parse_utc(reservation["reserved_utc"], "semantic reservation"),
        _parse_utc(worksheet["created_utc"], "semantic worksheet creation"),
        _parse_utc(judgments["adjudicated_utc"], "semantic adjudication"),
        _parse_utc(final["created_utc"], "semantic result creation"),
        _parse_utc(receipt["finished_utc"], "semantic receipt completion"),
    ]
    require(all(left <= right for left, right in zip(chronology, chronology[1:])),
            "semantic artifact chronology is invalid")
    if require_pass:
        require(operational["pass"] is True,
                "semantic operational non-regression did not pass")
    return {
        "candidate_id": binding["candidate_id"],
        "calibration_result_sha256": sha256_file(calibration_result_path),
        "semantic_result_path": str(final_path),
        "semantic_result_sha256": sha256_file(final_path),
        "worksheet_sha256": sha256_file(worksheet_path),
        "judgments_sha256": sha256_file(judgments_path),
        "adjudicator": judgments["adjudicator"],
        "blinding_key_commitment_sha256": key_commitment,
        "status": operational["status"],
    }


def _round_kind(role: str) -> tuple[int, str, int]:
    if role.startswith("pre_"):
        return 0, f"calibration_{role}", srun.MAX_INITIAL_PROMPT_TEXT_TOKENS
    return 1, f"calibration_{role}", srun.MAX_CONTEXT_TEXT_TOKENS


def run_calibration(
    *, model: Path, base_seed: int, fixture_root: Path, output_root: Path,
) -> tuple[dict[str, Any], Path]:
    plan = plan_document(base_seed)
    assert_development_paths(fixture_root, output_root)
    ledgers.enforce_offline_scientific_run("s4_qwen_calibration --run", [])
    candidate, manifest, manifest_path, serving_identity = build_candidate_contract(
        model=model, base_seed=base_seed, fixture_root=fixture_root,
    )
    manifest_sha = sha256_file(manifest_path)
    output_root.mkdir(parents=True, exist_ok=True)
    reservation = reserve_candidate_attempt(candidate, output_root=output_root)
    run_dir = Path(reservation["run_dir"])
    result_path = Path(reservation["output_path"])
    receipts: list[dict[str, Any]] = []
    run_dir.mkdir(parents=False, exist_ok=False)
    started = {
        **plan,
        "artifact_type": "s4_qwen_development_calibration_started",
        "created_utc": _utc_now(),
        "candidate_id": reservation["candidate_id"],
        "candidate": candidate,
        "reservation_path": reservation["reservation_path"],
        "reservation_sha256": reservation["reservation_sha256"],
        "reservation_id": reservation["reservation_id"],
        "expected_receipt_path": reservation["receipt_path"],
        "script_sha256": sha256_file(Path(__file__)),
        "sentinel_generator_sha256": sha256_file(Path(sentinels.__file__)),
        "development_asset_manifest": {
            "path": str(manifest_path.resolve()), "sha256": manifest_sha,
        },
        "serving_identity": serving_identity,
        "run_dir": str(run_dir.resolve()),
    }
    _atomic_create_json(run_dir / "STARTED.json", started)
    try:
        prepared: dict[str, dict[str, Any]] = {}
        active_by_id = {record["variant_id"]: record for record in manifest["active"]}
        for variant in development_variants(base_seed):
            fixture = sentinels.build_active_variant(
                "dev", variant["index"], base_seed,
            )
            fixture.pop("gold", None)
            record = active_by_id[variant["variant_id"]]
            messages, images, carrier = sentinels._active_initial_turn(  # noqa: SLF001
                fixture_root, record, fixture,
            )
            prepared[variant["variant_id"]] = {
                "fixture": fixture, "manifest_record": record,
                "messages": messages, "images": images, "carrier": carrier,
            }

        vlm = probe.Vlm(model)
        pre_calls: dict[str, dict[str, Any]] = {}
        for row in plan["call_plan"]:
            variant = prepared[row["variant_id"]]
            if row["role"].startswith("pre_"):
                messages = copy.deepcopy(variant["messages"])
                images = list(variant["images"])
            else:
                pre = pre_calls[row["variant_id"]]
                carrier_path = fixture_root / variant["manifest_record"]["carrier_file"]
                feedback, feedback_images, _audit = sentinels._active_probe_feedback(  # noqa: SLF001
                    variant["fixture"], variant["carrier"], pre["payload"], carrier_path,
                )
                history = (copy.deepcopy(pre["record"]["assistant_history"])
                           if row["history_condition"] == "preserved"
                           else stripped_history(pre["record"]["assistant_history"]))
                messages = copy.deepcopy(variant["messages"])
                messages.append(history)
                messages.append({"role": "user", "content": feedback})
                images = list(variant["images"]) + list(feedback_images)

            round_index, round_kind, text_cap = _round_kind(row["role"])
            record, payload, answer = srun.ask_chat(
                vlm, messages, images, seed=row["seed"], max_tokens=ANSWER_TOKENS,
                max_input_text_tokens=text_cap, run_dir=run_dir, tag=row["tag"],
                ledger_module="s4_qwen_calibration",
                ledger_purpose="development-only sampler/reasoning calibration",
                serving_identity=serving_identity,
                round_index=round_index, round_kind=round_kind,
            )
            receipts.append(_call_receipt(row, record, payload, run_dir))
            if row["role"] == "pre_primary":
                require(record.get("assistant_history") == {
                    "role": "assistant", "content": answer,
                    "reasoning_content": record.get("think"),
                }, f"{row['tag']}: assistant-history receipt is inconsistent")
                pre_calls[row["variant_id"]] = {
                    "record": record, "payload": payload,
                }

        require(len(receipts) == CALL_BUDGET,
                "calibration did not execute the exact eleven-call inventory")
        evaluation = evaluate_calibration(plan["call_plan"], receipts)
        result = {
            **started,
            "artifact_type": "s4_qwen_development_calibration_result",
            "completed_utc": _utc_now(),
            "calls": receipts,
            "evaluation": evaluation,
            "gold_access": {
                "semantic_gold_consulted": False,
                "gold_files_opened_by_calibration_harness": False,
                "semantic_adjudication": "separate blind process required",
            },
        }
        _atomic_create_json(result_path, result)
        terminal_status = "PASS" if evaluation["pass"] else "FAIL"
        terminal = finalize_candidate_receipt(
            reservation, status=terminal_status, result_path=result_path,
            traces=[copy.deepcopy(row["trace"]) for row in receipts],
        )
        require(Path(terminal["receipt_path"]).is_file(),
                "terminal calibration receipt was not created")
        for path in run_dir.iterdir():
            if path.is_file():
                path.chmod(0o444)
        run_dir.chmod(0o555)
        return result, result_path
    except BaseException as exc:
        failure = run_dir / "FAILED.json"
        if not failure.exists():
            _atomic_create_json(failure, {
                "artifact_type": "s4_qwen_development_calibration_failure",
                "created_utc": _utc_now(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "completed_call_tags": [row["tag"] for row in receipts],
                "automatic_retry": False,
            })
        receipt_path = Path(reservation["receipt_path"])
        if not receipt_path.exists():
            finalize_candidate_receipt(
                reservation, status="EXCEPTION", result_path=None,
                traces=[copy.deepcopy(row["trace"]) for row in receipts],
                error=f"{type(exc).__name__}: {exc}",
            )
        for path in run_dir.iterdir():
            if path.is_file():
                path.chmod(0o444)
        run_dir.chmod(0o555)
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true",
                      help="print the exact eleven-call plan; no model/assets/GPU")
    mode.add_argument("--run", action="store_true",
                      help="execute one new development-only calibration run")
    mode.add_argument("--validate-result", type=Path,
                      help="hard-validate an immutable PASS result for pre-freeze use")
    mode.add_argument(
        "--prepare-semantic", type=Path, metavar="CALIB_RESULT",
        help="create the one-shot blind semantic worksheet for a mechanical PASS",
    )
    mode.add_argument(
        "--finalize-semantic", type=Path, metavar="CALIB_RESULT",
        help="seal one blind human judgment and derive operational no-regression",
    )
    mode.add_argument(
        "--validate-semantic", type=Path, metavar="SEMANTIC_RESULT",
        help="independently validate a finalized semantic adjudication",
    )
    parser.add_argument("--model", type=Path,
                        help="pinned local Qwen3.8 MLX checkpoint")
    parser.add_argument("--base-seed", type=int, default=4)
    parser.add_argument("--fixture-root", type=Path, default=sentinels.DEV_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    parser.add_argument("--calibration-result", type=Path,
                        help="mechanical calibration result used by --validate-semantic")
    parser.add_argument("--worksheet", type=Path,
                        help="fixed blind worksheet used by --finalize-semantic")
    parser.add_argument("--judgments", type=Path,
                        help="complete blind human judgment JSON used once")
    parser.add_argument("--blinding-key", type=Path,
                        help="file containing at least 32 opaque key bytes")
    parser.add_argument("--semantic-output-root", type=Path,
                        default=SEMANTIC_OUTPUT_ROOT)
    return parser


def _validate_cli_mode_options(args: argparse.Namespace,
                               argv: list[str]) -> None:
    """Reject explicitly supplied options that the selected mode cannot use."""
    ancillary = {
        "--model", "--base-seed", "--fixture-root", "--output-root",
        "--calibration-result", "--worksheet", "--judgments",
        "--blinding-key", "--semantic-output-root",
    }
    if args.plan:
        mode, allowed = "--plan", {"--base-seed"}
    elif args.run:
        mode, allowed = "--run", {
            "--model", "--base-seed", "--fixture-root", "--output-root",
        }
    elif args.validate_result is not None:
        mode, allowed = "--validate-result", {"--model", "--fixture-root"}
    elif args.prepare_semantic is not None:
        mode, allowed = "--prepare-semantic", {
            "--model", "--fixture-root", "--blinding-key",
            "--semantic-output-root",
        }
    elif args.finalize_semantic is not None:
        mode, allowed = "--finalize-semantic", {
            "--model", "--fixture-root", "--worksheet", "--judgments",
            "--blinding-key",
        }
    else:
        mode, allowed = "--validate-semantic", {
            "--model", "--fixture-root", "--calibration-result",
            "--blinding-key",
        }
    supplied = {
        token.split("=", 1)[0] for token in argv if token.startswith("--")
    }
    irrelevant = sorted((supplied & ancillary) - allowed)
    require(
        not irrelevant,
        f"{mode} does not accept unrelated option(s): {', '.join(irrelevant)}",
    )


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(raw_argv)
    _validate_cli_mode_options(args, raw_argv)
    if args.plan:
        print(json.dumps(plan_document(args.base_seed), indent=1, sort_keys=True))
        return 0
    if args.validate_result is not None:
        require(args.model is not None, "--model is required with --validate-result")
        binding = validate_calibration_result(
            args.validate_result, model=args.model, fixture_root=args.fixture_root,
        )
        print(json.dumps(binding, indent=1, sort_keys=True))
        return 0
    if args.prepare_semantic is not None:
        require(args.model is not None,
                "--model is required with --prepare-semantic")
        require(args.blinding_key is not None and args.blinding_key.is_file(),
                "--blinding-key FILE is required with --prepare-semantic")
        worksheet, path = create_blind_semantic_worksheet(
            args.prepare_semantic, blinding_key=args.blinding_key.read_bytes(),
            model=args.model, fixture_root=args.fixture_root,
            output_root=args.semantic_output_root,
        )
        print(json.dumps({
            "worksheet": str(path),
            "pairs": len(worksheet["pairs"]),
            "samples": sum(len(pair["samples"]) for pair in worksheet["pairs"]),
            "status": "PENDING_HUMAN_ADJUDICATION",
        }, indent=1, sort_keys=True))
        return 0
    if args.finalize_semantic is not None:
        require(args.model is not None,
                "--model is required with --finalize-semantic")
        require(args.blinding_key is not None and args.blinding_key.is_file(),
                "--blinding-key FILE is required with --finalize-semantic")
        require(args.worksheet is not None and args.worksheet.is_file(),
                "--worksheet FILE is required with --finalize-semantic")
        require(args.judgments is not None and args.judgments.is_file(),
                "--judgments FILE is required with --finalize-semantic")
        result, path = finalize_blind_semantic_adjudication(
            args.finalize_semantic, args.worksheet, args.judgments,
            blinding_key=args.blinding_key.read_bytes(), model=args.model,
            fixture_root=args.fixture_root,
        )
        status = result["operational_non_inferiority"]["status"]
        print(json.dumps({
            "semantic_result": str(path), "status": status,
            "adjudicator": result["human_judgments"]["adjudicator"],
        }, indent=1, sort_keys=True))
        return 0 if status == "PASS" else 2
    if args.validate_semantic is not None:
        require(args.model is not None,
                "--model is required with --validate-semantic")
        require(args.calibration_result is not None
                and args.calibration_result.is_file(),
                "--calibration-result FILE is required with --validate-semantic")
        require(args.blinding_key is not None and args.blinding_key.is_file(),
                "--blinding-key FILE is required with --validate-semantic")
        binding = validate_semantic_adjudication(
            args.validate_semantic,
            calibration_result_path=args.calibration_result,
            blinding_key=args.blinding_key.read_bytes(),
            model=args.model, fixture_root=args.fixture_root,
        )
        print(json.dumps(binding, indent=1, sort_keys=True))
        return 0
    require(args.model is not None, "--model is required with --run")
    result, path = run_calibration(
        model=args.model, base_seed=args.base_seed,
        fixture_root=args.fixture_root, output_root=args.output_root,
    )
    print(json.dumps({
        "result": str(path), "status": result["evaluation"]["status"],
        "calls": len(result["calls"]), "kaggle_submissions": 0,
    }, indent=1, sort_keys=True))
    return 0 if result["evaluation"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
