#!/usr/bin/env python3
"""Contract and provenance tests for matched Slice-4 packet carriers."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_packet as packet
import s4_delta as sdl


def board(index: int) -> list[list[int]]:
    array = np.zeros((64, 64), dtype=int)
    array[1:4, 1:4] = 1
    array[8 + index % 40, 12 + index % 45] = 2 + index % 13
    return array.tolist()


class ExactGeometryAuditor:
    identity = {"implementation": "test-exact-geometry", "patch_size": 16, "merge_size": 2}

    def measure(self, image):
        assert image.width % 32 == 0 and image.height % 32 == 0
        return {
            "image_grid_thw": [1, image.height // 16, image.width // 16],
            "processed_size": [image.width, image.height],
            "visual_tokens": packet.visual_tokens(image.width, image.height),
            "measurement": "test-exact-geometry",
        }

    def measure_text(self, text):
        return {"text_tokens": len(text.split()), "text_chars": len(text),
                "measurement": "test-tokenizer"}

    def count_text_tokens(self, text):
        return len(text.split())


def synthetic_evidence(actions: int = 7, animation_frames: int = 5):
    states = {f"d{index}": board(index) for index in range(80)}
    performs = []
    historical = []
    for index in range(42):
        action = index % actions
        pre = f"d{index}"
        # Every action gets effect and no-effect cases with a recorded pre.
        post = pre if index // actions % 2 == 0 else f"d{index + 1}"
        performs.append({
            "step": index + 1, "episode_step": index, "source": "test",
            "pre": pre, "action": [action, None, None], "post": post,
            "levels": 1 if index == 34 else 0, "state": "NOT_FINISHED",
        })
        historical.append({
            "step": index + 1, "episode_step": index, "pre": pre,
            "action": [action, None, None], "post": post, "completed": index == 34,
            "level": 1, "frames": animation_frames if index == 34 else 1,
            "state": "NOT_FINISHED",
        })
    # Exercise the legitimate episode-boundary observation path: there is no
    # recorded predecessor to invent, but the selected TID must still receive a
    # complete bound temporal observation record.
    performs[0]["pre"] = None
    steps = []
    for index, row in enumerate(performs):
        frames = [states[row["post"]]]
        if index == 34:
            frames = [board(60 + offset) for offset in range(animation_frames - 1)] + [
                states[row["post"]]
            ]
        steps.append({
            "episode_step": index, "store_index": index, "store_step": index + 1,
            "action": row["action"], "frame_count": len(frames), "frames": frames,
            "verified": True,
        })
    return {
        "performs": performs, "states": states, "historical": historical, "kaggle": [],
        "recap_records": [{"episode_index": 0, "steps": steps}],
        "input_identity": {"synthetic": {"sha256": "0" * 64}},
    }


class PacketContractTests(unittest.TestCase):
    def test_processor_identity_binds_every_tokenizer_defining_file(self):
        auditor = packet.ProcessorAuditor()
        files = auditor.identity["serving_files"]
        for name in (
            "tokenizer.json", "vocab.json", "merges.txt", "tokenizer_config.json",
            "preprocessor_config.json", "processor_config.json",
        ):
            self.assertEqual(files[name]["sha256"], packet.sha256_file(packet.MODEL / name))
            self.assertEqual(len(files[name]["sha256"]), 64)
        self.assertEqual(
            auditor.identity["measurement_identity_sha256"], packet.canonical_sha256(files)
        )

    def test_transition_ids_keep_source_indexes_episodes_and_completion(self):
        evidence = {
            "states": {"a": board(1), "b": board(2)},
            "performs": [
                {"step": 1, "episode_step": 0, "source": "boot", "pre": None,
                 "action": [0, None, None], "post": "a", "levels": 0,
                 "state": "NOT_FINISHED"},
                {"step": 2, "episode_step": 1, "source": "test", "pre": "a",
                 "action": [1, None, None], "post": None, "levels": 0,
                 "state": "GAME_OVER"},
                {"step": 3, "episode_step": 0, "source": "test", "pre": "a",
                 "action": [5, None, None], "post": "b", "levels": 1,
                 "state": "NOT_FINISHED"},
            ],
            "historical": [
                {"step": 3, "completed": True, "level": 1, "frames": 20},
            ],
            "kaggle": [
                {"seq": 0, "type": "initial", "action": "RESET", "board": board(3),
                 "click": None, "level": 1, "score": 0, "level_completed": False,
                 "state": "NOT_FINISHED"},
                {"seq": 1, "type": "action", "action": "ACTION2", "board": board(4),
                 "click": None, "level": 1, "score": 0, "level_completed": False,
                 "state": "NOT_FINISHED"},
                {"seq": 2, "type": "action", "action": "RESET", "board": board(3),
                 "click": None, "level": 1, "score": 0, "level_completed": False,
                 "state": "NOT_FINISHED"},
            ],
        }
        stream = packet.transition_stream(evidence)
        self.assertEqual([row["tid"] for row in stream[:2]], ["S00000", "S00002"])
        self.assertEqual(stream[1]["store_index"], 2)
        self.assertEqual(stream[1]["episode_index"], 1)
        self.assertEqual(stream[1]["episode_step"], 0)
        self.assertTrue(stream[1]["completed"])
        self.assertEqual(stream[1]["historical_frames"], 20)
        kaggle = [row for row in stream if row["source"] == "kaggle"]
        self.assertEqual([row["tid"] for row in kaggle], ["K00000", "K00001", "K00002"])
        self.assertEqual([row["episode_index"] for row in kaggle], [0, 0, 1])
        self.assertEqual([row["episode_step"] for row in kaggle], [0, 1, 0])
        self.assertIsNone(kaggle[2]["pre"])

    def test_game_seed_is_order_independent(self):
        first = [packet.seed_for_game(game) for game in ("ls20", "ft09", "sp80")]
        reverse = {game: packet.seed_for_game(game) for game in ("sp80", "ft09", "ls20")}
        self.assertEqual(first, [reverse[game] for game in ("ls20", "ft09", "sp80")])
        self.assertEqual(packet.seed_for_game("ls20"), packet.seed_for_game("ls20"))
        self.assertNotEqual(packet.seed_for_game("ls20"), packet.seed_for_game("ft09"))

    def test_store_schema_rejects_manual_or_unknown_action_lineage(self):
        states = {"d": board(1)}
        base = {
            "step": 1, "episode_step": 0, "source": "test", "pre": None,
            "action": [0, None, None], "post": "d", "levels": 0,
            "state": "NOT_FINISHED",
        }
        packet._validate_store([base], states, [])

        manual = dict(base, source="human")
        with self.assertRaisesRegex(RuntimeError, "non-autonomous/unknown source tag"):
            packet._validate_store([manual], states, [])

        annotated = dict(base, operator_note="copied from a solved replay")
        with self.assertRaisesRegex(RuntimeError, "schema mismatch"):
            packet._validate_store([annotated], states, [])

    def test_exact_ten_matched_carrier_pages_and_complete_animation(self):
        temporary = Path(tempfile.mkdtemp(dir="/private/tmp"))
        out = temporary / "packet"
        out.mkdir()
        try:
            manifest = packet._build_into(
                "zz99", out, synthetic_evidence(), ExactGeometryAuditor()
            )
            self.assertEqual(manifest["page_count"], 10)
            self.assertEqual(manifest["selection"]["actual_initial_pages"], 10)
            self.assertFalse(manifest["selection"]["above_target_declared"])
            self.assertTrue(manifest["selection"]["interactive_three_result_pages_fit"])
            self.assertTrue(manifest["selection"]["three_retrieval_pages_fit"])
            self.assertTrue(manifest["selection"]["probe_and_retrieval_six_pages_fit"])
            self.assertTrue(manifest["selection"][
                "interactive_three_minimal_result_pages_fit_token_cap"
            ])
            self.assertTrue(manifest["selection"][
                "probe_and_retrieval_pages_fit_token_cap"
            ])
            self.assertEqual(manifest["selection"]["image_cap_headroom"], 6)
            self.assertEqual(packet.MIN_RESULT_PAGE_VISUAL_TOKENS, 2_112)
            self.assertEqual(packet.RESERVED_RESULT_VISUAL_TOKENS, 6_336)
            self.assertEqual(packet.RESERVED_RETRIEVAL_VISUAL_TOKENS, 3_600)
            self.assertEqual(packet.RESERVED_POST_INITIAL_VISUAL_TOKENS, 9_936)
            self.assertEqual(packet.MAX_INITIAL_VISUAL_TOKENS, 6_448)
            self.assertEqual(
                manifest["caps"]["reserved_post_initial_visual_tokens"], 9_936
            )
            temporal = manifest["temporal_delta_channel"]
            self.assertEqual(
                temporal["model_visible_cell_limit"], sdl.MODEL_VISIBLE_CELL_LIMIT
            )
            self.assertEqual(
                temporal["recorded_transition_ids"],
                temporal["selected_transition_ids"],
            )
            boundary = next(
                record for record in temporal["full_records"]
                if record["binding"]["tid"] == "S00000"
            )
            self.assertFalse(boundary["binding"]["has_recorded_pre"])
            self.assertGreaterEqual(len(boundary["frames"]), 1)
            self.assertIn(sdl.render_carrier_collection(temporal["full_records"]),
                          (out / "ledger.txt").read_text())
            self.assertEqual(
                temporal["model_carrier_sha256"],
                packet.canonical_sha256(
                    sdl.render_carrier_collection(temporal["full_records"])
                ),
            )
            for record in temporal["full_records"]:
                for pair in record["pairs"]:
                    encoded = sdl.encode_exact_pair(pair)
                    expected = ([tuple(item) for item in pair["sparse"]]
                                if "sparse" in pair
                                else sdl.decode_rle_delta(pair["rle"]))
                    self.assertEqual(sdl.decode_exact_pair(encoded), expected)
            for carrier in ("raw", "overlay"):
                pages = manifest["carrier_pages"][carrier]
                self.assertEqual(len(pages), 10)
                self.assertLessEqual(
                    manifest["carrier_totals"][carrier]["visual_tokens"],
                    packet.MAX_INITIAL_VISUAL_TOKENS,
                )
                for page in pages:
                    self.assertEqual(len(page["sha256"]), 64)
                    self.assertEqual(page["processed_size"], [page["width"], page["height"]])
                    self.assertTrue((out / "pages" / page["file"]).is_file())
            self.assertEqual(
                [page["evidence_id"] for page in manifest["carrier_pages"]["raw"]],
                [page["evidence_id"] for page in manifest["carrier_pages"]["overlay"]],
            )
            action_items = [item for item in manifest["evidence_items"]
                            if item["kind"].startswith("action_")]
            self.assertEqual(len(action_items), 6)
            contrasts = [
                value for item in action_items
                for value in item["carriers"]["text"]["derived"]
                if isinstance(value, dict) and "counts" in value
            ]
            self.assertEqual({value["action"] for value in contrasts},
                             {f"A{index}" for index in range(7)})
            for contrast in contrasts:
                counts = contrast["counts"]
                self.assertGreater(counts["effect"], 0)
                self.assertGreater(counts["no_effect"], 0)
                self.assertEqual(contrast["visual_full_board_cell_px"], 4)
                self.assertEqual(
                    contrast["overlay_full_board_panels"],
                    ["marked_pre", "settled_post", "diff"],
                )
                action_id = int(contrast["action"][1:])
                classes = {
                    action["class"] for item in action_items
                    for action in item["action_sequence"]
                    if int(str(action["action"]).removeprefix("A")) == action_id
                }
                expected_classes = {"effect", "no-effect"}
                if action_id == 0:
                    expected_classes.add("unclassified-reset-output")
                self.assertEqual(classes, expected_classes)
            causal = next(item for item in manifest["evidence_items"]
                          if item["kind"] == "causal_episode")
            self.assertTrue(all(action["to_frame"] == action["from_frame"] + 1
                                for action in causal["action_sequence"]))
            causal_layout = causal["carriers"]["text"]["derived"][0]
            self.assertEqual(causal_layout["visual_cell_px"], 4)
            atlas = next(item for item in manifest["evidence_items"]
                         if item["kind"] == "state_atlas")
            self.assertEqual(atlas["carriers"]["text"]["derived"][0]["visual_cell_px"], 4)
            summary = next(item for item in manifest["evidence_items"]
                           if item["kind"] == "temporal_history_coverage")
            animation = next(value["animation"] for value in summary["carriers"]["text"]["derived"]
                             if isinstance(value, dict) and "animation" in value)
            self.assertEqual(animation["frame_count"], 5)
            self.assertEqual(animation["settled_frame_index"], 4)
            self.assertEqual(animation["rendered_cell_px"], 4)
            self.assertEqual(animation["selection_reason"], "completion-transition")
            animation_boards = [entry for entry in summary["carriers"]["text"]["boards"]
                                if entry["frame_id"].startswith(
                                    f"{animation['tid']}:frame:"
                                )]
            self.assertEqual(len(animation_boards), 5)
            completion = next(value["completion_evidence"]
                              for value in summary["carriers"]["text"]["derived"]
                              if isinstance(value, dict) and "completion_evidence" in value)
            self.assertEqual(completion["tid"], animation["tid"])
            self.assertEqual(completion["returned_frame_count"], 5)
            self.assertEqual(completion["next_observed_tid"], "S00035")
            completion_action = next(action for action in summary["action_sequence"]
                                     if action.get("completed") is True)
            self.assertEqual(completion_action["pre_frame"], "S00034:pre")
            self.assertEqual(completion_action["returned_frames"][-1], "S00034:frame:4")
            self.assertEqual(completion_action["settled_frame"], "S00034:frame:4")
            self.assertEqual(completion_action["next_observed_frame"], "S00035:post")
            decoded = {}
            for item in manifest["evidence_items"]:
                for text_board in item["carriers"]["text"]["boards"]:
                    self.assertNotIn("_grid", text_board)
                    value = packet.decode_text_grid(text_board["hex"], decoded)
                    self.assertEqual(packet.canonical_sha256(value), text_board["sha256"])
                    decoded[text_board["frame_id"]] = value
            self.assertEqual(
                manifest["selection"]["text_grid_encoding"]["lossless_decode_hash_checks"],
                manifest["selection"]["text_grid_encoding"]["board_records"],
            )
            self.assertEqual(len(manifest["ledger_sha256"]), 64)
            self.assertEqual(len(manifest["manifest_sha256"]), 64)
        finally:
            shutil.rmtree(temporary)

    def test_normalized_and_recapture_hashes_are_blocking(self):
        temporary = Path(tempfile.mkdtemp(dir="/private/tmp"))
        observation = temporary / "observation"
        store = temporary / "store"
        kaggle = observation / "kaggle_v4"
        recap_dir = observation / "recapture" / "xx00"
        kaggle.mkdir(parents=True)
        recap_dir.mkdir(parents=True)
        store.mkdir()
        try:
            state = board(1)
            performs_text = json.dumps({
                "step": 1, "episode_step": 0, "source": "boot", "pre": None,
                "action": [0, None, None], "post": "d", "levels": 0,
                "state": "NOT_FINISHED",
            }, separators=(",", ":")) + "\n"
            states_text = json.dumps({"d": state}, separators=(",", ":"))
            transitions_text = ""
            graph_text = "{}"
            files = {
                "performs.jsonl": performs_text, "states.json": states_text,
                "transitions.jsonl": transitions_text, "graph.json": graph_text,
            }
            for suffix, text in files.items():
                (store / f"xx00.{suffix}").write_text(text)
            outcomes = temporary / "e1_outcomes_v3.json"
            outcomes.write_text(json.dumps({
                "format_version": 1,
                "games": {"xx00": {"game": "xx00", "performs": 1, "transitions": 0}},
            }))
            explorer = temporary / "e1_explorer.py"
            explorer.write_text("# deterministic fixture explorer\n")
            kaggle_row = {
                "action": "RESET", "action_num": 0, "board": state, "click": None,
                "done": False, "game_over": False, "level": 1,
                "level_completed": False, "reward": 0.0, "score": 0, "seq": 0,
                "state": "NOT_FINISHED", "type": "initial",
            }
            kaggle_text = json.dumps(kaggle_row, separators=(",", ":")) + "\n"
            output = kaggle / "xx00.observations.jsonl"
            output.write_text(kaggle_text)
            fleet = {
                "exporter_sha256": packet.sha256_file(packet.HARNESS / "s4_export_kaggle.py"),
                "fleet_rows": {"action": 0, "initial": 1, "analysis": 9},
                "games": [{
                    "game": "xx00", "output": output.name,
                    "output_sha256": hashlib.sha256(kaggle_text.encode()).hexdigest(),
                    "source_sha256": "1" * 64, "kept_rows": 1, "completions": 0,
                    "rows": {"action": 0, "initial": 1, "analysis": 9},
                }]
            }
            (kaggle / "manifest.json").write_text(json.dumps(fleet))
            record = {
                "format_version": 2, "episode_index": 0, "actions_expected": 1,
                "steps_verified": 1, "divergence": None, "total_frames": 1,
                "steps": [{
                    "episode_step": 0, "store_index": 0, "store_step": 1,
                    "action": [0, None, None], "frame_count": 1,
                    "frames": [state], "verified": True,
                    "expected_store_digest": "d",
                    "settled_grid_sha256": packet.canonical_sha256(state),
                    "response_state": "NOT_FINISHED", "expected_state": "NOT_FINISHED",
                    "levels_completed": 0, "expected_levels_completed": 0,
                    "checks": {"grid": True, "state": True, "levels": True},
                }],
            }
            record_text = json.dumps(record, separators=(",", ":"))
            episode = recap_dir / "episode_000.json"
            episode.write_text(record_text)
            recap = {
                "format_version": 2, "status": "complete", "game": "xx00",
                "steps_verified": 1,
                "episodes": [{
                    "episode_index": 0, "file": episode.name,
                    "sha256": hashlib.sha256(record_text.encode()).hexdigest(),
                }],
                "provenance": {
                    "store": {
                        suffix: {"sha256": hashlib.sha256(text.encode()).hexdigest()}
                        for suffix, text in files.items()
                    },
                    "engine": {
                        "game_source": {"sha256": "2" * 64},
                        "recapture_script": {"sha256": "3" * 64},
                    },
                    "versions": {},
                },
            }
            (recap_dir / "manifest.json").write_text(json.dumps(recap))
            patches = (
                mock.patch.object(packet, "OBSERVATION_ROOT", observation),
                mock.patch.object(packet, "STORE_ROOT", store),
                mock.patch.object(packet, "ALLOWED_ROOTS", (observation, store)),
                mock.patch.object(packet, "E1_OUTCOMES", outcomes),
                mock.patch.object(packet, "E1_EXPLORER", explorer),
                mock.patch.object(packet, "ALLOWED_FILES", (outcomes,)),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                evidence = packet.load_evidence("xx00")
                self.assertEqual(evidence["input_identity"]["normalized_export"]["kept_rows"], 1)
                output.write_text(kaggle_text + kaggle_text)
                with self.assertRaisesRegex(RuntimeError, "output hash mismatch"):
                    packet.load_evidence("xx00")
                output.write_text(kaggle_text)
                episode.write_text(record_text + " ")
                with self.assertRaisesRegex(RuntimeError, "episode 0 hash mismatch"):
                    packet.load_evidence("xx00")
                tampered = json.loads(record_text)
                tampered["steps"][0]["response_state"] = "GAME_OVER"
                tampered_text = json.dumps(tampered, separators=(",", ":"))
                episode.write_text(tampered_text)
                recap["episodes"][0]["sha256"] = hashlib.sha256(
                    tampered_text.encode()
                ).hexdigest()
                (recap_dir / "manifest.json").write_text(json.dumps(recap))
                with self.assertRaisesRegex(RuntimeError, "response-state mismatch"):
                    packet.load_evidence("xx00")
        finally:
            shutil.rmtree(temporary)


if __name__ == "__main__":
    unittest.main()
