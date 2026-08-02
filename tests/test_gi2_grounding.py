import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from gi2_grounding import compact_legacy_document  # noqa: E402


def test_compact_legacy_registry_preserves_counts_and_is_idempotent():
    document = {
        "games": [
            {
                "sessions": [
                    {
                        "completion_states": [
                            {
                                "observable_registry": [
                                    {
                                        "id": "o1",
                                        "kind": "atomic",
                                        "colors": [2],
                                        "shapes": ["shape"],
                                        "pixels": 3,
                                        "bbox": [0, 0, 1, 1],
                                        "role": "static",
                                    },
                                    {
                                        "id": "g:o1+o2",
                                        "kind": "group",
                                        "members": ["o1", "o2"],
                                    },
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    compacted = compact_legacy_document(document)
    registry = compacted["games"][0]["sessions"][0]["completion_states"][0][
        "observable_registry"
    ]
    assert registry["atomic_handles"] == 1
    assert registry["group_handles"] == 1
    assert len(registry["registry_sha256"]) == 64
    assert compact_legacy_document(compacted) == compacted
