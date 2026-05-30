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
