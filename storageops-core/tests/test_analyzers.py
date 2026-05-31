"""Unit tests for storageops-core analyzers."""
from __future__ import annotations

import pytest


# ── analyze_policy ────────────────────────────────────────────────────

class TestAnalyzePolicy:
    def test_cross_account_missing_iam(self):
        from analyze_policy import analyze
        result = analyze({
            "principal": "arn:aws:iam::111111111111:user/alice",
            "action": "s3:GetObject",
            "resource": "arn:aws:s3:::shared-data/report.pdf",
            "iam_policy": {
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Action": ["s3:ListAllMyBuckets"], "Resource": "*"}],
            },
            "bucket_policy": {
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"AWS": "arn:aws:iam::111111111111:root"},
                    "Action": ["s3:GetObject"],
                    "Resource": ["arn:aws:s3:::shared-data/*"],
                }],
            },
        })
        assert result["denial_source"] == "cross_account_missing_iam_allow"
        assert result["cross_account"]

    def test_explicit_deny_wins(self):
        from analyze_policy import analyze
        result = analyze({
            "principal": "arn:aws:iam::123456789012:user/bob",
            "action": "s3:GetObject",
            "resource": "arn:aws:s3:::my-bucket/key",
            "iam_policy": {
                "Version": "2012-10-17",
                "Statement": [
                    {"Effect": "Allow", "Action": ["s3:*"], "Resource": "*"},
                    {"Effect": "Deny", "Action": ["s3:GetObject"],
                     "Resource": "arn:aws:s3:::my-bucket/*"},
                ],
            },
        })
        assert "deny" in result["denial_source"].lower()

    def test_wildcard_action_allows(self):
        from analyze_policy import analyze
        result = analyze({
            "principal": "arn:aws:iam::123456789012:user/alice",
            "action": "s3:GetObject",
            "resource": "arn:aws:s3:::my-bucket/file.txt",
            "iam_policy": {
                "Version": "2012-10-17",
                "Statement": [{"Effect": "Allow", "Action": ["s3:Get*"], "Resource": "*"}],
            },
        })
        assert result["iam_evaluation"]["has_allow"]
        assert result["denial_source"] != "iam_policy_missing_allow"

    def test_inline_403_text(self):
        from analyze_policy import analyze_inline_403
        result = analyze_inline_403(
            "AccessDenied: User arn:aws:iam::123456789012:user/alice is not authorized "
            "to perform: s3:GetObject on resource: arn:aws:s3:::my-bucket/key"
        )
        assert isinstance(result, dict)
        assert result.get("denial_source")


# ── analyze_cost ──────────────────────────────────────────────────────

class TestAnalyzeCost:
    def test_small_file_ia_penalty(self):
        from analyze_cost import analyze
        result = analyze({
            "storage_price_per_gb": {"STANDARD": 0.023, "STANDARD_IA": 0.0125},
            "prefixes": [{
                "prefix": "logs/",
                "storage_class": "STANDARD_IA",
                "object_count": 8_000_000,
                "total_size_bytes": 8_000_000_000,
                "avg_object_age_days": 45,
            }],
        })
        assert result["issue_count"] >= 1
        assert result["prefix_analysis"][0]["has_min_size_penalty"]
        assert result["totals"]["penalty_percent"] > 50

    def test_no_false_positive_when_age_missing(self):
        from analyze_cost import analyze
        result = analyze({
            "storage_price_per_gb": {"STANDARD_IA": 0.0125},
            "prefixes": [{
                "prefix": "data/",
                "storage_class": "STANDARD_IA",
                "object_count": 100,
                "total_size_bytes": 10 * 1024 * 1024 * 1024,
            }],
        })
        duration_issues = [i for i in result["issues"] if i["type"] == "minimum_duration_at_risk"]
        assert len(duration_issues) == 0

    def test_standard_storage_no_penalty(self):
        from analyze_cost import analyze
        result = analyze({
            "storage_price_per_gb": {"STANDARD": 0.023},
            "prefixes": [{
                "prefix": "data/",
                "storage_class": "STANDARD",
                "object_count": 1000,
                "total_size_bytes": 1024 * 1024 * 1024,
            }],
        })
        assert result["prefix_analysis"][0]["has_min_size_penalty"] is False


# ── detect_throttling ─────────────────────────────────────────────────

class TestDetectThrottling:
    def test_detects_slowdown_errors(self):
        from detect_throttling import detect
        result = detect({
            "status_codes": {},
            "errors": ["SlowDown: Please reduce your request rate"] * 5,
            "total_operations": 100,
        })
        assert result["total_throttle_count"] == 5

    def test_detects_429_status(self):
        from detect_throttling import detect
        result = detect({
            "status_codes": {"429": 10, "200": 990},
            "errors": [],
            "total_operations": 1000,
        })
        assert result["throttle_rate_percent"] == pytest.approx(1.0)

    def test_no_throttling(self):
        from detect_throttling import detect
        result = detect({
            "status_codes": {"200": 1000},
            "errors": [],
            "total_operations": 1000,
        })
        assert result["total_throttle_count"] == 0
        assert result["severity"] == "none"

    def test_no_double_count(self):
        from detect_throttling import detect
        result = detect({
            "status_codes": {},
            "errors": ["SlowDown: reduce rate"] * 3,
            "total_operations": 50,
        })
        assert result["total_throttle_count"] == 3, "SlowDown errors must not be double-counted"


# ── analyze_throughput ────────────────────────────────────────────────

class TestAnalyzeThroughput:
    def test_latency_bound(self):
        from analyze_throughput import analyze
        result = analyze({"object_size_mb": 1000, "rtt_ms": 200, "bandwidth_mbps": 10000})
        assert isinstance(result, dict)
        assert result.get("theoretical") or result.get("theoretical_max_mbps") or result.get("layer_breakdown")

    def test_bandwidth_bound(self):
        from analyze_throughput import analyze
        result = analyze({"object_size_mb": 100, "rtt_ms": 1, "bandwidth_mbps": 10})
        assert isinstance(result, dict)

    def test_returns_recommendations(self):
        from analyze_throughput import analyze
        result = analyze({
            "object_size_mb": 500,
            "rtt_ms": 100,
            "bandwidth_mbps": 1000,
            "observed_throughput_mbps": 50,
        })
        assert result.get("recommendations") or result.get("recommendation") or result.get("layer_breakdown")


# ── analyze_metadata_amplification ───────────────────────────────────

class TestAnalyzeMetadataAmplification:
    def test_returns_dict(self):
        from analyze_metadata_amplification import analyze
        result = analyze({
            "rtt_ms": 50,
            "syscalls": {"stat": 10000, "open": 2000, "readdir": 200, "read": 5000},
            "operation_name": "git status",
        })
        assert isinstance(result, dict)
        assert "amplification_factor" in result or "total_rtt_ms" in result


# ── analyze_cors ──────────────────────────────────────────────────────

class TestAnalyzeCors:
    def test_returns_dict(self):
        from analyze_cors import analyze
        result = analyze({"cors_errors": [], "no_cors_config": False,
                          "preflight_failed": False, "missing_headers": [],
                          "summary": {"error_count": 0, "needs_cors_config": False}})
        assert isinstance(result, dict)

    def test_expected_keys_present(self):
        from analyze_cors import analyze
        result = analyze({
            "cors_errors": [{"type": "NoSuchCORSConfiguration", "origin": "https://example.com",
                             "method": "GET", "headers": []}],
            "no_cors_config": True,
            "preflight_failed": False,
            "missing_headers": [],
            "bucket": "my-bucket",
            "summary": {"error_count": 1, "needs_cors_config": True},
        })
        assert "issues" in result
        assert "recommended_cors_xml" in result
        assert "explanation" in result
        assert "usage" in result

    def test_generates_cors_xml(self):
        from analyze_cors import analyze
        result = analyze({
            "cors_errors": [{"type": "NoSuchCORSConfiguration", "origin": "https://app.example.com",
                             "method": "PUT", "headers": ["content-type"]}],
            "no_cors_config": True,
            "preflight_failed": False,
            "missing_headers": [],
            "bucket": "my-bucket",
            "summary": {"error_count": 1, "needs_cors_config": True},
        })
        xml = result["recommended_cors_xml"]
        assert "<CORSConfiguration" in xml
        assert "<AllowedOrigin>" in xml
        assert "<AllowedMethod>" in xml

    def test_usage_contains_manual_only(self):
        from analyze_cors import analyze
        result = analyze({
            "cors_errors": [],
            "no_cors_config": True,
            "preflight_failed": False,
            "missing_headers": [],
            "summary": {"error_count": 0, "needs_cors_config": True},
        })
        assert "manual-only" in result["usage"].lower()

    def test_issues_populated_for_no_cors_config(self):
        from analyze_cors import analyze
        result = analyze({
            "cors_errors": [{"type": "NoSuchCORSConfiguration", "origin": "", "method": "", "headers": []}],
            "no_cors_config": True,
            "preflight_failed": False,
            "missing_headers": [],
            "summary": {"error_count": 1, "needs_cors_config": True},
        })
        assert len(result["issues"]) >= 1

    def test_preflight_adds_options_method(self):
        from analyze_cors import analyze
        result = analyze({
            "cors_errors": [{"type": "preflight_failed", "origin": "https://app.io",
                             "method": "DELETE", "headers": []}],
            "no_cors_config": False,
            "preflight_failed": True,
            "missing_headers": [],
            "summary": {"error_count": 1, "needs_cors_config": True},
        })
        xml = result["recommended_cors_xml"]
        assert "OPTIONS" in xml


# ── analyze_replication ───────────────────────────────────────────────

class TestAnalyzeReplication:
    def test_returns_dict(self):
        from analyze_replication import analyze
        result = analyze({
            "objects": [], "rules": [],
            "status_counts": {"FAILED": 0, "PENDING": 0, "COMPLETED": 0},
            "has_failures": False, "failure_reasons": [],
            "summary": {"total_objects": 0, "failure_rate_pct": 0.0},
        })
        assert isinstance(result, dict)

    def test_expected_keys_present(self):
        from analyze_replication import analyze
        result = analyze({
            "objects": [{"key": "data/obj.parquet", "status": "FAILED", "rule_id": "rule1"}],
            "rules": [],
            "status_counts": {"FAILED": 1, "PENDING": 0, "COMPLETED": 0},
            "has_failures": True,
            "failure_reasons": [],
            "summary": {"total_objects": 1, "failure_rate_pct": 100.0},
        })
        assert "likely_cause" in result
        assert "diagnosis" in result
        assert "recommendations" in result
        assert "verification_commands" in result

    def test_iam_cause_detected_on_failures(self):
        from analyze_replication import analyze
        result = analyze({
            "objects": [{"key": "k", "status": "FAILED", "rule_id": "r1"}],
            "rules": [],
            "status_counts": {"FAILED": 5, "PENDING": 0, "COMPLETED": 0},
            "has_failures": True,
            "failure_reasons": ["Access Denied: not authorized"],
            "summary": {"total_objects": 5, "failure_rate_pct": 100.0},
        })
        assert result["likely_cause"] == "iam_permission"

    def test_kms_cause_detected(self):
        from analyze_replication import analyze
        result = analyze({
            "objects": [],
            "rules": [],
            "status_counts": {"FAILED": 3, "PENDING": 0, "COMPLETED": 0},
            "has_failures": True,
            "failure_reasons": ["kms:Decrypt not authorized"],
            "summary": {"total_objects": 3, "failure_rate_pct": 100.0},
        })
        assert result["likely_cause"] == "kms"

    def test_no_failure_returns_none_cause(self):
        from analyze_replication import analyze
        result = analyze({
            "objects": [],
            "rules": [],
            "status_counts": {"FAILED": 0, "PENDING": 0, "COMPLETED": 10},
            "has_failures": False,
            "failure_reasons": [],
            "summary": {"total_objects": 10, "failure_rate_pct": 0.0},
        })
        assert result["likely_cause"] == "none"

    def test_verification_commands_are_manual_only(self):
        from analyze_replication import analyze
        result = analyze({
            "objects": [{"key": "k", "status": "FAILED", "rule_id": "r1"}],
            "rules": [],
            "status_counts": {"FAILED": 1, "PENDING": 0, "COMPLETED": 0},
            "has_failures": True,
            "failure_reasons": [],
            "summary": {"total_objects": 1, "failure_rate_pct": 100.0},
        })
        for cmd in result["verification_commands"]:
            assert "manual-only" in cmd.lower(), f"Command must be labeled manual-only: {cmd}"
