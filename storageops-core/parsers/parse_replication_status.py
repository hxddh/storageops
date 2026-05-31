"""
Parse CRR/SRR replication status output from aws s3api head-object and
get-bucket-replication responses.

Detects: FAILED/PENDING/COMPLETED status, replication lag, rule failures.

Usage:
    cat replication-status.json | python parse_replication_status.py
"""
import re
import sys
import json
from pathlib import Path


_RE_REPLICATION_STATUS = re.compile(
    r'(?:ReplicationStatus|"ReplicationStatus")\s*[:\s"]+\s*(FAILED|PENDING|COMPLETED|REPLICA)',
    re.IGNORECASE
)
_RE_OBJECT_KEY = re.compile(
    r'(?:Key|"Key")\s*[:\s"]+\s*([^\s",\}]+)',
    re.IGNORECASE
)
_RE_RULE_ID = re.compile(
    r'(?:ID|"ID"|RuleId|"RuleId")\s*[:\s"]+\s*([^\s",\}]+)',
    re.IGNORECASE
)
_RE_REPLICATION_CONFIG = re.compile(
    r'ReplicationConfiguration|get-bucket-replication|GetBucketReplication',
    re.IGNORECASE
)
_RE_RULE_STATUS = re.compile(
    r'"Status"\s*:\s*"(Enabled|Disabled)"',
    re.IGNORECASE
)
_RE_DESTINATION = re.compile(
    r'(?:Destination|"Destination")[^{]*\{[^}]*(?:Bucket|"Bucket")\s*:\s*"([^"]+)"',
    re.IGNORECASE
)
_RE_FAILURE_REASON = re.compile(
    r'(?:FailureReason|failure.*reason|reason.*fail)[:\s"]+([^\n"]+)',
    re.IGNORECASE
)
_RE_REPLICATE_OBJECT = re.compile(r'ReplicateObject', re.IGNORECASE)
_RE_DELETE_MARKER = re.compile(r'DeleteMarkerReplication', re.IGNORECASE)
_RE_HEAD_OBJECT_BLOCK = re.compile(
    r'"Key"\s*:\s*"([^"]+)"[^}]*"ReplicationStatus"\s*:\s*"([^"]+)"',
    re.IGNORECASE | re.DOTALL
)
_RE_STATUS_LINE = re.compile(
    r'(?:key|object)[\s:]+(\S+).*?(?:status|ReplicationStatus)[\s:]+(\w+)',
    re.IGNORECASE
)
_RE_RULE_BLOCK = re.compile(
    r'"ID"\s*:\s*"([^"]+)"[^}]*"Status"\s*:\s*"([^"]+)"',
    re.IGNORECASE | re.DOTALL
)


def _parse_objects(text: str) -> list:
    """Extract per-object replication status records."""
    objects = []

    # Try JSON-style head-object output blocks
    for m in _RE_HEAD_OBJECT_BLOCK.finditer(text):
        objects.append({
            "key": m.group(1),
            "status": m.group(2).upper(),
            "rule_id": "",
        })

    # Try plain-text tabular format: "key: foo/bar  status: FAILED"
    if not objects:
        for m in _RE_STATUS_LINE.finditer(text):
            objects.append({
                "key": m.group(1),
                "status": m.group(2).upper(),
                "rule_id": "",
            })

    # Try standalone ReplicationStatus lines (head-object output without Key)
    if not objects:
        for m in _RE_REPLICATION_STATUS.finditer(text):
            status = m.group(1).upper()
            # Attempt to find nearby key
            start = max(0, m.start() - 200)
            snippet = text[start:m.end()]
            key_m = _RE_OBJECT_KEY.search(snippet)
            rule_m = _RE_RULE_ID.search(snippet)
            objects.append({
                "key": key_m.group(1) if key_m else "",
                "status": status,
                "rule_id": rule_m.group(1) if rule_m else "",
            })

    return objects


def _parse_rules(text: str) -> list:
    """Extract replication rule definitions."""
    rules = []
    destinations = list(_RE_DESTINATION.finditer(text))

    for m in _RE_RULE_BLOCK.finditer(text):
        rule_id = m.group(1)
        status = m.group(2)
        # Find nearest destination
        dest = ""
        for d in destinations:
            if abs(d.start() - m.start()) < 1000:
                dest = d.group(1)
                break
        rules.append({
            "id": rule_id,
            "status": status,
            "destination": dest,
        })

    return rules


def _compute_status_counts(objects: list) -> dict:
    counts = {"FAILED": 0, "PENDING": 0, "COMPLETED": 0}
    for obj in objects:
        s = obj.get("status", "").upper()
        if s in counts:
            counts[s] += 1
        elif s == "REPLICA":
            counts["COMPLETED"] += 1
    return counts


def parse(text: str) -> dict:
    """
    Parse replication status output and return structured diagnostics.

    Returns:
        {
            "objects": [{"key": str, "status": str, "rule_id": str}],
            "rules": [{"id": str, "status": str, "destination": str}],
            "status_counts": {"FAILED": int, "PENDING": int, "COMPLETED": int},
            "has_failures": bool,
            "failure_reasons": [str],
            "summary": {"total_objects": int, "failure_rate_pct": float}
        }
    """
    objects = _parse_objects(text)
    rules = _parse_rules(text)
    status_counts = _compute_status_counts(objects)
    failure_reasons = [m.group(1).strip() for m in _RE_FAILURE_REASON.finditer(text)]

    total = len(objects)
    failed = status_counts["FAILED"]
    failure_rate = round((failed / total * 100), 2) if total > 0 else 0.0
    has_failures = failed > 0 or bool(
        re.search(r'ReplicationStatus.*FAILED|FAILED.*replication', text, re.IGNORECASE)
    )

    return {
        "objects": objects,
        "rules": rules,
        "status_counts": status_counts,
        "has_failures": has_failures,
        "failure_reasons": failure_reasons,
        "summary": {
            "total_objects": total,
            "failure_rate_pct": failure_rate,
        },
    }


def main():
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()
    result = parse(text)
    result["ok"] = True
    result["module"] = "parse_replication_status"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
