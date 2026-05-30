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
