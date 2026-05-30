"""
Parse s5cmd error output (non-debug mode).

Handles error lines like:
    ERROR "ls s3://bucket/*": InvalidBucketName: The specified bucket is not valid.
    ERROR "cp file s3://bucket/key": AccessDenied: Access Denied

Usage:
    cat s5cmd-errors.txt | python -m storageops-core.parsers.parse_s5cmd_error
"""
import re
import sys
import json
from pathlib import Path

PATTERNS = {
    'error_line': re.compile(
        r'ERROR\s+"([^"]+)"\s*:\s*(\w[\w\s]*?):\s*(.+)',
        re.IGNORECASE
    ),
    'version': re.compile(
        r's5cmd\s+version:\s*v?([\d.]+)', re.IGNORECASE
    ),
    'endpoint': re.compile(
        r'S5CMD_ENDPOINT_URL\s*=\s*(\S+)', re.IGNORECASE
    ),
    'awscli_works': re.compile(
        r'awscli.*(?:works|success|正常)', re.IGNORECASE
    ),
}

ERROR_CODES = {
    'InvalidBucketName': {
        'category': 's3_protocol_compatibility',
        'note': 'Bucket name may violate naming rules or virtual-hosted-style DNS requirements.',
        'fix_hint': 'Check bucket name format. Try path-style if using virtual-hosted.',
    },
    'AccessDenied': {
        'category': 'security_iam_policy',
        'note': 'Credentials lack permission for this operation.',
        'fix_hint': 'Verify IAM policy grants this action on this resource.',
    },
    'NoSuchBucket': {
        'category': 's3_protocol_compatibility',
        'note': 'Bucket does not exist or endpoint is wrong.',
        'fix_hint': 'Verify bucket name and endpoint URL.',
    },
    'SignatureDoesNotMatch': {
        'category': 's3_protocol_compatibility',
        'note': 'SigV4 signature mismatch.',
        'fix_hint': 'Check clock sync, region, and endpoint configuration.',
    },
    'RequestTimeTooSkewed': {
        'category': 's3_protocol_compatibility',
        'note': 'Clock skew exceeds tolerance.',
        'fix_hint': 'Sync system clock via NTP.',
    },
}


def parse(text: str) -> dict:
    """Parse s5cmd error output."""
    errors = []
    version = None
    endpoint = None
    awscli_works = False

    # Extract version
    vm = PATTERNS['version'].search(text)
    if vm:
        version = vm.group(1)

    # Extract endpoint
    em = PATTERNS['endpoint'].search(text)
    if em:
        endpoint = em.group(1)

    # Extract errors
    for m in PATTERNS['error_line'].finditer(text):
        command = m.group(1)
        error_type = m.group(2).strip()
        message = m.group(3).strip()

        known = ERROR_CODES.get(error_type, {})
        errors.append({
            "command": command,
            "error_type": error_type,
            "message": message,
            "category": known.get('category', 'unknown'),
            "note": known.get('note', ''),
            "fix_hint": known.get('fix_hint', ''),
        })

    # Detect cross-tool context
    awscli_works = bool(PATTERNS['awscli_works'].search(text))

    if awscli_works and errors:
        # Cross-tool comparison: awscli works, s5cmd doesn't
        cross_tool_issues = []
        for err in errors:
            if err['error_type'] == 'InvalidBucketName':
                cross_tool_issues.append(
                    "awscli defaults to path-style for custom endpoints; "
                    "s5cmd may use virtual-hosted-style. "
                    "Bucket name may not be a valid DNS subdomain."
                )
            elif err['error_type'] in ('SignatureDoesNotMatch',):
                cross_tool_issues.append(
                    "awscli and s5cmd may compute SigV4 differently or use different "
                    "region inference. Check region configuration in both tools."
                )
        if cross_tool_issues:
            errors.append({
                "cross_tool_comparison": True,
                "issues": cross_tool_issues,
                "recommendation": (
                    "Compare s5cmd and awscli configurations side by side: "
                    "endpoint, region, addressing style."
                ),
            })

    return {
        "version": version,
        "endpoint": endpoint,
        "awscli_also_tested": awscli_works,
        "errors": errors,
        "summary": {
            "total_errors": len([e for e in errors if not e.get('cross_tool_comparison')]),
            "error_types": list(set(
                e['error_type'] for e in errors
                if not e.get('cross_tool_comparison')
            )),
            "categories": list(set(
                e['category'] for e in errors
                if not e.get('cross_tool_comparison') and e.get('category')
            )),
        },
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        text = path.read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()

    result = parse(text)
    result["ok"] = True
    result["module"] = "parse_s5cmd_error"
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
