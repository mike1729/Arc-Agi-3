"""Tests for the GI-2 A0 replay-environment freeze."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))
import gi2_replay_freeze as F  # noqa: E402

requires_corpus = pytest.mark.skipif(
    not F.OUTPUT.exists() or not F.CORPUS.exists(),
    reason="A0 freeze or human corpus absent",
)


def test_seed_contract_detects_only_an_explicit_seed_parameter(tmp_path):
    seeded = tmp_path / "seeded.py"
    seeded.write_text(
        "class ARCBaseGame: pass\n"
        "class Game(ARCBaseGame):\n"
        "    def __init__(self, seed=0): pass\n"
    )
    plain = tmp_path / "plain.py"
    plain.write_text(
        "class ARCBaseGame: pass\n"
        "class Game(ARCBaseGame):\n"
        "    def __init__(self): pass\n"
    )
    assert F._class_seed_contract(seeded) == ("Game", True)
    assert F._class_seed_contract(plain) == ("Game", False)


def test_seed_contract_rejects_ambiguous_game_classes(tmp_path):
    source = tmp_path / "ambiguous.py"
    source.write_text(
        "class ARCBaseGame: pass\n"
        "class One(ARCBaseGame): pass\n"
        "class Two(ARCBaseGame): pass\n"
    )
    with pytest.raises(ValueError, match="exactly one"):
        F._class_seed_contract(source)


def test_seed_contract_handles_inherited_constructor(tmp_path):
    source = tmp_path / "inherited.py"
    source.write_text("class ARCBaseGame: pass\nclass Game(ARCBaseGame): pass\n")
    assert F._class_seed_contract(source) == ("Game", False)


def test_action_stream_digest_ignores_recording_game_id_but_keeps_coordinates(tmp_path):
    def row(game_id, x):
        return json.dumps(
            {
                "data": {
                    "frame": [],
                    "action_input": {
                        "id": "ACTION6",
                        "data": {"game_id": game_id, "x": x, "y": 3},
                    },
                }
            }
        )

    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    third = tmp_path / "third.jsonl"
    first.write_text(row("instance-a", 2) + "\n")
    second.write_text(row("instance-b", 2) + "\n")
    third.write_text(row("instance-a", 4) + "\n")
    assert F._action_stream(first) == F._action_stream(second)
    assert F._action_stream(first)[0] != F._action_stream(third)[0]


def test_action_stream_skips_summary_tail(tmp_path):
    recording = tmp_path / "recording.jsonl"
    recording.write_text(
        json.dumps(
            {
                "data": {
                    "frame": [],
                    "action_input": {"id": 0, "data": {}},
                }
            }
        )
        + "\n"
        + json.dumps({"data": {"won": 1}})
        + "\n"
    )
    _, rows, resets = F._action_stream(recording)
    assert (rows, resets) == (1, 1)


def test_build_freeze_requires_one_version_with_source_and_metadata(tmp_path, monkeypatch):
    draw = tmp_path / "draw.json"
    sessions = tmp_path / "sessions.json"
    draw.write_text(json.dumps({"iteration": ["aa11"], "reserved": []}))
    sessions.write_text(json.dumps({"sessions": []}))
    environments = tmp_path / "environments"
    (environments / "aa11").mkdir(parents=True)
    monkeypatch.setattr(F, "DRAW", draw)
    monkeypatch.setattr(F, "SESSIONS", sessions)
    monkeypatch.setattr(F, "ENVIRONMENTS", environments)
    with pytest.raises(ValueError, match="exactly one environment version"):
        F.build_freeze()
    (environments / "aa11" / "v1").mkdir()
    with pytest.raises(ValueError, match="source or metadata missing"):
        F.build_freeze()


def test_verify_freeze_rejects_non_object():
    assert F.verify_freeze(None) == ["artifact: expected an object"]


def _minimal_freeze(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "ROOT", tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    monkeypatch.setattr(F, "CORPUS", corpus)
    inputs = {}
    for name in ("draw", "sessions", "frame"):
        path = tmp_path / f"{name}.json"
        path.write_text("{}")
        inputs[name] = path
    monkeypatch.setattr(F, "DRAW", inputs["draw"])
    monkeypatch.setattr(F, "SESSIONS", inputs["sessions"])
    monkeypatch.setattr(F, "FRAME_VALIDATION", inputs["frame"])
    monkeypatch.setattr(
        F,
        "_distribution_record",
        lambda name: {"name": name, "version": F.EXPECTED_DISTRIBUTIONS[name]},
    )
    games = []
    for env_index in range(6):
        env = f"g{env_index}"
        env_dir = corpus / env
        env_dir.mkdir()
        source = tmp_path / f"{env}.py"
        metadata = tmp_path / f"{env}.json"
        source.write_text("pass")
        metadata.write_text("{}")
        streams = []
        for stream_index in range(3):
            guid = f"s{stream_index}"
            recording = env_dir / f"{guid}.recording.jsonl"
            recording.write_text(
                json.dumps(
                    {
                        "data": {
                            "frame": [],
                            "action_input": {"id": 0, "data": {}},
                        }
                    }
                )
                + "\n"
            )
            digest, rows, resets = F._action_stream(recording)
            streams.append(
                {
                    "guid": guid,
                    "actions_sha256": digest,
                    "action_rows": rows,
                    "reset_actions": resets,
                }
            )
        games.append(
            {
                "env": env,
                "source": source.name,
                "source_sha256": F._sha256(source),
                "metadata": metadata.name,
                "metadata_sha256": F._sha256(metadata),
                "action_streams": streams,
            }
        )
    return {
        "format_version": F.FORMAT_VERSION,
        "status": "a0_frozen",
        "local_replay": {
            "requested_seed": F.REQUESTED_SEED,
            "only_reset_levels": None,
        },
        "inputs": {
            "draw_sha256": F._sha256(inputs["draw"]),
            "sessions_sha256": F._sha256(inputs["sessions"]),
            "frame_validation_sha256": F._sha256(inputs["frame"]),
        },
        "distributions": {
            name: F._distribution_record(name) for name in F.EXPECTED_DISTRIBUTIONS
        },
        "games": games,
    }


@pytest.mark.parametrize(
    "mutation,fragment",
    [
        (lambda d: d["games"].__setitem__(0, None), "invalid row"),
        (lambda d: d["games"][0].__setitem__("action_streams", None), "three action streams"),
        (lambda d: d["games"][0]["action_streams"].__setitem__(0, None), "invalid action stream"),
        (
            lambda d: d["games"][0]["action_streams"][0].__setitem__("guid", "missing"),
            "recording missing",
        ),
    ],
)
def test_verify_freeze_rejects_malformed_nested_rows(
    tmp_path, monkeypatch, mutation, fragment
):
    document = _minimal_freeze(tmp_path, monkeypatch)
    mutation(document)
    assert any(fragment in problem for problem in F.verify_freeze(document))


@requires_corpus
def test_measured_replay_freeze_verifies_and_pins_versions_and_seed_behavior():
    document = json.loads(F.OUTPUT.read_text())
    assert F.verify_freeze(document) == []
    assert document["distributions"]["arcengine"]["version"] == "0.9.3"
    assert document["distributions"]["arc-agi"]["version"] == "0.9.9"
    assert len(document["games"]) == 6
    assert all(not game["seed"]["constructor_accepts_seed"] for game in document["games"])
    assert sum(len(game["action_streams"]) for game in document["games"]) == 18


@requires_corpus
def test_verify_freeze_rejects_a_tampered_action_digest():
    document = json.loads(F.OUTPUT.read_text())
    document["games"][0]["action_streams"][0]["actions_sha256"] = "0" * 64
    assert any("action stream drift" in problem for problem in F.verify_freeze(document))
