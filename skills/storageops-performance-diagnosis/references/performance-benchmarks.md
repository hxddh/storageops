# Performance Benchmark Reference

## Typical Throughput by Scenario

All numbers are rough estimates assuming stable network with no throttling.
Actual values depend on provider, region, and client hardware.
Use as a sanity check — large deviations (5x+ below benchmark) warrant investigation.

### Single Object Throughput (1 large file)

| Object Size | Tool | Part Size | Concurrency | RTT 5ms | RTT 50ms | RTT 150ms |
|------------|------|-----------|-------------|---------|----------|-----------|
| 1 GB | awscli | 8 MB | 10 | 80-100 MB/s | 15-25 MB/s | 5-10 MB/s |
| 1 GB | rclone | 64 MB | 4 | 90-110 MB/s | 30-50 MB/s | 10-20 MB/s |
| 1 GB | s5cmd | 64 MB | 64 | 100-120 MB/s | 40-60 MB/s | 15-25 MB/s |
| 10 GB | rclone | 128 MB | 8 | 100-120 MB/s | 40-60 MB/s | 15-25 MB/s |
| 50 GB | rclone | 256 MB | 8 | 100-120 MB/s | 35-55 MB/s | 12-22 MB/s |

### Small File Throughput (1,000 files)

| File Size | Files | Tool | Concurrency | RTT 5ms | RTT 50ms |
|-----------|-------|------|-------------|---------|----------|
| 1 KB | 10,000 | s5cmd | 64 | 500-800 files/s | 50-100 files/s |
| 100 KB | 1,000 | awscli | 10 | 100-200 files/s | 20-40 files/s |
| 1 MB | 1,000 | rclone | 16 | 80-150 files/s | 15-30 files/s |
| 10 MB | 500 | s5cmd | 64 | 40-80 files/s | 10-25 files/s |

> Small files (< 1MB) are dominated by per-request overhead (TCP+TLS+HTTP), not bandwidth.
> Expected latency per small file = RTT + TLS_handshake + HeadObject/PutObject ~= 2×RTT + 50ms.

### Mount Operations (Local SSD vs Object Storage)

| Operation | Local SSD | Object Storage (50ms RTT) | Amplification |
|-----------|-----------|--------------------------|---------------|
| `git status` (10K files) | <1s | 500s+ | 500x+ |
| `ls -la` (1K files) | <0.1s | 3-5s | 30x+ |
| `npm install` (50K files) | 30-60s | 30-60min | 60x+ |
| Single file `stat()` | ~1μs | 50-100ms | 50,000x |
| `readdir` (1K files) | ~0.1ms | 100-500ms | 1,000x |

### Throttling Thresholds (Approximate)

| Provider | Account GET RPS | Account PUT RPS | Per-Prefix GET RPS | Recovery Behavior |
|----------|----------------|----------------|-------------------|-------------------|
| AWS S3 | >5,500/prefix (scaled) | >3,500/prefix (scaled) | 5,500 initially, scales with load | Exponential backoff, scales after sustained load |
| BOS | ~1,000/s account | ~500/s account | Varies by region | 10-30s recovery window |
| OSS | ~2,000/s account | ~1,000/s account | Varies by region | 5-15s recovery window |
| COS | ~1,500/s account | ~800/s account | Varies by region | 5-20s recovery window |
| MinIO | Hardware-bound | Hardware-bound | Hardware-bound | No built-in throttling |

> Numbers are approximate and may change. Always check provider documentation.
> Use `scripts/metadata-amplification-estimator.py` for mount scenario estimates.

## Using These Benchmarks

1. **Before diagnosing "slow":** Compare observed throughput to benchmark table.
2. **Efficiency ratio:** observed / benchmark. < 0.3 = severe issue. > 0.7 = within expected range.
3. **If far below benchmark:** Check RTT first (network), then throttling (429s), then client resources.
4. **If near benchmark:** Issue is workload design, not infrastructure — consider architectural changes.
