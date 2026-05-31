"""Unit tests for storageops-core utilities: secret_scanner and signatures."""
from __future__ import annotations


# ── secret_scanner ────────────────────────────────────────────────────

class TestSecretScanner:
    def test_detects_akia_key(self):
        from secret_scanner import scan
        result = scan("aws_access_key_id = AKIAIOSFODNN7EXAMPLE")
        assert result["count"] >= 1
        assert "AKIA" in str(result["findings"])

    def test_redacts_akia_in_text(self):
        from secret_scanner import scan
        result = scan("key=AKIAIOSFODNN7EXAMPLE something else")
        assert "AKIAIOSFODNN7EXAMPLE" not in result["redacted_text"]
        assert "[REDACTED]" in result["redacted_text"]

    def test_safe_placeholders_not_flagged(self):
        from secret_scanner import scan
        result = scan("aws_access_key_id = YOUR_ACCESS_KEY\naws_secret = YOUR_SECRET")
        assert result["count"] == 0

    def test_empty_input(self):
        from secret_scanner import scan
        result = scan("")
        assert result["count"] == 0
        assert result["redacted_text"] == ""

    def test_returns_required_fields(self):
        from secret_scanner import scan
        result = scan("no secrets here")
        assert "count" in result
        assert "findings" in result
        assert "redacted_text" in result

    def test_detects_authorization_header(self):
        from secret_scanner import scan
        result = scan("Authorization: AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20240101")
        assert result["count"] >= 1

    def test_asian_cloud_key(self):
        from secret_scanner import scan
        result = scan("LTAI4GxxxxxxxxxxxxxxxxxxxxxxL")
        # Alibaba Cloud key: LTAI followed by alphanumeric
        assert isinstance(result, dict)  # At minimum must not crash


# ── signatures / auto_detect ─────────────────────────────────────────

class TestAutoDetect:
    def test_returns_list(self):
        from signatures import auto_detect
        result = auto_detect("some text")
        assert isinstance(result, list)

    def test_sigv4_detection(self):
        from signatures import auto_detect
        result = auto_detect("SignatureDoesNotMatch error from S3 endpoint AWS4-HMAC-SHA256")
        assert len(result) > 0
        assert result[0]["domain"] == "s3_protocol_compatibility"

    def test_rclone_detection(self):
        from signatures import auto_detect
        result = auto_detect("rclone v1.65.0 ERROR corrupted on transfer ETag mismatch")
        assert len(result) > 0
        assert result[0]["domain"] == "cli_sdk_behavior"

    def test_throttling_detection(self):
        from signatures import auto_detect
        result = auto_detect("SlowDown: Please reduce your request rate. HTTP 429 RequestRateLimitExceeded")
        domains = [d["domain"] for d in result]
        assert "performance_throughput" in domains

    def test_access_denied_detection(self):
        from signatures import auto_detect
        result = auto_detect("AccessDenied: User is not authorized to perform s3:GetObject")
        domains = [d["domain"] for d in result]
        assert "security_iam_policy" in domains

    def test_confidence_is_float_between_0_and_1(self):
        from signatures import auto_detect
        result = auto_detect("SignatureDoesNotMatch AWS S3 error")
        for d in result:
            assert 0.0 <= d["confidence"] <= 1.0

    def test_empty_input_returns_empty(self):
        from signatures import auto_detect
        result = auto_detect("")
        assert result == []

    def test_results_sorted_by_confidence_descending(self):
        from signatures import auto_detect
        result = auto_detect("SignatureDoesNotMatch AccessDenied rclone corrupted transfer")
        if len(result) >= 2:
            for i in range(len(result) - 1):
                assert result[i]["confidence"] >= result[i + 1]["confidence"]

    def test_signatures_dict_structure(self):
        from signatures import SIGNATURES
        assert isinstance(SIGNATURES, dict)
        for domain, patterns in SIGNATURES.items():
            assert isinstance(patterns, list)
            for pattern, label in patterns:
                assert isinstance(pattern, str)
                assert isinstance(label, str)
