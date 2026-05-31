"""
Action tools: generate corrected configurations from diagnostic findings.

These tools output text (XML/JSON) for the user to review and apply manually.
They never connect to cloud APIs or modify live resources.
All outputs must be labeled with manual-only usage instructions.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET


# ── Lifecycle fix ─────────────────────────────────────────────────────

def generate_lifecycle_fix(xml_text: str) -> dict:
    """
    Generate a corrected lifecycle XML that addresses common issues:
    - Adds ObjectSizeGreaterThan filter (128 KB) to STANDARD_IA transitions
      to avoid minimum billable size penalty
    - Increases transition days to at least 30 for STANDARD_IA (minimum duration)
    - Leaves GLACIER / DEEP_ARCHIVE rules untouched (different thresholds)
    """
    changes: list[str] = []
    issues: list[str] = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"ok": False, "error": f"XML parse error: {e}"}

    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    def tag(name: str) -> str:
        return f"{ns}{name}"

    for rule in root.findall(tag("Rule")):
        rule_id_el = rule.find(tag("ID"))
        rule_id = rule_id_el.text if rule_id_el is not None else "(unnamed)"

        for transition in rule.findall(tag("Transition")):
            sc_el = transition.find(tag("StorageClass"))
            days_el = transition.find(tag("Days"))
            if sc_el is None:
                continue
            sc = sc_el.text or ""

            if sc in ("STANDARD_IA", "ONEZONE_IA"):
                # Ensure minimum 30-day wait
                if days_el is not None:
                    days = int(days_el.text or "0")
                    if days < 30:
                        days_el.text = "30"
                        changes.append(
                            f"Rule '{rule_id}': increased transition Days {days}→30 "
                            f"(STANDARD_IA minimum duration is 30 days)"
                        )

                # Add size filter to avoid 128 KB minimum billing
                filter_el = rule.find(tag("Filter"))
                if filter_el is None:
                    filter_el = ET.SubElement(rule, tag("Filter"))

                # Wrap existing prefix in And if needed
                prefix_el = filter_el.find(tag("Prefix"))
                and_el = filter_el.find(tag("And"))

                if and_el is None and prefix_el is None:
                    # Empty filter: add And with size
                    and_el = ET.SubElement(filter_el, tag("And"))
                    sz = ET.SubElement(and_el, tag("ObjectSizeGreaterThan"))
                    sz.text = "131072"
                    changes.append(
                        f"Rule '{rule_id}': added ObjectSizeGreaterThan 131072 (128 KB) "
                        "to avoid STANDARD_IA minimum size billing for small objects"
                    )
                elif prefix_el is not None and and_el is None:
                    # Existing prefix: wrap in And
                    prefix_text = prefix_el.text or ""
                    filter_el.remove(prefix_el)
                    and_el = ET.SubElement(filter_el, tag("And"))
                    p = ET.SubElement(and_el, tag("Prefix"))
                    p.text = prefix_text
                    sz = ET.SubElement(and_el, tag("ObjectSizeGreaterThan"))
                    sz.text = "131072"
                    changes.append(
                        f"Rule '{rule_id}': added ObjectSizeGreaterThan 131072 (128 KB) "
                        f"alongside existing Prefix '{prefix_text}'"
                    )
                elif and_el is not None:
                    sz_el = and_el.find(tag("ObjectSizeGreaterThan"))
                    if sz_el is None:
                        sz = ET.SubElement(and_el, tag("ObjectSizeGreaterThan"))
                        sz.text = "131072"
                        changes.append(
                            f"Rule '{rule_id}': added ObjectSizeGreaterThan 131072 (128 KB) "
                            "to existing And filter"
                        )

    if not changes:
        issues.append("No automatic fixes applied — rules already look correct, or issues need manual review.")

    ET.indent(root, space="  ")
    fixed_xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")

    return {
        "ok": True,
        "fixed_xml": fixed_xml,
        "changes": changes,
        "issues": issues,
        "usage": (
            "# manual-only: review changes above, then apply via:\n"
            "# aws s3api put-bucket-lifecycle-configuration "
            "--bucket <BUCKET> --lifecycle-configuration file://lifecycle-fixed.xml"
        ),
    }


# ── Policy fix ────────────────────────────────────────────────────────

def generate_policy_fix(data: dict) -> dict:
    """
    Generate a fixed IAM or bucket policy statement addressing the denial.

    Input: same as analyze_policy() — principal, action, resource, iam_policy, bucket_policy.
    Output: suggested fix statement(s) to add to the relevant policy.
    """
    from analyze_policy import analyze

    analysis = analyze(data)
    denial_source = analysis.get("denial_source", "unknown")
    principal = data.get("principal", "")
    action = data.get("action", "s3:GetObject")
    resource = data.get("resource", "")

    fixes: list[dict] = []
    explanation = ""

    if denial_source == "cross_account_missing_iam_allow":
        # Need to add allow to IAM policy
        fixes.append({
            "policy_type": "iam_policy",
            "statement_to_add": {
                "Effect": "Allow",
                "Action": [action],
                "Resource": resource,
            },
            "note": "Add this statement to the IAM policy for the principal.",
        })
        explanation = (
            f"Cross-account access denied: the bucket policy allows the principal, "
            f"but the IAM identity policy for {principal} does not grant {action}. "
            "Both must allow in cross-account scenarios."
        )

    elif denial_source == "iam_policy_missing_allow":
        fixes.append({
            "policy_type": "iam_policy",
            "statement_to_add": {
                "Effect": "Allow",
                "Action": [action],
                "Resource": resource,
            },
            "note": "Add this statement to the IAM policy for the principal.",
        })
        explanation = f"IAM policy does not allow {action} on {resource}."

    elif denial_source == "bucket_policy_missing_allow":
        account_id = re.search(r':(\d{12}):', principal)
        account = account_id.group(1) if account_id else "ACCOUNT_ID"
        fixes.append({
            "policy_type": "bucket_policy",
            "statement_to_add": {
                "Effect": "Allow",
                "Principal": {"AWS": principal or f"arn:aws:iam::{account}:root"},
                "Action": [action],
                "Resource": [resource, resource.rstrip("/") + "/*"]
                if not resource.endswith("*") else [resource],
            },
            "note": "Add this statement to the bucket policy.",
        })
        explanation = f"Bucket policy does not allow {action} for principal {principal}."

    elif denial_source == "explicit_deny":
        fixes = []
        explanation = (
            "An explicit Deny statement is blocking access. "
            "Explicit denies override all allows and cannot be overridden by adding more allows. "
            "You must remove or scope the Deny statement. "
            "Manual review required."
        )

    else:
        explanation = f"Denial source: {denial_source}. Manual review required."

    return {
        "ok": True,
        "denial_source": denial_source,
        "analysis_summary": analysis.get("summary", ""),
        "explanation": explanation,
        "fixes": fixes,
        "usage": (
            "# manual-only: review suggested fix statements above before applying.\n"
            "# Apply IAM fixes via: aws iam put-user-policy / put-role-policy\n"
            "# Apply bucket policy fixes via: aws s3api put-bucket-policy"
        ),
    }
