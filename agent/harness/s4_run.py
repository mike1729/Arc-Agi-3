#!/usr/bin/env python3
"""Slice-4 pilot runner — matched arms, managed uncertainty, certificate-gated.

`notes/qwen-3.8-slice4-design.md` → sections 6–7, review round 1 findings 2/3/6, and
the PROPOSED pre-registration. One cell = one (game, arm) conversation:

  arm T  ledger + hex-grid boards (text carrier; same selected evidence ids)
  arm V  ledger + packet pages as images (raw visual carrier)
  arm P  arm V + bounded retrieval + <=3 active probes (interaction rounds)

Discipline inherited from the certified probe (`e2_probe_vlm`, imported, not
reimplemented): hardened template invariants, per-tag deterministic seeds via the
global MLX RNG, xhigh + the pinned sampler, full per-call traces, atomic
checkpoints, run locking. The runner REFUSES to start unless the gate certificate
verifies: verdict PASS, pinned runtime versions equal live versions, checkpoint
config-file hashes re-verified (full shard re-verification with --verify-shards).

Never constrain the first decoded token. The primary answer is the ranked-hypotheses
JSON (rev 2 §6); the DSL is not requested — it is a sealed-side translation.

Dry run (no model, no GPU):
  .venv/bin/python agent/harness/s4_run.py --arms T V --dry-run
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import e2_probe_vlm as probe  # noqa: E402  (certified serving layer)
import s4_packet as spk  # noqa: E402
from s4_probes import ProbeSession  # noqa: E402

ROOT = spk.ROOT
CERTIFICATE = ROOT / "logs/e2_probe_vlm_38_8bit.json"
RUNS = ROOT / "logs/s4_runs"
PILOT_GAMES = ("ls20", "ft09", "m0r0", "sp80")
MAX_ANSWER_TOKENS = 20_000       # (w) fleet-calibrated at the gate night before use
INTERACTION_ROUNDS = 2           # (w) arm P: rounds after the initial answer
RETRIEVALS_PER_ROUND = 5         # (w)

REQUEST = """\
You are studying an unfamiliar interactive grid environment from recorded evidence
only. Everything shown is either OBSERVED (recorded frames and actions) or
DERIVED-EXACT (deterministic computation over observations). Nothing else is known.

Think first, at length. Then answer with ONLY a JSON object on the last line:
{
  "hypotheses": [
    {"probability": <0..1>, "necessary_conditions": ["..."],
     "sufficient_condition": "...", "evidence_for": ["<page or transition ids>"],
     "evidence_against": ["..."], "predicted_counterexample": "..."}
  ],
  "best_goal": {"plain_causal_condition": "...", "structured_factors": ["..."]},
  "next_probe": {"start_state_id": "<transition id>", "action": {"id": <0..7>,
                 "click": [row, col] or null},
                 "predictions_by_hypothesis": {"<index>": "..."}},
  "retrieval_requests": [{"op": "SHOW_FRAME|SHOW_TRANSITION|SHOW_EPISODE|\
SHOW_ACTION_CONTRAST|SHOW_COMPONENT_HISTORY", "args": ["..."]}],
  "goal_directed_plan": [{"action": {"id": <0..7>, "click": [row, col] or null}}]
}
Probabilities must sum to at most 1. Rank hypotheses by probability. If the evidence
underdetermines the objective, say so through the probabilities and design
"next_probe" to discriminate between your top hypotheses.
"""


def hex_grid(board: list[list[int]]) -> str:
    return "\n".join("".join(format(v, "x") for v in row) for row in board)


def verify_certificate(model: Path, verify_shards: bool) -> dict[str, Any]:
    require = probe.require
    require(CERTIFICATE.exists(), f"gate certificate missing: {CERTIFICATE}")
    cert = json.loads(CERTIFICATE.read_text())
    require(cert.get("verdict") == "PASS", f"gate certificate verdict {cert.get('verdict')!r}")
    compat = cert.get("serving_compatibility") or {}
    live = {p: pkg_version(p) for p in ("mlx-vlm", "mlx", "mlx-lm", "transformers")}
    require(compat.get("versions") == live,
            f"runtime drift vs certificate: {compat.get('versions')} != {live}")
    if verify_shards:
        identity = probe.fingerprint(model)  # full shard verification, minutes
        require(identity["checkpoint_sha256"] == compat.get("checkpoint_sha256"),
                "checkpoint identity drift vs certificate")
    return {"certificate_run_dir": cert.get("run_dir"),
            "checkpoint_sha256": compat.get("checkpoint_sha256"),
            "certificate_verified_shards": bool(verify_shards)}


def load_packet(game: str) -> dict[str, Any]:
    bid = spk.blind_id(game)
    pdir = spk.PACKET_ROOT / bid
    manifest = json.loads((pdir / "packet_manifest.json").read_text())
    ledger = (pdir / "ledger.txt").read_text()
    return {"blind_id": bid, "dir": pdir, "manifest": manifest, "ledger": ledger}


def initial_turn(game: str, arm: str, packet: dict[str, Any]) -> tuple[list[dict], list[Path]]:
    items: list[dict[str, str]] = [{"type": "text", "text": REQUEST}]
    items.append({"type": "text", "text": "== EXACT LEDGER ==\n" + packet["ledger"]})
    images: list[Path] = []
    if arm == "T":
        evidence = spk.load_evidence(game)
        transitions = spk.transition_stream(evidence)
        boards = {
            "first observed board": transitions[0]["post"],
            "last observed board": transitions[-1]["post"],
        }
        completed = [t for t in transitions if t["completed"]]
        if completed:
            boards["board at the autonomously earned completion"] = completed[0]["post"]
        for label, board in boards.items():
            items.append({"type": "text", "text":
                          f"== {label.upper()} (hex digits 0-f = colour ids 0-15) ==\n"
                          + hex_grid(board)})
        items.append({"type": "text", "text":
                      "(text carrier: storyboard pages are listed in the ledger by "
                      "frame id; no images are attached in this condition)"})
    else:
        for page in packet["manifest"]["pages"]:
            items.append({"type": "text", "text":
                          f"Page {page['page']} ({page['kind']}): {page['caption']}"})
            items.append({"type": "image"})
            images.append(packet["dir"] / "pages" / page["file"])
    if arm == "P":
        items.append({"type": "text", "text":
                      "You may request more evidence: fill \"retrieval_requests\" "
                      f"(up to {RETRIEVALS_PER_ROUND} per round) and \"next_probe\" "
                      "(a live experiment; you have a budget of 3 probes total; "
                      "invalid or redundant requests consume it). "
                      f"You will get {INTERACTION_ROUNDS} extra rounds."})
    return items, images


def ask_chat(vlm, messages, images, *, seed, max_tokens, run_dir, tag):
    """Multi-turn variant of the certified single-turn ask: same template kwargs,
    same seeding, same trace discipline. History assistant turns carry post-think
    answers only."""
    import mlx.core as mx
    from PIL import Image as PILImage
    from mlx_vlm import generate

    prompt = vlm.processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
        enable_thinking=True, reasoning_effort=probe.REASONING_EFFORT,
    )
    marker = prompt.rfind("<|im_start|>assistant")
    probe.require(marker != -1, "assistant marker missing")
    probe.require(prompt.rstrip().endswith("<think>"), "generation tail does not open <think>")
    import re as _re
    probe.require(not _re.search(r"<think>\s*</think>", prompt[marker:]),
                  "pre-filled think in generation region")
    pil = [PILImage.open(p) for p in images]
    inputs = vlm.processor(text=prompt, images=pil or None, return_tensors="np")
    expanded = int(np.asarray(inputs["input_ids"]).shape[-1])
    mx.random.seed(seed)
    out = generate(vlm.model, vlm.processor, prompt,
                   image=[str(p) for p in images] or None,
                   max_tokens=max_tokens, verbose=False, **probe.PRODUCTION_SAMPLER)
    text = out.text if hasattr(out, "text") else str(out)
    full = "<think>" + text
    closed = "</think>" in full
    think = full.split("<think>", 1)[-1].split("</think>", 1)[0]
    answer = full.split("</think>", 1)[-1].strip() if closed else ""
    payload = probe.extract_json(answer) if closed else None
    record = {
        "tag": tag, "seed": seed, "expanded_prompt_tokens": expanded,
        "images": [str(p) for p in images], "think_chars": len(think.strip()),
        "closed": closed, "payload_present": payload is not None,
        "stats": {k: getattr(out, k, None) for k in
                  ("prompt_tokens", "generation_tokens", "generation_tps", "peak_memory")},
    }
    probe.atomic_write(run_dir / f"{tag}.trace.json",
                       {**record, "raw": text, "think": think, "answer": answer})
    return record, payload, answer


def run_cell(vlm, game: str, arm: str, run_dir: Path, seed_base: int,
             dry_run: bool) -> dict[str, Any]:
    packet = load_packet(game)
    bid = packet["blind_id"]
    tag = f"{bid}_{arm}"
    items, images = initial_turn(game, arm, packet)
    cell: dict[str, Any] = {
        "game_blind": bid, "arm": arm,
        "packet_pages": packet["manifest"]["page_count"],
        "packet_visual_tokens": packet["manifest"]["visual_tokens_total"],
    }
    if dry_run:
        text_chars = sum(len(i["text"]) for i in items if i["type"] == "text")
        cell.update(dry_run=True, text_chars=text_chars, images=len(images))
        return cell

    messages = [{"role": "user", "content": items}]
    record, payload, answer = ask_chat(
        vlm, messages, images, seed=probe.seed_for(seed_base, tag + "_r0"),
        max_tokens=MAX_ANSWER_TOKENS, run_dir=run_dir, tag=tag + "_r0",
    )
    cell["pre_probe_answer"] = payload
    cell["rounds"] = [record]
    if payload is None:
        cell["outcome"] = "missing_output"
        return cell

    if arm == "P":
        session = ProbeSession(game, run_dir / f"{tag}_probe_assets")
        for round_no in range(1, INTERACTION_ROUNDS + 1):
            feedback_items: list[dict[str, str]] = []
            feedback_images: list[Path] = []
            for req in (payload.get("retrieval_requests") or [])[:RETRIEVALS_PER_ROUND]:
                result = session.retrieve(str(req.get("op", "")), *[str(a) for a in (req.get("args") or [])])
                feedback_items.append({"type": "text", "text":
                                       f"RETRIEVAL {req.get('op')}: "
                                       + (result.get("text") or result.get("error", ""))})
                for img in result.get("images", []):
                    feedback_items.append({"type": "image"})
                    feedback_images.append(Path(img))
            np_ = payload.get("next_probe") or {}
            action = (np_.get("action") or {})
            if np_.get("start_state_id") and isinstance(action.get("id"), int):
                click = action.get("click")
                result = session.probe(str(np_["start_state_id"]), int(action["id"]),
                                       tuple(click) if click else None)
                feedback_items.append({"type": "text", "text":
                                       "PROBE RESULT: " + (result.get("text") or result.get("error", ""))})
                for img in result.get("images", []):
                    feedback_items.append({"type": "image"})
                    feedback_images.append(Path(img))
            if not feedback_items:
                break
            messages.append({"role": "assistant", "content": answer})
            feedback_items.append({"type": "text", "text":
                                   "Update your analysis. Answer with the same JSON "
                                   "object schema, complete, on the last line."})
            messages.append({"role": "user", "content": feedback_items})
            images = images + feedback_images
            record, payload, answer = ask_chat(
                vlm, messages, images,
                seed=probe.seed_for(seed_base, f"{tag}_r{round_no}"),
                max_tokens=MAX_ANSWER_TOKENS, run_dir=run_dir, tag=f"{tag}_r{round_no}",
            )
            cell["rounds"].append(record)
            if payload is None:
                cell["outcome"] = "missing_output_in_round"
                cell["final_answer"] = None
                cell["probe_log"] = session.log
                return cell
        cell["probe_log"] = session.log
        cell["probes_spent"] = session.probes_spent

    cell["final_answer"] = payload
    cell["outcome"] = "answered"
    return cell


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(PILOT_GAMES))
    parser.add_argument("--arms", nargs="*", default=["T", "V", "P"],
                        choices=["T", "V", "P"])
    parser.add_argument("--model", type=Path, default=probe.MODEL)
    parser.add_argument("--seed", type=int, default=4)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true",
                        help="assemble every cell, count text/images, no model")
    parser.add_argument("--verify-shards", action="store_true",
                        help="full checkpoint shard verification against the certificate")
    args = parser.parse_args()

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    out_path = args.out or run_dir / "cells.json"

    doc: dict[str, Any] = {
        "note": "notes/qwen-3.8-slice4-design.md -> pilot runner",
        "git": probe.capture_git_state(),
        "seed_base": args.seed,
        "arms": args.arms,
        "run_dir": str(run_dir),
        "budgets": {"answer_tokens": MAX_ANSWER_TOKENS,
                    "interaction_rounds": INTERACTION_ROUNDS,
                    "retrievals_per_round": RETRIEVALS_PER_ROUND},
        "cells": [],
    }
    vlm = None
    if not args.dry_run:
        doc["certificate"] = verify_certificate(args.model, args.verify_shards)
        print(f"certificate verified; loading {args.model.name} ...", flush=True)
        vlm = probe.Vlm(args.model)
    for game in args.games:
        for arm in args.arms:
            cell = run_cell(vlm, game, arm, run_dir, args.seed, args.dry_run)
            doc["cells"].append(cell)
            probe.atomic_write(out_path, doc)
            print(f"{game:5s} arm {arm}: "
                  + (f"dry text {cell['text_chars']:6,}ch images {cell['images']:2d}"
                     if args.dry_run else cell.get("outcome", "?")), flush=True)
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
