#!/usr/bin/env python3
"""No-model regression tests for the closure-grade Slice-4 vision probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_probe_vlm as probe


class CompletionTests(unittest.TestCase):
    def test_finish_reason_is_authoritative(self) -> None:
        self.assertEqual(
            probe.classify_completion("length", 10, 10, True, {"answer": 1}),
            "truncated",
        )
        self.assertEqual(
            probe.classify_completion("stop", 10, 10, True, {"answer": 1}),
            "complete",
        )
        self.assertEqual(
            probe.classify_completion("stop", 3, 10, False, None),
            "unclosed",
        )
        self.assertEqual(
            probe.classify_completion("stop", 3, 10, True, None),
            "no_json",
        )
        self.assertEqual(
            probe.classify_completion(None, 3, 10, True, {}),
            "instrument_error",
        )

    def test_gate_statuses_stay_distinct(self) -> None:
        call = lambda status: {"completeness": status}
        self.assertEqual(probe.classify_gate(True, [call("complete")]), "PASS")
        self.assertEqual(
            probe.classify_gate(False, [call("complete")]), "SEMANTIC_FAIL"
        )
        self.assertEqual(
            probe.classify_gate(False, [call("no_json")]), "PROTOCOL_FAIL"
        )
        self.assertEqual(
            probe.classify_gate(False, [call("truncated")]),
            "INDETERMINATE_BUDGET",
        )

    def test_page_numbers_reject_json_booleans(self) -> None:
        self.assertTrue(probe.is_page_number(1))
        self.assertTrue(probe.is_page_number(16))
        self.assertFalse(probe.is_page_number(True))
        self.assertFalse(probe.is_page_number(False))
        self.assertFalse(probe.is_page_number(0))
        self.assertFalse(probe.is_page_number(17))

    def test_seed_is_tag_stable(self) -> None:
        later = probe.seed_for(4, "later")
        probe.seed_for(4, "inserted")
        self.assertEqual(probe.seed_for(4, "later"), later)
        self.assertNotEqual(probe.seed_for(4, "other"), later)

    def test_cli_value_validators(self) -> None:
        self.assertEqual(probe.stability_count("3"), 3)
        self.assertEqual(probe.uint64_seed(str(2 ** 64 - 1)), 2 ** 64 - 1)
        for function, value in (
            (probe.stability_count, "0"),
            (probe.stability_count, "2"),
            (probe.positive_int, "0"),
            (probe.uint64_seed, "-1"),
            (probe.uint64_seed, str(2 ** 64)),
        ):
            with self.subTest(function=function.__name__, value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    function(value)


class RunLockTests(unittest.TestCase):
    def test_lock_excludes_a_second_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock_path = Path(temporary) / "probe.lock"
            first = probe.acquire_run_lock(lock_path)
            try:
                with self.assertRaisesRegex(RuntimeError, "global run lock"):
                    probe.acquire_run_lock(lock_path)
            finally:
                first.close()
            second = probe.acquire_run_lock(lock_path)
            second.close()


class MainPersistenceTests(unittest.TestCase):
    def test_budget_indeterminacy_persists_partial_state_and_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model"
            model.mkdir()
            output = root / "result.json"
            checkpoint = {
                "checkpoint_sha256": "checkpoint",
                "versions": probe.PINNED_VERSIONS,
                "script_sha": "script",
                "renderer_sha": "renderer",
            }

            def fake_run_gates(vlm, work, run_dir, args, document, persist):
                del vlm, work, run_dir, args
                document["partial_gate"] = {"completed_calls": 1}
                persist()
                raise probe.IndeterminateBudget("g3_binding_a exhausted its budget")

            argv = ["e2_probe_vlm.py", "--out", str(output)]
            with (
                mock.patch.object(probe, "ROOT", root),
                mock.patch.object(probe, "MODEL", model),
                mock.patch.object(probe, "capture_git_state", return_value={}),
                mock.patch.object(probe, "fingerprint", return_value=checkpoint),
                mock.patch.object(probe, "Vlm", return_value=object()),
                mock.patch.object(probe, "run_gates", side_effect=fake_run_gates),
                mock.patch.object(sys, "argv", argv),
            ):
                self.assertEqual(probe.main(), 3)

            artifact = json.loads(output.read_text())
            self.assertEqual(artifact["status"], "indeterminate_budget")
            self.assertEqual(artifact["verdict"], "INDETERMINATE_BUDGET")
            self.assertEqual(artifact["partial_gate"]["completed_calls"], 1)
            manifest = Path(artifact["run_dir"]) / "run_manifest.json"
            self.assertEqual(json.loads(manifest.read_text())["status"], "indeterminate_budget")


class FingerprintTests(unittest.TestCase):
    @staticmethod
    def _git_blob(data: bytes) -> str:
        return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()

    def _make_model(self, root: Path) -> Path:
        model = root / "model"
        model.mkdir()
        shard_name = "model-00001-of-00001.safetensors"
        shard = model / shard_name
        shard.write_bytes(b"weights")
        shard_sha = hashlib.sha256(shard.read_bytes()).hexdigest()

        payloads: dict[str, bytes] = {
            ".gitattributes": b"attrs\n",
            "README.md": b"mlx-community/Qwen3.8-27B-8bit\n",
            "config.json": json.dumps({
                "model_type": probe.EXPECTED_MODEL_TYPE,
                "architectures": [probe.EXPECTED_ARCHITECTURE],
                "quantization": {"group_size": 64, "bits": 8, "mode": "affine"},
                "vision_config": {
                    "patch_size": 16,
                    "spatial_merge_size": 2,
                    "temporal_patch_size": 2,
                },
            }, sort_keys=True).encode(),
            "generation_config.json": b"{}",
            "tokenizer.json": b"{}",
            "vocab.json": b"{}",
            "merges.txt": b"",
            "tokenizer_config.json": b"{}",
            "chat_template.jinja": b"template",
            "preprocessor_config.json": json.dumps({
                "processor_class": "Qwen3VLProcessor",
                "size": {"longest_edge": 16_777_216, "shortest_edge": 65_536},
            }, sort_keys=True).encode(),
            "processor_config.json": b"{}",
            "video_preprocessor_config.json": b"{}",
            "model.safetensors.index.json": json.dumps({
                "weight_map": {"layer": shard_name}
            }, sort_keys=True).encode(),
        }
        for name, data in payloads.items():
            (model / name).write_bytes(data)

        tree_files = {
            name: {"size": len(data), "blob_id": self._git_blob(data)}
            for name, data in payloads.items()
        }
        tree_files[shard_name] = {
            "size": shard.stat().st_size,
            "lfs_sha256": shard_sha,
        }
        tree_dir = model / ".cache/huggingface/trees"
        tree_dir.mkdir(parents=True)
        (tree_dir / f"{probe.EXPECTED_MODEL_REVISION}.json").write_text(
            json.dumps({"files": tree_files})
        )
        metadata_dir = model / ".cache/huggingface/download"
        metadata_dir.mkdir(parents=True)
        (metadata_dir / f"{shard_name}.metadata").write_text(
            f"{probe.EXPECTED_MODEL_REVISION}\n{shard_sha}\n0\n"
        )
        return model

    def test_full_identity_and_same_size_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            model_a = self._make_model(Path(first))
            model_b = self._make_model(Path(second))
            git_state = {"commit": "test", "dirty": False, "status": []}
            fingerprint_a = probe.fingerprint(model_a, git_state=git_state)
            fingerprint_b = probe.fingerprint(model_b, git_state=git_state)
            self.assertEqual(
                fingerprint_a["checkpoint_sha256"],
                fingerprint_b["checkpoint_sha256"],
            )

            shard = model_a / "model-00001-of-00001.safetensors"
            shard.write_bytes(b"WeightS")
            with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
                probe.fingerprint(model_a, git_state=git_state)


class FakeVlm:
    _gate3_answers = {
        "g3_binding_a": {
            "green_board_page": 2,
            "purple_crop_page": 6,
            "orange_marker_page": 9,
            "three_change_diff_page": 13,
            "animation_storyboard_page": 16,
            "animation_frame_index": 23,
            "animation_yellow_row": 37,
            "animation_yellow_col": 11,
        },
        "g3_binding_b": {
            "green_board_page": 7,
            "purple_crop_page": 1,
            "orange_marker_page": 12,
            "three_change_diff_page": 16,
            "animation_storyboard_page": 5,
            "animation_frame_index": 23,
            "animation_yellow_row": 37,
            "animation_yellow_col": 11,
        },
    }

    def ask(self, items, images, *, tag, **kwargs):
        del kwargs
        record = {
            "completeness": "complete",
            "prompt_tokens_match": True,
            "think_chars": 1,
            "image_grid_thw": [[1, 16, 16] for _ in images],
            "visual_tokens": 10_657 if tag.startswith("g3_") else len(images) * 64,
        }
        if tag == "g1_palette" or tag.startswith("g5_"):
            payload = {
                "red_count": 3, "blue_count": 2, "green_count": 4,
                "marked_cell_colour": "purple", "top_row_colour": "yellow",
            }
        elif tag.startswith("g2_"):
            a_id, b_id, same = {
                "g2_same_light": (2, 2, True),
                "g2_same_dark": (3, 3, True),
                "g2_diff_ab": (2, 3, False),
                "g2_diff_ba": (3, 2, False),
            }[tag]
            payload = {
                "a_fill_id": a_id, "b_fill_id": b_id,
                "same_fill_colour": same,
            }
        elif tag in self._gate3_answers:
            if len(images) != probe.MAX_PACKET_IMAGES:
                raise AssertionError(f"Gate 3 image count: {len(images)}")
            if len([item for item in items if item.get("type") == "image"]) != 16:
                raise AssertionError("Gate 3 placeholder count")
            for path in images:
                with Image.open(path) as image:
                    if image.width % 32 or image.height % 32:
                        raise AssertionError(f"unaligned image: {path}")
            payload = self._gate3_answers[tag]
        elif tag.startswith("g4_"):
            payload = {
                "relation": "none" if tag == "g4_blank" else tag.removeprefix("g4_")
            }
        else:
            raise AssertionError(tag)
        return {**record, "payload": payload}


class FixtureTests(unittest.TestCase):
    def test_all_gates_and_counter_permutations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            work = root / "boards"
            work.mkdir()
            args = SimpleNamespace(
                seed=4, max_tokens=4000, packet_max_tokens=8000, stability=3,
            )
            document: dict = {}
            checkpoints = []
            results = probe.run_gates(
                FakeVlm(), work, root, args, document,
                persist=lambda: checkpoints.append(True),
            )
            self.assertTrue(all(results.values()), results)
            self.assertEqual(set(document["gate_statuses"].values()), {"PASS"})
            self.assertEqual(len(list(work.glob("g3_p*.png"))), 16)
            self.assertGreaterEqual(len(checkpoints), 17)
            expected_a = document["gate3_binding"]["a"]["expected"]
            expected_b = document["gate3_binding"]["b"]["expected"]
            self.assertTrue(all(expected_a[key] != expected_b[key] for key in expected_a))
            self.assertIn(16, expected_a.values())
            self.assertIn(16, expected_b.values())


if __name__ == "__main__":
    unittest.main()
