"""
StorageOps offline diagnostic utilities.

Provides domain classification, evidence assessment, analysis pipeline,
and report generation. Used by api_server.py and the serve command.
Pi Coding Agent invokes storageops CLI tools directly for agent sessions.
"""
from __future__ import annotations

import json
import re

from secret_scanner import scan as scan_secrets
from signatures import auto_detect


# ── Evidence Requirements per Domain ──────────────────────────────────

EVIDENCE_CHECKLIST = {
    'cors_configuration': {
        'required': ['Error message (NoSuchCORSConfiguration, CORSForbidden, etc.)', 'Origin header value', 'HTTP method'],
        'helpful': ['Full preflight request/response headers', 'Bucket name'],
    },
    'replication_versioning': {
        'required': ['ReplicationStatus per object or rule', 'Source and destination bucket names'],
        'helpful': ['IAM policy for replication role', 'KMS key ARN if encryption is used', 'aws s3api get-bucket-replication output'],
    },
    'bigdata_pipeline': {
        'required': ['Full stack trace or error log', 'Hadoop/Spark version', 'Committer type (staging or magic)'],
        'helpful': ['spark.hadoop.fs.s3a.committer.name config', 'IAM policy for EMR/Spark role', '_temporary/ path that failed'],
    },
    's3_protocol_compatibility': {
        'required': [
            'Error code or message (SignatureDoesNotMatch, InvalidPart, etc.)',
            'Provider name and endpoint',
            'SDK or tool name and version',
        ],
        'helpful': [
            'Debug log with canonical request and string-to-sign',
            'Client region configuration',
            'Whether path-style or virtual-hosted-style is used',
        ],
    },
    'cli_sdk_behavior': {
        'required': [
            'Tool name and exact version',
            'The command that was run (redact secrets)',
            'Error output or debug log',
        ],
        'helpful': [
            'Configuration file (endpoint, region, concurrency settings)',
            'Whether the same operation works with a different tool',
            'Object size and count',
        ],
    },
    'performance_throughput': {
        'required': [
            'Tool and version used',
            'Observed throughput or timing data',
            'Object sizes and count',
        ],
        'helpful': [
            'Concurrency and part size settings',
            'RTT to endpoint (ping result)',
            'Client machine specs (CPU, memory, disk type)',
            'Any 429/503/5xx errors in logs',
        ],
    },
    'mount_filesystem_workspace': {
        'required': [
            'Mount type and version (s3fs, rclone mount, bosfs, etc.)',
            'Mount options (command line or fstab)',
            'Workspace description (git repos, node_modules, venv, etc.)',
        ],
        'helpful': [
            'Timing comparison: local SSD vs mount for same operation',
            'Kernel log FUSE errors: dmesg | grep -i fuse',
            'Concurrency: number of simultaneous users/processes',
        ],
    },
    'network_endpoint_access': {
        'required': [
            'Endpoint URL or hostname',
            'Access path type (public, VPC, PrivateLink)',
        ],
        'helpful': [
            'DNS resolution output: dig <endpoint-hostname>',
            'Ping/traceroute to endpoint',
            'TLS certificate details',
            'Proxy configuration',
        ],
    },
    'security_iam_policy': {
        'required': [
            'Full error message with request ID',
            'Bucket name and object key (if applicable)',
            'Action being attempted (GetObject, PutObject, ListBucket, etc.)',
        ],
        'helpful': [
            'IAM policy JSON for the principal (redact account IDs if needed)',
            'Bucket policy JSON',
            'Whether STS/temporary credentials are in use',
        ],
    },
    'lifecycle_cost': {
        'required': [
            'Lifecycle configuration (XML or description)',
            'Storage class of objects in question',
            'Object sizes and count per prefix',
        ],
        'helpful': [
            'Access frequency patterns (how often are objects read?)',
            'Current monthly cost breakdown if available',
            'Region and pricing tier',
        ],
    },
}


# ── Domain classification ─────────────────────────────────────────────

def classify_evidence(text: str) -> dict:
    """Classify evidence and return primary domain with quality assessment."""
    detections = auto_detect(text)
    if not detections:
        return {
            'primary_domain': 'unknown',
            'all_domains': [],
            'scores': {},
            'evidence_quality': 'insufficient',
        }
    primary = detections[0]
    return {
        'primary_domain': primary['domain'],
        'all_domains': [d['domain'] for d in detections],
        'scores': {d['domain']: d['confidence'] for d in detections},
        'evidence_quality': 'sufficient' if primary['confidence'] >= 0.5 else 'partial',
    }


def assess_evidence(text: str, domain: str) -> dict:
    """Check what evidence is present vs missing for a domain."""
    checklist = EVIDENCE_CHECKLIST.get(domain, {})
    if not checklist:
        return {'quality': 'unknown', 'missing': []}

    has_debug = bool(re.search(r'\d{4}-\d{2}-\d{2}.*(?:DEBUG|ERROR|INFO|WARN)', text))
    has_error = bool(re.search(
        r'(?:Error|ERROR|AccessDenied|SignatureDoesNotMatch|corrupted|failed)', text
    ))
    missing_required = []
    missing_helpful = []

    for req in checklist.get('required', []):
        indicator = _indicator_for(req)
        if indicator and not indicator(text):
            missing_required.append(req)

    for help_item in checklist.get('helpful', []):
        indicator = _indicator_for(help_item)
        if indicator and not indicator(text):
            missing_helpful.append(help_item)

    quality = 'sufficient' if not missing_required else 'partial'
    if not has_error and not has_debug:
        quality = 'insufficient'

    return {
        'quality': quality,
        'missing_required': missing_required,
        'missing_helpful': missing_helpful,
    }


def _indicator_for(item: str):
    indicators = {
        'error': lambda t: bool(re.search(r'(?:Error|ERROR|fail|denied)', t)),
        'tool': lambda t: bool(re.search(
            r'(?:aws-cli|rclone|s5cmd|bcecmd|obsutil|boto3|aws\s+s3)', t, re.IGNORECASE
        )),
        'debug': lambda t: bool(re.search(r'(?:DEBUG|--debug|-vv)', t)),
        'config': lambda t: bool(re.search(
            r'(?:endpoint|region|concurrency|part.size|chunk.size)', t, re.IGNORECASE
        )),
        'timing': lambda t: bool(re.search(
            r'(?:\d+\s*(?:ms|s|MB/s)|RTT|latency|ping|elapsed)', t, re.IGNORECASE
        )),
        'mount': lambda t: bool(re.search(
            r'(?:s3fs|bosfs|rclone mount|fuse|mount\s+-[a-zA-Z])', t, re.IGNORECASE
        )),
        'policy': lambda t: bool(re.search(
            r'(?:Statement|Effect|Principal|Action|Resource|bucket.*policy)', t
        )),
    }
    for key, fn in indicators.items():
        if key in item.lower():
            return fn
    return None


# ── Analysis Pipeline ─────────────────────────────────────────────────

def run_analysis(domain: str, text: str) -> dict:
    """Run domain analysis. Returns structured result dict."""
    secret_result = scan_secrets(text)
    if secret_result['count'] > 0:
        text = secret_result['redacted_text']

    result: dict = {}
    try:
        if domain == 'cors_configuration':
            from parse_cors_error import parse as parse_cors
            from analyze_cors import analyze as analyze_cors
            parsed = parse_cors(text)
            result = analyze_cors(parsed)

        elif domain == 'replication_versioning':
            from parse_replication_status import parse as parse_replication
            from analyze_replication import analyze as analyze_replication
            parsed = parse_replication(text)
            result = analyze_replication(parsed)

        elif domain == 'bigdata_pipeline':
            from parse_hadoop_s3a import parse as parse_hadoop
            result = parse_hadoop(text)

        elif domain == 's3_protocol_compatibility':
            from parse_sigv4_error import parse_xml_error, diagnose as diagnose_sigv4
            if '<Code>' in text:
                result = diagnose_sigv4(parse_xml_error(text))
            else:
                from parse_awscli_debug import parse as parse_awscli
                result = parse_awscli(text)

        elif domain == 'cli_sdk_behavior':
            if 'rclone' in text.lower():
                from parse_rclone_log import parse as parse_rclone
                result = parse_rclone(text)
            elif 's5cmd' in text.lower():
                from parse_s5cmd_error import parse as parse_s5cmd_err
                result = parse_s5cmd_err(text)
            else:
                from parse_awscli_debug import parse as parse_awscli
                result = parse_awscli(text)

        elif domain == 'performance_throughput':
            from parse_awscli_debug import parse as parse_awscli
            from detect_throttling import detect as detect_throttling
            parsed = parse_awscli(text)
            if parsed.get('summary', {}).get('has_throttling'):
                result = detect_throttling(parsed)
            else:
                result = parsed

        elif domain == 'mount_filesystem_workspace':
            from analyze_metadata_amplification import analyze as analyze_amp
            import re as _re
            # Extract RTT from text if present (e.g. "rtt=50ms", "latency: 80ms")
            rtt_match = _re.search(r'rtt[= :]?\s*(\d+(?:\.\d+)?)\s*ms', text, _re.IGNORECASE)
            rtt_ms = float(rtt_match.group(1)) if rtt_match else 50
            # Extract syscall counts if strace-style output is present
            syscalls: dict[str, int] = {}
            for name in ('stat', 'lstat', 'open', 'read', 'write', 'readdir', 'getdents', 'rename', 'unlink', 'fsync'):
                m = _re.search(rf'\b{name}\b.*?(\d{{3,}})', text, _re.IGNORECASE)
                if m:
                    syscalls[name] = int(m.group(1))
            if not syscalls:
                syscalls = {"stat": 10000, "open": 2000, "readdir": 200, "read": 5000}
            result = analyze_amp({
                "rtt_ms": rtt_ms,
                "syscalls": syscalls,
                "operation_name": "detected from input",
                "note": "Syscall counts extracted from input text." if rtt_match or any(syscalls) else
                        "Default estimation — provide strace output for accurate analysis.",
            })

        elif domain == 'security_iam_policy':
            from analyze_policy import analyze as analyze_policy, analyze_inline_403
            try:
                result = analyze_policy(json.loads(text))
            except json.JSONDecodeError:
                result = analyze_inline_403(text)

        elif domain == 'lifecycle_cost':
            from analyze_cost import analyze as analyze_cost
            try:
                result = analyze_cost(json.loads(text))
            except json.JSONDecodeError:
                from parse_lifecycle_xml import parse as parse_lifecycle
                result = parse_lifecycle(text)

        elif domain == 'network_endpoint_access':
            from parse_network_diagnostics import parse as parse_net_diag
            from analyze_network import analyze as analyze_net
            parsed = parse_net_diag(text)
            result = analyze_net(parsed)
            result['_parsed'] = parsed

    except Exception as exc:
        result = {"error": str(exc), "note": "Analysis failed. More evidence may be needed."}

    result['_secret_scan'] = {
        'findings': secret_result['count'],
        'redacted': secret_result['count'] > 0,
    }
    return result


# ── Report Generation ─────────────────────────────────────────────────

def generate_report(domain: str, analysis: dict, evidence_quality: str) -> str:
    """Generate a structured markdown report from analysis results."""
    secret_info = analysis.pop('_secret_scan', {})
    redacted_note = (
        "\n> Warning: secrets detected in input and redacted before analysis.\n"
        if secret_info.get('redacted') else ''
    )

    report = f"""---
category: {domain}
root_cause_type: unknown
confidence: 0.5
severity: medium
---

## Summary

{_extract_conclusion(analysis, domain)}
{redacted_note}
## Key Evidence

```json
{json.dumps(analysis, indent=2, ensure_ascii=False, default=str)[:3000]}
```

## Remediation

{_extract_recommendations(analysis, domain)}

## Safety Notes

- All remediation steps require manual review before execution.
- Label any cloud-mutating command with `# manual-only:` before running.

---
*Generated by StorageOps offline analysis. Evidence quality: {evidence_quality}.*
*Verify all conclusions before acting.*
"""
    analysis['_secret_scan'] = secret_info
    return report


def _extract_conclusion(analysis: dict, domain: str) -> str:
    if analysis.get('conclusion'):
        return str(analysis['conclusion'])
    if analysis.get('note'):
        return str(analysis['note'])
    summary = analysis.get('summary', {})
    if summary.get('root_cause_likely'):
        return f"Likely root cause: {summary['root_cause_likely']}"
    if summary.get('corrupted_count', 0) > 0:
        return f"Detected {summary['corrupted_count']} transfer checksum failure(s)."
    if summary.get('has_signature_error'):
        return "SigV4 signature error detected."
    if analysis.get('denial_source'):
        return f"Access denial source: {analysis['denial_source']}"
    return "See Key Evidence section for analysis details."


def _extract_recommendations(analysis: dict, domain: str) -> str:
    recs = analysis.get('recommendations') or analysis.get('recommendation')
    if isinstance(recs, list):
        return '\n'.join(f'- {r}' for r in recs) or _default_rec(domain)
    if isinstance(recs, str) and recs:
        return f'- {recs}'
    if isinstance(recs, dict):
        return '\n'.join(f'- {k}: {v}' for k, v in recs.items())
    return _default_rec(domain)


def _default_rec(domain: str) -> str:
    defaults = {
        's3_protocol_compatibility': '- Check clock sync (NTP) and region configuration.',
        'cors_configuration': '- Add or update CORS configuration on the bucket. Check allowed origins.',
        'replication_versioning': '- Ensure versioning is enabled and the replication IAM role has required permissions.',
        'bigdata_pipeline': '- Check S3A credentials, endpoint config, and committer type for the job engine.',
        'cli_sdk_behavior': '- Check tool version and configuration. Try a different tool to compare.',
        'performance_throughput': '- Tune concurrency and part size. Check for throttling (429).',
        'mount_filesystem_workspace': '- Use local SSD for hot workspace. Use object storage for persistence only.',
        'security_iam_policy': '- Check IAM and bucket policy. For cross-account, both sides must Allow.',
        'lifecycle_cost': '- Review lifecycle rules. Avoid STANDARD_IA for small objects (<128 KB).',
        'network_endpoint_access': '- Check DNS resolution, TCP connectivity, and TLS handshake.',
    }
    return defaults.get(domain, '- See Key Evidence section.')
