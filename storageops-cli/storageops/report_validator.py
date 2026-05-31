"""
Validate the YAML frontmatter and required sections in LLM diagnostic reports.

The agent's system prompt requires every report to start with a YAML block:
    ---
    category: <domain>
    root_cause_type: <type>
    confidence: <0.0–1.0>
    severity: critical | high | medium | low
    ---

This module validates that structure so tests and the agent loop can
check output quality without re-running the full agent.
"""
from __future__ import annotations

import re

_REQUIRED_FIELDS = {"category", "root_cause_type", "confidence", "severity"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def validate_report(text: str) -> dict:
    """
    Validate a diagnostic report's YAML frontmatter and required sections.

    Returns:
        {
            "valid": bool,
            "has_frontmatter": bool,
            "missing_fields": list[str],
            "invalid_fields": dict[str, str],   # field → reason
            "warnings": list[str],
        }
    """
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
        result["warnings"].append("Report does not begin with YAML frontmatter (--- ... ---)")
        return result

    result["has_frontmatter"] = True
    yaml_block = m.group(1)
    fields = _parse_simple_yaml(yaml_block)

    missing = [f for f in _REQUIRED_FIELDS if f not in fields]
    result["missing_fields"] = missing

    # Validate individual fields
    if "confidence" in fields:
        try:
            conf = float(fields["confidence"])
            if not (0.0 <= conf <= 1.0):
                result["invalid_fields"]["confidence"] = (
                    f"{conf!r} is not in range 0.0–1.0"
                )
        except ValueError:
            result["invalid_fields"]["confidence"] = (
                f"{fields['confidence']!r} is not a float"
            )

    if "severity" in fields:
        sev = fields["severity"].lower()
        if sev not in _VALID_SEVERITIES:
            result["invalid_fields"]["severity"] = (
                f"{fields['severity']!r} not in {sorted(_VALID_SEVERITIES)}"
            )

    if "root_cause_type" in fields:
        rt = fields["root_cause_type"].strip()
        if rt in ("", "unknown"):
            result["warnings"].append("root_cause_type is 'unknown' — diagnosis may be incomplete")

    result["valid"] = not missing and not result["invalid_fields"]
    return result


def _parse_simple_yaml(block: str) -> dict[str, str]:
    """Parse key: value pairs from a YAML block (no nested structures)."""
    fields: dict[str, str] = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip().strip('"').strip("'")
    return fields

# ── Agent safety validation gate ──────────────────────────────────────

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


def _has_section(text: str, section_name: str) -> bool:
    return re.search(rf"^##+\s+{re.escape(section_name)}\b", text, re.IGNORECASE | re.MULTILINE) is not None


def validate_agent_report(text: str) -> dict:
    """Validate Pi-produced report structure, evidence, safety, and secret leakage.

    Returns a dict with ``valid`` and ``errors``. This hard gate is used before
    StorageOps prints a Pi report as final output.
    """
    result = validate_report(text)
    errors: list[str] = []

    if not result.get("has_frontmatter"):
        errors.append("YAML frontmatter is missing")
    for field in result.get("missing_fields", []):
        errors.append(f"{field} is missing")
    for field, reason in result.get("invalid_fields", {}).items():
        errors.append(f"{field} is invalid: {reason}")

    if not _has_section(text, "Key Evidence") and not _has_section(text, "Evidence"):
        errors.append("evidence section is missing")

    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            errors.append("report contains an obvious secret or signed credential")
            break

    for line in text.splitlines():
        if _line_has_manual_only(line):
            continue
        for pattern, name in _DESTRUCTIVE_PATTERNS:
            if pattern.search(line):
                errors.append(f"destructive operation lacks manual-only label: {name}")
                break

    public_bucket = re.search(r"(?i)(make|set|configure).{0,40}(bucket|object).{0,40}public", text)
    strong_warning = re.search(r"(?i)(strong warning|security warning|risk|do not|manual-only)", text)
    if public_bucket and not strong_warning:
        errors.append("public bucket exposure recommendation lacks a strong warning")

    disable_security = re.search(
        r"(?i)disable\s+(tls|ssl|encryption|kms|block public access|security controls?)", text
    )
    if disable_security and not strong_warning:
        errors.append("disabling security controls recommendation lacks a warning")

    return {
        "valid": not errors,
        "errors": errors,
        "frontmatter": result,
    }
