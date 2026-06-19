# VPC Endpoint Policy Diagnosis

A VPC endpoint policy is an extra, often-overlooked deny layer. It can block S3
access even when the IAM policy and bucket policy both allow the request — and the
symptom is "works from my laptop, 403 from inside the VPC".

## Two Endpoint Types

- **Gateway endpoint** (S3/DynamoDB): added to a route table; traffic to S3 stays
  on the AWS network. Has an attached **endpoint policy** (resource policy on the
  endpoint).
- **Interface endpoint** (PrivateLink): an ENI with a private IP; also supports an
  endpoint policy and uses private DNS.

Both carry an endpoint policy that defaults to "allow all", but is frequently
locked down to specific buckets, actions, or principals.

## Endpoint Policy vs Bucket Policy — They Stack

The endpoint policy and the bucket policy are evaluated **independently**, and the
request must pass both:

- **Endpoint policy**: "which S3 requests may traverse THIS endpoint." A request
  to a bucket not listed here is denied at the network boundary, regardless of IAM.
- **Bucket policy**: may itself REQUIRE the request to arrive via a specific
  endpoint using `aws:SourceVpce`, so requests over the public path are denied.

So there are two distinct failure modes:
1. Endpoint policy too narrow → denies a bucket the user IS allowed for.
2. Bucket policy demands a specific VPCE → denies traffic NOT coming through it
   (e.g. a NAT/public route, or a different endpoint).

## The Relevant Condition Keys

- `aws:SourceVpce` — the VPC endpoint ID the request came through (`vpce-...`).
- `aws:SourceVpc` — the VPC ID (`vpc-...`).
- `aws:SourceIp` — note: for requests via a gateway endpoint, the source IP is the
  **private** address, so public-IP allowlists will not match. Use SourceVpc/Vpce
  instead.

Example bucket policy that denies anything not coming through one endpoint:
```json
{
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": ["arn:aws:s3:::bucket", "arn:aws:s3:::bucket/*"],
  "Condition": {"StringNotEquals": {"aws:SourceVpce": "vpce-0123456789abcdef0"}}
}
```
A request from the right VPC but a different endpoint, or over the public path,
hits this Deny.

## Why IAM-Allowed Requests Still 403

- The endpoint policy lists only some buckets/actions; the target bucket or
  `s3:ListBucket` is missing from it.
- The endpoint policy restricts `Principal`/`PrincipalOrgID` and the caller is out.
- The bucket policy requires `aws:SourceVpce` and the instance is routing to S3 via
  NAT/IGW (public path) instead of the gateway endpoint.
- Multiple endpoints exist; the route table sends traffic through one the bucket
  policy does not trust.

## Verify (read-only)

```
# Endpoint policy and which buckets/conditions it permits
aws ec2 describe-vpc-endpoints --vpc-endpoint-ids vpce-... \
  --query 'VpcEndpoints[0].PolicyDocument'

# Is the gateway endpoint actually in the route table for this subnet?
aws ec2 describe-route-tables --route-table-ids rtb-...

# The bucket policy's SourceVpce/SourceVpc conditions
aws s3api get-bucket-policy --bucket <bucket> --query Policy --output text
```

For interface endpoints, also confirm private DNS is enabled and resolving, or the
client may reach S3 over the public path and miss the `SourceVpce` match.

## Diagnostic Order

1. Does the failure only happen from inside the VPC? → suspect endpoint policy.
2. Read the endpoint policy: is the bucket/action/principal allowed there?
3. Read the bucket policy: does it require a specific `aws:SourceVpce`/`SourceVpc`?
4. Confirm the route table actually sends S3 traffic through that endpoint.
5. For interface endpoints, confirm private DNS resolution.
