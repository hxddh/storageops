"""
Smoke test: run parsers against golden case input artifacts and verify
output structure and key findings.

Usage:
    python -m storageops-core.tests.smoke_test
"""
import sys
from pathlib import Path

# Add all sub-packages to path (using 'storageops-core' hyphenated dir name)
CORE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CORE_DIR / 'utils'))
sys.path.insert(0, str(CORE_DIR / 'parsers'))
sys.path.insert(0, str(CORE_DIR / 'analyzers'))

from secret_scanner import scan as scan_secrets  # noqa: E402
from parse_rclone_log import parse as parse_rclone  # noqa: E402
from parse_sigv4_error import parse_xml_error  # noqa: E402
from parse_awscli_debug import parse as parse_awscli  # noqa: E402
from analyze_policy import analyze as analyze_policy  # noqa: E402
from analyze_cost import analyze as analyze_cost  # noqa: E402

STORAGEOPS_ROOT = Path(__file__).parent.parent.parent
CASES_DIR = STORAGEOPS_ROOT / 'agents' / 'skills' / 'storageops-eval-golden-cases' / 'cases'

results = []


def _run(name, fn):
    try:
        fn()
        results.append({"test": name, "passed": True})
        print(f"  ✓ {name}")
    except Exception as e:
        results.append({"test": name, "passed": False, "error": str(e)})
        print(f"  ✗ {name}: {e}")


# ── Test: Secret Scanner ───────────────────────────────────────────────

def test_secret_scanner():
    """Secret scanner should detect AWS AKIA patterns."""
    text = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
    result = scan_secrets(text)
    assert result['count'] >= 1, f"Expected 1+ findings, got {result['count']}"
    assert 'AKIA' in str(result['findings']), "Should detect AKIA pattern"


# ── Test: Secret Scanner Safe Placeholders ─────────────────────────────

def test_secret_scanner_safe():
    """Secret scanner should NOT flag safe placeholders."""
    text = "aws_access_key_id = YOUR_ACCESS_KEY\naws_secret_access_key = YOUR_SECRET_KEY"
    result = scan_secrets(text)
    assert result['count'] == 0, f"Expected 0 findings for placeholders, got {result['count']}"


# ── Test: rclone Log Parser ────────────────────────────────────────────

def test_rclone_parser():
    """Parse rclone corrupted-on-transfer golden case."""
    rclone_log = CASES_DIR / 'rclone-corrupted-transfer' / 'input' / 'rclone-debug.log'
    text = rclone_log.read_text(encoding='utf-8', errors='replace')
    result = parse_rclone(text)

    assert result.get('version') == '1.65.0', f"Version: {result.get('version')}"
    assert len(result['corrupted']) >= 1, "Should detect corrupted transfer"
    assert result['summary']['etag_format_mismatch_detected'], "Should detect ETag format mismatch"
    assert result['summary']['root_cause_likely'] == 'multipart_etag_format_mismatch'


# ── Test: SigV4 Error Parser ───────────────────────────────────────────

def test_sigv4_parser():
    """Parse SignatureDoesNotMatch error XML."""
    error_path = CASES_DIR / 'signature-clock-skew' / 'input' / 'error-response.xml'
    text = error_path.read_text(encoding='utf-8', errors='replace')
    error = parse_xml_error(text)

    assert error['code'] == 'SignatureDoesNotMatch'
    assert 'AWS4-HMAC-SHA256' in error['string_to_sign']
    assert 'CanonicalRequest' in error or error['canonical_request']


# ── Test: Policy Analyzer ──────────────────────────────────────────────

def test_policy_analyzer():
    """Analyze cross-account missing IAM allow."""
    data = {
        "principal": "arn:aws:iam::111111111111:user/alice",
        "action": "s3:GetObject",
        "resource": "arn:aws:s3:::shared-data/report.pdf",
        "iam_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:ListAllMyBuckets"],
                    "Resource": "*",
                }
            ]
        },
        "bucket_policy": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "arn:aws:iam::111111111111:root"},
                    "Action": ["s3:GetObject"],
                    "Resource": ["arn:aws:s3:::shared-data/*"],
                }
            ]
        },
    }
    result = analyze_policy(data)

    assert result['denial_source'] == 'cross_account_missing_iam_allow', \
        f"Expected cross_account_missing_iam_allow, got {result['denial_source']}"
    assert result['cross_account'], "Should detect cross-account"


# ── Test: Cost Analyzer ────────────────────────────────────────────────

def test_cost_analyzer():
    """Analyze small files in Standard-IA cost amplification."""
    data = {
        "storage_price_per_gb": {"STANDARD": 0.023, "STANDARD_IA": 0.0125},
        "prefixes": [
            {
                "prefix": "logs/",
                "storage_class": "STANDARD_IA",
                "object_count": 8000000,
                "total_size_bytes": 8_000_000_000,
                "avg_object_age_days": 45,
            }
        ],
    }
    result = analyze_cost(data)

    assert result['issue_count'] >= 1, f"Expected issues, got {result['issue_count']}"
    assert result['prefix_analysis'][0]['has_min_size_penalty'], "Should detect min size penalty"
    assert result['totals']['penalty_percent'] > 50, \
        f"Penalty should be significant, got {result['totals']['penalty_percent']}%"


# ── Test: awscli Debug Parser ─────────────────────────────────────────

def test_awscli_parser():
    """Parse awscli debug log with SignatureDoesNotMatch."""
    debug_path = CASES_DIR / 'signature-clock-skew' / 'input' / 'awscli-debug.log'
    text = debug_path.read_text(encoding='utf-8', errors='replace')
    result = parse_awscli(text)

    assert result.get('summary', {}).get('has_signature_error'), "Should detect SignatureDoesNotMatch"
    assert result.get('operations'), "Should extract operations"


# ── Regression tests for verified bugs ────────────────────────────────

def test_throttling_no_double_count():
    """SlowDown errors must not be counted twice (SO-002)."""
    from detect_throttling import detect
    data = {
        "status_codes": {},
        "errors": ["SlowDown: Please reduce your request rate"] * 5,
        "total_operations": 100,
    }
    result = detect(data)
    assert result["total_throttle_count"] == 5, (
        f"Expected 5, got {result['total_throttle_count']} — double-count bug"
    )


def test_lifecycle_hierarchical_overlap():
    """Hierarchical prefix overlap must be detected (SO-004)."""
    from parse_lifecycle_xml import parse
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<LifecycleConfiguration>
  <Rule>
    <ID>logs-all</ID>
    <Status>Enabled</Status>
    <Filter><Prefix>logs/</Prefix></Filter>
    <Expiration><Days>365</Days></Expiration>
  </Rule>
  <Rule>
    <ID>logs-2024</ID>
    <Status>Enabled</Status>
    <Filter><Prefix>logs/2024/</Prefix></Filter>
    <Transition><Days>30</Days><StorageClass>STANDARD_IA</StorageClass></Transition>
  </Rule>
</LifecycleConfiguration>"""
    result = parse(xml)
    assert result["summary"]["overlapping_prefixes"], (
        "logs/ and logs/2024/ should be detected as overlapping"
    )


def test_cost_no_false_positive_when_age_missing():
    """No minimum_duration_risk warning when avg_object_age_days is absent (SO-005)."""
    from analyze_cost import analyze
    data = {
        "storage_price_per_gb": {"STANDARD_IA": 0.0125},
        "prefixes": [{
            "prefix": "data/",
            "storage_class": "STANDARD_IA",
            "object_count": 100,
            "total_size_bytes": 10 * 1024 * 1024 * 1024,
            # avg_object_age_days intentionally absent
        }],
    }
    result = analyze(data)
    duration_issues = [i for i in result["issues"] if i["type"] == "minimum_duration_at_risk"]
    assert len(duration_issues) == 0, (
        f"Should not flag duration risk when age is unknown; got {duration_issues}"
    )


def test_policy_prefix_wildcard():
    """s3:Get* prefix wildcard must match s3:GetObject (SO-006)."""
    from analyze_policy import analyze
    data = {
        "principal": "arn:aws:iam::123456789012:user/alice",
        "action": "s3:GetObject",
        "resource": "arn:aws:s3:::my-bucket/file.txt",
        "iam_policy": {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Action": ["s3:Get*", "s3:List*"],
                "Resource": "arn:aws:s3:::my-bucket/*",
            }],
        },
    }
    result = analyze(data)
    assert result["iam_evaluation"]["has_allow"], (
        "s3:Get* should match s3:GetObject but iam_allow is False"
    )
    assert result["denial_source"] != "iam_policy_missing_allow", (
        f"Should not deny when policy has s3:Get*; got denial_source={result['denial_source']}"
    )


def test_secret_scanner_no_dead_lines_var():
    """scan() should work correctly regardless (regression guard)."""
    from secret_scanner import scan
    text = "normal log line\nanother line\nno secrets here"
    result = scan(text)
    assert result["count"] == 0
    assert "redacted_text" in result


# ── Run ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("StorageOps Core — Smoke Tests\n")

    _run("Secret Scanner: detects AKIA", test_secret_scanner)
    _run("Secret Scanner: skip safe placeholders", test_secret_scanner_safe)
    _run("rclone Parser: detects ETag format mismatch", test_rclone_parser)
    _run("SigV4 Parser: parses SignatureDoesNotMatch XML", test_sigv4_parser)
    _run("Policy Analyzer: detects cross-account missing IAM", test_policy_analyzer)
    _run("Cost Analyzer: detects IA small-file penalty", test_cost_analyzer)
    _run("awscli Parser: detects SignatureDoesNotMatch in debug log", test_awscli_parser)
    _run("Throttling: no double-count for SlowDown", test_throttling_no_double_count)
    _run("Lifecycle: hierarchical prefix overlap detected", test_lifecycle_hierarchical_overlap)
    _run("Cost: no false-positive when age missing", test_cost_no_false_positive_when_age_missing)
    _run("Policy: s3:Get* prefix wildcard matches s3:GetObject", test_policy_prefix_wildcard)
    _run("Secret Scanner: regression guard", test_secret_scanner_no_dead_lines_var)

    print(f"\n{'='*50}")
    passed = sum(1 for r in results if r['passed'])
    print(f"Results: {passed}/{len(results)} passed")

    if passed == len(results):
        print("All tests passed.")
        sys.exit(0)
    else:
        print("Some tests failed.")
        sys.exit(1)
