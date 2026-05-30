# Case: VPC Endpoint DNS Not Resolving

## Situation

A user has created an S3 VPC Gateway endpoint inside their VPC, expecting S3 traffic to route
through the VPC endpoint instead of the public internet. However, DNS resolution for
`s3.amazonaws.com` still returns a public IP address, causing traffic to leave the VPC.

## Root Cause

The VPC endpoint is a **Gateway** type endpoint with no route table associations and
`PrivateDnsEnabled: false`. For Gateway endpoints, private DNS is not a per-endpoint setting —
instead, the route table must have a route to the endpoint. Without a route table entry, traffic
goes via the internet gateway/NAT gateway instead.

## Expected Diagnosis

- Category: network_endpoint_access
- Subcategory: VPC endpoint routing
- Root cause: VPC endpoint route table not associated, so traffic bypasses the endpoint
- Confidence: high
