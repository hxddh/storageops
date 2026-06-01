#!/usr/bin/env python3
"""Run read-only DNS/TCP/TLS/HTTP reachability checks for one endpoint."""

from __future__ import annotations

import argparse
import http.client
import json
import socket
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass
class Endpoint:
    url: str
    scheme: str
    host: str
    port: int
    path: str


def parse_endpoint(raw: str) -> Endpoint:
    value = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(value)
    if not parsed.hostname:
        raise ValueError(f"invalid endpoint URL: {raw}")
    scheme = parsed.scheme or "https"
    if scheme not in {"http", "https"}:
        raise ValueError(f"unsupported scheme {scheme!r}; use http or https")
    port = parsed.port or (443 if scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return Endpoint(url=value, scheme=scheme, host=parsed.hostname, port=port, path=path)


def _step(ok: bool, **extra: Any) -> dict[str, Any]:
    return {"ok": ok, **extra}


def check_dns(endpoint: Endpoint, family: int = socket.AF_UNSPEC) -> dict[str, Any]:
    started = time.monotonic()
    try:
        records = socket.getaddrinfo(endpoint.host, endpoint.port, family, socket.SOCK_STREAM)
    except OSError as exc:
        return _step(False, error=str(exc), elapsed_ms=round((time.monotonic() - started) * 1000, 1), addresses=[])
    addresses = []
    for record in records:
        sockaddr = record[4]
        address = sockaddr[0]
        if address not in addresses:
            addresses.append(address)
    return _step(True, elapsed_ms=round((time.monotonic() - started) * 1000, 1), addresses=addresses)


def check_tcp(endpoint: Endpoint, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=timeout):
            pass
    except OSError as exc:
        return _step(False, error=str(exc), elapsed_ms=round((time.monotonic() - started) * 1000, 1))
    return _step(True, elapsed_ms=round((time.monotonic() - started) * 1000, 1))


def check_tls(endpoint: Endpoint, timeout: float, verify: bool) -> dict[str, Any]:
    if endpoint.scheme != "https":
        return _step(True, skipped=True, reason="non-HTTPS endpoint")
    started = time.monotonic()
    context = ssl.create_default_context() if verify else ssl._create_unverified_context()
    try:
        with socket.create_connection((endpoint.host, endpoint.port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=endpoint.host) as tls:
                cert = tls.getpeercert() or {}
                version = tls.version()
                cipher = tls.cipher()
    except (OSError, ssl.SSLError) as exc:
        return _step(False, error=str(exc), elapsed_ms=round((time.monotonic() - started) * 1000, 1))
    return _step(
        True,
        elapsed_ms=round((time.monotonic() - started) * 1000, 1),
        tls_version=version,
        cipher=cipher[0] if cipher else None,
        subject=cert.get("subject"),
        not_after=cert.get("notAfter"),
    )


def check_http_head(endpoint: Endpoint, timeout: float, verify: bool) -> dict[str, Any]:
    started = time.monotonic()
    connection_cls = http.client.HTTPSConnection if endpoint.scheme == "https" else http.client.HTTPConnection
    kwargs: dict[str, Any] = {"timeout": timeout}
    if endpoint.scheme == "https" and not verify:
        kwargs["context"] = ssl._create_unverified_context()
    try:
        conn = connection_cls(endpoint.host, endpoint.port, **kwargs)
        conn.request("HEAD", endpoint.path, headers={"User-Agent": "storageops-endpoint-check/1"})
        response = conn.getresponse()
        response.read()
        conn.close()
    except Exception as exc:  # http.client can raise several protocol exceptions.
        return _step(False, error=str(exc), elapsed_ms=round((time.monotonic() - started) * 1000, 1))
    return _step(True, elapsed_ms=round((time.monotonic() - started) * 1000, 1), status=response.status, reason=response.reason)


def classify_failure(results: dict[str, Any]) -> str:
    checks = results["checks"]
    if not checks["dns"]["ok"]:
        return "DNS"
    if not checks["tcp"]["ok"]:
        return "TCP"
    if not checks["tls"]["ok"]:
        return "TLS"
    if not checks["http_head"]["ok"]:
        return "HTTP"
    status = checks["http_head"].get("status")
    if isinstance(status, int) and status in {400, 401, 403, 404}:
        return "application"
    return "reachable"


def run_checks(endpoint: Endpoint, timeout: float, verify_tls: bool, skip_http: bool = False) -> dict[str, Any]:
    checks = {
        "dns": check_dns(endpoint),
        "tcp": check_tcp(endpoint, timeout),
        "tls": check_tls(endpoint, timeout, verify_tls),
        "http_head": _step(True, skipped=True, reason="disabled") if skip_http else check_http_head(endpoint, timeout, verify_tls),
    }
    result = {
        "endpoint": {"url": endpoint.url, "scheme": endpoint.scheme, "host": endpoint.host, "port": endpoint.port, "path": endpoint.path},
        "checks": checks,
    }
    result["classification"] = classify_failure(result)
    result["ok"] = result["classification"] in {"reachable", "application"}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("endpoint", help="Endpoint URL or hostname; https:// is assumed if omitted")
    parser.add_argument("--timeout", type=float, default=5.0, help="Per-step timeout in seconds")
    parser.add_argument("--no-verify", action="store_true", help="Disable TLS certificate verification for diagnostics only")
    parser.add_argument("--skip-http", action="store_true", help="Only run DNS/TCP/TLS checks")
    parser.add_argument("--json-out", type=Path, help="Write JSON report to this path")
    args = parser.parse_args()

    endpoint = parse_endpoint(args.endpoint)
    result = run_checks(endpoint, args.timeout, not args.no_verify, args.skip_http)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.json_out:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
