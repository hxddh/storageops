"""Parser for network diagnostic output: dig, curl -v, ping, mtr, traceroute."""
from __future__ import annotations

import re
import sys
import json
from pathlib import Path


_RE_DIG_STATUS = re.compile(r'status:\s*(\w+)', re.IGNORECASE)
_RE_DIG_ANSWER = re.compile(r'ANSWER SECTION.*?(?=;|\Z)', re.DOTALL | re.IGNORECASE)
_RE_DIG_A_RECORD = re.compile(r'(\S+)\s+\d+\s+IN\s+(A|AAAA|CNAME)\s+(\S+)', re.IGNORECASE)
_RE_DIG_NXDOMAIN = re.compile(r'NXDOMAIN|status:\s*NXDOMAIN', re.IGNORECASE)
_RE_DIG_SERVFAIL = re.compile(r'SERVFAIL|status:\s*SERVFAIL', re.IGNORECASE)
_RE_DIG_TIME = re.compile(r'Query time:\s*(\d+)\s*msec', re.IGNORECASE)

_RE_CURL_HTTP_STATUS = re.compile(r'HTTP/\d[\d.]*\s+(\d{3})', re.IGNORECASE)
_RE_CURL_CONNECT_REFUSED = re.compile(r'Connection refused|connect to .* failed|Failed to connect', re.IGNORECASE)
_RE_CURL_TIMEOUT = re.compile(r'timed out|Operation timed out|Connection timed out', re.IGNORECASE)
_RE_CURL_TLS_ERROR = re.compile(
    r'SSL certificate problem|certificate verify failed|SSL handshake fail'
    r'|TLS handshake|unable to get local issuer certificate|self.signed certificate',
    re.IGNORECASE,
)
_RE_CURL_TLS_CERT_CN = re.compile(r'common name:\s*([^\n]+)', re.IGNORECASE)
_RE_CURL_TOTAL_TIME = re.compile(r'time_total\s*:\s*([\d.]+)', re.IGNORECASE)
_RE_CURL_CONNECT_TIME = re.compile(r'time_connect\s*:\s*([\d.]+)', re.IGNORECASE)
_RE_CURL_TLS_TIME = re.compile(r'time_appconnect\s*:\s*([\d.]+)', re.IGNORECASE)
_RE_CURL_LOCATION = re.compile(r'Location:\s*(\S+)', re.IGNORECASE)
_RE_CURL_SERVER_HEADER = re.compile(r'Server:\s*([^\r\n]+)', re.IGNORECASE)

_RE_PING_RTT = re.compile(
    r'min/avg/max(?:/mdev)?\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)',
    re.IGNORECASE,
)
_RE_PING_LOSS = re.compile(r'(\d+(?:\.\d+)?)\s*%\s*packet loss', re.IGNORECASE)
_RE_PING_HOST_UNREACHABLE = re.compile(r'Destination Host Unreachable|100% packet loss', re.IGNORECASE)

_RE_MTR_HOP = re.compile(
    r'^\s*(\d+)\.\s+(\S+)\s+([\d.]+)\s*%\s+\d+\s+([\d.]+)',
    re.MULTILINE,
)
_RE_TRACEROUTE_HOP = re.compile(
    r'^\s*(\d+)\s+(?:(\S+)\s+)?\(([\d.]+)\)\s+([\d.]+)\s*ms',
    re.MULTILINE,
)

_RE_ENDPOINT_URL = re.compile(
    r'https?://([a-zA-Z0-9._-]+(?::\d+)?)',
    re.IGNORECASE,
)
_RE_VPC_ENDPOINT = re.compile(
    r'vpce-[a-z0-9]+\.s3\.|\.vpce\.amazonaws\.com|privatelink',
    re.IGNORECASE,
)
_RE_S3_ENDPOINT = re.compile(
    r's3[.-][a-z0-9-]+\.amazonaws\.com|s3\.amazonaws\.com',
    re.IGNORECASE,
)


def _parse_dns(text: str) -> dict:
    dns: dict = {
        "status": None,
        "resolved_ips": [],
        "nxdomain": False,
        "servfail": False,
        "query_time_ms": None,
        "cname_chain": [],
    }
    m = _RE_DIG_STATUS.search(text)
    if m:
        dns["status"] = m.group(1).upper()

    dns["nxdomain"] = bool(_RE_DIG_NXDOMAIN.search(text))
    dns["servfail"] = bool(_RE_DIG_SERVFAIL.search(text))

    for m in _RE_DIG_A_RECORD.finditer(text):
        record_type = m.group(2).upper()
        value = m.group(3)
        if record_type in ("A", "AAAA"):
            if value not in dns["resolved_ips"]:
                dns["resolved_ips"].append(value)
        elif record_type == "CNAME":
            if value not in dns["cname_chain"]:
                dns["cname_chain"].append(value)

    m = _RE_DIG_TIME.search(text)
    if m:
        dns["query_time_ms"] = int(m.group(1))

    return dns


def _parse_tls(text: str) -> dict:
    tls: dict = {
        "error": None,
        "cert_common_name": None,
        "verified": True,
    }
    if _RE_CURL_TLS_ERROR.search(text):
        tls["verified"] = False
        # Extract specific error
        for pattern in [
            r'(SSL certificate problem[^\n]+)',
            r'(certificate verify failed[^\n]+)',
            r'(SSL handshake fail[^\n]+)',
            r'(unable to get local issuer certificate)',
            r'(self.signed certificate)',
        ]:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                tls["error"] = m.group(1).strip()
                break

    m = _RE_CURL_TLS_CERT_CN.search(text)
    if m:
        tls["cert_common_name"] = m.group(1).strip()
    return tls


def _parse_tcp(text: str) -> dict:
    tcp: dict = {
        "connected": None,
        "refused": False,
        "timed_out": False,
        "http_status": None,
        "redirect_location": None,
        "server_header": None,
        "timing": {},
    }
    tcp["refused"] = bool(_RE_CURL_CONNECT_REFUSED.search(text))
    tcp["timed_out"] = bool(_RE_CURL_TIMEOUT.search(text))

    if tcp["refused"] or tcp["timed_out"]:
        tcp["connected"] = False
    else:
        statuses = _RE_CURL_HTTP_STATUS.findall(text)
        if statuses:
            tcp["connected"] = True
            tcp["http_status"] = int(statuses[-1])

    m = _RE_CURL_LOCATION.search(text)
    if m:
        tcp["redirect_location"] = m.group(1).strip()
    m = _RE_CURL_SERVER_HEADER.search(text)
    if m:
        tcp["server_header"] = m.group(1).strip()

    for name, pattern in [
        ("total_s", _RE_CURL_TOTAL_TIME),
        ("connect_s", _RE_CURL_CONNECT_TIME),
        ("tls_s", _RE_CURL_TLS_TIME),
    ]:
        m = pattern.search(text)
        if m:
            tcp["timing"][name] = float(m.group(1))

    return tcp


def _parse_latency(text: str) -> dict:
    lat: dict = {
        "min_ms": None,
        "avg_ms": None,
        "max_ms": None,
        "packet_loss_pct": None,
        "host_unreachable": False,
    }
    m = _RE_PING_RTT.search(text)
    if m:
        lat["min_ms"] = float(m.group(1))
        lat["avg_ms"] = float(m.group(2))
        lat["max_ms"] = float(m.group(3))
    m = _RE_PING_LOSS.search(text)
    if m:
        lat["packet_loss_pct"] = float(m.group(1))
    lat["host_unreachable"] = bool(_RE_PING_HOST_UNREACHABLE.search(text))
    return lat


def _parse_hops(text: str) -> list:
    hops = []
    for m in _RE_MTR_HOP.finditer(text):
        hops.append({
            "hop": int(m.group(1)),
            "host": m.group(2),
            "loss_pct": float(m.group(3)),
            "avg_ms": float(m.group(4)),
        })
    if not hops:
        for m in _RE_TRACEROUTE_HOP.finditer(text):
            hops.append({
                "hop": int(m.group(1)),
                "host": m.group(3),
                "loss_pct": None,
                "avg_ms": float(m.group(4)),
            })
    return hops[:20]


def parse(text: str) -> dict:
    """
    Parse network diagnostic output (dig, curl -v, ping, mtr/traceroute).

    Returns:
        {
            "endpoint": str | None,
            "is_vpc_endpoint": bool,
            "is_s3_endpoint": bool,
            "dns": {"status", "resolved_ips", "nxdomain", "servfail", "query_time_ms"},
            "tcp": {"connected", "refused", "timed_out", "http_status", "timing"},
            "tls": {"error", "cert_common_name", "verified"},
            "latency": {"min_ms", "avg_ms", "max_ms", "packet_loss_pct"},
            "hops": [{"hop", "host", "loss_pct", "avg_ms"}],
            "summary": {"error_count": int, "root_cause_hint": str}
        }
    """
    dns = _parse_dns(text)
    tcp = _parse_tcp(text)
    tls = _parse_tls(text)
    latency = _parse_latency(text)
    hops = _parse_hops(text)

    # Extract primary endpoint
    endpoint = None
    m = _RE_ENDPOINT_URL.search(text)
    if m:
        endpoint = m.group(1)

    is_vpc = bool(_RE_VPC_ENDPOINT.search(text))
    is_s3 = bool(_RE_S3_ENDPOINT.search(text))

    # Root cause hint
    hint = "unknown"
    error_count = 0
    if dns["nxdomain"]:
        hint = "dns_nxdomain"
        error_count += 1
    elif dns["servfail"]:
        hint = "dns_servfail"
        error_count += 1
    elif not tls["verified"] and tls["error"]:
        hint = "tls_certificate_error"
        error_count += 1
    elif tcp["refused"]:
        hint = "tcp_connection_refused"
        error_count += 1
    elif tcp["timed_out"]:
        hint = "tcp_timeout"
        error_count += 1
    elif latency["host_unreachable"]:
        hint = "host_unreachable"
        error_count += 1
    elif latency["packet_loss_pct"] is not None and latency["packet_loss_pct"] > 0:
        hint = "packet_loss"
        error_count += 1
    elif tcp["http_status"] == 403:
        hint = "http_403_access_denied"
        error_count += 1
    elif tcp["http_status"] is not None and tcp["http_status"] < 400:
        hint = "connectivity_ok"

    return {
        "endpoint": endpoint,
        "is_vpc_endpoint": is_vpc,
        "is_s3_endpoint": is_s3,
        "dns": dns,
        "tcp": tcp,
        "tls": tls,
        "latency": latency,
        "hops": hops,
        "summary": {
            "error_count": error_count,
            "root_cause_hint": hint,
        },
    }


def main():
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    else:
        text = sys.stdin.read()
    print(json.dumps(parse(text), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
