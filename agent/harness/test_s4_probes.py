#!/usr/bin/env python3
"""Engine-free regression tests for bounded retrieval and active probes."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_probes as probes


def grid(*cells: tuple[int, int, int]) -> list[list[int]]:
    value = [[0 for _ in range(64)] for _ in range(64)]
    for row, col, colour in cells:
        value[row][col] = colour
    return value


def recap_step(
    episode_step: int,
    store_step: int,
    action: list[Any],
    frames: list[list[list[int]]],
) -> dict[str, Any]:
    settled = probes.canonical_sha256(frames[-1]) if frames else None
    return {
        "episode_step": episode_step,
        "store_index": store_step - 1,
        "store_step": store_step,
        "action": action,
        "frame_count": len(frames),
        "frames": frames,
        "settled_grid_sha256": settled,
        "response_state": "NOT_FINISHED",
        "levels_completed": 0,
        "verified": True,
    }


def fixture() -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, list[list[int]]]]:
    boards = {
        "g0": grid(),
        "g1": grid((2, 2, 3)),
        "g3": grid((0, 0, 2)),
        "g4": grid((0, 0, 2), (1, 1, 3)),
        "kg": grid((3, 3, 3)),
    }
    evidence = {
        "performs": [
            {"step": 1, "episode_step": 0, "action": [1, None, None], "post": "g0",
             "state": "NOT_FINISHED", "levels": 0},
            {"step": 2, "episode_step": 1, "action": [2, None, None], "post": "g1",
             "state": "NOT_FINISHED", "levels": 0},
            # This filtered terminal row is why compact transition indexes are unsafe.
            {"step": 3, "episode_step": 0, "action": [3, None, None], "post": None,
             "state": "GAME_OVER", "levels": 0},
            {"step": 4, "episode_step": 0, "action": [4, None, None], "post": "g3",
             "state": "NOT_FINISHED", "levels": 0},
            {"step": 5, "episode_step": 1, "action": [5, None, None], "post": "g4",
             "state": "NOT_FINISHED", "levels": 0},
        ],
        "states": {name: board for name, board in boards.items() if name != "kg"},
        "kaggle": [
            {"action": "RESET", "click": None, "board": boards["kg"],
             "level": 1, "level_completed": False},
            {"action": "ACTION1", "click": None, "board": boards["kg"],
             "level": 1, "level_completed": False},
        ],
        "recap": {"episodes": []},
        "recap_dir": Path("unused-in-injected-tests"),
    }
    recaptures = [
        {"episode_index": 0, "steps": [
            recap_step(0, 1, [1, None, None], [boards["g0"]]),
            recap_step(1, 2, [2, None, None], [boards["g1"]]),
        ]},
        {"episode_index": 1, "steps": []},
        {"episode_index": 2, "steps": [
            recap_step(0, 4, [4, None, None], [boards["g3"]]),
            recap_step(1, 5, [5, None, None], [boards["g4"]]),
        ]},
    ]
    return evidence, recaptures, boards


class FakeEngine:
    def __init__(self, outputs: dict[tuple[Any, ...], Any]):
        self.outputs = outputs
        self.performed: list[tuple[Any, ...]] = []
        self.driver = SimpleNamespace()

    def new(self) -> list[tuple[Any, ...]]:
        return []

    def perform(self, handle: list[tuple[Any, ...]], action: tuple[Any, ...]):
        handle.append(action)
        self.performed.append(action)
        value = self.outputs.get(action, [])
        if isinstance(value, dict):
            return value
        return {
            "frames": value,
            "state": "NOT_FINISHED",
            "levels_completed": 0,
        }

    @staticmethod
    def frames(response: dict[str, Any]):
        return response["frames"]


class ProbeSessionTests(unittest.TestCase):
    def make_session(
        self,
        temporary: str,
        *,
        budget: int = 3,
        outputs: dict[tuple[Any, ...], list[list[list[int]]]] | None = None,
        recaptures: list[dict[str, Any]] | None = None,
    ) -> tuple[probes.ProbeSession, FakeEngine, dict[str, list[list[int]]]]:
        evidence, default_recaptures, boards = fixture()
        engine = FakeEngine(outputs or {
            (4, None, None): [boards["g3"]],
            (5, None, None): [boards["g4"]],
            (1, None, None): [boards["g4"]],
        })
        session = probes.ProbeSession(
            "synthetic",
            Path(temporary),
            budget,
            evidence=evidence,
            recapture_records=recaptures if recaptures is not None else default_recaptures,
            engine_factory=lambda _game: engine,
        )
        return session, engine, boards

    def test_original_tid_maps_to_unfiltered_store_rows_and_gates_each_step(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session, engine, _boards = self.make_session(temporary)
            prefix = session._prefix_to("S00004")
            self.assertEqual([step["source_index"] for step in prefix or []], [3, 4])
            result = session.probe("S00004", 1, None)
            self.assertTrue(result["ok"], result)
            self.assertEqual(
                engine.performed,
                [(4, None, None), (5, None, None), (1, None, None)],
            )
            self.assertEqual([s["source_index"] for s in result["prefix_steps"]], [3, 4])
            self.assertTrue(all(s["gate_passed"] for s in result["prefix_steps"]))
            self.assertTrue(all(s["expected_post_sha256"] == s["reached_post_sha256"]
                                for s in result["prefix_steps"]))

    def test_intermediate_prefix_divergence_cannot_reconverge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence, recaptures, boards = fixture()
            wrong = grid((63, 63, 9))
            engine = FakeEngine({
                (4, None, None): [wrong],
                (5, None, None): [boards["g4"]],
                (1, None, None): [boards["g4"]],
            })
            session = probes.ProbeSession(
                "synthetic", Path(temporary), evidence=evidence,
                recapture_records=recaptures, engine_factory=lambda _game: engine,
            )
            result = session.probe("S00004", 1, None)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failure_stage"], "prefix_gate")
            self.assertEqual(result["failed_store_step"], 4)
            self.assertEqual(engine.performed, [(4, None, None)])

    def test_pixel_identical_hidden_state_divergence_fails_prefix_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence, recaptures, boards = fixture()
            engine = FakeEngine({
                (4, None, None): {
                    "frames": [boards["g3"]],
                    "state": "GAME_OVER",
                    "levels_completed": 0,
                },
                (5, None, None): [boards["g4"]],
                (1, None, None): [boards["g4"]],
            })
            session = probes.ProbeSession(
                "synthetic", Path(temporary), evidence=evidence,
                recapture_records=recaptures, engine_factory=lambda _game: engine,
            )
            result = session.probe("S00004", 1, None)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failure_stage"], "prefix_gate")
            self.assertFalse(
                result["prefix_steps"][0]["checks"]["recapture_response_state_match"]
            )

    def test_every_raw_frame_is_returned_on_audited_pages_with_settled_last(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _evidence, _recaptures, boards = fixture()
            active = [grid((i, i, (i % 15) + 1)) for i in range(28)]
            outputs = {
                (4, None, None): [boards["g3"]],
                (5, None, None): [boards["g4"]],
                (1, None, None): active,
            }
            session, _engine, _boards = self.make_session(temporary, outputs=outputs)
            result = session.probe("S00004", 1, None)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["frames_returned"], 28)
            self.assertEqual(len(result["raw_frame_sha256"]), 28)
            self.assertEqual(len(result["images"]), 1)
            self.assertEqual(
                [audit["frame_indexes"] for audit in result["image_audit"]],
                [list(range(28))],
            )
            self.assertTrue(result["image_audit"][0]["contains_settled_outcome"])
            self.assertTrue(result["image_audit"][0]["all_returned_frames"])
            self.assertEqual(result["settled_frame_index"], 27)
            self.assertEqual(result["settled_sha256"], result["raw_frame_sha256"][-1])
            for audit in result["image_audit"]:
                path = Path(audit["path"])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), audit["sha256"])
                self.assertEqual(audit["width"] % 32, 0)
                self.assertEqual(audit["height"] % 32, 0)
                self.assertLessEqual(
                    audit["visual_tokens"], probes.PROBE_RESULT_PAGE_MAX_VISUAL_TOKENS
                )

    def test_oversized_animation_fails_instead_of_rendering_below_four_px(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _evidence, _recaptures, boards = fixture()
            # The certified 28-frame regime fits at 4 px/cell.  This deliberately
            # larger result cannot fit the same single-image/token envelope and
            # must become an instrument error, never an uncertified tiny carrier.
            active = [grid((index % 64, index % 64, (index % 15) + 1))
                      for index in range(96)]
            outputs = {
                (4, None, None): [boards["g3"]],
                (5, None, None): [boards["g4"]],
                (1, None, None): active,
            }
            session, _engine, _boards = self.make_session(temporary, outputs=outputs)
            result = session.probe("S00004", 1, None)
            self.assertFalse(result["ok"], result)
            self.assertTrue(result["instrument_error"])
            self.assertEqual(result["failure_stage"], "probe_render")
            self.assertIn("cannot fit", result["error"])
            self.assertEqual(result["images"] if "images" in result else [], [])

        self.assertEqual(probes.PROBE_STORYBOARD_CELL_PX[-1], 4)

    def test_zero_frame_response_is_not_falsely_called_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _evidence, _recaptures, boards = fixture()
            outputs = {
                (4, None, None): [boards["g3"]],
                (5, None, None): [boards["g4"]],
                (1, None, None): [],
            }
            session, _engine, _boards = self.make_session(temporary, outputs=outputs)
            result = session.probe("S00004", 1, None)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["outcome"], "zero_frames")
            self.assertTrue(result["zero_frames"])
            self.assertFalse(result["terminal_state_observed"])
            self.assertEqual(result["response_state"], "NOT_FINISHED")
            self.assertEqual(result["levels_completed"], 0)
            self.assertIsNone(result["settled_sha256"])
            self.assertEqual(result["raw_frame_sha256"], [])
            self.assertEqual(result["images"], [])

    def test_active_probe_returns_exact_state_and_level_delta(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _evidence, _recaptures, boards = fixture()
            outputs = {
                (4, None, None): [boards["g3"]],
                (5, None, None): [boards["g4"]],
                (1, None, None): {
                    "frames": [],
                    "state": "GAME_OVER",
                    "levels_completed": 1,
                },
            }
            session, _engine, _boards = self.make_session(temporary, outputs=outputs)
            result = session.probe("S00004", 1, None)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["response_state"], "GAME_OVER")
            self.assertEqual(result["baseline_levels_completed"], 0)
            self.assertEqual(result["levels_completed"], 1)
            self.assertEqual(result["level_delta"], 1)
            self.assertTrue(result["level_advanced"])
            self.assertTrue(result["terminal_state_observed"])

    def test_invalid_and_redundant_requests_consume_budget_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session, _engine, _boards = self.make_session(temporary, budget=4)
            invalid = [
                session.probe("S00004", True, None),
                session.probe("S00004", 6, None),
                session.probe("S00004", 6, []),
                session.probe("S00004", 1, [1, 2]),
            ]
            self.assertTrue(all(not result["ok"] for result in invalid))
            self.assertEqual(session.probes_spent, 4)
            self.assertIn("booleans are invalid", invalid[0]["error"])
            self.assertIn("requires", invalid[1]["error"])
            self.assertIn("exactly two", invalid[2]["error"])
            self.assertIn("does not accept", invalid[3]["error"])

        with tempfile.TemporaryDirectory() as temporary:
            _evidence, _recaptures, boards = fixture()
            outputs = {
                (4, None, None): [boards["g3"]],
                (5, None, None): [boards["g4"]],
                (6, 1, 2): [boards["g4"]],
            }
            session, engine, _boards = self.make_session(
                temporary, budget=1, outputs=outputs
            )
            valid_json_click = session.probe("S00004", 6, [1, 2])
            self.assertTrue(valid_json_click["ok"], valid_json_click)
            self.assertEqual(engine.performed[-1], (6, 1, 2))

        with tempfile.TemporaryDirectory() as temporary:
            session, _engine, _boards = self.make_session(temporary, budget=2)
            first = session.probe("S00004", 1, None)
            second = session.probe("S00004", 1, None)
            self.assertTrue(first["ok"])
            self.assertFalse(second["ok"])
            self.assertIn("redundant", second["error"])
            self.assertEqual(session.probes_spent, 2)

    def test_episode_and_colour_history_do_not_cross_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session, _engine, _boards = self.make_session(temporary)
            episode = session.retrieve("SHOW_EPISODE", "S00003", "8")
            self.assertTrue(episode["ok"], episode)
            self.assertEqual(episode["episode_tids"], ["S00003", "S00004"])
            self.assertTrue(episode["boundary_truncated"])
            self.assertEqual(episode["boundary_tid"], "K00000")
            self.assertIn("[0] S00003 settled after A4 click=null", episode["text"])
            self.assertIn("[1] S00004 settled after A5 click=null", episode["text"])
            self.assertEqual(len(episode["images"]), 1)
            self.assertLessEqual(
                episode["image_audit"][0]["visual_tokens"],
                probes.RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS,
            )

            boot = session.retrieve("SHOW_TRANSITION", "S00003")
            self.assertFalse(boot["ok"])
            self.assertIn("boot row", boot["error"])

            history = session.retrieve("SHOW_COLOUR_HISTORY", "3")
            self.assertTrue(history["ok"], history)
            self.assertEqual(history["history_tids"], ["S00001", "S00004"])
            self.assertNotIn("S00003", history["history_tids"])
            self.assertNotIn("K00000", history["history_tids"])
            self.assertEqual(len(history["images"]), 1)

            contrast = session.retrieve("SHOW_ACTION_CONTRAST", "A5")
            self.assertTrue(contrast["ok"], contrast)
            self.assertEqual(contrast["contrast_tids"], ["S00004"])
            self.assertEqual(len(contrast["images"]), 1)
            self.assertIn("deterministic matched-pre contrast", contrast["text"])
            self.assertIn("matched pre-board cell-Hamming distance", contrast["text"])
            self.assertLessEqual(
                contrast["image_audit"][0]["visual_tokens"],
                probes.RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS,
            )

            refused = session.retrieve("SHOW_EPISODE", "S00003", "17")
            self.assertFalse(refused["ok"])
            self.assertIn("was not rewritten", refused["error"])

    def test_control_requests_are_deterministic_verified_and_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session, _engine, _boards = self.make_session(temporary)
            self.assertEqual(
                session.replayable_tids(), ["S00000", "S00001", "S00003", "S00004"]
            )
            first = session.control_request(0, 123)
            repeated = session.control_request(0, 123)
            second = session.control_request(1, 123)
            self.assertEqual(first, repeated)
            self.assertNotEqual(first, second)
            for request in (first, second):
                self.assertIn(request["start_tid"], session.replayable_tids())
                self.assertIsNone(
                    session._validate_action_click(request["action_id"], request["click"])
                )
            selections = [entry for entry in session.log if entry["kind"] == "control_selection"]
            self.assertEqual(len(selections), 3)
            self.assertTrue(all(len(entry["selection_sha256"]) == 64 for entry in selections))

        with tempfile.TemporaryDirectory() as temporary:
            _evidence, _recaptures, boards = fixture()
            outputs = {
                (1, None, None): [boards["g0"]],
                (2, None, None): [boards["g1"]],
                (4, None, None): [boards["g3"]],
                (5, None, None): [boards["g4"]],
            }
            session, _engine, _boards = self.make_session(
                temporary, budget=1, outputs=outputs
            )
            result = session.control_probe(0, 123)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["control_selection"]["seed"], 123)
            self.assertEqual(len(result["control_selection"]["selection_sha256"]), 64)
            self.assertEqual([entry["kind"] for entry in session.log[-2:]],
                             ["control_selection", "probe"])

    def test_static_recapture_mismatch_removes_the_entire_dependent_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            evidence, recaptures, _boards = fixture()
            broken = copy.deepcopy(recaptures)
            broken[2]["steps"][0]["action"] = [7, None, None]
            engine = FakeEngine({})
            session = probes.ProbeSession(
                "synthetic", Path(temporary), evidence=evidence,
                recapture_records=broken, engine_factory=lambda _game: engine,
            )
            self.assertNotIn("S00003", session.replayable_tids())
            self.assertNotIn("S00004", session.replayable_tids())
            result = session.probe("S00004", 1, None)
            self.assertFalse(result["ok"])
            self.assertIn("recapture-verified", result["error"])
            self.assertEqual(session.probes_spent, 1)
            self.assertEqual(engine.performed, [])

    def test_probe_records_provenance_and_full_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session, _engine, _boards = self.make_session(temporary)
            result = session.probe("S00004", 1, None)
            self.assertEqual(len(result["request_sha256"]), 64)
            self.assertEqual(len(result["session_provenance"]["recapture_root_sha256"]), 64)
            self.assertIn("s4_probes", result["session_provenance"]["code_sha256"])
            self.assertIn("wrapper", result["engine"])
            for step in result["prefix_steps"]:
                self.assertEqual(len(step["expected_post_sha256"]), 64)
                self.assertEqual(len(step["reached_post_sha256"]), 64)
                self.assertTrue(all(len(digest) == 64 for digest in step["raw_frame_sha256"]))

    def test_live_engine_source_must_match_the_recapture_bound_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            session, engine, _boards = self.make_session(temporary)
            source = Path(temporary) / "game.py"
            source.write_text("version = 2\n", encoding="utf-8")
            engine.source_path = source
            session._enforce_engine_identity = True
            session.evidence["recap"]["provenance"] = {
                "engine": {
                    "game_source": {
                        "path": str(source.resolve()),
                        "sha256": "0" * 64,
                        "bytes": source.stat().st_size,
                    },
                    "gi2_replay": {
                        "path": str((probes.HARNESS / "gi2_replay.py").resolve()),
                        "sha256": probes.sha256_file(probes.HARNESS / "gi2_replay.py"),
                    },
                    "recapture_script": {
                        "path": str((probes.HARNESS / "s4_recapture.py").resolve()),
                        "sha256": probes.sha256_file(probes.HARNESS / "s4_recapture.py"),
                    },
                },
                "versions": {"arcengine": probes.package_version("arcengine")},
            }
            with self.assertRaisesRegex(RuntimeError, "differs from the recapture-bound"):
                session._ensure_engine()

            session._engine = None
            session.evidence["recap"]["provenance"]["engine"]["game_source"] = {
                "path": str(source.resolve()),
                "sha256": probes.sha256_file(source),
                "bytes": source.stat().st_size,
            }
            self.assertEqual(
                session.verify_live_engine_identity()["game_source"]["sha256"],
                probes.sha256_file(source),
            )
            self.assertIs(session._ensure_engine(), engine)
            self.assertEqual(
                session._engine_identity["game_source"]["sha256"],
                probes.sha256_file(source),
            )


if __name__ == "__main__":
    unittest.main()
