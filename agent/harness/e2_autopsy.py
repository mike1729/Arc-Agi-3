#!/usr/bin/env python3
"""E2 trace autopsy — the mechanical half (`notes/e2-trace-autopsy.md`).

ZERO MODEL CALLS. This file does two jobs and deliberately not a third:

  1. parse each cell's digest (the exact prompt text the model saw) back into a fact
     table — action inventory, census, miner rules, unresolved-key effect groups with
     their varying-guard examples;
  2. extract every mechanically checkable CLAIM from the thinking body and check it
     against that fact table, producing a claim ledger with a denominator.

It does NOT label REASONING or EXPRESSIBILITY. Those are a human read of the trace with
a verbatim quote per label (notes/e2-trace-autopsy.md §Method); a regex cannot make them
and pretending otherwise would manufacture a rate. The ledger this file writes is the
evidence the rater reads.

Ground truth is the DIGEST, not the store. A reading error is defined in the note as "the
trace asserts something about the digest that the digest contradicts" — so the digest text
is the correct and complete referent, and no store is loaded (which also keeps this file
independent of concurrent edits to rs_transitions/rs_e0).

Claim families, each with its own denominator:

  feature_key   a vocabulary token (present:C / count:C / adj:C:dir / click_colour /
                click_on_background). INVALID if the name is not in the vocabulary, the
                colour is not in the census, or — for adj — the colour is not a
                single-object colour (census > 1), which is what makes adj:C:dir defined
                at all. Fully mechanical, no adjudication.
  count         a number in a counting context ("N transitions", "xN", "support N").
                Attributed to an ACTION when one is named within ATTRIB_WINDOW chars
                before it, and then checked against THAT action's inventory count;
                otherwise checked for membership in the digest's number multiset.
  guard_pair    an asserted (feature, value) pair. Checked for existence anywhere in the
                digest. UNSUPPORTED here is a screen, not a verdict: the model is also
                entitled to hypothesise values it never saw, so every flagged instance
                carries context and is adjudicated by the rater (adjudications live in
                logs/e2_autopsy_adjudication.json and are joined back in).

Run:
  .venv/bin/python agent/harness/e2_autopsy.py            # write logs/e2_autopsy_claims.json
  .venv/bin/python agent/harness/e2_autopsy.py --cell tu93_125 --show feature_key
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TRACES = ROOT / "logs/e2_slice_traces"
OUTPUT = ROOT / "logs/e2_autopsy_claims.json"
ADJUDICATION = ROOT / "logs/e2_autopsy_adjudication.json"

KEY_RE = r"ACTION[0-9](?: on colour [0-9]+)?"  # `_key_text` in e2_slice.build_digest
VOCAB_SIMPLE = {"click_colour", "click_on_background"}
VOCAB_COLOURED = {"present", "count"}
DIRECTIONS = {"up", "down", "left", "right"}
ATTRIB_WINDOW = 80  # chars back from a count claim in which an ACTION mention binds it
CONTEXT = 140  # chars either side of a claim, quoted into the ledger


# ======================================================================================
# Digest -> facts
# ======================================================================================


def parse_digest(text: str) -> dict[str, Any]:
    """Recover the fact table from the digest text. Format is `e2_slice.build_digest`."""
    facts: dict[str, Any] = {
        "actions": {},  # "ACTION1" / "ACTION6:3" -> transition count
        "census": {},  # colour (str) -> max simultaneous components
        "miner_rules": [],  # {key, guard, value, effect, support, tier}
        "unresolved": {},  # action key -> {"transitions", "distinct", "groups": [...]}
        "alias_lines": [],
        "completed": False,
        "dose": -1,
    }
    header = re.search(r"evidence dose (\d+) transitions", text)
    if header:
        facts["dose"] = int(header.group(1))
    sample = re.search(r"over the first (\d+) transitions", text)
    facts["census_sample"] = int(sample.group(1)) if sample else -1

    section = None
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if line.startswith("ACTION INVENTORY"):
            section = "inventory"
            continue
        if line.startswith("OBJECT CENSUS"):
            section = "census"
            continue
        if line.startswith("RULES THE MECHANICAL MINER RESOLVED"):
            section = "rules"
            continue
        if line.startswith("KEYS THE MINER COULD NOT RESOLVE"):
            section = "unresolved"
            continue
        if line.startswith("ALIAS CONFLICTS"):
            section = "alias"
            continue
        if line.startswith("LEVEL COMPLETION"):
            section = "completion"
            continue
        if not stripped:
            continue

        if section == "inventory":
            m = re.match(rf"^({KEY_RE}):\s+(\d+) transitions$", stripped)
            if m:
                facts["actions"][m.group(1)] = int(m.group(2))
        elif section == "census":
            if stripped.startswith("{"):
                facts["census"] = {
                    k: int(v) for k, v in re.findall(r"'(\d+)':\s*(\d+)", stripped)
                }
        elif section == "rules":
            m = re.match(
                rf"^\[(\w+)\]\s+({KEY_RE})"
                r"(?:\s+WHEN\s+(\S+)=(\S+))?\s+->\s+(.*?)\s+\(support (\d+)\)$",
                stripped,
            )
            if m:
                facts["miner_rules"].append(
                    {
                        "tier": m.group(1),
                        "key": m.group(2),
                        "guard": m.group(3),
                        "value": m.group(4),
                        "effect": m.group(5),
                        "support": int(m.group(6)),
                    }
                )
        elif section == "unresolved":
            head = re.match(
                rf"^({KEY_RE}) — (\d+) transitions, (\d+) distinct effects",
                stripped,
            )
            if head:
                facts["unresolved"][head.group(1)] = {
                    "transitions": int(head.group(2)),
                    "distinct": int(head.group(3)),
                    "no_varying_guard": "NO guard in the vocabulary varies" in stripped,
                    "groups": [],
                }
                continue
            grp = re.match(r"^x(\d+)\s+(.*?)\s+varying guards (\{.*\})$", stripped)
            if grp and facts["unresolved"]:
                key = list(facts["unresolved"])[-1]
                guards = {
                    g: _coerce(v)
                    for g, v in re.findall(r"'([^']+)':\s*('[^']*'|None|\d+)", grp.group(3))
                }
                facts["unresolved"][key]["groups"].append(
                    {
                        "count": int(grp.group(1)),
                        "effect": grp.group(2).strip(),
                        "guards": guards,
                    }
                )
        elif section == "alias":
            # the ALIAS header's parenthetical wraps onto a second line
            if stripped.endswith("identify the state)"):
                continue
            if stripped != "none recorded":
                facts["alias_lines"].append(stripped)
        elif section == "completion":
            facts["completed"] = "never completed" not in stripped

    facts["pairs"] = _digest_pairs(facts)
    facts["numbers"] = _digest_numbers(facts)
    facts["features"] = sorted(
        {g for spec in facts["unresolved"].values() for grp in spec["groups"] for g in grp["guards"]}
        | {r["guard"] for r in facts["miner_rules"] if r["guard"]}
    )
    return facts


def _coerce(raw: str) -> Any:
    if raw == "None":
        return None
    if raw.startswith("'"):
        return raw.strip("'")
    return int(raw)


def _digest_pairs(facts: dict[str, Any]) -> set[tuple[str, str]]:
    """Every (feature, value) pair the digest actually shows."""
    pairs = set()
    for rule in facts["miner_rules"]:
        if rule["guard"]:
            pairs.add((rule["guard"], str(rule["value"])))
    for spec in facts["unresolved"].values():
        for group in spec["groups"]:
            for name, value in group["guards"].items():
                pairs.add((name, str(value)))
    for colour, n in facts["census"].items():
        pairs.add((f"count:{colour}", str(n)))
    return pairs


def _digest_numbers(facts: dict[str, Any]) -> Counter:
    numbers = Counter()
    numbers[facts["dose"]] += 1  # the header's own "evidence dose N transitions"
    numbers[facts["census_sample"]] += 1  # "over the first N transitions" on the census line
    numbers[sum(facts["actions"].values())] += 1  # shown-inventory total, legitimately derivable
    for n in facts["actions"].values():
        numbers[n] += 1
    for n in facts["census"].values():
        numbers[n] += 1
    for rule in facts["miner_rules"]:
        numbers[rule["support"]] += 1
    for spec in facts["unresolved"].values():
        numbers[spec["transitions"]] += 1
        numbers[spec["distinct"]] += 1
        for group in spec["groups"]:
            numbers[group["count"]] += 1
    return numbers


# ======================================================================================
# Trace -> claims
# ======================================================================================

FEATURE_RE = re.compile(
    r"\b(?:(present|count|adj|adjacent)\s*:\s*(\d+)(?:\s*:\s*([A-Za-z_]\w*))?"
    r"|(click_colour|click_on_background))\b"
)
# `adj:4:*` / `adj:4:<dir>` are the trace's own wildcards for the whole family, not a
# malformed key. Counting them as invented keys would manufacture reading errors.
WILDCARD_RE = re.compile(r"^\s*:?\s*(\*|<)")
COUNT_RE = re.compile(
    r"(?:\bx(\d+)\b|\b(\d+)\s+transitions\b|\bsupport(?:\s+of)?\s+(\d+)\b)", re.IGNORECASE
)
# "colour 9 transitions" / "color-9 transitions" names a colour, not a count.
COLOUR_PREFIX_RE = re.compile(r"colou?r[-\s]$", re.IGNORECASE)
PAIR_RE = re.compile(
    r"\b((?:adj:\d+:\w+)|(?:count:\d+)|(?:present:\d+))\s*(?:==|=|:|\bis\b|\bof\b)\s*"
    r"[`'\"]?(\d+|None|null|edge)[`'\"]?\b"
)
ACTION_RE = re.compile(r"\bACTION\s?([0-9])\b", re.IGNORECASE)


def _ctx(body: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", body[max(0, start - CONTEXT) : end + CONTEXT]).strip()


def check_features(body: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    for m in FEATURE_RE.finditer(body):
        name, colour, direction, simple = m.groups()
        token = m.group(0)
        if simple:
            claims.append(
                {"family": "feature_key", "token": simple, "status": "ok", "pos": m.start()}
            )
            continue
        if name == "adjacent":
            continue  # prose, not a vocabulary token

        # Schematic notation — `adj:4:*`, `adj:4:<dir>`, `adj:4:ACTION_DIRECTION`, bare
        # `adj:4` standing for the whole family. These are the trace's own placeholders,
        # not asserted keys; scoring them would manufacture reading errors. Counted, not
        # checked.
        if name == "adj" and (direction is None or direction not in DIRECTIONS):
            claims.append(
                {"family": "feature_key", "token": token, "status": "schematic", "pos": m.start()}
            )
            continue
        if name != "adj" and direction is not None:
            claims.append(
                {"family": "feature_key", "token": token, "status": "schematic", "pos": m.start()}
            )
            continue

        status, reason = "ok", None
        if colour not in facts["census"]:
            # No such colour anywhere in the evidence. Unambiguous invention.
            status, reason = "error", f"colour {colour} is not in the census"
        elif name == "adj" and facts["census"][colour] != 1:
            # adj:C:dir is defined only for single-object colours, so this key cannot
            # exist — but the trace often names it precisely in order to REJECT it
            # (ft09 does exactly that). Assertion vs rejection is not decidable by regex.
            status, reason = "flagged", (
                f"adj:{colour}:* is undefined — census says {facts['census'][colour]} "
                "components and adj is single-object only"
            )
        claims.append(
            {
                "family": "feature_key",
                "token": token,
                "status": status,
                "reason": reason,
                "pos": m.start(),
                "context": None if status == "ok" else _ctx(body, m.start(), m.end()),
            }
        )
    return claims


def check_counts(body: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    for m in COUNT_RE.finditer(body):
        raw = next(g for g in m.groups() if g is not None)
        value = int(raw)
        if COLOUR_PREFIX_RE.search(body[max(0, m.start() - 8) : m.start()]):
            continue
        window = body[max(0, m.start() - ATTRIB_WINDOW) : m.start()]
        # An intervening sentence break or list bullet cuts the binding: "ACTION3 (30). -
        # Object census: … over 125 transitions" must not be read as a claim about ACTION3.
        window = re.split(r"[.;:\n]|\s-\s", window)[-1]
        actions = ACTION_RE.findall(window)
        attributed = f"ACTION{actions[-1]}" if actions else None
        if attributed and attributed in facts["actions"] and "transitions" in m.group(0):
            ok = value == facts["actions"][attributed]
            mode = "attributed"
            expected = facts["actions"][attributed]
        else:
            ok = facts["numbers"][value] > 0
            mode = "membership"
            expected = None
        claims.append(
            {
                "family": "count",
                "token": m.group(0).strip(),
                "value": value,
                "mode": mode,
                "attributed": attributed,
                "expected": expected,
                # An attributed count is checked against THAT action's inventory line, so a
                # mismatch is a definite misreading. A membership miss only says the number
                # is nowhere in the digest — it can also be the trace's own arithmetic.
                "status": "ok" if ok else ("error" if mode == "attributed" else "flagged"),
                "pos": m.start(),
                "context": None if ok else _ctx(body, m.start(), m.end()),
            }
        )
    return claims


def check_pairs(body: str, facts: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    for m in PAIR_RE.finditer(body):
        feature, value = m.group(1), m.group(2).strip("'\"")
        value = {"null": "None"}.get(value, value)
        ok = (feature, value) in facts["pairs"]
        claims.append(
            {
                "family": "guard_pair",
                "token": f"{feature}={value}",
                # The digest shows one example row per effect group, so a pair it never
                # shows is not thereby false, and the trace is entitled to hypothesise
                # values. Always a screen, never a verdict.
                "status": "ok" if ok else "flagged",
                "pos": m.start(),
                "context": _ctx(body, m.start(), m.end()) if not ok else None,
            }
        )
    return claims


# --------------------------------------------------------------------------------------
# Evidence-weight lexicon
# --------------------------------------------------------------------------------------
# The note's grounding fact is that tu93_125 produced a 312-support rule with ZERO
# evidence-weight language. Declared before counting, so the lexicon is not fitted to the
# result. Two bands, kept apart because they say different things: WEIGHT is "how much
# evidence is behind this", REFUTATION is "what would show it false".
LEXICON = {
    "weight": [
        r"\bsupport(?:s|ed|ing)?\b",
        r"\bsample size\b",
        r"\bsmall sample\b",
        r"\bhow many\b",
        r"\bfrequency\b",
        r"\bfrequent(?:ly)?\b",
        r"\bonly (?:one|two|a few|\d+) (?:transition|row|case|example)",
        r"\bcoincidence\b",
        r"\bstatistic(?:s|al|ally)?\b",
        r"\bconfiden(?:t|ce)\b",
        r"\bweak evidence\b",
        r"\bstrong evidence\b",
    ],
    "refutation": [
        r"\bcounter-?example\b",
        r"\bcontradict(?:s|ed|ion|ions|ory)?\b",
        r"\brefut(?:e|es|ed|ation)\b",
        r"\bfalsif(?:y|ies|ied|iable)\b",
        r"\boverfit(?:s|ting|ted)?\b",
        r"\bgeneralis|generaliz",
        r"\bwould (?:be )?(?:violate|break|disprove)\b",
        r"\bexception(?:s)?\b",
    ],
}


def lexicon_scan(body: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for band, patterns in LEXICON.items():
        hits: dict[str, int] = {}
        for pattern in patterns:
            n = len(re.findall(pattern, body, re.IGNORECASE))
            if n:
                hits[pattern] = n
        out[band] = {"total": sum(hits.values()), "hits": hits}
    return out


def think_body(raw: str) -> str:
    """The reasoning body: everything before </think>. Falls back to the whole string."""
    end = raw.find("</think>")
    body = raw if end < 0 else raw[:end]
    return body.replace("<think>", "")


# ======================================================================================
# Driver
# ======================================================================================


def cells() -> list[str]:
    return sorted(p.name[: -len(".think.json")] for p in TRACES.glob("*.think.json"))


def analyse(cell: str) -> dict[str, Any]:
    data = json.loads((TRACES / f"{cell}.think.json").read_text())
    facts = parse_digest(data["prompt"])
    body = think_body(data["raw"])
    claims = check_features(body, facts) + check_counts(body, facts) + check_pairs(body, facts)

    by_family: dict[str, dict[str, int]] = {}
    for claim in claims:
        bucket = by_family.setdefault(
            claim["family"], {"ok": 0, "error": 0, "flagged": 0, "schematic": 0}
        )
        bucket[claim["status"]] += 1

    return {
        "cell": cell,
        "game": cell.split("_")[0],
        "dose": cell.split("_")[1],
        "think_chars": len(body),
        "facts": {
            "actions": facts["actions"],
            "census": facts["census"],
            "miner_rules": facts["miner_rules"],
            "unresolved": facts["unresolved"],
            "features": facts["features"],
            "alias_lines": facts["alias_lines"],
            "completed": facts["completed"],
        },
        "rates": by_family,
        "lexicon": lexicon_scan(body),
        "claims": sorted(claims, key=lambda c: c["pos"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell")
    ap.add_argument("--show", help="print failed claims of this family")
    args = ap.parse_args()

    targets = [args.cell] if args.cell else cells()
    results = [analyse(cell) for cell in targets]

    if args.show:
        for result in results:
            bad = [
                c
                for c in result["claims"]
                if c["status"] in ("error", "flagged") and c["family"] == args.show
            ]
            print(f"\n=== {result['cell']}  {len(bad)} not-ok")
            for claim in bad:
                print(f"  [{claim['status']}] {claim['token']} — {claim.get('reason') or ''}")
                print(f"      …{claim['context']}…")
        return

    total: dict[str, dict[str, int]] = {}
    for result in results:
        for family, bucket in result["rates"].items():
            agg = total.setdefault(family, {"ok": 0, "error": 0, "flagged": 0, "schematic": 0})
            for status, n in bucket.items():
                agg[status] += n

    if not args.cell:
        OUTPUT.write_text(json.dumps({"cells": results, "total": total}, indent=1, sort_keys=True))
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
    for family, bucket in sorted(total.items()):
        checked = bucket["ok"] + bucket["error"] + bucket["flagged"]
        rate = bucket["error"] / checked if checked else 0.0
        print(
            f"  {family:12s} checked {checked:5d}  error {bucket['error']:4d} ({rate:.3f})  "
            f"flagged {bucket['flagged']:4d}  schematic {bucket['schematic']:4d}"
        )


if __name__ == "__main__":
    main()
