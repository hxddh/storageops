# DNS and Host Header

## DNS Resolution

### Basic Resolution
```bash
dig <endpoint-hostname>
nslookup <endpoint-hostname>
host <endpoint-hostname>
```

Key outputs:
- **A record:** IPv4 address.
- **AAAA record:** IPv6 address.
- **CNAME:** Alias (follow the chain).
- **TTL:** How long is this record cached?
- **Response time:** How fast is DNS resolution?

### DNS Resolution Time
DNS resolution time can be a significant component of first-request latency:
- Uncached: 10–200ms (depends on resolver proximity).
- Cached: <1ms (OS or application cache).

### Common DNS Issues

1. **No resolution:** NXDOMAIN or SERVFAIL.
   - Wrong hostname.
   - DNS server unreachable.
   - Custom DNS configuration issue.

2. **Resolves to wrong IP:** Public IP when expecting private, or vice versa.
   - Split DNS not configured correctly.
   - `/etc/hosts` has stale entries.
   - DNS cache poisoning (rare).

3. **Slow resolution:** > 100ms consistently.
   - DNS server far away or overloaded.
   - Too many CNAME hops.

4. **IPv6 vs IPv4:** Resolving to IPv6 when IPv4 expected (or network doesn't support IPv6).
   - Try forcing IPv4: `curl -4 ...`.

## Path-Style vs Virtual-Hosted-Style and DNS

### Path-Style
```
GET /bucket/key HTTP/1.1
Host: s3.example.com
```
- DNS resolves `s3.example.com`.
- Bucket name is in the URL path, not the Host header.
- No DNS requirement for bucket name.

### Virtual-Hosted-Style
```
GET /key HTTP/1.1
Host: bucket.s3.example.com
```
- DNS must resolve `bucket.s3.example.com`.
- Bucket name must be a valid DNS label.
- Wildcard DNS record required: `*.s3.example.com`.

### DNS Requirement for Virtual-Hosted-Style
If the DNS for `s3.example.com` does not include a wildcard:
```
dig bucket.s3.example.com  # FAILS
```
Virtual-hosted-style will fail with "Name or service not known" or "Connection refused".

Solutions:
1. Add wildcard DNS: `*.s3.example.com IN A <ip>`.
2. Add individual DNS records per bucket.
3. Use path-style instead (if provider supports it).

## Host Header

The `Host` header in the HTTP request is critical for S3 routing:
- **Path-style:** `Host: <endpoint-host>`.
- **Virtual-hosted-style:** `Host: <bucket>.<endpoint-host>`.

### Host Header Mismatch
If the client sends `Host: bucket.s3.example.com` but the server expects `Host: s3.example.com`:
- Server may return 404 (NoSuchBucket).
- Server may return 400 (Bad Request).
- Server may return 403 (AccessDenied, misinterpreted).

### Proxy and Host Header
- Proxies may modify the Host header.
- Load balancers may rewrite the Host header.
- Check if proxy preserves the original Host header.

## DNS Caching Considerations

- TTL values control DNS caching duration.
- For S3-compatible endpoints with dynamic IP addresses: low TTL.
- Negative caching: NXDOMAIN results may be cached for minutes to hours.
