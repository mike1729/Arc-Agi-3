"""Regression coverage for the slice-4 revision-4 contracts.

Covers the refinement plan's explicit list: final-PNG truth decoding, strict
integer coordinates, permutation movement, arm-scoped eligibility,
stale/mismatched continuation rejection, one-shot continuation creation,
control failure ending the version, packet-source read refusal, real token
accounting of the delta channel, 10-to-16-image interaction growth, and
no-silent-repair behavior.  No model, no GPU, no sealed artifacts touched.
"""

from __future__ import annotations

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
import s4_render as sr  # noqa: E402
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

    def test_rle_fallback_is_lossless_and_compact_text_drops_cells(self) -> None:
        pre = [[0] * 16 for _ in range(16)]
        post = [[5] * 16 for _ in range(16)]
        record = sdl.sequence_record(["Fa", "Fb"], [pre, post], binding={"tid": "T2"})
        pair = record["pairs"][0]
        self.assertIn("rle", pair)
        self.assertNotIn("sparse", pair)
        self.assertEqual(sdl.apply_pair_delta(pre, pair), post)
        full = sdl.render_text_block(record)
        compact = sdl.render_text_block(record, include_cells=False)
        self.assertIn("rle ", full)
        self.assertNotIn("rle ", compact)
        self.assertIn("changed=256", compact)


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
        eligibility = gates.derive_arm_eligibility(results, ["T", "V", "O", "P"])
        self.assertTrue(eligibility["all_selected_arms_eligible"])
        results["GO_overlay_readout"] = {"pass": False}
        eligibility = gates.derive_arm_eligibility(results, ["T", "V", "O", "P"])
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
        self.assertLessEqual(total, 16)
        self.assertEqual(fixture["truth_static"]["total_images"], total)
        self.assertEqual(fixture["truth_static"]["k_outcome"], "failed_no_result")
        failed_round = fixture["rounds"][1]
        self.assertEqual(failed_round["pages"], [])
        self.assertIn("was not rewritten", failed_round["text"])


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

    def test_active_variant_discriminating_probe_is_verified(self) -> None:
        fixture = sentinels.build_active_variant("dev", 0, base_seed=4)
        discriminating = [
            key for key, probe in fixture["probes"].items() if probe["discriminating"]
        ]
        self.assertEqual(len(discriminating), 1)
        self.assertEqual(discriminating[0], fixture["gold"]["discriminating_probe"])
        interaction = sentinels.score_active_interaction(fixture, {
            "hypotheses": [{"probability": 0.5}, {"probability": 0.5}],
            "probe_request": {"prefix": discriminating[0], "action": "A1"},
        })
        self.assertTrue(interaction["valid_discriminating_interaction"])
        lucky = sentinels.score_active_interaction(fixture, {
            "hypotheses": [{"probability": 0.95}],
            "probe_request": {"prefix": discriminating[0], "action": "A1"},
        })
        self.assertFalse(lucky["valid_discriminating_interaction"])

    def test_aggregates_enforce_two_of_three_and_undecided_blocks(self) -> None:
        def sheet(verdict: bool | None) -> dict:
            return {"VERDICT_goal_correct_in_kind": verdict,
                    "VERDICT_constraints_by_item": [verdict, verdict]}

        summary = sentinels.aggregate_passive({"T": [sheet(True), sheet(True), sheet(False)]})
        self.assertTrue(summary["T"]["pass"])
        summary = sentinels.aggregate_passive({"T": [sheet(True), sheet(None), sheet(True)]})
        self.assertFalse(summary["T"]["pass"])
        active = sentinels.aggregate_active([
            {"final_goal_pass": True,
             "interaction": {"valid_discriminating_interaction": True}},
            {"final_goal_pass": True,
             "interaction": {"valid_discriminating_interaction": True}},
            {"final_goal_pass": False,
             "interaction": {"valid_discriminating_interaction": False}},
        ])
        self.assertTrue(active["pass"])

    def test_adequacy_rejects_same_model_reviewer(self) -> None:
        base = {
            "reviewer": "operator", "reviewer_kind": "human", "method": "read carriers",
            "per_variant": {"SVabc": {"recovered_goal": "x", "evidence_sufficient": True}},
            "verdict": "adequate", "attested_utc": "2026-08-18T00:00:00+00:00",
        }
        sentinels.validate_adequacy_attestation(base)
        with self.assertRaises(RuntimeError):
            sentinels.validate_adequacy_attestation(
                {**base, "reviewer_kind": "independent_model"})
        with self.assertRaises(RuntimeError):
            sentinels.validate_adequacy_attestation({**base, "reviewer_kind": "same_model"})


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
            claims_path.write_text(json.dumps({
                "namespace": "confirm",
                "frozen_manifest_sha256": "0" * 64,   # stale binding
                "results": {},
            }))
            sentinel_path = Path(temporary) / "sentinels.json"
            sentinel_path.write_text(json.dumps({
                "namespace": "confirm", "frozen_manifest_sha256": frozen_sha,
                "passive_worksheets": {}, "active_records": [],
            }))
            adequacy_path = Path(temporary) / "adequacy.json"
            adequacy_path.write_text(json.dumps({
                "reviewer": "op", "reviewer_kind": "human", "method": "m",
                "per_variant": {"SV1": {"recovered_goal": "g",
                                        "evidence_sufficient": True}},
                "verdict": "adequate", "attested_utc": "2026-08-18T00:00:00+00:00",
            }))
            with mock.patch.object(grade, "FROZEN_R4", frozen_path), \
                    mock.patch.object(grade, "CONTINUE_R4", continue_path), \
                    mock.patch.object(grade, "verify_freeze_r4",
                                      return_value=frozen_payload):
                with self.assertRaisesRegex(RuntimeError, "not bound to this exact"):
                    grade.continue_r4(claims_path, sentinel_path, adequacy_path)
                claims_path.write_text(json.dumps({
                    "namespace": "confirm",
                    "frozen_manifest_sha256": frozen_sha,
                    "results": {
                        "G0_protocol_serving": {"kind": "mechanical", "pass": True},
                        "GT_text_exact": {"pass": False},
                    },
                }))
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
            with mock.patch.object(grade, "CONTINUE_R4", continue_path):
                with self.assertRaisesRegex(RuntimeError, "different freeze"):
                    grade.verify_continue_r4("e" * 64)
                with self.assertRaisesRegex(RuntimeError, "binding drift"):
                    grade.verify_continue_r4("a" * 64)


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


if __name__ == "__main__":
    unittest.main()
