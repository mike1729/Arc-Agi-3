"""Tests for the GI-1 implementation-freeze manifest."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_freeze as F  # noqa: E402


def _frozen_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "repo"
    path = root / "agent/harness/frozen.py"
    path.parent.mkdir(parents=True)
    path.write_text("VALUE = 1\n")
    index = root / "logs/index.json"
    index.parent.mkdir(parents=True)
    index.write_text('{"records":[]}\n')
    (root / "logs/gi1_game_draw.json").write_text(
        '{"iteration":["aa11"],"one_shot":[]}\n'
    )
    monkeypatch.setattr(F, "FROZEN_FILES", ("agent/harness/frozen.py",))
    monkeypatch.setattr(F, "INDEX_CACHE", index)
    monkeypatch.setattr(F, "CURRENT_STATUS", F.FROZEN_GOLD_STATUS)
    monkeypatch.setattr(F, "schema_fingerprint", lambda: "schema")
    monkeypatch.setattr(F, "SPEC", {"k": 3})
    monkeypatch.setattr(F, "validate_index_artifact", lambda artifact, games: [])
    return root


def test_build_refuses_to_freeze_development_gold(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "CURRENT_STATUS", "dev_unfrozen")
    with pytest.raises(ValueError, match="predicate gold status"):
        F.build_manifest(tmp_path)


def test_build_refuses_a_missing_frozen_input(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "CURRENT_STATUS", F.FROZEN_GOLD_STATUS)
    monkeypatch.setattr(F, "FROZEN_FILES", ("missing.py",))
    with pytest.raises(ValueError, match="frozen input missing"):
        F.build_manifest(tmp_path)


def test_build_refuses_a_missing_retrieval_index(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    F.INDEX_CACHE.unlink()
    with pytest.raises(ValueError, match="retrieval index first"):
        F.build_manifest(root)


def test_build_refuses_a_semantically_invalid_retrieval_index(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    monkeypatch.setattr(
        F, "validate_index_artifact", lambda artifact, games: ["spec drift"]
    )
    with pytest.raises(ValueError, match="not frozen-compatible.*spec drift"):
        F.build_manifest(root)


def test_manifest_covers_files_schema_retrieval_generation_and_models(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    manifest = F.build_manifest(root)
    contract = manifest["contract"]
    assert set(contract) == {
        "files",
        "retrieval_index",
        "schema_fingerprint",
        "retrieval_spec",
        "measured_generation",
        "measurement_model_basename",
        "development_model_basename",
    }
    assert contract["schema_fingerprint"] == "schema"
    assert contract["retrieval_spec"] == {"k": 3}
    assert contract["measured_generation"]["temperature"] == 0
    assert contract["measurement_model_basename"] == "Qwen3.6-27B-8bit"
    assert len(contract["files"]["agent/harness/frozen.py"]) == 64
    assert len(manifest["contract_fingerprint"]) == 64


def test_verify_accepts_an_exact_manifest(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    output = tmp_path / "freeze.json"
    output.write_text(json.dumps(F.build_manifest(root)))
    assert F.verify_manifest(output, root=root) == []


def test_verify_reports_file_drift(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    output = tmp_path / "freeze.json"
    output.write_text(json.dumps(F.build_manifest(root)))
    (root / "agent/harness/frozen.py").write_text("VALUE = 2\n")
    problems = F.verify_manifest(output, root=root)
    assert "frozen file drift: agent/harness/frozen.py" in problems


def test_verify_reports_contract_drift_even_if_file_table_is_unchanged(
    tmp_path, monkeypatch
):
    root = _frozen_root(tmp_path, monkeypatch)
    artifact = F.build_manifest(root)
    artifact["contract"]["retrieval_spec"] = {"k": 99}
    output = tmp_path / "freeze.json"
    output.write_text(json.dumps(artifact))
    problems = F.verify_manifest(output, root=root)
    assert "contract drift: retrieval_spec" in problems
    assert any(problem.startswith("contract_fingerprint:") for problem in problems)


def test_verify_reports_a_non_object_contract_without_raising(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    artifact = F.build_manifest(root)
    artifact["contract"] = None
    output = tmp_path / "freeze.json"
    output.write_text(json.dumps(artifact))
    assert "contract: expected an object" in F.verify_manifest(output, root=root)


def test_verify_names_the_exact_top_level_field_that_drifted(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    artifact = F.build_manifest(root)
    artifact["status"] = "draft"
    output = tmp_path / "freeze.json"
    output.write_text(json.dumps(artifact))
    problems = F.verify_manifest(output, root=root)
    assert [problem for problem in problems if problem.startswith("status:")] == [
        "status: artifact 'draft' != current 'frozen'"
    ]


@pytest.mark.parametrize("content", ["not json", "[]"])
def test_verify_returns_problems_instead_of_raising(tmp_path, monkeypatch, content):
    root = _frozen_root(tmp_path, monkeypatch)
    output = tmp_path / "freeze.json"
    output.write_text(content)
    problems = F.verify_manifest(output, root=root)
    assert problems


def test_require_frozen_returns_the_verified_artifact(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    artifact = F.build_manifest(root)
    output = tmp_path / "freeze.json"
    output.write_text(json.dumps(artifact))
    original = F.verify_manifest
    monkeypatch.setattr(F, "verify_manifest", lambda path: [])
    assert F.require_frozen(output) == artifact
    monkeypatch.setattr(F, "verify_manifest", original)


def test_require_frozen_refuses_any_problem(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "verify_manifest", lambda path: ["drift"])
    with pytest.raises(ValueError, match="not frozen.*drift"):
        F.require_frozen(tmp_path / "freeze.json")


def test_build_manifest_does_not_alias_the_mutable_retrieval_spec(tmp_path, monkeypatch):
    root = _frozen_root(tmp_path, monkeypatch)
    manifest = F.build_manifest(root)
    snapshot = copy.deepcopy(manifest)
    F.SPEC["k"] = 7
    assert manifest == snapshot
