#!/usr/bin/env python3
"""Slice-4 bounded retrieval + active probes.

`notes/qwen-3.8-slice4-design.md` → section 7. Two source-free capabilities the
runner exposes to Qwen mid-conversation:

RETRIEVAL (runner-budgeted to one request/round, stored autonomous evidence only):
  SHOW_FRAME <tid>              one transition's settled post board, full plate
  SHOW_TRANSITION <tid>         the five-panel exhibit for one transition
  SHOW_EPISODE <tid> <n>        storyboard of n settled frames starting at tid
  SHOW_ACTION_CONTRAST <action> one effect and one no-effect case for an action
  SHOW_COLOUR_HISTORY <colour_id>  storyboard of frames where that ARC colour changed

ACTIVE PROBES (budget, default 3): replay the recapture-verified autonomous prefix
that reaches a named state, perform the requested action, and return every raw frame
the engine emits on one audited exact nearest-neighbour storyboard. Every prefix
step must match both
the stored post board and the recaptured raw-frame sequence. Any mismatch, unknown
tid, malformed action/click, or redundant repeat consumes budget and returns an exact
failure record — never a silently repaired substitute. `replayable_tids()` and
`control_request(round_no, seed)` expose the same verified pool for control arms.

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
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any, Callable

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_packet as spk  # noqa: E402  (blind evidence assembly + allowlisted reads)
import s4_render as sr  # noqa: E402
from s4_recapture import Engine  # noqa: E402

ROOT = spk.ROOT
DEFAULT_BUDGET = 3
MAX_EPISODE_FRAMES = 16
MAX_COMPONENT_HISTORY_FRAMES = 12
# A live intervention always occupies exactly one image slot. The storyboard keeps
# every returned frame and selects the largest exact nearest-neighbour cell scale
# whose processor geometry fits this per-probe ceiling. Reserving this maximum three
# times prevents animation-rich actions from selectively exhausting the interactive
# arms' image or visual-token budget.
PROBE_RESULT_PAGE_MAX_VISUAL_TOKENS = 2_112
# The serving gate certifies exact localization only down to four rendered pixels
# per source cell.  A longer animation must therefore fail as an instrument/budget
# error instead of silently degrading into an uncertified 2 px or 1 px carrier.
PROBE_STORYBOARD_CELL_PX = (16, 8, 4)
RETRIEVAL_RESULT_MAX_IMAGES = 1
RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS = 1_200


def bounded_storyboard(
    frames: list[np.ndarray], *, max_visual_tokens: int
) -> tuple[Any, int, int, int]:
    """Render every 64x64 frame once at the largest scale fitting a hard cap."""
    if not frames:
        raise ValueError("bounded storyboard needs at least one frame")
    selected: tuple[int, int, int] | None = None
    for cell_px in PROBE_STORYBOARD_CELL_PX:
        candidates: list[tuple[int, int, int]] = []
        for cols in range(1, len(frames) + 1):
            rows = (len(frames) + cols - 1) // cols
            width = cols * (64 * cell_px) + (cols + 1) * 8
            height = rows * (64 * cell_px + 16) + (rows + 1) * 8
            width += (-width) % 32
            height += (-height) % 32
            candidates.append((abs(width - height), spk.visual_tokens(width, height), cols))
        fitting = [candidate for candidate in candidates if candidate[1] <= max_visual_tokens]
        if fitting:
            _, visual_tokens, cols = min(fitting, key=lambda value: value)
            selected = (cell_px, cols, visual_tokens)
            break
    if selected is None:
        raise RuntimeError(
            f"{len(frames)} frames cannot fit one exact storyboard under "
            f"{max_visual_tokens} visual tokens"
        )
    cell_px, cols, predicted_tokens = selected
    page = sr.storyboard(frames, cols=cols, cell_px=cell_px).image
    if spk.visual_tokens(page.width, page.height) != predicted_tokens:
        raise RuntimeError("storyboard token accounting drift")
    return page, cell_px, cols, predicted_tokens


def canonical_sha256(value: Any) -> str:
    """Stable full digest for grids, requests and provenance payloads."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalise_grid(grid: Any, *, label: str) -> list[list[int]]:
    """Require an exact 64x64 integer ARC grid; never coerce malformed frames."""
    array = np.asarray(grid)
    if array.shape != (64, 64):
        raise ValueError(f"{label}: grid shape {array.shape} != (64, 64)")
    if not np.issubdtype(array.dtype, np.integer):
        raise ValueError(f"{label}: grid dtype {array.dtype} is not integral")
    if np.any(array < 0) or np.any(array > 15):
        raise ValueError(f"{label}: grid contains a colour outside 0..15")
    return [[int(value) for value in row] for row in array.tolist()]


def json_safe(value: Any) -> Any:
    """Retain malformed request evidence without making the session log unwritable."""
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return {"python_type": type(value).__name__, "repr": repr(value)}
    return value


def response_metadata(response: Any, *, label: str) -> tuple[str, int]:
    """Read exact observable outcome fields from object- or mapping-style responses."""
    if isinstance(response, dict):
        raw_state = response.get("state")
        raw_levels = response.get("levels_completed")
    else:
        raw_state = getattr(response, "state", None)
        raw_levels = getattr(response, "levels_completed", None)
    state = getattr(raw_state, "value", raw_state)
    if state is None or not str(state):
        raise ValueError(f"{label}: response state is missing")
    if isinstance(raw_levels, bool) or not isinstance(raw_levels, (int, np.integer)):
        raise ValueError(f"{label}: levels_completed is missing or non-integral")
    return str(state), int(raw_levels)


class ProbeSession:
    """One game's retrieval + probe surface. Every call is logged verbatim."""

    def __init__(
        self,
        game: str,
        out_dir: Path,
        budget: int = DEFAULT_BUDGET,
        *,
        evidence: dict[str, Any] | None = None,
        recapture_records: list[dict[str, Any]] | None = None,
        engine_factory: Callable[[str], Any] = Engine,
        enforce_engine_identity: bool | None = None,
    ):
        if type(budget) is not int or budget < 0:
            raise ValueError(f"probe budget must be a non-negative integer, got {budget!r}")
        self.game = game
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._evidence_injected = evidence is not None
        self._enforce_engine_identity = (
            not self._evidence_injected
            if enforce_engine_identity is None else bool(enforce_engine_identity)
        )
        self.evidence = evidence if evidence is not None else spk.load_evidence(game)
        self.transitions = [dict(t) for t in spk.transition_stream(self.evidence)]
        self.by_tid = {t["tid"]: t for t in self.transitions}
        self.budget = budget
        self.probes_spent = 0
        self.log: list[dict[str, Any]] = []
        self._engine_factory = engine_factory
        self._engine: Any | None = None
        self._engine_identity: dict[str, Any] | None = None
        self._probe_keys: set[tuple] = set()
        self._asset_counter = 0
        self._transition_meta: dict[str, dict[str, Any]] = {}
        self._recapture_by_store_step: dict[int, dict[str, Any]] = {}
        self._store_step_meta: dict[int, dict[str, Any]] = {}
        self._replayable_tids: list[str] = []
        self._recapture_root_sha256 = self._load_recapture_records(recapture_records)
        self._index_transitions()
        self._index_verified_prefixes()
        self.provenance = self._build_provenance()

    # ------------------------------------------------------------ evidence identity

    def _load_recapture_records(
        self, injected: list[dict[str, Any]] | None
    ) -> str:
        """Load only verified recapture facts and bind them to their source files."""
        records: list[tuple[dict[str, Any], str, str]] = []
        source_digests: dict[str, str] = {}
        if injected is not None:
            for position, record in enumerate(injected):
                source = f"injected_episode_{position}"
                digest = canonical_sha256(record)
                source_digests[source] = digest
                records.append((record, source, digest))
        else:
            manifest = self.evidence.get("recap") or {}
            if manifest.get("format_version") != 2:
                raise RuntimeError("recapture manifest is not closure-grade format v2")
            recap_dir = Path(self.evidence["recap_dir"])
            for summary in manifest.get("episodes") or []:
                name = summary.get("file")
                if not isinstance(name, str) or Path(name).name != name:
                    raise RuntimeError(f"malformed recapture filename {name!r}")
                raw = spk.read_allowlisted(recap_dir / name)
                digest = hashlib.sha256(raw.encode()).hexdigest()
                expected = summary.get("sha256")
                if not isinstance(expected, str) or len(expected) != 64 or digest != expected:
                    raise RuntimeError(
                        f"recapture digest mismatch for episode {summary.get('episode_index')!r}"
                    )
                parsed = json.loads(raw)
                if parsed.get("format_version") != 2:
                    raise RuntimeError(f"recapture episode {name} is not format v2")
                if parsed.get("episode_index") != summary.get("episode_index"):
                    raise RuntimeError(f"recapture episode-index mismatch in {name}")
                source_digests[name] = digest
                records.append((parsed, name, digest))

        for record, source, source_sha256 in records:
            episode_index = record.get("episode_index")
            if type(episode_index) is not int or episode_index < 0:
                raise RuntimeError(f"malformed recapture episode index {episode_index!r}")
            for step in record.get("steps") or []:
                store_step = step.get("store_step")
                if type(store_step) is not int or store_step in self._recapture_by_store_step:
                    raise RuntimeError(f"invalid/duplicate recapture store step {store_step!r}")
                frames = [
                    normalise_grid(frame, label=f"recapture store step {store_step} frame {i}")
                    for i, frame in enumerate(step.get("frames") or [])
                ]
                if step.get("frame_count") != len(frames):
                    raise RuntimeError(
                        f"recapture frame-count mismatch at store step {store_step}"
                    )
                frame_sha256 = [canonical_sha256(frame) for frame in frames]
                reached_sha256 = frame_sha256[-1] if frame_sha256 else None
                settled_digest = step.get("settled_grid_sha256", step.get("settled_digest"))
                if injected is None and settled_digest is not None and (
                    not isinstance(settled_digest, str) or len(settled_digest) != 64
                ):
                    raise RuntimeError(
                        f"recapture settled digest is not full SHA-256 at store step {store_step}"
                    )
                if settled_digest != reached_sha256:
                    raise RuntimeError(
                        f"recapture settled digest mismatch at store step {store_step}"
                    )
                response_state = step.get("response_state")
                levels_completed = step.get("levels_completed")
                store_index = step.get("store_index")
                if injected is None:
                    if not isinstance(response_state, str) or not response_state:
                        raise RuntimeError(
                            f"recapture response state missing at store step {store_step}"
                        )
                    if type(levels_completed) is not int:
                        raise RuntimeError(
                            f"recapture level count missing at store step {store_step}"
                        )
                    if type(store_index) is not int:
                        raise RuntimeError(
                            f"recapture store index missing at store step {store_step}"
                        )
                self._recapture_by_store_step[store_step] = {
                    "episode_index": episode_index,
                    "episode_step": step.get("episode_step"),
                    "store_index": store_index,
                    "store_step": store_step,
                    "action": step.get("action"),
                    "verified": step.get("verified") is True,
                    "frame_count": len(frames),
                    "raw_frame_sha256": frame_sha256,
                    "reached_sha256": reached_sha256,
                    "response_state": response_state,
                    "levels_completed": levels_completed,
                    "source": source,
                    "source_sha256": source_sha256,
                }
        return canonical_sha256(source_digests)

    def _index_transitions(self) -> None:
        """Attach original row/episode identity and correct boundary pre-states."""
        performs = self.evidence["performs"]
        states = self.evidence["states"]
        store_rows: dict[int, dict[str, Any]] = {}
        episode_index = -1
        episode_start = -1
        for index, row in enumerate(performs):
            episode_step = row.get("episode_step")
            if type(episode_step) is not int or episode_step < 0:
                raise RuntimeError(f"store row {index}: invalid episode_step {episode_step!r}")
            if episode_step == 0:
                episode_index += 1
                episode_start = index
            if episode_index < 0 or index - episode_start != episode_step:
                raise RuntimeError(
                    f"store row {index}: non-contiguous episode_step {episode_step}"
                )
            store_rows[index] = {
                "source": "store",
                "source_index": index,
                "episode_index": episode_index,
                "episode_step": episode_step,
                "episode_start": episode_start,
            }

        kaggle_rows: dict[int, dict[str, Any]] = {}
        episode_index = -1
        episode_step = -1
        for index, row in enumerate(self.evidence["kaggle"]):
            if row.get("action") == "RESET" or episode_index < 0:
                episode_index += 1
                episode_step = 0
            else:
                episode_step += 1
            kaggle_rows[index] = {
                "source": "kaggle",
                "source_index": index,
                "episode_index": episode_index,
                "episode_step": episode_step,
            }

        for stream_index, transition in enumerate(self.transitions):
            tid = transition["tid"]
            if tid.startswith("S"):
                try:
                    source_index = int(tid[1:])
                except ValueError as exc:
                    raise RuntimeError(f"malformed store transition id {tid!r}") from exc
                if source_index not in store_rows:
                    raise RuntimeError(f"store transition {tid} has no original row")
                meta = dict(store_rows[source_index])
                row = performs[source_index]
                if meta["episode_step"] == 0:
                    transition["pre"] = None
                else:
                    previous_digest = performs[source_index - 1].get("post")
                    transition["pre"] = states.get(previous_digest) if previous_digest else None
                transition["post"] = states.get(row.get("post"))
            elif tid.startswith("K"):
                try:
                    # K ids are source-local, preserving the original normalized
                    # observation-row index even when another source has gaps.
                    source_index = int(tid[1:])
                except ValueError as exc:
                    raise RuntimeError(f"malformed Kaggle transition id {tid!r}") from exc
                if source_index not in kaggle_rows:
                    raise RuntimeError(f"Kaggle transition {tid} has no original row")
                meta = dict(kaggle_rows[source_index])
                row = self.evidence["kaggle"][source_index]
                if meta["episode_step"] == 0:
                    transition["pre"] = None
                else:
                    transition["pre"] = self.evidence["kaggle"][source_index - 1]["board"]
                transition["post"] = row["board"]
            else:
                raise RuntimeError(f"unknown transition id namespace {tid!r}")
            meta["stream_index"] = stream_index
            meta["episode_key"] = [meta["source"], meta["episode_index"]]
            self._transition_meta[tid] = meta

    def _index_verified_prefixes(self) -> None:
        """A target is replayable only if every preceding episode step is certified."""
        prefix_verified = False
        performs = self.evidence["performs"]
        states = self.evidence["states"]
        for index, row in enumerate(performs):
            episode_step = row["episode_step"]
            if episode_step == 0:
                prefix_verified = True
            post_ref = row.get("post")
            expected = states.get(post_ref) if post_ref else None
            expected_sha256 = None
            if expected is not None:
                expected_sha256 = canonical_sha256(
                    normalise_grid(expected, label=f"store row {index} expected post")
                )
            recapture = self._recapture_by_store_step.get(row.get("step"))
            action_match = bool(recapture and recapture.get("action") == row.get("action"))
            episode_match = bool(
                recapture
                and recapture.get("episode_index")
                == self._episode_index_for_store_row(index)
                and recapture.get("episode_step") == episode_step
            )
            recapture_post_match = bool(
                recapture
                and expected_sha256 is not None
                and recapture.get("reached_sha256") == expected_sha256
            )
            recapture_state = recapture.get("response_state") if recapture else None
            recapture_levels = recapture.get("levels_completed") if recapture else None
            checks = {
                "stored_post_present": expected_sha256 is not None,
                "recapture_present": recapture is not None,
                "recapture_verified": bool(recapture and recapture.get("verified")),
                "store_index_match": bool(
                    recapture and recapture.get("store_index") == index
                ),
                "action_match": action_match,
                "episode_match": episode_match,
                "recapture_state_present": isinstance(recapture_state, str)
                and bool(recapture_state),
                "recapture_levels_present": type(recapture_levels) is int,
                "response_state_match": bool(
                    recapture
                    and row.get("state") is not None
                    and recapture_state == str(row.get("state"))
                ),
                "levels_completed_match": bool(
                    recapture
                    and row.get("levels") is not None
                    and recapture_levels == int(row.get("levels"))
                ),
                "recapture_has_settled_frame": bool(
                    recapture and recapture.get("frame_count", 0) > 0
                ),
                "recapture_post_match": recapture_post_match,
            }
            step_verified = all(checks.values())
            prefix_verified = prefix_verified and step_verified
            meta = self._store_row_identity(index)
            self._store_step_meta[index] = {
                **meta,
                "tid": f"S{index:05d}",
                "store_step": row.get("step"),
                "action": list(row["action"]),
                "post_ref": post_ref,
                "expected_sha256": expected_sha256,
                "recapture": recapture,
                "static_checks": checks,
                "step_verified": step_verified,
                "prefix_verified": prefix_verified,
            }
            tid = f"S{index:05d}"
            if prefix_verified and tid in self.by_tid:
                self._replayable_tids.append(tid)

    def _store_row_identity(self, index: int) -> dict[str, Any]:
        tid = f"S{index:05d}"
        meta = self._transition_meta.get(tid)
        if meta is not None:
            return {
                "source_index": index,
                "episode_index": meta["episode_index"],
                "episode_step": meta["episode_step"],
                "episode_start": index - meta["episode_step"],
            }
        row = self.evidence["performs"][index]
        episode_start = index - row["episode_step"]
        episode_index = sum(
            1
            for candidate in self.evidence["performs"][: episode_start + 1]
            if candidate.get("episode_step") == 0
        ) - 1
        return {
            "source_index": index,
            "episode_index": episode_index,
            "episode_step": row["episode_step"],
            "episode_start": episode_start,
        }

    def _episode_index_for_store_row(self, index: int) -> int:
        return self._store_row_identity(index)["episode_index"]

    def _build_provenance(self) -> dict[str, Any]:
        try:
            arcengine_version = package_version("arcengine")
        except PackageNotFoundError:
            arcengine_version = None
        input_identity = self.evidence.get("input_identity")
        return {
            "game_blind": spk.blind_id(self.game),
            "budget": self.budget,
            "live_engine_identity_required": self._enforce_engine_identity,
            "input_bundle_sha256": (
                canonical_sha256(input_identity) if isinstance(input_identity, dict) else None
            ),
            "evidence_sha256": {
                key: canonical_sha256(self.evidence[key])
                for key in ("performs", "states", "kaggle", "recap")
            },
            "recapture_root_sha256": self._recapture_root_sha256,
            "code_sha256": {
                "s4_probes": sha256_file(Path(__file__)),
                "s4_packet": sha256_file(HARNESS / "s4_packet.py"),
                "s4_render": sha256_file(HARNESS / "s4_render.py"),
                "s4_recapture": sha256_file(HARNESS / "s4_recapture.py"),
                "gi2_replay": sha256_file(HARNESS / "gi2_replay.py"),
            },
            "arcengine_version": arcengine_version,
            "replayable_state_count": len(self._replayable_tids),
            "probe_page_rules": {
                "images_per_probe": 1,
                "all_frames_required": True,
                "cell_px_candidates": list(PROBE_STORYBOARD_CELL_PX),
                "minimum_pixels": 65_536,
                "maximum_visual_tokens_per_probe": PROBE_RESULT_PAGE_MAX_VISUAL_TOKENS,
            },
        }

    def _ensure_engine(self) -> Any:
        if self._engine is None:
            engine = self._engine_factory(self.game)
            live_source_identity = None
            if self._enforce_engine_identity:
                recapture_provenance = (
                    (self.evidence.get("recap") or {}).get("provenance") or {}
                )
                expected_engine = recapture_provenance.get("engine")
                if not isinstance(expected_engine, dict):
                    raise RuntimeError("recapture lacks engine-file provenance for live probes")
                expected = expected_engine.get("game_source")
                if not isinstance(expected, dict):
                    raise RuntimeError("recapture lacks the game-source identity for live probes")
                source_path = getattr(engine, "source_path", None)
                if not isinstance(source_path, Path):
                    source_path = Path(source_path) if isinstance(source_path, str) else None
                if source_path is None or not source_path.is_file():
                    raise RuntimeError("live probe engine does not expose its game source")
                live_source_identity = {
                    "path": str(source_path.resolve()),
                    "sha256": sha256_file(source_path),
                    "bytes": source_path.stat().st_size,
                }
                if live_source_identity != expected:
                    raise RuntimeError(
                        "live probe game source differs from the recapture-bound source"
                    )
                for name, path in (
                    ("gi2_replay", HARNESS / "gi2_replay.py"),
                    ("recapture_script", HARNESS / "s4_recapture.py"),
                ):
                    expected_component = expected_engine.get(name)
                    live_component = {
                        "path": str(path.resolve()),
                        "sha256": sha256_file(path),
                    }
                    if expected_component != live_component:
                        raise RuntimeError(
                            f"live probe {name} differs from the recapture-bound code"
                        )
                expected_versions = recapture_provenance.get("versions") or {}
                expected_arcengine = expected_versions.get("arcengine")
                if (not isinstance(expected_arcengine, str)
                        or package_version("arcengine") != expected_arcengine):
                    raise RuntimeError(
                        "live arcengine version differs from the recapture-bound runtime"
                    )
            driver = getattr(engine, "driver", None)
            self._engine_identity = {
                "wrapper": (
                    f"{type(engine).__module__}.{type(engine).__qualname__}"
                ),
                "driver": (
                    f"{type(driver).__module__}.{type(driver).__qualname__}"
                    if driver is not None else None
                ),
                "arcengine_version": self.provenance["arcengine_version"],
                "game_source": live_source_identity,
            }
            self._engine = engine
        return self._engine

    def verify_live_engine_identity(self) -> dict[str, Any]:
        """Load no episode and perform no action; only verify the live replay identity."""
        self._ensure_engine()
        if not isinstance(self._engine_identity, dict):
            raise RuntimeError("live probe engine identity was not recorded")
        return dict(self._engine_identity)

    def _save_audited(
        self, image: Any, stem: str, kind: str, **extra: Any
    ) -> dict[str, Any]:
        width, height = image.size
        if width % 32 or height % 32:
            raise RuntimeError(f"{stem}: image dimensions {(width, height)} are not multiples of 32")
        if width * height < 65_536:
            raise RuntimeError(f"{stem}: image is below the 65,536-pixel processor minimum")
        visual_tokens = spk.visual_tokens(width, height)
        if visual_tokens > spk.MAX_VISUAL_TOKENS:
            raise RuntimeError(
                f"{stem}: {visual_tokens} visual tokens exceed {spk.MAX_VISUAL_TOKENS}"
            )
        self._asset_counter += 1
        safe_stem = "".join(char if char.isalnum() or char in "_-" else "_" for char in stem)
        path = self.out_dir / f"{self._asset_counter:03d}_{safe_stem}.png"
        image.save(path)
        return {
            "path": str(path),
            "kind": kind,
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "width": width,
            "height": height,
            "visual_tokens": visual_tokens,
            **extra,
        }

    # ------------------------------------------------------------------ retrieval

    @staticmethod
    def _validate_retrieval_result(result: dict[str, Any]) -> None:
        if result.get("ok") is not True:
            return
        images = result.get("images") or []
        audits = result.get("image_audit") or []
        if len(images) != len(audits) or len(images) > RETRIEVAL_RESULT_MAX_IMAGES:
            raise RuntimeError(
                "successful retrieval must return at most one fully audited image"
            )
        if any(
            type(audit.get("visual_tokens")) is not int
            or audit["visual_tokens"] > RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS
            for audit in audits
        ):
            raise RuntimeError("retrieval result exceeds its visual-token envelope")

    def retrieve(self, op: str, *args: str) -> dict[str, Any]:
        handler = {
            "SHOW_FRAME": self._show_frame,
            "SHOW_TRANSITION": self._show_transition,
            "SHOW_EPISODE": self._show_episode,
            "SHOW_ACTION_CONTRAST": self._show_action_contrast,
            "SHOW_COLOUR_HISTORY": self._show_colour_history,
        }.get(op)
        internal_error = None
        if handler is None:
            result = {"ok": False, "error": f"unknown retrieval op {op!r}"}
        else:
            try:
                result = handler(*args)
                self._validate_retrieval_result(result)
            except (KeyError, TypeError, ValueError) as exc:
                # These are malformed/unsatisfied model requests.  Preserve exact
                # diagnostics in the local log, but do not expose Python internals
                # or store details through the model-visible feedback channel.
                internal_error = f"{type(exc).__name__}: {exc}"
                result = {
                    "ok": False,
                    "error": (
                        f"{op}: request is invalid or absent from the frozen observation "
                        "store; it was not rewritten"
                    ),
                    "error_type": type(exc).__name__,
                }
            except Exception as exc:
                internal_error = f"{type(exc).__name__}: {exc}"
                result = {
                    "ok": False,
                    "instrument_error": True,
                    "failure_stage": "retrieval_execute",
                    "error": "retrieval instrument failed; no observation was returned",
                }
        log_entry = {"kind": "retrieval", "op": op, "args": list(args), **result}
        if internal_error is not None:
            log_entry["internal_error"] = internal_error
        self.log.append(log_entry)
        return result

    def _show_frame(self, tid: str) -> dict[str, Any]:
        t = self.by_tid[tid]
        img = sr.render_board(np.asarray(t["post"])).image
        audit = self._save_audited(img, f"frame_{tid}", "retrieval_frame", tid=tid)
        click = f" click={t['click']}" if t["click"] is not None else " click=null"
        return {
            "ok": True,
            "images": [audit["path"]],
            "image_audit": [audit],
            "text": (
                f"settled board after transition {tid}: {t['action']}{click} [OBSERVED]"
            ),
        }

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
        audit = self._save_audited(
            image, f"transition_{tid}", "retrieval_transition", tid=tid
        )
        return {
            "ok": True,
            "images": [audit["path"]],
            "image_audit": [audit],
            "text": f"transition {tid}: action {t['action']}"
                    f"{' click ' + str(t['click']) if t['click'] else ''} [OBSERVED]",
        }

    def _show_episode(self, tid: str, count: str = "8") -> dict[str, Any]:
        if tid not in self.by_tid:
            raise KeyError(tid)
        try:
            n = int(count)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"episode count {count!r} is not an integer") from exc
        if not 1 <= n <= MAX_EPISODE_FRAMES:
            raise ValueError(
                f"episode count {n} outside 1..{MAX_EPISODE_FRAMES}; request was not rewritten"
            )
        start = self._transition_meta[tid]["stream_index"]
        episode_key = self._transition_meta[tid]["episode_key"]
        selected: list[dict[str, Any]] = []
        boundary_tid = None
        for transition in self.transitions[start:]:
            if self._transition_meta[transition["tid"]]["episode_key"] != episode_key:
                boundary_tid = transition["tid"]
                break
            selected.append(transition)
            if len(selected) == n:
                break
        frames = [np.asarray(t["post"]) for t in selected]
        ids = [t["tid"] for t in selected]
        image, cell_px, cols, _ = bounded_storyboard(
            frames, max_visual_tokens=RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS
        )
        audit = self._save_audited(
            image,
            f"episode_{tid}_{n}",
            "retrieval_episode",
            tids=ids,
            requested_count=n,
            returned_count=len(ids),
            storyboard_cell_px=cell_px,
            storyboard_cols=cols,
        )
        boundary_truncated = len(selected) < n
        boundary_description = (
            f"before {boundary_tid}" if boundary_tid is not None
            else "at the end of this source episode"
        )
        suffix = (
            f"; stopped at the episode/source boundary {boundary_description} "
            f"and returned {len(ids)} of {n} requested frames"
            if boundary_truncated else ""
        )
        frame_mapping = "; ".join(
            f"[{index}] {transition['tid']} settled after {transition['action']} "
            f"click={transition['click'] if transition['click'] is not None else 'null'}"
            for index, transition in enumerate(selected)
        )
        return {
            "ok": True,
            "images": [audit["path"]],
            "image_audit": [audit],
            "episode_tids": ids,
            "requested_count": n,
            "returned_count": len(ids),
            "boundary_truncated": boundary_truncated,
            "boundary_tid": boundary_tid,
            "text": f"episode frames in order: {frame_mapping} [OBSERVED]{suffix}",
        }

    def _show_action_contrast(self, action: str) -> dict[str, Any]:
        matched, _ = spk._matched_action_cases(self.transitions)
        cases = matched.get(action)
        if cases is None:
            return {"ok": False, "error": f"no observations of action {action}"}
        effect, none = cases["effect"], cases["no_effect"]
        if effect is None and none is None:
            return {"ok": False, "error": f"no observations of action {action}"}
        contrast_pages, contrast_tids, parts = [], [], []
        for label, t in (("effect", effect), ("no-effect", none)):
            if t is None:
                parts.append(f"{label}: not observed")
                continue
            panels = sr.exhibit(np.asarray(t["pre"]), np.asarray(t["post"]), t["action"],
                                tuple(t["click"]) if t["click"] else None)
            settled = sr.render_board(np.asarray(t["post"]))
            image = spk.compose_row(
                [spk.scaled(panels["context"], 320), spk.scaled(settled, 320),
                 spk.scaled(panels["diff_mask"], 320)],
                [f"{label} pre ({t['tid']})", "settled post", "changed cells"],
            )
            contrast_pages.append(image)
            contrast_tids.append(t["tid"])
            parts.append(f"{label}: {t['tid']}")
        combined = spk._stack(contrast_pages, gap=8)
        audit = self._save_audited(
            combined,
            f"contrast_{action}",
            "retrieval_action_contrast",
            action=action,
            tids=contrast_tids,
        )
        return {
            "ok": True,
            "images": [audit["path"]],
            "image_audit": [audit],
            "contrast_tids": contrast_tids,
            "text": (
                f"action {action} deterministic matched-pre contrast — {'; '.join(parts)}; "
                f"all-observation counts={cases['counts']}; matched pre-board cell-Hamming "
                f"distance={cases['pre_board_hamming_distance']} [OBSERVED / DERIVED-EXACT]"
            ),
        }

    def _show_colour_history(self, colour: str) -> dict[str, Any]:
        c = int(colour)
        if not 0 <= c <= 15:
            return {"ok": False, "error": f"colour id {colour} outside 0..15"}
        hits = []
        for t in self.transitions:
            if t["pre"] is None:
                continue
            pre = np.asarray(t["pre"])
            post = np.asarray(t["post"])
            if ((pre == c) != (post == c)).any():
                hits.append((t["tid"], post))
        if not hits:
            return {"ok": False, "error": f"colour {c} never changes in this record"}
        shown = hits[:MAX_COMPONENT_HISTORY_FRAMES]
        frames = [h[1] for h in shown]
        image, cell_px, cols, _ = bounded_storyboard(
            frames, max_visual_tokens=RETRIEVAL_RESULT_PAGE_MAX_VISUAL_TOKENS
        )
        tids = [h[0] for h in shown]
        audit = self._save_audited(
            image,
            f"colour_{c}_history",
            "retrieval_colour_history",
            colour_id=c,
            tids=tids,
            storyboard_cell_px=cell_px,
            storyboard_cols=cols,
        )
        truncated = len(hits) > len(shown)
        suffix = (
            f"; showing the first {len(shown)} of {len(hits)} exact within-episode changes"
            if truncated else ""
        )
        history_mapping = "; ".join(
            f"[{index}] {tid} settled after {self.by_tid[tid]['action']} "
            f"click={self.by_tid[tid]['click'] if self.by_tid[tid]['click'] is not None else 'null'}"
            for index, tid in enumerate(tids)
        )
        return {
            "ok": True,
            "images": [audit["path"]],
            "image_audit": [audit],
            "history_tids": tids,
            "total_hits": len(hits),
            "returned_hits": len(shown),
            "truncated": truncated,
            "text": (
                f"frames where colour {c} changed: {history_mapping} "
                f"[DERIVED-EXACT]{suffix}"
            ),
        }

    # ------------------------------------------------------------------ probes

    def _prefix_to(self, tid: str) -> list[dict[str, Any]] | None:
        """Return the original-row prefix only when every step has recapture proof."""
        target = self._store_step_meta.get(
            int(tid[1:]) if isinstance(tid, str) and tid.startswith("S")
            and tid[1:].isdigit() else -1
        )
        if target is None or tid not in self.by_tid or not target["prefix_verified"]:
            return None
        return [
            self._store_step_meta[index]
            for index in range(target["episode_start"], target["source_index"] + 1)
        ]

    def replayable_tids(self) -> list[str]:
        """Stable original store TIDs whose full prefixes passed static recapture gates."""
        return list(self._replayable_tids)

    def control_capacity(self) -> int:
        """Number of distinct verified state/action control requests available."""
        return len(self._replayable_tids) * len(self._verified_action_candidates())

    @staticmethod
    def _validate_action_click(action_id: Any, click: Any) -> str | None:
        if type(action_id) is not int:
            return f"action id must be an integer (JSON booleans are invalid), got {action_id!r}"
        if not 0 <= action_id <= 7:
            return f"action id {action_id!r} outside 0..7"
        if click is not None:
            if type(click) not in (list, tuple):
                return (
                    "click must be null or an exact two-element JSON list/tuple, "
                    f"got {type(click).__name__}"
                )
            if len(click) != 2:
                return f"click must contain exactly two coordinates, got {click!r}"
            if any(type(value) is not int for value in click):
                return f"click coordinates must be integers (JSON booleans are invalid), got {click!r}"
            if any(not 0 <= value < 64 for value in click):
                return f"click coordinates {click!r} outside the 64x64 board"
        if action_id == 6 and click is None:
            return "action A6 requires an explicit (row, col) click"
        if action_id != 6 and click is not None:
            return f"action A{action_id} does not accept click coordinates"
        return None

    def _verified_action_candidates(self) -> list[tuple[int, tuple[int, int] | None]]:
        candidates: set[tuple[int, tuple[int, int] | None]] = set()
        for step in self._store_step_meta.values():
            if not step["step_verified"]:
                continue
            action_id, row, col = step["action"]
            if action_id == 0:  # a reset is not an informative active control probe
                continue
            click = None if row is None else (row, col)
            if self._validate_action_click(action_id, click) is None:
                candidates.add((action_id, click))
        return sorted(candidates, key=lambda item: (item[0], item[1] or (-1, -1)))

    def control_request(self, round_no: int, seed: int) -> dict[str, Any]:
        """Select a pure, deterministic seeded-random request from verified evidence."""
        if type(round_no) is not int or round_no < 0:
            raise ValueError(f"control round must be a non-negative integer, got {round_no!r}")
        if type(seed) is not int or not 0 <= seed < 2 ** 64:
            raise ValueError(f"control seed must be a uint64 integer, got {seed!r}")
        tids = self.replayable_tids()
        actions = self._verified_action_candidates()
        if not tids or not actions:
            raise RuntimeError("no verified state/action candidates for a control probe")
        total = len(tids) * len(actions)
        if round_no >= total:
            raise RuntimeError(f"control round {round_no} exceeds {total} unique requests")

        used: set[int] = set()
        selected = -1
        for candidate_round in range(round_no + 1):
            material = (
                f"{self.provenance['game_blind']}:{seed}:{candidate_round}:control-probe"
            ).encode()
            selected = int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % total
            while selected in used:
                selected = (selected + 1) % total
            used.add(selected)
        tid = tids[selected // len(actions)]
        action_id, click = actions[selected % len(actions)]
        request = {"start_tid": tid, "action_id": action_id, "click": click}
        selection = {
            "kind": "control_selection",
            "round_no": round_no,
            "seed": seed,
            "replayable_state_count": len(tids),
            "verified_action_count": len(actions),
            "request": {
                "start_tid": tid,
                "action_id": action_id,
                "click": list(click) if click is not None else None,
            },
        }
        selection["selection_sha256"] = canonical_sha256(selection)
        self.log.append(selection)
        return request

    def control_probe(self, round_no: int, seed: int) -> dict[str, Any]:
        """Select, record and execute one deterministic verified control request."""
        request = self.control_request(round_no=round_no, seed=seed)
        selection = self.log[-1]
        result = self.probe(**request)
        result["control_selection"] = {
            "round_no": selection["round_no"],
            "seed": selection["seed"],
            "selection_sha256": selection["selection_sha256"],
            "request": selection["request"],
        }
        return result

    @staticmethod
    def _engine_frames(engine: Any, response: Any, *, label: str) -> list[list[list[int]]]:
        raw_frames = engine.frames(response)
        if not isinstance(raw_frames, (list, tuple)):
            raise ValueError(f"{label}: engine frames are not a list/tuple")
        return [
            normalise_grid(frame, label=f"{label} frame {index}")
            for index, frame in enumerate(raw_frames)
        ]

    def _render_probe_pages(
        self, frames: list[list[list[int]]], probe_no: int, start_tid: str
    ) -> list[dict[str, Any]]:
        if not frames:
            return []
        # All source pixels remain exact palette pixels; labels live only in gutters.
        # This makes a 20--28-frame animation one auditable image instead of five to
        # seven images.
        page, cell_px, cols, predicted_tokens = bounded_storyboard(
            [np.asarray(frame) for frame in frames],
            max_visual_tokens=PROBE_RESULT_PAGE_MAX_VISUAL_TOKENS,
        )
        settled_index = len(frames) - 1
        indexes = list(range(len(frames)))
        audit = self._save_audited(
            page,
            f"probe_{probe_no}_{start_tid}_all_frames",
            "probe_raw_frames",
            page_index=0,
            page_count=1,
            all_returned_frames=True,
            frame_indexes=indexes,
            raw_frame_sha256=[canonical_sha256(frame) for frame in frames],
            contains_settled_outcome=settled_index in indexes,
            storyboard_cell_px=cell_px,
            storyboard_cols=cols,
        )
        if audit["visual_tokens"] != predicted_tokens:
            raise RuntimeError("probe storyboard token accounting drift")
        if audit["visual_tokens"] > PROBE_RESULT_PAGE_MAX_VISUAL_TOKENS:
            raise RuntimeError(
                f"probe page geometry drift: {audit['visual_tokens']} > "
                f"{PROBE_RESULT_PAGE_MAX_VISUAL_TOKENS}"
            )
        return [audit]

    def _finish_probe(self, record: dict[str, Any], **updates: Any) -> dict[str, Any]:
        if updates.get("failure_stage") is not None:
            updates["instrument_error"] = True
        record.update(updates)
        record["budget_after"] = self.budget - self.probes_spent
        record["session_provenance"] = self.provenance
        if self._engine_identity is not None:
            record["engine"] = self._engine_identity
        self.log.append(record)
        return record

    def probe(
        self,
        start_tid: str,
        action_id: int,
        click: list[int] | tuple[int, int] | None,
    ) -> dict[str, Any]:
        raw_request = {
            "start_tid": json_safe(start_tid),
            "action_id": json_safe(action_id),
            "click": json_safe(click),
        }
        record: dict[str, Any] = {
            "kind": "probe",
            **raw_request,
            "budget_before": self.budget - self.probes_spent,
            "request_sha256": canonical_sha256(raw_request),
        }
        if self.probes_spent >= self.budget:
            return self._finish_probe(record, ok=False, error="probe budget exhausted")

        # Every submitted request consumes one slot before any validation.
        self.probes_spent += 1
        record["attempt_number"] = self.probes_spent
        if type(start_tid) is not str or not start_tid:
            return self._finish_probe(
                record, ok=False, error=f"start_tid must be a non-empty string, got {start_tid!r}"
            )
        request_error = self._validate_action_click(action_id, click)
        if request_error is not None:
            return self._finish_probe(record, ok=False, error=request_error)

        prefix = self._prefix_to(start_tid)
        if prefix is None:
            return self._finish_probe(
                record, ok=False, error=f"{start_tid} is not a recapture-verified replayable state"
            )
        normalised_click = tuple(click) if click is not None else None
        key = (start_tid, action_id, normalised_click)
        if key in self._probe_keys:
            return self._finish_probe(
                record, ok=False, error="redundant probe: identical request already made"
            )
        self._probe_keys.add(key)

        try:
            engine = self._ensure_engine()
            handle = engine.new()
        except Exception as exc:
            return self._finish_probe(
                record,
                ok=False,
                failure_stage="engine_start",
                error=f"engine start failed: {type(exc).__name__}: {exc}",
            )

        prefix_audit: list[dict[str, Any]] = []
        record["prefix_actions"] = [step["action"] for step in prefix]
        for step in prefix:
            action = tuple(step["action"])
            try:
                response = engine.perform(handle, action)
                frames = self._engine_frames(
                    engine, response, label=f"prefix store step {step['store_step']}"
                )
                response_state, levels_completed = response_metadata(
                    response, label=f"prefix store step {step['store_step']}"
                )
            except Exception as exc:
                return self._finish_probe(
                    record,
                    ok=False,
                    failure_stage="prefix_execute",
                    failed_store_step=step["store_step"],
                    prefix_steps=prefix_audit,
                    error=f"prefix execution failed: {type(exc).__name__}: {exc}",
                )
            frame_sha256 = [canonical_sha256(frame) for frame in frames]
            reached_sha256 = frame_sha256[-1] if frame_sha256 else None
            recapture = step["recapture"]
            checks = {
                "stored_post_match": reached_sha256 == step["expected_sha256"],
                "recapture_frame_count_match": len(frames) == recapture["frame_count"],
                "recapture_raw_frames_match": frame_sha256 == recapture["raw_frame_sha256"],
                "recapture_post_match": reached_sha256 == recapture["reached_sha256"],
                "recapture_response_state_match": (
                    response_state == recapture["response_state"]
                ),
                "recapture_levels_completed_match": (
                    levels_completed == recapture["levels_completed"]
                ),
            }
            step_record = {
                "tid": step["tid"],
                "source_index": step["source_index"],
                "store_step": step["store_step"],
                "episode_index": step["episode_index"],
                "episode_step": step["episode_step"],
                "action": step["action"],
                "expected_post_sha256": step["expected_sha256"],
                "reached_post_sha256": reached_sha256,
                "frames_returned": len(frames),
                "zero_frames": len(frames) == 0,
                "response_state": response_state,
                "recapture_response_state": recapture["response_state"],
                "levels_completed": levels_completed,
                "recapture_levels_completed": recapture["levels_completed"],
                "raw_frame_sha256": frame_sha256,
                "recapture_raw_frame_sha256": recapture["raw_frame_sha256"],
                "recapture_source": recapture["source"],
                "recapture_source_sha256": recapture["source_sha256"],
                "checks": checks,
                "gate_passed": all(checks.values()),
            }
            prefix_audit.append(step_record)
            if not step_record["gate_passed"]:
                return self._finish_probe(
                    record,
                    ok=False,
                    failure_stage="prefix_gate",
                    failed_store_step=step["store_step"],
                    prefix_steps=prefix_audit,
                    error=(
                        "prefix gate FAILED: replay did not match stored and recaptured "
                        "evidence at every frame"
                    ),
                )

        y, x = normalised_click if normalised_click is not None else (None, None)
        try:
            response = engine.perform(handle, (action_id, y, x))
            frames = self._engine_frames(engine, response, label="active probe")
            response_state, levels_completed = response_metadata(
                response, label="active probe"
            )
        except Exception as exc:
            return self._finish_probe(
                record,
                ok=False,
                failure_stage="probe_execute",
                prefix_steps=prefix_audit,
                error=f"active probe failed: {type(exc).__name__}: {exc}",
            )

        frame_sha256 = [canonical_sha256(frame) for frame in frames]
        settled_sha256 = frame_sha256[-1] if frame_sha256 else None
        try:
            image_audit = self._render_probe_pages(frames, self.probes_spent, start_tid)
        except Exception as exc:
            return self._finish_probe(
                record,
                ok=False,
                failure_stage="probe_render",
                prefix_steps=prefix_audit,
                raw_frame_sha256=frame_sha256,
                settled_sha256=settled_sha256,
                error=f"probe frame rendering failed: {type(exc).__name__}: {exc}",
            )
        images = [audit["path"] for audit in image_audit]
        zero_frames = len(frames) == 0
        baseline_levels = prefix[-1]["recapture"]["levels_completed"]
        level_delta = levels_completed - baseline_levels
        terminal_state_observed = response_state in {"GAME_OVER", "WIN"}
        outcome_fields = (
            f"response_state={response_state}; levels_completed={levels_completed}; "
            f"level_delta={level_delta}"
        )
        if zero_frames:
            text = (
                f"probe executed from {start_tid}: action A{action_id}"
                f"{' click ' + str(click) if click is not None else ''} returned zero raw "
                f"frames; no settled board was emitted; {outcome_fields} [OBSERVED, live]"
            )
        else:
            ranges = [
                f"{audit['frame_indexes'][0]}-{audit['frame_indexes'][-1]}"
                for audit in image_audit
            ]
            text = (
                f"probe executed from {start_tid}: action A{action_id}"
                f"{' click ' + str(click) if click is not None else ''} returned all "
                f"{len(frames)} raw frames on {len(images)} audited page(s) "
                f"(frame ranges {ranges}); frame {len(frames) - 1} is the settled outcome "
                f"and {outcome_fields} [OBSERVED, live]"
            )
        return self._finish_probe(
            record,
            ok=True,
            outcome="zero_frames" if zero_frames else "observed_frames",
            prefix_steps=prefix_audit,
            frames_returned=len(frames),
            raw_frame_sha256=frame_sha256,
            settled_frame_index=len(frames) - 1 if frames else None,
            settled_sha256=settled_sha256,
            settled_digest=settled_sha256[:16] if settled_sha256 else None,
            zero_frames=zero_frames,
            response_state=response_state,
            levels_completed=levels_completed,
            baseline_levels_completed=baseline_levels,
            level_delta=level_delta,
            level_advanced=level_delta > 0,
            terminal_state_observed=terminal_state_observed,
            images=images,
            image_audit=image_audit,
            text=text,
        )


def smoke(game: str) -> int:
    out = ROOT / "logs/s4_probe_smoke" / game
    session = ProbeSession(game, out)
    tids = [t["tid"] for t in session.transitions if t["source"] == "store"][:40]
    print(session.retrieve("SHOW_FRAME", tids[5])["text"])
    print(session.retrieve("SHOW_TRANSITION", tids[6])["text"])
    print(session.retrieve("SHOW_EPISODE", tids[2], "6")["text"])
    print(session.retrieve("SHOW_ACTION_CONTRAST", "A1").get("text") or
          session.retrieve("SHOW_ACTION_CONTRAST", "A6").get("text"))
    print(session.retrieve("SHOW_COLOUR_HISTORY", "9").get("text", "colour 9 static"))
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
