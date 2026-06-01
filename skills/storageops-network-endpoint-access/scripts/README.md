# storageops-network-endpoint-access Scripts

## `endpoint_reachability_test.py`

Given an endpoint URL, perform a systematic read-only reachability check:
1. DNS resolution (A, AAAA, CNAME).
2. TCP connect on port 443.
3. TLS handshake and certificate validation.
4. HTTP HEAD request.
5. Report pass/fail at each layer.

```bash
./endpoint_reachability_test.py https://s3.example.com --json-out endpoint-check.json
./endpoint_reachability_test.py bucket.s3.example.com --skip-http
```

Use only for endpoints the user is authorized to test. The script does not send credentials or mutate data.

## Planned Scripts

### `rtt_analyzer.py`
Given ping/mtr output for multiple endpoints or time periods:
- Compute min/avg/max/P95 RTT.
- Detect RTT anomalies (spikes, degradation).
- Compare RTT between different access paths.

### `dns_host_header_validator.py`
Given an endpoint hostname and bucket name:
- Test DNS resolution for `endpoint.com`.
- Test DNS resolution for `bucket.endpoint.com`.
- Test DNS resolution for `bucket.s3-region.endpoint.com`.
- Report which access styles (path, virtual-hosted) are likely supported.

### `mtu_discovery.sh`
Perform path MTU discovery to an endpoint:
- Binary search for maximum packet size that doesn't fragment.
- Report recommended MTU and potential fragmentation issues.

### `cross_cloud_path_analyzer.py`
Given traceroute/mtr from two different source locations:
- Compare hop counts, latencies, and paths.
- Identify whether traffic routes over internet or dedicated line.
- Detect asymmetric routing.

## Principles

- All scripts perform read-only network diagnostics.
- No active probing beyond standard ICMP/DNS/TCP/TLS.
- Scripts should not be used for unauthorized network scanning.
- `traceroute` and `mtr` options: use `-n` to avoid reverse DNS lookups (faster, less noise).
