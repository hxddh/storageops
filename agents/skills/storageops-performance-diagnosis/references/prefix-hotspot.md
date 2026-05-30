# Prefix Hotspot Analysis

## Background

S3-compatible object storage distributes objects across backend partitions based on key
prefixes. High request rates to objects sharing the same partition can trigger rate limiting.

## How Partitioning Works (Conceptual)

- Objects are distributed across partitions based on the key prefix hash.
- AWS S3 dynamically splits partitions when request rates exceed a threshold.
- S3-compatible providers may have different partition models.

## Hotspot Patterns

### 1. Sequential Key Prefixes
Keys like:
```
logs/2024-01-01-000001.log
logs/2024-01-01-000002.log
logs/2024-01-01-000003.log
```
All share the prefix `logs/2024-01-01-`. If the partition key is derived from
the prefix, these all land on the same partition.

### 2. Date-Based Prefixes (Current Date)
```
bucket/2024-06-15/object-1
bucket/2024-06-15/object-2
```
All writes for the current date hit the same partition. This is a classic hotspot.

### 3. Reverse Key Strategy (AWS S3 Recommendation)
```
bucket/object-1-2024-06-15
bucket/object-2-2024-06-15
```
By putting the unique part first, objects distribute across more partitions.

### 4. Hash Prefix Strategy
```
bucket/<md5-prefix>/object-1
```
Prepend a hash to evenly distribute writes.

## Symptoms of Prefix Hotspot

- 429 / SlowDown errors on specific prefixes.
- Performance degrades at high throughput for objects with similar prefixes.
- Different prefixes have different throughput ceilings.
- Burst of errors during peak write times for date-prefixed keys.

## Diagnostic Approach

1. **Identify the key naming pattern.**
2. **Check if errors cluster on specific prefixes.**
3. **Compare throughput for hotspot prefixes vs random prefixes.**
4. **If possible, test with randomized key prefixes and compare performance.**

## Mitigation

1. **Key design:** Use high-cardinality leading characters (e.g., reversed timestamps, hash prefixes).
2. **Workload spreading:** Distribute writes across multiple prefixes.
3. **Rate limiting client-side:** Implement client-side rate limiting with jitter.
4. **Provider-specific:** Some providers have different partition models — consult provider documentation.

## Note for v0.1

Without real-provider access, hotspot analysis is based on:
- Error code patterns (429/SlowDown clustering).
- Key prefix correlation in debug logs.
- Documented partition models for the specific provider.
