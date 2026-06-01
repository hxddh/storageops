"""
Safety lint for StorageOps agent responses.

Scans output for secrets, destructive recommendations, and security risks.
Returns warnings but does NOT block output — the agent flows naturally.
"""
from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    re.compile(r"\bLTAI[A-Za-z0-9]{16,24}\b"),
    re.compile(r"\bAKID[A-Za-z0-9]{32}\b"),
    re.compile(r"(?i)Authorization:\s*\S+\s+\S+"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+/-]{20,}=*"),
    re.compile(r"(?i)(secret_access_key|aws_secret_access_key|secretkey|api[_-]?key)\s*[:=]\s*[^\s`]+"),
    re.compile(r"(?i)(cookie|set-cookie):\s*.*"),
    re.compile(r"(?i)X-Amz-Signature=[0-9a-f]{32,64}"),
]

_DESTRUCTIVE_PATTERNS = [
    (re.compile(r"\b(delete|remove)\s+(?:the\s+)?bucket\b", re.IGNORECASE), "delete_bucket"),
    (re.compile(r"\b(delete|remove)\s+(?:the\s+)?objects?\b", re.IGNORECASE), "delete_object"),
    (re.compile(r"\b(?:aws\s+)?s3api\s+delete-bucket\b", re.IGNORECASE), "s3api_delete_bucket"),
    (re.compile(r"\b(?:aws\s+)?s3api\s+delete-objects?\b", re.IGNORECASE), "s3api_delete_object"),
    (re.compile(r"\bdelete-bucket\b", re.IGNORECASE), "delete_bucket"),
    (re.compile(r"\bdelete-objects?\b", re.IGNORECASE), "delete_object"),
    (re.compile(r"\baws\s+s3\s+rm\b", re.IGNORECASE), "aws_s3_rm"),
    (re.compile(r"\brm\s+(?:-[^\s]+\s+)*s3://", re.IGNORECASE), "rm_s3_uri"),
    (re.compile(r"\bs3\w*\s+rm\b", re.IGNORECASE), "s3_rm"),
    (re.compile(r"\b(?:s3cmd|s5cmd)\s+(?:del|delete|rm)\b", re.IGNORECASE), "s3_delete_command"),
    (re.compile(r"\bmc\s+rm\b", re.IGNORECASE), "mc_rm"),
    (re.compile(r"\brclone\s+(?:delete|deletefile|purge)\b.*\bs3:", re.IGNORECASE), "rclone_s3_delete"),
    (re.compile(r"\bput-bucket-policy\b", re.IGNORECASE), "put_bucket_policy"),
    (re.compile(r"\bput-bucket-acl\b", re.IGNORECASE), "put_bucket_acl"),
    (re.compile(r"\bput-bucket-lifecycle", re.IGNORECASE), "put_bucket_lifecycle"),
]


def _line_has_manual_only(line: str) -> bool:
    return "manual-only" in line.lower()


def safety_lint(text: str) -> dict:
    """
    Scan agent output for safety issues. Non-blocking — returns warnings only.

    Returns:
        {"issues": [...], "secret_leaks": int, "destructive_no_label": int}
    """
    issues: list[str] = []
    secret_leaks = 0
    destructive_no_label = 0

    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            issues.append("report may contain a secret or signed credential")
            secret_leaks += 1
            break

    for line in text.splitlines():
        if _line_has_manual_only(line):
            continue
        for pattern, name in _DESTRUCTIVE_PATTERNS:
            if pattern.search(line):
                issues.append(f"destructive operation lacks manual-only label: {name}")
                destructive_no_label += 1
                break

    public_bucket = re.search(r"(?i)(make|set|configure).{0,40}(bucket|object).{0,40}public", text)
    strong_warning = re.search(r"(?i)(strong warning|security warning|risk|do not|manual-only)", text)
    if public_bucket and not strong_warning:
        issues.append("public bucket exposure recommendation lacks a strong warning")

    disable_security = re.search(
        r"(?i)disable\s+(tls|ssl|encryption|kms|block public access|security controls?)", text
    )
    if disable_security and not strong_warning:
        issues.append("disabling security controls recommendation lacks a warning")

    return {
        "issues": issues,
        "secret_leaks": secret_leaks,
        "destructive_no_label": destructive_no_label,
    }


# ── Legacy validate_report (kept for backward compat) ──

_REQUIRED_FIELDS = {"category", "root_cause_type", "confidence", "severity"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def validate_report(text: str) -> dict:
    """Legacy YAML frontmatter validation — kept for eval and tests."""
    result: dict = {
        "valid": False,
        "has_frontmatter": False,
        "missing_fields": [],
        "invalid_fields": {},
        "warnings": [],
    }
    m = _FRONTMATTER_RE.match(text.strip())
    if not m:
        result["missing_fields"] = list(_REQUIRED_FIELDS)
        return result
    result["has_frontmatter"] = True
    yaml_block = m.group(1)
    fields = _parse_simple_yaml(yaml_block)
    missing = [f for f in _REQUIRED_FIELDS if f not in fields]
    result["missing_fields"] = missing
    if "confidence" in fields:
        try:
            conf = float(fields["confidence"])
            if not (0.0 <= conf <= 1.0):
                result["invalid_fields"]["confidence"] = f"{conf!r} is not in range 0.0–1.0"
        except ValueError:
            result["invalid_fields"]["confidence"] = f"{fields['confidence']!r} is not a float"
    if "severity" in fields:
        sev = fields["severity"].lower()
        if sev not in _VALID_SEVERITIES:
            result["invalid_fields"]["severity"] = f"{fields['severity']!r} not in {sorted(_VALID_SEVERITIES)}"
    if "root_cause_type" in fields:
        rt = fields["root_cause_type"].strip()
        if rt in ("", "unknown"):
            result["warnings"].append("root_cause_type is 'unknown' — diagnosis may be incomplete")
    result["valid"] = not missing and not result["invalid_fields"]
    return result


def _parse_simple_yaml(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip().strip('"').strip("'")
    return fields


# Legacy validate_agent_report — kept for backward compat but non-blocking
def validate_agent_report(text: str) -> dict:
    """Legacy compat: always returns valid=True. Use safety_lint() instead."""
    lint = safety_lint(text)
    return {
        "valid": True,  # always pass — safety lint is non-blocking now
        "errors": lint["issues"],
        "frontmatter": validate_report(text),
    }
