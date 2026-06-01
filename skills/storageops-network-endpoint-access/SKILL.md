---
name: storageops-network-endpoint-access
description: >
  Diagnose network connectivity issues to object storage endpoints. Covers DNS
  resolution failures (including virtual-hosted style), TCP connection timeouts,
  TLS/SSL handshake errors, proxy interference, MTU/fragmentation, VPC
  endpoint configuration, and cross-cloud dedicated line issues. Use when user
  reports connection refused, timeout, DNS errors, or SSL errors to S3 endpoints.
maturity: core
mode: light_heavy
estimated_tokens: 1300
trigger_keywords:
  - connection refused
  - connection timeout
  - DNS resolution
  - name resolution
  - TLS error
  - SSL error
  - certificate error
  - endpoint unreachable
  - VPC endpoint
  - PrivateLink
  - proxy error
  - NameResolutionError
recommended_tools:
  - scan_secrets
  - detect_domain
  - search_memory
---

# Network & Endpoint Access Diagnosis

Isolate the failing network layer: DNS → TCP → TLS → HTTP → Application. Most object storage connectivity issues are DNS configuration or TLS certificate mismatches.

## Decision Tree

```
Connectivity issue →
  ├─ "Name or service not known" / DNS error? → DNS layer
  │   ├─ Virtual-hosted style URL (bucket.endpoint.com)? → DNS CNAME check (Step 2)
  │   ├─ Custom endpoint? → Custom DNS or /etc/hosts
  │   └─ VPC endpoint? → Private DNS for VPC endpoint (Step 5)
  ├─ "Connection refused"?
  │   ├─ Wrong port? → S3 HTTPS is 443; check for HTTP(80) fallback
  │   └─ Firewall/security group? → Check outbound rules
  ├─ "Connection timeout"?
  │   ├─ Public endpoint from private subnet? → Need NAT gateway or VPC endpoint
  │   ├─ Cross-region? → Latency + firewall egress
  │   └─ Intermittent? → MTU black hole or proxy timeout (Step 4)
  ├─ "TLS/SSL error"?
  │   ├─ Certificate name mismatch? → SNI or endpoint URL mismatch
  │   ├─ Self-signed certificate? → install the correct CA cert bundle; do not disable verification
  │   └─ Expired certificate? → Check server cert validity
  └─ "HTTP 400/403 after connection"? → Not network — route to triage
```

## Workflow

### Step 1: Classify the Endpoint
Public endpoint, VPC endpoint (gateway/interface), PrivateLink endpoint, or custom endpoint (on-prem). The endpoint type determines the available diagnostic tools.

### Step 2: DNS Resolution Check
- **Virtual-hosted style**: `bucket.s3.region.amazonaws.com` — requires DNS CNAME support
- **Path-style**: `s3.region.amazonaws.com/bucket` — always works, no DNS dependency
- **VPC endpoint DNS**: Requires `enableDnsHostnames=true` and `enableDnsSupport=true` on VPC
- Non-AWS providers may NOT support virtual-hosted style (BOS, early OSS)

### Step 3: Basic Connectivity
What the user can test. If the user provides an endpoint and wants an active check from this machine, use `scripts/endpoint_reachability_test.py`; otherwise suggest equivalent commands:
```bash
# DNS resolution test
nslookup <endpoint>
# TCP connectivity (HTTPS)
curl -v --connect-timeout 5 https://<endpoint> 2>&1 | head -20
# Timing breakdown
curl -w "DNS: %{time_namelookup}s TCP: %{time_connect}s TLS: %{time_appconnect}s Total: %{time_total}s" -o /dev/null -s https://<endpoint>
```

### Step 4: Path Analysis
- **MTU**: Check if path MTU discovery is working (ICMP "fragmentation needed" may be blocked)
- **Proxy**: Check `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` env vars — proxy may strip Authorization header
- **Firewall**: Deep packet inspection may block S3 API calls on non-standard ports

### Step 5: Advanced Patterns
- **VPC endpoint**: Check endpoint policy, security group allows 443→endpoint, route table entry
- **PrivateLink**: Ensure endpoint is `accepted` (not `pendingAcceptance`)
- **Cross-cloud**: Dedicated line (ExpressRoute/FastConnect), check BGP, MTU 1500 vs 9001

### Step 6: Feedback Loop
If DNS/TCP checks are inconclusive, ask the user to run a timing diagnostic: **"Run `curl -w 'DNS: %{time_namelookup}s TCP: %{time_connect}s TLS: %{time_appconnect}s Total: %{time_total}s' -o /dev/null -s https://<endpoint>` and share the results."** This breaks down latency by network layer (DNS, TCP, TLS). If timeout is the issue: **"Test with `nc -zv -w 5 <endpoint> 443` or `python3 scripts/endpoint_reachability_test.py https://<endpoint> --skip-http` to check basic reachability."** If confidence < medium, go back to Step 1 and reclassify the endpoint type.

## User Interaction

### When to ask the user:
- **"What endpoint URL are you using (virtual-hosted style `bucket.endpoint.com` or path-style `endpoint.com/bucket`)?"** — DNS and URL format are the root cause of most connectivity issues
- **"Are you on a public subnet, private subnet, or behind a corporate proxy?"** — determines available diagnostic paths
- **"Can you run `curl -v --connect-timeout 5 https://<endpoint> 2>&1 | head -30` and share the output?"** — raw HTTPS output reveals the failing layer

### When to inform the user:
- **"If you're on a private subnet, you MUST use a VPC endpoint or NAT gateway to reach public S3 endpoints."**
- **"Path-style URLs always work. Virtual-hosted style requires DNS and may not be supported by all providers."**

## Output Format — ALWAYS use this exact template

```markdown
# Diagnosis: [one-line]
**Layer**: DNS | TCP | TLS | proxy | MTU | VPC-endpoint
**Confidence**: high | medium | low

## Evidence
- Endpoint: [sanitized URL]
- Error: [exact error message]
- Environment: [public/private subnet, VPC endpoint details]

## Root Cause
[Which network layer and why]

## Recommendations
1. **[fix]** (manual-only) — [specific network change]
2. **[diagnostic command]** — [to verify the fix]
```

## Examples

### Example 1: Virtual-hosted style fails on BOS
**Input**: `https://my-bucket.s3.bj.bcebos.com/` → `NameResolutionError`.
**Diagnosis**: BOS doesn't support virtual-hosted style for custom endpoints. DNS has no record for `my-bucket.s3.bj.bcebos.com`.
**Recommendation**: Use path-style: `https://s3.bj.bcebos.com/my-bucket/`. Set SDK config to `s3ForcePathStyle=true`.

### Example 2: Private subnet → public endpoint timeout
**Input**: EC2 in private subnet, `aws s3 ls` times out after 60s.
**Diagnosis**: Private subnet has no route to internet (no NAT gateway). S3 public endpoint unreachable.
**Recommendation**: Option A: Create S3 VPC Gateway Endpoint (free, preferred). Option B: Add NAT gateway (costs + data transfer).

### Example 3: Proxy stripping Authorization header
**Input**: curl through corporate proxy. Error: `AccessDenied: No AWS authentication`.
**Diagnosis**: Proxy is stripping/mangling the `Authorization` header. Some proxies treat `Authorization` as sensitive and remove it.
**Recommendation**: Add S3 endpoint to `NO_PROXY`. Or configure proxy to pass-through Authorization header.

## References
- `scripts/endpoint_reachability_test.py` — Read-only DNS/TCP/TLS/HTTP HEAD checker | **Read when:** user asks for an active endpoint check or provides a URL to test from this environment
- `references/dns-host-header.md` — Virtual-hosted vs path-style, provider support matrix | **Read when:** user reports DNS errors, NameResolutionError, or endpoint URL construction issues
- `references/tls-mtu-rtt.md` — TLS SNI, CA bundles, certificate validation | **Read when:** user reports TLS/SSL/certificate errors
- `references/private-access.md` — VPC endpoint configuration and troubleshooting | **Read when:** user mentions VPC endpoints, private subnets, or PrivateLink
- `references/endpoint-routing.md` — Proxy interference patterns | **Read when:** user is behind a corporate proxy or reports proxy-related errors
- `references/tls-mtu-rtt.md` — MTU and fragmentation analysis | **Read when:** user reports intermittent timeouts or MTU-related issues
- `references/cross-cloud-dedicated-line.md` — FastConnect/ExpressRoute diagnostics | **Read when:** user mentions cross-cloud dedicated lines, ExpressRoute, or FastConnect
