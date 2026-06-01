# TLS, MTU, and RTT

## TLS Handshake

### TLS 1.3 (Preferred)
```
Client → Server: ClientHello (1 RTT)
Server → Client: ServerHello + Certificate + Finished
Client → Server: Finished
Application Data: after 1 RTT
```

With 0-RTT (early data):
```
Client → Server: ClientHello + Early Application Data (0 RTT)
```

### TLS 1.2
```
Client → Server: ClientHello
Server → Client: ServerHello + Certificate
Client → Server: ClientKeyExchange + ChangeCipherSpec + Finished
Server → Client: ChangeCipherSpec + Finished
Application Data: after 2 RTTs
```

### TLS Configuration Check
```bash
# Check supported TLS versions and ciphers
openssl s_client -connect <endpoint>:443 -servername <endpoint> </dev/null 2>&1 | grep -E "Protocol|Cipher"

# Full certificate chain
echo | openssl s_client -connect <endpoint>:443 -showcerts 2>&1
```

### Common TLS Issues

1. **TLS version mismatch:** Client uses TLS 1.0, server requires TLS 1.2+.
2. **Certificate expiry:** Check `notBefore` and `notAfter`.
3. **Hostname mismatch:** Certificate CN/SAN does not match the endpoint hostname.
   - Common with virtual-hosted-style: `bucket.endpoint.com` but certificate is for `*.endpoint.com` (the wildcard must be at the correct level).
4. **Untrusted CA:** Self-signed or internal CA certificate not in trust store.
   - S3-compatible providers may use non-public CAs.
   - Fix: Add CA certificate to trust store (do NOT use `--no-verify-ssl` in production).
5. **TLS inspection proxy:** Transparent proxy presents its own certificate.

### Session Resumption
- Session IDs or session tickets can reduce TLS handshake from 1-2 RTTs to 0 RTT.
- Important for high-frequency small requests.
- Check if endpoint supports resumption:
```bash
openssl s_client -connect <endpoint>:443 -reconnect 2>&1 | grep "Reused"
```

## MTU (Maximum Transmission Unit)

### Standard MTU
- Ethernet: 1500 bytes.
- Jumbo frames: 9000 bytes (within same network/VPC).
- Internet: Typically 1500, often less with tunnels (VPN, GRE: ~1400-1460).

### Path MTU Discovery
```bash
# Find max MTU to endpoint
ping -M do -s <size> <endpoint-hostname>
# Start at 1472 (1500 - 20 IP - 8 ICMP) and decrease until it works.
```

### MTU Issues with Object Storage
- **Large headers:** SigV4 Authorization header can be 500+ bytes.
- **Large requests:** Multipart Upload XML can be large for many parts.
- **MTU too small → fragmentation → performance degradation.**
- **MTU too large → "packet too big" → silent drops if ICMP blocked.**

### Symptom of MTU Issue
- Small requests (HEAD, GET small object) succeed.
- Large requests (PUT large object, multipart complete) hang or timeout.
- TLS handshake succeeds but data transfer fails.

## RTT (Round Trip Time)

### Measurement
```bash
ping -c 10 <endpoint-hostname>
mtr -r -c 10 <endpoint-hostname>
```

### Typical RTT Ranges
| Scenario | RTT |
|---|---|
| Same VPC, same AZ | <1ms |
| Same VPC, different AZ | 1–3ms |
| Same region, public | 5–20ms |
| Cross-region | 20–100ms |
| Cross-cloud (same country) | 10–50ms |
| Cross-cloud (different country) | 100–300ms |
| Trans-oceanic | 100–400ms |

### RTT Impact on Object Storage Performance
- Each metadata operation (stat/HeadObject) costs at least 1 RTT.
- Single small file upload: DNS + TCP + TLS + Request + Transfer ≈ 4+ RTTs.
- At 100ms RTT: ~400ms minimum per small file.
- At 5ms RTT: ~20ms minimum per small file.
- **20× difference from RTT alone.**

## Combined Analysis

For each endpoint, calculate:
```
Minimum First-Request Latency = DNS + TCP (1 RTT) + TLS (1-2 RTT) + HTTP (0.5 RTT)
                                = DNS + 2.5-3.5 RTT
```
This is the absolute minimum for the FIRST request to a new connection.
Subsequent requests on the same connection save TCP + TLS cost.
