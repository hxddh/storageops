"""Analyzer for network diagnostic parsed output (from parse_network_diagnostics)."""
from __future__ import annotations


def analyze(parsed: dict) -> dict:
    """
    Analyze parsed network diagnostic output and return diagnosis with recommendations.

    Args:
        parsed: Output of parse_network_diagnostics.parse()

    Returns:
        {
            "root_cause": str,
            "severity": str,  # critical | high | medium | low | ok
            "confidence": float,
            "findings": [{"code": str, "detail": str, "severity": str}],
            "recommendations": [{"action": str, "command": str | None, "manual_only": bool}],
            "endpoint_type": str,  # public_s3 | vpc_endpoint | other
        }
    """
    dns = parsed.get("dns", {})
    tcp = parsed.get("tcp", {})
    tls = parsed.get("tls", {})
    latency = parsed.get("latency", {})
    hops = parsed.get("hops", [])
    summary = parsed.get("summary", {})
    is_vpc = parsed.get("is_vpc_endpoint", False)
    is_s3 = parsed.get("is_s3_endpoint", False)
    endpoint = parsed.get("endpoint")

    hint = summary.get("root_cause_hint", "unknown")
    findings = []
    recommendations = []

    if is_vpc:
        endpoint_type = "vpc_endpoint"
    elif is_s3:
        endpoint_type = "public_s3"
    else:
        endpoint_type = "other"

    # DNS failures
    if dns.get("nxdomain"):
        findings.append({
            "code": "DNS_NXDOMAIN",
            "detail": f"DNS lookup returned NXDOMAIN for {endpoint or 'target host'}. "
                      "The hostname does not exist or is not resolvable from this network.",
            "severity": "critical",
        })
        if is_vpc:
            recommendations.append({
                "action": "Verify that a VPC endpoint for S3 exists in the region and that "
                          "the private DNS name is enabled on the endpoint.",
                "command": "aws ec2 describe-vpc-endpoints --filters Name=service-name,"
                           "Values=com.amazonaws.<region>.s3 --query "
                           "'VpcEndpoints[*].{Id:VpcEndpointId,DNS:DnsEntries}'",
                "manual_only": True,
            })
        else:
            recommendations.append({
                "action": "Check that the bucket name is correct and the region-specific "
                          "endpoint is used (e.g., s3.<region>.amazonaws.com).",
                "command": None,
                "manual_only": False,
            })

    elif dns.get("servfail"):
        findings.append({
            "code": "DNS_SERVFAIL",
            "detail": "DNS server returned SERVFAIL. The resolver could not complete the lookup.",
            "severity": "high",
        })
        recommendations.append({
            "action": "Check DNS resolver configuration in /etc/resolv.conf. "
                      "If inside a VPC, confirm the Amazon-provided DNS (169.254.169.253) is reachable.",
            "command": "cat /etc/resolv.conf",
            "manual_only": False,
        })

    # TLS errors
    if not tls.get("verified", True) and tls.get("error"):
        findings.append({
            "code": "TLS_CERT_ERROR",
            "detail": f"TLS certificate verification failed: {tls['error']}",
            "severity": "critical",
        })
        recommendations.append({
            "action": "Check the system CA bundle and ensure it is up to date. "
                      "If using a custom endpoint, verify the certificate chain.",
            "command": "curl -v --cacert /etc/ssl/certs/ca-certificates.crt "
                       f"https://{endpoint or '<endpoint>'}/ 2>&1 | head -40",
            "manual_only": False,
        })
        if is_vpc:
            recommendations.append({
                "action": "For VPC endpoints, ensure the endpoint policy allows s3:GetObject "
                          "and the private DNS is not overriding the certificate CN.",
                "command": None,
                "manual_only": True,
            })

    # TCP connection failures
    if tcp.get("refused"):
        findings.append({
            "code": "TCP_CONNECTION_REFUSED",
            "detail": "TCP connection was actively refused by the remote host. "
                      "Port 443 (HTTPS) or 80 (HTTP) is not accepting connections.",
            "severity": "critical",
        })
        recommendations.append({
            "action": "Verify that the security group / NACL / firewall allows outbound TCP 443 "
                      "to the S3 endpoint. For VPC endpoints, check the endpoint's security group.",
            "command": "nc -zv <endpoint> 443",
            "manual_only": False,
        })

    elif tcp.get("timed_out"):
        findings.append({
            "code": "TCP_TIMEOUT",
            "detail": "TCP connection attempt timed out. The host may be unreachable or "
                      "traffic is being silently dropped by a firewall.",
            "severity": "high",
        })
        recommendations.append({
            "action": "Check security group rules for outbound TCP 443 to "
                      "prefix-list for S3 (com.amazonaws.<region>.s3). "
                      "Run a traceroute to identify where packets are dropped.",
            "command": "traceroute -T -p 443 <endpoint>",
            "manual_only": False,
        })

    # Latency / reachability
    if latency.get("host_unreachable"):
        findings.append({
            "code": "HOST_UNREACHABLE",
            "detail": "ICMP echo requests show the host is unreachable (100% packet loss or "
                      "'Destination Host Unreachable').",
            "severity": "high",
        })
        recommendations.append({
            "action": "Note: S3 endpoints may not respond to ICMP. Confirm via TCP (curl/nc) "
                      "rather than ping alone.",
            "command": f"curl -o /dev/null -s -w '%{{http_code}}' https://{endpoint or '<endpoint>'}/",
            "manual_only": False,
        })

    elif latency.get("packet_loss_pct") is not None and latency["packet_loss_pct"] > 5:
        loss = latency["packet_loss_pct"]
        sev = "high" if loss > 20 else "medium"
        findings.append({
            "code": "PACKET_LOSS",
            "detail": f"Packet loss detected: {loss:.1f}%. This may cause intermittent "
                      "connection errors and S3 request timeouts.",
            "severity": sev,
        })
        recommendations.append({
            "action": "Run mtr to identify which hop is dropping packets. "
                      "Contact network team if loss is on an internal segment.",
            "command": f"mtr --report --report-cycles 20 {endpoint or '<endpoint>'}",
            "manual_only": False,
        })

    # HTTP-level findings
    http_status = tcp.get("http_status")
    if http_status == 403:
        findings.append({
            "code": "HTTP_403_ACCESS_DENIED",
            "detail": "S3 returned HTTP 403 Access Denied. The network path is reachable but "
                      "the request is being rejected at the S3 policy layer.",
            "severity": "medium",
        })
        recommendations.append({
            "action": "Check the bucket policy, IAM policy, and S3 Block Public Access settings. "
                      "For VPC endpoints, verify the endpoint policy grants s3:GetObject.",
            "command": "aws s3api get-bucket-policy --bucket <bucket>",
            "manual_only": True,
        })

    # Routing hop analysis — detect early asymmetric drop
    if hops:
        last_hop = hops[-1]
        if last_hop.get("loss_pct") is not None and last_hop["loss_pct"] == 100:
            findings.append({
                "code": "TRACEROUTE_FINAL_HOP_LOSS",
                "detail": f"Final traceroute hop ({last_hop['host']}) shows 100% loss. "
                          "This is expected for S3 if ICMP is filtered, but may indicate "
                          "a routing black-hole.",
                "severity": "low",
            })

    # VPC endpoint-specific guidance
    if is_vpc and not findings:
        findings.append({
            "code": "VPC_ENDPOINT_REACHABLE",
            "detail": "VPC endpoint appears reachable. Connectivity looks healthy.",
            "severity": "info",
        })

    # High latency warning
    avg_ms = latency.get("avg_ms")
    if avg_ms is not None and avg_ms > 200:
        findings.append({
            "code": "HIGH_LATENCY",
            "detail": f"Average round-trip latency is {avg_ms:.1f} ms. "
                      "This may indicate cross-region traffic or network congestion.",
            "severity": "medium",
        })
        recommendations.append({
            "action": "Confirm the S3 bucket region matches the client region. "
                      "Cross-region S3 traffic incurs additional latency and data transfer charges.",
            "command": "aws s3api get-bucket-location --bucket <bucket>",
            "manual_only": True,
        })

    # Determine overall severity and confidence
    sev_order = ["critical", "high", "medium", "low", "info", "ok"]
    overall_sev = "ok"
    for f in findings:
        f_sev = f.get("severity", "info")
        if sev_order.index(f_sev) < sev_order.index(overall_sev):
            overall_sev = f_sev

    # Root cause mapping
    root_cause_map = {
        "dns_nxdomain": "DNS resolution failure — hostname not found",
        "dns_servfail": "DNS server failure — resolver could not complete lookup",
        "tls_certificate_error": "TLS certificate verification failure",
        "tcp_connection_refused": "TCP connection refused — port not open or firewall blocking",
        "tcp_timeout": "TCP connection timeout — traffic silently dropped",
        "host_unreachable": "Host unreachable — ICMP filtered or routing failure",
        "packet_loss": "Packet loss detected — network instability",
        "http_403_access_denied": "HTTP 403 — network OK but S3 access denied",
        "connectivity_ok": "No network issues detected",
        "unknown": "No specific network issue identified",
    }
    root_cause = root_cause_map.get(hint, hint)

    confidence_map = {
        "dns_nxdomain": 0.95,
        "dns_servfail": 0.90,
        "tls_certificate_error": 0.92,
        "tcp_connection_refused": 0.95,
        "tcp_timeout": 0.85,
        "host_unreachable": 0.80,
        "packet_loss": 0.80,
        "http_403_access_denied": 0.85,
        "connectivity_ok": 0.90,
        "unknown": 0.40,
    }
    confidence = confidence_map.get(hint, 0.50)

    if overall_sev == "ok" and hint == "unknown":
        overall_sev = "low"

    return {
        "root_cause": root_cause,
        "severity": overall_sev,
        "confidence": confidence,
        "findings": findings,
        "recommendations": recommendations,
        "endpoint_type": endpoint_type,
    }
