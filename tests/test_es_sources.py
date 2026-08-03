import hashlib
import json
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from es_sources import (  # noqa: E402
    FROZEN_GAMES,
    GameAdapter,
    authenticate_recording,
    load_all_adapters,
    read_jsonl,
    rows_fingerprint,
    settled_frame_assertion,
    split_by_custody,
    write_gold,
)


def test_registry_declares_exactly_the_frozen_corpus():
    adapters = load_all_adapters()
    assert sorted(adapters) == sorted(FROZEN_GAMES)
    for env, adapter in adapters.items():
        assert isinstance(adapter, GameAdapter)
        assert adapter.env == env
        assert adapter.adapter_version == 1
    assert adapters["vc33"].settled_frame_erratum is True
    assert all(
        not adapters[env].settled_frame_erratum for env in FROZEN_GAMES if env != "vc33"
    )


def _replay_result(**overrides):
    base = {
        "env": "dc22",
        "guid": "g",
        "engine_completions": [{"step": 5, "completed_level": 1}],
        "recorded_completions": [{"step": 5, "completed_level": 1}],
        "label_mismatches": [],
        "engine_verified_non_completions": 40,
        "divergences": [],
        "structural": [],
    }
    base.update(overrides)
    return base


def test_settled_frame_assertion_byte_exact_recomputed_passes():
    result = settled_frame_assertion("dc22", "g", _replay_result(), erratum=False)
    assert result["settled_frame_ok"] is True
    assert result["basis"] == "byte_exact_all_frames_recomputed"
    assert result["engine_verified_non_completions"] == 40


def test_settled_frame_assertion_rejects_label_mismatches():
    with pytest.raises(ValueError, match="not source-reproduced"):
        settled_frame_assertion(
            "dc22",
            "g",
            _replay_result(
                label_mismatches=[{"step": 9, "engine_levels": 1, "recorded_levels": 2}]
            ),
            erratum=True,
        )


def test_settled_frame_assertion_rejects_completion_event_disagreement():
    with pytest.raises(ValueError, match="differ from recorded completion events"):
        settled_frame_assertion(
            "dc22",
            "g",
            _replay_result(engine_completions=[{"step": 6, "completed_level": 1}]),
            erratum=True,
        )


def test_settled_frame_assertion_rejects_structural_divergence_even_with_erratum():
    with pytest.raises(ValueError, match="structural divergence"):
        settled_frame_assertion(
            "vc33",
            "g",
            _replay_result(
                structural=[{"step": 7, "replayed_frames": 3, "recorded_frames": 4}]
            ),
            erratum=True,
        )


def test_settled_frame_assertion_divergence_without_erratum_fails_closed():
    with pytest.raises(ValueError, match="without the settled-frame erratum"):
        settled_frame_assertion(
            "dc22",
            "g",
            _replay_result(
                divergences=[
                    {"step": 8, "frame_index": 2, "role": "intermediate", "changed_cells": 2}
                ]
            ),
            erratum=False,
        )


def test_settled_frame_assertion_rejects_any_non_intermediate_divergence():
    # the review's point: ONE settled divergence anywhere fails, regardless of how many
    # intermediate divergences preceded it
    divergences = [
        {"step": 8, "frame_index": 2, "role": "intermediate", "changed_cells": 2},
        {"step": 90, "frame_index": 5, "role": "settled", "changed_cells": 1},
    ]
    with pytest.raises(ValueError, match="non-intermediate"):
        settled_frame_assertion(
            "vc33", "g", _replay_result(divergences=divergences), erratum=True
        )


def test_settled_frame_assertion_intermediate_only_with_erratum_passes():
    divergences = [
        {"step": 8, "frame_index": 2, "role": "intermediate", "changed_cells": 2},
        {"step": 8, "frame_index": 3, "role": "intermediate", "changed_cells": 4},
        {"step": 12, "frame_index": 1, "role": "intermediate", "changed_cells": 2},
    ]
    result = settled_frame_assertion(
        "vc33", "g", _replay_result(divergences=divergences), erratum=True
    )
    assert result["settled_frame_ok"] is True
    assert result["basis"] == "accepted_2026-07-30_settled_frame_erratum_recomputed_all_frames"
    assert result["divergence_count"] == 3
    assert result["divergent_steps"] == [8, 12]
    assert result["all_divergences_intermediate"] is True


def test_authenticate_recording_hashes_the_actual_bytes(tmp_path):
    path = tmp_path / "session.recording.jsonl"
    path.write_text('{"data": {}}\n')
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    assert (
        authenticate_recording(
            "dc22", "g", path, {"fidelity-artifact": current, "es_inventory": current}
        )
        == current
    )
    with pytest.raises(ValueError, match="es_inventory pin"):
        authenticate_recording(
            "dc22", "g", path, {"fidelity-artifact": current, "es_inventory": "0" * 64}
        )


def _records():
    game = {"record": "game", "env": "dc22", "adapter_version": 1}
    sessions = [
        {"record": "session", "env": "dc22", "guid": f"g{i}", "role": role}
        for i, role in enumerate(["S", "C", "R"])
    ]
    return [game, *sessions]


def test_split_by_custody_routes_r_sessions_only():
    sc_rows, r_rows = split_by_custody(_records())
    assert [row["record"] for row in sc_rows] == ["game", "session", "session"]
    assert all(row["role"] != "R" for row in sc_rows if row["record"] == "session")
    assert [row["role"] for row in r_rows] == ["R"]


def test_write_gold_encrypts_r_and_withholds_the_key_from_disk(tmp_path):
    sc_path = tmp_path / "sc.jsonl"
    sealed_path = tmp_path / "r.sealed"
    key = Fernet.generate_key()
    digests = write_gold(
        _records(), {"input.json": "abc"}, sc_path=sc_path, sealed_path=sealed_path, key=key
    )

    sc_header, sc_rows = read_jsonl(sc_path)
    assert all(
        not (row["record"] == "session" and row["role"] == "R") for row in sc_rows
    )

    sealed_bytes = sealed_path.read_bytes()
    with pytest.raises((json.JSONDecodeError, UnicodeDecodeError)):
        json.loads(sealed_bytes.split(b"\n", 1)[0])

    plaintext = Fernet(key).decrypt(sealed_bytes).decode()
    r_rows = [json.loads(line) for line in plaintext.splitlines()]
    assert [row["role"] for row in r_rows] == ["R"]

    assert sc_header["r_key_sha256"] == hashlib.sha256(key).hexdigest()
    assert sc_header["r_plaintext_rows_fingerprint"] == rows_fingerprint(r_rows)
    assert sc_header["r_sealed_sha256"] == hashlib.sha256(sealed_bytes).hexdigest()
    assert sc_header["rows_fingerprint"] == rows_fingerprint(sc_rows)
    assert sc_header["r_row_count"] == 1
    assert digests["r_key"] == key
    assert (sealed_path.stat().st_mode & 0o777) == 0o600

    # the custody key must never be persisted by the writer
    for written in tmp_path.rglob("*"):
        if written.is_file():
            assert key not in written.read_bytes()


def test_write_gold_refuses_an_empty_r_side(tmp_path):
    records = [row for row in _records() if row.get("role") != "R"]
    with pytest.raises(ValueError, match="no R rows"):
        write_gold(
            records,
            {},
            sc_path=tmp_path / "sc.jsonl",
            sealed_path=tmp_path / "r.sealed",
        )


def test_read_jsonl_rejects_headerless_files(tmp_path):
    path = tmp_path / "x.jsonl"
    path.write_text(json.dumps({"record": "session"}) + "\n")
    with pytest.raises(ValueError, match="not a header"):
        read_jsonl(path)


from es_sources.state_access import (  # noqa: E402
    classify_fork_response,
    enumerate_candidates,
    grid_delta,
    mechanical_relations,
)


class _FakeResponse:
    def __init__(self, levels, state="NOT_FINISHED", full_reset=False):
        self.levels_completed = levels
        self.state = state
        self.full_reset = full_reset


def test_classify_fork_response_labels_and_continuation():
    completed = classify_fork_response(_FakeResponse(3), previous_levels=2)
    assert completed["label"] == "complete"
    assert completed["sequential_continuable"] is False  # level change ends the branch

    plain = classify_fork_response(_FakeResponse(2), previous_levels=2)
    assert plain["label"] == "non_complete"
    assert plain["sequential_continuable"] is True

    terminal = classify_fork_response(_FakeResponse(2, state="GAME_OVER"), 2)
    assert terminal["label"] == "non_complete"
    assert terminal["terminal"] is True
    assert terminal["sequential_continuable"] is False

    reset = classify_fork_response(_FakeResponse(2, full_reset=True), 2)
    assert reset["sequential_continuable"] is False


def test_enumerate_candidates_excludes_reset_and_expands_mouse():
    candidates = enumerate_candidates((0, 1, 6), [(2, 3), (5, 5)])
    assert {"action_id": 1, "action_data": {}} in candidates
    assert {"action_id": 6, "action_data": {"x": 3, "y": 2}} in candidates
    assert {"action_id": 6, "action_data": {"x": 5, "y": 5}} in candidates
    assert all(candidate["action_id"] != 0 for candidate in candidates)
    assert len(candidates) == 3


def test_grid_delta_is_row_major_and_exact():
    before = [[0, 1], [2, 3]]
    after = [[0, 9], [2, 8]]
    assert grid_delta(before, after) == [(0, 1), (1, 1)]
    assert grid_delta(before, before) == []


def test_mechanical_relations_from_masks():
    objects = [
        {"identity": "a", "cells": [(0, 0), (0, 1), (1, 0), (1, 1)]},
        {"identity": "b", "cells": [(0, 1)]},          # inside a
        {"identity": "c", "cells": [(5, 0), (5, 1)]},  # col-aligned with a, disjoint rows
    ]
    relations = {(r["a"], r["b"]): r for r in mechanical_relations(objects)}

    ab = relations[("a", "b")]
    assert ab["mask_overlap"] and ab["a_contains_b"] and not ab["b_contains_a"]

    ac = relations[("a", "c")]
    assert not ac["mask_overlap"] and not ac["bbox_overlap"]
    assert ac["col_aligned"] and not ac["row_aligned"]
