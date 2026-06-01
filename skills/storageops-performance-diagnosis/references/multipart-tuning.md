# Multipart Upload Tuning

## Key Parameters

### Part Size
- **AWS S3:** 5 MB min (except last part), 5 GB max.
- **Typical default:** 5–16 MB depending on tool.
- **Small parts (1–5 MB):** More parts → more HTTP requests → more overhead. Better for lossy networks (less to retry).
- **Large parts (16–100 MB):** Fewer parts → less overhead. Higher retry cost if a part fails. Better for stable networks.

### Concurrency (Parallel Part Uploads)
- Number of parts uploaded simultaneously.
- **Too low:** Underutilized bandwidth. Upload time = total_data / (concurrency × per_part_throughput).
- **Too high:** Server-side throttling (429). Connection pool exhaustion. Client CPU/memory pressure.

### Multipart Threshold
- Files below this threshold use single PUT.
- Files above use multipart upload.
- **Typical default:** 8 MB (awscli), 200 MB (rclone).
- Below 5 MB: single PUT always (AWS S3 minimum part size).

## The Bandwidth-Delay Product

The optimal concurrency for filling a network pipe:

```
BDP = Bandwidth (Mbps) × RTT (seconds) / 8 (bytes)
Concurrency_needed = BDP / PartSize
```

Example:
- 1000 Mbps, 50ms RTT → BDP = 1000 × 0.05 / 8 = 6.25 MB
- Part size 5 MB → 6.25 / 5 ≈ 2 concurrent parts to fill the pipe.
- Part size 1 MB → 7 concurrent parts.

## Optimization by Workload

### High-Bandwidth, Low-Latency (e.g., within same region)
- Large part size (16–64 MB).
- Moderate concurrency (4–8).
- Bottleneck: per-request overhead, not bandwidth.

### High-Bandwidth, High-Latency (e.g., cross-region, cross-cloud)
- Large part size (16–32 MB).
- High concurrency (8–20).
- Bottleneck: BDP, need many concurrent transfers to fill pipe.

### Low-Bandwidth, High-Latency
- Small part size (5–8 MB).
- Low concurrency (1–4).
- Large parts waste time on a slow link.

### Unstable Network
- Small part size (5–8 MB).
- Moderate concurrency (4–8).
- Retries are cheap with small parts.

## Tool-Specific Tuning

### awscli
```
aws configure set s3.max_concurrent_requests 20
aws configure set s3.multipart_threshold 64MB
aws configure set s3.multipart_chunksize 16MB
```

### rclone
```
--s3-chunk-size 16M
--s3-upload-concurrency 8
--s3-upload-cutoff 64M
```

### s5cmd
```
--part-size 16M
--concurrency 8
```

## Tuning Methodology

1. Measure baseline throughput with default settings.
2. Test with different part sizes (5M, 8M, 16M, 32M, 64M).
3. Test with different concurrency (1, 2, 4, 8, 16, 32).
4. Record errors (especially 429) at each concurrency level.
5. Find the concurrency just below the throttling threshold.
6. Validate with production-like workload.
