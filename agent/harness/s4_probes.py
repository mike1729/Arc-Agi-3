#!/usr/bin/env python3
"""Slice-4 bounded retrieval + active probes.

`notes/qwen-3.8-slice4-design.md` → section 7. Two source-free capabilities the
runner exposes to Qwen mid-conversation:

RETRIEVAL (unlimited, over stored autonomous evidence only):
  SHOW_FRAME <tid>              one transition's settled post board, full plate
  SHOW_TRANSITION <tid>         the five-panel exhibit for one transition
  SHOW_EPISODE <tid> <n>        storyboard of n settled frames starting at tid
  SHOW_ACTION_CONTRAST <action> one effect and one no-effect case for an action
  SHOW_COMPONENT_HISTORY <colour_id>  storyboard of frames where that colour changed

ACTIVE PROBES (budget, default 3): replay the verified autonomous prefix that
reaches a named state, perform Qwen's requested action, return every raw frame the
engine emits. The prefix gate is cell-for-cell (the recapture standard): if the
replayed board does not equal the stored board, the probe FAILS, consumes budget,
and returns the failure — never a silently repaired substitute. An unknown tid, a
malformed action, or a redundant repeat likewise consumes budget with an error
record. No request is ever rewritten.

The retrieval side reads only observation stores (same allowlist as the packet
builder). The active side uses the engine — explicitly permitted for the probe
executor (rev 2), and everything returned to Qwen is an engine observation.

Smoke:
  .venv/bin/python agent/harness/s4_probes.py --smoke ls20
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_packet as spk  # noqa: E402  (blind evidence assembly + allowlisted reads)
import s4_render as sr  # noqa: E402
from s4_recapture import Engine  # noqa: E402

ROOT = spk.ROOT
DEFAULT_BUDGET = 3


class ProbeSession:
    """One game's retrieval + probe surface. Every call is logged verbatim."""

    def __init__(self, game: str, out_dir: Path, budget: int = DEFAULT_BUDGET):
        self.game = game
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.evidence = spk.load_evidence(game)
        self.transitions = spk.transition_stream(self.evidence)
        self.by_tid = {t["tid"]: t for t in self.transitions}
        self.budget = budget
        self.probes_spent = 0
        self.log: list[dict[str, Any]] = []
        self._engine: Engine | None = None
        self._probe_keys: set[tuple] = set()

    # ------------------------------------------------------------------ retrieval

    def retrieve(self, op: str, *args: str) -> dict[str, Any]:
        handler = {
            "SHOW_FRAME": self._show_frame,
            "SHOW_TRANSITION": self._show_transition,
            "SHOW_EPISODE": self._show_episode,
            "SHOW_ACTION_CONTRAST": self._show_action_contrast,
            "SHOW_COMPONENT_HISTORY": self._show_component_history,
        }.get(op)
        if handler is None:
            result = {"ok": False, "error": f"unknown retrieval op {op!r}"}
        else:
            try:
                result = handler(*args)
            except Exception as exc:  # malformed args are the model's error, reported
                result = {"ok": False, "error": f"{op}: {exc}"}
        self.log.append({"kind": "retrieval", "op": op, "args": list(args), **{
            k: v for k, v in result.items() if k != "images" or True}})
        return result

    def _save(self, image, stem: str) -> str:
        path = self.out_dir / f"{stem}.png"
        image.save(path)
        return str(path)

    def _show_frame(self, tid: str) -> dict[str, Any]:
        t = self.by_tid[tid]
        img = sr.render_board(np.asarray(t["post"])).image
        return {"ok": True, "images": [self._save(img, f"frame_{tid}")],
                "text": f"settled board after transition {tid} [OBSERVED]"}

    def _show_transition(self, tid: str) -> dict[str, Any]:
        t = self.by_tid[tid]
        if t["pre"] is None:
            return {"ok": False, "error": f"{tid} is a boot row; it has no pre state"}
        panels = sr.exhibit(np.asarray(t["pre"]), np.asarray(t["post"]), t["action"],
                            tuple(t["click"]) if t["click"] else None)
        image = spk.compose_row(
            [spk.scaled(panels["context"], 320), spk.scaled(panels["pre_crop"], 320),
             spk.scaled(panels["marker"], 320), spk.scaled(panels["post_crop"], 320),
             spk.scaled(panels["diff_mask"], 320)],
            ["context", "pre", t["action"], "post", "diff"],
        )
        return {"ok": True, "images": [self._save(image, f"transition_{tid}")],
                "text": f"transition {tid}: action {t['action']}"
                        f"{' click ' + str(t['click']) if t['click'] else ''} [OBSERVED]"}

    def _show_episode(self, tid: str, count: str = "8") -> dict[str, Any]:
        start = list(self.by_tid).index(tid)
        n = max(2, min(16, int(count)))
        frames = [np.asarray(t["post"]) for t in self.transitions[start : start + n]]
        image = sr.storyboard(frames, cols=4, cell_px=3).image
        ids = [t["tid"] for t in self.transitions[start : start + n]]
        return {"ok": True, "images": [self._save(image, f"episode_{tid}_{n}")],
                "text": f"settled frames {ids[0]}..{ids[-1]} in order [OBSERVED]"}

    def _show_action_contrast(self, action: str) -> dict[str, Any]:
        effect = none = None
        for t in self.transitions:
            if t["action"] != action or t["pre"] is None:
                continue
            sig = spk.effect_signature(t)
            if sig[1] == "none" and none is None:
                none = t
            elif sig[1] != "none" and effect is None:
                effect = t
        if effect is None and none is None:
            return {"ok": False, "error": f"no observations of action {action}"}
        images, parts = [], []
        for label, t in (("effect", effect), ("no-effect", none)):
            if t is None:
                parts.append(f"{label}: not observed")
                continue
            panels = sr.exhibit(np.asarray(t["pre"]), np.asarray(t["post"]), t["action"],
                                tuple(t["click"]) if t["click"] else None)
            image = spk.compose_row(
                [spk.scaled(panels["context"], 320), spk.scaled(panels["diff_mask"], 320)],
                [f"{label} pre ({t['tid']})", "changed cells"],
            )
            images.append(self._save(image, f"contrast_{action}_{label}"))
            parts.append(f"{label}: {t['tid']}")
        return {"ok": True, "images": images,
                "text": f"action {action} contrast — {'; '.join(parts)} [OBSERVED]"}

    def _show_component_history(self, colour: str) -> dict[str, Any]:
        c = int(colour)
        if not 0 <= c <= 15:
            return {"ok": False, "error": f"colour id {colour} outside 0..15"}
        hits, prev = [], None
        for t in self.transitions:
            post = np.asarray(t["post"])
            if prev is not None and ((prev == c) != (post == c)).any():
                hits.append((t["tid"], post))
            prev = post
        if not hits:
            return {"ok": False, "error": f"colour {c} never changes in this record"}
        frames = [h[1] for h in hits[:12]]
        image = sr.storyboard(frames, cols=4, cell_px=3).image
        return {"ok": True, "images": [self._save(image, f"colour_{c}_history")],
                "text": f"frames where colour {c} changed: "
                        f"{[h[0] for h in hits[:12]]} [DERIVED-EXACT]"}

    # ------------------------------------------------------------------ probes

    def _prefix_to(self, tid: str) -> list[tuple] | None:
        """The explorer's own action sequence reaching tid's post state, from the
        store's episode structure. Only store transitions are replayable."""
        idx = None
        for i, t in enumerate(self.transitions):
            if t["tid"] == tid:
                idx = i
                break
        if idx is None or self.transitions[idx]["source"] != "store":
            return None
        performs = self.evidence["performs"]
        if idx >= len(performs):
            return None
        row = performs[idx]
        episode_start = idx - row["episode_step"]
        return [tuple(performs[j]["action"]) for j in range(episode_start, idx + 1)]

    def probe(self, start_tid: str, action_id: int, click: tuple[int, int] | None) -> dict[str, Any]:
        record: dict[str, Any] = {
            "kind": "probe", "start_tid": start_tid, "action_id": action_id,
            "click": click, "budget_before": self.budget - self.probes_spent,
        }
        if self.probes_spent >= self.budget:
            record.update(ok=False, error="probe budget exhausted")
            self.log.append(record)
            return record
        self.probes_spent += 1  # every attempt consumes budget — no silent repair
        key = (start_tid, action_id, click)
        if key in self._probe_keys:
            record.update(ok=False, error="redundant probe: identical request already made")
            self.log.append(record)
            return record
        self._probe_keys.add(key)

        target = self.by_tid.get(start_tid)
        prefix = self._prefix_to(start_tid) if target else None
        if target is None or prefix is None:
            record.update(ok=False, error=f"{start_tid} is not a replayable stored state")
            self.log.append(record)
            return record
        if not (isinstance(action_id, int) and 0 <= action_id <= 7):
            record.update(ok=False, error=f"action id {action_id!r} outside 0..7")
            self.log.append(record)
            return record

        if self._engine is None:
            self._engine = Engine(self.game)
        handle = self._engine.new()
        settled = None
        for act in prefix:
            response = self._engine.perform(handle, act)
            frames = self._engine.frames(response)
            settled = frames[-1] if frames else settled
        reached = [list(map(int, r)) for r in settled] if settled else None
        expected = [list(map(int, r)) for r in np.asarray(target["post"])]
        if reached != expected:
            record.update(ok=False, error="prefix gate FAILED: replay did not reproduce "
                                          "the stored board cell-for-cell")
            self.log.append(record)
            return record

        y, x = (click if click else (None, None))
        response = self._engine.perform(handle, (action_id, y, x))
        frames = [list(map(list, f)) for f in self._engine.frames(response)]
        images = []
        if frames:
            strip = sr.storyboard([np.asarray(f) for f in frames[:12]], cols=4, cell_px=3)
            images.append(self._save(strip.image, f"probe_{self.probes_spent}_{start_tid}"))
        record.update(
            ok=True, frames_returned=len(frames), images=images,
            settled_digest=hashlib.sha256(json.dumps(frames[-1]).encode()).hexdigest()[:16] if frames else None,
            text=f"probe executed from {start_tid}: action A{action_id}"
                 f"{' click ' + str(click) if click else ''} returned {len(frames)} frames "
                 "[OBSERVED, live]",
        )
        self.log.append(record)
        return record


def smoke(game: str) -> int:
    out = ROOT / "logs/s4_probe_smoke" / game
    session = ProbeSession(game, out)
    tids = [t["tid"] for t in session.transitions if t["source"] == "store"][:40]
    print(session.retrieve("SHOW_FRAME", tids[5])["text"])
    print(session.retrieve("SHOW_TRANSITION", tids[6])["text"])
    print(session.retrieve("SHOW_EPISODE", tids[2], "6")["text"])
    print(session.retrieve("SHOW_ACTION_CONTRAST", "A1").get("text") or
          session.retrieve("SHOW_ACTION_CONTRAST", "A6").get("text"))
    print(session.retrieve("SHOW_COMPONENT_HISTORY", "9").get("text", "colour 9 static"))
    bad = session.retrieve("SHOW_FRAME", "NOPE")
    print("bad retrieval handled:", bad["error"][:50])
    r1 = session.probe(tids[10], 1, None)
    print("probe 1:", r1.get("text") or r1["error"])
    r2 = session.probe(tids[10], 1, None)
    print("probe 2 (redundant):", r2["error"])
    r3 = session.probe("K00001", 1, None)
    print("probe 3 (unreplayable):", r3["error"])
    r4 = session.probe(tids[11], 1, None)
    print("probe 4 (over budget):", r4["error"])
    print(f"budget spent {session.probes_spent}/{session.budget}; log entries {len(session.log)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", metavar="GAME")
    args = parser.parse_args()
    if args.smoke:
        return smoke(args.smoke)
    parser.error("library module; run --smoke GAME or import ProbeSession")
    return 2


if __name__ == "__main__":
    sys.exit(main())
