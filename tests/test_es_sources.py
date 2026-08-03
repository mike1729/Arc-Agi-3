import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from es_sources import (  # noqa: E402
    FROZEN_GAMES,
    GameAdapter,
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
    # the settled-frame erratum belongs to vc33 alone
    assert adapters["vc33"].settled_frame_erratum is True
    assert all(
        not adapters[env].settled_frame_erratum for env in FROZEN_GAMES if env != "vc33"
    )


def test_settled_frame_assertion_byte_exact_passes():
    result = settled_frame_assertion(
        "dc22",
        {"frame_fidelity": True, "first_frame_divergence": None, "guid": "g"},
        erratum=False,
        first_divergence_intermediate=None,
    )
    assert result["settled_frame_ok"] is True
    assert result["basis"] == "byte_exact_all_frames"


def test_settled_frame_assertion_divergence_without_erratum_fails_closed():
    with pytest.raises(ValueError, match="without the settled-frame erratum"):
        settled_frame_assertion(
            "dc22",
            {
                "frame_fidelity": False,
                "first_frame_divergence": {"step": 5},
                "guid": "g",
            },
            erratum=False,
            first_divergence_intermediate=True,
        )


def test_settled_frame_assertion_erratum_requires_verified_intermediate():
    with pytest.raises(ValueError, match="not on an intermediate frame"):
        settled_frame_assertion(
            "vc33",
            {
                "frame_fidelity": False,
                "first_frame_divergence": {"step": 5},
                "guid": "g",
            },
            erratum=True,
            first_divergence_intermediate=False,
        )
    result = settled_frame_assertion(
        "vc33",
        {
            "frame_fidelity": False,
            "first_frame_divergence": {"step": 5, "detail": {"frame_index": 2}},
            "guid": "g",
        },
        erratum=True,
        first_divergence_intermediate=True,
    )
    assert result["settled_frame_ok"] is True
    assert result["basis"] == "accepted_2026-07-30_settled_frame_erratum"
    assert result["first_divergence_verified_intermediate"] is True


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


def test_write_gold_separates_custody_and_pins_sealed_digest(tmp_path):
    sc_path = tmp_path / "sc.jsonl"
    sealed_path = tmp_path / "r.sealed"
    digests = write_gold(
        _records(), {"input.json": "abc"}, sc_path=sc_path, sealed_path=sealed_path
    )

    sc_header, sc_rows = read_jsonl(sc_path)
    sealed_header, sealed_rows = read_jsonl(sealed_path)

    assert all(
        not (row["record"] == "session" and row["role"] == "R") for row in sc_rows
    )
    assert [row["role"] for row in sealed_rows] == ["R"]
    # the SC side pins the sealed file by digest and never carries its rows
    import hashlib

    assert sc_header["r_sealed_sha256"] == hashlib.sha256(
        sealed_path.read_bytes()
    ).hexdigest()
    assert sc_header["r_sealed_sha256"] == digests["r_sealed_sha256"]
    assert sc_header["rows_fingerprint"] == rows_fingerprint(sc_rows)
    assert sealed_header["rows_fingerprint"] == rows_fingerprint(sealed_rows)
    assert sc_header["r_row_count"] == 1
    # sealed file is access-restricted in the working tree
    assert (sealed_path.stat().st_mode & 0o777) == 0o600


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
