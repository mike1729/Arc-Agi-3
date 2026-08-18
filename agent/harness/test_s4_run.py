#!/usr/bin/env python3
"""No-model regression tests for the closure-grade Slice-4 runner."""

from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from PIL import Image

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_run as run


def valid_payload(*, probe_request: bool = False, retrieval_request: bool = False) -> dict:
    return {
        "hypotheses": [{
            "probability": 0.7,
            "necessary_conditions": ["condition"],
            "sufficient_condition": "condition and relation",
            "evidence_for": ["E001"],
            "evidence_against": [],
            "predicted_counterexample": "E002 would differ",
        }],
        "best_goal": {
            "plain_causal_condition": "make the relation hold",
            "structured_factors": ["relation"],
        },
        "next_probe": {
            "start_state_id": "S00001" if probe_request else None,
            "action": {"id": 6, "click": [2, 3]} if probe_request else None,
            "predictions_by_hypothesis": {"0": "the object changes"},
        },
        "retrieval_requests": (
            [{"op": "SHOW_FRAME", "args": ["S00001"]}]
            if retrieval_request else []
        ),
        "goal_directed_plan": [{"action": {"id": 1, "click": None}}],
    }


def complete_record() -> dict:
    return {"completeness": "complete"}


def packet(page: Path | None = None) -> dict:
    page_name = page.name if page is not None else "page.png"
    raw = [{
        "page": 1, "kind": "raw", "file": page_name, "caption": "raw",
        "visual_tokens": 64,
    }]
    overlay = [{
        "page": 1, "kind": "overlay", "file": page_name, "caption": "overlay",
        "visual_tokens": 64,
    }]
    return {
        "blind_id": "G000001",
        "dir": page.parent if page is not None else Path("."),
        "manifest": {
            "evidence_items": [{"evidence_id": "E001"}],
            "carrier_pages": {"raw": raw, "overlay": overlay},
            "input_bundle_sha256": "bundle",
        },
        "ledger": "ledger",
        "manifest_sha256": "manifest",
        "ledger_sha256": "ledger-sha",
    }


class ParsingTests(unittest.TestCase):
    def test_nested_final_object_is_parsed_as_the_root(self) -> None:
        expected = valid_payload(probe_request=True)
        answer = "reasoning prose\n" + json.dumps(expected, indent=2) + "\n"
        parsed = run.extract_final_json(answer)
        self.assertEqual(parsed, expected)
        self.assertEqual(run.validate_answer(parsed), [])

    def test_ask_chat_trace_is_an_immutable_complete_serving_receipt(self) -> None:
        class Processor:
            template_kwargs: dict | None = None

            def apply_chat_template(self, messages, **kwargs):
                self.template_kwargs = kwargs
                return "<|im_start|>user\nrequest<|im_start|>assistant\n<think>"

            def __call__(self, **kwargs):
                del kwargs
                import numpy as np
                return {"input_ids": np.zeros((1, 10), dtype=np.int64),
                        "image_grid_thw": None}

        class Vlm:
            def __init__(self):
                self.processor = Processor()
                self.model = object()
                self.path = "fake-qwen"

        class Output:
            text = "causal reasoning</think>" + json.dumps(valid_payload())
            prompt_tokens = 10
            generation_tokens = 20
            total_tokens = 30
            cached_tokens = 0
            finish_reason = "stop"
            prompt_tps = 1.0
            generation_tps = 1.0
            peak_memory = 0

        with tempfile.TemporaryDirectory() as temporary:
            messages = [{"role": "user", "content": [{"type": "text", "text": "request"}]}]
            fake_mlx = types.ModuleType("mlx")
            fake_core = types.ModuleType("mlx.core")
            fake_core.random = types.SimpleNamespace(seed=lambda _seed: None)
            fake_mlx.core = fake_core
            fake_mlx_vlm = types.ModuleType("mlx_vlm")
            fake_mlx_vlm.generate = lambda *args, **kwargs: Output()
            with (
                mock.patch("s4_ledgers.append"),
                mock.patch.dict(sys.modules, {
                    "mlx": fake_mlx,
                    "mlx.core": fake_core,
                    "mlx_vlm": fake_mlx_vlm,
                }),
            ):
                record, payload, answer = run.ask_chat(
                    Vlm(), messages, [], seed=1, max_tokens=100,
                    run_dir=Path(temporary), tag="receipt_r0",
                    max_input_text_tokens=100,
                    serving_identity={"checkpoint_sha256": "c" * 64},
                    round_index=0, round_kind="initial",
                )
            messages.append({"role": "user", "content": "later mutation"})
            self.assertEqual(len(record["messages"]), 1)
            self.assertTrue(record["preserve_thinking"])
            self.assertTrue(record["assistant_history"]["reasoning_content"])
            self.assertEqual(record["assistant_history"]["content"], answer)
            self.assertEqual(record["parsed_payload"], payload)
            self.assertEqual(record["input_tokens"], 10)
            self.assertEqual(record["output_tokens"], 20)
            self.assertEqual(run.sha256_file(Path(record["trace_path"])),
                             record["trace_sha256"])

    def test_trailing_text_and_truncated_outer_object_never_validate(self) -> None:
        encoded = json.dumps(valid_payload())
        self.assertIsNone(run.extract_final_json(encoded + " trailing"))
        truncated = '{"hypotheses":[{"probability": 1}'
        parsed = run.extract_final_json(truncated)
        self.assertTrue(parsed is None or run.validate_answer(parsed))

    def test_schema_rejects_leaf_and_probability_errors(self) -> None:
        self.assertTrue(run.validate_answer({"id": 1, "click": None}))
        payload = valid_payload()
        payload["hypotheses"].append({**payload["hypotheses"][0], "probability": 0.8})
        errors = run.validate_answer(payload)
        self.assertTrue(any("sum" in error for error in errors), errors)
        # Calibration v2: ordering is a nonfatal diagnostic, never a schema error.
        self.assertFalse(any("ranked" in error for error in errors), errors)
        self.assertIs(run.ranking_compliance(payload["hypotheses"]), False)

    def test_ranking_is_nonfatal_diagnostic_with_derived_original_indices(self) -> None:
        payload = valid_payload()
        template = payload["hypotheses"][0]
        payload["hypotheses"] = [
            {**template, "probability": 0.2},
            {**template, "probability": 0.7},
            {**template, "probability": 0.1},
        ]
        # Structurally valid though unordered: no schema error, diagnostic False.
        self.assertEqual(run.validate_answer(payload), [])
        self.assertIs(run.ranking_compliance(payload["hypotheses"]), False)
        self.assertEqual(
            run.ranked_hypothesis_indices(payload["hypotheses"]), [1, 0, 2])
        # Ties break by original index; compliant lists report True.
        self.assertEqual(run.ranked_hypothesis_indices(
            [{"probability": 0.4}, {"probability": 0.4}, {"probability": 0.1}],
        ), [0, 1, 2])
        self.assertIs(run.ranking_compliance(
            [{"probability": 0.7}, {"probability": 0.2}]), True)
        # Unstatable cases: no repair, no guess.
        self.assertIsNone(run.ranking_compliance([]))
        self.assertIsNone(run.ranking_compliance([{"probability": True}]))
        self.assertEqual(run.ranked_hypothesis_indices([{"probability": None}]), [])

    def test_invalid_probe_values_are_missing_not_silently_repaired(self) -> None:
        payload = valid_payload(probe_request=True)
        payload["next_probe"]["action"] = {"id": 99, "click": [False, 80]}
        errors = run.validate_answer(payload)
        self.assertTrue(any("action.id" in error for error in errors), errors)
        self.assertTrue(any("action.click" in error for error in errors), errors)
        # The low-level decoder itself still performs no coercion.
        self.assertEqual(run._probe_click([False, 80]), (False, 80))


class PacketLoadTests(unittest.TestCase):
    def test_legacy_packet_is_rejected_before_any_prefix_hash_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packet_dir = root / "G000001"
            packet_dir.mkdir()
            (packet_dir / "ledger.txt").write_text("legacy")
            (packet_dir / "packet_manifest.json").write_text(json.dumps({
                "format_version": 2,
                "blind_id": "G000001",
                "ledger_sha256_16": "deadbeefdeadbeef",
                "pages": [],
            }))
            with (
                mock.patch.object(run.spk, "PACKET_ROOT", root),
                mock.patch.object(run.spk, "blind_id", return_value="G000001"),
            ):
                with self.assertRaisesRegex(RuntimeError, "closure-grade format v3"):
                    run.load_packet("game")


class DeliveryTests(unittest.TestCase):
    def test_delivery_never_crosses_reserved_image_slots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "page.png"
            Image.new("RGB", (256, 256), "white").save(image)
            items: list[dict[str, str]] = []
            feedback: list[Path] = []
            log: list[dict] = []
            delivery = run._append_result(
                items, feedback, [image] * 12, "PROBE",
                {"ok": True, "text": "frames", "images": [str(image)] * 3},
                log, image_limit=14,
            )
            self.assertEqual(delivery["delivered_images"], [])
            self.assertEqual(len(delivery["omitted_images"]), 3)
            self.assertFalse(delivery["all_images_delivered"])
            self.assertFalse(delivery["model_visible"])
            self.assertEqual(delivery["context_images_after"], 12)
            self.assertEqual(items, [])
            self.assertEqual(feedback, [])

    def test_omitted_probe_pages_make_cell_indeterminate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "page.png"
            Image.new("RGB", (256, 256), "white").save(image)
            evidence = packet(image)

            class Session:
                def __init__(self, *args, **kwargs):
                    del args, kwargs
                    self.log = []
                    self.probes_spent = 0
                    self.provenance = {"input_bundle_sha256": "bundle"}

                def probe(self, start, action_id, click):
                    self.probes_spent += 1
                    self.log.append({"start": start, "action_id": action_id, "click": click})
                    return {
                        "ok": True, "text": "many frames",
                        "images": [str(image)] * 5,
                    }

            calls: list[dict] = []

            def fake_ask(*args, **kwargs):
                calls.append({"messages": deepcopy(args[1]), **kwargs})
                return complete_record(), valid_payload(probe_request=True), "{}"

            with (
                mock.patch.object(run, "load_packet", return_value=evidence),
                mock.patch.object(run, "load_packet_bound_evidence", return_value={}),
                mock.patch.object(
                    run, "initial_turn",
                    return_value=([{"type": "text", "text": "request"}], [image] * 12),
                ),
                mock.patch.object(run, "ProbeSession", Session),
                mock.patch.object(run, "ask_chat", side_effect=fake_ask),
            ):
                cell = run.run_cell(object(), "game", "A", root, 7, False)
            self.assertEqual(cell["outcome"], "indeterminate_visual_budget")
            # The scoring outcome remains indeterminate, while the producer-side
            # projection must still equal the final trace's parsed payload.
            self.assertEqual(cell["final_answer"], valid_payload(probe_request=True))
            self.assertEqual(len(calls), 4)
            self.assertEqual(cell["delivery_log"][0]["delivered_images"], [])
            self.assertTrue(all(
                call["messages"][-1]["content"][0]["text"] == run.NO_NEW_OBSERVATION
                for call in calls[1:]
            ))


class CellTests(unittest.TestCase):
    def test_protocol_failure_is_missing_not_answered(self) -> None:
        evidence = packet()
        calls = []

        def malformed(*args, **kwargs):
            del args
            calls.append(kwargs)
            return {"completeness": "malformed_schema"}, None, "{\"id\": 1}"

        with (
            mock.patch.object(run, "load_packet", return_value=evidence),
            mock.patch.object(
                run, "initial_turn",
                return_value=([{"type": "text", "text": "request"}], []),
            ),
            mock.patch.object(run, "ask_chat", side_effect=malformed),
        ):
            cell = run.run_cell(object(), "game", "T", Path("."), 4, False)
        self.assertEqual(cell["outcome"], "missing_malformed_or_refusal")
        self.assertIsNone(cell["final_answer"])
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(cell["rounds"]), 4)

    def test_every_arm_gets_four_matched_capped_calls_and_neutral_updates(self) -> None:
        evidence = packet()
        calls: dict[str, list[dict]] = {arm: [] for arm in run.ALL_ARMS}

        class Session:
            def __init__(self, *args, **kwargs):
                del args, kwargs
                self.log = []
                self.probes_spent = 0
                self.provenance = {"input_bundle_sha256": "bundle"}

            def probe(self, start, action_id, click):
                del start, action_id, click
                self.probes_spent += 1
                result = {"ok": False, "error": "invalid"}
                self.log.append(result)
                return result

            def control_probe(self, round_no, seed):
                del round_no, seed
                self.probes_spent += 1
                result = {"ok": False, "error": "unavailable"}
                self.log.append(result)
                return result

            def retrieve(self, op, *args):
                del op, args
                result = {"ok": False, "error": "unavailable"}
                self.log.append(result)
                return result

        def fake_ask(*args, **kwargs):
            arm = kwargs["tag"].split("_")[1]
            calls[arm].append({"messages": deepcopy(args[1]), **kwargs})
            return complete_record(), valid_payload(), "{}"

        with (
            mock.patch.object(run, "load_packet", return_value=evidence),
            mock.patch.object(run, "load_packet_bound_evidence", return_value={}),
            mock.patch.object(
                run, "initial_turn",
                side_effect=lambda game, arm, packet: (
                    [{"type": "text", "text": f"request-{arm}"}], []
                ),
            ),
            mock.patch.object(run, "ProbeSession", Session),
            mock.patch.object(run, "ask_chat", side_effect=fake_ask),
        ):
            cells = {
                arm: run.run_cell(
                    object(), "game", arm, Path("."), 11, False, max_tokens=321
                )
                for arm in run.ALL_ARMS
            }

        reference_seeds = [call["seed"] for call in calls["T"]]
        for arm in run.ALL_ARMS:
            self.assertEqual(len(calls[arm]), 4, arm)
            self.assertEqual([call["seed"] for call in calls[arm]], reference_seeds)
            self.assertEqual([call["max_tokens"] for call in calls[arm]], [321] * 4)
            self.assertEqual(len(cells[arm]["rounds"]), 4)
            self.assertEqual(cells[arm]["pre_probe_answer"], valid_payload())
            self.assertEqual(
                [entry["input_kind"] for entry in cells[arm]["update_log"]],
                ["neutral_no_new_observation"] * 3,
            )
            for call in calls[arm][1:]:
                self.assertEqual(call["messages"][-2]["role"], "assistant")
                self.assertIn("reasoning_content", call["messages"][-2])
                feedback = call["messages"][-1]["content"]
                self.assertEqual(feedback[0]["text"], run.NO_NEW_OBSERVATION)
                self.assertLessEqual(
                    len(feedback[0]["text"]), run.NO_NEW_OBSERVATION_MAX_CHARS
                )


    def test_invalid_probe_and_unavailable_retrieval_get_neutral_placeholders(self) -> None:
        evidence = packet()
        calls: dict[str, list[list[dict]]] = {"A": [], "R": []}
        sessions = []

        class Session:
            def __init__(self, *args, **kwargs):
                del args, kwargs
                self.log = []
                self.probes_spent = 0
                self.provenance = {"input_bundle_sha256": "bundle"}
                self.probe_calls = 0
                self.retrieval_calls = 0
                sessions.append(self)

            def probe(self, start, action_id, click):
                self.probe_calls += 1
                self.probes_spent += 1
                result = {
                    "ok": False, "error": "invalid exact request",
                    "start": start, "action_id": action_id, "click": click,
                }
                self.log.append(result)
                return result

            def retrieve(self, op, *args):
                self.retrieval_calls += 1
                result = {"ok": False, "error": "not in frozen store", "op": op,
                          "args": list(args)}
                self.log.append(result)
                return result

        def fake_ask(*args, **kwargs):
            arm = kwargs["tag"].split("_")[1]
            calls[arm].append(deepcopy(args[1]))
            return complete_record(), valid_payload(
                probe_request=arm == "A", retrieval_request=arm == "R"
            ), "{}"

        with (
            mock.patch.object(run, "load_packet", return_value=evidence),
            mock.patch.object(run, "load_packet_bound_evidence", return_value={}),
            mock.patch.object(
                run, "initial_turn",
                return_value=([{"type": "text", "text": "request"}], []),
            ),
            mock.patch.object(run, "ProbeSession", Session),
            mock.patch.object(run, "ask_chat", side_effect=fake_ask),
        ):
            cell_a = run.run_cell(object(), "game", "A", Path("."), 12, False)
            cell_r = run.run_cell(object(), "game", "R", Path("."), 12, False)

        self.assertEqual(sessions[0].probe_calls, 3)
        self.assertEqual(cell_a["probes_spent"], 3)
        self.assertEqual(sessions[1].retrieval_calls, 3)
        for arm in ("A", "R"):
            self.assertEqual(len(calls[arm]), 4)
            self.assertTrue(all(
                messages[-1]["content"][0]["text"] == run.NO_NEW_OBSERVATION
                for messages in calls[arm][1:]
            ))

    def test_p_delivers_both_probe_and_retrieval_each_update_round(self) -> None:
        evidence = packet()
        sessions = []

        class Session:
            def __init__(self, *args, **kwargs):
                del args, kwargs
                self.log = []
                self.probes_spent = 0
                self.provenance = {"input_bundle_sha256": "bundle"}
                self.probe_calls = 0
                self.retrieval_calls = 0
                sessions.append(self)

            def probe(self, start, action_id, click):
                del start, action_id, click
                self.probe_calls += 1
                self.probes_spent += 1
                return {"ok": True, "text": "probe evidence", "images": []}

            def retrieve(self, op, *args):
                del op, args
                self.retrieval_calls += 1
                return {"ok": True, "text": "retrieval evidence", "images": []}

        calls = []

        def fake_ask(*args, **kwargs):
            calls.append(deepcopy(args[1]))
            return complete_record(), valid_payload(
                probe_request=True, retrieval_request=True
            ), "{}"

        with (
            mock.patch.object(run, "load_packet", return_value=evidence),
            mock.patch.object(run, "load_packet_bound_evidence", return_value={}),
            mock.patch.object(
                run, "initial_turn",
                return_value=([{"type": "text", "text": "request"}], []),
            ),
            mock.patch.object(run, "ProbeSession", Session),
            mock.patch.object(run, "ask_chat", side_effect=fake_ask),
        ):
            cell = run.run_cell(object(), "game", "P", Path("."), 11, False)

        self.assertEqual(len(calls), 4)
        self.assertEqual(sessions[0].probe_calls, 3)
        self.assertEqual(sessions[0].retrieval_calls, 3)
        self.assertEqual(cell["probes_spent"], 3)
        self.assertTrue(all(
            entry["input_kind"] == "environment_evidence"
            and entry["delivered_labels"] == ["PROBE RESULT", "RETRIEVAL SHOW_FRAME"]
            for entry in cell["update_log"]
        ))
        for messages in calls[1:]:
            visible = " ".join(
                item["text"] for item in messages[-1]["content"]
                if item["type"] == "text"
            )
            self.assertIn("probe evidence", visible)
            self.assertIn("retrieval evidence", visible)
            self.assertNotIn(run.NO_NEW_OBSERVATION, visible)


class OneShotReceiptTests(unittest.TestCase):
    def test_fixed_reservation_refuses_a_fresh_timestamp_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = run.reserve_serving_attempt(
                role="qwen", attempt=0, frozen_manifest_sha256="f" * 64,
                run_dir=root / "run-1", output_path=root / "run-1" / "cells.json",
                serving_identity={"checkpoint_sha256": "c" * 64},
                prior_attempt=None, root=root / "sealed",
            )
            self.assertEqual(
                run.sha256_file(Path(first["reservation_path"])),
                first["reservation_sha256"],
            )
            with self.assertRaisesRegex(RuntimeError, "rerun refused"):
                run.reserve_serving_attempt(
                    role="qwen", attempt=0, frozen_manifest_sha256="f" * 64,
                    run_dir=root / "run-2", output_path=root / "run-2" / "cells.json",
                    serving_identity={"checkpoint_sha256": "c" * 64},
                    prior_attempt=None, root=root / "sealed",
                )
            receipt = run.finalize_serving_receipt(
                first, status="done", trace_receipts=[], cell_outcomes=[]
            )
            self.assertEqual(
                run.sha256_file(Path(receipt["receipt_path"])),
                receipt["receipt_sha256"],
            )


class CertificateTests(unittest.TestCase):
    def test_packet_measurement_identity_must_match_certified_checkpoint(self) -> None:
        files = {
            "tokenizer.json": {"bytes": 7, "sha256": "a" * 64},
            "preprocessor_config.json": {"bytes": 9, "sha256": "b" * 64},
        }
        evidence = packet()
        evidence["manifest"]["build_identity"] = {
            "packages": {"transformers": "5.14.1"},
            "processor": {
                "serving_files": files,
                "measurement_identity_sha256": run.canonical_sha256(files),
            },
        }
        certificate = {
            "checkpoint_sha256": "checkpoint",
            "checkpoint_identity": {
                "model_files": files,
                "versions": {"transformers": "5.14.1"},
            },
        }
        with mock.patch.object(run, "pkg_version", return_value="5.14.1"):
            binding = run.verify_packet_serving_identity(evidence, certificate)
            self.assertEqual(
                binding["measurement_identity_sha256"], run.canonical_sha256(files)
            )
            evidence["manifest"]["build_identity"]["processor"]["serving_files"] = {
                **files,
                "tokenizer.json": {"bytes": 7, "sha256": "c" * 64},
            }
            with self.assertRaisesRegex(RuntimeError, "identity drift"):
                run.verify_packet_serving_identity(evidence, certificate)

    def test_certificate_requires_live_full_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            certificate = root / "certificate.json"
            versions = {name: f"v-{name}" for name in (
                "mlx-vlm", "mlx", "mlx-lm", "transformers"
            )}
            compatibility = {
                "checkpoint_sha256": "checkpoint",
                "script_sha": "script",
                "renderer_sha": "renderer",
                "versions": versions,
                "production_sampler": run.probe.PRODUCTION_SAMPLER,
                "reasoning_effort": run.probe.REASONING_EFFORT,
                "experiment_config": {
                    "max_packet_images": run.MAX_IMAGES,
                    "max_visual_tokens": run.MAX_VISUAL_TOKENS,
                    "stability_replicates": 3,
                    "stability_required_passes": 3,
                },
            }
            compatibility["sha256"] = run.canonical_sha256(compatibility)
            certificate.write_text(json.dumps({
                "status": "done", "passed": True, "verdict": "PASS",
                "gate_statuses": {
                    name: "PASS" for name in run.EXPECTED_GATE_NAMES
                },
                "serving_compatibility": compatibility,
            }))
            identity = {
                key: compatibility[key]
                for key in ("checkpoint_sha256", "script_sha", "renderer_sha", "versions")
            }
            model = root / "model"
            with (
                mock.patch.object(run, "CERTIFICATE", certificate),
                mock.patch.object(run, "pkg_version", side_effect=lambda name: versions[name]),
                mock.patch.object(run.probe, "fingerprint", return_value=identity) as fingerprint,
            ):
                verified = run.verify_certificate(model)
            fingerprint.assert_called_once_with(model)
            self.assertEqual(verified["checkpoint_sha256"], "checkpoint")
            self.assertTrue(verified["certificate_verified_shards"])


if __name__ == "__main__":
    unittest.main()
