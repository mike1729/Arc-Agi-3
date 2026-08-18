#!/usr/bin/env python3
"""No-model regression tests for the sealed Slice-4 grader."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_grade as grade


ADJUDICATION_KEY = b"slice-4-test-adjudication-key-32-bytes!!"
ADJUDICATOR_PRIVATE_KEYS = {
    "judge_a": b"\x11" * 32,
    "judge_b": b"\x22" * 32,
}


def valid_answer(*, goal: str = "make red touch blue", plan_action: int = 1) -> dict:
    return {
        "hypotheses": [{
            "probability": 0.8,
            "necessary_conditions": ["red exists"],
            "sufficient_condition": "red touches blue",
            "evidence_for": ["page 1", "S00001"],
            "evidence_against": [],
            "predicted_counterexample": "separated colours",
        }],
        "best_goal": {
            "plain_causal_condition": goal,
            "structured_factors": ["red", "blue", "touching"],
        },
        "next_probe": {
            "start_state_id": "S00001",
            "action": {"id": 1, "click": None},
            "predictions_by_hypothesis": {"0": "contact changes"},
        },
        "retrieval_requests": [],
        "goal_directed_plan": [{"action": {"id": plan_action, "click": None}}],
    }


def valid_ceiling_spec() -> dict:
    return {
        "kind": "blinded_human_cohort",
        "cohort": {
            "cohort_id": "fixture-unfamiliar-cohort-v1",
            "selection_rule": "first eligible respondent in preregistered roster order",
            "respondent_id": "blind-respondent-001",
            "roster_selection_commitment_sha256": "b" * 64,
        },
        "respondent_count": 1,
        "aggregation": {
            "rule": "single_respondent",
            "tie_rule": "not_applicable",
        },
        "familiarity_collection": {
            "timing": "before_evidence",
            "scope": "per_respondent",
            "eligible_declarations": list(grade.CEILING_ELIGIBLE_FAMILIARITY),
        },
    }


def valid_model_ceiling_spec() -> dict:
    return {
        "kind": "model",
        "model": {
            "provider": "fixture-provider",
            "model_id": "fixture/model-v1",
            "checkpoint_sha256": "a" * 64,
            "serving_config": {"temperature": 0, "reasoning_effort": "high"},
        },
        "respondent_count": 1,
        "aggregation": {"rule": "single_respondent", "tie_rule": "not_applicable"},
        "familiarity_collection": {
            "timing": "not_applicable",
            "scope": "model_training_exposure_unknown",
            "eligible_declarations": [],
        },
    }


def valid_adjudication_protocol() -> dict:
    def adjudicator(adjudicator_id: str, identity_hex: str) -> dict:
        private_key = Ed25519PrivateKey.from_private_bytes(
            ADJUDICATOR_PRIVATE_KEYS[adjudicator_id]
        )
        return {
            "adjudicator_id": adjudicator_id,
            "identity_commitment_sha256": identity_hex * 64,
            "ed25519_public_key_hex": grade._ed25519_public_key_hex(private_key),
        }

    return {
        "format_version": grade.ADJUDICATION_PROTOCOL_VERSION,
        "adjudicators": [
            adjudicator("judge_a", "c"),
            adjudicator("judge_b", "d"),
        ],
        "blinding": {
            **grade.ADJUDICATION_BLINDING,
            "key_commitment_sha256": hashlib.sha256(ADJUDICATION_KEY).hexdigest(),
        },
        "independence": {
            "judgments_per_primary": grade.ADJUDICATION_REQUIRED_JUDGES,
            "other_verdicts_hidden_until_commitment": True,
            "role_and_cell_mapping_hidden_until_commitment": True,
            "rejoin_key_custodian_is_not_an_adjudicator": True,
            "separate_distribution_channels": True,
        },
        "aggregation": dict(grade.ADJUDICATION_AGGREGATION),
        "verdict_commitment": {
            "algorithm": "sha256-canonical-json-v2",
            "signature_algorithm": "ed25519",
            "before_unblinding": True,
            "all_verdict_leaves_required": True,
            "commitment_receipt_required": True,
        },
    }


def valid_prior_exposure_registry() -> dict:
    return {
        "format_version": 1,
        "registry_kind": "prior_goal_inference_exposure",
        "completeness_attestation": grade.STAGE_B_EXPOSURE_ATTESTATION,
        "entries": [
            {"game": game, "reasons": ["documented pre-Stage-B goal-inference work"]}
            for game in sorted(grade.KNOWN_PRIOR_EXPOSED_GAMES)
        ],
    }


def fixture_stage_b_selection(
    games: list[str], lengths: dict[str, int | None],
) -> dict:
    registry = valid_prior_exposure_registry()
    source_commitment = {
        "artifact_type": "fixture_stage_b_source_inventory_commitment",
        "eligible_inventory": [
            {"game": game, "autonomous_completion_length": lengths[game]}
            for game in games
        ],
    }
    return {
        "format_version": 1,
        "artifact_type": "fixture_stage_b_selection",
        "prior_exposure_registry": registry,
        "source_inventory_commitment": source_commitment,
        "eligible_inventory": source_commitment["eligible_inventory"],
        "selected_games": list(games),
    }


def add_fixture_stage_b_selection(
    config: dict, games: list[str], lengths: dict[str, int | None],
) -> dict:
    manifest = fixture_stage_b_selection(games, lengths)
    config["stage_b_source_inventory_commitment"] = manifest[
        "source_inventory_commitment"
    ]
    config["stage_b_prior_exposure_registry"] = valid_prior_exposure_registry()
    config["stage_b_selection_manifest"] = manifest
    config.setdefault("adjudication_protocol", valid_adjudication_protocol())
    return manifest


class AnswerAndAxisTests(unittest.TestCase):
    def test_nested_answer_is_required_and_flat_leaf_is_missing_malformed(self) -> None:
        grade.validate_answer(valid_answer())
        leaf = {"id": 2, "click": None}
        classification = grade.classify_attempt({"outcome": "answered", "final_answer": leaf})
        self.assertEqual(classification["status"], "missing")
        self.assertEqual(classification["missing_kind"], "malformed")
        self.assertIn("hypotheses", classification["schema_error"])

    def test_truncation_is_missing_even_if_json_is_valid(self) -> None:
        classification = grade.classify_attempt({
            "outcome": "answered",
            "final_answer": valid_answer(),
            "rounds": [{"finish_reason": "length"}],
        })
        self.assertEqual(classification["missing_kind"], "budget_indeterminate")

    def test_invalid_probe_values_remain_gradeable_and_are_left_to_executor(self) -> None:
        answer = valid_answer()
        answer["next_probe"]["action"] = {"id": "not-an-action", "click": [999]}
        grade.validate_answer(answer)
        self.assertEqual(
            grade.classify_attempt({"outcome": "answered", "final_answer": answer})["status"],
            "answered",
        )

    def test_axis1_uses_exact_frozen_lookup(self) -> None:
        answer = valid_answer()
        answer["hypotheses"][0]["evidence_for"] += [
            "page 999 invented", "S99999-not-real", "K12345x",
        ]
        cell = {"final_answer": answer}
        result = grade.axis1_consistency(cell, {"page 1", "S00001"})
        self.assertEqual(result["resolved"], 2)
        self.assertEqual(len(result["unresolved"]), 3)
        self.assertFalse(result["pass"])

    def test_axis1_admits_all_delivered_result_tids_but_not_omitted_assets(self) -> None:
        packet = {
            "page_refs_by_carrier": {"overlay": ["page 1"]},
            "evidence_ids": ["E000000000001"],
        }
        cell = {
            "arm": "R",
            "probe_log": [
                {
                    "kind": "retrieval", "op": "SHOW_EPISODE", "ok": True,
                    "text": "settled frames S00001..S00003 in order [OBSERVED]",
                    "episode_tids": ["S00001", "S00002", "S00003"],
                    "image_audit": [{
                        "path": "episode.png", "tids": ["S00001", "S00002", "S00003"],
                    }],
                    # Instrument-only replay metadata must never enlarge citations.
                    "prefix_steps": [{"tid": "S90000"}],
                },
                {
                    "kind": "retrieval", "op": "SHOW_COLOUR_HISTORY", "ok": True,
                    "text": "frames where colour 2 changed [DERIVED-EXACT]",
                    "history_tids": ["K00004", "K00005"],
                    "image_audit": [{
                        "path": "history.png", "tids": ["K00004", "K00005"],
                    }],
                },
                {
                    "kind": "retrieval", "op": "SHOW_ACTION_CONTRAST", "ok": True,
                    "text": "action A1 contrast [OBSERVED]",
                    "image_audit": [
                        {"path": "effect.png", "tid": "S00007"},
                        {"path": "omitted.png", "tid": "S99999"},
                    ],
                },
            ],
            "delivery_log": [
                {"result_ok": True, "delivered_images": ["episode.png"]},
                {"result_ok": True, "delivered_images": ["history.png"]},
                {
                    "result_ok": True,
                    "delivered_images": ["effect.png"],
                    "omitted_images": [{"path": "omitted.png", "visual_tokens": 64}],
                },
            ],
        }
        refs = grade.valid_evidence_refs(packet, cell)
        for tid in ("S00001", "S00002", "S00003", "K00004", "K00005", "S00007"):
            self.assertIn(tid.lower(), refs)
        self.assertNotIn("s99999", refs)
        self.assertNotIn("s90000", refs)

        ambiguous = copy.deepcopy(cell)
        ambiguous["delivery_log"].pop()
        ambiguous_refs = grade.valid_evidence_refs(packet, ambiguous)
        self.assertNotIn("s00002", ambiguous_refs)

    def test_axis3_contains_boards_and_axis4_rejects_truthy_strings(self) -> None:
        gold = {
            "paraphrase": "touch",
            "constraints": ["red"],
            "counterfactuals": [{"board": [[1, 2]], "objective_holds": True, "note": "yes"}],
            "familiarity": "unfamiliar",
        }
        worksheet3 = grade.axis3_worksheet(valid_answer(), gold)
        self.assertEqual(worksheet3["sealed_counterfactuals"][0]["board"], [[1, 2]])
        worksheet2 = grade.axis2_worksheet(valid_answer(), gold, terminal=False)
        worksheet2["VERDICT_correct_in_kind"] = True
        worksheet2["VERDICT_constraints_by_item"] = [True]
        worksheet2["VERDICT_constraints_present"] = True
        worksheet2["VERDICT_per_hypothesis_true"] = ["false"]
        with self.assertRaisesRegex(RuntimeError, "must be true, false, or null"):
            grade.axis4_calibration(worksheet2)


class PlanTests(unittest.TestCase):
    def test_first_action_levels_completed_is_detected(self) -> None:
        class FakeEngine:
            def __init__(self, game: str):
                self.game = game

            def new(self):
                return SimpleNamespace(levels_completed=0)

            def perform(self, handle, action):
                del handle
                level = 0 if action[0] == 0 else 1
                return SimpleNamespace(levels_completed=level, state="NOT_FINISHED")

        fake_module = SimpleNamespace(Engine=FakeEngine)
        with mock.patch.dict(sys.modules, {"s4_recapture": fake_module}):
            result = grade.axis5_plan(
                {"final_answer": valid_answer()}, "g1", budget=2, execute=True
            )
        self.assertTrue(result["level_advanced"])
        self.assertEqual(result["steps_executed"], 1)

    def test_malformed_click_is_a_plan_failure_not_a_crash(self) -> None:
        answer = valid_answer()
        answer["goal_directed_plan"][0]["action"]["click"] = [1]
        result = grade.axis5_plan({"final_answer": answer}, "g1", budget=2, execute=True)
        self.assertEqual(result["status"], "invalid_plan")
        self.assertFalse(result["level_advanced"])


class MatrixTests(unittest.TestCase):
    def test_absent_cell_and_single_rerun_are_explicit(self) -> None:
        frozen = {"preregistration": {"missing_reruns": 1}}
        absent = grade.resolve_attempts({"qwen|G000001|P|seed=4": {}}, frozen)
        self.assertEqual(absent["qwen|G000001|P|seed=4"]["status"], "incomplete_run")

        missing = {"cell": {}, "classification": {"status": "missing", "missing_kind": "refusal"}}
        first = grade.resolve_attempts({"key": {0: missing}}, frozen)
        self.assertEqual(first["key"]["status"], "rerun_required")
        second = grade.resolve_attempts({"key": {0: missing, 1: missing}}, frozen)
        self.assertEqual(second["key"]["status"], "missing_after_remedy")

    def test_duplicate_blind_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not one-to-one"):
            grade.validate_blind_map({"g1": "G000001", "g2": "G000001"})

    def test_stage_a_matrix_runs_qwen_all_arms_and_ceiling_primary_only(self) -> None:
        games = ["g1", "g2"]
        mapping = {"g1": "G000001", "g2": "G000002"}
        raw = {
            "stage": "A",
            "games": games,
            "arms": ["T", "V", "O", "P"],
            "seeds": [2],
            "roles": ["qwen", "ceiling"],
            "primary_arm": "P",
            "ceiling_spec": valid_model_ceiling_spec(),
        }
        with mock.patch.object(grade, "autonomous_completion_length", return_value=None):
            config = grade.normalize_preregistration(raw, mapping)
        qwen_cells = [cell for cell in config["expected_cells"] if cell["role"] == "qwen"]
        ceiling_cells = [
            cell for cell in config["expected_cells"] if cell["role"] == "ceiling"
        ]
        self.assertEqual(len(qwen_cells), len(games) * 4)
        self.assertEqual({cell["arm"] for cell in qwen_cells}, {"T", "V", "O", "P"})
        self.assertEqual(len(ceiling_cells), len(games))
        self.assertEqual({cell["arm"] for cell in ceiling_cells}, {"P"})
        self.assertEqual(config["seeds"], [2])

        extra_ceiling_arm = copy.deepcopy(raw)
        extra_ceiling_arm["expected_cells"] = copy.deepcopy(config["expected_cells"])
        extra_ceiling_arm["expected_cells"].append({
            "role": "ceiling", "game_blind": "G000001", "arm": "T", "seed": 2,
        })
        with mock.patch.object(grade, "autonomous_completion_length", return_value=None), \
                self.assertRaisesRegex(RuntimeError, "Qwen on every declared arm"):
            grade.normalize_preregistration(extra_ceiling_arm, mapping)

        missing_qwen_arm = copy.deepcopy(raw)
        missing_qwen_arm["expected_cells"] = [
            copy.deepcopy(cell) for cell in config["expected_cells"]
            if not (cell["role"] == "qwen" and cell["game_blind"] == "G000001"
                    and cell["arm"] == "O")
        ]
        with mock.patch.object(grade, "autonomous_completion_length", return_value=None), \
                self.assertRaisesRegex(RuntimeError, "Qwen on every declared arm"):
            grade.normalize_preregistration(missing_qwen_arm, mapping)

        missing_spec = copy.deepcopy(raw)
        missing_spec.pop("ceiling_spec")
        with self.assertRaisesRegex(RuntimeError, "ceiling role requires"):
            grade.normalize_preregistration(missing_spec, mapping)

        orphan_spec = copy.deepcopy(raw)
        orphan_spec["roles"] = ["qwen"]
        with self.assertRaisesRegex(RuntimeError, "without a preregistered ceiling role"):
            grade.normalize_preregistration(orphan_spec, mapping)

        ceiling_without_source = copy.deepcopy(raw)
        ceiling_without_source["roles"] = ["ceiling"]
        with self.assertRaisesRegex(RuntimeError, "requires the corresponding Qwen role"):
            grade.normalize_preregistration(ceiling_without_source, mapping)

    def test_selected_stage_a_pilot_preregistration_is_operational(self) -> None:
        preregistration_path = (
            grade.ROOT / "notes/qwen-3.8-slice4-pilot-preregistration.json"
        )
        raw = json.loads(preregistration_path.read_text())
        mapping = json.loads((grade.ROOT / "logs/s4_sealed/blind_map.json").read_text())
        certificate = json.loads(
            (grade.ROOT / "logs/e2_probe_vlm_38_8bit.json").read_text()
        )
        with mock.patch.object(grade, "autonomous_completion_length", return_value=None):
            normalized = grade.normalize_preregistration(raw, mapping)
        self.assertEqual(normalized["stage"], "A")
        self.assertEqual(normalized["arms"], ["T", "V", "O", "P"])
        self.assertEqual(normalized["seeds"], [2])
        self.assertEqual(len(normalized["expected_cells"]), 20)
        self.assertEqual(
            sum(cell["role"] == "qwen" for cell in normalized["expected_cells"]), 16,
        )
        self.assertEqual(
            sum(cell["role"] == "ceiling" for cell in normalized["expected_cells"]), 4,
        )
        self.assertTrue(all(
            cell["arm"] == "P"
            for cell in normalized["expected_cells"] if cell["role"] == "ceiling"
        ))
        self.assertEqual(
            normalized["ceiling_spec"]["model"]["checkpoint_sha256"],
            certificate["checkpoint_identity"]["checkpoint_sha256"],
        )
        self.assertEqual(
            normalized["ceiling_spec"]["model"]["serving_config"]["classification"],
            "descriptive_only_no_closure",
        )

    def test_stage_b_requires_unused_three_by_three_stratification(self) -> None:
        games = [f"u{index}" for index in range(6)]
        mapping = {game: f"G{index:06x}" for index, game in enumerate(games, 1)}
        raw = {
            "stage": "B", "games": games, "arms": ["P"],
            "seeds": grade.stage_b_generation_seeds(),
            "roles": ["qwen", "ceiling"], "primary_arm": "P",
            "ceiling_spec": valid_ceiling_spec(),
            "adjudication_protocol": valid_adjudication_protocol(),
            "autonomous_completion_lengths": {
                **{game: index + 1 for index, game in enumerate(games[:3])},
                **{game: None for game in games[3:]},
            },
        }
        derived = raw["autonomous_completion_lengths"]
        selection = add_fixture_stage_b_selection(raw, games, derived)
        with mock.patch.object(
            grade, "autonomous_completion_length",
            side_effect=lambda game, blind_id: derived[game],
        ), mock.patch.object(
            grade, "derive_stage_b_selection_manifest", return_value=selection,
        ):
            config = grade.normalize_preregistration(raw, mapping)
        self.assertEqual(config["game_pass_min_seeds"], 2)
        bad = copy.deepcopy(raw)
        bad["autonomous_completion_lengths"][games[3]] = 9
        with mock.patch.object(
            grade, "autonomous_completion_length",
            side_effect=lambda game, blind_id: derived[game],
        ), mock.patch.object(
            grade, "derive_stage_b_selection_manifest", return_value=selection,
        ), self.assertRaisesRegex(RuntimeError, "drift from packet-bound observations"):
            grade.normalize_preregistration(bad, mapping)

        four_exposed = bad["autonomous_completion_lengths"]
        four_selection = add_fixture_stage_b_selection(bad, games, four_exposed)
        with mock.patch.object(
            grade, "autonomous_completion_length",
            side_effect=lambda game, blind_id: four_exposed[game],
        ), mock.patch.object(
            grade, "derive_stage_b_selection_manifest", return_value=four_selection,
        ), self.assertRaisesRegex(RuntimeError, "stratified 3 completion-exposed"):
            grade.normalize_preregistration(bad, mapping)

        pilot_games = ["ls20", *games[1:]]
        pilot_mapping = {game: f"G{index:06x}" for index, game in enumerate(pilot_games, 1)}
        pilot = copy.deepcopy(raw)
        pilot["games"] = pilot_games
        pilot["autonomous_completion_lengths"] = {
            **{"ls20": 1, games[1]: 2, games[2]: 3},
            **{game: None for game in games[3:]},
        }
        add_fixture_stage_b_selection(
            pilot, pilot_games, pilot["autonomous_completion_lengths"]
        )
        with self.assertRaisesRegex(RuntimeError, "pilot overlap"):
            grade.normalize_preregistration(pilot, pilot_mapping)

    def test_stage_b_decision_rule_cannot_be_relaxed(self) -> None:
        games = [f"u{index}" for index in range(6)]
        mapping = {game: f"G{index:06x}" for index, game in enumerate(games, 1)}
        derived = {
            **{game: index + 1 for index, game in enumerate(games[:3])},
            **{game: None for game in games[3:]},
        }
        base = {
            "stage": "B",
            "games": games,
            "arms": ["P"],
            "seeds": grade.stage_b_generation_seeds(),
            "roles": ["qwen", "ceiling"],
            "primary_arm": "P",
            "game_pass_min_seeds": 2,
            "closure": {
                "qwen_max_pass_games": 0,
                "ceiling_min_pass_games": 4,
                "ceiling_min_pass_games_per_stratum": 2,
            },
            "ceiling_spec": valid_ceiling_spec(),
            "adjudication_protocol": valid_adjudication_protocol(),
            "autonomous_completion_lengths": derived,
        }
        selection = add_fixture_stage_b_selection(base, games, derived)
        mutations = {
            "primary arm": (
                lambda value: value.update({"arms": ["T", "P"], "primary_arm": "T"}),
                "primary_arm must be exactly 'P'",
            ),
            "one-of-three game pass": (
                lambda value: value.update({"game_pass_min_seeds": 1}),
                "game pass threshold must be exactly 2 of 3 seeds",
            ),
            "operator-chosen seeds": (
                lambda value: value.update({"seeds": [1, 2, 3]}),
                "ordered protocol-derived generation seeds",
            ),
            "qwen threshold": (
                lambda value: value["closure"].update({"qwen_max_pass_games": 6}),
                "closure thresholds must be exactly 0 Qwen / 4 ceiling games",
            ),
            "ceiling threshold": (
                lambda value: value["closure"].update({"ceiling_min_pass_games": 0}),
                "closure thresholds must be exactly 0 Qwen / 4 ceiling games",
            ),
        }
        for label, (mutate, expected_error) in mutations.items():
            with self.subTest(label=label):
                invalid = copy.deepcopy(base)
                mutate(invalid)
                with mock.patch.object(
                    grade, "autonomous_completion_length",
                    side_effect=lambda game, blind_id: derived[game],
                ), mock.patch.object(
                    grade, "derive_stage_b_selection_manifest", return_value=selection,
                ), self.assertRaisesRegex(RuntimeError, expected_error):
                    grade.normalize_preregistration(invalid, mapping)

    def test_stage_b_requires_a_complete_immutable_ceiling_spec(self) -> None:
        games = [f"u{index}" for index in range(6)]
        mapping = {game: f"G{index:06x}" for index, game in enumerate(games, 1)}
        derived = {
            **{game: index + 1 for index, game in enumerate(games[:3])},
            **{game: None for game in games[3:]},
        }
        base = {
            "stage": "B", "games": games, "arms": ["P"],
            "seeds": grade.stage_b_generation_seeds(),
            "roles": ["qwen", "ceiling"], "primary_arm": "P",
            "ceiling_spec": valid_ceiling_spec(),
            "adjudication_protocol": valid_adjudication_protocol(),
            "autonomous_completion_lengths": derived,
        }
        mutations = {
            "missing": (
                lambda value: value.pop("ceiling_spec"),
                "requires an immutable ceiling_spec",
            ),
            "missing cohort selection": (
                lambda value: value["ceiling_spec"]["cohort"].pop("selection_rule"),
                "human ceiling_spec must pin",
            ),
            "missing roster commitment": (
                lambda value: value["ceiling_spec"]["cohort"].pop(
                    "roster_selection_commitment_sha256"
                ),
                "human ceiling_spec must pin",
            ),
            "digest mismatch": (
                lambda value: value.update({"ceiling_spec_sha256": "0" * 64}),
                "ceiling_spec_sha256 disagrees",
            ),
            "multiple respondents": (
                lambda value: value["ceiling_spec"].update({"respondent_count": 2}),
                "respondent_count must be exactly 1",
            ),
            "unverifiable aggregation": (
                lambda value: value["ceiling_spec"]["aggregation"].update(
                    {"rule": "majority_vote"}
                ),
                "aggregation must be single_respondent/not_applicable",
            ),
        }
        for label, (mutate, expected_error) in mutations.items():
            with self.subTest(label=label):
                invalid = copy.deepcopy(base)
                mutate(invalid)
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    grade.normalize_preregistration(invalid, mapping)

        model_spec = {
            "kind": "model",
            "model": {
                "provider": "fixture-provider",
                "model_id": "fixture/model-v1",
                "checkpoint_sha256": "a" * 64,
                "serving_config": {"temperature": 0, "reasoning_effort": "high"},
            },
            "respondent_count": 1,
            "aggregation": {"rule": "single_respondent", "tie_rule": "not_applicable"},
            "familiarity_collection": {
                "timing": "not_applicable",
                "scope": "model_training_exposure_unknown",
                "eligible_declarations": [],
            },
        }
        self.assertIs(grade.validate_ceiling_spec(model_spec), model_spec)

    def test_store_only_completions_drive_packet_bound_stratification(self) -> None:
        games = [f"u{index}" for index in range(6)]
        mapping = {game: f"G{index:06x}" for index, game in enumerate(games, 1)}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            packets = root / "packets"
            observations = root / "observations"
            store = root / "store"
            observations.mkdir()
            store.mkdir()
            expected_lengths: dict[str, int | None] = {}
            for game_index, game in enumerate(games):
                kaggle_text = json.dumps({
                    "type": "initial", "action": "RESET", "seq": 0,
                    "level_completed": False, "game_over": False,
                    "state": "NOT_FINISHED",
                }, separators=(",", ":")) + "\n"
                (observations / f"{game}.observations.jsonl").write_text(kaggle_text)

                rows = []
                step = 1
                # A longer incomplete episode must not leak into the later length.
                for episode_step in range(4):
                    rows.append({
                        "step": step, "episode_step": episode_step,
                        "action": [1, None, None], "pre": "x", "post": "x",
                        "levels": 0, "state": "NOT_FINISHED",
                    })
                    step += 1
                completion_length = game_index + 1 if game_index < 3 else None
                second_length = completion_length or 2
                for episode_step in range(second_length):
                    rows.append({
                        "step": step, "episode_step": episode_step,
                        "action": [2, None, None], "pre": "x", "post": "x",
                        "levels": (
                            1 if completion_length is not None
                            and episode_step == second_length - 1 else 0
                        ),
                        "state": "NOT_FINISHED",
                    })
                    step += 1
                performs_text = "".join(
                    json.dumps(row, separators=(",", ":")) + "\n" for row in rows
                )
                transitions_text = ""
                (store / f"{game}.performs.jsonl").write_text(performs_text)
                (store / f"{game}.transitions.jsonl").write_text(transitions_text)
                identities = {
                    "normalized_export": {
                        "output_sha256": hashlib.sha256(kaggle_text.encode()).hexdigest(),
                    },
                    "store": {
                        "performs": {
                            "sha256": hashlib.sha256(performs_text.encode()).hexdigest(),
                            "bytes": len(performs_text.encode()),
                        },
                        "transitions": {
                            "sha256": hashlib.sha256(transitions_text.encode()).hexdigest(),
                            "bytes": 0,
                        },
                    },
                }
                packet_dir = packets / mapping[game]
                packet_dir.mkdir(parents=True)
                (packet_dir / "packet_manifest.json").write_text(json.dumps({
                    "format_version": grade.PACKET_FORMAT_VERSION,
                    "blind_id": mapping[game],
                    "inputs": identities,
                    "input_bundle_sha256": grade.sha256_json(identities),
                }))
                expected_lengths[game] = completion_length

            preregistration = {
                "stage": "B", "games": games, "arms": ["P"],
                "seeds": grade.stage_b_generation_seeds(),
                "roles": ["qwen", "ceiling"], "primary_arm": "P",
                "ceiling_spec": valid_ceiling_spec(),
                "adjudication_protocol": valid_adjudication_protocol(),
                "autonomous_completion_lengths": expected_lengths,
            }
            selection = add_fixture_stage_b_selection(
                preregistration, games, expected_lengths
            )
            with mock.patch.object(grade, "PACKET_ROOT", packets), \
                    mock.patch.object(grade, "KAGGLE_OBSERVATIONS", observations), \
                    mock.patch.object(grade, "STORE_ROOT", store), \
                    mock.patch.object(
                        grade, "derive_stage_b_selection_manifest", return_value=selection
                    ):
                config = grade.normalize_preregistration(preregistration, mapping)
                self.assertEqual(config["autonomous_completion_lengths"], expected_lengths)
                self.assertEqual(
                    config["plan_action_budgets"],
                    {game: (2 * (index + 1) if index < 3 else 150)
                     for index, game in enumerate(games)},
                )
                drift = copy.deepcopy(preregistration)
                drift["autonomous_completion_lengths"][games[0]] = 99
                with self.assertRaisesRegex(RuntimeError, "drift from packet-bound"):
                    grade.normalize_preregistration(drift, mapping)


class BlindedAdjudicationTests(unittest.TestCase):
    @staticmethod
    def _seal(document: dict) -> dict:
        adjudicator_id = document["adjudicator"]["adjudicator_id"]
        with tempfile.TemporaryDirectory() as temporary:
            key_path = Path(temporary) / "judge.key"
            key_path.write_bytes(ADJUDICATOR_PRIVATE_KEYS[adjudicator_id])
            return grade.seal_blinded_adjudication(document, key_path)

    @staticmethod
    def _cell(role: str, index: int) -> dict:
        answer = valid_answer(goal=f"fixture goal {index}")
        gold = {
            "paraphrase": f"sealed goal {index}",
            "constraints": ["red", "blue", "touching"],
            "counterfactuals": [
                {"board": [[1, 2], [0, 0]], "objective_holds": True, "note": "a"},
                {"board": [[1, 0], [0, 2]], "objective_holds": False, "note": "b"},
            ],
        }
        blind = f"G{index + 1:06x}"
        return {
            "cell_key": grade.logical_key(role, blind, "P", index + 1),
            "role": role,
            "game_blind": blind,
            "arm": "P",
            "seed": index + 1,
            "game": f"secret_game_{index}",
            "observation": {"status": "answered"},
            "source_attempt": 0,
            "answer_sha256": grade.sha256_json(answer),
            "axis1_consistency": {"pass": True},
            "axis2_worksheet": grade.axis2_worksheet(answer, gold, terminal=True),
            "pre_probe_axis2_worksheet": grade.axis2_worksheet(
                answer, gold, terminal=True
            ),
            "axis3_worksheet": grade.axis3_worksheet(answer, gold),
            "axis5_plan": {"status": "not_executed"},
        }

    @staticmethod
    def _frozen() -> dict:
        protocol = valid_adjudication_protocol()
        return {
            "preregistration_sha256": "e" * 64,
            "preregistration": {
                "stage": "B",
                "expected_matrix_sha256": "f" * 64,
                "adjudication_protocol": protocol,
                "adjudication_protocol_sha256": grade.sha256_json(protocol),
            },
        }

    @staticmethod
    def _fill(document: dict, verdict: bool) -> dict:
        filled = copy.deepcopy(document)
        for item in filled["items"]:
            for field in ("axis2_worksheet",):
                worksheet = item[field]
                if worksheet is None:
                    continue
                worksheet["VERDICT_correct_in_kind"] = verdict
                worksheet["VERDICT_constraints_by_item"] = [
                    verdict for _ in worksheet["sealed_constraints"]
                ]
                worksheet["VERDICT_constraints_present"] = verdict
                worksheet["VERDICT_per_hypothesis_true"] = [
                    verdict for _ in worksheet["model_hypotheses"]
                ]
                worksheet["VERDICT_terminal_evidence_present"] = False
            axis3 = item["axis3_worksheet"]
            axis3["VERDICT_counterfactuals"] = [
                verdict for _ in axis3["sealed_counterfactuals"]
            ]
            axis3["VERDICT_survives_counterfactuals"] = verdict
        return BlindedAdjudicationTests._seal(filled)

    def _bundle(self, cells: list[dict]) -> tuple[dict, dict]:
        frozen = self._frozen()
        bindings = [
            {"path": f"/private/answer-{index}.json", "sha256": f"{index + 1:x}" * 64}
            for index in range(2)
        ]
        with tempfile.TemporaryDirectory() as temporary:
            frozen_path = Path(temporary) / "FROZEN.json"
            frozen_path.write_text("{}")
            with mock.patch.object(grade, "FROZEN", frozen_path):
                bundle = grade._build_blinded_adjudication_bundle(
                    cells, bindings, frozen, ADJUDICATION_KEY
                )
        return bundle, frozen

    def test_protocol_requires_two_distinct_committed_judges(self) -> None:
        grade.validate_adjudication_protocol(valid_adjudication_protocol())
        legacy = valid_adjudication_protocol()
        legacy["format_version"] = 1
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
            grade.validate_adjudication_protocol(legacy)
        one = valid_adjudication_protocol()
        one["adjudicators"].pop()
        with self.assertRaisesRegex(RuntimeError, "exactly 2"):
            grade.validate_adjudication_protocol(one)
        duplicate = valid_adjudication_protocol()
        duplicate["adjudicators"][1]["identity_commitment_sha256"] = "c" * 64
        with self.assertRaisesRegex(RuntimeError, "must be distinct"):
            grade.validate_adjudication_protocol(duplicate)
        duplicate_key = valid_adjudication_protocol()
        duplicate_key["adjudicators"][1]["ed25519_public_key_hex"] = (
            duplicate_key["adjudicators"][0]["ed25519_public_key_hex"]
        )
        with self.assertRaisesRegex(RuntimeError, "public keys must be distinct"):
            grade.validate_adjudication_protocol(duplicate_key)
        relaxed = valid_adjudication_protocol()
        relaxed["aggregation"]["disagreement"] = "majority"
        with self.assertRaisesRegex(RuntimeError, "disagreement indeterminate"):
            grade.validate_adjudication_protocol(relaxed)

    def test_build_is_deterministic_role_blinded_and_sealable_end_to_end(self) -> None:
        cells = [self._cell("qwen" if index % 2 == 0 else "ceiling", index)
                 for index in range(6)]
        for cell in cells:
            if cell["role"] == "ceiling":
                # This production asymmetry must never survive into judge files:
                # Qwen has a pre-probe answer; the matched human ceiling does not.
                cell["pre_probe_axis2_worksheet"] = None
        cells[0]["axis2_worksheet"]["model_best_goal"] = (
            f"Qwen discusses {cells[0]['game_blind']} / {cells[0]['game']} / "
            f"{cells[0]['cell_key']}"
        )
        bundle, frozen = self._bundle(cells)
        reversed_bundle, _ = self._bundle(list(reversed(cells)))
        self.assertEqual(bundle, reversed_bundle)
        self.assertEqual(len(bundle["worksheets"]), 2)
        id_sets = []
        raw_answer_hashes = {cell["answer_sha256"] for cell in cells}
        for worksheet in bundle["worksheets"]:
            serialized = grade.canonical_json(worksheet)
            self.assertNotIn('"qwen"', serialized)
            self.assertNotIn('"ceiling"', serialized)
            for cell in cells:
                self.assertNotIn(cell["cell_key"], serialized)
                self.assertNotIn(cell["game_blind"], serialized)
                self.assertNotIn(cell["game"], serialized)
            self.assertNotIn("answers_bundle_sha256", worksheet)
            self.assertNotIn("answer_artifact_sha256s", worksheet)
            self.assertIn("opaque_answer_bundle_commitment", worksheet)
            self.assertIn("[BLINDED_METADATA]", serialized)
            for raw_hash in raw_answer_hashes:
                self.assertNotIn(raw_hash, serialized)
            for item in worksheet["items"]:
                self.assertEqual(set(item), {
                    "item_id", "opaque_answer_commitment", "axis2_worksheet",
                    "axis3_worksheet",
                })
            id_sets.append({item["item_id"] for item in worksheet["items"]})
        self.assertTrue(id_sets[0].isdisjoint(id_sets[1]))

        sealed = [self._fill(worksheet, True) for worksheet in bundle["worksheets"]]
        validated = grade.validate_blinded_adjudications(
            bundle, sealed, frozen["preregistration"]
        )
        self.assertEqual(set(validated), {"judge_a", "judge_b"})

    def test_both_opaque_commitments_are_verified_then_rejoined_and_scored(self) -> None:
        cells = [self._cell("qwen", 0), self._cell("ceiling", 1)]
        bundle, frozen = self._bundle(cells)
        frozen["preregistration"]["plan_action_budgets"] = {
            cell["game"]: 150 for cell in cells
        }
        sealed = [self._fill(worksheet, True) for worksheet in bundle["worksheets"]]
        resolved = {
            cell["cell_key"]: {
                "status": "answered",
                "selected": {"cell": {"probe_log": []}},
            }
            for cell in cells
        }
        role_summary = {"qwen": {"games": {}}, "ceiling": {"games": {}}}
        with tempfile.TemporaryDirectory() as temporary:
            frozen_path = Path(temporary) / "FROZEN.json"
            frozen_path.write_text("{}")
            with mock.patch.object(grade, "FROZEN", frozen_path):
                receipt = grade.build_adjudication_commitment_receipt(sealed, frozen)
                with mock.patch.object(grade, "_worksheet_cells", return_value=cells), \
                        mock.patch.object(grade, "blind_to_game", return_value={
                            cell["game_blind"]: cell["game"] for cell in cells
                        }), \
                        mock.patch.object(
                            grade, "axis5_plan", return_value={"status": "not_executed"}
                        ), \
                        mock.patch.object(
                            grade, "aggregate_primary", return_value=role_summary
                        ), \
                        mock.patch.object(
                            grade, "closure_decision", return_value={"decision": "fixture"}
                        ):
                    scored = grade._score_blinded_adjudications(
                        bundle, sealed, frozen, resolved, execute_plans=False,
                        adjudication_key=ADJUDICATION_KEY,
                        adjudication_commitment_receipt=receipt,
                    )
        self.assertTrue(scored["both_signed_opaque_commitments_verified_before_rejoin"])
        self.assertEqual(scored["primary_by_role"], role_summary)
        self.assertEqual(scored["closure"]["decision"], "fixture")
        self.assertEqual(len(scored["cells"]), 2)
        self.assertTrue(all(cell["axis2"]["primary_pass"] for cell in scored["cells"]))
        self.assertTrue(all(
            cell["axis2"]["exact_verdict_agreement"] for cell in scored["cells"]
        ))

    def test_tamper_order_and_verdict_list_shape_are_rejected_before_unblinding(self) -> None:
        bundle, frozen = self._bundle([self._cell("qwen", 0), self._cell("ceiling", 1)])
        sealed = [self._fill(worksheet, True) for worksheet in bundle["worksheets"]]
        with tempfile.TemporaryDirectory() as temporary:
            frozen_path = Path(temporary) / "FROZEN.json"
            frozen_path.write_text("{}")
            with mock.patch.object(grade, "FROZEN", frozen_path):
                receipt = grade.build_adjudication_commitment_receipt(sealed, frozen)
                verdict_tamper = copy.deepcopy(sealed)
                verdict_tamper[0]["items"][0]["axis2_worksheet"][
                    "VERDICT_correct_in_kind"
                ] = False
                with mock.patch.object(
                    grade, "_opaque_item_id",
                    side_effect=AssertionError("unblinded too early"),
                ), self.assertRaisesRegex(RuntimeError, "opaque verdict commitment drift"):
                    grade._score_blinded_adjudications(
                        bundle, verdict_tamper, frozen, {}, execute_plans=False,
                        adjudication_key=ADJUDICATION_KEY,
                        adjudication_commitment_receipt=receipt,
                    )

        reordered = copy.deepcopy(bundle["worksheets"][0])
        reordered["items"].reverse()
        with self.assertRaisesRegex(RuntimeError, "immutable fields"):
            self._seal(reordered)

        shortened = copy.deepcopy(bundle["worksheets"][0])
        shortened["items"][0]["axis2_worksheet"][
            "VERDICT_constraints_by_item"
        ].pop()
        with self.assertRaisesRegex(RuntimeError, "immutable fields"):
            self._seal(shortened)

        incomplete = copy.deepcopy(sealed[0])
        incomplete["items"][0]["axis3_worksheet"][
            "VERDICT_survives_counterfactuals"
        ] = None
        with self.assertRaisesRegex(RuntimeError, "must be completed"):
            self._seal(incomplete)

        forged = copy.deepcopy(sealed)
        forged[0]["adjudicator_signature_ed25519"] = "0" * 128
        with self.assertRaisesRegex(RuntimeError, "signature verification failed"):
            grade.validate_blinded_adjudications(
                bundle, forged, frozen["preregistration"]
            )

    def test_official_scoring_rejects_bad_signature_before_loading_rejoin_key(self) -> None:
        bundle, frozen = self._bundle([
            self._cell("qwen", 0), self._cell("ceiling", 1)
        ])
        signed = [self._fill(worksheet, True) for worksheet in bundle["worksheets"]]
        signed[0]["adjudicator_signature_ed25519"] = "0" * 128
        adjudication_paths = [Path("signed-a.json"), Path("signed-b.json")]
        supplied = dict(zip(adjudication_paths, signed))
        with tempfile.TemporaryDirectory() as temporary:
            frozen_path = Path(temporary) / "FROZEN.json"
            frozen_path.write_text("{}")
            with mock.patch.object(grade, "FROZEN", frozen_path), \
                    mock.patch.object(grade, "verify_authorized_r4", return_value=frozen), \
                    mock.patch.object(
                        grade, "load_object",
                        side_effect=lambda path, _label: supplied[path],
                    ), \
                    mock.patch.object(grade, "load_adjudication_key") as load_key:
                with self.assertRaisesRegex(RuntimeError, "signature verification failed"):
                    grade.grade(
                        Path("answers.json"), False, False,
                        adjudications_paths=adjudication_paths,
                        adjudication_key_path=Path("rejoin.key"),
                        adjudication_receipt_path=Path("receipt.json"),
                    )
                load_key.assert_not_called()

    def test_cross_cancelling_judgments_are_indeterminate(self) -> None:
        cell = self._cell("qwen", 0)
        template = cell["axis2_worksheet"]
        left = copy.deepcopy(template)
        right = copy.deepcopy(template)
        for worksheet in (left, right):
            worksheet["VERDICT_per_hypothesis_true"] = [False]
            worksheet["VERDICT_terminal_evidence_present"] = False
        left["VERDICT_correct_in_kind"] = True
        left["VERDICT_constraints_by_item"] = [False, False, False]
        left["VERDICT_constraints_present"] = False
        right["VERDICT_correct_in_kind"] = False
        right["VERDICT_constraints_by_item"] = [True, True, True]
        right["VERDICT_constraints_present"] = True
        axis2, _ = grade._dual_score_axis2(
            template, [left, right], terminal=True,
            adjudicator_ids=["judge_a", "judge_b"],
        )
        self.assertEqual(axis2["status"], "adjudicator_disagreement")
        self.assertIsNone(axis2["primary_pass"])

        template3 = cell["axis3_worksheet"]
        left3, right3 = copy.deepcopy(template3), copy.deepcopy(template3)
        left3["VERDICT_counterfactuals"] = [True, False]
        right3["VERDICT_counterfactuals"] = [False, True]
        left3["VERDICT_survives_counterfactuals"] = False
        right3["VERDICT_survives_counterfactuals"] = False
        axis3 = grade._dual_score_axis3(
            template3, [left3, right3], ["judge_a", "judge_b"]
        )
        self.assertEqual(axis3["status"], "adjudicator_disagreement")
        self.assertIsNone(axis3["pass"])

        frozen = {
            "preregistration": {
                "stage": "A", "roles": ["qwen"], "games": ["g0"],
                "seeds": [1], "primary_arm": "P", "game_pass_min_seeds": 1,
            }
        }
        scored_cell = {
            "cell_key": grade.logical_key("qwen", "G000001", "P", 1),
            "observation": {"status": "answered"},
            "axis2": {"primary_pass": True},
            "closure_adjudication_ready": False,
        }
        with mock.patch.object(
            grade, "read_blind_map", return_value={"g0": "G000001"}
        ):
            aggregate = grade.aggregate_primary([scored_cell], frozen)
        self.assertIsNone(aggregate["qwen"]["games"]["g0"]["pass"])


class StageBSelectionTests(unittest.TestCase):
    def test_exposure_registry_requires_known_games_and_reasons(self) -> None:
        registry = valid_prior_exposure_registry()
        normalized = grade.normalize_prior_exposure_registry(registry)
        self.assertEqual(
            [entry["game"] for entry in normalized["entries"]],
            sorted(grade.KNOWN_PRIOR_EXPOSED_GAMES),
        )

        missing = copy.deepcopy(registry)
        missing["entries"].pop()
        with self.assertRaisesRegex(RuntimeError, "must exactly equal"):
            grade.normalize_prior_exposure_registry(missing)

        extra = copy.deepcopy(registry)
        extra["entries"].append({"game": "shop1", "reasons": ["operator-added"]})
        with self.assertRaisesRegex(RuntimeError, "unexpected=.*shop1"):
            grade.normalize_prior_exposure_registry(extra)

        unexplained = copy.deepcopy(registry)
        unexplained["entries"][0]["reasons"] = []
        with self.assertRaisesRegex(RuntimeError, "requires non-empty reasons"):
            grade.normalize_prior_exposure_registry(unexplained)

    def test_selection_is_complete_deterministic_stratified_and_packet_bound(self) -> None:
        known = sorted(grade.KNOWN_PRIOR_EXPOSED_GAMES)
        exposed_candidates = [f"ex{index}" for index in range(5)]
        unexposed_candidates = [f"nx{index}" for index in range(5)]
        games = known + exposed_candidates + unexposed_candidates
        registry = valid_prior_exposure_registry()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "e1_store_v3"
            observations = root / "kaggle_v4"
            packets = root / "packets"
            outcomes = root / "e1_outcomes_v3.json"
            explorer = root / "e1_explorer.py"
            store.mkdir()
            observations.mkdir()
            fleet_entries = []
            fleet_rows = {"action": 0, "analysis": 0, "initial": 0}
            outcome_games = {}
            for index, game in enumerate(games):
                completion_exposed = game in exposed_candidates or (
                    game in grade.KNOWN_PRIOR_EXPOSED_GAMES and index % 2 == 0
                )
                performs_text = json.dumps({
                    "step": 1,
                    "episode_step": 0,
                    "source": "test",
                    "action": [1, None, None],
                    "pre": None,
                    "post": "settled",
                    "levels": 1 if completion_exposed else 0,
                    "state": "NOT_FINISHED",
                }, separators=(",", ":")) + "\n"
                source_texts = {
                    "performs": performs_text,
                    "states": "{}",
                    "transitions": "",
                    "graph": "{}",
                }
                for kind, text in source_texts.items():
                    (store / f"{game}.{grade.STORE_INPUT_SUFFIXES[kind]}").write_text(text)

                normalized_row = {
                    "type": "initial",
                    "action": "RESET",
                    "action_num": 0,
                    "board": [[0 for _ in range(64)] for _ in range(64)],
                    "click": None,
                    "done": False,
                    "seq": 0,
                    "level": 1,
                    "level_completed": False,
                    "game_over": False,
                    "reward": 0.0,
                    "score": 0,
                    "state": "NOT_FINISHED",
                }
                normalized_text = json.dumps(
                    normalized_row, sort_keys=True, separators=(",", ":")
                ) + "\n"
                output = f"{game}.observations.jsonl"
                (observations / output).write_text(normalized_text)
                rows = {"action": 0, "analysis": 0, "initial": 1}
                for kind, count in rows.items():
                    fleet_rows[kind] += count
                fleet_entries.append({
                    "game": game,
                    "output": output,
                    "output_sha256": hashlib.sha256(normalized_text.encode()).hexdigest(),
                    "source_sha256": hashlib.sha256(f"source:{game}".encode()).hexdigest(),
                    "kept_rows": 1,
                    "completions": 0,
                    "rows": rows,
                })
                outcome_games[game] = {
                    "game": game, "performs": 1, "transitions": 0,
                }
            fleet = {
                "exporter_sha256": grade.sha256_file(
                    grade.HARNESS / "s4_export_kaggle.py"
                ),
                "fleet_rows": fleet_rows,
                "games": fleet_entries,
            }
            (observations / "manifest.json").write_text(json.dumps(fleet))
            outcomes.write_text(json.dumps({"format_version": 1, "games": outcome_games}))
            explorer.write_text("# deterministic fixture explorer\n")

            patches = (
                mock.patch.object(grade, "STORE_ROOT", store),
                mock.patch.object(grade, "KAGGLE_OBSERVATIONS", observations),
                mock.patch.object(grade, "PACKET_ROOT", packets),
                mock.patch.object(grade, "E1_OUTCOMES", outcomes),
                mock.patch.object(grade, "E1_EXPLORER", explorer),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                commitment = grade.derive_stage_b_source_inventory_commitment()
                beacon = "b" * 64
                first = grade._preview_stage_b_selection_manifest(
                    registry, commitment, beacon
                )
                second = grade._preview_stage_b_selection_manifest(
                    registry, commitment, beacon
                )
                self.assertEqual(first, second)
                self.assertEqual(
                    first["authorization_status"],
                    "non_authorizing_preview_pending_authenticated_beacon",
                )
                self.assertEqual(len(first["eligible_inventory"]), len(games))
                self.assertEqual(
                    set(first["selected_by_stratum"]["completion_exposed"]),
                    set(first["selected_games"][:3]),
                )
                self.assertEqual(
                    set(first["selected_by_stratum"]["completion_unexposed"]),
                    set(first["selected_games"][3:]),
                )
                self.assertFalse(
                    set(first["selected_games"]) & grade.KNOWN_PRIOR_EXPOSED_GAMES
                )
                reworded_registry = copy.deepcopy(registry)
                reworded_registry["entries"][0]["reasons"] = [
                    "same disclosed exposure, clarified wording"
                ]
                reworded = grade._preview_stage_b_selection_manifest(
                    reworded_registry, commitment, beacon
                )
                self.assertNotEqual(
                    first["prior_exposure_registry_sha256"],
                    reworded["prior_exposure_registry_sha256"],
                )
                self.assertEqual(first["selection_seed_sha256"], reworded["selection_seed_sha256"])
                self.assertEqual(first["ranking_by_stratum"], reworded["ranking_by_stratum"])
                self.assertEqual(first["selected_games"], reworded["selected_games"])

                inventory = {entry["game"]: entry for entry in first["eligible_inventory"]}
                mapping = {
                    game: f"G{index:06x}"
                    for index, game in enumerate(sorted(first["selected_games"]), 1)
                }
                for game, blind_id in mapping.items():
                    packet_dir = packets / blind_id
                    packet_dir.mkdir(parents=True)
                    inputs = {
                        "normalized_export": inventory[game]["normalized_export"],
                        "store": inventory[game]["store"],
                    }
                    (packet_dir / "packet_manifest.json").write_text(json.dumps({
                        "format_version": grade.PACKET_FORMAT_VERSION,
                        "blind_id": blind_id,
                        "inputs": inputs,
                        "input_bundle_sha256": grade.sha256_json(inputs),
                    }))
                self.assertEqual(
                    grade._preview_stage_b_selection_manifest(
                        registry, commitment, beacon, mapping
                    ),
                    first,
                )
                with self.assertRaisesRegex(RuntimeError, "authenticated selection beacon"):
                    grade.derive_stage_b_selection_manifest(registry, commitment, mapping)

                preregistration = {
                    "stage": "B",
                    "games": first["selected_games"],
                    "arms": ["P"],
                    "seeds": grade.stage_b_generation_seeds(),
                    "roles": ["qwen", "ceiling"],
                    "primary_arm": "P",
                    "ceiling_spec": valid_ceiling_spec(),
                    "adjudication_protocol": valid_adjudication_protocol(),
                    "stage_b_source_inventory_commitment": commitment,
                    "stage_b_prior_exposure_registry": registry,
                    "stage_b_selection_manifest": first,
                }
                # The preview deliberately cannot authorize a freeze. Mock the future
                # authenticated selector result only to exercise normalization's exact
                # selected-game/order binding independently of beacon admission.
                with mock.patch.object(
                    grade, "derive_stage_b_selection_manifest", return_value=first
                ):
                    normalized = grade.normalize_preregistration(preregistration, mapping)
                    self.assertEqual(normalized["games"], first["selected_games"])

                    reversed_games = list(reversed(first["selected_games"]))
                    wrong = copy.deepcopy(preregistration)
                    wrong["games"] = reversed_games
                    with self.assertRaisesRegex(
                        RuntimeError, "mechanically selected Stage B games"
                    ):
                        grade.normalize_preregistration(wrong, mapping)

                selected_game = first["selected_games"][0]
                packet_path = packets / mapping[selected_game] / "packet_manifest.json"
                packet = json.loads(packet_path.read_text())
                packet["inputs"]["store"]["producer_lineage"]["actor"] = (
                    "unbound_fixture_actor"
                )
                packet["input_bundle_sha256"] = grade.sha256_json(packet["inputs"])
                packet_path.write_text(json.dumps(packet))
                with self.assertRaisesRegex(RuntimeError, "packet store sources differ"):
                    grade._preview_stage_b_selection_manifest(
                        registry, commitment, beacon, mapping
                    )

                drifted_commitment = copy.deepcopy(commitment)
                drifted_commitment["eligible_inventory_sha256"] = "0" * 64
                with self.assertRaisesRegex(RuntimeError, "commitment differs"):
                    grade._preview_stage_b_selection_manifest(
                        registry, drifted_commitment, beacon
                    )

                tampered_game = games[-1]
                tampered_path = observations / f"{tampered_game}.observations.jsonl"
                tampered_row = json.loads(tampered_path.read_text())
                tampered_row["leaked_free_text"] = "goal guess"
                tampered_text = json.dumps(
                    tampered_row, sort_keys=True, separators=(",", ":")
                ) + "\n"
                tampered_path.write_text(tampered_text)
                for entry in fleet["games"]:
                    if entry["game"] == tampered_game:
                        entry["output_sha256"] = hashlib.sha256(
                            tampered_text.encode()
                        ).hexdigest()
                (observations / "manifest.json").write_text(json.dumps(fleet))
                with self.assertRaisesRegex(RuntimeError, "schema mismatch"):
                    grade._preview_stage_b_selection_manifest(
                        registry, commitment, beacon
                    )

    def test_current_repository_inventory_is_fully_exposed_and_selection_refuses(self) -> None:
        commitment = grade.derive_stage_b_source_inventory_commitment()
        inventory_games = {
            entry["game"] for entry in commitment["eligible_inventory"]
        }
        self.assertEqual(
            inventory_games,
            grade.KNOWN_PRIOR_EXPOSED_GAMES - {"s5i5"},
        )
        with self.assertRaisesRegex(RuntimeError, "fewer than 3 unused"):
            grade.derive_stage_b_selection_manifest(
                valid_prior_exposure_registry(), commitment
            )


class TemporaryProtocol:
    def __init__(self, root: Path, *, arms: list[str] | None = None):
        self.root = root
        self.sealed = root / "logs/s4_sealed"
        self.gold = self.sealed / "gold"
        self.frozen = self.sealed / "FROZEN.json"
        self.packets = root / "logs/s4_model_packet"
        self.observations = root / "logs/s4_observation_log/kaggle_v4"
        self.store = root / "logs/e1_store_v3"
        self.e1_outcomes = root / "logs/e1_outcomes_v3.json"
        self.e1_explorer = root / "agent/harness/e1_explorer.py"
        self.certificate = root / "logs/e2_probe_vlm_38_8bit.json"
        self.scripts = grade.SCRIPT_RELATIVE
        self.mapping = {"g1": "G000001"}
        self.arms = arms or ["P"]

    def create(self) -> Path:
        self.gold.mkdir(parents=True)
        self.observations.mkdir(parents=True)
        self.store.mkdir(parents=True)
        (self.sealed / "blind_map.json").write_text(json.dumps(self.mapping))
        gold = {
            "paraphrase": "red touches blue",
            "constraints": ["red", "blue", "touching"],
            "counterfactuals": [{
                "board": [[1, 2], [0, 0]], "objective_holds": True, "note": "contact",
            }],
            "familiarity": "operator has not played g1",
        }
        (self.gold / "g1.json").write_text(json.dumps(gold))
        for relative in self.scripts:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative + "\n")
        probe_path = self.root / "agent/harness/e2_probe_vlm.py"
        probe_path.write_text("agent/harness/e2_probe_vlm.py\n")

        packet = self.packets / "G000001"
        (packet / "pages").mkdir(parents=True)
        raw_pages = []
        overlay_pages = []
        evidence_items = []
        for number in range(1, grade.PACKET_TARGET_INITIAL_PAGES + 1):
            evidence_id = f"E{number:012x}"
            kind = f"fixture_{number:02d}"
            carrier_entries = {}
            for carrier, pages in (("raw", raw_pages), ("overlay", overlay_pages)):
                name = f"{carrier}_page_{number:02d}_{kind}.png"
                page_path = packet / "pages" / name
                page_path.write_bytes(f"{carrier}-{number}".encode())
                entry = {
                    "page": number,
                    "kind": kind,
                    "evidence_id": evidence_id,
                    "file": name,
                    "caption": f"fixture page {number}",
                    "width": 256,
                    "height": 256,
                    "sha256": hashlib.sha256(page_path.read_bytes()).hexdigest(),
                    "bytes": page_path.stat().st_size,
                    "image_grid_thw": [1, 16, 16],
                    "processed_size": [256, 256],
                    "visual_tokens": 64,
                    "measurement": "processor-real",
                }
                pages.append(entry)
                carrier_entries[carrier] = {
                    "page": number, "file": name, "pages": [name],
                }
            evidence_items.append({
                "evidence_id": evidence_id,
                "kind": kind,
                "provenance": "OBSERVED",
                "transition_refs": ["S00001"],
                "episode_refs": ["store:0"],
                "action_sequence": [],
                "text": f"fixture evidence {number}",
                "carriers": {
                    **carrier_entries,
                    "text": {"boards": [], "actions": [], "derived": []},
                },
            })
        ledger = "".join(
            f"PAGE {number:02d} evidence=E{number:012x} transitions=S00001\n"
            for number in range(1, grade.PACKET_TARGET_INITIAL_PAGES + 1)
        )
        (packet / "ledger.txt").write_text(ledger)
        kaggle_text = json.dumps({
            "type": "initial", "action": "RESET", "seq": 0,
            "level_completed": False, "game_over": False, "state": "NOT_FINISHED",
        }, separators=(",", ":")) + "\n"
        performs_text = json.dumps({
            "step": 1, "episode_step": 0, "source": "boot", "pre": None,
            "action": [0, None, None], "post": "fixture", "levels": 0,
            "state": "NOT_FINISHED",
        }, separators=(",", ":")) + "\n"
        source_texts = {
            "performs": performs_text,
            "states": "{}",
            "transitions": "",
            "graph": "{}",
        }
        (self.observations / "g1.observations.jsonl").write_text(kaggle_text)
        for name, text in source_texts.items():
            suffix = "jsonl" if name in {"performs", "transitions"} else "json"
            (self.store / f"g1.{name}.{suffix}").write_text(text)
        self.e1_explorer.write_text("# deterministic fixture explorer\n")
        outcomes_text = json.dumps({
            "format_version": 1,
            "games": {"g1": {"game": "g1", "performs": 1, "transitions": 0}},
        })
        self.e1_outcomes.write_text(outcomes_text)
        producer_lineage = {
            "actor": "deterministic_model_free_explorer",
            "action_input": "closed_internal_policy_no_human_or_model_actions",
            "explorer_script": {
                "path": "agent/harness/e1_explorer.py",
                "sha256": hashlib.sha256(self.e1_explorer.read_bytes()).hexdigest(),
            },
            "outcomes_manifest": {
                "path": "logs/e1_outcomes_v3.json",
                "sha256": hashlib.sha256(outcomes_text.encode()).hexdigest(),
                "bytes": len(outcomes_text.encode()),
            },
            "closed_source_tags": sorted(grade.AUTONOMOUS_EXPLORER_SOURCES),
            "observed_source_tags": ["boot"],
            "game_counts": {"performs": 1, "transitions": 0},
        }
        inputs = {
            "normalized_export": {
                "fleet_manifest_sha256": "1" * 64,
                "exporter_sha256": "2" * 64,
                "output_sha256": hashlib.sha256(kaggle_text.encode()).hexdigest(),
                "source_sha256": "4" * 64,
                "kept_rows": 1,
                "dropped_analysis_rows": 0,
                "superseded_abort": None,
            },
            "store": {
                **{
                    name: {
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                        "bytes": len(text.encode()),
                    }
                    for name, text in source_texts.items()
                },
                "producer_lineage": producer_lineage,
            },
            "recapture": {
                "manifest_sha256": "9" * 64,
                "manifest_bytes": 1,
                "episodes": [{"episode_index": 0, "sha256": "a" * 64, "bytes": 1}],
                "engine_hashes": {
                    "game_source": "b" * 64,
                    "recapture_script": "c" * 64,
                },
                "versions": {},
            },
        }
        serving_names = (
            "config.json", "tokenizer.json", "vocab.json", "merges.txt",
            "tokenizer_config.json", "chat_template.jinja", "preprocessor_config.json",
            "processor_config.json", "video_preprocessor_config.json",
            "model.safetensors.index.json",
        )
        serving_files = {
            name: {"bytes": index + 1, "sha256": f"{index:x}" * 64}
            for index, name in enumerate(serving_names)
        }
        page_count = len(raw_pages)
        visual_tokens = sum(page["visual_tokens"] for page in raw_pages)
        visual_headroom = grade.DEFAULT_BUDGETS["max_visual_tokens"] - visual_tokens
        manifest = {
            "format_version": grade.PACKET_FORMAT_VERSION,
            "blind_id": "G000001",
            "evidence_items": evidence_items,
            "carrier_pages": {"raw": raw_pages, "overlay": overlay_pages},
            "carrier_totals": {
                carrier: {
                    "page_count": page_count,
                    "visual_tokens": visual_tokens,
                    "visual_token_headroom": visual_headroom,
                    "reserved_minimal_result_visual_tokens": (
                        grade.PACKET_RESERVED_RESULT_VISUAL_TOKENS
                    ),
                    "reserved_retrieval_visual_tokens": (
                        grade.PACKET_RESERVED_RETRIEVAL_VISUAL_TOKENS
                    ),
                    "reserved_post_initial_visual_tokens": (
                        grade.PACKET_RESERVED_POST_INITIAL_VISUAL_TOKENS
                    ),
                    "initial_visual_token_ceiling": grade.PACKET_MAX_INITIAL_VISUAL_TOKENS,
                    "processor_measurements": "per-page image_grid_thw",
                }
                for carrier in ("raw", "overlay")
            } | {
                "text": {
                    "text_tokens": 100,
                    "text_chars": len(ledger),
                    "measurement": "checkpoint-tokenizer-real",
                }
            },
            "pages": raw_pages,
            "page_count": page_count,
            "visual_tokens_total": visual_tokens,
            "ledger_sha256": hashlib.sha256(ledger.encode()).hexdigest(),
            "ledger_bytes": len(ledger.encode()),
            "selection": {
                "algorithm_version": grade.PACKET_FORMAT_VERSION,
                "target_initial_pages": grade.PACKET_TARGET_INITIAL_PAGES,
                "actual_initial_pages": page_count,
                "above_target_declared": False,
                "image_cap_headroom": grade.DEFAULT_BUDGETS["max_images"] - page_count,
                "interactive_three_result_pages_fit": True,
                "three_retrieval_pages_fit": True,
                "probe_and_retrieval_six_pages_fit": True,
                "interactive_three_minimal_result_pages_fit_token_cap": True,
                "probe_and_retrieval_pages_fit_token_cap": True,
            },
            "caps": {
                "max_images": grade.DEFAULT_BUDGETS["max_images"],
                "max_visual_tokens": grade.DEFAULT_BUDGETS["max_visual_tokens"],
                "max_initial_pages": grade.PACKET_MAX_INITIAL_PAGES,
                "max_initial_visual_tokens": grade.PACKET_MAX_INITIAL_VISUAL_TOKENS,
                "max_text_tokens": grade.PACKET_MAX_TEXT_TOKENS,
                "interactive_result_headroom": grade.PACKET_INTERACTIVE_RESULT_HEADROOM,
                "retrieval_result_headroom": grade.PACKET_RETRIEVAL_RESULT_HEADROOM,
                "minimal_result_page_visual_tokens": (
                    grade.PACKET_MIN_RESULT_PAGE_VISUAL_TOKENS
                ),
                "reserved_minimal_result_visual_tokens": (
                    grade.PACKET_RESERVED_RESULT_VISUAL_TOKENS
                ),
                "max_retrieval_page_visual_tokens": (
                    grade.PACKET_MAX_RETRIEVAL_PAGE_VISUAL_TOKENS
                ),
                "reserved_retrieval_visual_tokens": (
                    grade.PACKET_RESERVED_RETRIEVAL_VISUAL_TOKENS
                ),
                "reserved_post_initial_visual_tokens": (
                    grade.PACKET_RESERVED_POST_INITIAL_VISUAL_TOKENS
                ),
            },
            "inputs": inputs,
            "input_bundle_sha256": grade.sha256_json(inputs),
            "build_identity": {
                "packet_builder_sha256": grade.sha256_file(
                    self.root / "agent/harness/s4_packet.py"
                ),
                "renderer_sha256": grade.sha256_file(
                    self.root / "agent/harness/s4_render.py"
                ),
                "packages": {
                    "numpy": "fixture",
                    "transformers": "5.14.1",
                },
                "processor": {
                    "implementation": (
                        "transformers.models.qwen2_vl.image_processing_pil_qwen2_vl."
                        "Qwen2VLImageProcessorPil"
                    ),
                    "preprocessor_config_sha256": "e" * 64,
                    "processor_config_sha256": "f" * 64,
                    "tokenizer_config_sha256": "0" * 64,
                    "tokenizer_class": "FixtureTokenizer",
                    "patch_size": 16,
                    "merge_size": 2,
                    "pixel_limits": {"shortest_edge": 65536, "longest_edge": 16777216},
                    "serving_files": serving_files,
                    "measurement_identity_sha256": grade.sha256_json(serving_files),
                },
            },
        }
        (packet / "packet_manifest.json").write_text(json.dumps(manifest))
        self.certificate.parent.mkdir(parents=True, exist_ok=True)
        runtime_versions = {
            "mlx-vlm": "0.6.8",
            "mlx": "0.32.0",
            "mlx-lm": "0.31.3",
            "transformers": "5.14.1",
        }
        compatibility = {
            "checkpoint_sha256": "a" * 64,
            "versions": runtime_versions,
            "script_sha": grade.sha256_file(probe_path),
            "renderer_sha": grade.sha256_file(
                self.root / "agent/harness/s4_render.py"
            ),
            "wiring_sampler": grade.CERTIFICATE_WIRING_SAMPLER,
            "production_sampler": grade.CERTIFICATE_PRODUCTION_SAMPLER,
            "reasoning_effort": grade.CERTIFICATE_REASONING_EFFORT,
            "experiment_config": {
                "seed_base": 4,
                "stability_replicates": 3,
                "stability_required_passes": 3,
                "max_tokens": 12_000,
                "packet_max_tokens": 16_000,
                "max_packet_images": grade.DEFAULT_BUDGETS["max_images"],
                "max_visual_tokens": grade.DEFAULT_BUDGETS["max_visual_tokens"],
            },
        }
        compatibility["sha256"] = grade.sha256_json(compatibility)
        self.certificate.write_text(json.dumps({
            "status": "done",
            "passed": True,
            "verdict": "PASS",
            "gate_statuses": {
                name: "PASS" for name in grade.EXPECTED_GATE_NAMES
            },
            "serving_compatibility": compatibility,
            "checkpoint_identity": {
                "checkpoint_sha256": "a" * 64,
                "model_files": serving_files,
                "versions": runtime_versions,
                "script_sha": compatibility["script_sha"],
                "renderer_sha": compatibility["renderer_sha"],
            },
        }))
        preregistration = self.sealed / "preregistration.json"
        preregistration.write_text(json.dumps({
            "stage": "A",
            "games": ["g1"],
            "arms": self.arms,
            "seeds": [4],
            "roles": ["qwen"],
            "primary_arm": "P",
        }))
        return preregistration

    @contextmanager
    def patched(self):
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(grade, "ROOT", self.root))
            stack.enter_context(mock.patch.object(grade, "SEALED", self.sealed))
            stack.enter_context(mock.patch.object(grade, "GOLD", self.gold))
            stack.enter_context(mock.patch.object(grade, "FROZEN", self.frozen))
            stack.enter_context(mock.patch.object(grade, "PACKET_ROOT", self.packets))
            stack.enter_context(mock.patch.object(grade, "KAGGLE_OBSERVATIONS", self.observations))
            stack.enter_context(mock.patch.object(grade, "STORE_ROOT", self.store))
            stack.enter_context(mock.patch.object(grade, "E1_OUTCOMES", self.e1_outcomes))
            stack.enter_context(mock.patch.object(grade, "E1_EXPLORER", self.e1_explorer))
            stack.enter_context(mock.patch.object(grade, "CERTIFICATE", self.certificate))
            stack.enter_context(mock.patch.object(grade, "SCRIPT_RELATIVE", self.scripts))
            stack.enter_context(mock.patch.object(
                grade, "package_version",
                side_effect=lambda name: {
                    "mlx-vlm": "0.6.8",
                    "mlx": "0.32.0",
                    "mlx-lm": "0.31.3",
                    "transformers": "5.14.1",
                }[name],
            ))
            stack.enter_context(mock.patch.object(
                grade, "current_git_state",
                return_value={"commit": "f" * 40, "dirty": False, "status": []},
            ))
            yield


class FreezeAndWorkflowTests(unittest.TestCase):
    def test_freeze_rejects_stale_serving_gate_script(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            protocol = TemporaryProtocol(Path(temporary))
            preregistration = protocol.create()
            (protocol.root / "agent/harness/e2_probe_vlm.py").write_text(
                "gate implementation changed after certification\n"
            )
            with protocol.patched(), self.assertRaisesRegex(
                RuntimeError, "gate script is stale"
            ):
                grade.freeze(preregistration)

    def test_freeze_rejects_incomplete_gate_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            protocol = TemporaryProtocol(Path(temporary))
            preregistration = protocol.create()
            certificate = json.loads(protocol.certificate.read_text())
            del certificate["gate_statuses"]["gate5_sampler_stability"]
            protocol.certificate.write_text(json.dumps(certificate))
            with protocol.patched(), self.assertRaisesRegex(
                RuntimeError, "incomplete or unknown gate inventory"
            ):
                grade.freeze(preregistration)

    def test_freeze_rejects_packet_certificate_measurement_identity_drift(self) -> None:
        mutations = {
            "serving file": (
                lambda manifest: (
                    manifest["build_identity"]["processor"]["serving_files"][
                        "config.json"
                    ].update({"sha256": "a" * 64}),
                    manifest["build_identity"]["processor"].update({
                        "measurement_identity_sha256": grade.sha256_json(
                            manifest["build_identity"]["processor"]["serving_files"]
                        )
                    }),
                ),
                "measurement identity drift for config.json",
            ),
            "transformers runtime": (
                lambda manifest: manifest["build_identity"]["packages"].update(
                    {"transformers": "different"}
                ),
                "tokenizer runtime differs from certified/live transformers",
            ),
        }
        for label, (mutate, expected_error) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                protocol = TemporaryProtocol(Path(temporary))
                preregistration = protocol.create()
                manifest_path = protocol.packets / "G000001/packet_manifest.json"
                manifest = json.loads(manifest_path.read_text())
                mutate(manifest)
                manifest_path.write_text(json.dumps(manifest))
                with protocol.patched(), self.assertRaisesRegex(RuntimeError, expected_error):
                    grade.freeze(preregistration)

    def test_freeze_rejects_legacy_or_non_closure_grade_packets(self) -> None:
        mutations = {
            "legacy": (
                lambda manifest: manifest.update({"format_version": 2}),
                "non-v3/unbound packet",
            ),
            "carrier mismatch": (
                lambda manifest: manifest["carrier_pages"]["overlay"][0].update(
                    {"evidence_id": "Effffffffffff"}
                ),
                "evidence ids are not carrier-matched",
            ),
            "truncated page hash": (
                lambda manifest: (
                    manifest["carrier_pages"]["raw"][0].update(
                        {"sha256": manifest["carrier_pages"]["raw"][0]["sha256"][:16]}
                    ),
                    manifest["pages"][0].update(
                        {"sha256": manifest["pages"][0]["sha256"][:16]}
                    ),
                ),
                "full lowercase SHA-256",
            ),
            "text over cap": (
                lambda manifest: manifest["carrier_totals"]["text"].update(
                    {"text_tokens": grade.PACKET_MAX_TEXT_TOKENS + 1}
                ),
                "<=12k-token total",
            ),
        }
        for label, (mutate, expected_error) in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                protocol = TemporaryProtocol(Path(temporary))
                preregistration = protocol.create()
                manifest_path = protocol.packets / "G000001/packet_manifest.json"
                manifest = json.loads(manifest_path.read_text())
                mutate(manifest)
                manifest_path.write_text(json.dumps(manifest))
                with protocol.patched(), self.assertRaisesRegex(RuntimeError, expected_error):
                    grade.freeze(preregistration)

    def test_freeze_verifies_exact_map_gold_packet_scripts_and_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            protocol = TemporaryProtocol(Path(temporary))
            preregistration = protocol.create()
            with protocol.patched():
                self.assertEqual(grade.freeze(preregistration), 0)
                frozen = grade.verify_legacy_freeze()
                self.assertEqual(frozen["format_version"], 2)
                self.assertEqual(set(frozen["scripts"]), set(protocol.scripts))
                self.assertIn(
                    "raw_page_01_fixture_01.png",
                    frozen["packets"]["G000001"]["pages"],
                )
                with self.assertRaisesRegex(RuntimeError, "already exists"):
                    grade.freeze(preregistration)
                (protocol.gold / "extra.json").write_text(
                    (protocol.gold / "g1.json").read_text()
                )
                with self.assertRaisesRegex(RuntimeError, "gold set mismatch"):
                    grade.verify_legacy_freeze()

    def test_packet_or_blind_map_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            protocol = TemporaryProtocol(Path(temporary))
            preregistration = protocol.create()
            with protocol.patched():
                grade.freeze(preregistration)
                (protocol.packets / "G000001/pages/raw_page_01_fixture_01.png").write_bytes(
                    b"changed"
                )
                with self.assertRaisesRegex(RuntimeError, "digest disagrees with bytes"):
                    grade.verify_legacy_freeze()

    def test_blind_map_and_script_drift_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            protocol = TemporaryProtocol(Path(temporary))
            preregistration = protocol.create()
            with protocol.patched():
                grade.freeze(preregistration)
                (protocol.sealed / "blind_map.json").write_text(
                    json.dumps({"g1": "G000002"})
                )
                with self.assertRaisesRegex(RuntimeError, "blind_map.json changed"):
                    grade.verify_legacy_freeze()

        with tempfile.TemporaryDirectory() as temporary:
            protocol = TemporaryProtocol(Path(temporary))
            preregistration = protocol.create()
            with protocol.patched():
                grade.freeze(preregistration)
                (protocol.root / protocol.scripts[0]).write_text("drift")
                with self.assertRaisesRegex(RuntimeError, "PROTOCOL DRIFT"):
                    grade.verify_legacy_freeze()

    def test_filled_worksheet_scores_primary_and_terminal_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            protocol = TemporaryProtocol(Path(temporary))
            preregistration = protocol.create()
            with protocol.patched():
                grade.freeze(preregistration)
                frozen = grade.verify_legacy_freeze()
                answers = protocol.root / "answers.json"
                answers.write_text(json.dumps({
                    "frozen_manifest_sha256": grade.sha256_file(protocol.frozen),
                    "git": {"commit": "f" * 40, "dirty": False, "status": []},
                    "role": "qwen",
                    "seeds": [4],
                    "arms": ["P"],
                    "budgets": dict(grade.DEFAULT_BUDGETS),
                    "certificate": {"checkpoint_sha256": "a" * 64,
                                    "certificate_sha256": frozen["certificate"]["sha256"],
                                    "certificate_verified_shards": True},
                    "cells": [{
                        "game_blind": "G000001", "arm": "P", "outcome": "answered",
                        "packet_pages": grade.PACKET_TARGET_INITIAL_PAGES,
                        "packet_manifest_sha256": frozen["packets"]["G000001"]["manifest_sha256"],
                        "packet_ledger_sha256": frozen["packets"]["G000001"]["ledger_sha256"],
                        "rounds": [{
                            "tag": f"G000001_P_s4_r{round_number}",
                            "seed": grade.generation_seed(
                                4, "G000001", round_number
                            ),
                            "max_tokens": grade.DEFAULT_BUDGETS["answer_tokens"],
                            "completeness": "complete",
                        } for round_number in range(4)],
                        "pre_probe_answer": valid_answer(goal="wrong guess"),
                        "final_answer": valid_answer(),
                        "probe_log": [{"kind": "probe", "ok": True, "start_tid": "S00001"}],
                    }],
                }))
                worksheet, resolved = grade.build_worksheet(
                    [answers], frozen, execute_plans=False
                )
                filled = copy.deepcopy(worksheet)
                cell = filled["cells"][0]
                final2 = cell["axis2_worksheet"]
                final2["VERDICT_correct_in_kind"] = True
                final2["VERDICT_constraints_by_item"] = [True, True, True]
                final2["VERDICT_constraints_present"] = True
                final2["VERDICT_per_hypothesis_true"] = [True]
                final2["VERDICT_terminal_evidence_present"] = True
                pre2 = cell["pre_probe_axis2_worksheet"]
                pre2["VERDICT_correct_in_kind"] = False
                pre2["VERDICT_constraints_by_item"] = [False, False, False]
                pre2["VERDICT_constraints_present"] = False
                pre2["VERDICT_per_hypothesis_true"] = [False]
                pre2["VERDICT_terminal_evidence_present"] = False
                axis3 = cell["axis3_worksheet"]
                axis3["VERDICT_counterfactuals"] = [True]
                axis3["VERDICT_survives_counterfactuals"] = True
                scored = grade.score_adjudications(
                    worksheet, filled, frozen, resolved, execute_plans=False
                )
                scored_cell = scored["cells"][0]
                self.assertTrue(scored_cell["axis2"]["primary_pass"])
                self.assertEqual(
                    scored_cell["terminal_evidence"]["classification"], "probe-acquired"
                )
                self.assertEqual(scored["closure"]["decision"], "NO_CLOSURE")

    def test_expected_but_absent_cell_is_retained_as_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            protocol = TemporaryProtocol(Path(temporary))
            preregistration = protocol.create()
            with protocol.patched():
                grade.freeze(preregistration)
                frozen = grade.verify_legacy_freeze()
                answers = protocol.root / "partial.json"
                answers.write_text(json.dumps({
                    "frozen_manifest_sha256": grade.sha256_file(protocol.frozen),
                    "git": {"commit": "f" * 40, "dirty": False, "status": []},
                    "role": "qwen", "seeds": [4], "arms": ["P"],
                    "budgets": dict(grade.DEFAULT_BUDGETS),
                    "certificate": {"checkpoint_sha256": "a" * 64,
                                    "certificate_sha256": frozen["certificate"]["sha256"],
                                    "certificate_verified_shards": True},
                    "cells": [],
                }))
                worksheet, _ = grade.build_worksheet([answers], frozen, execute_plans=False)
                self.assertEqual(worksheet["cells"][0]["observation"]["status"], "incomplete_run")


class ClosureTests(unittest.TestCase):
    def test_stage_a_is_always_descriptive_and_cannot_close(self) -> None:
        frozen = {
            "preregistration": {
                "stage": "A",
                "games": ["g0"],
                "closure": {
                    "qwen_max_pass_games": 99,
                    "ceiling_min_pass_games": 0,
                },
            }
        }
        roles = {
            "qwen": {"games_passed": 0, "games_scored": 1},
            "ceiling": {"games_passed": 1, "games_scored": 1},
        }
        decision = grade.closure_decision(roles, frozen)
        self.assertEqual(decision["status"], "descriptive_only")
        self.assertEqual(decision["decision"], "NO_CLOSURE")

    def test_stage_a_model_ceiling_input_is_matched_but_remains_descriptive(self) -> None:
        spec = valid_model_ceiling_spec()
        spec_sha = grade.sha256_json(spec)
        qwen_key = "qwen|G000001|P|seed=2"
        ceiling_key = "ceiling|G000001|P|seed=2"
        qwen_cell = {
            "rounds": [{
                "messages": [{
                    "role": "user", "content": [{"type": "text", "text": "evidence"}],
                }],
                "images": [],
            }],
            "delivery_log": [{"delivered_images": [], "omitted_images": []}],
        }
        frozen = {
            "preregistration_sha256": "prereg",
            "preregistration": {
                "stage": "A",
                "roles": ["qwen", "ceiling"],
                "primary_arm": "P",
                "ceiling_spec": spec,
                "ceiling_spec_sha256": spec_sha,
                "ceiling_familiarity_policy": {
                    "eligible_declarations": list(grade.CEILING_ELIGIBLE_FAMILIARITY),
                },
                "expected_cells": [
                    {"role": "qwen", "game_blind": "G000001", "arm": arm, "seed": 2}
                    for arm in ("T", "V", "O", "P")
                ] + [{
                    "role": "ceiling", "game_blind": "G000001", "arm": "P", "seed": 2,
                }],
            },
            "packets": {"G000001": {"manifest_sha256": "packet"}},
        }
        resolved = {
            qwen_key: {"status": "answered", "selected": {"cell": qwen_cell}},
            ceiling_key: {"status": "answered", "selected": {"cell": {}}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            frozen_path = Path(temporary) / "FROZEN.json"
            frozen_path.write_text("{}")
            with mock.patch.object(grade, "FROZEN", frozen_path):
                artifact = grade.build_ceiling_input_payload(
                    resolved, frozen, released_utc="2026-08-17T10:01:00+00:00"
                )
                self.assertEqual(artifact["closure_eligibility"], "descriptive_only_model")
                self.assertEqual(len(artifact["cells"]), 1)
                artifact_path = Path(temporary) / "ceiling_input.json"
                artifact_path.write_text(json.dumps(artifact))
                resolved[ceiling_key]["selected"] = {
                    "cell": {
                        "ceiling_input_cell_sha256": artifact["cells"][0][
                            "evidence_sha256"
                        ],
                    },
                    "ceiling_input": {
                        "path": str(artifact_path),
                        "sha256": grade.sha256_file(artifact_path),
                    },
                }
                grade.enforce_ceiling_matches(resolved, frozen)
        self.assertEqual(resolved[ceiling_key]["status"], "answered")
        self.assertIsNotNone(resolved[ceiling_key]["selected"])
        decision = grade.closure_decision({"qwen": {}, "ceiling": {}}, frozen)
        self.assertEqual(decision["status"], "descriptive_only")
        self.assertEqual(decision["decision"], "NO_CLOSURE")

    def test_model_ceiling_is_descriptive_only_and_cannot_close(self) -> None:
        frozen = {
            "preregistration": {
                "stage": "B", "games": [f"g{i}" for i in range(6)],
                "ceiling_spec": {"kind": "model"},
                "closure": {"qwen_max_pass_games": 0, "ceiling_min_pass_games": 4},
            }
        }
        roles = {
            "qwen": {"games_passed": 0, "games_scored": 6},
            "ceiling": {"games_passed": 6, "games_scored": 6},
        }
        decision = grade.closure_decision(roles, frozen)
        self.assertEqual(decision["status"], "descriptive_only")
        self.assertEqual(decision["decision"], "NO_CLOSURE")

    def test_stage_b_ceiling_answer_and_input_must_match_frozen_spec(self) -> None:
        spec = valid_ceiling_spec()
        spec_sha = grade.sha256_json(spec)
        cell_key = "ceiling|G000001|P|seed=1"
        final_answer = valid_answer()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frozen_path = root / "FROZEN.json"
            frozen_path.write_text("{}")
            frozen = {
                "git_commit": "f" * 40,
                "preregistration_sha256": "prereg",
                "preregistration": {
                    "stage": "B", "roles": ["qwen", "ceiling"],
                    "seeds": [1, 2, 3], "arms": ["P"], "primary_arm": "P",
                    "missing_reruns": 1,
                    "budgets": dict(grade.DEFAULT_BUDGETS),
                    "ceiling_spec": spec, "ceiling_spec_sha256": spec_sha,
                    "ceiling_familiarity_policy": {
                        "eligible_declarations": list(grade.CEILING_ELIGIBLE_FAMILIARITY),
                    },
                    "expected_cells": [{
                        "role": "ceiling", "game_blind": "G000001", "arm": "P", "seed": 1,
                    }],
                },
            }
            with mock.patch.object(grade, "FROZEN", frozen_path):
                with self.assertRaisesRegex(RuntimeError, "not closure-eligible before evidence"):
                    grade.build_familiarity_commitment_payload(
                        {
                            "respondent_id": spec["cohort"]["respondent_id"],
                            "declarations": [{
                                "cell_key": cell_key, "familiarity": "familiar",
                            }],
                        },
                        frozen,
                        committed_utc="2026-08-17T10:00:00+00:00",
                    )
                commitment = grade.build_familiarity_commitment_payload(
                    {
                        "respondent_id": spec["cohort"]["respondent_id"],
                        "declarations": [{
                            "cell_key": cell_key, "familiarity": "unfamiliar",
                        }],
                    },
                    frozen,
                    committed_utc="2026-08-17T10:00:00+00:00",
                )
            commitment_path = root / "familiarity.json"
            commitment_path.write_text(json.dumps(commitment))
            commitment_binding = {
                "path": str(commitment_path), "sha256": grade.sha256_file(commitment_path),
            }
            evidence = {"user_messages": [{"role": "user", "content": "evidence"}]}
            input_cell = {
                "ceiling_cell_key": cell_key,
                "evidence": evidence,
                "evidence_sha256": grade.sha256_json(evidence),
            }
            ceiling_input = {
                "format_version": grade.FORMAT_VERSION,
                "artifact_type": "s4_transcript_matched_ceiling_input",
                "frozen_manifest_sha256": grade.sha256_file(frozen_path),
                "preregistration_sha256": frozen["preregistration_sha256"],
                "ceiling_spec": spec, "ceiling_spec_sha256": spec_sha,
                "ceiling_familiarity_policy": frozen["preregistration"][
                    "ceiling_familiarity_policy"
                ],
                "released_utc": "2026-08-17T10:01:00+00:00",
                "closure_eligibility": "screened_blinded_human",
                "respondent_id": spec["cohort"]["respondent_id"],
                "familiarity_commitment": commitment_binding,
                "familiarity_declarations": commitment["declarations"],
                "cells": [input_cell],
            }
            ceiling_input_path = root / "ceiling_input.json"
            ceiling_input_path.write_text(json.dumps(ceiling_input))
            ceiling_input_sha = grade.sha256_file(ceiling_input_path)
            receipt = {
                "format_version": grade.FORMAT_VERSION,
                "artifact_type": "s4_human_ceiling_delivery_receipt",
                "ceiling_spec_sha256": spec_sha,
                "ceiling_input_sha256": ceiling_input_sha,
                "familiarity_commitment_sha256": commitment_binding["sha256"],
                "respondent_id": spec["cohort"]["respondent_id"],
                "cells": [{
                    "ceiling_spec_sha256": spec_sha,
                    "familiarity_commitment_sha256": commitment_binding["sha256"],
                    "cell_key": cell_key,
                    "respondent_id": spec["cohort"]["respondent_id"],
                    "ceiling_input_sha256": ceiling_input_sha,
                    "evidence_sha256": input_cell["evidence_sha256"],
                    "familiarity": "unfamiliar",
                    "no_extra_evidence": True,
                    "final_answer_sha256": grade.sha256_json(final_answer),
                }],
            }
            receipt_path = root / "delivery_receipt.json"
            receipt_path.write_text(json.dumps(receipt))
            document = {
                "frozen_manifest_sha256": grade.sha256_file(frozen_path),
                "git": {"commit": "f" * 40, "dirty": False},
                "budgets": dict(grade.DEFAULT_BUDGETS),
                "role": "ceiling",
                "seeds": [1],
                "arms": ["P"],
                "cells": [{
                    "respondent_id": spec["cohort"]["respondent_id"],
                    "familiarity": "unfamiliar",
                    "game_blind": "G000001", "arm": "P", "seed": 1,
                    "final_answer": final_answer,
                }],
                "ceiling_spec": spec,
                "ceiling_spec_sha256": spec_sha,
                "respondent_id": spec["cohort"]["respondent_id"],
                "ceiling_input": {
                    "path": str(ceiling_input_path),
                    "sha256": ceiling_input_sha,
                },
                "familiarity_commitment": commitment_binding,
                "ceiling_delivery_receipt": {
                    "path": str(receipt_path), "sha256": grade.sha256_file(receipt_path),
                },
            }
            with mock.patch.object(grade, "FROZEN", frozen_path):
                self.assertEqual(grade.validate_run_document(document, frozen)[0], "ceiling")

                missing_commitment = copy.deepcopy(document)
                del missing_commitment["familiarity_commitment"]
                with self.assertRaisesRegex(RuntimeError, "differs from ceiling_input"):
                    grade.validate_run_document(missing_commitment, frozen)

                changed_document = copy.deepcopy(document)
                changed_document["ceiling_spec"]["cohort"]["cohort_id"] = "shopped-cohort"
                with self.assertRaisesRegex(RuntimeError, "frozen ceiling_spec"):
                    grade.validate_run_document(changed_document, frozen)

                changed_respondent = copy.deepcopy(document)
                changed_respondent["cells"][0]["respondent_id"] = "substituted-respondent"
                with self.assertRaisesRegex(RuntimeError, "respondent_id differs"):
                    grade.validate_run_document(changed_respondent, frozen)

                changed_document_respondent = copy.deepcopy(document)
                changed_document_respondent["respondent_id"] = "substituted-respondent"
                with self.assertRaisesRegex(RuntimeError, "document respondent_id differs"):
                    grade.validate_run_document(changed_document_respondent, frozen)

                wrong_eligibility = copy.deepcopy(ceiling_input)
                wrong_eligibility["closure_eligibility"] = "descriptive_only_model"
                ceiling_input_path.write_text(json.dumps(wrong_eligibility))
                bad_eligibility = copy.deepcopy(document)
                bad_eligibility["ceiling_input"]["sha256"] = grade.sha256_file(
                    ceiling_input_path
                )
                with self.assertRaisesRegex(RuntimeError, "screened blinded respondent"):
                    grade.validate_run_document(bad_eligibility, frozen)
                ceiling_input_path.write_text(json.dumps(ceiling_input))

                changed_receipt = copy.deepcopy(receipt)
                changed_receipt["cells"][0]["no_extra_evidence"] = False
                receipt_path.write_text(json.dumps(changed_receipt))
                bad_delivery = copy.deepcopy(document)
                bad_delivery["ceiling_delivery_receipt"]["sha256"] = grade.sha256_file(
                    receipt_path
                )
                with self.assertRaisesRegex(RuntimeError, "does not attest no extra evidence"):
                    grade.validate_run_document(bad_delivery, frozen)
                receipt_path.write_text(json.dumps(receipt))

                commitment_path.write_text(json.dumps({**commitment, "committed_utc": (
                    "2026-08-17T10:02:00+00:00"
                )}))
                with self.assertRaisesRegex(RuntimeError, "missing or its bytes changed"):
                    grade.validate_run_document(document, frozen)
                commitment_path.write_text(json.dumps(commitment))

                changed_input = copy.deepcopy(spec)
                changed_input["cohort"]["cohort_id"] = "shopped-cohort"
                ceiling_input_path.write_text(json.dumps({
                    "ceiling_spec": changed_input,
                    "ceiling_spec_sha256": grade.sha256_json(changed_input),
                }))
                changed_binding = copy.deepcopy(document)
                changed_binding["ceiling_input"]["sha256"] = grade.sha256_file(
                    ceiling_input_path
                )
                with self.assertRaisesRegex(RuntimeError, "does not match the frozen ceiling_spec"):
                    grade.validate_run_document(changed_binding, frozen)

    def test_stage_a_model_ceiling_requires_strict_execution_trace(self) -> None:
        spec = {
            "kind": "model",
            "model": {
                "provider": "fixture-provider",
                "model_id": "fixture/model-v1",
                "checkpoint_sha256": "a" * 64,
                "serving_config": {"temperature": 0, "reasoning_effort": "high"},
            },
            "respondent_count": 1,
            "aggregation": {"rule": "single_respondent", "tie_rule": "not_applicable"},
            "familiarity_collection": {
                "timing": "not_applicable",
                "scope": "model_training_exposure_unknown",
                "eligible_declarations": [],
            },
        }
        spec_sha = grade.sha256_json(spec)
        final_answer = valid_answer()
        cell_key = "ceiling|G000001|P|seed=1"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frozen_path = root / "FROZEN.json"
            frozen_path.write_text("{}")
            evidence = {
                "user_messages": [{"role": "user", "content": "exact evidence prompt"}],
            }
            input_cell = {
                "ceiling_cell_key": cell_key,
                "evidence": evidence,
                "evidence_sha256": grade.sha256_json(evidence),
            }
            ceiling_input_path = root / "ceiling_input.json"
            ceiling_input_path.write_text(json.dumps({
                "format_version": grade.FORMAT_VERSION,
                "artifact_type": "s4_transcript_matched_ceiling_input",
                "frozen_manifest_sha256": grade.sha256_file(frozen_path),
                "preregistration_sha256": "prereg",
                "ceiling_spec": spec, "ceiling_spec_sha256": spec_sha,
                "ceiling_familiarity_policy": {
                    "eligible_declarations": list(grade.CEILING_ELIGIBLE_FAMILIARITY),
                },
                "released_utc": "2026-08-17T10:01:00+00:00",
                "closure_eligibility": "descriptive_only_model",
                "respondent_id": None,
                "familiarity_commitment": None,
                "familiarity_declarations": None,
                "cells": [input_cell],
            }))
            ceiling_input_sha = grade.sha256_file(ceiling_input_path)
            raw_path = root / "raw_response_run_metadata.json"
            raw_execution = {
                "format_version": grade.FORMAT_VERSION,
                "artifact_type": "s4_model_ceiling_raw_execution",
                "ceiling_spec_sha256": spec_sha,
                "cell_key": cell_key,
                "provider": spec["model"]["provider"],
                "model": spec["model"],
                "run_id": "provider-run-0001",
                "ceiling_input_sha256": ceiling_input_sha,
                "evidence_sha256": input_cell["evidence_sha256"],
                "prompt_messages": evidence["user_messages"],
                "raw_response": {"provider_payload": "{...}"},
                "run_metadata": {"request_id": "provider-run-0001"},
                "final_answer": final_answer,
            }
            raw_path.write_text(json.dumps(raw_execution))
            trace_path = root / "ceiling_trace.json"
            trace = {
                "format_version": grade.FORMAT_VERSION,
                "artifact_type": "s4_model_ceiling_execution_trace",
                "ceiling_spec_sha256": spec_sha,
                "cells": [{
                    "ceiling_spec_sha256": spec_sha,
                    "cell_key": cell_key,
                    "provider": spec["model"]["provider"],
                    "run_id": "provider-run-0001",
                    "model": spec["model"],
                    "ceiling_input_sha256": ceiling_input_sha,
                    "evidence_sha256": input_cell["evidence_sha256"],
                    "prompt_messages_sha256": grade.sha256_json(
                        evidence["user_messages"]
                    ),
                    "raw_response_run_metadata": {
                        "path": str(raw_path), "sha256": grade.sha256_file(raw_path),
                    },
                    "final_answer_sha256": grade.sha256_json(final_answer),
                }],
            }
            trace_path.write_text(json.dumps(trace))
            frozen = {
                "git_commit": "f" * 40,
                "preregistration_sha256": "prereg",
                "preregistration": {
                    "stage": "A", "roles": ["qwen", "ceiling"],
                    "seeds": [1, 2, 3], "arms": ["P"], "missing_reruns": 1,
                    "budgets": dict(grade.DEFAULT_BUDGETS),
                    "ceiling_spec": spec, "ceiling_spec_sha256": spec_sha,
                    "ceiling_familiarity_policy": {
                        "eligible_declarations": list(grade.CEILING_ELIGIBLE_FAMILIARITY),
                    },
                },
            }
            document = {
                "frozen_manifest_sha256": grade.sha256_file(frozen_path),
                "git": {"commit": "f" * 40, "dirty": False},
                "budgets": dict(grade.DEFAULT_BUDGETS),
                "role": "ceiling", "seeds": [1], "arms": ["P"],
                "ceiling_spec": spec, "ceiling_spec_sha256": spec_sha,
                "ceiling_input": {
                    "path": str(ceiling_input_path),
                    "sha256": ceiling_input_sha,
                },
                "ceiling_execution_trace": {
                    "path": str(trace_path), "sha256": grade.sha256_file(trace_path),
                },
                "cells": [{
                    "game_blind": "G000001", "arm": "P", "seed": 1,
                    "familiarity": "unfamiliar", "final_answer": final_answer,
                }],
            }
            with mock.patch.object(grade, "FROZEN", frozen_path):
                self.assertEqual(grade.validate_run_document(document, frozen)[0], "ceiling")
                missing = copy.deepcopy(document)
                del missing["ceiling_execution_trace"]
                with self.assertRaisesRegex(RuntimeError, "must bind an immutable"):
                    grade.validate_run_document(missing, frozen)

                trace["cells"][0]["final_answer_sha256"] = "b" * 64
                trace_path.write_text(json.dumps(trace))
                mismatched = copy.deepcopy(document)
                mismatched["ceiling_execution_trace"]["sha256"] = grade.sha256_file(trace_path)
                with self.assertRaisesRegex(RuntimeError, "answer drift"):
                    grade.validate_run_document(mismatched, frozen)

                trace["cells"][0]["final_answer_sha256"] = grade.sha256_json(final_answer)
                trace["cells"][0]["evidence_sha256"] = "c" * 64
                substituted_evidence_raw = copy.deepcopy(raw_execution)
                substituted_evidence_raw["evidence_sha256"] = "c" * 64
                raw_path.write_text(json.dumps(substituted_evidence_raw))
                trace["cells"][0]["raw_response_run_metadata"]["sha256"] = (
                    grade.sha256_file(raw_path)
                )
                trace_path.write_text(json.dumps(trace))
                tampered_evidence = copy.deepcopy(document)
                tampered_evidence["ceiling_execution_trace"]["sha256"] = grade.sha256_file(
                    trace_path
                )
                with self.assertRaisesRegex(RuntimeError, "evidence drift"):
                    grade.validate_run_document(tampered_evidence, frozen)

                trace["cells"][0]["evidence_sha256"] = input_cell["evidence_sha256"]
                raw_path.write_text(json.dumps(raw_execution))
                trace["cells"][0]["raw_response_run_metadata"]["sha256"] = (
                    grade.sha256_file(raw_path)
                )
                trace_path.write_text(json.dumps(trace))
                raw_path.write_text(json.dumps({"run_id": "substituted", "raw_response": "x"}))
                tampered_raw = copy.deepcopy(document)
                tampered_raw["ceiling_execution_trace"]["sha256"] = grade.sha256_file(trace_path)
                with self.assertRaisesRegex(RuntimeError, "raw response metadata changed"):
                    grade.validate_run_document(tampered_raw, frozen)

                substituted_raw = copy.deepcopy(raw_execution)
                substituted_raw["run_id"] = "substituted-provider-run"
                raw_path.write_text(json.dumps(substituted_raw))
                trace["cells"][0]["raw_response_run_metadata"]["sha256"] = (
                    grade.sha256_file(raw_path)
                )
                trace_path.write_text(json.dumps(trace))
                rehashed_substitution = copy.deepcopy(document)
                rehashed_substitution["ceiling_execution_trace"]["sha256"] = (
                    grade.sha256_file(trace_path)
                )
                with self.assertRaisesRegex(RuntimeError, "raw execution binding drift"):
                    grade.validate_run_document(rehashed_substitution, frozen)

                substituted_prompt = copy.deepcopy(raw_execution)
                substituted_prompt["prompt_messages"] = [{
                    "role": "user", "content": "extra undisclosed evidence",
                }]
                raw_path.write_text(json.dumps(substituted_prompt))
                trace["cells"][0]["prompt_messages_sha256"] = grade.sha256_json(
                    substituted_prompt["prompt_messages"]
                )
                trace["cells"][0]["raw_response_run_metadata"]["sha256"] = (
                    grade.sha256_file(raw_path)
                )
                trace_path.write_text(json.dumps(trace))
                rehashed_prompt_substitution = copy.deepcopy(document)
                rehashed_prompt_substitution["ceiling_execution_trace"]["sha256"] = (
                    grade.sha256_file(trace_path)
                )
                with self.assertRaisesRegex(RuntimeError, "prompt/messages drift"):
                    grade.validate_run_document(rehashed_prompt_substitution, frozen)

    def test_ceiling_evidence_digest_binds_actual_delivery_log(self) -> None:
        packet = {"manifest_sha256": "packet"}
        base = {
            "rounds": [{"messages": [{"role": "user", "content": [{"type": "text", "text": "evidence"}]}],
                        "images": []}],
            "probe_log": [{"kind": "retrieval", "ok": True}],
            "delivery_log": [{"delivered_images": ["one.png"], "omitted_images": []}],
        }
        changed = copy.deepcopy(base)
        changed["delivery_log"][0] = {
            "delivered_images": [], "omitted_images": [{"path": "one.png"}],
        }
        self.assertNotEqual(
            grade.evidence_digest(base, packet), grade.evidence_digest(changed, packet)
        )

    def test_ceiling_match_requires_grader_reconstructable_immutable_artifact(self) -> None:
        qkey = "qwen|G000001|P|seed=1"
        ckey = "ceiling|G000001|P|seed=1"
        ceiling_spec = valid_ceiling_spec()
        qcell = {
            "rounds": [{
                "messages": [{"role": "user", "content": [{"type": "text", "text": "evidence"}]}],
                "images": [],
            }],
            "delivery_log": [{"delivered_images": [], "omitted_images": []}],
        }
        frozen = {
            "preregistration": {
                "stage": "B", "roles": ["qwen", "ceiling"], "primary_arm": "P",
                "ceiling_familiarity_policy": {
                    "eligible_declarations": list(grade.CEILING_ELIGIBLE_FAMILIARITY),
                },
                "ceiling_spec": ceiling_spec,
                "ceiling_spec_sha256": grade.sha256_json(ceiling_spec),
                "expected_cells": [
                    {"role": "qwen", "game_blind": "G000001", "arm": "P", "seed": 1},
                    {"role": "ceiling", "game_blind": "G000001", "arm": "P", "seed": 1},
                ],
            },
            "preregistration_sha256": "prereg",
            "packets": {"G000001": {"manifest_sha256": "packet"}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frozen_path = root / "FROZEN.json"
            frozen_path.write_text("{}")
            resolved = {
                qkey: {"selected": {"cell": qcell}},
                ckey: {"status": "answered", "selected": {"cell": {}}},
            }
            with mock.patch.object(grade, "FROZEN", frozen_path):
                commitment = grade.build_familiarity_commitment_payload(
                    {
                        "respondent_id": ceiling_spec["cohort"]["respondent_id"],
                        "declarations": [{
                            "cell_key": ckey, "familiarity": "unfamiliar",
                        }],
                    },
                    frozen,
                    committed_utc="2026-08-17T10:00:00+00:00",
                )
                commitment_path = root / "familiarity.json"
                commitment_path.write_text(json.dumps(commitment))
                commitment_binding = {
                    "path": str(commitment_path),
                    "sha256": grade.sha256_file(commitment_path),
                }
                with self.assertRaisesRegex(RuntimeError, "before ceiling evidence release"):
                    grade.build_ceiling_input_payload(
                        resolved,
                        frozen,
                        familiarity_commitment=commitment_binding,
                        released_utc="2026-08-17T09:59:00+00:00",
                    )
                artifact = grade.build_ceiling_input_payload(
                    resolved,
                    frozen,
                    familiarity_commitment=commitment_binding,
                    released_utc="2026-08-17T10:01:00+00:00",
                )
                artifact_path = root / "ceiling_input.json"
                artifact_path.write_text(json.dumps(artifact))
                expected_cell = artifact["cells"][0]
                resolved[ckey]["selected"] = {
                    "cell": {
                        "ceiling_input_cell_sha256": expected_cell["evidence_sha256"],
                        "familiarity": "unfamiliar",
                        "respondent_id": ceiling_spec["cohort"]["respondent_id"],
                    },
                    "ceiling_input": {
                        "path": str(artifact_path),
                        "sha256": grade.sha256_file(artifact_path),
                    },
                }
                grade.enforce_ceiling_matches(resolved, frozen)
                self.assertEqual(resolved[ckey]["status"], "answered")

                for declaration in ("familiar", "unknown", "no prior exposure"):
                    resolved[ckey] = {
                        "status": "answered",
                        "selected": {
                            "cell": {
                                "ceiling_input_cell_sha256": expected_cell["evidence_sha256"],
                                "familiarity": declaration,
                                "respondent_id": ceiling_spec["cohort"]["respondent_id"],
                            },
                            "ceiling_input": {
                                "path": str(artifact_path),
                                "sha256": grade.sha256_file(artifact_path),
                            },
                        },
                    }
                    grade.enforce_ceiling_matches(resolved, frozen)
                    self.assertIsNone(resolved[ckey]["selected"])
                    self.assertEqual(
                        resolved[ckey]["missing_kind"], "ceiling_familiarity_mismatch"
                    )

                qcell["delivery_log"] = [{
                    "delivered_images": [], "omitted_images": [{"path": "withheld.png"}],
                }]
                resolved[ckey] = {
                    "status": "answered",
                    "selected": {
                        "cell": {
                            "ceiling_input_cell_sha256": expected_cell["evidence_sha256"],
                            "familiarity": "unfamiliar",
                            "respondent_id": ceiling_spec["cohort"]["respondent_id"],
                        },
                        "ceiling_input": {
                            "path": str(artifact_path),
                            "sha256": grade.sha256_file(artifact_path),
                        },
                    },
                }
                grade.enforce_ceiling_matches(resolved, frozen)
                self.assertEqual(resolved[ckey]["missing_kind"], "unmatched_ceiling")

    def test_closure_requires_zero_qwen_and_two_ceiling_passes_in_each_stratum(self) -> None:
        games = [f"g{i}" for i in range(6)]
        frozen = {
            "preregistration": {
                "stage": "B",
                "games": games,
                "autonomous_completion_lengths": {
                    **{game: index + 1 for index, game in enumerate(games[:3])},
                    **{game: None for game in games[3:]},
                },
                "closure": dict(grade.STAGE_B_CLOSURE),
                "ceiling_spec": valid_ceiling_spec(),
            }
        }

        def role(passed: set[str], missing: set[str] | None = None) -> dict:
            missing = missing or set()
            rows = {
                game: {"pass": None if game in missing else game in passed}
                for game in games
            }
            return {
                "games": rows,
                "games_passed": sum(row["pass"] is True for row in rows.values()),
                "games_scored": sum(row["pass"] is not None for row in rows.values()),
            }

        roles = {
            "qwen": role(set()),
            "ceiling": role({"g0", "g1", "g3", "g4"}),
        }
        closed = grade.closure_decision(roles, frozen)
        self.assertEqual(closed["decision"], "FAILS_REQUIRED_GOAL_INFERENCE_GATE")
        self.assertEqual(
            closed["completion_strata"]["completion_unexposed"]["verdict"],
            "closure_condition_met",
        )

        ineligible = copy.deepcopy(roles)
        ineligible["ceiling"] = role({"g0", "g1", "g3", "g4"}, {"g5"})
        decision = grade.closure_decision(ineligible, frozen)
        self.assertEqual(decision["status"], "indeterminate")
        self.assertEqual(decision["decision"], "NO_CLOSURE")

        concentrated = copy.deepcopy(roles)
        concentrated["ceiling"] = role({"g0", "g1", "g2", "g3"})
        decision = grade.closure_decision(concentrated, frozen)
        self.assertEqual(decision["status"], "indeterminate")
        self.assertEqual(decision["decision"], "NO_CLOSURE_PACKET_INDICTED")
        self.assertEqual(
            decision["completion_strata"]["completion_unexposed"]["verdict"],
            "packet_adequacy_not_established",
        )

        witnessed = copy.deepcopy(roles)
        witnessed["qwen"] = role({"g5"})
        self.assertEqual(
            grade.closure_decision(witnessed, frozen)["decision"], "KEEP_ROLE_OPEN"
        )


if __name__ == "__main__":
    unittest.main()
