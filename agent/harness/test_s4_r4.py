"""Regression coverage for the slice-4 revision-4 contracts.

Covers the refinement plan's explicit list: final-PNG truth decoding, strict
integer coordinates, permutation movement, arm-scoped eligibility,
stale/mismatched continuation rejection, one-shot continuation creation,
control failure ending the version, packet-source read refusal, real token
accounting of the delta channel, 10-to-16-image interaction growth, and
no-silent-repair behavior.  No model, no GPU, no sealed artifacts touched.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_delta as sdl  # noqa: E402
import s4_gates as gates  # noqa: E402
import s4_grade as grade  # noqa: E402
import s4_ledgers as ledgers  # noqa: E402
import s4_packet as spk  # noqa: E402
import s4_qwen_calibration as qcal  # noqa: E402
import s4_render as sr  # noqa: E402
import s4_run as runner  # noqa: E402
import s4_sentinels as sentinels  # noqa: E402


class DeltaChannelTests(unittest.TestCase):
    def test_sequence_record_rederives_and_reapplies_exactly(self) -> None:
        pre = [[0] * 8 for _ in range(8)]
        post = [row[:] for row in pre]
        post[2][3] = 9
        post[2][4] = 9
        record = sdl.sequence_record(["Fa", "Fb"], [pre, post], binding={"tid": "T1"})
        sdl.verify_sequence_record(record, [pre, post])
        self.assertEqual(record["pairs"][0]["bbox"], [2, 3, 2, 4])
        self.assertEqual(record["pairs"][0]["palette_transitions"], {"0->9": 2})
        tampered = json.loads(json.dumps(record))
        tampered["pairs"][0]["changed_cells"] = 3
        with self.assertRaises(RuntimeError):
            sdl.verify_sequence_record(tampered, [pre, post])

    def test_rle_fallback_is_lossless_and_model_carrier_keeps_all_cells(self) -> None:
        pre = [[0] * 16 for _ in range(16)]
        post = [[5] * 16 for _ in range(16)]
        record = sdl.sequence_record(["Fa", "Fb"], [pre, post], binding={"tid": "T2"})
        pair = record["pairs"][0]
        self.assertIn("rle", pair)
        self.assertNotIn("sparse", pair)
        self.assertEqual(sdl.apply_pair_delta(pre, pair), post)
        full = sdl.render_text_block(record)
        compact = sdl.render_text_block(record, include_cells=False)
        carrier = sdl.render_carrier_block(record)
        self.assertIn("rle ", full)
        self.assertNotIn("rle ", compact)
        self.assertIn("changed=256", compact)
        encoded = sdl.encode_exact_pair(pair)
        self.assertIn(f"p0={encoded}", carrier)
        self.assertEqual(sdl.decode_exact_pair(encoded), sdl.decode_rle_delta(pair["rle"]))

    def test_model_carrier_keeps_exact_cells_for_local_changes(self) -> None:
        pre = [[0] * 8 for _ in range(8)]
        post = [row[:] for row in pre]
        post[2][3] = 9
        record = sdl.sequence_record(
            ["T3.pre", "T3.frame:0"], [pre, post],
            binding={"tid": "T3", "evidence_ids": ["E1"],
                     "has_recorded_pre": True},
        )
        carrier = sdl.render_carrier_block(record)
        self.assertIn("frames=pre,f0", carrier)
        encoded = sdl.encode_exact_pair(record["pairs"][0])
        self.assertIn(f"p0={encoded}", carrier)
        self.assertEqual(sdl.decode_exact_pair(encoded), [(2, 3, 0, 9)])

    def test_large_model_carrier_is_exact_not_summary_only(self) -> None:
        pre = [[0] * 64 for _ in range(64)]
        post = [row[:] for row in pre]
        for row in range(12, 36):
            for col in range(7, 43):
                post[row][col] = 6 if (row + col) % 3 else 9
        record = sdl.sequence_record(
            ["T4.pre", "T4.frame:0"], [pre, post],
            binding={"tid": "T4", "evidence_ids": ["E2"],
                     "has_recorded_pre": True},
        )
        pair = record["pairs"][0]
        self.assertGreater(pair["changed_cells"], 8)
        encoded = sdl.encode_exact_pair(pair)
        expected = ([tuple(item) for item in pair["sparse"]]
                    if "sparse" in pair else sdl.decode_rle_delta(pair["rle"]))
        self.assertEqual(sdl.decode_exact_pair(encoded), expected)
        carrier = sdl.render_carrier_collection([record])
        self.assertIn(encoded, carrier)
        self.assertNotIn("exact summaries", carrier)


class GateHarnessTests(unittest.TestCase):
    def test_counter_permutation_moves_every_position(self) -> None:
        first, second = gates.counter_permutations(16, seed=7)
        self.assertEqual(sorted(first), list(range(16)))
        self.assertTrue(all(a != b for a, b in zip(first, second)))

    def test_strict_integer_coordinates_reject_equal_floats(self) -> None:
        truth = {"target_row": 5, "target_col": 7}
        exact = gates.score_call({"target_row": 5, "target_col": 7}, truth,
                                 ["target_row", "target_col"])
        floaty = gates.score_call({"target_row": 5.0, "target_col": 7}, truth,
                                  ["target_row", "target_col"])
        self.assertTrue(exact["pass"])
        self.assertFalse(floaty["pass"])
        self.assertFalse(gates.score_call(None, truth, ["target_row"])["pass"])

    def test_gx_fixture_truth_comes_from_png_decode(self) -> None:
        fixture = gates.build_gx_fixture("dev", 0, base_seed=4)
        plate = sr.render_ruler_crop(
            np.asarray(fixture["grid"], dtype=np.uint8),
            tuple(fixture["window"]), margin=0, cell_px=32,
        )
        decoded = sr.decode_ruler_view(plate)
        r0, c0, _r1, _c1 = plate.bbox
        hits = np.argwhere(decoded == np.asarray(fixture["grid"])[
            fixture["truth"]["target_row"], fixture["truth"]["target_col"]])
        self.assertEqual(hits.shape[0], 1)
        self.assertEqual(int(hits[0][0]) + r0, fixture["truth"]["target_row"])
        self.assertEqual(int(hits[0][1]) + c0, fixture["truth"]["target_col"])

    def test_namespaces_derive_disjoint_fixtures(self) -> None:
        dev = gates.build_gx_fixture("dev", 0, base_seed=4)
        confirm = gates.build_gx_fixture("confirm", 0, base_seed=4)
        self.assertNotEqual(dev["truth"], confirm["truth"])

    def test_arm_scoped_eligibility_never_lets_gd_block(self) -> None:
        results = {claim: {"pass": True} for claim in gates.ALL_CLAIMS}
        results["GD_dense_4px_exact"] = {"pass": False}
        eligibility = gates.derive_arm_eligibility(
            results, ["T", "V", "O", "P"], strict=False,
        )
        self.assertTrue(eligibility["all_selected_arms_eligible"])
        results["GO_overlay_readout"] = {"pass": False}
        eligibility = gates.derive_arm_eligibility(
            results, ["T", "V", "O", "P"], strict=False,
        )
        self.assertFalse(eligibility["all_selected_arms_eligible"])
        self.assertTrue(eligibility["arms"]["T"]["eligible"])
        self.assertTrue(eligibility["arms"]["V"]["eligible"])
        self.assertFalse(eligibility["arms"]["O"]["eligible"])
        self.assertFalse(eligibility["arms"]["P"]["eligible"])
        self.assertIn("GO_overlay_readout", eligibility["arms"]["P"]["blocking_claims"])

    def test_gp_fixture_grows_ten_to_sixteen_and_flags_failure_row(self) -> None:
        fixture = gates.build_gp_fixture("dev", 0, base_seed=4)
        self.assertEqual(len(fixture["initial_pages"]), 10)
        total = len(fixture["initial_pages"]) + sum(
            len(r["pages"]) for r in fixture["rounds"])
        self.assertEqual(total, 16)
        self.assertEqual(fixture["truth_static"]["total_images"], total)
        self.assertEqual(fixture["truth_static"]["k_outcome"], "failed_no_result")
        failed_round = fixture["rounds"][1]
        self.assertEqual(failed_round["pages"], [])
        self.assertIn("was not rewritten", failed_round["text"])

    def test_gx_holdouts_cover_real_patch_phases(self) -> None:
        fixtures = [
            gates.build_gx_fixture("dev", index, base_seed=4)
            for index in range(gates.GX_STABILITY_FIXTURES, gates.GX_TOTAL_FIXTURES)
        ]
        coverage = gates.gx_phase_coverage(fixtures)
        self.assertTrue(coverage["pass"])
        self.assertEqual(coverage["row_mod32"], [0, 8, 16, 24])
        self.assertEqual(coverage["col_mod32"], [0, 8, 16, 24])

    def test_summary_booleans_do_not_authorize_strict_eligibility(self) -> None:
        fabricated = {claim: {"pass": True} for claim in gates.ALL_CLAIMS}
        eligibility = gates.derive_arm_eligibility(fabricated, ["T"])
        self.assertFalse(eligibility["all_selected_arms_eligible"])

    def test_confirm_gate_reservation_binds_fixed_run_and_claim_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sealed = Path(temporary) / "r4"
            run_dir = sealed / "gate_run"
            reservation_path = sealed / "gate_confirm_reservation.json"
            results_path = sealed / "claims.json"
            model = Path(temporary) / "model"
            serving_identity = {
                "checkpoint_sha256": "c" * 64,
                "verified_shards": True,
                "snapshot_sha256": "s" * 64,
            }
            with mock.patch.object(gates, "CONFIRM_RUN_DIR", run_dir), \
                    mock.patch.object(gates, "CONFIRM_RESERVATION", reservation_path), \
                    mock.patch.object(gates, "CONFIRM_RESULTS", results_path):
                reservation = gates._reserve_confirm_run(
                    frozen_sha="f" * 64, manifest_sha="m" * 64,
                    base_seed=4, model=model, run_dir=run_dir,
                    answer_tokens=runner.MAX_ANSWER_TOKENS,
                    serving_identity=serving_identity,
                )
                self.assertEqual(reservation["run_dir"], str(run_dir.resolve()))
                self.assertEqual(reservation["claims"], list(gates.ALL_CLAIMS))
                self.assertEqual(gates._confirm_reservation_errors(
                    reservation, frozen_sha="f" * 64, manifest_sha="m" * 64,
                    base_seed=4, model=model, run_dir=run_dir,
                    answer_tokens=runner.MAX_ANSWER_TOKENS,
                    serving_identity=serving_identity,
                ), [])

                started_sha = gates._start_confirm_run(
                    base_seed=4, run_dir=run_dir,
                    answer_tokens=runner.MAX_ANSWER_TOKENS,
                    serving_identity=serving_identity,
                )
                self.assertEqual(
                    started_sha, gates.sha256_file(run_dir / "STARTED.json"),
                )
                gates._authorize_confirm_claim(
                    claim="GT_text_exact", base_seed=4, run_dir=run_dir,
                    answer_tokens=runner.MAX_ANSWER_TOKENS,
                    serving_identity=serving_identity,
                )
                with self.assertRaisesRegex(RuntimeError, "already exists"):
                    gates._authorize_confirm_claim(
                        claim="GT_text_exact", base_seed=4, run_dir=run_dir,
                        answer_tokens=runner.MAX_ANSWER_TOKENS,
                        serving_identity=serving_identity,
                    )
                with self.assertRaisesRegex(RuntimeError, "fixed"):
                    gates._reserve_confirm_run(
                        frozen_sha="f" * 64, manifest_sha="m" * 64,
                        base_seed=4, model=model, run_dir=sealed / "other_run",
                        answer_tokens=runner.MAX_ANSWER_TOKENS,
                        serving_identity=serving_identity,
                    )


class SentinelTests(unittest.TestCase):
    def test_passive_variant_invariants(self) -> None:
        fixture = sentinels.build_passive_variant("dev", 0, base_seed=4)
        gold = fixture["gold"]
        by_name = {episode["name"]: episode for episode in fixture["episodes"]}
        pair = gold["history_pair"]
        self.assertEqual(by_name[pair["success"]]["final_board"],
                         by_name[pair["failure"]]["final_board"])
        self.assertTrue(by_name[pair["success"]]["completed"])
        self.assertFalse(by_name[pair["failure"]]["completed"])
        self.assertEqual(len(gold["constraints"]), 2)
        no_op = by_name["unused_action_probe"]["rows"][0]
        self.assertEqual(no_op["pre"], no_op["post"])

    def test_every_rendered_sentinel_page_clears_serving_minimum(self) -> None:
        # Regression: the pinned processor rejects images below 65,536 px^2
        # (s4_run.ask_chat).  The first calibration candidate died on an 8px
        # 24x24 overlay page (192x192 = 36,864 px^2) at its first model call.
        from PIL import Image

        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            passive = sentinels.build_passive_variant("dev", 0, base_seed=4)
            for carrier in ("raw", "overlay"):
                sentinels.render_page_carrier(passive, carrier, work / carrier)
            active = sentinels.build_active_variant("dev", 0, base_seed=4)
            sentinels.render_active_assets(active, work / "active")
            pngs = sorted(work.rglob("*.png"))
            self.assertGreater(len(pngs), 4)
            for path in pngs:
                with Image.open(path) as image:
                    area = image.width * image.height
                self.assertGreaterEqual(
                    area, sentinels.MIN_SERVING_IMAGE_AREA,
                    f"{path.name} below processor minimum ({area} px^2)",
                )

    def test_active_variant_discriminating_probe_is_verified(self) -> None:
        fixture = sentinels.build_active_variant("dev", 0, base_seed=4)
        discriminating = [
            key for key, probe in fixture["probes"].items() if probe["discriminating"]
        ]
        self.assertEqual(len(discriminating), 1)
        self.assertEqual(discriminating[0], fixture["gold"]["discriminating_probe"])
        interaction = sentinels.score_active_interaction(fixture, {
            "hypotheses": [{"probability": 0.5}, {"probability": 0.5}],
            "next_probe": {
                "start_state_id": discriminating[0],
                "action": fixture["probes"][discriminating[0]]["action_schema"],
                "predictions_by_hypothesis": {"0": "moves", "1": "stays"},
            },
        })
        self.assertTrue(interaction["valid_discriminating_interaction"])
        lucky = sentinels.score_active_interaction(fixture, {
            "hypotheses": [{"probability": 0.95}],
            "next_probe": {
                "start_state_id": discriminating[0],
                "action": fixture["probes"][discriminating[0]]["action_schema"],
                "predictions_by_hypothesis": {"0": "moves", "1": "stays"},
            },
        })
        self.assertFalse(lucky["valid_discriminating_interaction"])

    def test_active_scoring_uses_highest_probability_original_indices(self) -> None:
        # Calibration v2: an unordered but valid list is scored via the two
        # highest-probability ORIGINAL indices, never by list position.
        fixture = sentinels.build_active_variant("dev", 0, base_seed=4)
        discriminating = [
            key for key, probe in fixture["probes"].items() if probe["discriminating"]
        ][0]
        unordered = {
            "hypotheses": [{"probability": 0.2}, {"probability": 0.7}],
            "next_probe": {
                "start_state_id": discriminating,
                "action": fixture["probes"][discriminating]["action_schema"],
                "predictions_by_hypothesis": {"1": "moves", "0": "stays"},
            },
        }
        scored = sentinels.score_active_interaction(fixture, unordered)
        self.assertEqual(scored["ranked_prediction_indices"], ["1", "0"])
        self.assertTrue(scored["valid_discriminating_interaction"])
        # Three hypotheses whose top-two ORIGINAL indices {1, 2} differ from the
        # positional subset {0, 1}: the old fixed-index rule would silently read
        # the wrong pair here, not merely the same pair in a different order.
        three = {
            "hypotheses": [{"probability": 0.05}, {"probability": 0.6},
                           {"probability": 0.3}],
            "next_probe": {
                "start_state_id": discriminating,
                "action": fixture["probes"][discriminating]["action_schema"],
                "predictions_by_hypothesis": {"1": "moves", "2": "stays"},
            },
        }
        scored_three = sentinels.score_active_interaction(fixture, three)
        self.assertEqual(scored_three["ranked_prediction_indices"], ["1", "2"])
        self.assertTrue(scored_three["valid_discriminating_interaction"])
        positional_three = {
            "hypotheses": three["hypotheses"],
            "next_probe": {**three["next_probe"],
                           "predictions_by_hypothesis": {"0": "moves", "1": "stays"}},
        }
        self.assertFalse(sentinels.score_active_interaction(fixture, positional_three)[
            "valid_discriminating_interaction"])
        # A prediction map missing one of the two ranked original indices must
        # not be silently reinterpreted; the interaction fails, unrepaired.
        positional = {
            "hypotheses": unordered["hypotheses"],
            "next_probe": {**unordered["next_probe"],
                           "predictions_by_hypothesis": {"1": "moves"}},
        }
        self.assertFalse(sentinels.score_active_interaction(fixture, positional)[
            "valid_discriminating_interaction"])

    def test_aggregates_enforce_two_of_three_and_undecided_blocks(self) -> None:
        def sheet(arm: str, index: int, verdict: bool | None) -> dict:
            return {"variant_id": f"SV{index}", "carrier": arm,
                    "kind": "passive", "stage": "single",
                    "VERDICT_goal_correct_in_kind": verdict,
                    "VERDICT_constraints_by_item": [verdict, verdict]}

        worksheets = {
            arm: [sheet(arm, 0, True), sheet(arm, 1, True), sheet(arm, 2, False)]
            for arm in sentinels.PASSIVE_ARMS
        }
        summary = sentinels.aggregate_passive(worksheets)
        self.assertTrue(summary["T"]["pass"])
        worksheets["T"] = [sheet("T", 0, True), sheet("T", 1, None),
                            sheet("T", 2, True)]
        summary = sentinels.aggregate_passive(worksheets)
        self.assertFalse(summary["T"]["pass"])
        def active_record(index: int, verdict: bool, interaction: bool) -> dict:
            return {
                "variant_id": f"AV{index}", "kind": "active", "carrier": "P",
                "stages": ["pre", "post"],
                "final_worksheet": {
                    "variant_id": f"AV{index}", "kind": "active", "carrier": "P",
                    "stage": "post", "VERDICT_goal_correct_in_kind": verdict,
                    "VERDICT_constraints_by_item": [verdict, verdict],
                },
                "interaction": {"valid_discriminating_interaction": interaction},
            }

        active = sentinels.aggregate_active([
            active_record(0, True, True), active_record(1, True, True),
            active_record(2, False, False),
        ])
        self.assertTrue(active["pass"])

    def test_adequacy_rejects_same_model_reviewer(self) -> None:
        base = {
            "reviewer": "operator", "reviewer_kind": "human", "method": "read carriers",
            "source_blind": True, "pinned_same_model_used": False,
            "sentinel_outputs_seen": False,
            "per_variant": {
                f"SV{index}": {"carriers": {
                    "T": {"recovered_goal": "x", "evidence_sufficient": True},
                }} for index in range(6)
            },
            "verdict": "adequate", "attested_utc": "2026-08-18T00:00:00+00:00",
        }
        sentinels.validate_adequacy_attestation(base)
        with self.assertRaises(RuntimeError):
            sentinels.validate_adequacy_attestation(
                {**base, "reviewer_kind": "independent_model"})
        with self.assertRaises(RuntimeError):
            sentinels.validate_adequacy_attestation({**base, "reviewer_kind": "same_model"})

    def test_served_post_probe_history_requires_preserved_reasoning(self) -> None:
        initial = {"role": "user", "content": [{"type": "text", "text": "carrier"}]}
        assistant = {
            "role": "assistant",
            "content": '{"best_goal":{"plain_causal_condition":"goal"}}',
            "reasoning_content": "the exact pre-probe reasoning",
        }
        feedback = {
            "role": "user",
            "content": [{"type": "text", "text": "exact probe result"}],
        }
        expected = [initial, assistant, feedback]
        trace = {
            "messages": expected,
            "messages_sha256": hashlib.sha256(json.dumps(
                expected, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")).hexdigest(),
            "images": [],
        }
        sentinels._validate_served_inputs(trace, expected, [], "post-probe fixture")

        # Rehashing a transcript that drops reasoning_content must not turn the
        # substituted history into the exact model-visible post-probe context.
        without_reasoning = json.loads(json.dumps(expected))
        del without_reasoning[1]["reasoning_content"]
        substituted = {
            "messages": without_reasoning,
            "messages_sha256": hashlib.sha256(json.dumps(
                without_reasoning, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")).hexdigest(),
            "images": [],
        }
        with self.assertRaisesRegex(RuntimeError, "messages differ"):
            sentinels._validate_served_inputs(
                substituted, expected, [], "post-probe fixture",
            )

    def test_rehashed_message_and_image_substitutions_are_rejected(self) -> None:
        from PIL import Image

        expected_messages = [{
            "role": "user",
            "content": [{"type": "text", "text": "frozen carrier text"},
                        {"type": "image"}],
        }]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected_image = root / "expected.png"
            replacement_image = root / "replacement.png"
            Image.new("RGB", (256, 256), (12, 34, 56)).save(expected_image)
            Image.new("RGB", (256, 256), (65, 43, 21)).save(replacement_image)
            trace = {
                "messages": expected_messages,
                "messages_sha256": hashlib.sha256(json.dumps(
                    expected_messages, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")).hexdigest(),
                "images": [{
                    "path": str(expected_image.resolve()),
                    "sha256": sentinels.sha256_file(expected_image),
                    "source_size": [256, 256], "processed_size": [256, 256],
                }],
            }
            sentinels._validate_served_inputs(
                trace, expected_messages, [expected_image], "served-input fixture",
            )

            changed_messages = json.loads(json.dumps(expected_messages))
            changed_messages[0]["content"][0]["text"] = "substituted carrier text"
            rehashed_message = {
                **trace,
                "messages": changed_messages,
                "messages_sha256": hashlib.sha256(json.dumps(
                    changed_messages, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")).hexdigest(),
            }
            with self.assertRaisesRegex(RuntimeError, "messages differ"):
                sentinels._validate_served_inputs(
                    rehashed_message, expected_messages, [expected_image],
                    "served-input fixture",
                )

            rehashed_image = {
                **trace,
                "images": [{
                    "path": str(replacement_image.resolve()),
                    "sha256": sentinels.sha256_file(replacement_image),
                    "source_size": [256, 256], "processed_size": [256, 256],
                }],
            }
            with self.assertRaisesRegex(RuntimeError, r"image\[0\] differs"):
                sentinels._validate_served_inputs(
                    rehashed_image, expected_messages, [expected_image],
                    "served-input fixture",
                )

    def test_confirm_results_reject_self_declared_stale_answer_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sealed = Path(temporary) / "r4"
            run_dir = sealed / "sentinel_run"
            run_dir.mkdir(parents=True)
            frozen_path = sealed / "FROZEN.json"
            checkpoint = "c" * 64
            snapshot_sha = "s" * 64
            frozen_path.write_text(json.dumps({
                "serving_snapshot": {
                    "checkpoint_fingerprint": {"checkpoint_sha256": checkpoint},
                    "snapshot_sha256": snapshot_sha,
                    "budgets": {"answer_tokens": runner.MAX_ANSWER_TOKENS},
                },
            }))
            manifest_sha = "m" * 64
            document = {
                "format_version": sentinels.RESULT_FORMAT_VERSION,
                "protocol_version": sentinels.PROTOCOL_VERSION,
                "namespace": "confirm",
                "base_seed": 4,
                "answer_tokens": 20_000,
                "sentinel_manifest_sha256": manifest_sha,
                "run_dir": str(run_dir),
                "serving_identity": {
                    "checkpoint_sha256": checkpoint,
                    "verified_shards": True,
                    "snapshot_sha256": snapshot_sha,
                },
                "frozen_manifest_sha256": sentinels.sha256_file(frozen_path),
            }
            manifest = {"namespace": "confirm", "base_seed": 4}
            with mock.patch.object(sentinels, "SEALED_R4", sealed), \
                    mock.patch.object(sentinels, "CONFIRM_RUN_DIR", run_dir):
                with self.assertRaisesRegex(
                    RuntimeError, "answer-token budget differs from frozen production",
                ):
                    sentinels.validate_sentinel_results_document(
                        document, manifest=manifest,
                        manifest_sha256=manifest_sha,
                    )


class ContinuationTests(unittest.TestCase):
    def _sealed(self, stack: tempfile.TemporaryDirectory) -> Path:
        root = Path(stack.name) / "r4"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_continuation_is_one_shot_and_rejects_stale_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sealed = Path(temporary) / "r4"
            sealed.mkdir()
            frozen_path = sealed / "FROZEN.json"
            continue_path = sealed / "CONTINUE.json"
            frozen_payload = {
                "format_version": grade.R4_FORMAT_VERSION,
                "protocol_version": grade.PROTOCOL_R4,
                "preregistration": {"arms": ["T"], "seeds": [2]},
                "kaggle_eval_budget": 0,
            }
            frozen_path.write_text(json.dumps(frozen_payload))
            frozen_sha = grade.sha256_file(frozen_path)
            claims_path = Path(temporary) / "claims.json"
            claims_path.write_text(json.dumps({"kind": "claims"}))
            sentinel_path = Path(temporary) / "sentinels.json"
            sentinel_path.write_text(json.dumps({"kind": "sentinels"}))
            adequacy_path = Path(temporary) / "adequacy.json"
            adequacy_path.write_text(json.dumps({"kind": "adequacy"}))
            frozen_payload["packet_adequacy_attestation"] = {
                "path": str(adequacy_path.resolve()),
                "sha256": grade.sha256_file(adequacy_path),
            }
            derived = {
                "gate_validation": {"G0_protocol_serving": {"pass": True, "errors": []}},
                "eligibility": {"all_selected_arms_eligible": False},
                "sentinel_summary": {"passive": {}, "active": {"pass": True}},
                "adequacy_verdict": "adequate", "verdict": "STOP",
            }
            with mock.patch.object(grade, "FROZEN_R4", frozen_path), \
                    mock.patch.object(grade, "CONTINUE_R4", continue_path), \
                    mock.patch.object(grade, "verify_freeze_r4",
                                      return_value=frozen_payload), \
                    mock.patch.object(grade, "_derive_continuation_r4",
                                      return_value=derived):
                code = grade.continue_r4(claims_path, sentinel_path, adequacy_path)
                self.assertEqual(code, 3)  # control/claim failure -> STOP
                written = json.loads(continue_path.read_text())
                self.assertEqual(written["verdict"], "STOP")
                with self.assertRaisesRegex(RuntimeError, "one-shot"):
                    grade.continue_r4(claims_path, sentinel_path, adequacy_path)
                with self.assertRaisesRegex(RuntimeError, "has ended"):
                    grade.verify_continue_r4(frozen_sha)

    def test_runner_requires_continue_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sealed = Path(temporary) / "r4"
            sealed.mkdir()
            continue_path = sealed / "CONTINUE.json"
            payload = {
                "format_version": grade.R4_FORMAT_VERSION,
                "frozen_manifest_sha256": "a" * 64,
                "gate_claims": {"path": str(sealed / "x"), "sha256": "b" * 64},
                "sentinel_results": {"path": str(sealed / "y"), "sha256": "c" * 64},
                "adequacy_attestation": {"path": str(sealed / "z"), "sha256": "d" * 64},
                "verdict": "CONTINUE",
            }
            continue_path.write_text(json.dumps(payload))
            frozen_path = sealed / "FROZEN.json"
            frozen_path.write_text("{}")
            actual_sha = grade.sha256_file(frozen_path)
            with mock.patch.object(grade, "FROZEN_R4", frozen_path), \
                    mock.patch.object(grade, "CONTINUE_R4", continue_path), \
                    mock.patch.object(grade, "verify_freeze_r4", return_value={}):
                with self.assertRaisesRegex(RuntimeError, "stale r4 freeze digest"):
                    grade.verify_continue_r4("e" * 64)
                payload["frozen_manifest_sha256"] = actual_sha
                continue_path.write_text(json.dumps(payload))
                with self.assertRaisesRegex(RuntimeError, "binding drift"):
                    grade.verify_continue_r4(actual_sha)


class R4AuthorityReceiptTests(unittest.TestCase):
    @staticmethod
    def _answer() -> dict:
        return {
            "hypotheses": [{
                "probability": 0.8,
                "necessary_conditions": ["red exists"],
                "sufficient_condition": "red touches blue",
                "evidence_for": ["S00001"],
                "evidence_against": [],
                "predicted_counterexample": "separated colours",
            }],
            "best_goal": {
                "plain_causal_condition": "make red touch blue",
                "structured_factors": ["red", "blue", "touching"],
            },
            "next_probe": {
                "start_state_id": "S00001",
                "action": {"id": 1, "click": None},
                "predictions_by_hypothesis": {"0": "contact changes"},
            },
            "retrieval_requests": [],
            "goal_directed_plan": [{"action": {"id": 1, "click": None}}],
        }

    @staticmethod
    def _frozen() -> dict:
        identity_hash = "a" * 64
        return {
            "frozen_utc": "2026-08-18T00:00:00+00:00",
            "serving_snapshot": {
                "snapshot_sha256": "b" * 64,
                "checkpoint_fingerprint": {"checkpoint_sha256": identity_hash},
                "production_sampler": dict(grade.EXPECTED_PRODUCTION_SAMPLER),
                "reasoning_effort": "xhigh",
                "preserve_thinking": True,
                "native_context_tokens": grade.NATIVE_CONTEXT_TOKENS,
                "budgets": dict(grade.DEFAULT_BUDGETS),
            },
            "preregistration": {
                "budgets": dict(grade.DEFAULT_BUDGETS),
                "expected_cells": [{
                    "role": "qwen", "game_blind": "G000001",
                    "arm": "P", "seed": 2,
                }],
            },
        }

    def test_runner_and_grader_parity_on_unordered_hypotheses(self) -> None:
        # P1 regression: the v1 false failure existed because the runner and
        # the production grader disagreed about ordering.  Both must accept a
        # structurally valid unordered answer, both must reject the same fatal
        # defects, and both must see the identical ranking diagnostic.
        answer = self._answer()
        template = answer["hypotheses"][0]
        answer["hypotheses"] = [
            {**template, "probability": 0.15},
            {**template, "probability": 0.5},
            {**template, "probability": 0.2},
        ]
        self.assertEqual(runner.validate_answer(answer), [])
        self.assertIsNone(grade.answer_validation_error(answer))
        self.assertIs(runner.ranking_compliance(answer["hypotheses"]), False)
        self.assertEqual(
            runner.ranked_hypothesis_indices(answer["hypotheses"]), [1, 2, 0])
        ordered = self._answer()
        self.assertEqual(runner.validate_answer(ordered), [])
        self.assertIsNone(grade.answer_validation_error(ordered))
        self.assertIs(runner.ranking_compliance(ordered["hypotheses"]), True)
        fatal = self._answer()
        fatal["hypotheses"][0]["probability"] = 1.5
        self.assertTrue(runner.validate_answer(fatal))
        self.assertIsNotNone(grade.answer_validation_error(fatal))
        oversum = self._answer()
        oversum["hypotheses"] = [
            {**template, "probability": 0.8}, {**template, "probability": 0.7},
        ]
        self.assertTrue(runner.validate_answer(oversum))
        self.assertIsNotNone(grade.answer_validation_error(oversum))

    def test_round_trace_is_reparsed_and_hash_checked(self) -> None:
        frozen = self._frozen()
        answer = self._answer()
        raw = "kept reasoning</think>" + json.dumps(answer, sort_keys=True)
        think = "kept reasoning"
        answer_text = json.dumps(answer, sort_keys=True)
        messages = [{"role": "user", "content": "exact prompt"}]
        stats = {
            "prompt_tokens": 10, "generation_tokens": 5,
            "total_tokens": 15, "finish_reason": "stop",
        }
        identity = {
            "checkpoint_sha256": "a" * 64,
            "verified_shards": True,
            "snapshot_sha256": "b" * 64,
        }
        tag = "G000001_P_s2_r0"
        record = {
            "tag": tag, "trace_tag": tag, "round_index": 0,
            "round_kind": "initial", "seed": grade.generation_seed(2, "G000001", 0),
            "sampler": dict(grade.EXPECTED_PRODUCTION_SAMPLER),
            "reasoning_effort": "xhigh", "preserve_thinking": True,
            "serving_identity": identity,
            "max_tokens": grade.DEFAULT_BUDGETS["answer_tokens"],
            "native_context_tokens": grade.NATIVE_CONTEXT_TOKENS,
            "messages": messages, "messages_sha256": grade.sha256_json(messages),
            "prompt_sha256": grade.hashlib.sha256(b"serialized prompt").hexdigest(),
            "images": [], "image_grid_thw": [], "visual_tokens": 0,
            "expanded_prompt_tokens": 10, "derived_text_tokens": 10,
            "input_text_token_cap": grade.RUN_INITIAL_PROMPT_TEXT_TOKENS,
            "generator_prompt_tokens": 10, "input_tokens": 10, "output_tokens": 5,
            "finish_reason": "stop", "prompt_tokens_match": True,
            "token_accounting_match": True, "think_chars": len(think),
            "completion_contains_close": True, "payload_present": True,
            "schema_errors": [],
            "ranking_compliance": runner.ranking_compliance(
                answer.get("hypotheses")),
            "completeness": "complete",
            "raw_response": raw, "parsed_payload": answer, "think": think,
            "answer": answer_text,
            "assistant_history": {
                "role": "assistant", "content": answer_text,
                "reasoning_content": think,
            },
            "stats": stats, "wall_seconds": 1.0,
        }
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            trace_path = run_dir / f"{tag}.trace.json"
            trace_path.write_text(json.dumps({
                **record, "prompt": "serialized prompt", "raw": raw,
            }))
            trace_path.chmod(0o444)
            record["trace_path"] = str(trace_path.resolve())
            record["trace_sha256"] = grade.sha256_file(trace_path)
            self.assertEqual(
                grade._validate_immutable_round_trace(
                    record, frozen, expected_tag=tag, expected_round=0,
                    expected_kind="initial", run_dir=run_dir,
                ),
                answer,
            )
            tampered = json.loads(json.dumps(record))
            tampered["parsed_payload"]["best_goal"]["plain_causal_condition"] = "shopped"
            with self.assertRaisesRegex(RuntimeError, "differs from its immutable trace"):
                grade._validate_immutable_round_trace(
                    tampered, frozen, expected_tag=tag, expected_round=0,
                    expected_kind="initial", run_dir=run_dir,
                )

    def test_fixed_serving_reservation_and_receipt_are_authority(self) -> None:
        frozen = self._frozen()
        identity = {
            "checkpoint_sha256": "a" * 64,
            "verified_shards": True,
            "snapshot_sha256": "b" * 64,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frozen_path = root / "FROZEN.json"
            frozen_path.write_text("{}")
            run_dir = root / "run"
            run_dir.mkdir()
            output_path = run_dir / "answers.json"
            reservation = runner.reserve_serving_attempt(
                role="qwen", attempt=0,
                frozen_manifest_sha256=grade.sha256_file(frozen_path),
                run_dir=run_dir, output_path=output_path,
                serving_identity=identity, prior_attempt=None,
                root=root / "serving_attempts",
            )
            cell = {
                "role": "qwen", "game_blind": "G000001", "arm": "P",
                "seed": 2, "attempt": 0, "outcome": "answered", "rounds": [],
            }
            receipt = runner.finalize_serving_receipt(
                reservation, status="done", trace_receipts=[],
                cell_outcomes=[{
                    "role": "qwen", "game_blind": "G000001", "arm": "P",
                    "seed": 2, "attempt": 0, "outcome": "answered",
                }],
            )
            document = {
                "role": "qwen", "attempt": 0, "status": "done",
                "run_dir": str(run_dir.resolve()),
                "output_path": str(output_path.resolve()),
                "serving_identity": identity, "prior_attempt": None,
                "cells": [cell], **reservation, **receipt,
            }
            output_path.write_text(json.dumps(document))
            with mock.patch.object(grade, "FROZEN_R4", frozen_path), \
                    mock.patch.object(grade, "SERVING_ATTEMPT_ROOT",
                                      root / "serving_attempts"):
                grade._validate_serving_attempt_authority(
                    document, frozen, role="qwen", attempt=0,
                    document_path=output_path,
                )
                substituted = json.loads(json.dumps(document))
                substituted["cells"][0]["outcome"] = "missing_malformed_or_refusal"
                with self.assertRaisesRegex(RuntimeError, "cell inventory/outcomes"):
                    grade._validate_serving_attempt_authority(
                        substituted, frozen, role="qwen", attempt=0,
                        document_path=output_path,
                    )

    def test_pre_freeze_adequacy_receipt_binds_exact_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sealed = Path(temporary) / "r4"
            manifest = sealed / "fixtures/sentinels/sentinel_manifest.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}")
            base = {
                "reviewer": "operator-1", "reviewer_kind": "human",
                "method": "read every intended carrier", "per_variant": {},
                "verdict": "adequate", "attested_utc": "2026-08-17T10:00:00+00:00",
                "source_blind": True, "pinned_same_model_used": False,
                "sentinel_outputs_seen": False,
                "sentinel_manifest_sha256": grade.sha256_file(manifest),
            }
            receipt = {
                "format_version": grade.ADEQUACY_RECEIPT_FORMAT_VERSION,
                "artifact_type": grade.ADEQUACY_RECEIPT_TYPE,
                "created_utc": "2026-08-17T10:01:00+00:00",
                "reviewer": "operator-1", "reviewer_kind": "operator",
                "sentinel_manifest_sha256": grade.sha256_file(manifest),
                "attestation_payload_sha256": grade.sha256_json(base),
                "source_blind": True, "sentinel_outputs_seen": False,
            }
            attestation = {**base, "review_receipt": receipt}
            path = Path(temporary) / "adequacy.json"
            path.write_text(json.dumps(attestation))
            with mock.patch.object(grade, "SEALED_R4", sealed), \
                    mock.patch.object(sentinels, "verify_manifest", return_value={}), \
                    mock.patch.object(sentinels, "validate_adequacy_attestation",
                                      side_effect=lambda value, **_kwargs: value):
                binding = grade._validate_packet_adequacy_attestation(
                    path, before_utc="2026-08-18T00:00:00+00:00",
                )
                self.assertEqual(binding["sha256"], grade.sha256_file(path))
                changed = json.loads(json.dumps(attestation))
                changed["method"] = "different review"
                path.write_text(json.dumps(changed))
                with self.assertRaisesRegex(RuntimeError, "payload digest"):
                    grade._validate_packet_adequacy_attestation(
                        path, before_utc="2026-08-18T00:00:00+00:00",
                    )


class GuardTests(unittest.TestCase):
    def test_packet_source_reads_are_refused(self) -> None:
        for forbidden in (
            Path("data/environment_files/ls20/9607627b/ls20.py"),
            Path("data/human_replays/official/x.zip"),
            Path("logs/s4_sealed/gold/ls20.json"),
        ):
            with self.assertRaises(RuntimeError):
                spk.read_allowlisted(spk.ROOT / forbidden)

    def test_submission_capability_fails_closed(self) -> None:
        with mock.patch.dict("os.environ", {"TRUE_SUBMISSION": "true"}):
            with self.assertRaises(ledgers.SubmissionCapabilityRefused):
                ledgers.enforce_offline_scientific_run("test", [])
        with mock.patch.dict("os.environ", {"KAGGLE_RUN_AS_SUBMISSION": "1"}):
            with self.assertRaises(ledgers.SubmissionCapabilityRefused):
                ledgers.enforce_offline_scientific_run("test", [])
        with self.assertRaises(ledgers.SubmissionCapabilityRefused):
            ledgers.enforce_offline_scientific_run("test", ["--submit"])
        ledgers.enforce_offline_scientific_run("test", ["--arms", "T"])

    def test_ledger_chain_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(ledgers, "LEDGER_ROOT", Path(temporary)):
                ledgers.append("local_generations", {
                    "module": "test", "tag": "t0", "purpose": "unit",
                    "model": "m", "seed": 1, "max_tokens": 10,
                })
                ledgers.append("local_generations", {
                    "module": "test", "tag": "t1", "purpose": "unit",
                    "model": "m", "seed": 2, "max_tokens": 10,
                })
                path = ledgers.ledger_path("local_generations")
                lines = path.read_text().splitlines()
                first = json.loads(lines[0])
                first["seed"] = 99
                path.write_text("\n".join([json.dumps(first), lines[1]]) + "\n")
                with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                    ledgers.read_ledger("local_generations")

    def test_show_frame_region_is_never_rewritten(self) -> None:
        probe_session = object.__new__(
            __import__("s4_probes").ProbeSession
        )
        probe_session.by_tid = {
            "S1": {"post": [[0] * 64 for _ in range(64)], "click": None,
                   "action": "A1"},
        }
        saved = {}

        def fake_save(image, stem, kind, **extra):
            saved["size"] = image.size
            return {"path": "x", "kind": kind, "sha256": "0" * 64, "bytes": 1,
                    "width": image.size[0], "height": image.size[1],
                    "visual_tokens": (image.size[0] // 16) * (image.size[1] // 16) // 4,
                    **extra}

        probe_session._save_audited = fake_save
        with self.assertRaisesRegex(ValueError, "larger than 32x32"):
            probe_session._show_frame("S1", "0", "0", "40", "40")
        with self.assertRaisesRegex(ValueError, "exactly"):
            probe_session._show_frame("S1", "0", "0", "5")
        result = probe_session._show_frame("S1", "10", "10", "20", "20")
        self.assertTrue(result["ok"])
        self.assertLessEqual(saved["size"][0] * saved["size"][1] // 1024, 1_200)
        full = probe_session._show_frame("S1")
        self.assertIn("rulers", full["text"])

    def test_r4_freeze_refuses_implicit_defaults(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "explicit --preregistration"):
            grade.freeze_r4(None, Path("/unused/model"))

    def test_freeze_r4_cli_rejects_every_unrelated_workflow_option(self) -> None:
        base_argv = [
            "s4_grade.py", "--freeze-r4",
            "--preregistration", "preregistration.json",
            "--adequacy", "adequacy.json",
            "--qwen-calibration", "calibration.json",
            "--qwen-semantic", "semantic.json",
            "--qwen-semantic-key", "semantic.key",
        ]
        extras = (
            ["--freeze"],
            ["--answers", "answers.json"],
            ["--adjudications", "adjudication.json"],
            ["--adjudication-key", "adjudication.key"],
            ["--adjudication-receipt", "receipt.json"],
            ["--seal-adjudication", "worksheet.json"],
            ["--adjudicator-signing-key", "signing.key"],
            ["--commit-adjudications", "signed-a.json", "signed-b.json"],
            ["--prepare-ceiling"],
            ["--prepare-familiarity", "draft.json"],
            ["--familiarity-commitment", "commitment.json"],
            ["--derive-stage-b-selection", "registry.json"],
            ["--commit-stage-b-inventory"],
            ["--source-inventory-commitment", "inventory.json"],
            ["--out", "output.json"],
            ["--execute-plans"],
            ["--tally"],
            ["--continue-r4"],
            ["--gate-claims", "claims.json"],
            ["--sentinel-results", "sentinels.json"],
        )
        for extra in extras:
            with self.subTest(option=extra[0]), \
                    mock.patch.object(sys, "argv", base_argv + extra), \
                    mock.patch.object(
                        ledgers, "enforce_offline_scientific_run",
                    ), self.assertRaisesRegex(RuntimeError, extra[0]):
                grade.main()

    def test_freeze_r4_cli_allows_its_inputs_and_default_model(self) -> None:
        argv = [
            "s4_grade.py", "--freeze-r4",
            "--preregistration", "preregistration.json",
            "--adequacy", "adequacy.json",
            "--qwen-calibration", "calibration.json",
            "--qwen-semantic", "semantic.json",
            "--qwen-semantic-key", "semantic.key",
        ]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
                ledgers, "enforce_offline_scientific_run"), mock.patch.object(
                    grade, "freeze_r4", return_value=0) as freeze:
            self.assertEqual(grade.main(), 0)
        self.assertEqual(
            freeze.call_args.args[1],
            Path.home() / "models/mlx/Qwen3.8-27B-8bit",
        )

    def test_freeze_calibration_binding_requires_same_mechanical_semantic_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_id = "c" * 64
            mechanical_path = root / "RESULT.json"
            semantic_path = root / "SEMANTIC_RESULT.json"
            semantic_key = root / "semantic.key"
            mechanical_receipt = root / "mechanical.receipt.json"
            semantic_attempts = root / "semantic_attempts"
            semantic_attempts.mkdir()
            semantic_receipt = semantic_attempts / f"{candidate_id}.receipt.json"
            mechanical_path.write_text(json.dumps({
                "completed_utc": "2026-08-18T01:00:00+00:00",
            }))
            semantic_path.write_text(json.dumps({
                "created_utc": "2026-08-18T04:00:00+00:00",
                "human_judgments": {
                    "adjudicated_utc": "2026-08-18T03:00:00+00:00",
                },
            }))
            mechanical_receipt.write_text(json.dumps({
                "finished_utc": "2026-08-18T02:00:00+00:00",
            }))
            semantic_receipt.write_text(json.dumps({
                "finished_utc": "2026-08-18T05:00:00+00:00",
            }))
            semantic_key.write_bytes(b"k" * 32)
            semantic_key.chmod(0o444)
            mechanical = {
                "candidate_id": candidate_id,
                "git_commit": "g" * 40,
                "checkpoint_sha256": "m" * 64,
                "result_sha256": grade.sha256_file(mechanical_path),
                "receipt_path": str(mechanical_receipt),
                "status": "PASS",
            }
            semantic = {
                "candidate_id": candidate_id,
                "calibration_result_sha256": grade.sha256_file(mechanical_path),
                "blinding_key_commitment_sha256": hashlib.sha256(
                    semantic_key.read_bytes()
                ).hexdigest(),
                "status": "PASS",
            }
            with mock.patch.object(
                    qcal, "validate_calibration_result", return_value=mechanical), \
                    mock.patch.object(
                        qcal, "validate_semantic_adjudication",
                        return_value=semantic,
                    ), mock.patch.object(
                        qcal, "SEMANTIC_ATTEMPT_ROOT", semantic_attempts,
                    ):
                binding = grade._validate_pre_freeze_qwen_calibration(
                    mechanical_path, semantic_path, semantic_key,
                    Path("/unused/model"),
                    before_utc="2026-08-18T06:00:00+00:00",
                    require_live_environment=False,
                )
                self.assertEqual(binding["status"], "PASS")
                self.assertEqual(binding["candidate_id"], candidate_id)
                mismatched = {**semantic, "candidate_id": "d" * 64}
                with mock.patch.object(
                        qcal, "validate_semantic_adjudication",
                        return_value=mismatched,
                    ), self.assertRaisesRegex(RuntimeError, "same PASS candidate"):
                    grade._validate_pre_freeze_qwen_calibration(
                        mechanical_path, semantic_path, semantic_key,
                        Path("/unused/model"),
                        require_live_environment=False,
                    )

    def test_sealed_gold_is_exact_unique_64x64(self) -> None:
        for game in ("ls20", "ft09", "m0r0", "sp80"):
            gold = grade.load_object(grade.GOLD / f"{game}.json", "gold")
            grade.validate_gold(game, gold)
            hashes = [grade.sha256_json(row["board"])
                      for row in gold["counterfactuals"]]
            self.assertEqual(len(hashes), len(set(hashes)))


if __name__ == "__main__":
    unittest.main()
