#!/usr/bin/env python3
"""Offline, deterministic analyzer for S3 replication / versioning evidence.

Classifies the dominant failure class from get-bucket-replication /
get-bucket-versioning / head-object output and/or free-text logs (--file/--stdin).
Never contacts a bucket. Failure classes, in priority order:
dest_versioning_disabled, source_versioning_suspended, rule_disabled,
delete_marker_not_replicated, replication_failed, healthy.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional

# --- destination versioning ------------------------------------------------
# `get-bucket-versioning` on an unversioned bucket returns {} (no Status key).
_RE_VERS_STATUS = re.compile(r'"Status"\s*:\s*"(Enabled|Suspended)"')
_RE_GET_VERSIONING = re.compile(r"get-bucket-versioning", re.I)
_RE_DEST_HINT = re.compile(r"destination", re.I)
_RE_REPL_FAILED = re.compile(r'ReplicationStatus["\s:]+\s*"?FAILED', re.I)
_RE_FAILED_METRIC = re.compile(r"OperationsFailedReplication\b[^\n:]*:\s*([0-9]+)", re.I)


def _as_text(data) -> str:
    return data if isinstance(data, str) else json.dumps(data)


def _find_json_objects(text: str) -> List[dict]:
    """Extract balanced top-level {...} JSON objects embedded in free text."""
    objs: List[dict] = []
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    blob = text[start : i + 1]
                    try:
                        parsed = json.loads(blob)
                        if isinstance(parsed, dict):
                            objs.append(parsed)
                    except Exception:
                        pass
                    start = -1
    return objs


def _versioning_status(obj: dict) -> Optional[str]:
    """Return 'Enabled'/'Suspended'/None for a get-bucket-versioning-shaped dict."""
    if "Status" in obj and "Rules" not in obj and "ReplicationConfiguration" not in obj:
        return obj.get("Status")
    return None


def _replication_rules(obj: dict) -> List[dict]:
    cfg = obj.get("ReplicationConfiguration", obj)
    rules = cfg.get("Rules")
    return rules if isinstance(rules, list) else []


def analyze(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {
            "ok": False,
            "summary": "No replication/versioning evidence provided.",
            "root_cause": "no_input",
            "findings": [],
            "recommendation": "Provide get-bucket-replication / get-bucket-versioning output or a replication log.",
        }

    objects = _find_json_objects(text)
    findings: List[str] = []

    # --- gather signals ----------------------------------------------------
    rules: List[dict] = []
    source_versioning: Optional[str] = None
    dest_versioning_enabled: Optional[bool] = None

    for obj in objects:
        rules.extend(_replication_rules(obj))

    # Versioning state: associate each get-bucket-versioning block with the
    # nearest preceding "destination"/"get-bucket-versioning" hint in the text.
    for m in re.finditer(r"\{[^{}]*\}", text):
        block = m.group(0)
        status_m = _RE_VERS_STATUS.search(block)
        # Look at a window before this block for context.
        window = text[max(0, m.start() - 200) : m.start()]
        # Only treat a {...} as a versioning block when get-bucket-versioning is
        # invoked nearby, OR the whole input is a bare versioning response. This
        # avoids misreading DeleteMarkerReplication's {"Status": "Disabled"}.
        near_cmd = bool(_RE_GET_VERSIONING.search(window))
        bare = text.strip() in ("{}",) or (
            block.strip() == text.strip() and "Bucket" not in block and "Rules" not in block
        )
        if not (near_cmd or bare):
            continue
        is_dest = bool(_RE_DEST_HINT.search(window))
        status = status_m.group(1) if status_m else None  # {} -> None -> disabled
        if is_dest:
            dest_versioning_enabled = status == "Enabled"
        elif status == "Suspended":
            source_versioning = "Suspended"
        elif status == "Enabled" and source_versioning is None:
            source_versioning = "Enabled"

    repl_failed = bool(_RE_REPL_FAILED.search(text))
    failed_metric_m = _RE_FAILED_METRIC.search(text)
    failed_count = int(failed_metric_m.group(1)) if failed_metric_m else None

    # delete marker replication
    dmr_disabled = False
    for r in rules:
        dmr = (r.get("DeleteMarkerReplication") or {}).get("Status")
        if dmr and dmr != "Enabled":
            dmr_disabled = True
    if not rules and re.search(r"DeleteMarkerReplication[^}]*Disabled", text, re.I):
        dmr_disabled = True
    delete_marker_complaint = bool(
        re.search(r"delete\s*marker", text, re.I) and re.search(r"replica\w* still|not replicat", text, re.I)
    )

    # rule status
    rule_statuses = [r.get("Status") for r in rules]
    has_enabled_rule = any(s == "Enabled" for s in rule_statuses)
    has_rule = bool(rules)
    rule_disabled = has_rule and not has_enabled_rule

    # --- classify (priority order) -----------------------------------------
    root_cause = "healthy"
    summary = "No replication/versioning failure detected in the provided evidence."
    recommendation = "Configuration looks consistent; if objects are still missing, gather CloudWatch replication metrics."
    ok = True

    if dest_versioning_enabled is False:
        ok = False
        root_cause = "dest_versioning_disabled"
        summary = (
            "Destination bucket versioning is not Enabled (get-bucket-versioning shows no "
            "Status: Enabled). S3 replication requires versioning on BOTH buckets, so every "
            "replication fails."
        )
        recommendation = (
            "Enable versioning on the destination bucket: "
            "aws s3api put-bucket-versioning --bucket <dest> --versioning-configuration Status=Enabled. "
            "Verify with get-bucket-versioning. Re-replicate pre-existing objects with S3 Batch Replication. "
            "(Enabling versioning is irreversible.)"
        )
        findings.append("destination get-bucket-versioning is not Enabled")
        if repl_failed:
            findings.append("ReplicationStatus: FAILED confirms replication is being attempted and rejected")
        if failed_count:
            findings.append(f"OperationsFailedReplication: {failed_count}")
    elif source_versioning == "Suspended":
        ok = False
        root_cause = "source_versioning_suspended"
        summary = "Versioning is Suspended on the source bucket; new objects get versionId=null and are not replicated."
        recommendation = (
            "Re-enable versioning on the source: put-bucket-versioning ... Status=Enabled. "
            "Replication only applies to versioned objects created after re-enabling."
        )
        findings.append("source get-bucket-versioning Status: Suspended")
    elif rule_disabled:
        ok = False
        root_cause = "rule_disabled"
        summary = "The replication rule is not Enabled (Status Disabled or missing), so no objects replicate."
        recommendation = (
            "Set the replication rule Status to Enabled in the bucket replication configuration "
            "(get-bucket-replication / put-bucket-replication)."
        )
        findings.append(f"replication rule statuses: {rule_statuses or 'none found'}")
    elif delete_marker_complaint or (dmr_disabled and not repl_failed):
        ok = False
        root_cause = "delete_marker_not_replicated"
        summary = (
            "Delete markers are not replicated: DeleteMarkerReplication is Disabled in the rule, so "
            "deleting a source object leaves the destination replica intact."
        )
        recommendation = (
            "Set DeleteMarkerReplication: {Status: Enabled} on the replication rule. "
            "Existing delete markers must be cleaned up manually on the destination."
        )
        findings.append("DeleteMarkerReplication is Disabled in the replication rule")
    elif repl_failed or failed_count:
        ok = False
        root_cause = "replication_failed"
        summary = "Objects show ReplicationStatus: FAILED but no single config cause was isolated from the evidence."
        recommendation = (
            "Check destination versioning, the replication IAM role permissions "
            "(s3:ReplicateObject/ReplicateDelete) and KMS grants for SSE-KMS objects."
        )
        if repl_failed:
            findings.append("ReplicationStatus: FAILED")
        if failed_count:
            findings.append(f"OperationsFailedReplication: {failed_count}")

    # informational add-ons (do not change root cause)
    if dmr_disabled and root_cause not in ("delete_marker_not_replicated",):
        findings.append("note: DeleteMarkerReplication is Disabled (delete markers will not propagate)")
    if re.search(r"before\s+replication\s+was\s+configured|not\s+retroactive|pre-?existing", text, re.I):
        findings.append("note: objects created before the rule are not replicated retroactively (use S3 Batch Replication)")

    return {
        "ok": ok,
        "summary": summary,
        "root_cause": root_cause,
        "findings": findings,
        "recommendation": recommendation,
    }


def _read_input(args) -> str:
    if args.stdin:
        return sys.stdin.read()
    if args.file:
        try:
            return Path(args.file).read_text(encoding="utf-8")
        except Exception as exc:
            print(json.dumps({
                "ok": False,
                "summary": f"cannot read input file: {exc}",
                "root_cause": "no_input",
                "findings": [],
                "recommendation": "Provide a readable --file or pipe evidence via --stdin.",
            }))
            raise SystemExit(0)
    return ""


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", help="Path to replication/versioning evidence (JSON and/or log text)")
    ap.add_argument("--stdin", action="store_true", help="Read evidence from stdin")
    args = ap.parse_args(argv)

    raw = _read_input(args)
    try:
        result = analyze(raw)
    except Exception as exc:  # never emit a traceback
        result = {
            "ok": False,
            "summary": f"analyzer error: {exc}",
            "root_cause": "error",
            "findings": [],
            "recommendation": "Check the input format (get-bucket-replication / get-bucket-versioning output or a log).",
        }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
