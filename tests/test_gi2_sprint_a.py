import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from gi2_sprint_a import FORKS, GOLD, GROUNDING, OUTPUT, build  # noqa: E402

requires_artifacts = pytest.mark.skipif(
    not all(path.exists() for path in (FORKS, GOLD, GROUNDING, OUTPUT)),
    reason="local measured GI-2 artifacts are absent",
)


@requires_artifacts
def test_measured_sprint_a_artifact_rebuilds_and_stops_at_failed_gate():
    measured = json.loads(OUTPUT.read_text())
    assert build() == measured
    assert measured["status"] == "sprint_a_halted_at_representability"
    assert measured["gates"]["representability"] == {
        "passed": False,
        "games": 4,
        "required": 5,
    }
    assert measured["gates"]["trajectory_identifiability"]["passed"] is None
