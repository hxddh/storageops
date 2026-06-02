# Cost Attribution Assumptions

last_verified: 2026-06-02

Access logs can support request and egress attribution, but they are not a
pricing source. Use logs to count operations, bytes, requesters, and time
windows; use current provider pricing or billing exports to convert those counts
into money.

## Must Confirm

- provider, region, and bucket location
- destination type for bytes sent: same-region, cross-region, internet, CDN, or
  private network
- request pricing for each operation class
- whether failed requests are billable for the provider
- whether discounts, commitments, taxes, or support fees are in scope

## Safe Output Pattern

- Report counts and proportions from logs first.
- If pricing is unconfirmed, say "cost driver" rather than quoting a dollar
  amount.
- If pricing is confirmed, show the pricing date and formula.
- Route storage-class questions to `storageops-lifecycle-cost`.
