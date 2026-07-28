"""Census every training signal the screening experiments can draw on — one pass over 6.4 GB.

`s2_replay_ingest.py` deliberately does not parse the action lines: it seeks to the first and last
line of each recording and counts newlines, because session-level facts (wins, per-level costs,
resets) live in the summary tail. This module is the complement — it streams every action line and
materializes the `frame` payloads, because the questions here are per-transition and cannot be
answered from summaries.

WHAT A TRANSITION IS HERE
-------------------------
Each line records one action AND the frame that resulted from it. So the transition is

    (row[i].frame_settled, row[i+1].action_input, row[i+1].frame_settled)

and `full_reset` rows break the chain rather than forming a transition with their predecessor.

SETTLED FRAME, NOT FRAME
------------------------
`frame` is a LIST of 64x64 grids, not a grid — 1..N, and N varies within an episode (measured:
71% are N=1, mean 2.86, max 404). Every outcome label in SPEC §5 is defined against the *settled*
frame, so the comparison key is `frame[-1]`. Hashing the whole list instead would classify a
transition as "changed" whenever the intermediate animation differed, which is not what any head
predicts. The full-list length is recorded separately as `framelen` because it drives encoder cost:
at mean 2.86 grids per observation, an encoder honouring the convention reads 2.86x the volume the
training benchmark in `notes/local-compute-options.md` assumed.

REVERSIBILITY IS TWO CLASSES, NOT THREE
---------------------------------------
SPEC §5's reversibility head is three-valued, and replays can only ever populate one of the three.
*Demonstrated reversible* is observable — a return to the same settled frame, same level, within
H_rev = 30 actions. *Demonstrated irreversible* requires VERIFIED absence of a return route, which is
a search the recordings do not contain. And absence of an observed return is explicitly not evidence
of irreversibility, so the remaining transitions are `unknown` and are never trained as negatives.

`no_return_within_horizon` is therefore named for what it is. Calling that field "irreversible" would
hand the head 166,134 fabricated negatives against 5,065 real positives.

THE COUNTERFACTUAL COUNTS ARE THE POINT
---------------------------------------
Replays are on-policy: for any state, one action was taken and the other outcomes are unobserved.
The only exception is a state visited more than once with different actions. Those are counted three
ways, because they are not interchangeable:

  - `discrete`  — same settled frame, >=2 distinct ids from ACTION1-5
  - `coord`     — same settled frame, >=2 distinct ACTION6 (x, y)
  - `coord_pairs_by_outcome` — those coordinate pairs split by what each click actually did

The third split matters more than the total. A (noop, change) pair teaches only "this cell is dead";
a (change, change) pair is the genuine "which effective action is better" signal a ranking head
needs. Reporting the total alone overstates the usable ranking supervision by roughly 2.5x.

CN04 ENCODES ACTION IDS AS STRINGS
----------------------------------
`action_input.id` is "ACTION5" in cn04 and an int everywhere else — the same trap
`s2_replay_ingest.py` documents for click bucketing. `_action_id` normalizes both.

180,836 LINES IS NOT 180,836 OBSERVATIONS
-----------------------------------------
`wc -l` over the corpus gives 180,836 and that figure has been quoted as a transition count. It is
not. The decomposition is exact and every line is accounted for:

    180,836  lines
      - 340  session-summary tail lines (one per recording, no `frame` field)
      -  12  rows carrying `"frame": []` — six cn04 sessions and one m0r0
    ---------
    180,484  usable observations  ->  180,144 transitions after 340 chain starts

The empty-frame rows are skipped rather than treated as unchanged. Counting them as observations
would silently insert 12 spurious no-op transitions into a class that only has 8,945 members.

Emits `logs/s2_corpus_census.json`, one object per game.
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import os
import sys
from pathlib import Path

try:
    from orjson import loads as _loads
except ImportError:
    from json import loads as _loads

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data/human_replays/kaggle_mirror/public_games-dataset"
OUT = REPO / "logs/s2_corpus_census.json"

DISCRETE = range(1, 6)
CLICK = 6
H_REV = 30          # SPEC §13.1 reversibility evidence horizon: same level, <= 30 actions


def _hash(grid) -> bytes:
    return hashlib.blake2b(repr(grid).encode(), digest_size=12).digest()


def _action_id(action_input):
    """Normalize cn04's "ACTION5" against everyone else's 5. Returns None if unparseable."""
    if not isinstance(action_input, dict):
        return None
    i = action_input.get("id")
    if isinstance(i, str):
        i = i.replace("ACTION", "").replace("RESET", "0")
        try:
            i = int(i)
        except ValueError:
            return None
    return i if isinstance(i, int) else None


def _blank_game():
    return dict(
        files=0, rows=0, trans=0, noop=0, changed=0, terminal=0,
        acts=collections.Counter(),
        framelen=collections.Counter(),
        frames=set(),                                   # distinct settled frames
        discrete=collections.defaultdict(set),          # frame -> {action id}
        coord=collections.defaultdict(dict),            # frame -> {(x, y): outcome}
        reversible=0, no_return_within_horizon=0,
    )


def _reversibility(seq, g) -> None:
    """Label each changed transition in one session by whether its origin state came back.

    `seq` is (settled hash, level) per row, with reset boundaries already broken. A transition out
    of position i is *demonstrated reversible* when seq[i]'s state reappears at the same level
    within H_REV actions. Everything else is `unknown` — see the module docstring.
    """
    for i in range(len(seq) - 1):
        origin, level = seq[i]
        if seq[i + 1][0] == origin:
            continue                                     # no-op, not a reversibility question
        window = seq[i + 2: i + 2 + H_REV]
        if any(h == origin and lv == level for h, lv in window):
            g["reversible"] += 1
        else:
            g["no_return_within_horizon"] += 1


def census(corpus: Path) -> dict:
    games = collections.defaultdict(_blank_game)
    files = sorted(glob.glob(str(corpus / "*" / "*.recording.jsonl")))
    if not files:
        sys.exit(f"no recordings under {corpus}")
    print(f"{len(files)} recordings", file=sys.stderr)

    for n, path in enumerate(files, 1):
        game = os.path.basename(os.path.dirname(path))
        g = games[game]
        g["files"] += 1
        prev_hash = prev_levels = None
        seq = []                                         # (settled hash, level), reset boundaries broken

        with open(path, "rb") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    record = _loads(line)
                except Exception:
                    continue
                data = record.get("data")
                if not isinstance(data, dict) or "frame" not in data:
                    continue                             # session-summary tail line
                frame = data["frame"]
                if not isinstance(frame, list) or not frame:
                    continue

                g["rows"] += 1
                g["framelen"][len(frame)] += 1
                settled = _hash(frame[-1])
                g["frames"].add(settled)

                levels = data.get("levels_completed")
                if data.get("full_reset"):
                    seq = []
                seq.append((settled, levels))
                action_input = data.get("action_input")
                aid = _action_id(action_input)
                if aid is not None:
                    g["acts"][aid] += 1

                if prev_hash is not None and not data.get("full_reset"):
                    g["trans"] += 1
                    terminal = (prev_levels is not None and levels is not None
                                and levels > prev_levels)
                    unchanged = settled == prev_hash
                    g["noop" if unchanged else "changed"] += 1
                    if terminal:
                        g["terminal"] += 1

                    if aid in DISCRETE:
                        g["discrete"][prev_hash].add(aid)
                    elif aid == CLICK:
                        payload = (action_input or {}).get("data") or {}
                        if "x" in payload and "y" in payload:
                            outcome = "term" if terminal else ("noop" if unchanged else "chg")
                            g["coord"][prev_hash][(payload["x"], payload["y"])] = outcome

                prev_hash, prev_levels = settled, levels

        _reversibility(seq, g)
        if n % 50 == 0:
            print(f"  {n}/{len(files)}", file=sys.stderr)
    return games


def summarize(games: dict) -> dict:
    out = {}
    for game, g in sorted(games.items()):
        disc_multi = [len(v) for v in g["discrete"].values() if len(v) > 1]
        crd_multi = [len(v) for v in g["coord"].values() if len(v) > 1]

        by_outcome = collections.Counter()
        for cells in g["coord"].values():
            if len(cells) < 2:
                continue
            outcomes = sorted(cells.values())
            for a in range(len(outcomes)):
                for b in range(a + 1, len(outcomes)):
                    by_outcome["|".join(sorted((outcomes[a], outcomes[b])))] += 1

        out[game] = dict(
            files=g["files"], rows=g["rows"], transitions=g["trans"],
            changed=g["changed"], noop=g["noop"], terminal=g["terminal"],
            reversible=g["reversible"],
            no_return_within_horizon=g["no_return_within_horizon"],
            distinct_settled_frames=len(g["frames"]),
            grids=sum(k * v for k, v in g["framelen"].items()),
            actions={str(k): v for k, v in sorted(g["acts"].items())},
            framelen={str(k): v for k, v in sorted(g["framelen"].items())},
            frames_with_discrete=len(g["discrete"]),
            frames_multi_discrete=len(disc_multi),
            discrete_cf_pairs=sum(n * (n - 1) // 2 for n in disc_multi),
            frames_with_coord=len(g["coord"]),
            frames_multi_coord=len(crd_multi),
            coord_cf_pairs=sum(n * (n - 1) // 2 for n in crd_multi),
            coord_pairs_by_outcome=dict(by_outcome),
            max_coords_from_one_frame=max((len(v) for v in g["coord"].values()), default=0),
        )
    return out


def report(summary: dict) -> None:
    total = lambda k: sum(g[k] for g in summary.values())
    trans = total("transitions")
    print(f"\n{len(summary)} games · {total('files')} recordings · {total('rows'):,} rows")
    print(f"{trans:,} transitions · {total('grids'):,} grids "
          f"(mean {total('grids') / total('rows'):.2f} per observation)")
    for label, key in [("changed", "changed"), ("no-op", "noop"), ("terminal", "terminal"),
                       ("reversible", "reversible")]:
        print(f"  {label:<12}{total(key):>9,}  {100 * total(key) / trans:5.2f}%")
    print(f"  {'unknown':<12}{total('no_return_within_horizon'):>9,}"
          f"  {100 * total('no_return_within_horizon') / trans:5.2f}%  (never trained as negative)")
    print(f"  distinct settled frames {total('distinct_settled_frames'):,}")
    print(f"\ncounterfactual structure — the only 'same state, different action' evidence replays hold")
    print(f"  discrete pairs {total('discrete_cf_pairs'):>8,} "
          f"from {total('frames_multi_discrete'):,} frames")
    print(f"  coord pairs    {total('coord_cf_pairs'):>8,} "
          f"from {total('frames_multi_coord'):,} frames")
    by_outcome = collections.Counter()
    for g in summary.values():
        by_outcome.update(g["coord_pairs_by_outcome"])
    n = sum(by_outcome.values()) or 1
    for k, v in by_outcome.most_common():
        print(f"    {k:<12}{v:>8,}{100 * v / n:>7.1f}%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=CORPUS)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    summary = summarize(census(args.corpus))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=1))
    report(summary)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
