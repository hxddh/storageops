"""
Parse a SignatureDoesNotMatch XML error response into structured diff.

Extracts CanonicalRequest, StringToSign, and computes a comparison
against client-expected values (if provided).

Usage:
    cat error.xml | python -m storageops-core.parsers.parse_sigv4_error
    python -m storageops-core.parsers.parse_sigv4_error error.xml
"""
import re
import sys
import json
from pathlib import Path
from typing import Optional


def parse_xml_error(text: str) -> dict:
    """Extract error details from S3 XML error response."""
    h = lambda tag: (
        (m := re.search(f'<{tag}>([^<]+)</{tag}>', text)) and m.group(1)
    )

    return {
        "code": h('Code') or '',
        "message": h('Message') or '',
        "request_id": h('RequestId') or '',
        "host_id": h('HostId') or '',
        "access_key_id": h('AWSAccessKeyId') or '',
        "string_to_sign": h('StringToSign') or '',
        "canonical_request": h('CanonicalRequest') or '',
        "signature_provided": h('SignatureProvided') or '',
    }


def parse_string_to_sign(sts: str) -> dict:
    """Parse StringToSign into components."""
    lines = sts.strip().split('\n')
    if len(lines) < 4:
        return {"raw": sts, "parse_error": True}
    return {
        "algorithm": lines[0],
        "timestamp": lines[1],
        "scope": lines[2],
        "scope_parts": lines[2].split('/') if '/' in lines[2] else [],
        "region": lines[2].split('/')[1] if '/' in lines[2] and len(lines[2].split('/')) > 1 else '',
        "service": lines[2].split('/')[2] if '/' in lines[2] and len(lines[2].split('/')) > 2 else '',
        "request_hash": lines[3],
        "raw": sts,
    }


def parse_canonical_request(cr: str) -> dict:
    """Parse CanonicalRequest into components."""
    lines = cr.strip().split('\n')
    if len(lines) < 6:
        return {"raw": cr, "parse_error": True}
    return {
        "method": lines[0],
        "uri": lines[1],
        "query_string": lines[2],
        "canonical_headers": lines[3],
        "signed_headers": lines[4],
        "payload_hash": lines[5],
        "raw": cr,
    }


def diagnose(error: dict, system_time: Optional[str] = None,
             expected_region: Optional[str] = None) -> dict:
    """Generate diagnostic hypotheses from parsed error."""
    causes = []
    sts = parse_string_to_sign(error.get('string_to_sign', ''))
    cr = parse_canonical_request(error.get('canonical_request', ''))

    # Clock skew check
    if system_time and sts.get('timestamp'):
        causes.append({
            "type": "clock_skew_check",
            "note": "Compare system time with request timestamp. SigV4 tolerance is ±15 minutes.",
            "system_time": system_time,
            "request_timestamp": sts['timestamp'],
        })

    # Region mismatch check
    if expected_region and sts.get('region'):
        if expected_region != sts['region']:
            causes.append({
                "type": "region_mismatch",
                "note": "Signing region differs from expected region.",
                "expected": expected_region,
                "actual": sts['region'],
            })

    # Service check
    if sts.get('service') and sts['service'] != 's3':
        causes.append({
            "type": "wrong_service",
            "note": "Signing service is not 's3'.",
            "actual": sts['service'],
        })

    # Signed headers check (missing required headers)
    if cr.get('signed_headers'):
        signed = set(cr['signed_headers'].split(';'))
        required = {'host'}
        missing = required - signed
        if missing:
            causes.append({
                "type": "missing_signed_headers",
                "note": "Required headers not in signed headers list.",
                "missing": list(missing),
            })

    # Determine most likely root cause
    likely = None
    priority_order = ['clock_skew_check', 'region_mismatch', 'missing_signed_headers',
                      'wrong_service']
    for ptype in priority_order:
        for c in causes:
            if c['type'] == ptype:
                likely = ptype
                break
        if likely:
            break

    if not likely and causes:
        likely = causes[0]['type']
    elif not likely:
        likely = "unknown"

    return {
        "error": error,
        "string_to_sign_parsed": sts,
        "canonical_request_parsed": cr,
        "hypotheses": causes,
        "likely_root_cause": likely,
        "recommendation": (
            "Sync system clock via NTP and retry."
            if likely == 'clock_skew_check' else
            "Correct the region configuration to match the bucket/endpoint."
            if likely == 'region_mismatch' else
            "Verify signed headers include all required headers (host)."
            if likely == 'missing_signed_headers' else
            "Verify the service is 's3' for object storage endpoints."
            if likely == 'wrong_service' else
            "Compare full CanonicalRequest and StringToSign between client and server."
        ),
    }


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        text = path.read_text(encoding='utf-8', errors='replace')
    else:
        text = sys.stdin.read()

    error = parse_xml_error(text)
    result = diagnose(error)

    result["ok"] = True
    result["module"] = "parse_sigv4_error"
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
