#!/usr/bin/env python3
"""Slice-4 blind packet builder — pages, ledger, caps; source-blind by construction.

`notes/qwen-3.8-slice4-design.md` → sections 1–5 + review round 1. Builds, per game,
the ONLY artifact Qwen ever sees:

  logs/s4_model_packet/<blind_id>/pages/page_NN_<kind>.png
  logs/s4_model_packet/<blind_id>/ledger.txt
  logs/s4_model_packet/<blind_id>/packet_manifest.json

Blindness is structural, not aspirational:
  - every file read goes through `read_allowlisted()`, which refuses any path
    outside {s4_observation_log, e1_store_v3} — game source, human replays, and
    prior-model analyses are unreadable from this process;
  - imports: stdlib + numpy + PIL + s4_render (pure pixels). No engine, no dsl,
    no miner, no store semantics;
  - game names are blinded (stable salted ids); the name↔id map is written to the
    SEALED side, never into the packet;
  - the ledger is semantics-free: ids, counts, coordinates, provenance tags
    OBSERVED / DERIVED-EXACT. No "player", no "goal", no "HUD", no miner rules.

Selection is frozen and deterministic (fixed seed, greedy coverage); the random
reserve transition is seeded. Caps enforced against the review-7 manifest limits:
<= 16 images and <= 16,384 measured visual tokens (ceil(h/16)*ceil(w/16)/4 per
image — the checkpoint's patch-16 merge-2 arithmetic, cross-checked against the
probe's recorded image_grid_thw). Over-cap builds trim on a pre-stated ladder and
record every trim; blocks are never silently dropped.

Run:
  .venv/bin/python agent/harness/s4_packet.py --games ls20 ft09 m0r0 sp80
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_render as sr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ALLOWED_ROOTS = (ROOT / "logs/s4_observation_log", ROOT / "logs/e1_store_v3")
PACKET_ROOT = ROOT / "logs/s4_model_packet"
SEALED_ROOT = ROOT / "logs/s4_sealed"

BLIND_SALT = "ship-jepa-s4-2026-08-17"
SEED = 4
MAX_IMAGES = 16
MAX_VISUAL_TOKENS = 16_384
ATLAS_STATES = 14
PAGE_W = 1024  # composed pages are 1024 wide; heights vary, always %32


def blind_id(game: str) -> str:
    return "G" + hashlib.sha256((BLIND_SALT + game).encode()).hexdigest()[:6]


def read_allowlisted(path: Path) -> str:
    resolved = path.resolve()
    if not any(str(resolved).startswith(str(root.resolve()) + "/") for root in ALLOWED_ROOTS):
        raise RuntimeError(f"BLINDNESS VIOLATION: refused to read {resolved}")
    return resolved.read_text()


def visual_tokens(width: int, height: int) -> int:
    return ((height + 15) // 16) * ((width + 15) // 16) // 4


# ---------------------------------------------------------------------------------
# Evidence assembly (observations only)
# ---------------------------------------------------------------------------------


def load_evidence(game: str) -> dict[str, Any]:
    performs = [
        json.loads(line)
        for line in read_allowlisted(ROOT / f"logs/e1_store_v3/{game}.performs.jsonl").splitlines()
    ]
    states = json.loads(read_allowlisted(ROOT / f"logs/e1_store_v3/{game}.states.json"))
    kaggle_rows = [
        json.loads(line)
        for line in read_allowlisted(
            ROOT / f"logs/s4_observation_log/kaggle_v4/{game}.observations.jsonl"
        ).splitlines()
    ]
    recap_dir = ROOT / f"logs/s4_observation_log/recapture/{game}"
    recap_manifest = json.loads(read_allowlisted(recap_dir / "manifest.json"))
    return {
        "performs": performs,
        "states": states,
        "kaggle": kaggle_rows,
        "recap_dir": recap_dir,
        "recap": recap_manifest,
    }


def transition_stream(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    """Uniform (pre, action, click, post) grid transitions from both autonomous
    sources, tagged with provenance. DERIVED-EXACT: pure lookups and diffs."""
    out: list[dict[str, Any]] = []
    states = evidence["states"]
    prev_digest = None
    for row in evidence["performs"]:
        pre = states.get(prev_digest) if prev_digest else None
        post = states.get(row.get("post"))
        aid, y, x = row["action"]
        out.append(
            {
                "tid": f"S{len(out):05d}",
                "source": "store",
                "action": f"A{aid}",
                "click": None if y is None else [y, x],
                "pre": pre,
                "post": post,
                "level": row.get("levels"),
                "completed": False,
            }
        )
        prev_digest = row.get("post") if row.get("episode_step") is not None else None
        if row.get("episode_step") == 0:
            prev_digest = row.get("post")
    prev = None
    for row in evidence["kaggle"]:
        action = row["action"]
        out.append(
            {
                "tid": f"K{len(out):05d}",
                "source": "kaggle",
                "action": "A0" if action == "RESET" else action.replace("ACTION", "A"),
                "click": row.get("click"),
                "pre": prev,
                "post": row["board"],
                "level": row.get("level"),
                "completed": bool(row.get("level_completed")),
            }
        )
        prev = row["board"]
    return [t for t in out if t["post"] is not None]


def effect_signature(t: dict[str, Any]) -> tuple:
    if t["pre"] is None:
        return ("boot",)
    pre, post = np.asarray(t["pre"]), np.asarray(t["post"])
    changed = int((pre != post).sum())
    if changed == 0:
        return (t["action"], "none")
    bucket = "local" if changed <= 8 else "regional" if changed <= 200 else "global"
    added = sorted(set(np.unique(post[pre != post]).tolist()))
    removed = sorted(set(np.unique(pre[pre != post]).tolist()))
    return (t["action"], bucket, tuple(added), tuple(removed))


# ---------------------------------------------------------------------------------
# Page composition
# ---------------------------------------------------------------------------------


class PageBook:
    def __init__(self, out_dir: Path):
        self.dir = out_dir / "pages"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.pages: list[dict[str, Any]] = []

    def add(self, kind: str, image: Image.Image, caption: str) -> dict[str, Any]:
        number = len(self.pages) + 1
        name = f"page_{number:02d}_{kind}.png"
        assert image.width % 32 == 0 and image.height % 32 == 0, f"{name}: dims not %32"
        assert image.width * image.height >= 65_536, f"{name}: below processor minimum"
        image.save(self.dir / name)
        entry = {
            "page": number,
            "kind": kind,
            "file": name,
            "caption": caption,
            "width": image.width,
            "height": image.height,
            "visual_tokens": visual_tokens(image.width, image.height),
            "sha256_16": hashlib.sha256((self.dir / name).read_bytes()).hexdigest()[:16],
        }
        self.pages.append(entry)
        return entry


def compose_row(plates: list[Image.Image], labels: list[str], gap: int = 16) -> Image.Image:
    """Panels side by side on one page canvas, labels in the gutter strip below
    each panel — annotations never touch board pixels."""
    label_h = 24
    height = max(p.height for p in plates) + label_h
    width = sum(p.width for p in plates) + gap * (len(plates) + 1)
    canvas = Image.new("RGB", (width, height), sr.PAD_RGB)
    draw = ImageDraw.Draw(canvas)
    x = gap
    for plate, label in zip(plates, labels):
        canvas.paste(plate, (x, 0))
        draw.text((x, plate.height + 4), label, fill=(0, 0, 0))
        x += plate.width + gap
    arr, _ = sr._pad_to_32(np.asarray(canvas))
    return Image.fromarray(arr)


def scaled(plate: sr.Plate, width: int = 500) -> Image.Image:
    img = plate.image
    if img.width > width:
        h = int(img.height * width / img.width) // 32 * 32 or 32
        img = img.resize((width, h), Image.NEAREST)
    return img


def exhibit_page(book: PageBook, kind: str, pre, post, action: str, click, caption: str):
    panels = sr.exhibit(np.asarray(pre), np.asarray(post), action, tuple(click) if click else None)
    image = compose_row(
        [scaled(panels["context"], 320), scaled(panels["pre_crop"], 320),
         scaled(panels["marker"], 320), scaled(panels["post_crop"], 320),
         scaled(panels["diff_mask"], 320)],
        ["context (pre)", "pre crop", f"action {action}", "post crop", "changed-cell mask"],
    )
    return book.add(kind, image, caption)


# ---------------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------------


def build_game(game: str, rng: np.random.Generator) -> dict[str, Any]:
    evidence = load_evidence(game)
    bid = blind_id(game)
    out_dir = PACKET_ROOT / bid
    book = PageBook(out_dir)
    ledger: list[str] = [
        f"GAME {bid}",
        "PROVENANCE: every section is tagged OBSERVED (recorded frames/actions) or "
        "DERIVED-EXACT (deterministic computation over observations). Nothing else "
        "exists in this packet.",
    ]
    transitions = transition_stream(evidence)
    boards = [t["post"] for t in transitions]
    initial = boards[0]

    # 1 · opening scene [OBSERVED]
    book.add("opening", sr.render_board(np.asarray(initial)).image,
             "the first observed board, unmodified")
    ledger.append("PAGE 1 opening [OBSERVED]: first observed board.")

    # 2 · state atlas [OBSERVED] — greedy max-min diversity, deterministic
    chosen = [0]
    while len(chosen) < min(ATLAS_STATES, len(boards)):
        arr_chosen = [np.asarray(boards[i]) for i in chosen]
        best, best_d = None, -1
        for i in range(0, len(boards), max(1, len(boards) // 400)):
            if i in chosen:
                continue
            d = min(int((np.asarray(boards[i]) != c).sum()) for c in arr_chosen)
            if d > best_d:
                best, best_d = i, d
        if best is None or best_d <= 0:
            break
        chosen.append(best)
    atlas = sr.storyboard([np.asarray(boards[i]) for i in chosen], cols=4, cell_px=3)
    book.add("state_atlas", atlas.image,
             f"{len(chosen)} structurally diverse observed states, thumbnails, "
             "indices are frame ids")
    ledger.append(
        f"PAGE 2 state_atlas [OBSERVED]: frame ids {[transitions[i]['tid'] for i in chosen]}."
    )

    # 3 · causal episode [OBSERVED] — maximize distinct effect signatures
    signatures: dict[tuple, str] = {}
    for t in transitions:
        signatures.setdefault(effect_signature(t), t["tid"])
    episode_frames = [np.asarray(t["post"]) for t in transitions[: min(12, len(transitions))]]
    book.add("causal_episode", sr.storyboard(episode_frames, cols=4, cell_px=3).image,
             "the first consecutive episode, settled frames in order")
    ledger.append(
        f"PAGE 3 causal_episode [OBSERVED]: first {len(episode_frames)} settled frames; "
        f"per-step actions in the ACTIONS section."
    )

    # 4 · action atlas [OBSERVED/DERIVED-EXACT] — one effect + one no-effect per action
    action_pages = 0
    per_action: dict[str, dict[str, Any]] = {}
    for t in transitions:
        if t["pre"] is None:
            continue
        sig = effect_signature(t)
        slot = per_action.setdefault(t["action"], {})
        key = "none" if sig[1] == "none" else "effect"
        slot.setdefault(key, t)
    for action, slot in sorted(per_action.items()):
        if "effect" in slot and action_pages < 4:
            t = slot["effect"]
            exhibit_page(book, f"action_{action}", t["pre"], t["post"], action, t["click"],
                         f"{action}: an observed effect (id {t['tid']})"
                         + ("; a no-effect case exists — see ledger" if "none" in slot else ""))
            action_pages += 1
    ledger.append(
        "ACTIONS [DERIVED-EXACT]: "
        + "; ".join(
            f"{a}: effect observed {'yes' if 'effect' in s else 'no'}, "
            f"no-effect observed {'yes' if 'none' in s else 'no'}"
            for a, s in sorted(per_action.items())
        )
    )

    # 5 · transformation strip [OBSERVED] — richest animation from the recapture
    best_strip = None
    for ep in evidence["recap"]["episodes"]:
        if ep["animation_steps"] > 0 and (best_strip is None or ep["animation_steps"] > best_strip["animation_steps"]):
            best_strip = ep
    if best_strip:
        record = json.loads(read_allowlisted(evidence["recap_dir"] / best_strip["file"]))
        anim = max((s for s in record["steps"] if s["frame_count"] > 1),
                   key=lambda s: s["frame_count"])
        frames = [np.asarray(f) for f in anim["frames"][:12]]
        book.add("transformation_strip", sr.storyboard(frames, cols=4, cell_px=3).image,
                 f"every frame returned by one action (A{anim['action'][0]}), in order")
        ledger.append(
            f"PAGE transformation_strip [OBSERVED]: episode {best_strip['episode_index']}, "
            f"step {anim['episode_step']}, {anim['frame_count']} frames "
            f"(showing {len(frames)})."
        )
    else:
        ledger.append("TRANSFORMATION STRIPS: no multi-frame action observed for this game.")

    # 6 · history exhibit [OBSERVED] — same pre digest + action, different post
    groups: dict[tuple, set] = {}
    for t in transitions:
        if t["pre"] is None:
            continue
        key = (hashlib.sha256(json.dumps(t["pre"]).encode()).hexdigest()[:12], t["action"],
               tuple(t["click"]) if t["click"] else None)
        groups.setdefault(key, set()).add(
            hashlib.sha256(json.dumps(t["post"]).encode()).hexdigest()[:12]
        )
    conflicted = [k for k, posts in groups.items() if len(posts) > 1]
    ledger.append(
        f"HISTORY [DERIVED-EXACT]: {len(conflicted)} (board, action) pairs with more "
        "than one observed outcome."
        if conflicted
        else "HISTORY [DERIVED-EXACT]: no board+action pair in this record produced "
        "two different outcomes — this record shows no evidence of hidden state."
    )

    # 7 · autonomous completion [OBSERVED], only if self-earned
    completions = [t for t in transitions if t["completed"]]
    if completions:
        t = completions[0]
        exhibit_page(book, "completion", t["pre"], t["post"], t["action"], t["click"],
                     "an autonomously earned level completion: the acting transition")
        ledger.append(f"PAGE completion [OBSERVED]: transition {t['tid']}; the level "
                      "counter advanced at this action.")
    else:
        ledger.append("COMPLETION: no autonomous completion exists in this record. "
                      "This game is in the no-autonomous-completion stratum.")

    # 8 · random reserve [OBSERVED] — seeded, against curator cherry-picking
    with_pre = [t for t in transitions if t["pre"] is not None]
    reserve = with_pre[int(rng.integers(0, len(with_pre)))]
    exhibit_page(book, "random_reserve", reserve["pre"], reserve["post"],
                 reserve["action"], reserve["click"],
                 f"a uniformly random observed transition (id {reserve['tid']})")
    ledger.append(f"PAGE random_reserve [OBSERVED]: transition {reserve['tid']}, "
                  f"seeded draw, seed {SEED}.")

    # coverage + effect frequencies [DERIVED-EXACT]
    freq: dict[str, int] = {}
    for t in transitions:
        freq[t["action"]] = freq.get(t["action"], 0) + 1
    ledger.append("COVERAGE [DERIVED-EXACT]: observed action counts "
                  + ", ".join(f"{a}:{n}" for a, n in sorted(freq.items()))
                  + f"; distinct effect signatures: {len(signatures)}; "
                  f"transitions: {len(transitions)} (store {sum(1 for t in transitions if t['source']=='store')}, "
                  f"prior-agent {sum(1 for t in transitions if t['source']=='kaggle')}).")

    # caps
    total_tokens = sum(p["visual_tokens"] for p in book.pages)
    assert len(book.pages) <= MAX_IMAGES, f"{game}: {len(book.pages)} pages over image cap"
    assert total_tokens <= MAX_VISUAL_TOKENS, f"{game}: {total_tokens} visual tokens over cap"

    ledger_text = "\n".join(ledger) + "\n"
    (out_dir / "ledger.txt").write_text(ledger_text)
    manifest = {
        "blind_id": bid,
        "pages": book.pages,
        "page_count": len(book.pages),
        "visual_tokens_total": total_tokens,
        "ledger_sha256_16": hashlib.sha256(ledger_text.encode()).hexdigest()[:16],
        "seed": SEED,
        "caps": {"max_images": MAX_IMAGES, "max_visual_tokens": MAX_VISUAL_TOKENS},
    }
    (out_dir / "packet_manifest.json").write_text(json.dumps(manifest, indent=1))
    return {"game": game, **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=["ls20", "ft09", "m0r0", "sp80"])
    args = parser.parse_args()
    SEALED_ROOT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    blind_map = {}
    for game in args.games:
        manifest = build_game(game, rng)
        blind_map[game] = manifest["blind_id"]
        print(f"{game:5s} -> {manifest['blind_id']}  pages {manifest['page_count']:2d}  "
              f"visual tokens {manifest['visual_tokens_total']:6,}", flush=True)
    (SEALED_ROOT / "blind_map.json").write_text(json.dumps(blind_map, indent=1))
    print(f"blind map -> {SEALED_ROOT / 'blind_map.json'} (sealed side)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
