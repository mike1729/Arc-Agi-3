"""R1 — does a level RESET preserve knowledge? (reset experiment, part 1)

Pre-registered in `gate_manifest.yaml → s1.reset_experiment.r1_knowledge_preservation`. R1 gates nothing
and configures everything: together with R2 it selects the global controller, so getting it wrong sends
eight weeks of construction into the wrong agent.

Sampling is pre-registered, not improvised:
  games                >= 2 distinct public games (one game cannot ground a claim about the class)
  prefixes per game    2 — one short (~10 actions), one longer (~40), so a divergence that only appears
                       with depth is reachable
  replays per prefix   3 (1 original + 2 replays)
  criterion            EXACT frame-sequence equality at every step; on failure record the
                       first-divergence step index — divergence at step 0 means a re-randomised initial
                       state, later divergence means stochastic dynamics, and those imply different agents

Four outcomes, not two: deterministic | mixed | re_randomizes | inconclusive.

SCOPE — state it, do not overclaim. This runs against the competition's OFFLINE environment files, which
are the same game implementations Kaggle's visible path uses. It is evidence about the game code. It is
NOT a test of competition mode, whose scorecard and one-make() restrictions (V5-V7) differ. A
`deterministic` result here licenses the claim "these tested prefixes replay exactly offline" and nothing
broader.

Run:  .venv/bin/python agent/harness/r1_determinism.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import asdict, dataclass, field

import arc_agi
import arcengine

ENV_DIR = "data/environment_files"

# Scripted prefixes use only the simple actions. ACTION6 needs coordinates, and a coordinate policy
# would be a second uncontrolled variable inside a determinism test.
SIMPLE_ACTIONS = [
    arcengine.GameAction.ACTION1,
    arcengine.GameAction.ACTION2,
    arcengine.GameAction.ACTION3,
    arcengine.GameAction.ACTION4,
    arcengine.GameAction.ACTION5,
]


# Fields that are NOT part of the observation and must be excluded from the comparison:
#   full_reset   — metadata ABOUT the reset (True on the first reset after make(), False after). It is
#                  not a property of the observed state. Including it made every first replay "diverge
#                  at step 0" for a reason that has nothing to do with determinism.
#   guid         — a per-call identifier, different on every call by construction.
#   action_input — an echo of the action we just sent, not an observation.
_EXCLUDED_FROM_OBSERVATION = {"full_reset", "guid", "action_input"}


def _grids(frame):
    """The actual pixel grids. `FrameDataRaw.frame` holds them as numpy arrays, and `model_dump()`
    silently OMITS the field — so a digest built from model_dump() compares metadata only and never
    looks at a single pixel. That bug produced the first R1 run's verdicts; it is the reason this
    helper exists and reads the attribute directly."""
    raw = getattr(frame, "frame", None)
    if raw is None:
        return None
    out = []
    for layer in raw:
        arr = layer.tolist() if hasattr(layer, "tolist") else layer
        out.append(arr)
    return out


def frame_digest(frame) -> str:
    """Content hash of an OBSERVATION: the grids plus the observable status fields, with per-call
    metadata excluded. Hashing the grids is the whole point — a metadata-only digest can agree while
    the boards differ, which would silently manufacture a `deterministic` result."""
    if frame is None:
        return "NONE"
    obs = {
        "grids": _grids(frame),
        "available_actions": [int(a) for a in (getattr(frame, "available_actions", None) or [])],
        "state": str(getattr(frame, "state", "")),
        "levels_completed": int(getattr(frame, "levels_completed", 0) or 0),
        "win_levels": int(getattr(frame, "win_levels", 0) or 0),
    }
    assert obs["grids"] is not None, "no grid on frame — refusing to compare metadata only"
    blob = json.dumps(obs, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def scripted_prefix(seed: int, length: int) -> list:
    """A fixed action script. Deterministic given the seed, and identical across replays by construction —
    the script must never depend on observations, or the two arms would not be the same script."""
    rng = random.Random(seed)
    return [rng.choice(SIMPLE_ACTIONS) for _ in range(length)]


@dataclass
class ReplayResult:
    digests: list[str]
    states: list[str]
    levels: list[int]


@dataclass
class PrefixResult:
    game: str
    prefix_len: int
    seed: int
    replays: list[ReplayResult] = field(default_factory=list)
    identical: bool | None = None
    first_divergence: int | None = None


def run_replay(env, actions) -> ReplayResult:
    digests, states, levels = [], [], []
    frame = env.reset()
    digests.append(frame_digest(frame))
    states.append(str(getattr(frame, "state", "")))
    levels.append(int(getattr(frame, "score", 0) or 0))
    for a in actions:
        frame = env.step(a)
        digests.append(frame_digest(frame))
        states.append(str(getattr(frame, "state", "")))
        levels.append(int(getattr(frame, "score", 0) or 0))
    return ReplayResult(digests=digests, states=states, levels=levels)


def compare(replays: list[ReplayResult]) -> tuple[bool, int | None]:
    base = replays[0].digests
    for r in replays[1:]:
        n = min(len(base), len(r.digests))
        for i in range(n):
            if base[i] != r.digests[i]:
                return False, i
        if len(base) != len(r.digests):
            return False, n
    return True, None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", default="ft09-0d8bbf25,ls20-9607627b",
                    help=">=2 distinct public games (pre-registered minimum)")
    ap.add_argument("--short", type=int, default=10)
    ap.add_argument("--long", type=int, default=40)
    ap.add_argument("--replays", type=int, default=3, help="1 original + 2 replays")
    ap.add_argument("--out", default="logs/r1_determinism.json")
    args = ap.parse_args()

    games = [g.strip() for g in args.games.split(",") if g.strip()]
    assert len(games) >= 2, "pre-registration requires >=2 distinct games"

    arcade = arc_agi.Arcade(operation_mode=arc_agi.OperationMode.OFFLINE, environments_dir=ENV_DIR)
    results: list[PrefixResult] = []

    for game in games:
        # V6: one make() per game. Replays use the wrapper's RESET, which is the level reset the
        # competition permits (V5) — not a fresh environment.
        env = arcade.make(game, seed=0)
        if env is None:
            print(f"  {game}: make() returned None — SKIPPED")
            continue
        for prefix_len in (args.short, args.long):
            seed = 1000 + prefix_len
            actions = scripted_prefix(seed, prefix_len)
            pr = PrefixResult(game=game, prefix_len=prefix_len, seed=seed)
            for _ in range(args.replays):
                pr.replays.append(run_replay(env, actions))
            pr.identical, pr.first_divergence = compare(pr.replays)
            results.append(pr)
            flag = "IDENTICAL" if pr.identical else f"DIVERGED@{pr.first_divergence}"
            print(f"  {game}  prefix={prefix_len:>2}  replays={args.replays}  -> {flag}")

    # Classification, per the pre-registered four outcomes.
    per_game: dict[str, list[bool]] = {}
    for r in results:
        per_game.setdefault(r.game, []).append(bool(r.identical))
    all_ident = all(all(v) for v in per_game.values()) if per_game else False
    none_ident = all(not any(v) for v in per_game.values()) if per_game else False
    game_level = {g: all(v) for g, v in per_game.items()}

    if not per_game:
        outcome = "inconclusive"
    elif all_ident:
        outcome = "deterministic"
    elif none_ident:
        outcome = "re_randomizes"
    elif len(set(game_level.values())) > 1:
        outcome = "mixed"
    else:
        outcome = "inconclusive"

    print(f"\nper-game determinism: {game_level}")
    print(f"R1 OUTCOME: {outcome}")
    if outcome == "deterministic":
        print("  Claim ONLY that the tested prefixes replay exactly, offline. NOT that 'everything")
        print("  learned transfers', and NOT that competition mode behaves the same way.")
    elif outcome == "mixed":
        print("  The property is PER-GAME. No global controller is correct; runtime determinism")
        print("  detection plus a switch becomes a build item in its own right.")

    payload = {
        "outcome": outcome,
        "per_game_deterministic": game_level,
        "scope": "OFFLINE competition environment files; not a test of competition mode (V5-V7)",
        "sampling": {"games": games, "prefix_lengths": [args.short, args.long], "replays": args.replays},
        "results": [
            {"game": r.game, "prefix_len": r.prefix_len, "seed": r.seed,
             "identical": r.identical, "first_divergence": r.first_divergence,
             "digests_per_replay": [x.digests for x in r.replays]}
            for r in results
        ],
    }
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
