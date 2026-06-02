# Egress Cost Assumptions

last_verified: 2026-06-02

Migration cost estimates are sensitive to provider, region, destination, transfer
path, and negotiated pricing. Keep concrete prices out of runtime instructions
unless the user provides current pricing or a billing export.

## Must Confirm

- source provider and source region
- destination provider, destination region, and network path
- whether the transfer is internet egress, private link, same-cloud, or
  provider-managed transfer
- request pricing for LIST, GET, PUT, COPY, and multipart operations
- compute cost for transfer workers and any managed migration service
- retry rate, failed-request billing, and expected re-transfer volume

## Estimate Shape

```text
total = source egress + destination ingress/request cost + transfer compute +
        retry overhead + verification cost
```

State uncertainty explicitly. When pricing is not confirmed, provide the
measurement plan and cost drivers instead of a concrete dollar estimate.
