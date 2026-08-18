"""Transcript-matched model-ceiling executor for slice 4 (Stage-A descriptive comparator).

Consumes the sealed ceiling_input artifact written by `s4_grade.py --prepare-ceiling`,
delivers each cell's exact user-message transcript — verbatim, assistant turns already
excluded by the artifact's construction — to the same pinned checkpoint through the
identical serving path (`s4_run.ask_chat`: template invariants, production sampler,
frozen effort), and writes the append-only artifacts that the grader's
`validate_model_ceiling_execution_trace` verifies:

  - one immutable raw execution artifact per cell (prompt messages, raw response,
    run metadata, parsed final answer),
  - the execution trace binding every cell to the frozen ceiling_spec and input,
  - the ceiling answers document, self-verified through the grader's own
    `validate_run_document`/`collect_attempts` before the run reports success.

Nothing here may repair or rewrite evidence: an image whose bytes drifted from the
recorded SHA-256, a mismatched checkpoint, or a serving_config that does not describe
the actual runtime each abort the run before any generation.

Run (after the Qwen primary cells are answered and --prepare-ceiling has released the
input artifact):

  .venv/bin/python agent/harness/s4_ceiling.py --ceiling-input logs/s4_ceiling/... .json
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_probe_vlm as probe  # noqa: E402
import s4_grade as grade  # noqa: E402
import s4_run as runner  # noqa: E402

ROOT = grade.ROOT
RUNS = ROOT / "logs/s4_ceiling_runs"


def require(condition: Any, message: str) -> None:
    probe.require(condition, message)


def sha256_file(path: Path) -> str:
    return grade.sha256_file(path)


def validate_serving_config_matches_runtime(spec: dict[str, Any], budgets: dict[str, Any]) -> None:
    """The frozen spec must DESCRIBE the actual serving path, not merely name one."""
    config = spec["model"].get("serving_config") or {}
    require(config.get("enable_thinking") is True,
            "ceiling serving_config must pin enable_thinking=true (instrument rule)")
    require(config.get("preserve_thinking") is True,
            "ceiling serving_config must pin preserve_thinking=true")
    require(config.get("reasoning_effort") == probe.REASONING_EFFORT,
            f"ceiling serving_config effort {config.get('reasoning_effort')!r} != "
            f"runtime {probe.REASONING_EFFORT!r}")
    sampler = probe.PRODUCTION_SAMPLER
    for spec_key, sampler_key in (
        ("temperature", "temperature"), ("top_p", "top_p"), ("top_k", "top_k"),
        ("min_p", "min_p"), ("presence_penalty", "presence_penalty"),
        ("repetition_penalty", "repetition_penalty"),
    ):
        require(config.get(spec_key) == sampler[sampler_key],
                f"ceiling serving_config {spec_key}={config.get(spec_key)!r} != "
                f"production sampler {sampler[sampler_key]!r}")
    require(config.get("max_output_tokens_per_call") == budgets["answer_tokens"],
            "ceiling serving_config output budget differs from the frozen answer budget")
    require(config.get("native_context_tokens") == budgets.get("native_context_tokens"),
            "ceiling serving_config native context differs from the frozen budget")
    require(budgets.get("native_context_tokens") == runner.NATIVE_CONTEXT_TOKENS
            and budgets.get("max_context_text_tokens") == runner.MAX_CONTEXT_TEXT_TOKENS,
            "ceiling context budgets differ from the actual native serving envelope")
    import mlx_vlm
    runtime = f"mlx-vlm-{mlx_vlm.__version__}"
    require(config.get("runtime") == runtime,
            f"ceiling serving_config runtime {config.get('runtime')!r} != {runtime!r}")


def load_ceiling_input(path: Path, frozen: dict[str, Any]) -> dict[str, Any]:
    artifact = grade.load_object(path, "ceiling input artifact")
    preregistration = frozen["preregistration"]
    require(artifact.get("artifact_type") == "s4_transcript_matched_ceiling_input"
            and artifact.get("format_version") == grade.FORMAT_VERSION,
            "not a transcript-matched ceiling input artifact")
    require(artifact.get("frozen_manifest_sha256") == sha256_file(grade.FROZEN_R4),
            "ceiling input is not bound to this exact FROZEN.json")
    require(artifact.get("preregistration_sha256") == frozen["preregistration_sha256"],
            "ceiling input preregistration digest mismatch")
    require(artifact.get("ceiling_spec") == preregistration["ceiling_spec"]
            and artifact.get("ceiling_spec_sha256") == preregistration["ceiling_spec_sha256"],
            "ceiling input does not carry the frozen ceiling_spec")
    require(artifact.get("closure_eligibility") == "descriptive_only_model"
            and artifact.get("respondent_id") is None
            and artifact.get("familiarity_commitment") is None
            and artifact.get("familiarity_declarations") is None,
            "this executor serves only the descriptive model comparator")
    grade._ceiling_input_cells(artifact)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--ceiling-input", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=probe.MODEL)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--attempt", type=int, default=0)
    parser.add_argument(
        "--prior-attempt", type=Path, default=None,
        help="attempt-0 ceiling answers; required for attempt 1 so the executor "
             "derives the exact missing comparator cells",
    )
    args = parser.parse_args()
    import s4_ledgers
    s4_ledgers.enforce_offline_scientific_run("s4_ceiling", sys.argv[1:])
    require(args.attempt in (0, 1), "--attempt must be 0 or 1")
    require((args.attempt == 1) == (args.prior_attempt is not None),
            "--prior-attempt is required exactly when --attempt 1")

    git = probe.capture_git_state()
    frozen = grade.verify_freeze_r4()
    frozen_sha = sha256_file(grade.FROZEN_R4)
    grade.verify_continue_r4(frozen_sha)
    require(git.get("commit") == frozen["git_commit"] and git.get("dirty") is False,
            "ceiling execution requires a clean tree at the frozen commit")
    preregistration = frozen["preregistration"]
    spec = preregistration.get("ceiling_spec")
    require(isinstance(spec, dict) and spec.get("kind") == "model",
            "frozen ceiling_spec is not a model comparator")
    budgets = preregistration["budgets"]
    validate_serving_config_matches_runtime(spec, budgets)

    ceiling_input_path = args.ceiling_input.resolve()
    require(ceiling_input_path.is_file(), f"missing ceiling input: {ceiling_input_path}")
    ceiling_input_sha = sha256_file(ceiling_input_path)
    artifact = load_ceiling_input(ceiling_input_path, frozen)
    input_cells = grade._ceiling_input_cells(artifact)
    require(input_cells, "ceiling input contains no cells")
    expected_ceiling_keys = {
        grade.logical_key(row["role"], row["game_blind"], row["arm"], row["seed"])
        for row in preregistration["expected_cells"] if row["role"] == "ceiling"
    }
    prior_attempt_binding = None
    if args.attempt == 0:
        require(set(input_cells) == expected_ceiling_keys,
                "primary comparator run requires the exact frozen ceiling matrix")
        execution_keys = set(input_cells)
    else:
        prior_path = args.prior_attempt.expanduser().resolve()
        require(prior_path.is_file(), f"prior comparator attempt is missing: {prior_path}")
        prior_doc = grade.load_object(prior_path, "prior comparator attempt")
        require(prior_doc.get("role") == "ceiling" and prior_doc.get("attempt", 0) == 0,
                "--prior-attempt must be an attempt-0 ceiling answer document")
        prior_reservation = runner.prior_reservation_binding(prior_doc)
        attempts, _ = grade.collect_attempts([prior_path], frozen)
        resolved = grade.resolve_attempts(attempts, frozen)
        execution_keys = {
            key for key, resolution in resolved.items()
            if key in expected_ceiling_keys and resolution.get("rerun_required") is True
        }
        require(execution_keys,
                "attempt 0 has no comparator cells eligible for the missing-output remedy")
        require(execution_keys <= set(input_cells),
                "ceiling input does not contain every derived missing comparator cell")
        prior_attempt_binding = {
            "path": str(prior_path), "sha256": sha256_file(prior_path),
            "required_cell_keys": sorted(execution_keys),
            "reservation": prior_reservation,
        }

    # Cross-module seed derivation must agree before anything is generated.
    for cell in input_cells.values():
        blind, seed = cell["game_blind"], cell["seed"]
        require(probe.seed_for(seed, f"{blind}_r0")
                == grade.generation_seed(seed, blind, 0),
                "seed_for/generation_seed derivation drift between modules")

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = RUNS / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    out_path = (args.out or run_dir / "ceiling_cells.json").resolve()
    require(not out_path.exists(), f"output already exists; runs are append-only: {out_path}")

    model_decl = spec["model"]
    identity = runner.verify_serving_snapshot(args.model, frozen["serving_snapshot"])
    require(identity["checkpoint_sha256"] == model_decl.get("checkpoint_sha256"),
            f"served checkpoint {identity['checkpoint_sha256']!r} differs from "
            f"the frozen ceiling model {model_decl.get('checkpoint_sha256')!r}")
    vlm = probe.Vlm(args.model)
    # Loading the already-verified checkpoint is not a serving attempt.  Claim
    # the fixed one-shot marker immediately after load and before generation.
    reservation_binding = runner.reserve_serving_attempt(
        role="ceiling",
        attempt=args.attempt,
        frozen_manifest_sha256=frozen_sha,
        run_dir=run_dir,
        output_path=out_path,
        serving_identity=identity,
        prior_attempt=prior_attempt_binding,
    )

    started_utc = _dt.datetime.now(_dt.timezone.utc).isoformat()
    answer_cells: list[dict[str, Any]] = []
    trace_cells: list[dict[str, Any]] = []
    games_blind: list[str] = []
    for cell_key in sorted(execution_keys):
        cell = input_cells[cell_key]
        blind, arm, seed = cell["game_blind"], cell["arm"], cell["seed"]
        games_blind.append(blind)
        evidence = cell["evidence"]
        require(grade.sha256_json(evidence) == cell["evidence_sha256"],
                f"{cell_key}: evidence digest drift inside ceiling input")
        for index, item in enumerate(evidence.get("images") or []):
            image_path = Path(item["path"])
            require(image_path.is_file() and sha256_file(image_path) == item["sha256"],
                    f"{cell_key}: delivered image {index} bytes drifted: {item['path']}")
        messages = evidence["user_messages"]
        images = [Path(item["path"]) for item in evidence.get("images") or []]
        tag = f"{blind}_{arm}_s{seed}_r0"
        effective_seed = probe.seed_for(seed, f"{blind}_r0")
        print(f"[{cell_key}] {len(messages)} user messages, {len(images)} images", flush=True)
        record, payload, _answer = runner.ask_chat(
            vlm, messages, images,
            seed=effective_seed, max_tokens=budgets["answer_tokens"],
            run_dir=run_dir, tag=tag,
            max_input_text_tokens=budgets["max_context_text_tokens"],
            ledger_module="s4_ceiling",
            ledger_purpose="stage_a_descriptive_comparator",
            serving_identity=identity,
            round_index=0,
            round_kind="ceiling_initial",
        )
        require(record["messages"] is messages or record["messages"] == messages,
                f"{cell_key}: serving path altered the delivered messages")
        trace_path = Path(record["trace_path"])
        require(sha256_file(trace_path) == record["trace_sha256"],
                f"{cell_key}: immutable serving trace drifted immediately after generation")
        raw_text = record["raw_response"]
        outcome = runner._outcome_for(record) or "answered"

        run_id = f"ceiling_{tag}_{stamp}"
        raw_artifact = {
            "format_version": grade.FORMAT_VERSION,
            "artifact_type": "s4_model_ceiling_raw_execution",
            "ceiling_spec_sha256": preregistration["ceiling_spec_sha256"],
            "cell_key": cell_key,
            "provider": model_decl["provider"],
            "model": model_decl,
            "run_id": run_id,
            "ceiling_input_sha256": ceiling_input_sha,
            "evidence_sha256": cell["evidence_sha256"],
            "prompt_messages": messages,
            "raw_response": raw_text,
            "run_metadata": record,
            "final_answer": record["parsed_payload"],
        }
        raw_path = run_dir / f"{tag}.raw_execution.json"
        grade.atomic_create(raw_path, raw_artifact, mode=0o444)
        trace_cells.append({
            "ceiling_spec_sha256": preregistration["ceiling_spec_sha256"],
            "cell_key": cell_key,
            "provider": model_decl["provider"],
            "run_id": run_id,
            "model": model_decl,
            "ceiling_input_sha256": ceiling_input_sha,
            "evidence_sha256": cell["evidence_sha256"],
            "prompt_messages_sha256": grade.sha256_json(messages),
            "trace_tag": record["trace_tag"],
            "trace_path": record["trace_path"],
            "trace_sha256": record["trace_sha256"],
            "serving_identity": identity,
            "sampler": record["sampler"],
            "reasoning_effort": record["reasoning_effort"],
            "completeness": record["completeness"],
            "input_tokens": record["input_tokens"],
            "output_tokens": record["output_tokens"],
            "raw_response_run_metadata": {"path": str(raw_path), "sha256": sha256_file(raw_path)},
            "final_answer_sha256": grade.sha256_json(record["parsed_payload"]),
        })
        answer_cells.append({
            "role": "ceiling",
            "game_blind": blind,
            "arm": arm,
            "seed": seed,
            "attempt": args.attempt,
            "run_id": run_id,
            "outcome": outcome,
            "final_answer": record["parsed_payload"],
            "rounds": [record],
            "ceiling_input_cell_sha256": cell["evidence_sha256"],
        })
        print(f"[{cell_key}] outcome={outcome} completeness={record['completeness']} "
              f"wall={record['wall_seconds']}s", flush=True)

    trace_artifact = {
        "format_version": grade.FORMAT_VERSION,
        "artifact_type": "s4_model_ceiling_execution_trace",
        "ceiling_spec_sha256": preregistration["ceiling_spec_sha256"],
        "serving_identity": identity,
        **reservation_binding,
        "cells": trace_cells,
    }
    trace_out = run_dir / "ceiling_execution_trace.json"
    grade.atomic_create(trace_out, trace_artifact, mode=0o444)
    receipt_binding = runner.finalize_serving_receipt(
        reservation_binding,
        status="complete",
        trace_receipts=runner.trace_receipts_from_cells(answer_cells),
        cell_outcomes=[{
            "role": cell["role"],
            "game_blind": cell["game_blind"],
            "arm": cell["arm"],
            "seed": cell["seed"],
            "attempt": cell["attempt"],
            "outcome": cell["outcome"],
        } for cell in answer_cells],
    )

    document = {
        "note": "notes/qwen-3.8-slice4-design.md -> transcript-matched model ceiling",
        "format_version": 2,
        "status": "complete",
        "started_utc": started_utc,
        "finished_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "argv": list(sys.argv),
        "git": git,
        "role": "ceiling",
        "attempt": args.attempt,
        "games_blind": sorted(set(games_blind)),
        "arms": sorted({cell["arm"] for cell in answer_cells}),
        "seeds": sorted({cell["seed"] for cell in answer_cells}),
        "run_dir": str(run_dir),
        "output_path": str(out_path),
        "frozen_manifest_sha256": frozen_sha,
        "prior_attempt": prior_attempt_binding,
        "serving_identity": identity,
        **reservation_binding,
        **receipt_binding,
        "budgets": {key: budgets[key] for key in grade.RUN_BUDGET_KEYS},
        "ceiling_spec": preregistration["ceiling_spec"],
        "ceiling_spec_sha256": preregistration["ceiling_spec_sha256"],
        "ceiling_input": {"path": str(ceiling_input_path), "sha256": ceiling_input_sha},
        "ceiling_execution_trace": {"path": str(trace_out), "sha256": sha256_file(trace_out)},
        "cells": answer_cells,
    }
    probe.atomic_write(out_path, document)

    # Self-verification through the grader's own gate before reporting success.
    reloaded = grade.load_object(out_path, "ceiling answers document")
    role, seeds, attempt = grade.validate_run_document(reloaded, frozen)
    require(role == "ceiling" and attempt == args.attempt,
            "self-verification returned an unexpected role/attempt")
    attempts, _bindings = grade.collect_attempts([out_path], frozen)
    produced = {key for key, by_attempt in attempts.items() if by_attempt}
    require(produced == execution_keys,
            "self-verification: produced cells differ from the attempt's authorized inventory")
    print(f"ceiling answers -> {out_path} ({sha256_file(out_path)})")
    print(f"execution trace -> {trace_out}")
    print("SELF-VERIFY PASS (validate_run_document + collect_attempts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
