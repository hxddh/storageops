"""
Parse awscli --debug output into a structured trace.

Extracts request/response cycles, credential resolution, retry events,
canonical requests, string-to-sign, and timing data.

Usage:
    cat awscli-debug.log | python -m storageops-core.parsers.parse_awscli_debug
    python -m storageops-core.parsers.parse_awscli_debug awscli-debug.log
"""
import re
import sys
import json
from pathlib import Path

# ── Patterns ──────────────────────────────────────────────────────────

PATTERNS = {
    'credential_source': re.compile(
        r'Found credentials in ([\w/._-]+)', re.IGNORECASE
    ),
    'endpoint': re.compile(
        r"Making request for OperationModel\(name=(\w+)\).*?Endpoint:\s*(https?://\S+)",
        re.DOTALL
    ),
    'canonical_request_block': re.compile(
        r'CanonicalRequest:\n(.+?)(?=\n\d{4}-\d{2}-\d{2}|\Z)', re.DOTALL
    ),
    'string_to_sign': re.compile(
        r'StringToSign:\n(AWS4-HMAC-SHA256\n.+?)(?=\n\d{4}-\d{2}-\d{2}|'
        r'\nMaking request|\nSending|\Z)', re.DOTALL
    ),
    'http_request': re.compile(
        r"Sending http request: <AWSPreparedRequest method=(\w+) url=(\S+)"
    ),
    'response_headers': re.compile(
        r'Response headers:\s*(\{.*?\})', re.DOTALL
    ),
    'response_body': re.compile(
        r'Response body:\n(.*?)(?=\n\d{4}-\d{2}-\d{2}.*?(?:DEBUG|ERROR|INFO)|\Z)',
        re.DOTALL
    ),
    'retry': re.compile(
        r'Retry needed.*?attempt (\d+).*?after ([\d.]+) seconds',
        re.IGNORECASE
    ),
    'error': re.compile(
        r'(ERROR|FAIL|Exception|Traceback).*', re.IGNORECASE
    ),
    'http_status': re.compile(
        r'Response (?:headers|status).*?(?:status[:\s]*)?(\d{3})', re.IGNORECASE
    ),
    'timing': re.compile(
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[.,]\d+)',
    ),
}


def parse(text: str) -> dict:
    """Parse awscli --debug output into structured trace."""
    lines = text.split('\n')

    trace = {
        "operations": [],
        "credential_sources": [],
        "retries": [],
        "errors": [],
        "canonical_requests": [],
        "string_to_signs": [],
        "response_bodies": [],
        "_has_sig_error": False,
        "_has_access_denied": False,
        "_has_throttling": False,
    }

    # Extract credential sources
    for m in PATTERNS['credential_source'].finditer(text):
        trace["credential_sources"].append(m.group(1))

    # Extract endpoints and operations
    for m in PATTERNS['endpoint'].finditer(text):
        trace["operations"].append({
            "name": m.group(1),
            "endpoint": m.group(2),
        })

    # Extract canonical requests
    for m in PATTERNS['canonical_request_block'].finditer(text):
        cr_text = m.group(1).strip()
        cr_lines = cr_text.split('\n')
        if len(cr_lines) >= 3:
            trace["canonical_requests"].append({
                "method": cr_lines[0],
                "uri": cr_lines[1],
                "query": cr_lines[2],
                "full": cr_text,
            })

    # Extract string-to-sign
    for m in PATTERNS['string_to_sign'].finditer(text):
        sts_text = m.group(1).strip()
        sts_lines = sts_text.split('\n')
        if len(sts_lines) >= 4:
            trace["string_to_signs"].append({
                "algorithm": sts_lines[0],
                "timestamp": sts_lines[1],
                "scope": sts_lines[2],
                "full": sts_text,
            })

    # Extract HTTP request — append to matching operation or create new entry
    for m in PATTERNS['http_request'].finditer(text):
        if trace["operations"]:
            trace["operations"][-1].update({
                "method": m.group(1),
                "url": m.group(2),
            })
        else:
            trace["operations"].append({
                "method": m.group(1),
                "url": m.group(2),
            })

    # Extract response bodies
    for m in PATTERNS['response_body'].finditer(text):
        body = m.group(1).strip()
        # Try to parse XML error
        error = None
        err_match = re.search(r'<Code>(\w+)</Code>', body)
        err_msg = re.search(r'<Message>([^<]+)</Message>', body)
        req_id = re.search(r'<RequestId>([^<]+)</RequestId>', body)
        if err_match:
            error = {
                "code": err_match.group(1),
                "message": err_msg.group(1) if err_msg else "",
                "request_id": req_id.group(1) if req_id else "",
            }
        trace["response_bodies"].append({
            "error": error,
            "body": body[:500],  # Truncate for output size
        })
        # Also track for summary
        if error:
            if error.get("code") == "SignatureDoesNotMatch":
                trace["_has_sig_error"] = True
            if error.get("code") == "AccessDenied":
                trace["_has_access_denied"] = True
            if error.get("code") in ("SlowDown", "Throttling", "RequestRateLimitExceeded"):
                trace["_has_throttling"] = True

    # Extract retries
    for m in PATTERNS['retry'].finditer(text):
        trace["retries"].append({
            "attempt": int(m.group(1)),
            "delay_seconds": float(m.group(2)),
        })

    # Extract errors
    for m in PATTERNS['error'].finditer(text):
        if 'DEBUG' not in m.group():  # Don't flag DEBUG lines as errors
            trace["errors"].append(m.group().strip())

    # Summary metrics
    trace["summary"] = {
        "total_operations": len(trace["operations"]),
        "total_retries": len(trace["retries"]),
        "total_errors": len(trace["errors"]),
        "has_signature_error": trace.get("_has_sig_error", False),
        "has_access_denied": trace.get("_has_access_denied", False),
        "has_throttling": trace.get("_has_throttling", False),
    }

    return trace


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        text = path.read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()

    result = parse(text)
    result["ok"] = True
    result["module"] = "parse_awscli_debug"
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
