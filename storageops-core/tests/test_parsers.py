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
