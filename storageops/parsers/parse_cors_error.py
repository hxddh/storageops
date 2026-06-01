"""
Parse CORS error responses and preflight failures from S3-compatible storage.

Detects: Access-Control-Allow-Origin missing, preflight failure,
CORSForbidden, NoSuchCORSConfiguration, AllowedOrigin/Method/Header mismatches.

Usage:
    cat cors-error.txt | python parse_cors_error.py
"""
import re
import sys
import json
from pathlib import Path


# Regex patterns for CORS detection
_RE_NO_CORS_CONFIG = re.compile(r'NoSuchCORSConfiguration', re.IGNORECASE)
_RE_CORS_FORBIDDEN = re.compile(r'CORSForbidden', re.IGNORECASE)
_RE_MISSING_ALLOW_ORIGIN = re.compile(
    r'Access-Control-Allow-Origin.*(?:missing|not present|not set|absent)',
    re.IGNORECASE
)
_RE_PREFLIGHT_FAIL = re.compile(
    r'(?:preflight.*fail|OPTIONS.*\b403\b|\b403\b.*OPTIONS)',
    re.IGNORECASE
)
_RE_ALLOWED_ORIGIN = re.compile(r'AllowedOrigin[:\s]+(\S+)', re.IGNORECASE)
_RE_ALLOWED_METHOD = re.compile(r'AllowedMethod[:\s]+(\S+)', re.IGNORECASE)
_RE_ALLOWED_HEADER = re.compile(r'AllowedHeader[:\s]+(\S+)', re.IGNORECASE)
_RE_EXPOSE_HEADER = re.compile(r'ExposeHeader[:\s]+(\S+)', re.IGNORECASE)
_RE_ORIGIN_HEADER = re.compile(r'(?:^|\s)Origin:\s*(\S+)', re.IGNORECASE | re.MULTILINE)
_RE_REQUEST_METHOD = re.compile(
    r'(?:Access-Control-Request-Method|request.*method)[:\s]+(\S+)',
    re.IGNORECASE
)
_RE_REQUEST_HEADERS = re.compile(
    r'Access-Control-Request-Headers[:\s]+(.+?)(?:\n|$)',
    re.IGNORECASE
)
_RE_BUCKET = re.compile(
    r'(?:bucket[/:\s]+([a-z0-9][a-z0-9\-]{1,61}[a-z0-9])|s3://([a-z0-9][a-z0-9\-]{1,61}[a-z0-9]))',
    re.IGNORECASE
)
_RE_MISSING_RESPONSE_HEADERS = re.compile(
    r'(?:missing|not present|absent)[^:]*:\s*(Access-Control-[A-Za-z-]+)',
    re.IGNORECASE
)
_RE_CORS_POLICY_ERROR = re.compile(
    r'(?:CORS.*policy|policy.*CORS|not.*allowed.*origin|origin.*not.*allowed)',
    re.IGNORECASE
)

# Headers that should be present in CORS responses
_REQUIRED_CORS_RESPONSE_HEADERS = [
    'Access-Control-Allow-Origin',
    'Access-Control-Allow-Methods',
    'Access-Control-Allow-Headers',
]


def _extract_bucket(text: str):
    m = _RE_BUCKET.search(text)
    if m:
        return m.group(1) or m.group(2)
    return None


def _extract_missing_headers(text: str) -> list:
    missing = []
    for header in _REQUIRED_CORS_RESPONSE_HEADERS:
        if re.search(
            rf'(?:missing|not present|absent|no)[^:]*{re.escape(header)}',
            text, re.IGNORECASE
        ):
            missing.append(header)
    for m in _RE_MISSING_RESPONSE_HEADERS.finditer(text):
        h = m.group(1)
        if h not in missing:
            missing.append(h)
    return missing


def parse(text: str) -> dict:
    """
    Parse CORS error text and return structured diagnostics.

    Returns:
        {
            "cors_errors": [{"type": str, "origin": str, "method": str, "headers": [str]}],
            "bucket": str | None,
            "no_cors_config": bool,
            "preflight_failed": bool,
            "missing_headers": [str],
            "summary": {"error_count": int, "needs_cors_config": bool}
        }
    """
    cors_errors = []

    no_cors_config = bool(_RE_NO_CORS_CONFIG.search(text))
    cors_forbidden = bool(_RE_CORS_FORBIDDEN.search(text))
    preflight_failed = bool(_RE_PREFLIGHT_FAIL.search(text))
    missing_allow_origin = bool(_RE_MISSING_ALLOW_ORIGIN.search(text))
    cors_policy_error = bool(_RE_CORS_POLICY_ERROR.search(text))

    # Extract origin from request/response
    origin = None
    origin_m = _RE_ORIGIN_HEADER.search(text)
    if origin_m:
        origin = origin_m.group(1).strip()
    if not origin:
        ao_m = _RE_ALLOWED_ORIGIN.search(text)
        if ao_m:
            origin = ao_m.group(1).strip()

    # Extract method
    method = None
    method_m = _RE_REQUEST_METHOD.search(text)
    if method_m:
        method = method_m.group(1).strip()

    # Extract request headers
    req_headers = []
    req_hdr_m = _RE_REQUEST_HEADERS.search(text)
    if req_hdr_m:
        req_headers = [h.strip() for h in req_hdr_m.group(1).split(',') if h.strip()]

    # Build cors_errors list
    if no_cors_config:
        cors_errors.append({
            "type": "NoSuchCORSConfiguration",
            "origin": origin or "",
            "method": method or "",
            "headers": req_headers,
        })
    if cors_forbidden:
        cors_errors.append({
            "type": "CORSForbidden",
            "origin": origin or "",
            "method": method or "",
            "headers": req_headers,
        })
    if preflight_failed:
        cors_errors.append({
            "type": "preflight_failed",
            "origin": origin or "",
            "method": method or "",
            "headers": req_headers,
        })
    if missing_allow_origin and not cors_errors:
        cors_errors.append({
            "type": "missing_allow_origin_header",
            "origin": origin or "",
            "method": method or "",
            "headers": req_headers,
        })
    if cors_policy_error and not cors_errors:
        cors_errors.append({
            "type": "cors_policy_mismatch",
            "origin": origin or "",
            "method": method or "",
            "headers": req_headers,
        })

    # If no specific errors found but CORS content is present, record a generic issue
    if not cors_errors and (
        _RE_ALLOWED_ORIGIN.search(text) or
        _RE_EXPOSE_HEADER.search(text) or
        re.search(r'CORS', text, re.IGNORECASE)
    ):
        cors_errors.append({
            "type": "cors_configuration_issue",
            "origin": origin or "",
            "method": method or "",
            "headers": req_headers,
        })

    missing_headers = _extract_missing_headers(text)
    bucket = _extract_bucket(text)
    needs_cors_config = no_cors_config or len(cors_errors) > 0

    return {
        "cors_errors": cors_errors,
        "bucket": bucket,
        "no_cors_config": no_cors_config,
        "preflight_failed": preflight_failed,
        "missing_headers": missing_headers,
        "summary": {
            "error_count": len(cors_errors),
            "needs_cors_config": needs_cors_config,
        },
    }


def main():
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()
    result = parse(text)
    result["ok"] = True
    result["module"] = "parse_cors_error"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
