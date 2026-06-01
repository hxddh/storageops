# Triage Questions

## Ask first
1. What exact error code or message do you see?
2. Which tool/SDK/version produced it?
3. Which provider and endpoint are involved?
4. When did it start and is it persistent or intermittent?
5. Is production traffic, data integrity, or security affected?

## Domain-specific follow-ups
- Permissions: principal ARN, action, bucket/key, policy snippets.
- Performance: object size/count, concurrency, region/path, timing sample.
- Protocol: signed request details, endpoint style, provider, SDK version.
- Network: DNS result, TLS error, source network, proxy/VPC endpoint.
- Cost: inventory summary, request counts, lifecycle rules.
