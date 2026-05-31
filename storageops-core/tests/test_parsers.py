"""Unit tests for storageops-core parsers."""
from __future__ import annotations

import pytest
from pathlib import Path

_CASES = Path(__file__).parent.parent.parent / "agents" / "skills" / "storageops-eval-golden-cases" / "cases"


# ── parse_rclone_log ──────────────────────────────────────────────────

class TestParseRcloneLog:
    def test_returns_dict(self):
        from parse_rclone_log import parse
        result = parse("rclone v1.65.0")
        assert isinstance(result, dict)

    def test_corrupted_transfer_golden_case(self):
        from parse_rclone_log import parse
        log = (_CASES / "rclone-corrupted-transfer" / "input" / "rclone-debug.log").read_text()
        result = parse(log)
        assert result.get("version") == "1.65.0"
        assert len(result["corrupted"]) >= 1
        assert result["summary"]["etag_format_mismatch_detected"]
        assert result["summary"]["root_cause_likely"] == "multipart_etag_format_mismatch"

    def test_empty_input(self):
        from parse_rclone_log import parse
        result = parse("")
        assert isinstance(result, dict)
        assert "corrupted" in result


# ── parse_sigv4_error ─────────────────────────────────────────────────

class TestParseSigV4Error:
    def test_returns_dict(self):
        from parse_sigv4_error import parse_xml_error
        result = parse_xml_error("<Error><Code>SignatureDoesNotMatch</Code></Error>")
        assert isinstance(result, dict)
        assert result["code"] == "SignatureDoesNotMatch"

    def test_golden_case_xml(self):
        from parse_sigv4_error import parse_xml_error
        xml = (_CASES / "signature-clock-skew" / "input" / "error-response.xml").read_text()
        result = parse_xml_error(xml)
        assert result["code"] == "SignatureDoesNotMatch"
        assert result.get("string_to_sign") or result.get("canonical_request")

    def test_clock_skew_detection(self):
        from parse_sigv4_error import parse_xml_error, diagnose
        xml = (_CASES / "signature-clock-skew" / "input" / "error-response.xml").read_text()
        parsed = parse_xml_error(xml)
        result = diagnose(parsed)
        assert isinstance(result, dict)
        assert "likely_root_cause" in result or "hypotheses" in result


# ── parse_awscli_debug ────────────────────────────────────────────────

class TestParseAwscliDebug:
    def test_returns_dict(self):
        from parse_awscli_debug import parse
        result = parse("DEBUG botocore.endpoint")
        assert isinstance(result, dict)

    def test_signature_error_in_golden_case(self):
        from parse_awscli_debug import parse
        log = (_CASES / "signature-clock-skew" / "input" / "awscli-debug.log").read_text()
        result = parse(log)
        assert result.get("summary", {}).get("has_signature_error")
        assert result.get("operations")

    def test_empty_input(self):
        from parse_awscli_debug import parse
        result = parse("")
        assert isinstance(result, dict)


# ── parse_lifecycle_xml ───────────────────────────────────────────────

class TestParseLifecycleXml:
    def test_returns_dict(self):
        from parse_lifecycle_xml import parse
        result = parse("<LifecycleConfiguration/>")
        assert isinstance(result, dict)

    def test_small_file_ia_golden_case(self):
        from parse_lifecycle_xml import parse
        xml = (_CASES / "lifecycle-small-file-ia" / "input").iterdir()
        text = next(f for f in xml if f.suffix == ".xml").read_text()
        result = parse(text)
        assert result.get("rules")
        warnings = result.get("warnings", [])
        assert any("128" in w or "size" in w.lower() or "STANDARD_IA" in w
                   for w in warnings), f"Expected size warning, got: {warnings}"

    def test_overlap_detection(self):
        from parse_lifecycle_xml import parse
        xml = """<LifecycleConfiguration>
          <Rule><ID>a</ID><Status>Enabled</Status>
            <Filter><Prefix>logs/</Prefix></Filter>
            <Expiration><Days>365</Days></Expiration></Rule>
          <Rule><ID>b</ID><Status>Enabled</Status>
            <Filter><Prefix>logs/2024/</Prefix></Filter>
            <Transition><Days>30</Days><StorageClass>STANDARD_IA</StorageClass></Transition></Rule>
        </LifecycleConfiguration>"""
        result = parse(xml)
        assert result["summary"]["overlapping_prefixes"]


# ── parse_s5cmd_error ─────────────────────────────────────────────────

class TestParseS5cmdError:
    def test_returns_dict(self):
        from parse_s5cmd_error import parse
        result = parse('ERROR "cp file s3://b/k": AccessDenied: Access Denied')
        assert isinstance(result, dict)

    def test_golden_case(self):
        from parse_s5cmd_error import parse
        log = (_CASES / "s5cmd-no-such-key" / "input").iterdir()
        text = next(f for f in log if f.is_file()).read_text()
        result = parse(text)
        assert isinstance(result, dict)
        assert result.get("errors") or result.get("summary")


# ── parse_s5cmd_log ───────────────────────────────────────────────────

class TestParseS5cmdLog:
    def test_returns_dict(self):
        from parse_s5cmd_log import parse
        result = parse("s5cmd cp s3://bucket/key local 200 OK")
        assert isinstance(result, dict)

    def test_empty_input(self):
        from parse_s5cmd_log import parse
        result = parse("")
        assert isinstance(result, dict)

    def test_error_extraction(self):
        from parse_s5cmd_log import parse
        log = 'ERROR "cp s3://b/k ./f": NoSuchKey: The specified key does not exist.'
        result = parse(log)
        assert isinstance(result, dict)


# ── parse_cors_error ──────────────────────────────────────────────────

class TestParseCorsError:
    def test_returns_dict(self):
        from parse_cors_error import parse
        result = parse("NoSuchCORSConfiguration")
        assert isinstance(result, dict)

    def test_no_cors_config_detected(self):
        from parse_cors_error import parse
        result = parse("<Code>NoSuchCORSConfiguration</Code>")
        assert "cors_errors" in result
        assert "no_cors_config" in result
        assert "preflight_failed" in result
        assert "missing_headers" in result
        assert "summary" in result
        assert result["no_cors_config"] is True
        assert result["summary"]["needs_cors_config"] is True

    def test_preflight_failure_detected(self):
        from parse_cors_error import parse
        result = parse("OPTIONS request returned 403 preflight failed")
        assert result["preflight_failed"] is True
        assert result["summary"]["error_count"] >= 1

    def test_cors_forbidden_detected(self):
        from parse_cors_error import parse
        result = parse("CORSForbidden: Origin not allowed")
        assert any(e["type"] == "CORSForbidden" for e in result["cors_errors"])

    def test_empty_input(self):
        from parse_cors_error import parse
        result = parse("")
        assert isinstance(result, dict)
        assert "cors_errors" in result
        assert result["summary"]["error_count"] == 0

    def test_origin_extracted(self):
        from parse_cors_error import parse
        result = parse("Origin: https://example.com\nCORSForbidden: not allowed")
        assert result["summary"]["error_count"] >= 1


# ── parse_replication_status ──────────────────────────────────────────

class TestParseReplicationStatus:
    def test_returns_dict(self):
        from parse_replication_status import parse
        result = parse("ReplicationStatus: FAILED")
        assert isinstance(result, dict)

    def test_expected_keys_present(self):
        from parse_replication_status import parse
        result = parse("ReplicationStatus: FAILED")
        assert "objects" in result
        assert "rules" in result
        assert "status_counts" in result
        assert "has_failures" in result
        assert "failure_reasons" in result
        assert "summary" in result

    def test_failed_status_detected(self):
        from parse_replication_status import parse
        text = '"Key": "data/obj.parquet"\n"ReplicationStatus": "FAILED"'
        result = parse(text)
        assert result["has_failures"] is True
        assert result["status_counts"]["FAILED"] >= 1

    def test_completed_status(self):
        from parse_replication_status import parse
        text = '"Key": "data/obj.parquet"\n"ReplicationStatus": "COMPLETED"'
        result = parse(text)
        assert result["status_counts"]["COMPLETED"] >= 1

    def test_empty_input(self):
        from parse_replication_status import parse
        result = parse("")
        assert isinstance(result, dict)
        assert result["summary"]["total_objects"] == 0


# ── parse_hadoop_s3a ──────────────────────────────────────────────────

class TestParseHadoopS3a:
    def test_returns_dict(self):
        from parse_hadoop_s3a import parse
        result = parse("S3AFileSystem: error")
        assert isinstance(result, dict)

    def test_expected_keys_present(self):
        from parse_hadoop_s3a import parse
        result = parse("S3AFileSystem: error")
        assert "errors" in result
        assert "committer_type" in result
        assert "has_rename_error" in result
        assert "has_credential_error" in result
        assert "spark_version" in result
        assert "hadoop_version" in result
        assert "affected_paths" in result
        assert "summary" in result

    def test_rename_failure_detected(self):
        from parse_hadoop_s3a import parse
        result = parse("HADOOP-13345 Cannot rename s3a://bucket/src to s3a://bucket/dst")
        assert result["has_rename_error"] is True
        assert result["summary"]["error_count"] >= 1

    def test_magic_committer_detected(self):
        from parse_hadoop_s3a import parse
        result = parse("spark.hadoop.fs.s3a.committer.name=magic MagicS3GuardCommitter")
        assert result["committer_type"] == "magic"

    def test_staging_committer_detected(self):
        from parse_hadoop_s3a import parse
        result = parse("Using StagingCommitter for output path s3a://bucket/output")
        assert result["committer_type"] == "staging"

    def test_credential_error_detected(self):
        from parse_hadoop_s3a import parse
        result = parse("ExpiredToken: The provided token has expired")
        assert result["has_credential_error"] is True

    def test_spark_version_extracted(self):
        from parse_hadoop_s3a import parse
        result = parse("Spark/3.4.1 S3AFileSystem error")
        assert result["spark_version"] == "3.4.1"

    def test_empty_input(self):
        from parse_hadoop_s3a import parse
        result = parse("")
        assert isinstance(result, dict)
        assert result["summary"]["error_count"] == 0
