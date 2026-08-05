#!/usr/bin/env python3
"""E2 — the Qwen synthesis slice. The first model-bearing measurement of the line.

`notes/e2-dose.md` establishes the zero-model floor: the E0 miner over E1-v2 explorer
evidence recovers rules at median 0.938 of the human-replay ceiling, and the dose curve is
FLAT in the median — more actions is not where synthesis is bottlenecked. What the miner
cannot do is resolve the structure its own vocabulary lacks: census-separable and
guard-fixable failure mass. That is this slice's brief.

Per game x dose: an organized store digest -> Qwen thinking -> proposals -> machine
verification -> scoring against the SAME held-out human targets the miner was scored on.
The zero-model curve is the floor at every dose; a proposal set that does not beat it has
measured nothing.

INSTRUMENT RULES (the screens died on these; CLAUDE.md 2026-08-04)
------------------------------------------------------------------
* Qwen3.6-27B-8bit only. The FP8-class model is the deploy reference and the one S1's
  `goal_unknown` bottleneck was measured on; the 4-bit probe thought 2.7x shorter on an
  identical prompt, so precision is not a free axis and the slice must not mix it.
* Direct `mlx_lm`. NO server layer — the July `mlx_vlm` server is the voided lineage.
* Two-phase decode. Phase 1 thinks freely and NEVER has its first token constrained.
  Phase 2 is a separate mechanical extraction call over phase 1's own answer text, with
  thinking off by design; it re-reads, it does not reason. Recorded, not implied.
* Per-call mechanical thinking check identical to `e2_probe.py`. An unclosed think block
  VOIDS the call — the result is discarded, not repaired.
* Every call's raw trace is written to logs/e2_slice_traces/ before scoring.

SCORING
-------
Proposals are parsed into the miner's own `Rule` structure, so they are scored by exactly
the code that scored the miner (`rs_e0.score`) on exactly its test sets (human L1, human L2).

  verification   each proposed rule is fired against the STORE transitions it was shown.
                 A rule with zero support there was not read off the evidence; a rule with
                 contradictions there is refuted by the evidence it was given. Only
                 survivors are scored. This is the step that makes a fluent wrong answer
                 cost nothing.
  floor          the miner's own rules at the same game and dose, scored identically.

Goal, hidden-state and next-probe answers are **logged verbatim and NOT scored in this
slice**. The prompt asks for prose, extraction transcribes one sentence, and nothing
evaluates it — there is no grammar-expressed goal channel here. Wiring proposals into the
row-C universe so the frozen three-valued evaluator can falsify them is a real design task,
not a bolt-on, and it is deliberately out of scope. The rule above applies to this file as
much as to the model: an unscored proposal is reported as unscored, never as a pass.

Run:
  .venv/bin/python agent/harness/e2_slice.py --dry-run          # digests only, no model
  .venv/bin/python agent/harness/e2_slice.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from e2_dose import load_store  # noqa: E402
from rs_e0 import Rule, abstract, mine, score  # noqa: E402
from rs_transitions import ITERATION_GAMES, ROOT, load_game  # noqa: E402

MODEL = Path.home() / "models/mlx/Qwen3.6-27B-8bit"  # PINNED — see notes/e2-dose.md
OUTPUT = ROOT / "logs/e2_slice.json"
TRACES = ROOT / "logs/e2_slice_traces"
FORMAT_VERSION = 1

DOSES = (125, None)  # (w) endpoints only — licensed by the flat median dose curve
MODE = "full"  # the layer the miner is weakest on, and the one Qwen is being asked for
THINK_BUDGET = 16384  # (w) >=16k; a 5k budget produced an unclosed block in bring-up
EXTRACT_BUDGET = 4096
TEMP = 0.6  # (w) Qwen thinking defaults
TOP_P = 0.95

MAX_RULES_SHOWN = 40
MAX_UNRESOLVED_SHOWN = 12
MAX_EVIDENCE_PER_KEY = 6
# slice 1.1 measured the cost of capping features silently: the digest asserted complete
# value sets while showing only the first 6 varying features, and 21 of 24 traces inferred
# "unlisted => constant => cannot separate". In 14 unresolved-key blocks the witness named a
# feature the display never showed. The cap is lifted so that inference is SOUND: every
# feature that varies is shown, so absence now really does mean constant across the key.
MAX_FEATURES_PER_GROUP = None  # no cap — see notes/e2-variance-arm.md §2
MAX_VALUES_PER_FEATURE = 4  # (w) truncation is marked "+N more" and declared in the prompt
MAX_ALIAS_SHOWN = 8
SEED = 20260804  # phase 1 is sampled; seeded and recorded so a cell is reproducible

# The miner's actual guard vocabulary (rs_transitions.guard_features). A proposal naming a
# feature outside it is REJECTED, not silently unguarded: `guards.get(unknown)` is None for
# every transition, which equals a null guard_value, so an invented guard would vanish and
# the rule would be scored as unguarded — strictly more permissive than proposed.
GUARD_PREFIXES = ("present:", "count:", "adj:", "clicked_adjacent_to:")
GUARD_EXACT = ("click_colour", "click_on_background")


def valid_guard(feature: str, vocabulary: set[str]) -> bool:
    return feature in vocabulary and (
        feature.startswith(GUARD_PREFIXES) or feature in GUARD_EXACT
    )


_STORE_CACHE: dict[str, list] = {}
_MINE_CACHE: dict[tuple[str, Any], tuple] = {}


def store_for(game: str) -> list:
    if game not in _STORE_CACHE:
        _STORE_CACHE[game] = load_store(game)[0]
    return _STORE_CACHE[game]


def mined(game: str, dose: int | None) -> tuple:
    key = (game, dose)
    if key not in _MINE_CACHE:
        store = store_for(game)
        used = store if dose is None else store[:dose]
        _MINE_CACHE[key] = (used, *mine(used, MODE))
    return _MINE_CACHE[key]


# ======================================================================================
# Digest — the whole prompt payload, built with zero model calls
# ======================================================================================


def _effect_text(effect: tuple) -> str:
    if not effect:
        return "no-change"
    return " + ".join(
        f"{event[0]}({event[1]}" + (f",{event[2]},{event[3]})" if len(event) > 3 else ")")
        for event in effect
    )


def _key_text(key: tuple) -> str:
    return f"ACTION6 on colour {key[1]}" if key[0] == "A6" else f"ACTION{key[1]}"


def _hv(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


def _no_separation_witness(rows: list, varying: list[str]) -> tuple | None:
    """The best single feature shown failing: fewest mixed value-classes, then the
    largest one — two transition sets sharing the feature's value with different effects.

    A varying feature with NO mixed class separates only under the None-for-absent
    convention the miner does not use; it is skipped, not presented as a witness.
    """
    best = None
    for name in varying:
        classes: dict[Any, Counter] = {}
        for row in rows:
            classes.setdefault(_hv(row.guards.get(name)), Counter())[
                abstract(row.effect, MODE)
            ] += 1
        mixed = {v: c for v, c in classes.items() if len(c) > 1}
        if not mixed:
            continue
        value, counts = max(
            mixed.items(), key=lambda item: (sum(item[1].values()), repr(item[0]))
        )
        rank = (len(mixed), -sum(counts.values()), name)
        if best is None or rank < best[0]:
            top = counts.most_common(2)
            best = (rank, name, value, (top[0][0], top[0][1]), (top[1][0], top[1][1]))
    if best is None:
        return None
    _, name, value, first, second = best
    return name, value, first, second


def unresolved_keys(rules: dict[str, Rule]) -> list[tuple]:
    """The keys the miner could not resolve.

    Derived from the rules themselves — the miner emits exactly one `tier == "majority"`
    rule per unresolved key. NOT parsed from mine()'s report: that report keys the list
    under "unresolved_keys" and stores `str(key)`, so reading it by the wrong name yields
    an empty section and reading it by the right one yields strings that never match a real
    transition key. Both failures are silent, and both empty the one section this slice
    exists to show.
    """
    return [rule.key for rule in rules.values() if rule.tier == "majority"]


def state_identity(game: str) -> list[str]:
    """The STATE IDENTITY block — replaces the old ALIAS CONFLICTS block.

    The old block listed `graph.conflicted` and printed "none recorded" when it was empty.
    That reads as "no aliasing here", and it is not: E1 flags a (state, action) pair only
    when its routing happens to re-test the pair, and the v2 policy re-tests almost
    nothing. `notes/e1-prefix-audit.md` measured what the list is worth — ka59, dc22, wa30
    and sk48 all record ZERO conflicted edges while under 6% of their stored states are
    reachable by their own recorded prefix. dc22's digest printed "none recorded" for a
    store whose settled frames do not identify its states at all, and 21 of 24 slice
    traces then reasoned from a clean state graph they were never given evidence for.

    So the section now leads with the MEASURED quantity — the fraction of stored states
    whose recorded prefix replays to the grid the store claims, over a deterministic engine
    — and demotes the conflict list to the lower bound it always was. Absence of evidence
    is stated as absence of evidence, in the prompt, in words.

    Reads `logs/e1_prefix_audit.json` (`agent/harness/e1_prefix_audit.py`). If that file is
    missing the block says the check has not been run rather than implying a clean store.
    """
    lines: list[str] = []
    audit_path = ROOT / "logs/e1_prefix_audit.json"
    audit = None
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text()).get("games", {}).get(game)

    if audit is None:
        lines.append(
            "  NOT MEASURED for this game. Whether the settled frame identifies the state "
            "is unknown here, and unknown is not the same as clean — treat every rule "
            "below as possibly conditioned on something these frames do not show."
        )
    else:
        rate = audit["verified_rate"]
        lines.append(
            f"  Measured: {audit['verified']} of {audit['states']} stored states "
            f"({rate:.1%}) are reached by replaying their own recorded action prefix from "
            f"reset. The engine is deterministic, so where a replay lands elsewhere, two "
            f"different histories produced the same settled frame."
        )
        if rate >= 0.999:
            lines.append(
                "  Every stored state replays. For this game the settled frame does "
                "identify the state, and a rule conditioned only on what you see below "
                "is not missing a hidden variable."
            )
        else:
            lines.append(
                f"  {1 - rate:.1%} of states do NOT replay to themselves. The settled "
                f"frame does NOT fully identify this game's state: there is at least one "
                f"hidden variable that no feature in the guard vocabulary can express. A "
                f"key you cannot separate may be unseparable for that reason, and no "
                f"guard over these frames would fix it."
            )

    graph_path = ROOT / "logs/e1_store_v2" / f"{game}.graph.json"
    if graph_path.is_file():
        graph = json.loads(graph_path.read_text())
        conflicted = graph.get("conflicted", [])
        lines.append(
            f"  ({len(conflicted)} (state, action) pairs are flagged in the store as having "
            f"contradicted themselves. That count is NOT usable as evidence in either "
            f"direction and no pairs are listed: the explorer re-tested only a small "
            f"unrecorded fraction of pairs, so absence means nothing, and its routing "
            f"replayed paths that were never walked and flagged the divergences as "
            f"contradictions, so presence is often an artifact. Use the measurement above.)"
        )
    return lines


def build_digest(game: str, dose: int | None) -> dict[str, Any]:
    used, rules, _ = mined(game, dose)

    census = Counter()
    sampled = used[: min(len(used), 200)]
    for transition in sampled:
        for guard, value in transition.guards.items():
            if guard.startswith("count:"):
                census[guard.split(":")[1]] = max(census[guard.split(":")[1]], value)

    by_key: dict[tuple, list] = {}
    for transition in used:
        by_key.setdefault(transition.key(), []).append(transition)

    rule_lines = []
    for rule in sorted(rules.values(), key=lambda r: -r.support)[:MAX_RULES_SHOWN]:
        if rule.tier == "majority":
            continue  # unresolved keys get their own section, with their evidence
        guard = "" if rule.guard is None else f"  WHEN {rule.guard}={rule.guard_value}"
        rule_lines.append(
            f"  [{rule.tier}] {_key_text(rule.key)}{guard}  ->  {_effect_text(rule.effect)}"
            f"   (support {rule.support})"
        )

    pending = unresolved_keys(rules)
    unresolved_lines = []
    for key in pending[:MAX_UNRESOLVED_SHOWN]:
        rows = by_key.get(key, [])
        effects = Counter(abstract(row.effect, MODE) for row in rows)

        # Only guards that VARY across this key's transitions can possibly separate them.
        values: dict[str, set] = {}
        for row in rows:
            for name, value in row.guards.items():
                values.setdefault(name, set()).add(_hv(value))
        varying = [name for name, seen in sorted(values.items()) if len(seen) > 1]
        constant_note = "" if varying else "  (NO guard in the vocabulary varies here at all)"
        unresolved_lines.append(
            f"  {_key_text(key)} — {len(rows)} transitions, {len(effects)} distinct effects, "
            f"no single guard separates them:{constant_note}"
        )
        # Autopsy rec 1: the COMPLETE value set per feature within each effect group —
        # slice 1's one-example row was read as a group constant by 59 of 84 proposals.
        for effect, count in effects.most_common(MAX_EVIDENCE_PER_KEY):
            group = [row for row in rows if abstract(row.effect, MODE) == effect]
            parts = []
            for name in (varying if MAX_FEATURES_PER_GROUP is None
                         else varying[:MAX_FEATURES_PER_GROUP]):
                seen = sorted({_hv(row.guards.get(name)) for row in group}, key=repr)
                vals = ", ".join(str(v) for v in seen[:MAX_VALUES_PER_FEATURE])
                if len(seen) > MAX_VALUES_PER_FEATURE:
                    vals += f", +{len(seen) - MAX_VALUES_PER_FEATURE} more"
                parts.append(f"{name} in {{{vals}}}")
            unresolved_lines.append(f"      x{count:<4d} {_effect_text(effect)}")
            if parts:
                unresolved_lines.append(f"            {'; '.join(parts)}")
        # Autopsy rec 2: the miner's assertion carries its own evidence — the best single
        # feature shown FAILING. 55 of 84 slice-1 proposals overrode the bare assertion.
        witness = _no_separation_witness(rows, varying)
        if witness is not None:
            name, value, (effect_a, n_a), (effect_b, n_b) = witness
            unresolved_lines.append(
                f"      NO-SEPARATION WITNESS — the best single feature `{name}` still "
                f"fails: at {name}={value}, x{n_a} gave {_effect_text(effect_a)} while "
                f"x{n_b} gave {_effect_text(effect_b)}"
            )

    identity_lines = state_identity(game)

    completion = next((t for t in used if t.completed), None)
    completion_line = (
        f"  {_key_text(completion.key())} completed the level at step {completion.step}"
        if completion is not None
        else "  none — this run never completed level 1"
    )

    text = f"""GAME {game}, evidence dose {"full store" if dose is None else dose} transitions.

Every fact below was derived mechanically from one autonomous exploration run of level 1.

ACTION INVENTORY (keys the evidence contains)
{chr(10).join(f"  {_key_text(k)}: {len(v)} transitions" for k, v in sorted(by_key.items(), key=lambda i: -len(i[1]))[:20])}

OBJECT CENSUS (max simultaneous components per colour, over the first {len(sampled)} transitions)
  {dict(sorted(census.items()))}

RULES THE MECHANICAL MINER RESOLVED ({len(rules)} total, top {MAX_RULES_SHOWN} by support)
{chr(10).join(rule_lines) if rule_lines else (
    "  none — every mined rule at this dose is a majority-tier guess for a key listed below"
    if rules else "  none")}

KEYS THE MINER COULD NOT RESOLVE — the actual problem
  A key is unresolved when its transitions disagree about the effect and NO SINGLE guard
  feature in the miner's vocabulary separates them. The vocabulary is: present:C, count:C,
  adj:C:direction (the first non-background colour met stepping one cell out from colour C's
  single object, or "edge"), clicked_adjacent_to:C (ACTION6 only — does the 4-connected
  same-colour component under the click touch any cell of colour C), click_colour,
  click_on_background. A guard tests exactly
  `feature = one literal value`; negation, inequalities, thresholds and combined conditions
  do not exist and cannot be tested.
  READ THE VALUE SETS LITERALLY. For each effect group, every feature that VARIES anywhere
  in this key is listed, with the set of values it takes within that group. A one-element
  set means constant within that group; a multi-element set means the feature took ALL of
  those values while producing the same effect. A set ending "+N more" is truncated at
  {MAX_VALUES_PER_FEATURE} values and N further values are not shown; an unmarked set is complete.
  A feature ABSENT from these lines is constant across every transition of this key, so it
  cannot separate anything — that inference is sound here, but it is the ONLY thing absence
  licenses. Only the {MAX_EVIDENCE_PER_KEY} largest effect groups are shown; if the header
  reports more distinct effects than there are groups below, the remainder are omitted.
  Each key ends with a NO-SEPARATION WITNESS: the single feature that comes CLOSEST to
  separating the key, shown failing on concrete counts. It is the best available, not a
  good one — a feature that splits two groups cleanly can still fail the key, because
  separating the key means telling ALL of its effects apart.
{chr(10).join(unresolved_lines) if unresolved_lines else "  none"}

STATE IDENTITY — does the settled frame below fully identify the game's state?
{chr(10).join(identity_lines)}

LEVEL COMPLETION
{completion_line}
"""
    return {
        "game": game,
        "dose": dose,
        "text": text,
        "store_transitions": len(used),
        "miner_rules": len(rules),
        "unresolved_keys": len(pending),
        "unresolved_shown": min(len(pending), MAX_UNRESOLVED_SHOWN),
        "chars": len(text),
    }


PROMPT = """You are analysing an unfamiliar grid-puzzle game from mechanically extracted evidence.

{digest}

An object is a 4-connected same-colour component, measured against the state's background
(its most common colour). An effect is position-free: move(colour,dr,dc), reshape(colour),
appear(colour), disappear(colour), or no-change. A recolour appears as disappear+appear.

Your job is the part the mechanical miner cannot do: explain the UNRESOLVED keys. For each
one, work out what actually distinguishes the transitions that disagree. You may use any
reasoning you like, but your final rules must be expressible as:

    action (+ the colour clicked, for ACTION6)  [+ at most ONE guard]  ->  effect

A guard is exactly `feature = literal` — equality against ONE literal value that appears in
the evidence. Negation ("not 11"), inequalities ("> 1"), and combined conditions cannot be
expressed or tested; if the true condition needs them, name that as a vocabulary limit
instead of forcing a rule.

Think about whether the disagreement is caused by something the guard vocabulary can name.
If it cannot, say so explicitly rather than inventing a rule that fits. The miner's
no-separation claims above come with their witness counts — treat them as constraints your
rule must survive, not as claims to argue with.

Then answer, in plain prose:
1. RULES — each as: action, optional guard (feature=value), the exact effect, the number of
   shown transitions that support it, and the single observation that would refute it.
2. GOAL — what you believe completing this level requires, and what evidence supports it.
3. HIDDEN STATE — read the STATE IDENTITY section. If it reports states that do not replay
   to themselves, a hidden variable EXISTS and your job is to name what it plausibly is, not
   to decide whether there is one. If it reports that every state replays, say so and do not
   invent one. Never infer "no hidden state" from a short conflict list.
4. WHAT WOULD SETTLE IT — the single most informative action to try next, and where.
"""

EXTRACT = """Below is an analysis of a grid game. Re-read it and transcribe its conclusions into JSON.
Do not add, judge, or correct anything — transcribe only what is stated.

{answer}

Emit ONLY a JSON object, no commentary:
{{"rules": [{{"action_id": <int 1-7>, "click_colour": <int or null>,
              "guard": null or {{"feature": "<e.g. adj:3:up or count:5>", "value": <int, string or null>}},
              "effect": [["move", <colour>, <dr>, <dc>] or ["reshape", <colour>] or
                         ["appear", <colour>] or ["disappear", <colour>]],
              "support_claim": <int or null>, "refuter": "<one sentence or null>"}}],
 "goal": "<one sentence>",
 "hidden_state": "<one sentence or empty>",
 "next_probe": "<one sentence or empty>"}}
An empty effect list means the action changes nothing. If the analysis states no rule in that
form, return an empty rules list."""


# ======================================================================================
# Model
# ======================================================================================


class Qwen:
    def __init__(self, path: Path):
        from mlx_lm import load

        self.path = path
        self.model, self.tokenizer = load(str(path))

    def generate(
        self,
        messages: list,
        *,
        max_tokens: int,
        thinking: bool,
        temp: float = TEMP,
        seed: int | None = None,
    ) -> dict[str, Any]:
        import mlx.core as mx
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler

        if seed is not None:
            mx.random.seed(seed)
        prompt = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, enable_thinking=thinking, tokenize=False
        )
        opens_think = prompt.rstrip().endswith("<think>")
        prefilled = "<think>\n\n</think>" in prompt
        # Phase 2 is transcription, so it decodes GREEDILY (temp=0): a sampled transcription
        # can lose a rule the analysis actually stated, and a parse failure costs the whole
        # ~20-minute cell.
        sampler = make_sampler(temp=temp, top_p=TOP_P if temp > 0 else 1.0)
        pieces: list[str] = []
        gen_tps = prompt_tps = None
        start = time.monotonic()
        for response in stream_generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
            sampler=sampler,
        ):
            pieces.append(response.text)
            gen_tps = getattr(response, "generation_tps", None)
            prompt_tps = getattr(response, "prompt_tps", None)
        completion = "".join(pieces)
        full = ("<think>" + completion) if opens_think else completion
        closed = "</think>" in full
        body = full.split("<think>", 1)[-1].split("</think>", 1)[0] if "<think>" in full else ""
        answer = full.split("</think>", 1)[-1].strip() if closed else ""
        return {
            "prompt_chars": len(prompt),
            "prefilled_empty_think": prefilled,
            "prompt_opens_think": opens_think,
            "think_opened": "<think>" in full,
            "think_closed": closed,
            "think_chars": len(body.strip()),
            "answer": answer if thinking else completion.strip(),
            "raw": completion,
            "wall_seconds": round(time.monotonic() - start, 1),
            "prompt_tps": prompt_tps,
            "generation_tps": gen_tps,
            "temp": temp,
            "seed": seed,
        }


def thinking_verdict(call: dict[str, Any]) -> dict[str, bool]:
    return {
        "no_prefilled_empty_think": not call["prefilled_empty_think"],
        "think_opened": call["think_opened"],
        "think_closed": call["think_closed"],
        "think_substantive": call["think_chars"] >= 200,
        "answer_nonempty": bool(call["answer"]),
    }


# ======================================================================================
# Proposal parsing, verification, scoring
# ======================================================================================


def parse_json(text: str) -> dict[str, Any] | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        candidate = text[start : end + 1] if start != -1 and end > start else None
    if candidate is None:
        return None
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _event(event: Any) -> tuple:
    """Canonicalize one effect event, int-coercing numerics.

    JSON has no int/float distinction, so a transcribed `1.0` would never equal the
    miner's `1` and the rule would silently score zero support instead of being read.
    """
    out = []
    for field in tuple(event):
        if isinstance(field, bool):
            out.append(field)
        elif isinstance(field, float) and field.is_integer():
            out.append(int(field))
        else:
            out.append(field)
    return tuple(out)


def to_rules(
    payload: dict[str, Any], vocabulary: set[str]
) -> tuple[dict[str, Rule], list[str]]:
    rules: dict[str, Rule] = {}
    rejected: list[str] = []
    for index, item in enumerate(payload.get("rules") or []):
        try:
            action_id = int(item["action_id"])
            colour = item.get("click_colour")
            key = ("A6", None if colour is None else int(colour)) if action_id == 6 else ("A", action_id)
            guard_spec = item.get("guard")
            guard = guard_value = None
            if isinstance(guard_spec, dict) and guard_spec.get("feature"):
                guard = str(guard_spec["feature"])
                if not valid_guard(guard, vocabulary):
                    rejected.append(f"rule {index}: guard '{guard}' is not in the vocabulary")
                    continue
                guard_value = guard_spec.get("value")
                if isinstance(guard_value, float) and guard_value.is_integer():
                    guard_value = int(guard_value)
            effect = tuple(sorted(_event(event) for event in (item.get("effect") or [])))
        except (KeyError, TypeError, ValueError) as error:
            rejected.append(f"rule {index}: {type(error).__name__} {error}")
            continue
        rule = Rule(
            key=key,
            guard=guard,
            guard_value=guard_value,
            effect=effect,
            support=0,
            supporters=[],
            tier="proposed",
        )
        rules[f"p{index}:{rule.rid()}"] = rule
    return rules, rejected


def verify(rules: dict[str, Rule], store: list) -> tuple[dict[str, Rule], list[dict[str, Any]]]:
    """Fire each proposal against the evidence it was shown. Survivors only."""
    report = []
    survivors: dict[str, Rule] = {}
    for name, rule in rules.items():
        support = contradicted = 0
        for index, transition in enumerate(store):
            if transition.key() != rule.key:
                continue
            if rule.guard is not None:
                value = transition.guards.get(rule.guard)
                value = tuple(value) if isinstance(value, list) else value
                if value != rule.guard_value:
                    continue
            if abstract(transition.effect, MODE) == rule.effect:
                support += 1
                rule.supporters.append(index)
            else:
                contradicted += 1
        rule.support = support
        kept = support > 0 and contradicted == 0
        if kept:
            survivors[name] = rule
        report.append(
            {
                "rule": rule.rid(),
                "support_on_store": support,
                "contradicted_on_store": contradicted,
                "kept": kept,
            }
        )
    return survivors, report


def per_key_delta(
    miner: dict[str, Rule],
    union: dict[str, Rule],
    train: list,
    test: list,
    keys: list[tuple],
) -> dict[str, Any]:
    """Accuracy on exactly the transitions whose key the miner could not resolve.

    The headline contrast is diluted by every key the miner already got right; this is the
    subset the slice is actually about.
    """
    target = [t for t in test if t.key() in set(keys)]
    if not target:
        return {"transitions": 0}
    before = score(miner, train, target, MODE)
    after = score(union, train, target, MODE)
    return {
        "transitions": len(target),
        "miner_accuracy_over_all": before["accuracy_over_all"],
        "union_accuracy_over_all": after["accuracy_over_all"],
        "delta": (
            round(after["accuracy_over_all"] - before["accuracy_over_all"], 4)
            if before["accuracy_over_all"] is not None
            and after["accuracy_over_all"] is not None
            else None
        ),
    }


def run_cell(
    game: str,
    dose: int | None,
    qwen: Qwen | None,
    human: dict[str, list],
    seed: int = SEED,
) -> dict[str, Any]:
    digest = build_digest(game, dose)
    used, baseline_rules, _ = mined(game, dose)
    pending = unresolved_keys(baseline_rules)
    vocabulary = {name for t in used for name in t.guards}

    floor = {
        "human_l1": score(baseline_rules, used, human["l1"], MODE),
        "human_l2": score(baseline_rules, used, human["l2"], MODE),
    }
    cell: dict[str, Any] = {
        "game": game,
        "dose": dose,
        "digest_chars": digest["chars"],
        "store_transitions": digest["store_transitions"],
        "miner_rules": digest["miner_rules"],
        "unresolved_keys": digest["unresolved_keys"],
        "floor": floor,
    }
    if qwen is None:
        cell["skipped"] = "dry-run"
        return cell

    think = qwen.generate(
        [{"role": "user", "content": PROMPT.format(digest=digest["text"])}],
        max_tokens=THINK_BUDGET,
        thinking=True,
        seed=seed,
    )
    verdict = thinking_verdict(think)
    TRACES.mkdir(parents=True, exist_ok=True)
    # seed-tagged so variance-arm reruns can never overwrite slice 1's committed traces
    tag = f"{game}_{'full' if dose is None else dose}_s{seed}"
    (TRACES / f"{tag}.think.json").write_text(
        json.dumps({"prompt": digest["text"], **think, "verdict": verdict}, indent=2)
    )
    cell["thinking"] = {k: v for k, v in think.items() if k not in ("raw", "answer")}
    cell["thinking_verdict"] = verdict
    if not all(verdict.values()):
        cell["outcome"] = "VOID — thinking check failed"
        return cell

    payload = None
    attempts = []
    for attempt in range(2):
        # Greedy decoding makes a bare retry a no-op — attempt 1 would reproduce attempt 0
        # byte for byte. The second attempt therefore changes the PROMPT, not the sampler,
        # so the retry can actually pay out while staying deterministic given the transcript.
        content = EXTRACT.format(answer=think["answer"])
        if attempt:
            content = (
                "Your previous reply was not valid JSON. Emit the JSON object only — no "
                "prose, no code fence, no trailing text.\n\n" + content
            )
        extract = qwen.generate(
            [{"role": "user", "content": content}],
            max_tokens=EXTRACT_BUDGET,
            thinking=False,
            temp=0.0,
            seed=seed + attempt,
        )
        attempts.append(extract)
        (TRACES / f"{tag}.extract{attempt}.json").write_text(json.dumps(extract, indent=2))
        payload = parse_json(extract["answer"])
        if payload is not None:
            break
    cell["extract_attempts"] = len(attempts)
    if payload is None:
        cell["outcome"] = "unparsed extraction"
        cell["wall_seconds"] = think["wall_seconds"] + sum(a["wall_seconds"] for a in attempts)
        return cell

    proposed, rejected = to_rules(payload, vocabulary)
    survivors, report = verify(proposed, used)

    # Survivors FIRST: _fire prefers guarded rules by support and otherwise takes the first
    # unguarded rule in insertion order, so this makes a verified proposal beat the miner's
    # majority guess on the key it addresses — deterministically, not by dict luck.
    union = {**survivors, **baseline_rules}
    cell.update(
        {
            "outcome": "scored",
            "proposed": len(proposed),
            "parse_rejected": rejected,
            "verified": len(survivors),
            "verification": report,
            # Qwen's rules ALONE — narrow by construction, reported for completeness only.
            # Nobody deploys Qwen-instead-of-miner; this is not the contrast.
            "qwen_only": {
                "human_l1": score(survivors, used, human["l1"], MODE) if survivors else None,
                "human_l2": score(survivors, used, human["l2"], MODE) if survivors else None,
            },
            # THE HEADLINE: the miner repaired by verified proposals, against the same floor.
            "union": {
                "human_l1": score(union, used, human["l1"], MODE),
                "human_l2": score(union, used, human["l2"], MODE),
            },
            "unresolved_delta": {
                "human_l1": per_key_delta(baseline_rules, union, used, human["l1"], pending),
                "human_l2": per_key_delta(baseline_rules, union, used, human["l2"], pending),
            },
            "goal": payload.get("goal"),
            "hidden_state": payload.get("hidden_state"),
            "next_probe": payload.get("next_probe"),
            "wall_seconds": think["wall_seconds"] + sum(a["wall_seconds"] for a in attempts),
        }
    )
    return cell


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--doses", type=int, nargs="*", default=None)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--dry-run", action="store_true", help="digests + floors, no model")
    parser.add_argument(
        "--seed", type=int, default=SEED, help="phase-1 sampling seed; tags traces and output"
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    out = args.out or (ROOT / f"logs/e2_slice_seed{args.seed}.json")

    doses = tuple(args.doses) if args.doses else DOSES
    qwen = None
    if not args.dry_run:
        print(f"loading {args.model.name} ...", flush=True)
        start = time.monotonic()
        qwen = Qwen(args.model)
        print(f"loaded in {time.monotonic() - start:.1f}s", flush=True)

    cells = []
    for game in args.games:
        human_all = load_game(game, max_level=2)
        human = {
            "l1": [t for t in human_all if t.level == 1],
            "l2": [t for t in human_all if t.level == 2],
        }
        for dose in doses:
            label = f"{game} dose={'full' if dose is None else dose}"
            print(f"\n=== {label} ===", flush=True)
            cell = run_cell(game, dose, qwen, human, seed=args.seed)
            cells.append(cell)
            if cell.get("outcome") == "scored":
                # accuracy_over_ALL with coverage beside it. accuracy_over_covered rewards a
                # proposal set that claims three transitions and gets them right, which is
                # exactly the artifact a narrow guarded proposal produces.
                floor2, union2 = cell["floor"]["human_l2"], cell["union"]["human_l2"]
                delta = cell["unresolved_delta"]["human_l2"]
                print(
                    f"{label}: proposed {cell['proposed']} verified {cell['verified']} | "
                    f"L2 acc/all floor {floor2['accuracy_over_all']} "
                    f"(cov {floor2['coverage']}) -> union {union2['accuracy_over_all']} "
                    f"(cov {union2['coverage']}) | unresolved-key delta "
                    f"{delta.get('delta')} on n={delta.get('transitions')} | "
                    f"think {cell['thinking']['think_chars']} chars "
                    f"{cell['wall_seconds']:.0f}s",
                    flush=True,
                )
            else:
                print(f"{label}: {cell.get('outcome', 'dry-run')}", flush=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(
                    {
                        "format_version": FORMAT_VERSION,
                        "model": str(args.model),
                        "mode": MODE,
                        "seed": args.seed,
                        "doses": [d if d is not None else "full" for d in doses],
                        "budgets": {"think": THINK_BUDGET, "extract": EXTRACT_BUDGET},
                        "cells": cells,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
