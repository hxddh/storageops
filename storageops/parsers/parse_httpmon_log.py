"""Parse httpmon (https-traffic-inspector) output for StorageOps diagnostics.

Handles two formats:
  - NDJSON: --format json output (one JSON object per line)
  - HAR:    --har output.har files (HTTP Archive standard format)

Extracts S3-relevant signals: error codes, status, auth type, timing, CORS headers.
Never exposes raw credential values — Authorization header values are pattern-matched
and classified only (SigV4 / presigned / anonymous / other).
"""
from __future__ import annotations

import json
import re
from typing import Any


# ── S3 URL patterns ───────────────────────────────────────────────────

_S3_HOST_RE = re.compile(
    r'(s3[\.-][a-z0-9-]*\.amazonaws\.com|'
    r'[a-z0-9-]+\.s3[\.-][a-z0-9-]*\.amazonaws\.com|'
    r'[a-z0-9-]+\.s3\.amazonaws\.com|'
    r'(?:bos|bj|gz|su)\.bcebos\.com|'
    r'oss-[a-z0-9-]+\.aliyuncs\.com|'
    r'cos\.[a-z0-9-]+\.myqcloud\.com|'
    r'tos-[a-z0-9-]+\.volces\.com|'
    r'[a-z0-9-]+\.r2\.cloudflarestorage\.com)',
    re.IGNORECASE,
)

_S3_XML_ERROR_RE = re.compile(
    r'<Code>([^<]+)</Code>.*?<Message>([^<]*)</Message>'
    r'(?:.*?<RequestId>([^<]*)</RequestId>)?',
    re.DOTALL,
)

_AUTH_SIGV4_RE = re.compile(r'AWS4-HMAC-SHA256\s+Credential=([^/]+)/', re.IGNORECASE)
_AUTH_PRESIGNED_RE = re.compile(r'X-Amz-Signature|X-Goog-Signature', re.IGNORECASE)

_AMZ_REQUEST_ID_RE = re.compile(r'^x-amz-request-id$', re.IGNORECASE)
_CORS_HEADERS = {
    'access-control-allow-origin',
    'access-control-allow-methods',
    'access-control-allow-headers',
    'access-control-expose-headers',
    'access-control-max-age',
    'vary',
}


# ── Header utilities ──────────────────────────────────────────────────

def _headers_to_dict(headers: Any) -> dict[str, str]:
    """Normalize headers list [{name, value}] or dict → lowercase-key dict."""
    if isinstance(headers, dict):
        return {k.lower(): v for k, v in headers.items()}
    if isinstance(headers, list):
        return {h.get('name', '').lower(): h.get('value', '') for h in headers}
    return {}


def _classify_auth(headers: dict[str, str], url: str) -> str:
    """Return auth type without exposing credential values."""
    auth = headers.get('authorization', '')
    if _AUTH_SIGV4_RE.search(auth):
        return 'sigv4'
    if _AUTH_PRESIGNED_RE.search(url):
        return 'presigned_url'
    if auth.startswith('AWS '):
        return 'sigv2_deprecated'
    if auth:
        return 'other'
    return 'anonymous'


def _extract_s3_operation(method: str, url: str) -> str:
    """Infer S3 operation name from HTTP method + URL path."""
    path = url.split('?')[0]
    qs = url[len(path):]
    parts = [p for p in path.split('/') if p]

    if method == 'GET':
        if '?list-type=' in qs or '?prefix' in qs:
            return 'ListObjectsV2'
        if '?uploads' in qs:
            return 'ListMultipartUploads'
        if len(parts) >= 2:
            return 'GetObject'
        return 'ListBuckets' if not parts else 'ListObjects'
    if method == 'PUT':
        if '?acl' in qs:
            return 'PutObjectAcl'
        if '?partNumber=' in qs:
            return 'UploadPart'
        if '?uploadId=' in qs:
            return 'CompleteMultipartUpload'
        if len(parts) >= 2:
            return 'PutObject'
        return 'CreateBucket'
    if method == 'DELETE':
        if '?uploadId=' in qs:
            return 'AbortMultipartUpload'
        if len(parts) >= 2:
            return 'DeleteObject'
        return 'DeleteBucket'
    if method == 'HEAD':
        return 'HeadObject' if len(parts) >= 2 else 'HeadBucket'
    if method == 'POST':
        if '?uploads' in qs:
            return 'CreateMultipartUpload'
        if '?delete' in qs:
            return 'DeleteObjects'
        return 'PostObject'
    if method == 'OPTIONS':
        return 'CORSPreflight'
    return f'{method}_Unknown'


def _parse_error_body(body: str) -> dict:
    """Extract error code, message, request ID from S3 XML error body."""
    m = _S3_XML_ERROR_RE.search(body or '')
    if m:
        return {
            'error_code': m.group(1),
            'error_message': m.group(2)[:200],
            'request_id': m.group(3) or '',
        }
    return {}


# ── Entry normalization ───────────────────────────────────────────────

def _process_entry(req: dict, resp: dict, timing_ms: float | None) -> dict | None:
    """Convert a request+response pair to a StorageOps diagnostic entry."""
    url = req.get('url', '')
    method = req.get('method', 'GET').upper()

    if not _S3_HOST_RE.search(url):
        return None  # Not an S3 request

    req_headers = _headers_to_dict(req.get('headers', {}))
    resp_headers = _headers_to_dict(resp.get('headers', {}))

    status = int(resp.get('status', 0))
    body = resp.get('content', {}).get('text', '') if 'content' in resp else resp.get('body', '')

    auth_type = _classify_auth(req_headers, url)
    operation = _extract_s3_operation(method, url)

    # X-Amz-Date presence indicates request timestamp
    amz_date = req_headers.get('x-amz-date', req_headers.get('x-amz-content-sha256', ''))
    request_id = resp_headers.get('x-amz-request-id', '')

    cors_response_headers = {k: v for k, v in resp_headers.items() if k in _CORS_HEADERS}

    entry: dict = {
        'operation': operation,
        'method': method,
        'status': status,
        'url_host': _S3_HOST_RE.search(url).group(0) if _S3_HOST_RE.search(url) else '',
        'auth_type': auth_type,
        'has_amz_date': bool(amz_date),
        'request_id': request_id,
    }

    if timing_ms is not None:
        entry['timing_ms'] = round(timing_ms, 1)

    if status >= 400:
        err = _parse_error_body(body)
        if err:
            entry.update(err)
        elif body:
            entry['raw_error_snippet'] = body[:300]

    if cors_response_headers:
        entry['cors_headers'] = cors_response_headers

    # Content-Type of response
    ct = resp_headers.get('content-type', '')
    if ct:
        entry['response_content_type'] = ct.split(';')[0].strip()

    return entry


# ── HAR parser ────────────────────────────────────────────────────────

def _parse_har(data: dict) -> list[dict]:
    entries = []
    for entry in data.get('log', {}).get('entries', []):
        req = entry.get('request', {})
        resp = entry.get('response', {})
        timings = entry.get('timings', {})
        total_ms = sum(v for v in timings.values() if isinstance(v, (int, float)) and v >= 0)
        processed = _process_entry(req, resp, total_ms or None)
        if processed:
            entries.append(processed)
    return entries


# ── NDJSON parser ─────────────────────────────────────────────────────

def _parse_ndjson(text: str) -> list[dict]:
    """Parse httpmon --format json NDJSON output."""
    entries = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # httpmon NDJSON: alternating request/response lines, or combined objects
    pending_req: dict | None = None

    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        typ = obj.get('type', '')

        if typ == 'request' or ('method' in obj and 'url' in obj and 'status' not in obj):
            pending_req = obj
            continue

        if typ == 'response' or 'status' in obj:
            if pending_req:
                timing = obj.get('timing', {})
                total_ms = timing.get('total') if isinstance(timing, dict) else None
                processed = _process_entry(pending_req, obj, total_ms)
                if processed:
                    entries.append(processed)
                pending_req = None
            continue

        # Combined object (some httpmon versions emit one object per exchange)
        if 'method' in obj and 'status' in obj:
            timing = obj.get('timing', {})
            total_ms = timing.get('total') if isinstance(timing, dict) else None
            processed = _process_entry(obj, obj, total_ms)
            if processed:
                entries.append(processed)

    return entries


# ── Public API ────────────────────────────────────────────────────────

def parse(text: str) -> dict:
    """Parse httpmon NDJSON or HAR output into StorageOps diagnostic signals.

    Returns a dict with:
      - format: "har" | "ndjson" | "unknown"
      - s3_request_count: total S3 requests captured
      - entries: list of per-request dicts
      - error_summary: aggregated error codes and counts
      - status_distribution: {status_code: count}
      - auth_types: list of distinct auth types seen
      - has_cors_traffic: bool
      - timing_stats: {min_ms, max_ms, avg_ms} if timing available
      - signals: list of diagnostic signals for StorageOps
    """
    text = text.strip()
    if not text:
        return {'error': 'Empty input', 'format': 'unknown', 's3_request_count': 0, 'entries': []}

    fmt = 'unknown'
    entries: list[dict] = []

    # Try HAR first (JSON object with log.entries)
    if text.startswith('{'):
        try:
            data = json.loads(text)
            if 'log' in data and 'entries' in data['log']:
                fmt = 'har'
                entries = _parse_har(data)
        except json.JSONDecodeError:
            pass

    # Try NDJSON
    if fmt == 'unknown' or (fmt == 'har' and not entries):
        ndjson_entries = _parse_ndjson(text)
        if ndjson_entries or fmt == 'unknown':
            fmt = 'ndjson'
            entries = ndjson_entries

    # Aggregate
    error_counts: dict[str, int] = {}
    status_dist: dict[str, int] = {}
    auth_types: set[str] = set()
    timings: list[float] = []
    has_cors = False

    for e in entries:
        status_dist[str(e['status'])] = status_dist.get(str(e['status']), 0) + 1
        auth_types.add(e['auth_type'])
        if e.get('timing_ms'):
            timings.append(e['timing_ms'])
        if e.get('cors_headers'):
            has_cors = True
        if err := e.get('error_code'):
            error_counts[err] = error_counts.get(err, 0) + 1

    timing_stats = {}
    if timings:
        timing_stats = {
            'min_ms': round(min(timings), 1),
            'max_ms': round(max(timings), 1),
            'avg_ms': round(sum(timings) / len(timings), 1),
        }

    # Derive diagnostic signals
    signals: list[str] = []
    if error_counts.get('AccessDenied') or error_counts.get('AllAccessDisabled'):
        signals.append('access_denied_detected → security_iam_policy')
    if error_counts.get('SignatureDoesNotMatch') or error_counts.get('InvalidSignature'):
        signals.append('signature_error_detected → s3_protocol_compatibility')
    if error_counts.get('RequestExpired'):
        signals.append('clock_skew_suspected → s3_protocol_compatibility')
    if any(k in error_counts for k in ('SlowDown', 'ServiceUnavailable', 'RequestRateLimitExceeded')):
        signals.append('throttling_detected → performance_throughput')
    if has_cors:
        signals.append('cors_traffic_captured → cors_configuration')
    if 'anonymous' in auth_types and any(int(s) >= 400 for s in status_dist):
        signals.append('unauthenticated_requests_with_errors → security_iam_policy')
    if 'sigv2_deprecated' in auth_types:
        signals.append('deprecated_sigv2_auth → s3_protocol_compatibility')
    if timing_stats.get('avg_ms', 0) > 5000:
        signals.append('high_latency_detected → performance_throughput')

    return {
        'format': fmt,
        's3_request_count': len(entries),
        'entries': entries,
        'error_summary': error_counts,
        'status_distribution': status_dist,
        'auth_types': sorted(auth_types),
        'has_cors_traffic': has_cors,
        'timing_stats': timing_stats,
        'signals': signals,
    }
