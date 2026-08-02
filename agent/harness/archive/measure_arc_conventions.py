"""Measure the ARC-AGI-3 conventions the S2 generators must match. Reproducible evidence for the
S1 close-out's "S2 inheritance" section, which previously recorded prose only.

Emits logs/s2_arc_conventions.json.

Run:  .venv/bin/python agent/harness/measure_arc_conventions.py
"""
from __future__ import annotations

import collections
import json
import os
from pathlib import Path

import arc_agi
import arcengine

REPO = Path(__file__).resolve().parents[2]
ENV_DIR = REPO / "data" / "environment_files"


def main() -> None:
    arcade = arc_agi.Arcade(operation_mode=arc_agi.OperationMode.OFFLINE, environments_dir=str(ENV_DIR))
    vals, shapes, frames_at_reset = set(), collections.Counter(), collections.Counter()
    acts, per_game, levels = collections.Counter(), {}, []

    for g in sorted(os.listdir(ENV_DIR)):
        d = ENV_DIR / g
        if not d.is_dir():
            continue
        h = os.listdir(d)[0]
        meta = json.loads((d / h / "metadata.json").read_text())
        gid, bl = meta["game_id"], meta.get("baseline_actions") or []
        levels.append(len(bl))
        try:
            env = arcade.make(gid, seed=0)
            f = env.reset()
        except Exception as exc:  # noqa: BLE001
            per_game[gid] = {"error": repr(exc)}
            continue
        fr = getattr(f, "frame", None) or []
        frames_at_reset[len(fr)] += 1
        for layer in fr:
            a = layer.tolist() if hasattr(layer, "tolist") else layer
            shapes[(len(a), len(a[0]) if a else 0)] += 1
            for row in a:
                vals.update(row)
        a_ids = [int(x) for x in (f.available_actions or [])]
        for x in a_ids:
            acts[x] += 1
        per_game[gid] = {"levels": len(bl), "baselines": bl,
                         "frames_at_reset": len(fr), "actions_at_reset": a_ids,
                         "tags": meta.get("tags")}

    # Does the frame count vary WITHIN an episode, and does the ACTION SET change per state?
    # Both are claimed in the close-out; recording only the reset state could not evidence either.
    seq, avail_seq = [], []
    env = arcade.make("ls20-9607627b", seed=0)
    f = env.reset()
    seq.append(len(getattr(f, "frame", []) or []))
    avail_seq.append(sorted(int(x) for x in (f.available_actions or [])))
    for _ in range(8):
        f = env.step(arcengine.GameAction.ACTION1)
        seq.append(len(getattr(f, "frame", []) or []))
        avail_seq.append(sorted(int(x) for x in (f.available_actions or [])))

    out = {
        "games": len(per_game),
        "grid_shapes_at_reset": {f"{k[0]}x{k[1]}": v for k, v in shapes.items()},
        "cell_values": {"min": min(vals), "max": max(vals), "distinct": len(vals), "observed": sorted(vals)},
        "frames_per_observation_at_reset": dict(frames_at_reset),
        "frame_count_sequence_ls20_first_8_steps": seq,
        "available_actions_sequence_ls20_first_8_steps": avail_seq,
        "availability_varies_within_episode": len({tuple(a) for a in avail_seq}) > 1,
        "levels_per_game": dict(collections.Counter(levels)),
        "action_ids_at_reset_counts": dict(sorted(acts.items())),
        "per_game": per_game,
    }
    (REPO / "logs" / "s2_arc_conventions.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "per_game"}, indent=2))
    print(f"\nwrote {REPO/'logs'/'s2_arc_conventions.json'}")


if __name__ == "__main__":
    main()
