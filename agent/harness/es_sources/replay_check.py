#!/usr/bin/env python3
"""Source-derived truth for one selected session: engine replay + role-aware fidelity.

Breaks the circularity the adapter review found: completion and non-completion labels are
read from the EXECUTING game source (``ReplayDriver`` over ``arcengine``), not from the
recording's own metadata, and compared per step against the recording. Fidelity is a full
role-aware comparison of EVERY frame — settled, solved-terminal, and next-level frames must
be byte-equal always; intermediate frames may diverge only under the accepted vc33
settled-frame erratum. All divergences are collected, not just the first.

Reuses the audited GI-2 estate per the frozen reuse contract: ``gi2_replay.ReplayDriver``,
``iter_recorded_actions``, frame normalization, and ``gi2_traces.frame_roles``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from gi2_replay import (  # noqa: E402
    ReplayDriver,
    _plain_frames,
    iter_recorded_actions,
)
from gi2_traces import CORPUS, frame_roles  # noqa: E402


def replay_session(env: str, guid: str) -> dict[str, Any]:
    """Replay one recording through the frozen game source and compare everything."""
    path = CORPUS / env / f"{guid}.recording.jsonl"
    driver = ReplayDriver(env)
    game = driver.new_game()

    previous_engine = 0
    previous_recorded = 0
    engine_completions: list[dict[str, int]] = []
    recorded_completions: list[dict[str, int]] = []
    label_mismatches: list[dict[str, int]] = []
    divergences: list[dict[str, Any]] = []
    structural: list[dict[str, int]] = []
    engine_verified_non_completions = 0

    for recorded in iter_recorded_actions(path):
        replayed = driver.perform(game, recorded)

        engine_levels = int(replayed.levels_completed or 0)
        engine_increment = engine_levels - previous_engine
        recorded_increment = recorded.levels_completed - previous_recorded
        if engine_levels != recorded.levels_completed or (engine_increment > 0) != (
            recorded_increment > 0
        ):
            label_mismatches.append(
                {
                    "step": recorded.step,
                    "engine_levels": engine_levels,
                    "recorded_levels": recorded.levels_completed,
                }
            )
        if engine_increment > 0:
            engine_completions.append(
                {"step": recorded.step, "completed_level": engine_levels}
            )
        elif engine_levels == recorded.levels_completed:
            engine_verified_non_completions += 1
        if recorded_increment > 0:
            recorded_completions.append(
                {"step": recorded.step, "completed_level": recorded.levels_completed}
            )

        roles = frame_roles(
            state=recorded.state,
            n_frames=len(recorded.frames),
            completion_increment=recorded_increment,
        )
        got = _plain_frames(replayed.frame or [])
        if len(got) != len(recorded.frames):
            structural.append(
                {
                    "step": recorded.step,
                    "replayed_frames": len(got),
                    "recorded_frames": len(recorded.frames),
                }
            )
        else:
            for frame_index, (replayed_frame, recorded_frame) in enumerate(
                zip(got, recorded.frames)
            ):
                if replayed_frame != recorded_frame:
                    changed = sum(
                        left != right
                        for left_row, right_row in zip(replayed_frame, recorded_frame)
                        for left, right in zip(left_row, right_row)
                    )
                    divergences.append(
                        {
                            "step": recorded.step,
                            "frame_index": frame_index,
                            "role": roles[frame_index],
                            "changed_cells": changed,
                        }
                    )

        previous_engine = engine_levels
        previous_recorded = recorded.levels_completed

    return {
        "env": env,
        "guid": guid,
        "engine_completions": engine_completions,
        "recorded_completions": recorded_completions,
        "label_mismatches": label_mismatches,
        "engine_verified_non_completions": engine_verified_non_completions,
        "divergences": divergences,
        "structural": structural,
    }
