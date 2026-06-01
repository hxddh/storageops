# Bandwidth Estimation

## When to read
Use when estimating migration time or explaining slow transfer rates.

## Formula
Estimated hours = total_bits / effective_bits_per_second / 3600.

Apply overhead for TLS/TCP retries, small files, and throttling. Validate against an actual dry-run sample before committing to a schedule.
