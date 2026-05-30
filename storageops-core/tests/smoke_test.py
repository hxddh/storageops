"""
Smoke test: run parsers against golden case input artifacts and verify
output structure and key findings.

Usage:
    python -m storageops-core.tests.smoke_test
"""
import json
import sys
from pathlib import Path

# Add all sub-packages to path (using 'storageops-core' hyphenated dir name)
CORE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(CORE_DIR / 'utils'))
sys.path.insert(0, str(CORE_DIR / 'parsers'))
sys.path.insert(0, str(CORE_DIR / 'analyzers'))

from secret_scanner import scan as scan_secrets
from parse_rclone_log import parse as parse_rclone
from parse_sigv4_error import parse_xml_error, diagnose as diagnose_sigv4
from parse_awscli_debug import parse as parse_awscli
from analyze_policy import analyze as analyze_policy
from analyze_cost import analyze as analyze_cost

STORAGEOPS_ROOT = Path(__file__).parent.parent.parent
CASES_DIR = STORAGEOPS_ROOT / 'agents' / 'skills' / 'storageops-eval-golden-cases' / 'cases'

results = []


def test(name, fn):
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


# ── Run ────────────────────────────────────────────────────────────────

print("StorageOps Core v0.2 — Smoke Tests\n")

test("Secret Scanner: detects AKIA", test_secret_scanner)
test("Secret Scanner: skip safe placeholders", test_secret_scanner_safe)
test("rclone Parser: detects ETag format mismatch", test_rclone_parser)
test("SigV4 Parser: parses SignatureDoesNotMatch XML", test_sigv4_parser)
test("Policy Analyzer: detects cross-account missing IAM", test_policy_analyzer)
test("Cost Analyzer: detects IA small-file penalty", test_cost_analyzer)
test("awscli Parser: detects SignatureDoesNotMatch in debug log", test_awscli_parser)

print(f"\n{'='*50}")
passed = sum(1 for r in results if r['passed'])
print(f"Results: {passed}/{len(results)} passed")

if passed == len(results):
    print("All tests passed.")
    sys.exit(0)
else:
    print("Some tests failed.")
    sys.exit(1)
