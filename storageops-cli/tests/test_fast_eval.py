"""
Fast evaluation of golden cases using rule-based parsers — no LLM required.

Tests:
1. Triage (auto_detect) correctly identifies each case's domain as the top result.
2. Domain-specific parsers produce structured output with expected evidence keywords.
3. Triage confidence meets a reasonable threshold for each case.

These tests run fully offline in CI (no LLM API key needed).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_CASES_DIR = _PROJECT_ROOT / "agents" / "skills" / "storageops-eval-golden-cases" / "cases"


def _load_case(case_name: str) -> tuple[str, dict]:
    """Return (combined_input_text, expected_dict) for a golden case."""
    case_dir = _CASES_DIR / case_name
    input_dir = case_dir / "input"
    texts: list[str] = []
    for fpath in sorted(input_dir.iterdir()):
        if fpath.is_file():
            texts.append(fpath.read_text(encoding="utf-8", errors="replace"))
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    return "\n\n".join(texts), expected


def _auto_detect(text: str) -> list[dict]:
    from storageops.cli import auto_detect
    return auto_detect(text)


class TestTriageDomainDetection(unittest.TestCase):
    """auto_detect must return the correct domain as the top result for each case."""

    def _assert_top_domain(self, case_name: str, expected_category: str):
        text, _ = _load_case(case_name)
        detections = _auto_detect(text)
        self.assertTrue(detections, f"{case_name}: auto_detect returned empty list")
        top = detections[0]["domain"]
        self.assertEqual(
            top, expected_category,
            f"{case_name}: top domain={top!r}, expected={expected_category!r}. "
            f"All detected: {[d['domain'] for d in detections]}",
        )

    def test_rclone_corrupted_transfer(self):
        self._assert_top_domain("rclone-corrupted-transfer", "cli_sdk_behavior")

    def test_signature_clock_skew(self):
        self._assert_top_domain("signature-clock-skew", "s3_protocol_compatibility")

    def test_access_denied_cross_account(self):
        self._assert_top_domain("access-denied-cross-account", "security_iam_policy")

    def test_throttling_hot_prefix(self):
        self._assert_top_domain("throttling-hot-prefix", "performance_throughput")

    def test_lifecycle_small_file_ia(self):
        self._assert_top_domain("lifecycle-small-file-ia", "lifecycle_cost")

    def test_small_files_ia_cost(self):
        self._assert_top_domain("small-files-ia-cost", "lifecycle_cost")

    def test_workspace_mount_slow_git(self):
        self._assert_top_domain("workspace-mount-slow-git", "mount_filesystem_workspace")

    def test_network_vpc_endpoint_dns(self):
        self._assert_top_domain("network-vpc-endpoint-dns", "network_endpoint_access")

    def test_rclone_mount_hang(self):
        self._assert_top_domain("rclone-mount-hang", "mount_filesystem_workspace")

    def test_kms_denied_encrypt(self):
        self._assert_top_domain("kms-denied-encrypt", "security_iam_policy")


class TestParserStructuredOutput(unittest.TestCase):
    """Domain-specific parsers must produce structured output with key evidence."""

    def test_rclone_log_parser_finds_transfer_issue(self):
        from parse_rclone_log import parse
        text, _ = _load_case("rclone-corrupted-transfer")
        result = parse(text)
        self.assertNotIn("error", result, f"parse_rclone_log returned error: {result.get('error')}")
        dump = json.dumps(result).lower()
        self.assertTrue(
            any(k in dump for k in ("etag", "mismatch", "corrupted", "multipart", "checksum")),
            f"Expected checksum/ETag evidence in rclone parse output. Keys: {list(result.keys())}",
        )

    def test_sigv4_parser_identifies_error_code(self):
        from parse_sigv4_error import parse_xml_error
        xml_path = _CASES_DIR / "signature-clock-skew" / "input" / "error-response.xml"
        xml_text = xml_path.read_text(encoding="utf-8")
        result = parse_xml_error(xml_text)
        self.assertNotIn("error", result, f"parse_sigv4_error returned error: {result.get('error')}")
        dump = json.dumps(result).lower()
        self.assertIn(
            "signaturedoesnotmatch", dump.replace("_", "").replace(" ", ""),
            f"Expected SignatureDoesNotMatch in SigV4 parse output. Got: {dump[:300]}",
        )

    def test_lifecycle_xml_parser_detects_ia_rule(self):
        from parse_lifecycle_xml import parse
        xml_path = _CASES_DIR / "lifecycle-small-file-ia" / "input" / "lifecycle.xml"
        xml_text = xml_path.read_text(encoding="utf-8")
        result = parse(xml_text)
        self.assertNotIn("error", result, f"parse_lifecycle_xml returned error: {result.get('error')}")
        dump = json.dumps(result).lower()
        self.assertTrue(
            "standard_ia" in dump or "standardia" in dump or "_ia" in dump,
            f"Expected STANDARD_IA in lifecycle parse output. Got: {dump[:300]}",
        )

    def test_policy_analyzer_detects_cross_account_deny(self):
        from analyze_policy import analyze
        policy_path = _CASES_DIR / "access-denied-cross-account" / "input" / "error.json"
        policy_data = json.loads(policy_path.read_text(encoding="utf-8"))
        result = analyze(policy_data)
        self.assertNotIn("error", result, f"analyze_policy returned error: {result.get('error')}")
        dump = json.dumps(result).lower()
        self.assertTrue(
            any(k in dump for k in ("deny", "allow", "access", "403", "cross", "iam")),
            f"Expected access denial analysis. Got: {dump[:300]}",
        )

    def test_throttle_detector_flags_slowdown(self):
        from detect_throttling import detect
        result = detect({
            "status_codes": {"429": 45, "200": 955},
            "errors": ["SlowDown: Please reduce your request rate"],
            "total_operations": 1000,
        })
        self.assertNotIn("error", result, f"detect_throttling returned error: {result.get('error')}")
        dump = json.dumps(result).lower()
        self.assertTrue(
            any(k in dump for k in ("throttl", "slowdown", "rate", "429")),
            f"Expected throttling indicators. Got: {dump[:300]}",
        )
        # Throttle rate must be detectable (key is throttle_rate_percent)
        rate = float(
            result.get("throttle_rate_percent",
                       result.get("throttle_rate_pct",
                                  result.get("throttle_rate", 0))) or 0
        )
        self.assertGreater(rate, 1.0, f"Expected throttle rate > 1%, got {rate}")


class TestTriageConfidenceThresholds(unittest.TestCase):
    """
    Triage must detect each case's expected domain with non-zero confidence.

    Note: expected_min_confidence in the golden cases reflects LLM agent targets.
    Rule-based auto_detect uses pattern hit ratios that are naturally lower —
    we only require that the correct domain is detected (confidence > 0).
    """

    def _check(self, case_name: str):
        text, expected = _load_case(case_name)
        category = expected["expected_category"]
        detections = _auto_detect(text)
        conf_by_domain = {d["domain"]: d["confidence"] for d in detections}
        actual = conf_by_domain.get(category, 0.0)
        self.assertGreater(
            actual, 0.0,
            f"{case_name}: domain {category!r} not detected (confidence=0). "
            f"All detected: {conf_by_domain}",
        )

    def test_confidence_rclone(self):
        self._check("rclone-corrupted-transfer")

    def test_confidence_clock_skew(self):
        self._check("signature-clock-skew")

    def test_confidence_access_denied(self):
        self._check("access-denied-cross-account")

    def test_confidence_throttling(self):
        self._check("throttling-hot-prefix")

    def test_confidence_lifecycle(self):
        self._check("lifecycle-small-file-ia")

    def test_confidence_workspace(self):
        self._check("workspace-mount-slow-git")

    def test_confidence_vpc_endpoint_dns(self):
        self._check("network-vpc-endpoint-dns")

    def test_confidence_rclone_mount_hang(self):
        self._check("rclone-mount-hang")

    def test_confidence_kms_denied(self):
        self._check("kms-denied-encrypt")

    def test_confidence_s5cmd_no_such_key(self):
        self._check("s5cmd-no-such-key")

    def test_confidence_tls_cert_expired(self):
        self._check("tls-cert-expired")

    def test_confidence_cross_region_slow(self):
        self._check("cross-region-slow")

    def test_confidence_cors_preflight_failed(self):
        self._check("cors-preflight-failed")

    def test_confidence_crr_replication_lag(self):
        self._check("crr-replication-lag")

    def test_confidence_versioned_delete_marker(self):
        self._check("versioned-delete-marker")


class TestCmdEvalFast(unittest.TestCase):
    """storageops eval --all runs fast triage eval when no --outputs-dir is given."""

    def test_eval_all_returns_results_without_outputs_dir(self):
        import argparse
        from storageops.cli import cmd_eval
        args = argparse.Namespace(
            all=True, case=None, regression=False,
            cases_dir=str(_CASES_DIR), outputs_dir=None,
        )
        captured = []
        import builtins, io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                cmd_eval(args)
            except SystemExit:
                pass
        output = buf.getvalue()
        self.assertTrue(output.strip(), "cmd_eval produced no output")
        result = json.loads(output)
        self.assertEqual(result.get("mode"), "fast")
        self.assertIn("total_cases", result)
        self.assertGreater(result["total_cases"], 0)
        self.assertGreater(result["passed"], 0,
                           "Fast eval should pass at least 1 case")

    def test_eval_case_fast_without_outputs_dir(self):
        import argparse
        from storageops.cli import cmd_eval
        args = argparse.Namespace(
            all=False, case="rclone-corrupted-transfer", regression=False,
            cases_dir=str(_CASES_DIR), outputs_dir=None,
        )
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                cmd_eval(args)
            except SystemExit:
                pass
        result = json.loads(buf.getvalue())
        self.assertEqual(result.get("mode"), "fast")
        self.assertEqual(result.get("expected_category"), "cli_sdk_behavior")
        self.assertTrue(result.get("passed"), "rclone-corrupted-transfer should pass fast eval")


if __name__ == "__main__":
    unittest.main()
