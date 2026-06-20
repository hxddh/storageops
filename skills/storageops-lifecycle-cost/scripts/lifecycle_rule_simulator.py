#!/usr/bin/env python3
"""Simulate a lifecycle config against an object age/size profile and surface
STRUCTURAL cost risks. Deterministic, offline, NO currency.

Risks reported only as: minimum-duration DAYS, minimum-billable BYTES, and
amplification MULTIPLIERS. Never money.

Input: --file/--stdin a lifecycle config (XML or JSON, e.g. the output of
get-bucket-lifecycle-configuration). Profile flags: --object-age-days,
--avg-object-size, --object-count, --storage-class.

Output JSON:
{"ok":bool,"applicable_rules":[...],"min_duration_risks":[...],
 "size_penalty":{...},"warnings":[...],"summary":str,"recommendation":str}
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

# Reuse the canonical minimum-billable-size thresholds from the sibling analyzer
# so the two scripts never contradict each other.
try:
    from small_object_analyzer import _MIN_BILLABLE, _min_billable
except ImportError:  # pragma: no cover - import shim for out-of-dir execution
    import os

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from small_object_analyzer import _MIN_BILLABLE, _min_billable

# Minimum storage duration (DAYS) per storage-class family. Dated AWS defaults;
# provider-specific values must be confirmed (see references/storage-class.md).
_MIN_DURATION_DAYS = {
    "STANDARD": 0,
    "INTELLIGENT_TIERING": 0,
    "STANDARD_IA": 30,
    "ONEZONE_IA": 30,
    "GLACIER_IR": 90,
    "GLACIER": 90,
    "DEEP_ARCHIVE": 180,
}


def _min_duration_days(storage_class: str) -> int:
    upper = (storage_class or "").upper()
    for marker in sorted(_MIN_DURATION_DAYS, key=len, reverse=True):
        if marker in upper:
            return _MIN_DURATION_DAYS[marker]
    return 0


def _parse_config(text: str) -> dict:
    """Return {"ok":True,"rules":[...]} or {"ok":False,"error":str}.

    Each rule: {id, status, transitions:[{days,storage_class}],
    expiration_days, abort_multipart}.
    """
    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "Empty lifecycle configuration"}
    if text[0] in "{[":
        return _parse_json(text)
    return _parse_xml(text)


def _norm_class(value) -> str:
    return str(value or "").strip().upper().replace("-", "_")


def _parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except (ValueError, TypeError) as exc:
        return {"ok": False, "error": f"Invalid JSON: {exc}"}
    if isinstance(data, dict):
        raw_rules = data.get("Rules") or data.get("rules") or []
    elif isinstance(data, list):
        raw_rules = data
    else:
        return {"ok": False, "error": "Unrecognized JSON lifecycle shape"}
    rules = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        transitions = []
        raw_tr = raw.get("Transitions") or raw.get("transitions") or []
        if isinstance(raw_tr, dict):
            raw_tr = [raw_tr]
        for tr in raw_tr:
            if not isinstance(tr, dict):
                continue
            days = tr.get("Days", tr.get("days"))
            sc = tr.get("StorageClass", tr.get("storage_class"))
            if days is not None:
                transitions.append({"days": _to_int(days), "storage_class": _norm_class(sc)})
        exp = raw.get("Expiration") or raw.get("expiration") or {}
        exp_days = None
        if isinstance(exp, dict):
            exp_days = _to_int(exp.get("Days", exp.get("days")))
        abort = raw.get("AbortIncompleteMultipartUpload") or raw.get("abort_incomplete_multipart_upload")
        rules.append({
            "id": str(raw.get("ID", raw.get("id", ""))),
            "status": str(raw.get("Status", raw.get("status", "Enabled"))),
            "transitions": sorted(transitions, key=lambda t: (t["days"] is None, t["days"] or 0)),
            "expiration_days": exp_days,
            "abort_multipart": abort is not None,
        })
    return {"ok": True, "rules": rules}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_xml(text: str) -> dict:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        return {"ok": False, "error": f"Invalid XML: {exc}"}
    rules = []
    rule_nodes = [n for n in root.iter() if _local(n.tag) == "rule"]
    if not rule_nodes and _local(root.tag) == "rule":
        rule_nodes = [root]
    for node in rule_nodes:
        rid, status, exp_days, abort = "", "Enabled", None, False
        transitions = []
        for child in node:
            name = _local(child.tag)
            if name == "id":
                rid = (child.text or "").strip()
            elif name == "status":
                status = (child.text or "").strip() or "Enabled"
            elif name == "transition":
                days, sc = None, ""
                for sub in child:
                    sn = _local(sub.tag)
                    if sn == "days":
                        days = _to_int((sub.text or "").strip())
                    elif sn == "storageclass":
                        sc = _norm_class((sub.text or "").strip())
                if days is not None:
                    transitions.append({"days": days, "storage_class": sc})
            elif name == "expiration":
                for sub in child:
                    if _local(sub.tag) == "days":
                        exp_days = _to_int((sub.text or "").strip())
            elif name == "abortincompletemultipartupload":
                abort = True
        rules.append({
            "id": rid,
            "status": status,
            "transitions": sorted(transitions, key=lambda t: (t["days"] is None, t["days"] or 0)),
            "expiration_days": exp_days,
            "abort_multipart": abort,
        })
    return {"ok": True, "rules": rules}


def _to_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _enabled(rule: dict) -> bool:
    return str(rule.get("status", "")).strip().lower() == "enabled"


def analyze(rules: list, age_days, avg_size, object_count, start_class: str) -> dict:
    warnings = []
    applicable_rules = []
    min_duration_risks = []

    start_class = _norm_class(start_class) or "STANDARD"
    # Ordered timeline of class-residency boundaries across all enabled rules.
    events = []  # (day, kind, storage_class)
    for rule in rules:
        if not _enabled(rule):
            warnings.append(f"Rule '{rule.get('id') or '?'}' is Disabled; its actions will not apply")
            continue
        for tr in rule["transitions"]:
            if tr["days"] is None:
                continue
            events.append((tr["days"], "transition", tr["storage_class"]))
        if rule.get("expiration_days") is not None:
            events.append((rule["expiration_days"], "expire", None))
        # Rule-conflict: transition-after-N coincident-or-after expiration.
        if rule.get("expiration_days") is not None:
            for tr in rule["transitions"]:
                if tr["days"] is not None and tr["days"] >= rule["expiration_days"]:
                    warnings.append(
                        f"Rule '{rule.get('id') or '?'}': transition to {tr['storage_class']} "
                        f"at day {tr['days']} never fires (expiration at day {rule['expiration_days']})"
                    )
        if not rule.get("abort_multipart"):
            warnings.append(
                f"Rule '{rule.get('id') or '?'}' has no AbortIncompleteMultipartUpload: "
                "orphaned/incomplete multipart parts remain billable"
            )

    events.sort(key=lambda e: e[0])

    # Walk the timeline to determine class residency windows. A class entered at
    # day D and left at day L bills for max(L-D, min_duration_days). If the
    # residency is shorter than the minimum duration, wasted_days are billed.
    current_class = start_class
    current_since = 0
    for day, kind, sc in events:
        # Close out the current residency at `day`.
        residency = day - current_since
        min_days = _min_duration_days(current_class)
        if min_days > 0 and residency < min_days:
            min_duration_risks.append({
                "class": current_class,
                "min_days": min_days,
                "residency_days": residency,
                "wasted_days": min_days - residency,
            })
        if kind == "transition":
            current_class = sc
            current_since = day
        elif kind == "expire":
            current_class = None
            break

    # Report which transitions/expirations actually apply at the requested age.
    if age_days is not None:
        eff_class = start_class
        for rule in rules:
            if not _enabled(rule):
                continue
            for tr in rule["transitions"]:
                if tr["days"] is not None and tr["days"] <= age_days:
                    applicable_rules.append({
                        "rule_id": rule.get("id"),
                        "action": "transition",
                        "at_day": tr["days"],
                        "storage_class": tr["storage_class"],
                    })
                    eff_class = tr["storage_class"]
            if rule.get("expiration_days") is not None and rule["expiration_days"] <= age_days:
                applicable_rules.append({
                    "rule_id": rule.get("id"),
                    "action": "expire",
                    "at_day": rule["expiration_days"],
                    "storage_class": None,
                })
        effective_class = eff_class
    else:
        effective_class = start_class

    # Minimum-billable-size penalty for the effective resting class.
    size_penalty = None
    if avg_size is not None:
        floor = _min_billable(effective_class)
        if floor > 0 and avg_size < floor:
            multiplier = round(floor / max(avg_size, 1), 2)
            size_penalty = {
                "class": effective_class,
                "min_billable_bytes": floor,
                "avg_object_size": avg_size,
                "multiplier": multiplier,
            }
            if object_count:
                size_penalty["object_count"] = object_count
                size_penalty["billable_bytes"] = floor * object_count
            warnings.append(
                f"Objects average {avg_size} bytes below the {effective_class} minimum "
                f"billable size {floor} bytes: storage amplified {multiplier}x"
            )

    summary = _summary(min_duration_risks, size_penalty, effective_class)
    recommendation = _recommendation(min_duration_risks, size_penalty, rules)

    return {
        "ok": True,
        "applicable_rules": applicable_rules,
        "min_duration_risks": min_duration_risks,
        "size_penalty": size_penalty,
        "warnings": warnings,
        "summary": summary,
        "recommendation": recommendation,
    }


def _summary(min_duration_risks, size_penalty, effective_class) -> str:
    parts = [f"Effective resting class at given age: {effective_class}."]
    if min_duration_risks:
        worst = max(min_duration_risks, key=lambda r: r["wasted_days"])
        parts.append(
            f"Minimum-duration penalty: {worst['class']} requires {worst['min_days']} days "
            f"but residency is {worst['residency_days']} days "
            f"({worst['wasted_days']} wasted days billed)."
        )
    if size_penalty:
        parts.append(
            f"Small-object amplification {size_penalty['multiplier']}x against the "
            f"{size_penalty['min_billable_bytes']}-byte minimum billable size."
        )
    if not min_duration_risks and not size_penalty:
        parts.append("No minimum-duration or minimum-billable-size structural risk detected.")
    return " ".join(parts)


def _recommendation(min_duration_risks, size_penalty, rules) -> str:
    recs = []
    if min_duration_risks:
        worst = max(min_duration_risks, key=lambda r: r["wasted_days"])
        recs.append(
            f"Delay the transition into {worst['class']} or extend its residency to at "
            f"least the {worst['min_days']}-day minimum duration before deleting or "
            "re-transitioning."
        )
    if size_penalty:
        recs.append(
            f"Aggregate objects above the {size_penalty['min_billable_bytes']}-byte minimum "
            "billable size (tar/zip) or keep small objects in STANDARD before any "
            "transition to avoid the size multiplier."
        )
    if rules and not any(r.get("abort_multipart") for r in rules):
        recs.append("Add an AbortIncompleteMultipartUpload rule to reclaim orphaned multipart parts.")
    if not recs:
        recs.append("Lifecycle configuration shows no structural minimum-duration or size risk.")
    return " ".join(recs)


def run(file_path=None, use_stdin=False, age_days=None, avg_size=None,
        object_count=None, storage_class="STANDARD") -> dict:
    if file_path:
        try:
            with open(file_path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as exc:
            return {"ok": False, "error": f"Cannot read file: {exc}"}
    elif use_stdin:
        text = sys.stdin.read()
    else:
        return {"ok": False, "error": "Provide --file or --stdin"}

    parsed = _parse_config(text)
    if not parsed["ok"]:
        return {"ok": False, "error": parsed["error"]}
    return analyze(parsed["rules"], age_days, avg_size, object_count, storage_class)


def main() -> None:
    p = argparse.ArgumentParser(description="Lifecycle rule structural-cost simulator")
    p.add_argument("--file", "-f", help="Lifecycle config (XML or JSON)")
    p.add_argument("--stdin", action="store_true", help="Read config from stdin")
    p.add_argument("--object-age-days", type=int, default=None)
    p.add_argument("--avg-object-size", type=int, default=None, help="Average object size in bytes")
    p.add_argument("--object-count", type=int, default=None)
    p.add_argument("--storage-class", default="STANDARD", help="Starting storage class")
    p.add_argument("--pretty", "-p", action="store_true")
    args = p.parse_args()
    if not args.file and not args.stdin:
        p.error("Either --file or --stdin is required")
    try:
        result = run(
            file_path=args.file, use_stdin=args.stdin, age_days=args.object_age_days,
            avg_size=args.avg_object_size, object_count=args.object_count,
            storage_class=args.storage_class,
        )
    except Exception as exc:  # never traceback
        result = {"ok": False, "error": f"Unexpected: {exc}"}
    json.dump(result, sys.stdout, indent=2 if args.pretty else None,
              default=str, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
