#!/usr/bin/env python3
"""E3 follow-up — is a GROUNDED (cell-level) forward model learnable from the E1 store?

`notes/e3-grounded-delta.md`. X1 established that the position-free effect grammar pins the
next state on 0 of 35,568 board-changing edges, so no planner can step over it. That is a
statement about the VOCABULARY. This file asks the question X1 did not: can the delta be
predicted at all, when the model is allowed to name cells?

Zero model calls, zero game contact. Three measurements of increasing strength:

  S1  grounded determinism   -- upper bound. For repeated (pre_grid, action) observations,
                                how often is the post grid identical? Plus the latent-
                                augmentation arm (in-episode action count) on the counter
                                games. Source: the instrumented rerun census, which alone
                                carries repeats (the v2 store's log cannot disagree with
                                itself -- e2_hidden_state's standing note).
  S2  locality radius        -- the load-bearing one. For every changed cell, the smallest r
                                such that the (2r+1)^2 pre-grid patch plus the action
                                determines the cell's new value across the whole store.
  S3  patch-rule generalization -- mine patch->value rules on a train split, score EXACT
                                grounded next-state accuracy on the held-out store split and
                                on human replays, against a memorizer floor and the identity
                                floor.

CONVENTIONS
-----------
Patches are taken from the PRE grid, padded with -1 outside the board (a value no cell can
hold), so a cell's key never silently aliases the border with the interior.

Two action-key variants are carried throughout, because the choice is not neutral and the
note's literal spec is the looser of the two:

  `local`  the honest local rule: for ACTION6, the click offset (dy, dx) when the click
           falls INSIDE the patch, and the single symbol `out` when it does not. A radius-r
           rule then sees exactly the radius-r neighbourhood and nothing else.
  `rel`    the note's literal spec: the raw click offset (dy, dx) for every cell, however
           far away. This is a strictly stronger model -- it smuggles in a global coordinate
           -- and it makes keys much rarer, so its determination rates are inflated by
           singleton groups. Both are reported; support statistics accompany every rate.

A group of size 1 is determined VACUOUSLY. Every determination rate is therefore reported
twice: over all queried cells, and over cells whose group has support >= 2.

Unchanged cells are SAMPLED (32 per transition, seeded) rather than enumerated: 50,330
transitions x 4,096 cells is 206M cells, and the population is homogeneous enough that a
seeded sample answers the false-positive-pressure question at 1/128 the cost. Changed cells
are never sampled -- all 1,131,532 of them are used.

Run:
  .venv/bin/python agent/harness/e3_grounded.py --stage s1 --out logs/e3_grounded_s1.json
  .venv/bin/python agent/harness/e3_grounded.py --stage s2 --jobs 8 --out logs/e3_grounded_s2.json
  .venv/bin/python agent/harness/e3_grounded.py --stage s3 --jobs 8 --out logs/e3_grounded_s3.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from es_candidates import _Objects, _lineage  # noqa: E402
from e3_executor import load_store, reconstruct  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    EXCLUDED_GAMES,
    ROOT,
    Transition,
    _rigid_translation,
    grid_digest,
    load_game,
)

STORE = ROOT / "logs/e1_store_v2"
RERUN = ROOT / "logs/e2_hidden_state_rerun"
FORMAT_VERSION = 1

# ---- working defaults, all (w) and all reported ---------------------------------------
R_CAP = 8  # locality search stops here; "never" means "not determined at r <= 8"
UNCHANGED_SAMPLE = 32  # sampled unchanged cells per transition (seeded)
TRAIN_FRACTION = 0.7  # store split, in STEP order (the store is one trajectory)
S3_RADII = (1, 2, 3)
HUMAN_SAMPLE = 400  # human test transitions per level, sampled (seeded) for cost
COUNTER_GAMES = ("m0r0", "g50t", "cn04")  # the known-latent games (hidden-state results)

KIND_BITS = {"move": 1, "reshape": 2, "appear": 4, "disappear": 8, "unattributed": 16}


def games() -> list[str]:
    return [game for game in ALL_GAMES if game not in EXCLUDED_GAMES]


# ======================================================================================
# Patch machinery
# ======================================================================================


def as_array(grid: list) -> np.ndarray:
    return np.asarray(grid, dtype=np.int8)


def patch_table(grid: np.ndarray, radius: int) -> np.ndarray:
    """(H*W, (2r+1)^2) int8 — every cell's pre-grid neighbourhood, -1 outside the board."""
    padded = np.pad(grid, radius, constant_values=-1)
    windows = sliding_window_view(padded, (2 * radius + 1, 2 * radius + 1))
    return np.ascontiguousarray(windows.reshape(grid.size, -1))


def action_key(
    action_id: int,
    click: tuple[int | None, int | None],
    row: int,
    col: int,
    radius: int,
    variant: str,
) -> tuple:
    """The action half of a cell's rule key. See the module docstring on `local` vs `rel`."""
    if action_id != 6:
        return (action_id,)
    click_row, click_col = click
    if not isinstance(click_row, int) or not isinstance(click_col, int):
        return (6, "noclick")
    drow, dcol = click_row - row, click_col - col
    if variant == "rel":
        return (6, drow, dcol)
    if abs(drow) <= radius and abs(dcol) <= radius:
        return (6, drow, dcol)
    return (6, "out")


def click_of(transition: Transition) -> tuple[int | None, int | None]:
    data = transition.action_data or {}
    return (data.get("y"), data.get("x"))


# ======================================================================================
# Per-cell event-kind attribution (the X1 vocabulary, projected onto cells)
# ======================================================================================


def cell_kind_mask(pre_objects: _Objects, post_objects: _Objects, width: int) -> dict[int, int]:
    """cell index -> bitmask of the event kinds whose components cover it.

    The same lineage rs_transitions.effect_signature uses, so a cell's kind and the edge's
    signature cannot disagree. A cell may carry several kinds (a `move` destination that is
    also inside a `reshape`d component of another colour); it is counted under each, and the
    per-kind tables state so. `assignment` has no per-cell analogue — it is a property of a
    signature's ambiguity, not of a cell — and is reported at the EDGE level instead.
    """
    mask: dict[int, int] = defaultdict(int)
    colours = set(pre_objects.by_colour) | set(post_objects.by_colour)
    for colour in colours:
        pre_members = pre_objects.by_colour.get(colour, [])
        post_members = post_objects.by_colour.get(colour, [])
        descendants, ancestors = _lineage(pre_members, post_members)
        for index, member in enumerate(pre_members):
            targets = descendants[index]
            if not targets:
                kind, cells = "disappear", member["cells"]
            elif len(targets) == 1 and len(ancestors[targets[0]]) == 1:
                after = post_members[targets[0]]["cells"]
                if after == member["cells"]:
                    continue
                vector = _rigid_translation(member["cells"], after)
                kind = "move" if vector is not None else "reshape"
                cells = member["cells"] | after
            else:
                kind = "reshape"
                cells = member["cells"].union(*(post_members[t]["cells"] for t in targets))
            bit = KIND_BITS[kind]
            for row, col in cells:
                mask[row * width + col] |= bit
        for index, member in enumerate(post_members):
            if not ancestors[index]:
                for row, col in member["cells"]:
                    mask[row * width + col] |= KIND_BITS["appear"]
    return mask


# ======================================================================================
# S1 — grounded determinism
# ======================================================================================


def s1_game(game: str) -> dict[str, Any]:
    """Repeated (pre_grid, action) observations in the instrumented rerun census.

    Digest-level: the rerun records state digests, and identical digest == identical grid
    (the explorer's own sha256 over the frame). Routing actions are included — they are why
    this census has repeats at all.
    """
    path = RERUN / f"{game}.performs.jsonl"
    if not path.exists():
        return {"game": game, "skipped": "no rerun census"}
    rows = [json.loads(line) for line in path.open() if line.strip()]
    usable = [row for row in rows if row.get("pre") and row.get("post")]

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in usable:
        groups[(row["pre"], tuple(row["action"]))].append(row)
    repeated = {key: obs for key, obs in groups.items() if len(obs) > 1}
    deterministic = {key: obs for key, obs in repeated.items() if len({o["post"] for o in obs}) == 1}
    aliased = {key: obs for key, obs in repeated.items() if len({o["post"] for o in obs}) > 1}

    # observation-weighted view: of all repeated observations, how many sit in a
    # deterministic group (the fraction a forward model would actually meet)
    repeated_obs = sum(len(obs) for obs in repeated.values())
    deterministic_obs = sum(len(obs) for obs in deterministic.values())

    # -- latent augmentation: the in-episode action count ------------------------------
    arms: dict[str, dict[str, Any]] = {}
    for arm, extract in (
        ("episode_count", lambda c: c.get("episode")),
        ("episode_parity", lambda c: None if c.get("episode") is None else c["episode"] % 2),
    ):
        resolved = 0
        resolved_nontrivial = 0
        computable = 0
        for obs in aliased.values():
            values = [extract(o.get("counters") or {}) for o in obs]
            if any(value is None for value in values):
                continue
            computable += 1
            cells: dict[Any, set[str]] = defaultdict(set)
            sizes: Counter = Counter()
            for value, row in zip(values, obs, strict=True):
                cells[value].add(row["post"])
                sizes[value] += 1
            if all(len(posts) == 1 for posts in cells.values()):
                resolved += 1
                # a cell of size 1 resolves nothing: the raw counter is close to a
                # per-observation identifier, so the honest number requires a cell that
                # actually held two observations and still agreed.
                if any(sizes[value] > 1 for value in cells):
                    resolved_nontrivial += 1
        arms[arm] = {
            "aliased_groups_computable": computable,
            "resolved": resolved,
            "resolved_with_a_supported_cell": resolved_nontrivial,
            "fraction": round(resolved / computable, 4) if computable else None,
            "fraction_nontrivial": (
                round(resolved_nontrivial / computable, 4) if computable else None
            ),
        }

    # the v2 store itself, for the record: it cannot hold repeats by construction
    store_groups: dict[tuple, set[str]] = defaultdict(set)
    with (STORE / f"{game}.transitions.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            store_groups[(row["pre"], tuple(row["action"]))].add(row["post"])

    return {
        "game": game,
        "is_counter_game": game in COUNTER_GAMES,
        "performs": len(rows),
        "performs_with_both_digests": len(usable),
        "distinct_pre_action_groups": len(groups),
        "repeated_groups": len(repeated),
        "deterministic_groups": len(deterministic),
        "aliased_groups": len(aliased),
        "determinism_group_weighted": (
            round(len(deterministic) / len(repeated), 4) if repeated else None
        ),
        "repeated_observations": repeated_obs,
        "determinism_observation_weighted": (
            round(deterministic_obs / repeated_obs, 4) if repeated_obs else None
        ),
        "latent_arms": arms,
        "store_repeated_groups": sum(1 for posts in store_groups.values() if len(posts) > 1),
    }


# ======================================================================================
# Shared store preparation for S2/S3
# ======================================================================================


def prepared_rows(game: str) -> dict[str, Any]:
    """Store transitions with both frames, as arrays, plus per-edge kind/blocker labels."""
    loaded = load_store(game)
    transitions: list[Transition] = loaded["transitions"]
    post_missing: set[int] = loaded["post_missing"]
    rows: list[dict[str, Any]] = []
    for transition in transitions:
        if transition.step in post_missing:
            continue  # no real post frame; a fabricated one would be scored as truth
        pre = as_array(transition.pre)
        post = as_array(transition.post)
        width = pre.shape[1]
        pre_objects = _Objects(transition.pre)
        post_objects = _Objects(transition.post)
        _, blockers = reconstruct(transition.pre, pre_objects, transition.effect)
        rows.append(
            {
                "step": transition.step,
                "action_id": transition.action_id,
                "click": click_of(transition),
                "pre": pre,
                "post": post,
                "pre_digest": grid_digest(transition.pre),
                "width": width,
                "changed": np.flatnonzero((pre != post).reshape(-1)),
                "kinds": cell_kind_mask(pre_objects, post_objects, width),
                "blockers": blockers,
                "effect_len": len(transition.effect),
            }
        )
    return {"game": game, "rows": rows, "transitions": transitions}


def queried_cells(rows: list[dict[str, Any]], game: str) -> list[tuple[int, int, bool, int]]:
    """(row index, cell index, changed?, kind mask) — every changed cell, plus a seeded
    sample of unchanged cells for the false-positive-pressure measurement."""
    out: list[tuple[int, int, bool, int]] = []
    for index, row in enumerate(rows):
        changed = set(int(cell) for cell in row["changed"])
        for cell in sorted(changed):
            out.append((index, cell, True, row["kinds"].get(cell, KIND_BITS["unattributed"])))
        total = row["pre"].size
        rng = random.Random(f"{game}:{row['step']}")
        pool = total - len(changed)
        if pool <= 0:
            continue
        take = min(UNCHANGED_SAMPLE, pool)
        picked: set[int] = set()
        # rejection sampling: cheaper than materialising the 4,096-element complement
        while len(picked) < take:
            candidate = rng.randrange(total)
            if candidate not in changed:
                picked.add(candidate)
        for cell in sorted(picked):
            out.append((index, cell, False, 0))
    return out


# ======================================================================================
# S2 — locality radius
# ======================================================================================


def s2_game(game: str) -> dict[str, Any]:
    started = time.time()
    prepared = prepared_rows(game)
    rows = prepared["rows"]
    if not rows:
        return {"game": game, "skipped": "no rows with both frames"}
    cells = queried_cells(rows, game)
    changed_flags = np.array([entry[2] for entry in cells], dtype=bool)
    outcomes = np.array(
        [int(rows[entry[0]]["post"].reshape(-1)[entry[1]]) for entry in cells], dtype=np.int16
    )
    n_changed = int(changed_flags.sum())
    n_unchanged = int((~changed_flags).sum())

    by_pre: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_pre[row["pre_digest"]].append(index)
    row_cells: dict[int, list[int]] = defaultdict(list)
    for position, entry in enumerate(cells):
        row_cells[entry[0]].append(position)

    variants = ("local", "rel")
    # r_min[variant][arm] : per queried cell, the smallest determining radius (-1 = never)
    r_min = {
        variant: {arm: np.full(len(cells), -1, dtype=np.int8) for arm in ("all", "changed")}
        for variant in variants
    }
    per_radius: dict[str, list[dict[str, Any]]] = {variant: [] for variant in variants}

    for radius in range(R_CAP + 1):
        keys: dict[str, list[Any]] = {variant: [None] * len(cells) for variant in variants}
        for digest, indices in by_pre.items():
            table = patch_table(rows[indices[0]]["pre"], radius)
            for index in indices:
                row = rows[index]
                for position in row_cells[index]:
                    cell = cells[position][1]
                    patch = table[cell].tobytes()
                    cell_row, cell_col = divmod(cell, row["width"])
                    for variant in variants:
                        keys[variant][position] = (
                            patch,
                            action_key(
                                row["action_id"], row["click"], cell_row, cell_col, radius, variant
                            ),
                        )
            del table

        for variant in variants:
            key_list = keys[variant]
            for arm in ("all", "changed"):
                groups: dict[Any, set[int]] = defaultdict(set)
                support: Counter = Counter()
                for position, key in enumerate(key_list):
                    if arm == "changed" and not changed_flags[position]:
                        continue
                    groups[key].add(int(outcomes[position]))
                    support[key] += 1
                determined = np.zeros(len(cells), dtype=bool)
                supported = np.zeros(len(cells), dtype=bool)
                for position, key in enumerate(key_list):
                    if arm == "changed" and not changed_flags[position]:
                        continue
                    if len(groups[key]) == 1:
                        determined[position] = True
                    supported[position] = support[key] >= 2
                fresh = determined & (r_min[variant][arm] < 0)
                r_min[variant][arm][fresh] = radius
                if arm == "all":
                    # false-positive pressure: an unchanged cell sharing a key with a
                    # changed one is a cell the model would be tempted to repaint
                    mixed = {key for key, values in groups.items() if len(values) > 1}
                    unchanged_colliding = int(
                        sum(
                            1
                            for position, key in enumerate(key_list)
                            if not changed_flags[position] and key in mixed
                        )
                    )
                else:
                    unchanged_colliding = None
                denominator = n_changed if arm == "changed" else len(cells)
                cell_mask = changed_flags if arm == "changed" else np.ones(len(cells), bool)
                per_radius[variant].append(
                    {
                        "radius": radius,
                        "arm": arm,
                        "cells": int(denominator),
                        "determined": int(determined[cell_mask].sum()),
                        "fraction": round(float(determined[cell_mask].mean()), 4),
                        "supported_ge2": int(supported[cell_mask].sum()),
                        "determined_with_support_ge2": int(
                            (determined & supported)[cell_mask].sum()
                        ),
                        "fraction_of_supported": (
                            round(
                                float((determined & supported)[cell_mask].sum())
                                / max(int(supported[cell_mask].sum()), 1),
                                4,
                            )
                            if supported[cell_mask].sum()
                            else None
                        ),
                        "distinct_keys": len(groups),
                        "unchanged_cells_colliding_with_changed": unchanged_colliding,
                    }
                )
        del keys

    def distribution(values: np.ndarray) -> dict[str, Any]:
        counts = Counter(int(value) for value in values)
        total = len(values)
        determined = total - counts.get(-1, 0)
        return {
            "cells": total,
            "histogram": {("never" if r == -1 else str(r)): counts[r] for r in sorted(counts)},
            "le_2": round(sum(counts[r] for r in range(0, 3)) / total, 4) if total else None,
            "le_4": round(sum(counts[r] for r in range(0, 5)) / total, 4) if total else None,
            "le_8": round(determined / total, 4) if total else None,
            "never": round(counts.get(-1, 0) / total, 4) if total else None,
            "median_r": (
                int(np.median(values[values >= 0])) if determined else None
            ),
        }

    result: dict[str, Any] = {
        "game": game,
        "rows": len(rows),
        "changing_rows": sum(1 for row in rows if row["changed"].size),
        "changed_cells": n_changed,
        "sampled_unchanged_cells": n_unchanged,
        "per_radius": per_radius,
        "r_min": {
            variant: {
                # `all`      every queried cell, grouped with the unchanged sample present
                # `all_on_changed`  the headline: changed cells only, but judged under the
                #            grouping a real forward model faces (unchanged cells included,
                #            so a patch that must stay put competes with one that must move)
                # `changed`  changed cells grouped among themselves — the note's literal
                #            reading, and the looser of the two
                "all": distribution(r_min[variant]["all"]),
                "all_on_changed": distribution(r_min[variant]["all"][changed_flags]),
                "changed": distribution(r_min[variant]["changed"][changed_flags]),
            }
            for variant in variants
        },
    }

    # per event kind, on changed cells only (a cell counts under every kind covering it)
    kinds = np.array([entry[3] for entry in cells], dtype=np.int32)
    per_kind: dict[str, dict[str, Any]] = {}
    for kind, bit in KIND_BITS.items():
        mask = changed_flags & ((kinds & bit) != 0)
        if not mask.any():
            per_kind[kind] = {"cells": 0}
            continue
        per_kind[kind] = {
            variant: distribution(r_min[variant]["all"][mask]) for variant in ("local", "rel")
        }
        per_kind[kind]["cells"] = int(mask.sum())
    result["per_cell_kind"] = per_kind

    # edge level: an edge is grounded-determinate at r when EVERY one of its changed cells
    # is (the necessary condition for an exact next state; S3 measures the sufficient one)
    edge_rows: dict[str, Any] = {}
    for variant in ("local", "rel"):
        values = r_min[variant]["all"]
        per_edge = np.full(len(rows), -1, dtype=np.int16)
        for index, row in enumerate(rows):
            positions = [p for p in row_cells[index] if changed_flags[p]]
            if not positions:
                per_edge[index] = 0
                continue
            worst = max(int(values[p]) for p in positions)
            per_edge[index] = -1 if any(values[p] < 0 for p in positions) else worst
        changing = np.array([bool(row["changed"].size) for row in rows])
        edge_rows[variant] = {
            "all_edges": distribution(per_edge),
            "state_changing_edges": distribution(per_edge[changing]),
            "by_blocker_kind": {
                blocker: distribution(
                    per_edge[np.array([blocker in row["blockers"] for row in rows])]
                )
                for blocker in ("reshape", "appear", "assignment")
                if any(blocker in row["blockers"] for row in rows)
            },
        }
    result["per_edge"] = edge_rows
    result["seconds"] = round(time.time() - started, 1)
    return result


# ======================================================================================
# S3 — patch-rule generalization
# ======================================================================================


def row_keys(row: dict[str, Any], radius: int, variant: str) -> list[tuple]:
    """Every cell's rule key for this transition, in flat cell order."""
    patches = patch_table(row["pre"], radius)
    stride = patches.shape[1]
    buffer = patches.tobytes()
    width = row["width"]
    action_id, click = row["action_id"], row["click"]
    keys: list[tuple] = []
    for cell in range(row["pre"].size):
        cell_row = cell // width
        keys.append(
            (
                buffer[cell * stride : (cell + 1) * stride],
                action_key(action_id, click, cell_row, cell - cell_row * width, radius, variant),
            )
        )
    return keys


def build_table(rows: list[dict[str, Any]], radius: int, variant: str) -> dict[Any, int]:
    """key -> majority outcome. Ties break to the smaller colour, so the model is a function
    of the data and of nothing else.

    Counted with a head/tally pair and a Counter only for keys that actually see a second
    outcome: the vast majority of keys are pure, and a Counter per key costs an order of
    magnitude more memory than the store's distinct-patch count justifies.
    """
    head: dict[Any, int] = {}
    tally: dict[Any, int] = {}
    contested: dict[Any, Counter] = {}
    for row in rows:
        flat_post = row["post"].reshape(-1).tolist()
        for cell, key in enumerate(row_keys(row, radius, variant)):
            value = flat_post[cell]
            if key in contested:
                contested[key][value] += 1
            elif key in head:
                if head[key] == value:
                    tally[key] += 1
                else:
                    contested[key] = Counter({head[key]: tally[key], value: 1})
            else:
                head[key] = value
                tally[key] = 1
    table = dict(head)
    for key, counter in contested.items():
        table[key] = min(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return table


def predict(
    row: dict[str, Any], table: dict[Any, int], radius: int, variant: str
) -> tuple[np.ndarray, int]:
    """Predicted post grid (flat) and the number of cells whose key was unseen. An unseen
    key predicts NO CHANGE — the only default that does not invent a value."""
    out = row["pre"].reshape(-1).astype(np.int16).copy()
    misses = 0
    for cell, key in enumerate(row_keys(row, radius, variant)):
        value = table.get(key)
        if value is None:
            misses += 1
        else:
            out[cell] = value
    return out, misses


def score_set(
    rows: list[dict[str, Any]],
    table: dict[Any, int],
    memo: dict[tuple, Any],
    radius: int,
    variant: str,
) -> dict[str, Any]:
    exact = 0
    exact_changing = 0
    changing = 0
    cell_correct = 0
    cell_total = 0
    misses_total = 0
    memo_exact = 0
    memo_exact_changing = 0
    memo_hits = 0
    identity_exact = 0
    for row in rows:
        flat_post = row["post"].reshape(-1).astype(np.int16)
        is_changing = bool(row["changed"].size)
        changing += is_changing
        predicted, misses = predict(row, table, radius, variant)
        misses_total += misses
        agree = predicted == flat_post
        cell_correct += int(agree.sum())
        cell_total += agree.size
        if agree.all():
            exact += 1
            exact_changing += is_changing
        if not is_changing:
            identity_exact += 1
        stored = memo.get((row["pre_digest"], row["action_id"], row["click"]))
        if stored is None:
            memo_prediction = row["pre"].reshape(-1).astype(np.int16)
        else:
            memo_hits += 1
            memo_prediction = stored
        if bool((memo_prediction == flat_post).all()):
            memo_exact += 1
            memo_exact_changing += is_changing
    total = len(rows)
    return {
        "edges": total,
        "state_changing_edges": changing,
        "exact_all": round(exact / total, 4) if total else None,
        "exact_state_changing": round(exact_changing / changing, 4) if changing else None,
        "cell_accuracy": round(cell_correct / cell_total, 6) if cell_total else None,
        "unseen_key_cells": round(misses_total / cell_total, 4) if cell_total else None,
        "memorizer_exact_all": round(memo_exact / total, 4) if total else None,
        "memorizer_exact_state_changing": (
            round(memo_exact_changing / changing, 4) if changing else None
        ),
        "memorizer_hit_rate": round(memo_hits / total, 4) if total else None,
        "identity_floor_exact_all": round(identity_exact / total, 4) if total else None,
    }


def human_rows(game: str, level: int, rng: random.Random) -> list[dict[str, Any]]:
    transitions = [t for t in load_game(game, max_level=2) if t.level == level]
    if len(transitions) > HUMAN_SAMPLE:
        transitions = rng.sample(transitions, HUMAN_SAMPLE)
    rows = []
    for transition in transitions:
        pre = as_array(transition.pre)
        post = as_array(transition.post)
        rows.append(
            {
                "step": transition.step,
                "action_id": transition.action_id,
                "click": click_of(transition),
                "pre": pre,
                "post": post,
                "pre_digest": grid_digest(transition.pre),
                "width": pre.shape[1],
                "changed": np.flatnonzero((pre != post).reshape(-1)),
            }
        )
    return rows


def s3_game(
    game: str, radii: tuple[int, ...] = S3_RADII, variants: tuple[str, ...] = ("local", "rel")
) -> dict[str, Any]:
    started = time.time()
    prepared = prepared_rows(game)
    rows = prepared["rows"]
    if len(rows) < 10:
        return {"game": game, "skipped": f"only {len(rows)} rows with both frames"}
    cut = int(len(rows) * TRAIN_FRACTION)
    train, held_out = rows[:cut], rows[cut:]
    memo: dict[tuple, Any] = {}
    for row in train:
        memo[(row["pre_digest"], row["action_id"], row["click"])] = row["post"].reshape(-1).astype(
            np.int16
        )

    rng = random.Random(f"{game}:human")
    human = {level: human_rows(game, level, rng) for level in (1, 2)}

    result: dict[str, Any] = {
        "game": game,
        "train_rows": len(train),
        "held_out_rows": len(held_out),
        "human_l1_rows": len(human[1]),
        "human_l2_rows": len(human[2]),
        "radii": {},
    }
    for radius in radii:
        per_variant: dict[str, Any] = {}
        for variant in variants:
            table = build_table(train, radius, variant)
            per_variant[variant] = {
                "rules": len(table),
                "store_held_out": score_set(held_out, table, memo, radius, variant),
                "store_train_refit": score_set(train, table, memo, radius, variant),
                "human_l1": score_set(human[1], table, memo, radius, variant) if human[1] else None,
                "human_l2": score_set(human[2], table, memo, radius, variant) if human[2] else None,
            }
            del table
        result["radii"][str(radius)] = per_variant
    result["seconds"] = round(time.time() - started, 1)
    return result


# ======================================================================================
# Driver
# ======================================================================================


STAGES = {"s1": s1_game, "s2": s2_game, "s3": s3_game}


def _job(stage: str, game: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return STAGES[stage](game, **kwargs) if kwargs else STAGES[stage](game)
    except Exception as error:  # a failed game is a reported row, never a lost run
        return {"game": game, "error": f"{type(error).__name__}: {error}"}


def _line(stage: str, row: dict[str, Any]) -> str:
    game = row.get("game", "?")
    if "error" in row:
        return f"{game:5s} ERROR {row['error']}"
    if "skipped" in row:
        return f"{game:5s} skipped: {row['skipped']}"
    if stage == "s1":
        return (
            f"{game:5s} repeats={row['repeated_groups']:5d} "
            f"det={row['determinism_group_weighted']} "
            f"aliased={row['aliased_groups']:4d} "
            f"count_arm={row['latent_arms']['episode_count']['fraction']}"
            f"/{row['latent_arms']['episode_count']['fraction_nontrivial']}"
        )
    if stage == "s2":
        local = row["r_min"]["local"]["all_on_changed"]
        return (
            f"{game:5s} changed={row['changed_cells']:7d} "
            f"local le2={local['le_2']} le8={local['le_8']} never={local['never']} "
            f"edge_le8={row['per_edge']['local']['state_changing_edges']['le_8']} "
            f"({row['seconds']}s)"
        )
    radius = sorted(row["radii"], key=int)[-1]
    best = row["radii"][radius][sorted(row["radii"][radius])[0]]
    return (
        f"{game:5s} last-r held-out exact={best['store_held_out']['exact_all']} "
        f"changing={best['store_held_out']['exact_state_changing']} "
        f"memo={best['store_held_out']['memorizer_exact_all']} "
        f"humanL1={None if not best['human_l1'] else best['human_l1']['exact_all']} "
        f"({row['seconds']}s)"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("s1", "s2", "s3"), required=True)
    parser.add_argument("--games", nargs="*", default=games())
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--out", type=Path, default=None)
    # s3 only: override the radii / action-key variants scored (both are (w) and reported)
    parser.add_argument("--radii", nargs="*", type=int, default=None)
    parser.add_argument("--variants", nargs="*", default=None)
    args = parser.parse_args()

    extra: dict[str, Any] = {}
    if args.stage == "s3":
        if args.radii:
            extra["radii"] = tuple(args.radii)
        if args.variants:
            extra["variants"] = tuple(args.variants)

    out = args.out or ROOT / f"logs/e3_grounded_{args.stage}.json"
    started = time.time()
    results: list[dict[str, Any]] = []
    if args.jobs <= 1:
        for game in args.games:
            row = _job(args.stage, game, **extra)
            results.append(row)
            print(_line(args.stage, row), flush=True)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = {
                pool.submit(_job, args.stage, game, **extra): game for game in args.games
            }
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                results.append(row)
                print(_line(args.stage, row), flush=True)
    results.sort(key=lambda row: args.games.index(row["game"]))

    document = {
        "format_version": FORMAT_VERSION,
        "stage": args.stage,
        "store": str(STORE.relative_to(ROOT)),
        "rerun_census": str(RERUN.relative_to(ROOT)),
        "working_defaults": {
            "r_cap": R_CAP,
            "unchanged_sample_per_transition": UNCHANGED_SAMPLE,
            "train_fraction": TRAIN_FRACTION,
            "s3_radii": list(extra.get("radii", S3_RADII)),
            "s3_variants": list(extra.get("variants", ("local", "rel"))),
            "human_sample_per_level": HUMAN_SAMPLE,
        },
        "wall_clock_seconds": round(time.time() - started, 1),
        "games": {row["game"]: row for row in results},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {out}  ({document['wall_clock_seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
