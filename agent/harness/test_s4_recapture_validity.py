#!/usr/bin/env python3
"""Focused validity tests for the Slice-4 recapture gate."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_recapture as recapture


def grid(value: int) -> list[list[int]]:
    return [[value for _ in range(64)] for _ in range(64)]


class ScriptedEngine:
    def __init__(self, episodes):
        self.episodes = [list(episode) for episode in episodes]
        self.new_calls = 0

    def new(self):
        script = self.episodes[self.new_calls]
        self.new_calls += 1
        return script

    def perform(self, handle, action):
        response = handle.pop(0)
        response.seen_action = action
        return response

    def frames(self, response):
        return response.frames


def response(frames, state="NOT_FINISHED", levels=0):
    return SimpleNamespace(frames=frames, state=state, levels_completed=levels)


class RecaptureValidityTests(unittest.TestCase):
    def test_zero_frame_terminal_and_following_reset_are_both_accounted(self):
        temporary = Path(tempfile.mkdtemp(dir="/private/tmp"))
        try:
            performs = [
                {"step": 1, "episode_step": 0, "source": "boot", "pre": None,
                 "action": [0, None, None], "post": "g", "levels": 0,
                 "state": "NOT_FINISHED"},
                {"step": 2, "episode_step": 1, "source": "test", "pre": "g",
                 "action": [6, None, None], "post": None, "levels": 0,
                 "state": "GAME_OVER"},
                {"step": 3, "episode_step": 0, "source": "boot", "pre": None,
                 "action": [0, None, None], "post": "g", "levels": 0,
                 "state": "NOT_FINISHED"},
            ]
            (temporary / "xx.performs.jsonl").write_text(
                "\n".join(json.dumps(row) for row in performs) + "\n"
            )
            (temporary / "xx.states.json").write_text(json.dumps({"g": grid(3)}))
            historical = [
                {"step": 1, "frames": 1, "state": "NOT_FINISHED"},
                {"step": 2, "frames": 0, "state": "GAME_OVER"},
                {"step": 3, "frames": 1, "state": "NOT_FINISHED"},
            ]
            (temporary / "xx.transitions.jsonl").write_text(
                "\n".join(json.dumps(row) for row in historical) + "\n"
            )
            with mock.patch.object(recapture, "STORE", temporary):
                episodes, states, old = recapture.load_store("xx")
            self.assertEqual([len(episode) for episode in episodes], [2, 1])
            self.assertEqual([row["_store_index"] for row in episodes[1]], [2])

            engine = ScriptedEngine([
                [response([grid(3)]), response([], state="GAME_OVER")],
                [response([grid(3)])],
            ])
            records = [
                recapture.recapture_episode(engine, states, episode, index, old)
                for index, episode in enumerate(episodes)
            ]
            self.assertEqual(sum(record["steps_verified"] for record in records), 3)
            self.assertEqual(records[0]["zero_frame_steps"], 1)
            self.assertIsNone(records[0]["divergence"])
            self.assertEqual(records[1]["store_start_index"], 2)
            self.assertEqual(records[1]["steps"][0]["action"], [0, None, None])
        finally:
            shutil.rmtree(temporary)

    def test_temporal_state_and_level_mismatches_fail_and_skip_suffix(self):
        rows = [
            {"_store_index": 4, "step": 10, "episode_step": 0, "source": "test",
             "action": [1, None, None], "post": "g", "state": "NOT_FINISHED",
             "levels": 0},
            {"_store_index": 5, "step": 11, "episode_step": 1, "source": "test",
             "action": [2, None, None], "post": "g", "state": "NOT_FINISHED",
             "levels": 0},
        ]
        engine = ScriptedEngine([[
            response([grid(2), grid(2)], state="GAME_OVER", levels=1),
        ]])
        record = recapture.recapture_episode(
            engine, {"g": grid(2)}, rows, 0,
            {10: {"frames": 1, "state": "NOT_FINISHED"}},
        )
        self.assertEqual(record["steps_verified"], 0)
        self.assertEqual(record["actions_attempted"], 1)
        self.assertEqual(record["steps_skipped_after_divergence"], 1)
        self.assertEqual(
            set(record["divergence"]["failed_checks"]),
            {"state", "levels_completed", "historical_frame_count", "historical_state"},
        )

    def test_output_guard_and_atomic_swap_do_not_create_hybrids(self):
        with self.assertRaisesRegex(RuntimeError, "unsafe recapture output"):
            recapture.validate_output_root(Path("/private/tmp/s4-recapture-outside"))
        with self.assertRaisesRegex(RuntimeError, "may not replace the logs root"):
            recapture.validate_output_root(recapture.ROOT / "logs")
        accepted = recapture.validate_output_root(recapture.ROOT / "logs/test-recapture-validity")
        self.assertEqual(accepted, (recapture.ROOT / "logs/test-recapture-validity").resolve())

        temporary = Path(tempfile.mkdtemp(dir="/private/tmp"))
        try:
            target, staged = temporary / "game", temporary / ".ready"
            target.mkdir()
            staged.mkdir()
            (target / "old.json").write_text("old")
            (staged / "new.json").write_text("new")
            recapture.atomic_replace_dir(staged, target)
            self.assertEqual(sorted(path.name for path in target.iterdir()), ["new.json"])
            self.assertFalse(any("backup" in path.name for path in temporary.iterdir()))
        finally:
            shutil.rmtree(temporary)


if __name__ == "__main__":
    unittest.main()
