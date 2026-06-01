# Anomaly Detection Thresholds

Statistical thresholds used by the access log analyzer to determine whether a pattern is significant enough to flag.

## Hot Key Threshold

- **Definition**: A single object key receives ≥10% of total requests in the analysis window
- **Formula**: `key_request_count / total_requests ≥ 0.10`
- **Severity**:
  - 10-20%: Moderate hot key — may cause intermittent throttling under load
  - 20-40%: Severe hot key — expect consistent throttling
  - >40%: Critical hot key — request partitioning has failed; recommend CDN immediately

## Traffic Spike Threshold

- **Definition**: Hourly request count exceeds 2× the trailing average
- **Formula**: `hourly_count > 2 * avg(hourly_counts)`
- **Window**: Last 12 hours for short-term, 72 hours for baseline

## Error Rate Threshold

- **Definition**: Error rate exceeds baseline by >5 percentage points
- **Formula**: `(error_count / total) > (baseline_error_rate + 0.05)`
- **Baseline**: 1-2% error rate is normal for S3. >5% warrants investigation. >10% is critical.

## Throttle Rate Threshold

- **Definition**: 429/503 errors as percentage of total requests
- **Thresholds**:
  - <0.1%: Normal — occasional throttling is expected at scale
  - 0.1-1%: Elevated — hot key likely, investigate key distribution
  - 1-5%: Severe — active throttling impacting users
  - >5%: Critical — service degradation, immediate action needed

## Request Source Anomaly

- **Definition**: Single IP or user making >1% of total requests AND >90% error rate
- **Formula**: `ip_request_count / total > 0.01 AND ip_error_count / ip_request_count > 0.90`
- **Interpretation**: Likely unauthorized scan or misconfigured client

## LIST-to-GET Ratio Anomaly

- **Definition**: LIST operations exceed 50% of total operations
- **Normal ratio**: LIST < 2% of total operations (typical workload)
- **Formula**: `list_count / total_operations > 0.50`
- **Interpretation**: Client is listing excessively — cost impact or inefficient code

## Statistical Significance

- **Minimum sample size**: 1000 requests for reliable pattern detection
- **Confidence**: Increase with larger sample sizes (10K → medium confidence, 100K → high confidence)
- **Multiple anomaly types**: If 2+ anomaly types trigger simultaneously, compound severity
