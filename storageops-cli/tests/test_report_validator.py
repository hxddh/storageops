"""Tests for the report_validator module."""
from __future__ import annotations

import unittest
from storageops.report_validator import validate_report


def _report(extra: str = "") -> str:
    return f"""\
---
category: cli_sdk_behavior
root_cause_type: multipart_etag_mismatch
confidence: 0.85
severity: medium
---

## Summary

Transfer corruption caused by multipart ETag mismatch.
{extra}
## Key Evidence

rclone log shows corrupted on transfer.

## Remediation

Add --use-multipart-etag=false flag.
"""


class TestValidateReport(unittest.TestCase):

    def test_valid_report_passes(self):
        r = validate_report(_report())
        self.assertTrue(r["valid"])
        self.assertEqual(r["missing_fields"], [])
        self.assertEqual(r["invalid_fields"], {})

    def test_missing_frontmatter(self):
        r = validate_report("## Summary\n\nNo frontmatter here.")
        self.assertFalse(r["valid"])
        self.assertFalse(r["has_frontmatter"])
        self.assertIn("category", r["missing_fields"])

    def test_missing_required_field(self):
        text = "---\ncategory: cli_sdk_behavior\nconfidence: 0.8\nseverity: high\n---\n## Summary"
        r = validate_report(text)
        self.assertFalse(r["valid"])
        self.assertIn("root_cause_type", r["missing_fields"])

    def test_invalid_confidence_out_of_range(self):
        text = "---\ncategory: x\nroot_cause_type: y\nconfidence: 1.5\nseverity: high\n---\n"
        r = validate_report(text)
        self.assertFalse(r["valid"])
        self.assertIn("confidence", r["invalid_fields"])

    def test_invalid_confidence_not_float(self):
        text = "---\ncategory: x\nroot_cause_type: y\nconfidence: high\nseverity: high\n---\n"
        r = validate_report(text)
        self.assertFalse(r["valid"])
        self.assertIn("confidence", r["invalid_fields"])

    def test_invalid_severity(self):
        text = "---\ncategory: x\nroot_cause_type: y\nconfidence: 0.8\nseverity: extreme\n---\n"
        r = validate_report(text)
        self.assertFalse(r["valid"])
        self.assertIn("severity", r["invalid_fields"])

    def test_unknown_root_cause_warns(self):
        text = "---\ncategory: x\nroot_cause_type: unknown\nconfidence: 0.5\nseverity: low\n---\n"
        r = validate_report(text)
        self.assertTrue(r["valid"])   # not invalid, just a warning
        self.assertTrue(any("unknown" in w for w in r["warnings"]))

    def test_all_valid_severities(self):
        for sev in ("critical", "high", "medium", "low"):
            text = (
                f"---\ncategory: x\nroot_cause_type: y\n"
                f"confidence: 0.9\nseverity: {sev}\n---\n"
            )
            r = validate_report(text)
            self.assertNotIn("severity", r["invalid_fields"], f"severity={sev} should be valid")


if __name__ == "__main__":
    unittest.main()
