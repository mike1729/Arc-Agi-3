#!/usr/bin/env python3
"""GI-1 canonical evidence packets from human replay recordings.

Implements layer 1 of the three-layer split in notes/design-pivot.md ("Evidence packets"):
the CANONICAL PACKET — condition-independent data, a function of the session prefix up to a
checkpoint only. Rendering (layer 2, baseline) and compilation (layer 3, digest) consume the
Packet API; neither lives here.

WHAT A TIMELINE HOLDS
---------------------
One recording streams into an ordered list of steps, one per action line. Per step we retain:
normalized action id + data, the SETTLED grid (frame[-1] — the operational definition shared
with s2_corpus_census.py, SPEC §5 and §6.6), frame count, levels_completed, available_actions,
state, full_reset. Non-settled frames are dropped at parse time; recordings reach 100 MB and are
never loaded whole.

COMPLETIONS
-----------
A completion is `levels_completed > prev` between consecutive action lines (the only progress
signal ARC-AGI-3 reports — notes/progress-head-and-goal-inference.md §1). For the completion at
step t:

  - pre_terminal_settled  = settled grid of step t-1 (what the board looked like when the
                            completing action was taken);
  - completing action     = step t's action;
  - the level's evidence  = steps level_start..t-1 (within-level settled frames);
  - step t's OWN settled grid is the NEXT level's board — a level reset, not a solved-state
    image. It is stored only as the next level's initial board and is structurally excluded
    from the completed level's goal evidence.

A completion on the very first recorded line has no pre-terminal grid; it is flagged
`degenerate` rather than silently backfilled.

CONVENTIONS THIS MODULE FIXES (uniform across all conditions, so contrasts stay matched)
----------------------------------------------------------------------------------------
  - "action offset N" counts RECORDED ACTION LINES (leading RESET included where the client
    recorded one). The declared `actions` total differs per game (line_delta, see
    s2_replay_ingest.py); offsets are a checkpoint convention, not a score, and uniformity
    across conditions is what matters.
  - "initial settled board" is the first line's settled grid. Clients that record no leading
    RESET line (cn04; some dc22/lf52/m0r0/tr87 sessions) make that a post-action board; the
    packet carries `initial_is_post_action` so renderers can say so instead of lying.
  - Action ids arrive as ints or strings ("ACTION5", RESET=0); normalized to ints here, both
    spellings accepted, anything else is an error.
  - A few action lines carry an EMPTY `frame` list — measured 2026-07-29: cn04 only, 1-2 per
    session, always `state: GAME_OVER`, never the first line. The step keeps the previous
    settled grid with `n_frames=0` (the action happened; no observation was returned); an empty
    first line would raise rather than guess.

CHECKPOINTS (accepted 2026-07-29)
---------------------------------
  - zero-completion: after 10 and 30 action lines; VALID only if the session has no completion
    at or before that offset — invalid checkpoints are reported, never silently kept;
  - completion-anchored: at the 1st/2nd/3rd completion step (packet includes that completion).

SESSION SELECTION (accepted 2026-07-29)
---------------------------------------
Per game, 3 sessions from logs/s2_replay_sessions.json ordered by (levels_completed desc,
total_actions asc, guid asc), preferring sessions with >=3 completions, falling back to >=2 then
>=1; the tier actually used is recorded. Selection reads the ingest table — one source of truth
for the card-parsing traps.

RESERVED-GAME GUARD
-------------------
The four reserved games in logs/gi1_game_draw.json are refused outright — they appear in no
GI-1 artifact, this module included.

CLI: --selftest (invariants on iteration games) · --game ENV · --inventory (all 21 non-reserved
games -> logs/gi1_packet_inventory.json).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data/human_replays/kaggle_mirror/public_games-dataset"
SESSIONS_TABLE = REPO / "logs/s2_replay_sessions.json"
DRAW = REPO / "logs/gi1_game_draw.json"
INVENTORY_OUT = REPO / "logs/gi1_packet_inventory.json"

ZERO_COMPLETION_OFFSETS = (10, 30)
COMPLETION_ANCHORS = (1, 2, 3)
GRID = 64
CELL_MAX = 15


def normalize_action_id(raw) -> int:
    if isinstance(raw, bool):
        raise ValueError(f"boolean action id: {raw!r}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        s = raw.strip().upper()
        if s == "RESET":
            return 0
        if s.startswith("ACTION") and s[6:].isdigit():
            return int(s[6:])
        if s.isdigit():
            return int(s)
    raise ValueError(f"unrecognized action id: {raw!r}")


@dataclass
class Step:
    index: int                # 1-based over action lines
    action_id: int
    action_data: dict         # coords etc.; game_id stripped
    n_frames: int
    settled: list             # 64x64 grid
    levels_completed: int
    available_actions: list
    state: str
    full_reset: bool


@dataclass
class Completion:
    step_index: int
    level: int                # levels_completed after this step
    increment: int
    action_id: int
    action_data: dict
    level_start_index: int    # first step of the completed level's attempt window
    pre_terminal_settled: list | None
    degenerate: bool          # completion on line 1 -> no pre-terminal grid


@dataclass
class Timeline:
    env: str
    guid: str
    win_levels: int
    initial_is_post_action: bool
    steps: list = field(default_factory=list)
    completions: list = field(default_factory=list)

    def first_completion_step(self) -> int | None:
        return self.completions[0].step_index if self.completions else None


@dataclass
class Packet:
    """Canonical evidence packet: everything below is a function of steps 1..checkpoint only."""
    env: str
    guid: str
    checkpoint_kind: str      # "offset:10" | "offset:30" | "completion:1" ...
    checkpoint_step: int
    initial_settled: list
    initial_is_post_action: bool
    steps: list               # Step objects, 1..checkpoint_step
    completions: list         # Completion objects with step_index <= checkpoint_step
    available_actions: list   # at the checkpoint

    def max_step(self) -> int:
        return self.steps[-1].index if self.steps else 0


def load_timeline(env: str, guid: str) -> Timeline:
    path = CORPUS / env / f"{guid}.recording.jsonl"
    steps: list[Step] = []
    completions: list[Completion] = []
    prev_levels = 0
    level_start = 1
    win_levels = 0
    with path.open() as f:
        for line in f:
            d = json.loads(line).get("data")
            if not isinstance(d, dict) or "frame" not in d:
                continue  # session-summary tail line
            idx = len(steps) + 1
            frames = d["frame"]
            if not frames:
                if not steps:
                    raise ValueError(f"{env}/{guid}: first action line has no frames")
                frames = [steps[-1].settled]  # carry-forward; n_frames records the truth below
            action = d.get("action_input") or {}
            data = dict(action.get("data") or {})
            data.pop("game_id", None)
            levels = int(d.get("levels_completed") or 0)
            win_levels = int(d.get("win_levels") or win_levels)
            step = Step(
                index=idx,
                action_id=normalize_action_id(action.get("id")),
                action_data=data,
                n_frames=len(d["frame"]),
                settled=frames[-1],
                levels_completed=levels,
                available_actions=list(d.get("available_actions") or []),
                state=str(d.get("state")),
                full_reset=bool(d.get("full_reset")),
            )
            steps.append(step)
            if levels > prev_levels:
                completions.append(Completion(
                    step_index=idx,
                    level=levels,
                    increment=levels - prev_levels,
                    action_id=step.action_id,
                    action_data=step.action_data,
                    level_start_index=level_start,
                    pre_terminal_settled=steps[idx - 2].settled if idx >= 2 else None,
                    degenerate=idx < 2,
                ))
                level_start = idx + 1
                prev_levels = levels
    if not steps:
        raise ValueError(f"{env}/{guid}: no action lines")
    return Timeline(
        env=env,
        guid=guid,
        win_levels=win_levels,
        initial_is_post_action=steps[0].action_id != 0,
        steps=steps,
        completions=completions,
    )


def checkpoints(tl: Timeline) -> dict[str, int | None]:
    """Checkpoint name -> step index, or None where invalid/absent (reported, never guessed)."""
    out: dict[str, int | None] = {}
    first = tl.first_completion_step()
    for off in ZERO_COMPLETION_OFFSETS:
        valid = len(tl.steps) >= off and (first is None or first > off)
        out[f"offset:{off}"] = off if valid else None
    for k in COMPLETION_ANCHORS:
        out[f"completion:{k}"] = tl.completions[k - 1].step_index if len(tl.completions) >= k else None
    return out


def extract(tl: Timeline, kind: str, step: int) -> Packet:
    return Packet(
        env=tl.env,
        guid=tl.guid,
        checkpoint_kind=kind,
        checkpoint_step=step,
        initial_settled=tl.steps[0].settled,
        initial_is_post_action=tl.initial_is_post_action,
        steps=tl.steps[:step],
        completions=[c for c in tl.completions if c.step_index <= step],
        available_actions=tl.steps[step - 1].available_actions,
    )


def settled_delta(a: list, b: list) -> list[tuple[int, int, int, int]]:
    """(row, col, value_before, value_after) for every changed cell — the delta primitive the
    digest compiler builds on. Pure function; packets store grids, not deltas."""
    return [(r, c, va, vb)
            for r, (row_a, row_b) in enumerate(zip(a, b))
            for c, (va, vb) in enumerate(zip(row_a, row_b)) if va != vb]


def _draw() -> dict:
    return json.loads(DRAW.read_text())


def select_sessions(env: str, table: dict | None = None) -> list[dict]:
    """3 sessions per the accepted rule; each carries its selection tier and rank."""
    if env in set(_draw()["reserved"]):
        raise SystemExit(f"{env} is RESERVED — untouched by GI-1, this module refuses it")
    table = table or json.loads(SESSIONS_TABLE.read_text())
    rows = [s for s in table["sessions"] if s["env"] == env]
    rows.sort(key=lambda s: (-s["levels_completed"], s["total_actions"], s["guid"]))
    for tier in (3, 2, 1):
        eligible = [s for s in rows if s["levels_completed"] >= tier]
        if len(eligible) >= 3 or tier == 1:
            picked = eligible[:3]
            return [{"guid": s["guid"], "levels_completed": s["levels_completed"],
                     "total_actions": s["total_actions"], "tier": tier, "rank": i}
                    for i, s in enumerate(picked)]
    return []


def game_inventory(env: str, table: dict) -> dict:
    sessions = []
    for sel in select_sessions(env, table):
        tl = load_timeline(env, sel["guid"])
        cps = checkpoints(tl)
        streamed = tl.completions[-1].level if tl.completions else 0
        sessions.append({
            **sel,
            "n_steps": len(tl.steps),
            "win_levels": tl.win_levels,
            "initial_is_post_action": tl.initial_is_post_action,
            "completions": [{"step": c.step_index, "level": c.level, "increment": c.increment,
                             "degenerate": c.degenerate} for c in tl.completions],
            "checkpoints": cps,
            "streamed_matches_card": streamed == sel["levels_completed"],
        })
    return {"env": env, "sessions": sessions,
            "shortfall": any(s["tier"] < 3 for s in sessions) or len(sessions) < 3}


def selftest() -> int:
    """Invariants, on iteration games only (ls20 simple-action, vc33 click-only, m0r0 mixed —
    m0r0 covers the string-action-id client per the ingest docstring)."""
    draw = _draw()
    games = [g for g in ("ls20", "vc33", "m0r0") if g in draw["iteration"]]
    assert games, "selftest games must be in the iteration slice"
    table = json.loads(SESSIONS_TABLE.read_text())
    failures = []
    for env in games:
        for sel in select_sessions(env, table):
            tl = load_timeline(env, sel["guid"])
            tag = f"{env}/{sel['guid'][:8]}"
            streamed = tl.completions[-1].level if tl.completions else 0
            if streamed != sel["levels_completed"]:
                failures.append(f"{tag}: streamed completions {streamed} != card {sel['levels_completed']}")
            levels = [c.level for c in tl.completions]
            if levels != sorted(levels) or len(set(levels)) != len(levels):
                failures.append(f"{tag}: completion levels not strictly increasing: {levels}")
            for s in tl.steps:
                if len(s.settled) != GRID or any(len(r) != GRID for r in s.settled):
                    failures.append(f"{tag}: step {s.index} grid not {GRID}x{GRID}")
                    break
                if any(v < 0 or v > CELL_MAX for r in s.settled for v in r):
                    failures.append(f"{tag}: step {s.index} cell out of 0..{CELL_MAX}")
                    break
            for kind, step in checkpoints(tl).items():
                if step is None:
                    continue
                p = extract(tl, kind, step)
                if p.max_step() > step:
                    failures.append(f"{tag}: packet {kind} leaks past checkpoint")
                if kind.startswith("offset:") and any(c.step_index <= step for c in tl.completions):
                    failures.append(f"{tag}: {kind} marked valid despite completion at/before offset")
                for c in p.completions:
                    if not c.degenerate and c.pre_terminal_settled is None:
                        failures.append(f"{tag}: completion at {c.step_index} lacks pre-terminal grid")
            # post-terminal exclusion: a completion's own settled grid appears in the packet only
            # as the NEXT level's board, never inside the completed level's window.
            for c in tl.completions:
                if c.level_start_index > c.step_index:
                    failures.append(f"{tag}: level window inverted at completion {c.step_index}")
    if failures:
        print(f"SELFTEST FAILED — {len(failures)} problem(s):")
        for x in failures:
            print("  " + x)
        return 1
    print(f"selftest OK on {games} — timelines, completions, checkpoint validity, prefix property")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--game")
    ap.add_argument("--inventory", action="store_true",
                    help="all non-reserved games -> logs/gi1_packet_inventory.json")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    table = json.loads(SESSIONS_TABLE.read_text())
    if args.game:
        print(json.dumps(game_inventory(args.game, table), indent=1))
        return 0
    if args.inventory:
        draw = _draw()
        games = sorted(draw["iteration"] + draw["one_shot"])
        inv = {"games": {}, "draw_file": str(DRAW.relative_to(REPO))}
        for env in games:
            g = game_inventory(env, table)
            inv["games"][env] = g
            valid = sum(1 for s in g["sessions"] for v in s["checkpoints"].values() if v)
            flag = " SHORTFALL" if g["shortfall"] else ""
            print(f"{env:<6} sessions {len(g['sessions'])} · valid checkpoints {valid}/15{flag}")
        INVENTORY_OUT.write_text(json.dumps(inv, indent=1) + "\n")
        print(f"\nwrote {INVENTORY_OUT.relative_to(REPO)}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
