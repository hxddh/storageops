# Small File Performance

Small files (typically < 1 MB) have fundamentally different performance characteristics
from large files in object storage.

## Why Small Files Are Slow

### Per-Request Overhead
Each object operation incurs fixed overhead:
- **HTTP:** Headers (~500–1000 bytes), request line.
- **TCP:** Connection setup (SYN/SYN-ACK/ACK) if not reused.
- **TLS:** Handshake (2+ RTTs) if not resumed.
- **SigV4:** Signing computation per request.
- **Metadata:** Storage and retrieval of object metadata.

For a 100 KB file, the overhead can exceed the payload transfer time.

### Connection Overhead Without Reuse
Without connection pooling:
```
1000 files × (TCP + TLS + Request + Response + close)
      = 1000 × (1 RTT + 2 RTT + 0.5 RTT + 0.5 RTT)
      = 1000 × 4 RTT
```
At 50ms RTT: 200 seconds of connection overhead alone.

With connection reuse:
```
1 × (TCP + TLS) + 1000 × (Request + Response)
    = 4 RTT + 1000 × 1 RTT
    = 1004 RTT
```
At 50ms RTT: 50.2 seconds (4× improvement).

### Metadata Amplification
- Each HeadObject is a separate HTTP request.
- Stat-like operations on mounted filesystems → one HeadObject per file.
- Listing 10,000 files → multiple paginated ListObjects requests.

## Optimization Strategies

### 1. Connection Pooling
- Use HTTP keep-alive.
- Use a connection pool (e.g., boto3 `max_pool_connections`).
- Tools like s5cmd and rclone maintain persistent connections.

### 2. Batching / Multi-Object Operations
- S3 DeleteObjects: up to 1000 objects per request.
- Some providers support batch operations beyond S3 spec.
- rclone `--transfers` for parallel transfers.

### 3. Increase Concurrency
- Small files benefit from high concurrency (connection-level parallelism).
- Balance against server-side rate limits (429).
- Rule of thumb: 4× RTT × bandwidth / object_size ≈ optimal concurrency.

### 4. Reduce Metadata Operations
- rclone `--no-traverse` to skip directory listing optimization.
- rclone `--no-check-certificate` (careful: security risk).
- Cache object metadata locally.

### 5. Use Multipart for Medium Files
- For files 5–50 MB, multipart upload with 1–2 parts can be faster than single PUT due to parallel part computation.

## TAR/Aggregation Strategy

For static small files, consider:
- TAR → upload as single large object.
- ZIP → with on-demand extraction (if provider supports).
- Parquet/ORC for structured small data.

## Diagnostic Metrics

For small file workloads, measure:
- Operations per second (OPS), not MB/s.
- Average latency per operation (P50, P95, P99).
- Connection reuse ratio.
- Time spent in TCP+TLS handshake vs transfer.
