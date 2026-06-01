# Case: Cross-Region Transfer Slow Due to RTT

## Summary
Cross-region S3 transfers from us-east-1 to ap-southeast-1 achieve only 3.2 MiB/s
against a 1 Gbps link. Root cause is high RTT (~192ms) combined with a small default
TCP window (64 KB), limiting in-flight data to ~333 KB instead of the ~24 MB
needed to saturate the link.

## Domain
`performance_throughput` — WAN latency, TCP window, parallel upload optimization

## Root Cause
High RTT (192ms) × small TCP window (64 KB) = low throughput. Single-threaded transfer
cannot keep the WAN pipe full. Solution: parallel multipart uploads with s5cmd or
increased AWS CLI concurrency.

## What the Agent Should Diagnose
1. Identify the RTT as ~192ms (cross-region WAN latency)
2. Recognize bandwidth-delay product constraint limiting TCP throughput
3. Note single-threaded vs parallel throughput comparison (3.2 vs 87 MiB/s)
4. Recommend parallel transfers with s5cmd --numworkers or aws s3 cp --storage-class
   with increased multipart concurrency
