"""No-model tests for the bounded Qwen3.8 development calibration."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_qwen_calibration as calibration  # noqa: E402
import s4_sentinels as sentinels  # noqa: E402


def _fixed_dev_root(path):
    """Patch value for sentinels.dev_fixture_root: every seed maps to `path`."""
    return lambda _seed, _path=path: _path


class QwenCalibrationTests(unittest.TestCase):
    @staticmethod
    def _valid_payload() -> dict:
        return {
            "hypotheses": [{
                "probability": 0.6,
                "necessary_conditions": ["condition"],
                "sufficient_condition": "condition is sufficient",
                "evidence_for": ["E1"],
                "evidence_against": [],
                "predicted_counterexample": "omit condition",
            }],
            "best_goal": {
                "plain_causal_condition": "satisfy condition",
                "structured_factors": ["condition"],
            },
            "next_probe": {
                "start_state_id": None, "action": None,
                "predictions_by_hypothesis": {},
            },
            "retrieval_requests": [],
            "goal_directed_plan": [{"action": {"id": 0, "click": None}}],
        }

    def _valid_authority_tree(self, root: Path) -> dict:
        fixture_root = root / "dev-fixtures"
        fixture_root.mkdir()
        manifest_path = fixture_root / "sentinel_manifest.json"
        manifest_path.write_text("{}\n")
        manifest = {
            "generator_sha256": calibration.sha256_file(Path(sentinels.__file__)),
            "asset_files": {},
        }
        plan = calibration.plan_document(4)
        git = {"commit": "a" * 40, "dirty": False, "status": []}
        checkpoint = {
            "model_path": str((root / "model").resolve()),
            "checkpoint_sha256": "c" * 64,
            "git": git,
            "versions": {"runtime": "test"},
        }
        candidate = {
            "format_version": calibration.FORMAT_VERSION,
            "artifact_type": "s4_qwen_calibration_candidate",
            "protocol_version": calibration.PROTOCOL_VERSION,
            "seed_authority": calibration.required_next_seed(root / "attempts"),
            "git": git,
            "critical_scripts": {
                relative: calibration.sha256_file(calibration.ROOT / relative)
                for relative in calibration.CRITICAL_SCRIPTS
            },
            "checkpoint_identity": checkpoint,
            "development_manifest": {
                "path": str(manifest_path.resolve()),
                "sha256": calibration.sha256_file(manifest_path),
                "namespace": "dev", "base_seed": 4,
                "generator_sha256": manifest["generator_sha256"],
                "asset_inventory_sha256": calibration.canonical_sha256({}),
            },
            "plan_sha256": calibration.canonical_sha256(plan),
            "request_prompt_sha256": hashlib.sha256(
                calibration.srun.REQUEST.encode()
            ).hexdigest(),
            "sampler": copy.deepcopy(calibration.OFFICIAL_THINKING_SAMPLER),
            "reasoning_effort": "xhigh", "preserve_thinking": True,
            "answer_tokens": calibration.ANSWER_TOKENS,
            "native_context_tokens": calibration.srun.NATIVE_CONTEXT_TOKENS,
            "kaggle_submissions": 0,
        }
        serving_identity = {
            "scope": "pinned local checkpoint conversion, not the BF16 model family",
            "verified_shards": True,
            "checkpoint_sha256": checkpoint["checkpoint_sha256"],
            "candidate_checkpoint_identity_sha256": calibration.canonical_sha256(
                checkpoint
            ),
        }
        attempts = root / "attempts"
        reservation = calibration.reserve_candidate_attempt(
            candidate, output_root=root / "runs", attempt_root=attempts,
        )
        run_dir = Path(reservation["run_dir"])
        run_dir.mkdir(parents=True)
        payload = self._valid_payload()
        answer = json.dumps(payload, sort_keys=True)
        primary_think: dict[str, str] = {}
        calls = []
        for planned in plan["call_plan"]:
            role = planned["role"]
            variant_id = planned["variant_id"]
            if role.startswith("pre_"):
                messages = [{"role": "user", "content": [
                    {"type": "text", "text": f"fixture {variant_id}"},
                ]}]
                think = "same reproducible reasoning" if planned["variant_index"] == 0 \
                    else f"reasoning {variant_id}"
                if role == "pre_different_seed":
                    think = "different seeded reasoning"
                if role == "pre_primary":
                    primary_think[variant_id] = think
            else:
                messages = [
                    {"role": "user", "content": [
                        {"type": "text", "text": f"fixture {variant_id}"},
                    ]},
                    {"role": "assistant", "content": answer},
                    {"role": "user", "content": [
                        {"type": "text", "text": "same probe result"},
                    ]},
                ]
                if role == "post_preserved":
                    messages[1]["reasoning_content"] = primary_think[variant_id]
                think = f"post reasoning {variant_id} {role}"
            raw = think + "</think>" + answer
            prompt = "PROMPT:" + json.dumps(messages, sort_keys=True)
            expanded = 5
            stats = {
                "prompt_tokens": expanded, "generation_tokens": 10,
                "total_tokens": expanded + 10, "finish_reason": "stop",
            }
            round_index, round_kind, text_cap = calibration._round_kind(role)  # noqa: SLF001
            trace = {
                "tag": planned["tag"], "trace_tag": planned["tag"],
                "round_index": round_index, "round_kind": round_kind,
                "seed": planned["seed"],
                "sampler": copy.deepcopy(calibration.OFFICIAL_THINKING_SAMPLER),
                "reasoning_effort": "xhigh", "preserve_thinking": True,
                "serving_identity": serving_identity,
                "max_tokens": calibration.ANSWER_TOKENS,
                "native_context_tokens": calibration.srun.NATIVE_CONTEXT_TOKENS,
                "messages": messages,
                "messages_sha256": calibration.canonical_sha256(messages),
                "prompt": prompt,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "images": [], "image_grid_thw": [], "visual_tokens": 0,
                "expanded_prompt_tokens": expanded, "derived_text_tokens": expanded,
                "input_text_token_cap": text_cap,
                "generator_prompt_tokens": expanded, "input_tokens": expanded,
                "finish_reason": "stop", "output_tokens": 10,
                "prompt_tokens_match": True, "token_accounting_match": True,
                "completion_contains_close": True, "think": think, "answer": answer,
                "parsed_payload": payload, "schema_errors": [],
                "ranking_compliance": calibration.srun.ranking_compliance(
                    payload.get("hypotheses")) if isinstance(payload, dict) else None,
                "payload_present": True, "completeness": "complete",
                "assistant_history": {
                    "role": "assistant", "content": answer,
                    "reasoning_content": think,
                },
                "raw": raw, "raw_response": raw, "stats": stats,
            }
            trace_path = run_dir / f"{planned['tag']}.trace.json"
            calibration._atomic_create_json(trace_path, trace)  # noqa: SLF001
            record = {
                **trace, "trace_path": str(trace_path.resolve()),
                "trace_sha256": calibration.sha256_file(trace_path),
            }
            calls.append(calibration._call_receipt(  # noqa: SLF001
                planned, record, payload, run_dir,
            ))
        evaluation = calibration.evaluate_calibration(plan["call_plan"], calls)
        self.assertTrue(evaluation["pass"])
        created = dt.datetime.now(dt.timezone.utc).isoformat()
        common = {
            **plan,
            "created_utc": created,
            "candidate_id": reservation["candidate_id"],
            "candidate": candidate,
            "reservation_path": reservation["reservation_path"],
            "reservation_sha256": reservation["reservation_sha256"],
            "reservation_id": reservation["reservation_id"],
            "expected_receipt_path": reservation["receipt_path"],
            "script_sha256": calibration.sha256_file(Path(calibration.__file__)),
            "sentinel_generator_sha256": calibration.sha256_file(Path(sentinels.__file__)),
            "development_asset_manifest": {
                "path": str(manifest_path.resolve()),
                "sha256": calibration.sha256_file(manifest_path),
            },
            "serving_identity": serving_identity,
            "run_dir": str(run_dir.resolve()),
        }
        started = {
            **common,
            "artifact_type": "s4_qwen_development_calibration_started",
        }
        calibration._atomic_create_json(run_dir / "STARTED.json", started)  # noqa: SLF001
        result = {
            **common,
            "artifact_type": "s4_qwen_development_calibration_result",
            "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "calls": calls, "evaluation": evaluation,
            "gold_access": {
                "semantic_gold_consulted": False,
                "gold_files_opened_by_calibration_harness": False,
                "semantic_adjudication": "separate blind process required",
            },
        }
        result_path = Path(reservation["output_path"])
        calibration._atomic_create_json(result_path, result)  # noqa: SLF001
        calibration.finalize_candidate_receipt(
            reservation, status="PASS", result_path=result_path,
            traces=[row["trace"] for row in calls],
        )
        run_dir.chmod(0o555)
        return {
            "fixture_root": fixture_root, "manifest": manifest,
            "manifest_path": manifest_path, "attempts": attempts,
            "result_path": result_path, "run_dir": run_dir,
            "candidate": candidate,
        }

    def _receipts(self) -> tuple[list[dict], list[dict]]:
        plan = calibration.build_call_plan(4)
        receipts = []
        primary_raw = "a" * 64
        for index, row in enumerate(plan):
            raw = f"{index + 10:064x}"
            if row["role"] in {"pre_primary", "pre_same_seed_repeat"} \
                    and row["variant_index"] == 0:
                raw = primary_raw
            if row["role"] == "pre_different_seed":
                raw = "b" * 64
            receipts.append({
                **copy.deepcopy(row),
                "raw_response_sha256": raw,
                "prompt_sha256": (
                    "prompt-0" if row["variant_index"] == 0
                    and row["role"].startswith("pre_") else f"prompt-{index}"
                ),
                "messages_sha256": (
                    "messages-0" if row["variant_index"] == 0
                    and row["role"].startswith("pre_") else f"messages-{index}"
                ),
                "messages_without_reasoning_sha256": (
                    f"post-context-{row['variant_id']}"
                    if row["role"].startswith("post_") else f"pre-context-{index}"
                ),
                "history_reasoning_chars": (
                    123 if row["role"] == "post_preserved" else 0
                ),
                "image_sha256s": (
                    ["image-0"] if row["variant_index"] == 0
                    and row["role"].startswith("pre_")
                    else ([f"post-image-{row['variant_id']}"]
                          if row["role"].startswith("post_") else [f"image-{index}"])
                ),
                "completeness": "complete",
                "payload_present": True,
                "schema_errors": [],
                "ranking_compliance": True,
            })
        return plan, receipts

    def _semantic_tree(self, root: Path) -> dict:
        tree = self._valid_authority_tree(root)
        key = b"semantic-test-key-material-32-bytes-minimum"
        semantic_output = root / "semantic-runs"
        semantic_attempts = root / "semantic-attempts"
        with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                               _fixed_dev_root(tree["fixture_root"])), \
                mock.patch.object(
                    calibration, "verify_development_assets",
                    return_value=(tree["manifest"], tree["manifest_path"]),
                ), mock.patch.object(calibration, "_validate_exact_call_contexts"):
            worksheet, worksheet_path = calibration.create_blind_semantic_worksheet(
                tree["result_path"], blinding_key=key,
                fixture_root=tree["fixture_root"],
                calibration_attempt_root=tree["attempts"],
                output_root=semantic_output,
                semantic_attempt_root=semantic_attempts,
                require_live_environment=False,
            )
        return {
            **tree, "key": key, "worksheet": worksheet,
            "worksheet_path": worksheet_path,
            "semantic_output": semantic_output,
            "semantic_attempts": semantic_attempts,
        }

    @staticmethod
    def _semantic_judgments(
        worksheet: dict, worksheet_path: Path, *, plan_verdict: bool = False,
    ) -> dict:
        sample_ids = {
            sample["sample_id"]
            for pair in worksheet["pairs"] for sample in pair["samples"]
        }
        return {
            "format_version": calibration.SEMANTIC_FORMAT_VERSION,
            "protocol_version": calibration.SEMANTIC_PROTOCOL_VERSION,
            "artifact_type": "s4_qwen_calibration_blind_semantic_judgments",
            "adjudicator": "blind-human-1",
            "adjudicated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "blind_worksheet_sha256": calibration.sha256_file(worksheet_path),
            "blind_attestation": copy.deepcopy(
                calibration.SEMANTIC_BLIND_ATTESTATION
            ),
            "verdicts": {
                sample_id: {
                    "goal_correct_in_kind": True,
                    "constraints_by_item": [True, True],
                    "plan_executable": plan_verdict,
                }
                for sample_id in sample_ids
            },
        }

    def _finalize_semantic(self, tree: dict, judgments: dict) -> tuple[dict, Path]:
        source = Path(tree["worksheet_path"]).parent.parent / "human-input.json"
        source.write_text(json.dumps(judgments, indent=1, sort_keys=True) + "\n")
        with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                               _fixed_dev_root(tree["fixture_root"])), \
                mock.patch.object(
                    calibration, "verify_development_assets",
                    return_value=(tree["manifest"], tree["manifest_path"]),
                ), mock.patch.object(calibration, "_validate_exact_call_contexts"):
            return calibration.finalize_blind_semantic_adjudication(
                tree["result_path"], tree["worksheet_path"], source,
                blinding_key=tree["key"], fixture_root=tree["fixture_root"],
                calibration_attempt_root=tree["attempts"],
                semantic_attempt_root=tree["semantic_attempts"],
                require_live_environment=False,
            )

    def test_plan_is_exactly_eleven_official_sampler_calls(self) -> None:
        document = calibration.plan_document(4)
        plan = document["call_plan"]
        self.assertEqual(len(plan), 11)
        self.assertEqual(document["call_budget"], 11)
        self.assertEqual(document["answer_tokens"], 32_768)
        self.assertEqual(document["sampler"], calibration.OFFICIAL_THINKING_SAMPLER)
        self.assertEqual(document["reasoning_effort"], "xhigh")
        self.assertTrue(document["preserve_thinking"])
        self.assertEqual(document["constraints"]["kaggle_submissions"], 0)
        self.assertFalse(document["constraints"]["temperature_or_top_p_grid"])
        self.assertFalse(document["truncation_escalation"]["automatic"])
        roles = [row["role"] for row in plan]
        self.assertEqual(roles.count("pre_primary"), 3)
        self.assertEqual(roles.count("pre_same_seed_repeat"), 1)
        self.assertEqual(roles.count("pre_different_seed"), 1)
        self.assertEqual(roles.count("post_stripped"), 3)
        self.assertEqual(roles.count("post_preserved"), 3)
        primary = next(row for row in plan if row["role"] == "pre_primary"
                       and row["variant_index"] == 0)
        repeat = next(row for row in plan if row["role"] == "pre_same_seed_repeat")
        different = next(row for row in plan if row["role"] == "pre_different_seed")
        self.assertEqual(primary["seed"], repeat["seed"])
        self.assertNotEqual(primary["seed"], different["seed"])
        for variant_id in {row["variant_id"] for row in plan}:
            post = [row for row in plan if row["variant_id"] == variant_id
                    and row["role"].startswith("post_")]
            self.assertEqual(len(post), 2)
            self.assertEqual(post[0]["seed"], post[1]["seed"])

    def test_mechanical_evaluation_passes_only_with_live_rng_and_no_regression(self) -> None:
        plan, receipts = self._receipts()
        result = calibration.evaluate_calibration(plan, receipts)
        self.assertTrue(result["pass"])
        self.assertTrue(result["same_seed_raw_reproducible"])
        self.assertTrue(result["different_seed_raw_changed"])
        self.assertEqual(result["semantic_goal_scoring"],
                         "NOT_PERFORMED_BY_THIS_HARNESS")

        broken_repeat = copy.deepcopy(receipts)
        next(row for row in broken_repeat
             if row["role"] == "pre_same_seed_repeat")["raw_response_sha256"] = "c" * 64
        self.assertFalse(calibration.evaluate_calibration(plan, broken_repeat)["pass"])

        stuck_rng = copy.deepcopy(receipts)
        next(row for row in stuck_rng
             if row["role"] == "pre_different_seed")["raw_response_sha256"] = "a" * 64
        stuck = calibration.evaluate_calibration(plan, stuck_rng)
        self.assertFalse(stuck["pass"])
        self.assertFalse(stuck["different_seed_raw_changed"])

        regression = copy.deepcopy(receipts)
        next(row for row in regression
             if row["role"] == "post_preserved")["payload_present"] = False
        self.assertFalse(calibration.evaluate_calibration(plan, regression)["pass"])

    def test_truncation_is_only_marked_for_manual_predeclared_escalation(self) -> None:
        plan, receipts = self._receipts()
        receipts[0]["completeness"] = "truncated"
        receipts[0]["payload_present"] = False
        result = calibration.evaluate_calibration(plan, receipts)
        self.assertFalse(result["pass"])
        escalation = result["manual_truncation_escalation"]
        self.assertEqual(escalation["eligible_call_tags"], [receipts[0]["tag"]])
        self.assertFalse(escalation["automatic"])
        self.assertEqual(escalation["max_tokens"], 49_152)

    def test_stripped_history_removes_only_reasoning_and_does_not_mutate(self) -> None:
        original = {
            "role": "assistant", "content": "visible answer",
            "reasoning_content": "hidden reasoning",
        }
        stripped = calibration.stripped_history(original)
        self.assertEqual(stripped, {"role": "assistant", "content": "visible answer"})
        self.assertIn("reasoning_content", original)

    def test_append_only_writer_and_sealed_path_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "receipt.json"
            calibration._atomic_create_json(path, {"ok": True})  # noqa: SLF001
            self.assertEqual(json.loads(path.read_text()), {"ok": True})
            self.assertEqual(path.stat().st_mode & 0o222, 0)
            with self.assertRaises(RuntimeError):
                calibration._atomic_create_json(path, {"ok": False})  # noqa: SLF001
            with self.assertRaises(RuntimeError):
                calibration.assert_development_paths(
                    sentinels.SEALED_R4 / "fixtures/sentinels", root / "out",
                )
            with self.assertRaises(RuntimeError):
                calibration.assert_development_paths(
                    root / "fixtures", sentinels.SEALED_R4 / "calibration",
                )

    def test_candidate_reservation_is_fixed_across_output_paths_and_one_shot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = {"candidate": "same immutable bytes"}
            first = calibration.reserve_candidate_attempt(
                candidate, output_root=root / "runs-a", attempt_root=root / "attempts",
            )
            self.assertEqual(first["candidate_id"], calibration.canonical_sha256(candidate))
            reservation = Path(first["reservation_path"])
            self.assertTrue(reservation.is_file())
            self.assertEqual(reservation.stat().st_mode & 0o222, 0)
            with self.assertRaises(RuntimeError):
                calibration.reserve_candidate_attempt(
                    candidate, output_root=root / "runs-b",
                    attempt_root=root / "attempts",
                )
            receipt = calibration.finalize_candidate_receipt(
                first, status="EXCEPTION", result_path=None, traces=[], error="test",
            )
            self.assertTrue(Path(receipt["receipt_path"]).is_file())
            with self.assertRaises(RuntimeError):
                calibration.finalize_candidate_receipt(
                    first, status="EXCEPTION", result_path=None, traces=[], error="retry",
                )

    def test_candidate_contract_rejects_dirty_git_before_fingerprinting(self) -> None:
        fake_manifest = {
            "generator_sha256": "g" * 64, "asset_files": {"assets/x": "a" * 64},
        }
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                  _fixed_dev_root(Path(temporary))), \
                mock.patch.object(calibration, "verify_development_assets",
                                  return_value=(fake_manifest,
                                                Path(temporary) / "sentinel_manifest.json")), \
                mock.patch.object(calibration.probe, "capture_git_state",
                                  return_value={"commit": "a" * 40, "dirty": True,
                                                "status": [" M file"]}), \
                mock.patch.object(calibration.probe, "fingerprint") as fingerprint:
            with self.assertRaisesRegex(RuntimeError, "clean committed worktree"):
                calibration.build_candidate_contract(
                    model=Path(temporary) / "model",
                    fixture_root=Path(temporary),
                    attempt_root=Path(temporary) / "attempts",
                )
            fingerprint.assert_not_called()

    def test_seed_authority_chain_is_mechanical_and_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            attempts = Path(temporary) / "attempts"
            genesis = calibration.required_next_seed(attempts)
            self.assertEqual(genesis["base_seed"], calibration.INITIAL_BASE_SEED)
            self.assertIsNone(genesis["predecessor_candidate_id"])
            attempts.mkdir()
            result_path = Path(temporary) / "RESULT.json"
            result_path.write_text('{"sealed": true}\n')
            receipt = {
                "candidate_id": "x" * 64,
                "result": {"path": str(result_path),
                           "sha256": calibration.sha256_file(result_path)},
                "finished_utc": "2026-08-18T10:00:00+00:00",
            }
            (attempts / ("x" * 64 + ".receipt.json")).write_text(json.dumps(receipt))
            successor = calibration.required_next_seed(attempts)
            expected_seed = int.from_bytes(hashlib.sha256(
                result_path.read_bytes()).digest()[:8], "big") % (2 ** 63)
            self.assertEqual(successor, {
                "base_seed": expected_seed,
                "predecessor_candidate_id": "x" * 64,
                "source": "terminal_result",
                "source_sha256": hashlib.sha256(
                    result_path.read_bytes()).hexdigest(),
                "derivation": calibration.SEED_DERIVATION,
            })
            # Excluding the only terminal candidate falls back to genesis.
            self.assertEqual(calibration.required_next_seed(
                attempts, exclude_candidate_id="x" * 64)["base_seed"],
                calibration.INITIAL_BASE_SEED)
            # A crash receipt without a bound result derives from receipt bytes.
            crash_path = attempts / ("y" * 64 + ".receipt.json")
            crash_path.write_text(json.dumps({
                "candidate_id": "y" * 64, "result": None,
                "finished_utc": "2026-08-18T11:00:00+00:00",
            }))
            after_crash = calibration.required_next_seed(attempts)
            self.assertEqual(after_crash["predecessor_candidate_id"], "y" * 64)
            self.assertEqual(after_crash["source"], "terminal_receipt")
            self.assertEqual(after_crash["base_seed"], int.from_bytes(
                hashlib.sha256(crash_path.read_bytes()).digest()[:8],
                "big") % (2 ** 63))
            # Tampering with a bound terminal result fails the whole chain.
            result_path.write_text('{"sealed": "tampered"}\n')
            with self.assertRaisesRegex(RuntimeError, "stale"):
                calibration.required_next_seed(attempts)

    def test_validation_refuses_superseded_or_shopped_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tree = self._valid_authority_tree(Path(temporary))
            # A later terminal attempt supersedes the tree's candidate: the
            # anti-shopping rule must refuse validating the earlier one.
            (tree["attempts"] / ("f" * 64 + ".receipt.json")).write_text(
                json.dumps({
                    "candidate_id": "f" * 64, "result": None,
                    "finished_utc": "2030-01-01T00:00:00+00:00",
                }))
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"):
                with self.assertRaisesRegex(RuntimeError,
                                            "latest terminal calibration attempt"):
                    calibration.validate_calibration_result(
                        tree["result_path"], fixture_root=tree["fixture_root"],
                        attempt_root=tree["attempts"],
                        require_live_environment=False,
                    )

    def test_strict_result_validator_rederives_complete_authority(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tree = self._valid_authority_tree(Path(temporary))
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"):
                binding = calibration.validate_calibration_result(
                    tree["result_path"], fixture_root=tree["fixture_root"],
                    attempt_root=tree["attempts"], require_live_environment=False,
                )
            self.assertEqual(binding["status"], "PASS")
            self.assertEqual(binding["candidate_id"],
                             calibration.canonical_sha256(tree["candidate"]))
            self.assertEqual(binding["git_commit"], "a" * 40)
            self.assertEqual(binding["checkpoint_sha256"], "c" * 64)

    def test_strict_result_validator_rejects_trace_and_live_checkpoint_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tree = self._valid_authority_tree(Path(temporary))
            trace_path = next(tree["run_dir"].glob("*.trace.json"))
            trace_path.chmod(0o644)
            trace_path.write_text(trace_path.read_text() + " ")
            trace_path.chmod(0o444)
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    self.assertRaisesRegex(RuntimeError, "trace binding"):
                calibration.validate_calibration_result(
                    tree["result_path"], fixture_root=tree["fixture_root"],
                    attempt_root=tree["attempts"], require_live_environment=False,
                )

        with tempfile.TemporaryDirectory() as temporary:
            tree = self._valid_authority_tree(Path(temporary))
            wrong = copy.deepcopy(tree["candidate"]["checkpoint_identity"])
            wrong["checkpoint_sha256"] = "d" * 64
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(
                        calibration.probe, "capture_git_state",
                        return_value=tree["candidate"]["git"],
                    ), mock.patch.object(
                        calibration.probe, "fingerprint", return_value=wrong,
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    self.assertRaisesRegex(RuntimeError, "checkpoint/runtime"):
                calibration.validate_calibration_result(
                    tree["result_path"], model=Path(temporary) / "model",
                    fixture_root=tree["fixture_root"], attempt_root=tree["attempts"],
                    require_live_environment=True,
                )

    def test_blind_semantic_workflow_is_one_shot_and_independently_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tree = self._semantic_tree(Path(temporary))
            serialized = json.dumps(tree["worksheet"], sort_keys=True).casefold()
            self.assertNotIn("stripped", serialized)
            self.assertNotIn("preserved", serialized)
            self.assertNotIn("history_condition", serialized)
            self.assertEqual(len(tree["worksheet"]["pairs"]), 3)
            self.assertEqual(sum(len(pair["samples"])
                                 for pair in tree["worksheet"]["pairs"]), 6)
            source_rows = calibration._semantic_source_rows(  # noqa: SLF001
                json.loads(tree["result_path"].read_text())
            )
            natural_word = copy.deepcopy(tree["worksheet"])
            natural_word["pairs"][0]["samples"][0]["model_best_goal"][
                "plain_causal_condition"
            ] = "the charged state is preserved until completion"
            calibration._assert_semantic_blindness(  # noqa: SLF001
                natural_word, source_rows,
            )
            metadata_leak = copy.deepcopy(tree["worksheet"])
            metadata_leak["blinding"]["debug_assignment"] = "preserved"
            with self.assertRaisesRegex(RuntimeError, "leaks condition label"):
                calibration._assert_semantic_blindness(  # noqa: SLF001
                    metadata_leak, source_rows,
                )

            judgments = self._semantic_judgments(
                tree["worksheet"], tree["worksheet_path"], plan_verdict=False,
            )
            result, result_path = self._finalize_semantic(tree, judgments)
            self.assertTrue(result["operational_non_inferiority"]["pass"])
            self.assertFalse(result["operational_non_inferiority"]["definition"]
                             ["statistical_non_inferiority_claim"])
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"):
                binding = calibration.validate_semantic_adjudication(
                    result_path, calibration_result_path=tree["result_path"],
                    blinding_key=tree["key"],
                    fixture_root=tree["fixture_root"],
                    calibration_attempt_root=tree["attempts"],
                    semantic_attempt_root=tree["semantic_attempts"],
                    require_live_environment=False,
                )
            self.assertEqual(binding["status"], "PASS")
            self.assertEqual(binding["adjudicator"], "blind-human-1")
            self.assertEqual(
                binding["blinding_key_commitment_sha256"],
                hashlib.sha256(tree["key"]).hexdigest(),
            )
            self.assertEqual(Path(result_path).parent.stat().st_mode & 0o222, 0)
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    self.assertRaisesRegex(RuntimeError, "blinding key mismatch"):
                calibration.validate_semantic_adjudication(
                    result_path, calibration_result_path=tree["result_path"],
                    blinding_key=b"wrong-semantic-key-material-32bytes",
                    fixture_root=tree["fixture_root"],
                    calibration_attempt_root=tree["attempts"],
                    semantic_attempt_root=tree["semantic_attempts"],
                    require_live_environment=False,
                )

    def test_semantic_creation_cannot_retry_with_another_key_or_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tree = self._semantic_tree(Path(temporary))
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    self.assertRaisesRegex(RuntimeError, "attempt 0"):
                calibration.create_blind_semantic_worksheet(
                    tree["result_path"], blinding_key=b"x" * 32,
                    fixture_root=tree["fixture_root"],
                    calibration_attempt_root=tree["attempts"],
                    output_root=Path(temporary) / "alternate-output",
                    semantic_attempt_root=tree["semantic_attempts"],
                    require_live_environment=False,
                )

    def test_malformed_semantic_judgment_is_sealed_and_blocks_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = self._semantic_tree(root)
            malformed = root / "malformed-human-input.json"
            malformed_bytes = b'{"adjudicator": "first-but-malformed"'
            malformed.write_bytes(malformed_bytes)
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    self.assertRaises(RuntimeError):
                calibration.finalize_blind_semantic_adjudication(
                    tree["result_path"], tree["worksheet_path"], malformed,
                    blinding_key=tree["key"], fixture_root=tree["fixture_root"],
                    calibration_attempt_root=tree["attempts"],
                    semantic_attempt_root=tree["semantic_attempts"],
                    require_live_environment=False,
                )
            fixed = tree["worksheet_path"].parent / "JUDGMENTS.json"
            self.assertEqual(fixed.read_bytes(), malformed_bytes)
            self.assertEqual(fixed.stat().st_mode & 0o222, 0)
            receipt_path = next(tree["semantic_attempts"].glob("*.receipt.json"))
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["status"], "FAIL")
            self.assertIsNone(receipt["result"])
            self.assertEqual(receipt["judgments"]["sha256"],
                             calibration.sha256_file(fixed))
            self.assertEqual(tree["worksheet_path"].parent.stat().st_mode & 0o222, 0)

            alternate = root / "alternate-human-input.json"
            alternate.write_text(json.dumps(self._semantic_judgments(
                tree["worksheet"], tree["worksheet_path"], plan_verdict=False,
            )))
            original_receipt_sha = calibration.sha256_file(receipt_path)
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    self.assertRaisesRegex(RuntimeError, "already consumed"):
                calibration.finalize_blind_semantic_adjudication(
                    tree["result_path"], tree["worksheet_path"], alternate,
                    blinding_key=tree["key"], fixture_root=tree["fixture_root"],
                    calibration_attempt_root=tree["attempts"],
                    semantic_attempt_root=tree["semantic_attempts"],
                    require_live_environment=False,
                )
            self.assertEqual(fixed.read_bytes(), malformed_bytes)
            self.assertEqual(calibration.sha256_file(receipt_path), original_receipt_sha)

    def test_semantic_internal_exception_gets_terminal_receipt_and_no_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tree = self._semantic_tree(root)
            judgments = self._semantic_judgments(
                tree["worksheet"], tree["worksheet_path"], plan_verdict=False,
            )
            source = root / "human-input.json"
            source.write_text(json.dumps(judgments, sort_keys=True) + "\n")
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    mock.patch.object(
                        calibration, "_validate_semantic_judgments",
                        side_effect=ValueError("forced adjudication fault"),
                    ), self.assertRaisesRegex(ValueError, "forced adjudication fault"):
                calibration.finalize_blind_semantic_adjudication(
                    tree["result_path"], tree["worksheet_path"], source,
                    blinding_key=tree["key"], fixture_root=tree["fixture_root"],
                    calibration_attempt_root=tree["attempts"],
                    semantic_attempt_root=tree["semantic_attempts"],
                    require_live_environment=False,
                )
            receipt_path = next(tree["semantic_attempts"].glob("*.receipt.json"))
            receipt = json.loads(receipt_path.read_text())
            self.assertEqual(receipt["status"], "EXCEPTION")
            self.assertEqual(receipt["error"]["type"], "ValueError")
            self.assertIsNone(receipt["result"])
            fixed = tree["worksheet_path"].parent / "JUDGMENTS.json"
            self.assertEqual(calibration.sha256_file(fixed),
                             receipt["judgments"]["sha256"])

            alternate = root / "other-adjudicator.json"
            alternate.write_text(json.dumps({**judgments, "adjudicator": "other"}))
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    self.assertRaisesRegex(RuntimeError, "already consumed"):
                calibration.finalize_blind_semantic_adjudication(
                    tree["result_path"], tree["worksheet_path"], alternate,
                    blinding_key=tree["key"], fixture_root=tree["fixture_root"],
                    calibration_attempt_root=tree["attempts"],
                    semantic_attempt_root=tree["semantic_attempts"],
                    require_live_environment=False,
                )

    def test_semantic_non_regression_fails_on_one_preserved_goal_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tree = self._semantic_tree(Path(temporary))
            judgments = self._semantic_judgments(
                tree["worksheet"], tree["worksheet_path"], plan_verdict=False,
            )
            source = json.loads(tree["result_path"].read_text())
            condition_by_trace = {
                row["trace"]["sha256"]: row["history_condition"]
                for row in source["calls"] if row["role"].startswith("post_")
            }
            first_pair = tree["worksheet"]["pairs"][0]
            preserved = next(
                sample for sample in first_pair["samples"]
                if condition_by_trace[sample["trace_sha256"]] == "preserved"
            )
            judgments["verdicts"][preserved["sample_id"]][
                "goal_correct_in_kind"
            ] = False
            result, result_path = self._finalize_semantic(tree, judgments)
            self.assertFalse(result["operational_non_inferiority"]["pass"])
            with mock.patch.object(calibration.sentinels, "dev_fixture_root",
                                   _fixed_dev_root(tree["fixture_root"])), \
                    mock.patch.object(
                        calibration, "verify_development_assets",
                        return_value=(tree["manifest"], tree["manifest_path"]),
                    ), mock.patch.object(calibration, "_validate_exact_call_contexts"), \
                    self.assertRaisesRegex(RuntimeError, "did not pass"):
                calibration.validate_semantic_adjudication(
                    result_path, calibration_result_path=tree["result_path"],
                    blinding_key=tree["key"],
                    fixture_root=tree["fixture_root"],
                    calibration_attempt_root=tree["attempts"],
                    semantic_attempt_root=tree["semantic_attempts"],
                    require_live_environment=False,
                )

    def test_semantic_plan_replay_uses_inverse_pilot_action_mapping(self) -> None:
        fixture = sentinels.build_active_variant("dev", 0, 4)
        route = sentinels._route(  # noqa: SLF001
            fixture["layout"], ["zone_a", "zone_b"],
        )
        plan = [
            {"action": sentinels._action_schema(label)}  # noqa: SLF001
            for label in route
        ]
        replay = calibration._replay_semantic_plan(  # noqa: SLF001
            fixture, plan, action_budget=2 * len(route),
        )
        self.assertTrue(replay["pass"])
        self.assertTrue(sentinels.objective_holds(fixture["layout"], route))
        self.assertLessEqual(replay["completed_at_action"], len(route))
        self.assertIsNone(replay["schema_error"])

        invalid_id = calibration._replay_semantic_plan(  # noqa: SLF001
            fixture, [{"action": {"id": 5, "click": None}}],
            action_budget=2 * len(route),
        )
        invalid_click = calibration._replay_semantic_plan(  # noqa: SLF001
            fixture, [{"action": {"id": 0, "click": [0, 0]}}],
            action_budget=2 * len(route),
        )
        self.assertFalse(invalid_id["pass"])
        self.assertFalse(invalid_click["pass"])
        self.assertIsNotNone(invalid_id["schema_error"])
        self.assertIsNotNone(invalid_click["schema_error"])

    def test_semantic_plan_verdict_must_equal_exact_reset_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            tree = self._semantic_tree(Path(temporary))
            judgments = self._semantic_judgments(
                tree["worksheet"], tree["worksheet_path"], plan_verdict=True,
            )
            with self.assertRaisesRegex(RuntimeError, "exact replay"):
                self._finalize_semantic(tree, judgments)

    def test_semantic_cli_modes_are_exclusive_and_forward_file_key_bytes(self) -> None:
        with self.assertRaises(SystemExit):
            calibration._parser().parse_args([  # noqa: SLF001
                "--prepare-semantic", "calibration.json",
                "--validate-semantic", "semantic.json",
            ])
        with self.assertRaisesRegex(RuntimeError, "--model"):
            calibration.main(["--prepare-semantic", "calibration.json"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key_path = root / "blind.key"
            key_bytes = b"k" * 32
            key_path.write_bytes(key_bytes)
            fake_worksheet = {
                "pairs": [{"samples": [{}, {}]} for _ in range(3)],
            }
            with mock.patch.object(
                calibration, "create_blind_semantic_worksheet",
                return_value=(fake_worksheet, root / "BLIND_WORKSHEET.json"),
            ) as prepare:
                status = calibration.main([
                    "--prepare-semantic", str(root / "calibration.json"),
                    "--model", str(root / "model"),
                    "--blinding-key", str(key_path),
                ])
            self.assertEqual(status, 0)
            self.assertEqual(prepare.call_args.kwargs["blinding_key"], key_bytes)
            self.assertEqual(prepare.call_args.args[0], root / "calibration.json")

    def test_cli_rejects_options_irrelevant_to_each_mode(self) -> None:
        cases = (
            (["--plan", "--model", "model"], "--model"),
            (["--run", "--model", "model", "--judgments", "j.json"],
             "--judgments"),
            (["--validate-result", "result.json", "--model", "model",
              "--output-root", "out"], "--output-root"),
            (["--prepare-semantic", "result.json", "--model", "model",
              "--blinding-key", "key", "--worksheet", "worksheet.json"],
             "--worksheet"),
            (["--finalize-semantic", "result.json", "--model", "model",
              "--blinding-key", "key", "--worksheet", "worksheet.json",
              "--judgments", "judgments.json", "--semantic-output-root", "out"],
             "--semantic-output-root"),
            (["--validate-semantic", "semantic.json", "--model", "model",
              "--calibration-result", "result.json", "--blinding-key", "key",
              "--base-seed", "4"], "--base-seed"),
        )
        for argv, option in cases:
            with self.subTest(argv=argv), self.assertRaisesRegex(
                    RuntimeError, option):
                calibration.main(argv)

    def test_cli_mode_validation_preserves_implicit_and_relevant_defaults(self) -> None:
        parser = calibration._parser()  # noqa: SLF001
        for argv in (
            ["--plan"],
            ["--plan", "--base-seed", "4"],
            ["--run", "--model", "model"],
            ["--run", "--model", "model", "--output-root",
             str(calibration.OUTPUT_ROOT)],
        ):
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                calibration._validate_cli_mode_options(args, argv)  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
