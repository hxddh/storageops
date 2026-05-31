# Throughput Modeling

## Latency Components

Total time for an object storage operation = sum of:

```
Total = DNS + TCP_Connect + TLS_Handshake + HTTP_Request + Server_Processing + Transfer + Ack
```

### DNS Lookup
- Cost: 0–50ms (cached vs uncached).
- One-time per connection (or per request without pooling).
- Mitigation: DNS caching, connection pooling.

### TCP Connect (SYN/SYN-ACK/ACK)
- Cost: 1 RTT.
- One-time per connection.
- Mitigation: Connection pooling, keep-alive.

### TLS Handshake
- Cost: 1–2 RTTs (TLS 1.3: 1 RTT; TLS 1.2: 2 RTTs).
- One-time per connection.
- Mitigation: TLS session resumption (0-RTT with TLS 1.3 early data).

### HTTP Request
- Cost: 0.5 RTT (request sent, waiting for response).
- Per operation.
- Mitigation: Pipelining (HTTP/1.1), multiplexing (HTTP/2, HTTP/3).

### Server Processing
- Cost: Variable. Simple Key→Value: <1ms. Complex operations: 100ms+.
- Per operation.
- Mitigation: None client-side.

### Transfer
- Cost: Object size / available bandwidth.
- Dominates for large objects.
- Mitigation: Multipart parallelization, TCP tuning.

## Throughput Models

### Single Large Object (Upload)
```
Throughput = ObjectSize / (Overhead + TransferTime)
Overhead = DNS + TCP + TLS + HTTP + ServerStart
TransferTime = ObjectSize / SingleConnectionBandwidth
```

### Multiple Small Objects
```
Throughput = Objects × AvgObjectSize / TotalTime
TotalTime ≈ Objects × (PerOpOverhead + AvgObjectSize / Bandwidth)
PerOpOverhead → dominant for small objects
```

### Multipart Upload (N parts, C concurrent)
```
UploadTime ≈ Overhead + max(Part_i_Transfer) + (N/C - 1) × PartTransferTime
Ideal with no server delay: ≈ ObjectSize / (C × SingleConnectionBandwidth)
```

### Bandwidth-Delay Product (BDP)

The BDP determines how much data must be "in flight" to fully saturate a link:

```
BDP_bytes = Bandwidth_bps × RTT_sec / 8

Example:
  1 Gbps link, 50ms RTT
  BDP = 1,000,000,000 × 0.05 / 8 = 6,250,000 bytes ≈ 6 MB
  → At least 6 MB must be in flight at all times to fill the pipe.
```

### Optimal Concurrency Formula

Given BDP and part size, compute the concurrency needed to saturate the link:

```
optimal_concurrency = max(1, ceil(BDP_bytes / part_size_bytes))

Example:
  BDP = 6 MB, part_size = 5 MB (default rclone)
  optimal_concurrency = ceil(6 / 5) = 2
  → Only 2 concurrent parts needed to saturate a 1 Gbps, 50ms RTT link with 5MB parts.

  BDP = 6 MB, part_size = 8 MB (default awscli)
  optimal_concurrency = ceil(6 / 8) = 1
  → 1 concurrent part is enough; more concurrency just wastes resources.
```

**Concurrency ceiling:** Do not exceed the concurrency that triggers provider throttling.
Test with incremental concurrency: 1 → 2 → 4 → 8 → 16 → find 429 onset.

### RTT × Concurrency Interaction Table

| RTT | 1 Gbps BDP | Optimal Concurrency (64MB parts) | Optimal Concurrency (8MB parts) |
|-----|-----------|--------------------------------|-------------------------------|
| 1 ms | 125 KB | 1 | 1 |
| 10 ms | 1.25 MB | 1 | 1 |
| 50 ms | 6.25 MB | 1 | 1 |
| 100 ms | 12.5 MB | 1 | 2 |
| 200 ms | 25 MB | 1 | 4 |

**For cross-region/cross-cloud scenarios (RTT > 100ms):** Higher concurrency is essential.

## Bandwidth Ceilings

| Layer | Typical Ceiling | Bottleneck When |
|---|---|---|
| Client NIC | 1–100 Gbps | Multi-stream to fill |
| Client Disk | 50–500 MB/s (HDD), 500–5000 MB/s (SSD) | Random reads for multipart |
| Client CPU | Varies | TLS encryption bound |
| Network Path | Varies by RTT | BDP not filled |
| Provider | Varies by tier/region | Provider rate limits |

## Diagnostic Formula

```
Efficiency = ObservedThroughput / ExpectedThroughput

If Efficiency < 0.3:
    Likely: misconfiguration, throttling, or client bottleneck

If 0.3 ≤ Efficiency < 0.7:
    Likely: suboptimal tuning (concurrency, part size)

If Efficiency ≥ 0.7:
    Likely: within expected range; marginal improvements possible
```

## What to Measure

For a complete throughput model:
1. RTT to endpoint (minimum latency floor).
2. Single-connection throughput (TCP window scaling).
3. Multi-connection throughput (find concurrency ceiling).
4. Throttling onset point (concurrency where 429s begin).
5. Client resource utilization at each concurrency level.

## QPS vs In-Flight Concurrency

A critical distinction often conflated in performance diagnosis:

| Metric | Definition | What It Measures |
|--------|-----------|-----------------|
| **QPS (每秒请求数)** | Requests completed per second | Throughput rate — how fast work flows through |
| **In-Flight Concurrency (在途并发)** | Requests active at a single moment | Connection pool pressure — how many concurrent connections are open |

**Example:**
- 100 requests/sec (QPS), each takes 2 seconds → average in-flight = 200
- 100 requests/sec (QPS), each takes 10ms → average in-flight = 1

**Why it matters:**
- Connection pool exhaustion happens at high in-flight concurrency, not high QPS
- Client tools (awscli, s5cmd) have connection pool limits (typically 10-25)
- Server-side throttling may limit in-flight requests per connection/account
- When diagnosing "too slow" with high concurrency settings, check if in-flight exceeds the pool size

**Computing In-Flight (扫描线法):**
```
For each request:
  event_start = request_time           (+1 active)
  event_end   = request_time + latency (-1 active)

Sort all events by time, accumulate running sum.
Max(running_sum) = peak in-flight concurrency.

p95_in_flight = sustained load on connection pool.
```

**Diagnostic rule:** If p95_in_flight > connection_pool_size, TCP connect overhead dominates.
Reduce concurrency or increase pool size.
