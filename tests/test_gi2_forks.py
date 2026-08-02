import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from gi2_forks import (  # noqa: E402
    _candidate_actions,
    compact_v2,
    decode_grid,
    encode_grid,
)


def test_grid_codec_round_trip():
    grid = [[(row + col) % 16 for col in range(64)] for row in range(64)]
    assert decode_grid(encode_grid(grid)) == grid


def test_grid_codec_rejects_wrong_dimensions():
    with pytest.raises(ValueError, match="expected 4096"):
        decode_grid(encode_grid([[1]]))


def test_candidate_actions_excludes_recorded_action():
    recorded = SimpleNamespace(action_id=6, action_data={"x": 2, "y": 1})
    candidates = _candidate_actions((1, 6), [(1, 2), (3, 4)], recorded)
    assert {"action_id": 1, "action_data": {}} in candidates
    assert {"action_id": 6, "action_data": {"x": 2, "y": 1}} not in candidates
    assert {"action_id": 6, "action_data": {"x": 4, "y": 3}} in candidates


def test_compact_v2_preserves_grid():
    grid = [[0] * 64 for _ in range(64)]
    v2 = {
        "format_version": 2,
        "games": [
            {
                "sessions": [
                    {
                        "completions": [
                            {
                                "pre_grid_rle": [[0, 4096]],
                                "forks": [{"terminal_grid_rle": [[0, 4096]]}],
                            }
                        ]
                    }
                ]
            }
        ],
    }
    compacted = compact_v2(v2)
    row = compacted["games"][0]["sessions"][0]["completions"][0]
    assert compacted["format_version"] == 3
    assert decode_grid(row["pre_grid_rle"]) == grid
    assert decode_grid(row["forks"][0]["terminal_grid_rle"]) == grid
